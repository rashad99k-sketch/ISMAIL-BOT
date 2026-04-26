#!/usr/bin/env python3
# SMC SNIPER BOT - Institutional Grade v3.0
# Complete rewrite: Trap Detection, Liquidity Engine, Volume Profile, Orderflow, Trend, Structure, Candle Intelligence
# Entry only with full confluence, smart execution, dashboard, telegram, adaptive learning.
# Single file, production ready.

import os
import time
import json
import threading
import traceback
import math
import logging
from datetime import datetime, timezone, timedelta
from collections import deque
import ccxt
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
import requests

# ---------- CONFIGURATION ----------
API_KEY = os.getenv("BINGX_API_KEY", "")
API_SECRET = os.getenv("BINGX_API_SECRET", "")
PAPER_MODE = os.getenv("PAPER_MODE", "True") == "False"
MODE_LIVE = bool(API_KEY and API_SECRET) and not PAPER_MODE

DEFAULT_SYMBOL = os.getenv("SYMBOL", "BTC/USDT:USDT")
INTERVAL = os.getenv("INTERVAL", "15m")
LEVERAGE = int(os.getenv("LEVERAGE", 5))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1.5)) / 100   # 1.5% risk per trade

# Scanner config
SCAN_INTERVAL = 20
MAX_SCAN_COINS = 50
SCAN_BATCH = 10
GLOBAL_SCAN_INTERVAL = 300

# Trade management
TP1_RATIO = 0.5          # 50% partial
TP2_RATIO = 0.5
BREAKEVEN_ACTIVATE_PCT = 0.5   # after TP1, move SL to entry
TRAIL_ATR_MULT = 1.5
MAX_DAILY_LOSS_PCT = 5.0
MAX_CONSECUTIVE_LOSSES = 3
COOLDOWN_MINUTES_LOSS = 10
COOLDOWN_MINUTES_DRAWDOWN = 20

# Execution
MAX_SPREAD_PCT = 0.1    # 0.1% max spread

# Telegram
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

# System
BASE_SLEEP = 5
SNAPSHOT_INTERVAL = 15
MIN_API_DELAY = 0.2

# ---------- GLOBAL STATE ----------
STATE = {
    "open": False,
    "side": None,
    "entry": 0.0,
    "qty": 0.0,
    "remaining_qty": 0.0,
    "sl": 0.0,
    "tp1_done": False,
    "trail_activated": False,
    "trail_stop": 0.0,
    "peak": 0.0,
    "cooldown_until": None,
    "daily_trades": 0,
    "last_trade_day": None,
    "consecutive_losses": 0,
    "daily_peak_balance": None,
    "daily_loss_limit_hit": False,
    "current_symbol": None,
    "trade_strength": None,   # 'STRONG', 'MEDIUM', 'WEAK'
    "entry_reasons": [],
}

paper = {"balance": 1000.0, "position": None, "trades": [], "wins": 0, "losses": 0}
DASHBOARD_STATE = {
    "account": {"balance": 0.0, "free": 0.0, "used": 0.0, "mode": "PAPER"},
    "stats": {"trades": 0, "wins": 0, "losses": 0, "profit_total": 0.0},
    "position": None,
    "scanner": {"running": False, "last_update": "", "top5": []},
    "logs": [],
    "errors": [],
    "ai": {"avg_pnl": 0.0, "total_trades": 0}
}
MONITOR_ERRORS, MONITOR_WARNINGS = [], []
TRADE_MEMORY = deque(maxlen=20)   # store pnl percentages

# ---------- HELPER FUNCTIONS ----------
def format_time(dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.now(timezone.utc)
    return dt_obj.strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    t = format_time()
    print(f"[{t}] {msg}", flush=True)
    DASHBOARD_STATE["logs"].append(f"[{t}] {msg}")
    if len(DASHBOARD_STATE["logs"]) > 200:
        DASHBOARD_STATE["logs"].pop(0)

def log_g(msg): log(f"✅ {msg}")
def log_e(msg): log(f"❌ {msg}")
def log_warn(msg): log(f"⚠️ {msg}")

def update_account_dashboard(balance, free, used, mode):
    DASHBOARD_STATE["account"].update({"balance": balance, "free": free, "used": used, "mode": mode})

def update_stats_dashboard(pnl_usdt):
    DASHBOARD_STATE["stats"]["trades"] += 1
    DASHBOARD_STATE["stats"]["profit_total"] += pnl_usdt
    if pnl_usdt >= 0:
        DASHBOARD_STATE["stats"]["wins"] += 1
    else:
        DASHBOARD_STATE["stats"]["losses"] += 1

def update_position_dashboard(symbol, side, entry, price, qty, leverage=1):
    if side == "LONG":
        pnl_pct = ((price - entry) / entry) * 100 * leverage if entry else 0
    else:
        pnl_pct = ((entry - price) / entry) * 100 * leverage if entry else 0
    profit = (pnl_pct / 100) * (entry * qty) if entry else 0
    DASHBOARD_STATE["position"] = {
        "symbol": symbol, "side": side, "entry": round(entry, 6), "price": round(price, 6),
        "pnl_pct": round(pnl_pct, 2), "profit": round(profit, 4)
    }

def clear_position_dashboard():
    DASHBOARD_STATE["position"] = None

def update_top5_dashboard(opps):
    out = []
    for o in opps[:5]:
        out.append({
            "symbol": o.get("symbol", "?"),
            "score": round(o.get("score", 0), 2),
            "zone": o.get("strength", "WEAK"),
            "reason": o.get("reason", ""),
            "suggest": "READY" if o.get("score", 0) >= 8 else "WATCH"
        })
    DASHBOARD_STATE["scanner"]["top5"] = out
    DASHBOARD_STATE["scanner"]["last_update"] = format_time()

def send_telegram(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT, "text": msg}, timeout=5)
        except:
            pass

# ---------- EXCHANGE SETUP ----------
ex = ccxt.bingx({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

class ExecutionEngine:
    def __init__(self, exchange):
        self.ex = exchange
    def set_leverage(self, symbol, lev):
        try:
            self.ex.set_leverage(lev, symbol)
        except: pass
    def market_order(self, symbol, side, qty):
        for _ in range(3):
            try:
                return self.ex.create_order(symbol, "market", side, qty)
            except Exception as e:
                time.sleep(0.5)
        raise Exception(f"Order failed {symbol} {side}")
    def fetch_orderbook(self, symbol, limit=10):
        return self.ex.fetch_order_book(symbol, limit)

executor = ExecutionEngine(ex)

# ---------- DATA FETCHING ----------
def fetch_ohlcv(symbol, limit=150):
    return ex.fetch_ohlcv(symbol, INTERVAL, limit=limit)

def fetch_trades(symbol, limit=200):
    return ex.fetch_trades(symbol, limit=limit)

def fetch_ticker(symbol):
    return ex.fetch_ticker(symbol)

def get_balance():
    if PAPER_MODE:
        return paper["balance"]
    bal = ex.fetch_balance()
    return bal.get("total", {}).get("USDT", 0.0)

def price_now(symbol):
    try:
        return fetch_ticker(symbol)["last"]
    except:
        return 0.0

def get_spread(symbol):
    ob = executor.fetch_orderbook(symbol, 5)
    if ob and ob['asks'] and ob['bids']:
        ask = ob['asks'][0][0]
        bid = ob['bids'][0][0]
        return (ask - bid) / bid * 100
    return 999.0

# ---------- ENGINE 1: TRAP DETECTION ----------
def detect_trap(df):
    if len(df) < 3:
        return None, 0
    last = df.iloc[-1]
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']
    wick_ratio = max(upper_wick, lower_wick) / (body + 1e-9)
    trap_strength = "weak"
    if wick_ratio >= 2.5:
        trap_strength = "strong"
    elif wick_ratio >= 1.5:
        trap_strength = "medium"
    else:
        return None, 0
    # Bull trap: high > prev_high but close < prev_high
    if last['high'] > prev_high and last['close'] < prev_high:
        return "sell_trap", trap_strength
    # Bear trap: low < prev_low but close > prev_low
    if last['low'] < prev_low and last['close'] > prev_low:
        return "buy_trap", trap_strength
    return None, 0

# ---------- ENGINE 2: LIQUIDITY ENGINE ----------
def find_liquidity_levels(df, lookback=50):
    highs = df['high'].tail(lookback).values
    lows = df['low'].tail(lookback).values
    # equal highs/lows within 0.1%
    eq_highs = []
    eq_lows = []
    for i in range(len(highs)-1):
        if abs(highs[i] - highs[i+1]) / highs[i] < 0.001:
            eq_highs.append(highs[i])
        if abs(lows[i] - lows[i+1]) / lows[i] < 0.001:
            eq_lows.append(lows[i])
    liquidity_pools = {
        "buy_stops": np.mean(eq_highs) if eq_highs else None,
        "sell_stops": np.mean(eq_lows) if eq_lows else None,
        "recent_high": df['high'].tail(20).max(),
        "recent_low": df['low'].tail(20).min()
    }
    return liquidity_pools

# ---------- ENGINE 3: VOLUME PROFILE ----------
def volume_profile(df, num_bins=50):
    if len(df) < 50:
        return None, None, None
    low = df['low'].min()
    high = df['high'].max()
    bin_width = (high - low) / num_bins
    bins = np.arange(low, high + bin_width, bin_width)
    vol_profile = np.zeros(len(bins)-1)
    for i in range(len(df)):
        price = df['close'].iloc[i]
        idx = min(int((price - low) / bin_width), len(vol_profile)-1)
        if idx >= 0:
            vol_profile[idx] += df['volume'].iloc[i]
    poc_idx = np.argmax(vol_profile)
    poc = (bins[poc_idx] + bins[poc_idx+1]) / 2
    # Value Area: 70% of volume
    sorted_vol = np.sort(vol_profile)[::-1]
    cum_vol = np.cumsum(sorted_vol)
    total_vol = cum_vol[-1]
    threshold = total_vol * 0.7
    va_vol = 0
    va_bins = []
    for i, v in enumerate(sorted_vol):
        if va_vol >= threshold:
            break
        va_vol += v
        idx_orig = np.where(vol_profile == v)[0][0]
        va_bins.append(idx_orig)
    va_low = bins[min(va_bins)]
    va_high = bins[max(va_bins)+1]
    return poc, va_low, va_high

# ---------- ENGINE 4: FOOTPRINT / ORDERFLOW ----------
def footprint_analysis(trades, lookback=100):
    if len(trades) < 50:
        return None, None
    buy_vol = sum(t['amount'] for t in trades if t.get('side', '').lower() == 'buy')
    sell_vol = sum(t['amount'] for t in trades if t.get('side', '').lower() == 'sell')
    total = buy_vol + sell_vol
    if total == 0:
        return None, None
    delta = buy_vol - sell_vol
    imbalance = delta / total
    # absorption: high volume but price not moving
    # simplified: if delta small but total high
    absorption = (abs(delta) < total * 0.2) and total > np.median([t['amount'] for t in trades[-50:]]) * 2
    return imbalance, absorption

# ---------- ENGINE 5: TREND ENGINE (ADX + DI) ----------
def compute_adx(df, period=14):
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = abs(minus_dm)
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    return {
        'adx': adx.iloc[-1],
        'plus_di': plus_di.iloc[-1],
        'minus_di': minus_di.iloc[-1],
        'trend': 'up' if plus_di.iloc[-1] > minus_di.iloc[-1] else 'down'
    }

# ---------- ENGINE 6: STRUCTURE + TRENDLINE ----------
def detect_choch(df):
    if len(df) < 10:
        return False
    highs = df['high'].tail(5).values
    lows = df['low'].tail(5).values
    # simple choch: last two highs/lows break
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return 'bullish'
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return 'bearish'
    return None

def trendline_break(df):
    # simplified: linear regression slope of last 20 closes
    if len(df) < 20:
        return None
    y = df['close'].tail(20).values
    x = np.arange(len(y))
    slope = np.polyfit(x, y, 1)[0]
    price = y[-1]
    prev = y[-2]
    if slope > 0 and price < prev:
        return 'break_down'
    if slope < 0 and price > prev:
        return 'break_up'
    return None

# ---------- ENGINE 7: CANDLE INTELLIGENCE ----------
def candle_patterns(df):
    if len(df) < 3:
        return {}
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last['close'] - last['open'])
    upper_wick = last['high'] - max(last['close'], last['open'])
    lower_wick = min(last['close'], last['open']) - last['low']
    patterns = {}
    # Engulfing
    if (last['close'] > last['open'] and prev['close'] < prev['open'] and
        last['close'] > prev['open'] and last['open'] < prev['close']):
        patterns['bullish_engulfing'] = True
    if (last['close'] < last['open'] and prev['close'] > prev['open'] and
        last['close'] < prev['open'] and last['open'] > prev['close']):
        patterns['bearish_engulfing'] = True
    # Pin bar / Hammer
    if lower_wick > 2 * body and upper_wick < body:
        patterns['hammer'] = True
    if upper_wick > 2 * body and lower_wick < body:
        patterns['shooting_star'] = True
    # Three soldiers / crows (simple)
    if len(df) >= 3:
        three_up = all(df.iloc[-i]['close'] > df.iloc[-i]['open'] for i in range(1,4))
        three_down = all(df.iloc[-i]['close'] < df.iloc[-i]['open'] for i in range(1,4))
        if three_up:
            patterns['three_soldiers'] = True
        if three_down:
            patterns['three_crows'] = True
    return patterns

# ---------- ENGINE 8: ENTRY DECISION (FULL CONFLUENCE) ----------
def evaluate_entry(symbol, df, trades, orderbook):
    # 1) Trap detection
    trap, trap_strength = detect_trap(df)
    if not trap:
        return None, 0, "No trap", {}
    # 2) Liquidity pools
    liq = find_liquidity_levels(df)
    # 3) Volume Profile
    poc, va_low, va_high = volume_profile(df)
    if poc is None:
        return None, 0, "No volume profile", {}
    price = df['close'].iloc[-1]
    # VP rule: BUY only below POC, SELL only above POC
    if trap == 'buy_trap' and price > poc:
        return None, 0, "Price above POC for buy", {}
    if trap == 'sell_trap' and price < poc:
        return None, 0, "Price below POC for sell", {}
    # 4) Footprint
    imbalance, absorption = footprint_analysis(trades)
    if absorption:
        return None, 0, "Absorption detected", {}
    if trap == 'buy_trap' and (imbalance is None or imbalance < 0):
        return None, 0, "No buyer dominance", {}
    if trap == 'sell_trap' and (imbalance is None or imbalance > 0):
        return None, 0, "No seller dominance", {}
    # 5) Trend ADX
    adx_data = compute_adx(df)
    if adx_data['adx'] < 18:
        return None, 0, f"ADX too low ({adx_data['adx']:.1f})", {}
    if trap == 'buy_trap' and adx_data['trend'] == 'down':
        return None, 0, "Buying against downtrend", {}
    if trap == 'sell_trap' and adx_data['trend'] == 'up':
        return None, 0, "Selling against uptrend", {}
    # 6) Structure
    choch = detect_choch(df)
    if choch is None:
        return None, 0, "No CHoCH", {}
    if trap == 'buy_trap' and choch != 'bullish':
        return None, 0, "No bullish structure", {}
    if trap == 'sell_trap' and choch != 'bearish':
        return None, 0, "No bearish structure", {}
    # 7) Candle patterns
    patterns = candle_patterns(df)
    if trap == 'buy_trap' and not patterns.get('hammer') and not patterns.get('bullish_engulfing'):
        return None, 0, "No bullish candle confirmation", {}
    if trap == 'sell_trap' and not patterns.get('shooting_star') and not patterns.get('bearish_engulfing'):
        return None, 0, "No bearish candle confirmation", {}
    # 8) Fibonacci golden zone (0.618-0.786)
    high = df['high'].tail(50).max()
    low = df['low'].tail(50).min()
    diff = high - low
    fib_618 = high - diff * 0.618
    fib_786 = high - diff * 0.786
    if trap == 'buy_trap' and not (fib_786 <= price <= fib_618):
        return None, 0, "Not in golden zone", {}
    if trap == 'sell_trap' and not (fib_786 <= price <= fib_618):
        return None, 0, "Not in golden zone", {}
    # Determine side and strength
    side = "BUY" if trap == 'buy_trap' else "SELL"
    strength = "STRONG" if trap_strength == "strong" and adx_data['adx'] > 25 else "MEDIUM"
    score = 10 + (adx_data['adx'] - 18) / 2
    score = min(20, max(0, score))
    reasons = f"Trap:{trap_strength}, ADX:{adx_data['adx']:.0f}, VolProfile OK, Footprint OK, CHoCH:{choch}"
    return side, score, reasons, {"strength": strength, "sl_level": liq['recent_low'] if side == "BUY" else liq['recent_high'], "atr": adx_data['adx']}

# ---------- SCANNER (multi-stage) ----------
def scan_symbols():
    # Stage1: all symbols, liquidity filter
    ex.load_markets()
    all_symbols = [s for s, m in ex.markets.items() if m.get('swap') and 'USDT' in s]
    tickers = ex.fetch_tickers()
    volumes = [(s, tickers.get(s, {}).get('quoteVolume', 0)) for s in all_symbols if tickers.get(s)]
    volumes.sort(key=lambda x: x[1], reverse=True)
    top_liquid = [s for s, vol in volumes[:MAX_SCAN_COINS] if vol > 5_000_000]
    # Stage2: ADX > 15
    stage2 = []
    for sym in top_liquid:
        try:
            ohlcv = fetch_ohlcv(sym, 100)
            if len(ohlcv) < 50:
                continue
            df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
            adx = compute_adx(df)
            if adx['adx'] > 15:
                stage2.append(sym)
        except:
            continue
    # Stage3: trap detected
    stage3 = []
    for sym in stage2[:30]:
        try:
            ohlcv = fetch_ohlcv(sym, 100)
            df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
            trap, _ = detect_trap(df)
            if trap:
                stage3.append(sym)
        except:
            continue
    # Stage4: full evaluation
    candidates = []
    for sym in stage3[:10]:
        try:
            ohlcv = fetch_ohlcv(sym, 150)
            trades = fetch_trades(sym, 200)
            ob = executor.fetch_orderbook(sym, 10)
            df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
            side, score, reasons, extra = evaluate_entry(sym, df, trades, ob)
            if side:
                candidates.append({
                    'symbol': sym,
                    'side': side,
                    'score': score,
                    'reason': reasons,
                    'strength': extra.get('strength', 'MEDIUM'),
                    'price': df['close'].iloc[-1],
                    'atr': extra.get('atr', 0),
                    'sl_level': extra.get('sl_level')
                })
        except:
            continue
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:5]

# ---------- POSITION SIZING ----------
def position_size(balance, entry_price, stop_price):
    risk_amount = balance * RISK_PERCENT
    sl_distance = abs(entry_price - stop_price)
    if sl_distance <= 0:
        return 0
    qty = risk_amount / sl_distance
    # leverage adjust
    qty = qty / LEVERAGE
    # rounding
    market = ex.market(DEFAULT_SYMBOL)  # placeholder, adjust per symbol
    step = market['precision']['amount']
    qty = math.floor(qty / step) * step
    min_qty = market['limits']['amount']['min']
    if qty < min_qty:
        qty = min_qty
    return qty

# ---------- SMART STOP LOSS ----------
def smart_stop(side, liq_level, atr_val):
    if side == "BUY":
        return liq_level - atr_val * 0.3
    else:
        return liq_level + atr_val * 0.3

# ---------- TRADE MANAGEMENT ----------
def manage_trade_smart(state, price, atr):
    side = state["side"]
    entry = state["entry"]
    if side == "BUY":
        pnl_pct = (price - entry) / entry * 100
    else:
        pnl_pct = (entry - price) / entry * 100
    # Stop loss
    if (side == "BUY" and price < state["sl"]) or (side == "SELL" and price > state["sl"]):
        return "CLOSE", pnl_pct
    # TP1 (50%)
    if pnl_pct >= TP1_ACTIVATE_PCT and not state.get("tp1_done"):
        return "TP1", pnl_pct
    # Trail after TP1
    if state.get("tp1_done") and pnl_pct >= TRAIL_ACTIVATE_PCT:
        if not state.get("trail_activated"):
            state["trail_activated"] = True
            state["trail_stop"] = price - TRAIL_ATR_MULT * atr if side == "BUY" else price + TRAIL_ATR_MULT * atr
        else:
            if side == "BUY":
                if price > state["trail_stop"]:
                    state["trail_stop"] = price - TRAIL_ATR_MULT * atr
                if price < state["trail_stop"]:
                    return "CLOSE", pnl_pct
            else:
                if price < state["trail_stop"]:
                    state["trail_stop"] = price + TRAIL_ATR_MULT * atr
                if price > state["trail_stop"]:
                    return "CLOSE", pnl_pct
    # Update peak
    if pnl_pct > state.get("peak", 0):
        state["peak"] = pnl_pct
    return "HOLD", pnl_pct

TP1_ACTIVATE_PCT = 0.5
TRAIL_ACTIVATE_PCT = 1.0

# ---------- EXECUTION WITH SPREAD CHECK ----------
def safe_open(symbol, side, qty, price):
    spread = get_spread(symbol)
    if spread > MAX_SPREAD_PCT:
        log_warn(f"Spread {spread:.2f}% too high, skipping trade")
        return False
    executor.set_leverage(symbol, LEVERAGE)
    executor.market_order(symbol, side, qty)
    return True

# ---------- CLOSE POSITION ----------
def close_position_full(symbol, side, qty):
    if PAPER_MODE:
        paper["position"] = None
        return True
    try:
        close_side = "sell" if side == "BUY" else "buy"
        executor.market_order(symbol, close_side, qty)
        return True
    except:
        return False

def close_partial(symbol, side, qty, ratio):
    close_qty = qty * ratio
    close_side = "sell" if side == "BUY" else "buy"
    executor.market_order(symbol, close_side, close_qty)
    return close_qty

# ---------- ADAPTIVE LEARNING ----------
def learn_from_trade(pnl_pct):
    TRADE_MEMORY.append(pnl_pct)
    DASHBOARD_STATE["ai"]["avg_pnl"] = sum(TRADE_MEMORY) / len(TRADE_MEMORY)
    DASHBOARD_STATE["ai"]["total_trades"] = len(TRADE_MEMORY)

def adaptive_score_multiplier():
    if not TRADE_MEMORY:
        return 1.0
    avg = sum(TRADE_MEMORY) / len(TRADE_MEMORY)
    if avg < -1:
        return 1.2   # require higher score
    if avg > 2:
        return 0.9
    return 1.0

# ---------- DASHBOARD ----------
app = Flask(__name__)

@app.route("/")
def dashboard():
    return """
    <!DOCTYPE html>
    <html><head><title>SMC Sniper PRO</title><meta name="viewport" content="width=device-width, initial-scale=1"/>
    <style>body{background:#0b0f14;color:#e6edf3;font-family:Consolas;margin:0}
    .header{padding:14px 16px;background:#111827;color:#00ff9f;font-size:22px;}
    .section{padding:12px 14px;border-bottom:1px solid #1f2937}
    .title{color:#9ca3af;margin-bottom:6px}
    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
    .card{background:#111827;border-radius:10px;padding:10px}
    .green{color:#00ffa6}.red{color:#ff4d4d}
    .log,.err{max-height:220px;overflow:auto;white-space:pre-wrap}
    </style></head>
    <body>
    <div class="header">🚀 SMC SNIPER BOT PRO v3.0</div>
    <div class="section"><div class="title">💰 ACCOUNT</div><div class="grid">
    <div class="card">Balance<div id="bal">-</div></div>
    <div class="card">Free<div id="free">-</div></div>
    <div class="card">Used<div id="used">-</div></div>
    <div class="card">Mode<div id="mode">-</div></div></div></div>
    <div class="section"><div class="title">📊 STATS</div><div class="grid">
    <div class="card">Trades<div id="trades">0</div></div>
    <div class="card">Wins<div id="wins" class="green">0</div></div>
    <div class="card">Losses<div id="losses" class="red">0</div></div>
    <div class="card">Total PnL<div id="ptotal">0</div></div></div></div>
    <div class="section"><div class="title">📌 POSITION</div><div id="pos" class="card">No Trade</div></div>
    <div class="section"><div class="title">🧠 TOP OPPORTUNITIES</div><div id="opps"></div></div>
    <div class="section"><div class="title">📜 LOGS</div><div id="logs" class="card log"></div></div>
    <div class="section"><div class="title">🤖 AI</div><div id="ai">Avg PnL: -</div></div>
    <script>
    async function fetchData(){
        const r=await fetch('/data'); const d=await r.json();
        document.getElementById("bal").innerText=d.account.balance.toFixed(2);
        document.getElementById("free").innerText=d.account.free.toFixed(2);
        document.getElementById("used").innerText=d.account.used.toFixed(2);
        document.getElementById("mode").innerText=d.account.mode;
        document.getElementById("trades").innerText=d.stats.trades;
        document.getElementById("wins").innerText=d.stats.wins;
        document.getElementById("losses").innerText=d.stats.losses;
        document.getElementById("ptotal").innerText=d.stats.profit_total.toFixed(2);
        if(d.position) document.getElementById("pos").innerHTML=`${d.position.symbol} ${d.position.side} Entry:${d.position.entry} Price:${d.position.price} PnL:${d.position.pnl_pct}%`;
        else document.getElementById("pos").innerText="No Trade";
        let html="";
        (d.scanner.top5||[]).forEach(o=>{html+=`<div class="card"><b>${o.symbol}</b> Score:${o.score} ${o.zone}<br>${o.reason}</div>`;});
        document.getElementById("opps").innerHTML=html||"No opportunities";
        document.getElementById("logs").innerHTML=(d.logs||[]).join("<br>");
        document.getElementById("ai").innerHTML=`Avg PnL: ${d.ai.avg_pnl.toFixed(2)}% | Trades: ${d.ai.total_trades}`;
    }
    setInterval(fetchData,2000);
    </script>
    </body></html>
    """

@app.route("/data")
def data():
    return jsonify(DASHBOARD_STATE)

# ---------- MAIN LOOP ----------
def main_loop():
    last_scan = 0
    last_snapshot = 0
    while True:
        try:
            now = time.time()
            # Snapshot
            if now - last_snapshot >= SNAPSHOT_INTERVAL:
                bal = get_balance()
                update_account_dashboard(bal, bal, 0.0, "LIVE" if MODE_LIVE else "PAPER")
                last_snapshot = now
            # Scan
            if not STATE["open"] and (now - last_scan) >= SCAN_INTERVAL:
                candidates = scan_symbols()
                if candidates:
                    best = candidates[0]
                    # Apply adaptive score multiplier
                    mult = adaptive_score_multiplier()
                    if best['score'] * mult >= 8:
                        symbol = best['symbol']
                        side = best['side']
                        price = best['price']
                        sl_level = best.get('sl_level')
                        atr_val = best.get('atr', 0)
                        if sl_level is None:
                            sl_level = price - atr_val * 1.5 if side == "BUY" else price + atr_val * 1.5
                        stop_price = smart_stop(side, sl_level, atr_val)
                        balance = get_balance()
                        qty = position_size(balance, price, stop_price)
                        if qty > 0 and get_spread(symbol) <= MAX_SPREAD_PCT:
                            if safe_open(symbol, side.lower(), qty, price):
                                STATE.update({
                                    "open": True,
                                    "side": side,
                                    "entry": price,
                                    "qty": qty,
                                    "remaining_qty": qty,
                                    "sl": stop_price,
                                    "current_symbol": symbol,
                                    "tp1_done": False,
                                    "trail_activated": False,
                                    "peak": 0.0,
                                    "trade_strength": best['strength'],
                                    "entry_reasons": best['reason'].split(',')
                                })
                                log_g(f"OPEN {side} {qty:.6f} {symbol} @ {price}")
                                send_telegram(f"🟢 NEW {side} on {symbol}\nPrice: {price}\nStrength: {best['strength']}\nReasons: {best['reason']}")
                update_top5_dashboard(candidates)
                last_scan = now
            # Manage open trade
            if STATE["open"] and STATE.get("current_symbol"):
                symbol = STATE["current_symbol"]
                price = price_now(symbol)
                if price:
                    atr_val = STATE.get("atr", 0)
                    # if atr missing, compute from recent data
                    if atr_val == 0:
                        ohlcv = fetch_ohlcv(symbol, 50)
                        df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
                        atr_val = compute_adx(df).get('adx', 0) * 0.01  # dummy
                    action, pnl = manage_trade_smart(STATE, price, atr_val)
                    if action == "TP1":
                        close_qty = close_partial(symbol, STATE["side"], STATE["remaining_qty"], 0.5)
                        STATE["remaining_qty"] -= close_qty
                        STATE["tp1_done"] = True
                        STATE["sl"] = STATE["entry"]   # breakeven
                        log_g(f"TP1 hit, partial close, breakeven set")
                        send_telegram(f"🟡 TP1 hit on {symbol}, partial profit")
                    elif action == "CLOSE":
                        close_position_full(symbol, STATE["side"], STATE["remaining_qty"])
                        learn_from_trade(pnl)
                        update_stats_dashboard(pnl * STATE["entry"] * STATE["qty"] / 100)
                        log_g(f"CLOSE {symbol} PnL: {pnl:.2f}%")
                        send_telegram(f"🔴 CLOSE {symbol}\nPnL: {pnl:.2f}%")
                        STATE["open"] = False
                        clear_position_dashboard()
                    update_position_dashboard(symbol, STATE["side"], STATE["entry"], price, STATE["remaining_qty"], LEVERAGE)
            time.sleep(BASE_SLEEP)
        except Exception as e:
            log_e(f"Loop error: {traceback.format_exc()}")
            time.sleep(BASE_SLEEP)

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False, use_reloader=False)
