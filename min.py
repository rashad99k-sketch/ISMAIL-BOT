#!/usr/bin/env python3
# ====================================================================
# RF LIQUIDITY ENGINE v29 – TRADE COUNCIL EDITION
# [PRODUCTION READY] All features + Council-Based Trade Management
# ====================================================================

import os, time, json, threading, traceback, math, gc, random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from collections import deque
import queue as qlib
import copy
from dataclasses import dataclass, field

import ccxt
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
import requests

if 'log_execution' not in dir():
    def log_execution(msg, level="INFO", debounce_key=None, debounce_sec=60):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {msg}")
        try:
            if 'DASHBOARD_STATE' in globals() and DASHBOARD_STATE is not None:
                DASHBOARD_STATE["logs"].append(f"[{ts}] {msg}")
                if level == "ERROR": DASHBOARD_STATE["errors"].append(f"[{ts}] {msg}")
        except: pass

# ========== SMART MONEY ENGINE ==========
class SmartMoneyEngine:
    @staticmethod
    def _rsi(series, period=14):
        delta = series.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean(); avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    @staticmethod
    def analyze_smart_money(df):
        if df is None or df.empty: return SmartMoneyEngine._default_state()
        if not all(c in df.columns for c in ["close","high","low","volume"]): return SmartMoneyEngine._default_state()
        if len(df) < 20: return SmartMoneyEngine._default_state()
        close = df["close"]; volume = df["volume"]
        rsi = SmartMoneyEngine._rsi(close, 14)
        vol_ma = volume.rolling(20).mean()
        volume_impulse = volume / vol_ma.replace(0, np.nan)
        vwma = (close * volume).rolling(20).sum() / volume.rolling(20).sum()
        price_distance = ((close - vwma) / vwma.replace(0, np.nan)) * 100
        momentum = close.pct_change(5) * 100
        banker_pressure = (rsi * 0.35) + (volume_impulse * 15) + (momentum * 2) + (price_distance * 1.5)
        banker_pressure = banker_pressure.clip(0, 100)
        retailer_pressure = (100 - banker_pressure).clip(0, 100)
        hot_money_pressure = (abs(momentum) * 5).clip(0, 100)
        smart_money_dominant = banker_pressure.iloc[-1] > 52 and banker_pressure.iloc[-1] > retailer_pressure.iloc[-1] + 6
        retail_euphoria = retailer_pressure.iloc[-1] > 75
        distribution_risk = max(0, retailer_pressure.iloc[-1] - banker_pressure.iloc[-1])
        accumulation_strength = banker_pressure.iloc[-1]
        if banker_pressure.iloc[-1] > 60: institutional_bias = "BUY"
        elif retailer_pressure.iloc[-1] > 70: institutional_bias = "SELL"
        else: institutional_bias = "NEUTRAL"
        delta = banker_pressure.iloc[-1] - retailer_pressure.iloc[-1]
        if delta >= 30: institutional_bias_detailed = "STRONG_BUY"
        elif delta >= 12: institutional_bias_detailed = "BUY"
        elif delta >= 5: institutional_bias_detailed = "WEAK_BUY"
        elif delta <= -30: institutional_bias_detailed = "STRONG_SELL"
        elif delta <= -12: institutional_bias_detailed = "SELL"
        elif delta <= -5: institutional_bias_detailed = "WEAK_SELL"
        else: institutional_bias_detailed = "NEUTRAL"
        trend_quality = banker_pressure.iloc[-1] - retailer_pressure.iloc[-1]
        flow_alignment = (banker_pressure.iloc[-1] / (retailer_pressure.iloc[-1] + 1)) * 50
        def sfv(v):
            if pd.isna(v) or np.isinf(v): return 0.0
            return float(v)
        return {"banker_pressure": sfv(banker_pressure.iloc[-1]), "retailer_pressure": sfv(retailer_pressure.iloc[-1]),
                "hot_money_pressure": sfv(hot_money_pressure.iloc[-1]), "smart_money_dominant": bool(smart_money_dominant),
                "retail_euphoria": bool(retail_euphoria), "distribution_risk": sfv(distribution_risk),
                "accumulation_strength": sfv(accumulation_strength), "institutional_bias": institutional_bias,
                "institutional_bias_detailed": institutional_bias_detailed, "trend_quality": sfv(trend_quality),
                "flow_alignment": sfv(flow_alignment)}
    @staticmethod
    def _default_state():
        return {"banker_pressure": 50.0, "retailer_pressure": 50.0, "hot_money_pressure": 50.0,
                "smart_money_dominant": False, "retail_euphoria": False, "distribution_risk": 0.0,
                "accumulation_strength": 0.0, "institutional_bias": "NEUTRAL",
                "institutional_bias_detailed": "NEUTRAL", "trend_quality": 0.0, "flow_alignment": 25.0}

# ========== MOMENTUM FLOW ENGINE ==========
class MomentumFlowEngine:
    @staticmethod
    def _rsi(series, period=14):
        delta = series.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean(); avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    @staticmethod
    def analyze_momentum_flow(df):
        if df is None or df.empty: return MomentumFlowEngine._default_state()
        if not all(c in df.columns for c in ["close","high","low","volume"]): return MomentumFlowEngine._default_state()
        if len(df) < 20: return MomentumFlowEngine._default_state()
        close = df["close"]
        rsi = MomentumFlowEngine._rsi(close, 14)
        ema_fast = close.ewm(span=9).mean(); ema_slow = close.ewm(span=21).mean()
        momentum_spread = ((ema_fast - ema_slow) / ema_slow.replace(0, np.nan)) * 100
        norm_spread = max(-2.5, min(2.5, momentum_spread.iloc[-1])) / 2.5
        momentum_health = 50 + (norm_spread * 50)
        continuation_strength = min(100, max(0, abs(momentum_spread.iloc[-1]) * 20))
        trend_expansion = momentum_spread.iloc[-1] > 0.35
        momentum_decay = momentum_spread.iloc[-1] < 0.05
        climax_risk = max(0, rsi.iloc[-1] - 70) * 3
        exhaustion_risk = max(0, 40 - momentum_health)
        greed_state = (rsi.iloc[-1] > 75) and trend_expansion
        if momentum_spread.iloc[-1] > 0: flow_bias = "BUY"
        elif momentum_spread.iloc[-1] < 0: flow_bias = "SELL"
        else: flow_bias = "NEUTRAL"
        def sfv(v):
            if pd.isna(v) or np.isinf(v): return 0.0
            return float(v)
        return {"continuation_strength": sfv(continuation_strength), "momentum_health": sfv(momentum_health),
                "trend_expansion": bool(trend_expansion), "momentum_decay": bool(momentum_decay),
                "climax_risk": sfv(climax_risk), "exhaustion_risk": sfv(exhaustion_risk),
                "greed_state": bool(greed_state), "flow_bias": flow_bias}
    @staticmethod
    def _default_state():
        return {"continuation_strength": 0.0, "momentum_health": 50.0, "trend_expansion": False,
                "momentum_decay": False, "climax_risk": 0.0, "exhaustion_risk": 0.0,
                "greed_state": False, "flow_bias": "NEUTRAL"}

# ========== INSTITUTIONAL INTENT ENGINE ==========
class InstitutionalIntentEngine:
    @staticmethod
    def detect(df, ob=None, symbol=None):
        if df is None or len(df) < 30: return 0, "NEUTRAL", {}
        details = {}; score = 0
        price = df['close'].iloc[-1]
        pools = build_liquidity_pools(df)
        eq_high, eq_low = detect_equal_highs_lows(df, lookback=30)
        liq_score = 0
        if pools.get("high_pools") or pools.get("low_pools"): liq_score += 25
        if eq_high or eq_low: liq_score += 15
        recent_high = df['high'].iloc[-10:].max(); recent_low = df['low'].iloc[-10:].min()
        if abs(price - recent_high) / price < 0.002: liq_score += 10
        if abs(price - recent_low) / price < 0.002: liq_score += 10
        liq_score = min(100, liq_score)
        details['liquidity_score'] = liq_score; score += liq_score * 0.12
        absorption_score, is_abs = InstitutionalIntentEngine._detect_absorption_sequence(df)
        details['absorption_score'] = absorption_score; details['absorption'] = is_abs
        score += absorption_score * 0.15
        atr = compute_atr(df)
        atr_current = atr.iloc[-1]
        atr_ma = atr.rolling(20).mean().iloc[-1] if len(atr) >= 20 else atr_current
        atr_ratio = atr_current / atr_ma if atr_ma > 0 else 1.0
        bb_std = df['close'].rolling(20).std().iloc[-1]; bb_mid = df['close'].rolling(20).mean().iloc[-1]
        bb_width = (2 * bb_std) / bb_mid if bb_mid > 0 else 0.01
        compression = (atr_ratio < 0.8) and (bb_width < 0.05)
        vol_score = 85 if compression else (65 if atr_ratio < 0.9 else 40)
        details['volatility_score'] = vol_score; details['atr_ratio'] = round(atr_ratio, 2); details['bb_width'] = round(bb_width * 100, 2)
        score += vol_score * 0.10
        smart = SmartMoneyEngine.analyze_smart_money(df)
        banker = smart.get("banker_pressure", 50); retail = smart.get("retailer_pressure", 50)
        acc = smart.get("accumulation_strength", 0); dist = smart.get("distribution_risk", 0)
        pressure_diff = banker - retail
        if pressure_diff > 15: flow_score = 80; status_candidate = "ACCUMULATION"
        elif pressure_diff < -15: flow_score = 80; status_candidate = "DISTRIBUTION"
        else: flow_score = 50 + pressure_diff * 1.5; status_candidate = "NEUTRAL"
        if acc > 60: flow_score = min(100, flow_score + 15)
        if dist > 50: flow_score = max(0, flow_score - 20)
        details['flow_score'] = flow_score
        details['banker_pressure'] = round(banker, 1); details['retail_pressure'] = round(retail, 1)
        score += flow_score * 0.15
        struct_type, struct_score = InstitutionalIntentEngine._detect_fractal_structure(df)
        details['structure_type'] = struct_type; details['structure_score'] = struct_score
        score += struct_score * 0.12
        adx_series = compute_adx(df)
        adx_current = adx_series.iloc[-1] if len(adx_series) > 0 else 20
        adx_prev = adx_series.iloc[-2] if len(adx_series) > 1 else adx_current
        adx_slope = adx_current - adx_prev
        mom = MomentumFlowEngine.analyze_momentum_flow(df)
        mom_health = mom.get("momentum_health", 50); expansion = mom.get("trend_expansion", False)
        if adx_slope > 0 and expansion and mom_health > 55: mom_score = 85
        elif adx_slope > 0 and mom_health > 50: mom_score = 70
        elif mom_health > 60: mom_score = 60
        else: mom_score = 40
        details['momentum_score'] = mom_score; details['adx_slope'] = round(adx_slope, 2)
        score += mom_score * 0.15
        vol = df['volume']; vol_ma = vol.rolling(20).mean().iloc[-1]
        vol_ratio = vol.iloc[-1] / vol_ma if vol_ma > 0 else 1.0
        vol_accel = vol.iloc[-5:].mean() / (vol.iloc[-10:-5].mean() + 1e-9)
        if vol_ratio > 1.5 and vol_accel > 1.2: vol_score = 85
        elif vol_ratio > 1.2: vol_score = 65
        elif vol_ratio < 0.7: vol_score = 20
        else: vol_score = 50
        details['volume_score'] = vol_score; details['vol_ratio'] = round(vol_ratio, 2); details['vol_accel'] = round(vol_accel, 2)
        score += vol_score * 0.08
        narrative, narrative_score = InstitutionalIntentEngine._institutional_narrative(df, smart, pools, struct_type, price)
        details['narrative'] = narrative; details['narrative_score'] = narrative_score
        score += narrative_score * 0.13
        regime = MEMORY.get("regime", "RANGE")
        weights = InstitutionalIntentEngine._get_regime_weights(regime)
        final_score = (liq_score*weights['liquidity'] + absorption_score*weights['absorption'] +
                       vol_score*weights['volatility'] + flow_score*weights['institutional_flow'] +
                       struct_score*weights['structure'] + mom_score*weights['momentum'] +
                       vol_score*weights['volume'] + narrative_score*weights['narrative']) / 100
        final_score = max(0, min(100, final_score))
        if final_score >= 70:
            if pressure_diff > 10 or (acc > 50 and dist < 30): status = "ACCUMULATION"
            elif pressure_diff < -10 or (dist > 50 and acc < 30): status = "DISTRIBUTION"
            else: status = "NEUTRAL"
        else: status = "NEUTRAL"
        details['regime_weights'] = weights; details['regime'] = regime
        return round(final_score, 2), status, details
    @staticmethod
    def _detect_absorption_sequence(df, window=4):
        if len(df) < window: return 0, False
        last_n = df.iloc[-window:]
        vol_avg = last_n['volume'].mean(); overall_avg = df['volume'].iloc[-20:].mean()
        vol_ratio = vol_avg / overall_avg if overall_avg > 0 else 1.0
        br = []
        for i in range(window):
            c = last_n.iloc[i]; b = abs(c['close'] - c['open']); r = c['high'] - c['low']
            br.append(b / r if r > 0 else 1.0)
        avg_br = sum(br) / window
        is_abs = vol_ratio > 1.2 and avg_br < 0.35
        wick = 0
        for i in range(window):
            c = last_n.iloc[i]
            uw = c['high'] - max(c['open'], c['close']); lw = min(c['open'], c['close']) - c['low']
            if uw > (c['high'] - c['low']) * 0.4: wick += 1
            if lw > (c['high'] - c['low']) * 0.4: wick += 1
        wa = wick >= window * 0.75
        if is_abs and wa: return 80, True
        elif is_abs: return 60, True
        else: return max(0, 50 - (vol_ratio - 1) * 30), False
    @staticmethod
    def _detect_fractal_structure(df):
        if len(df) < 30: return "NONE", 0
        ih = df['high'].iloc[-6:-1].max(); il = df['low'].iloc[-6:-1].min()
        cc = df['close'].iloc[-1]
        eh = df['high'].iloc[-21:-1].max(); el = df['low'].iloc[-21:-1].min()
        if cc > eh or cc < el: return "EXTERNAL", 90
        elif cc > ih or cc < il: return "INTERNAL", 60
        else: return "NONE", 30
    @staticmethod
    def _institutional_narrative(df, smart, pools, struct_type, price):
        narr = []; conf = 0
        side = "BUY" if smart.get("institutional_bias") == "BUY" else "SELL"
        if side == "BUY" and pools.get("low_pools") and price < pools["low_pools"][0]:
            narr.append("Sweep of major low"); conf += 20
        if side == "SELL" and pools.get("high_pools") and price > pools["high_pools"][0]:
            narr.append("Sweep of major high"); conf += 20
        if smart.get("accumulation_strength", 0) > 60: narr.append("Accumulation strength"); conf += 15
        if struct_type in ("INTERNAL", "EXTERNAL"): narr.append(f"{struct_type} structure break"); conf += 15
        supports, resistances = get_clustered_zones(df, lookback=60)
        if side == "BUY" and resistances:
            nr = min([r for r in resistances if r > price], default=price*2)
            if (nr - price) / price > 0.03: narr.append("Room to run"); conf += 10
        if side == "SELL" and supports:
            ns = max([s for s in supports if s < price], default=price*0.5)
            if (price - ns) / price > 0.03: narr.append("Room to run"); conf += 10
        return " | ".join(narr) if narr else "NEUTRAL", min(100, conf)
    @staticmethod
    def _get_regime_weights(regime):
        if regime == "RANGE": return {'liquidity': 20, 'absorption': 18, 'volatility': 10, 'institutional_flow': 15, 'structure': 12, 'momentum': 5, 'volume': 8, 'narrative': 12}
        elif regime == "TREND": return {'liquidity': 12, 'absorption': 12, 'volatility': 10, 'institutional_flow': 18, 'structure': 15, 'momentum': 18, 'volume': 8, 'narrative': 7}
        elif regime == "NEWS": return {'liquidity': 10, 'absorption': 15, 'volatility': 5, 'institutional_flow': 20, 'structure': 10, 'momentum': 10, 'volume': 20, 'narrative': 10}
        return {k: 12.5 for k in ['liquidity','absorption','volatility','institutional_flow','structure','momentum','volume','narrative']}

# ========== DYNAMIC TRADE MANAGER (kept) ==========
class DynamicTradeManager:
    def __init__(self, symbol, side, entry, qty, atr, initial_sl, tp1, tp2):
        self.symbol=symbol; self.side=side; self.entry=entry; self.qty=qty
        self.atr=atr; self.sl=initial_sl; self.tp1=tp1; self.tp2=tp2
        self.tp1_hit=False; self.tp2_hit=False; self.trailing_activated=False
        self.trailing_stop=0.0; self.runner_active=False
        self.peak_price=entry; self.peak_roe=0.0; self.drawdown=0.0
        self.lifecycle="LIVE"; self.last_update=time.time()
        self.smart_exit_triggered=False; self.partial_closed=False
    def update(self, current_price, df, ob, atr):
        self.last_update=time.time()
        roe=self.calculate_roe(current_price)
        self.peak_price = max(self.peak_price,current_price) if self.side=="BUY" else min(self.peak_price,current_price)
        self.peak_roe=max(self.peak_roe,roe)
        self.drawdown=max(0,(self.peak_roe-roe) if self.peak_roe>0 else 0)
        if roe>0.4 and not self.trailing_activated:
            self.trailing_activated=True
            self.trailing_stop = current_price-atr*0.8 if self.side=="BUY" else current_price+atr*0.8
        if self.trailing_activated:
            if self.side=="BUY":
                ns=current_price-atr*1.2
                if ns>self.trailing_stop: self.trailing_stop=ns
            else:
                ns=current_price+atr*1.2
                if ns<self.trailing_stop: self.trailing_stop=ns
            if (self.side=="BUY" and current_price<=self.trailing_stop) or (self.side=="SELL" and current_price>=self.trailing_stop):
                self.lifecycle="SL_HIT"; return "EXIT"
        if not self.tp1_hit:
            if (self.side=="BUY" and current_price>=self.tp1) or (self.side=="SELL" and current_price<=self.tp1):
                self.tp1_hit=True; return "PARTIAL"
        if self.tp1_hit and not self.tp2_hit:
            if (self.side=="BUY" and current_price>=self.tp2) or (self.side=="SELL" and current_price<=self.tp2):
                self.tp2_hit=True; self.runner_active=True; return "TP2"
        if self.tp1_hit and self.runner_active and self.drawdown>3.0:
            if self.side=="BUY": self.trailing_stop=max(self.trailing_stop,current_price-atr*0.6)
            else: self.trailing_stop=min(self.trailing_stop,current_price+atr*0.6)
        if self.tp1_hit:
            smart=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
            if smart.get("distribution_risk",0)>60 and mom.get("momentum_decay",False):
                self.lifecycle="INSTITUTIONAL_EXIT"; return "EXIT"
        st,_=InstitutionalIntentEngine._detect_fractal_structure(df)
        if st=="EXTERNAL" and self.side=="BUY" and df['close'].iloc[-1]<df['close'].iloc[-3]: return "EXIT"
        if st=="EXTERNAL" and self.side=="SELL" and df['close'].iloc[-1]>df['close'].iloc[-3]: return "EXIT"
        return "HOLD"
    def calculate_roe(self, price):
        if self.side=="BUY": return ((price-self.entry)/self.entry)*100
        return ((self.entry-price)/self.entry)*100

# ========== WATCHLIST PRIORITY ==========
class WatchlistPriorityManager:
    @staticmethod
    def update_priorities():
        now=time.time(); wl=MEMORY.get("watchlist",{})
        for sym,entry in list(wl.items()):
            if now-entry.get("last_update",0)>3600: continue
            df=get_ohlcv_safe(sym,100)
            if df is None: continue
            isc,st,_=InstitutionalIntentEngine.detect(df,None,sym)
            if isc>60:
                entry["priority"]=isc; entry["intent_status"]=st; entry["priority_until"]=now+7200
        sw=sorted(wl.items(),key=lambda x:x[1].get("priority",0),reverse=True)
        MEMORY["watchlist"]=dict(sw)

# ========== TRADE STATE MACHINE ==========
class TradeStateMachine:
    STATES={"ACCUMULATION":0,"EXPANSION":1,"TREND_RIDE":2,"DISTRIBUTION":3,"EXHAUSTION":4,"FAKE_BREAKOUT":5,
            "MOMENTUM_COLLAPSE":6,"PANIC_EXIT":7,"RANGE_CHOP":8,"HEALTHY_PULLBACK":9,"PROFIT_DEFENSE":10,"LIQUIDITY_EXHAUSTION":11}
    def __init__(self):
        self.current_state="RANGE_CHOP"; self.last_state_change=0; self.state_confidence=0.0
    def update(self, smart, momentum, adx, regime):
        banker=smart.get("banker_pressure",50); retail=smart.get("retailer_pressure",50)
        dist_risk=smart.get("distribution_risk",0); accum=smart.get("accumulation_strength",0)
        mom_health=momentum.get("momentum_health",50); cont=momentum.get("continuation_strength",50)
        exh=momentum.get("exhaustion_risk",0); climax=momentum.get("climax_risk",0)
        expansion=momentum.get("trend_expansion",False); decay=momentum.get("momentum_decay",False)
        bd=smart.get("institutional_bias_detailed","NEUTRAL")
        if (bd in ("STRONG_SELL","STRONG_BUY") and dist_risk>75 and mom_health<15 and cont<20): ns="PANIC_EXIT"
        elif mom_health<15 and cont<25 and decay: ns="MOMENTUM_COLLAPSE"
        elif exh>70 or climax>75: ns="LIQUIDITY_EXHAUSTION"
        elif dist_risk>50 and banker<45 and mom_health<30: ns="PROFIT_DEFENSE"
        elif dist_risk>60 and banker<45: ns="DISTRIBUTION"
        elif banker>65 and dist_risk<25 and mom_health>40: ns="ACCUMULATION"
        elif adx>30 and expansion and cont>60 and mom_health>50: ns="EXPANSION"
        elif cont>75 and mom_health>60 and dist_risk<30: ns="TREND_RIDE"
        elif 20<=adx<=35 and mom_health>45 and not expansion and not decay and dist_risk<40: ns="HEALTHY_PULLBACK"
        elif retail>70 and banker<45 and climax>60: ns="FAKE_BREAKOUT"
        elif adx<22 or regime in ("CHOPPY","COMPRESSION"): ns="RANGE_CHOP"
        else: ns=self.current_state
        if ns!=self.current_state:
            self.last_state_change=time.time(); self.state_confidence=0.5
        else: self.state_confidence=min(1.0,self.state_confidence+0.05)
        self.current_state=ns
        return ns
    def get_trail_multiplier(self):
        return {"ACCUMULATION":3.0,"EXPANSION":3.5,"TREND_RIDE":4.0,"HEALTHY_PULLBACK":2.8,"PROFIT_DEFENSE":1.2,
                "DISTRIBUTION":1.2,"EXHAUSTION":1.0,"LIQUIDITY_EXHAUSTION":0.8,"FAKE_BREAKOUT":0.8,
                "MOMENTUM_COLLAPSE":0.6,"PANIC_EXIT":0.5,"RANGE_CHOP":1.5}.get(self.current_state,1.5)
    def should_delay_tp1(self): return self.current_state in ("ACCUMULATION","EXPANSION","TREND_RIDE","HEALTHY_PULLBACK")
    def should_aggressive_profit_lock(self): return self.current_state in ("EXHAUSTION","DISTRIBUTION","MOMENTUM_COLLAPSE","PROFIT_DEFENSE","LIQUIDITY_EXHAUSTION")
    def should_hard_exit(self): return self.current_state in ("PANIC_EXIT","MOMENTUM_COLLAPSE","LIQUIDITY_EXHAUSTION")
    def get_patience_level(self):
        if self.current_state in ("ACCUMULATION","EXPANSION","TREND_RIDE","HEALTHY_PULLBACK"): return "HIGH"
        elif self.current_state in ("DISTRIBUTION","EXHAUSTION","PROFIT_DEFENSE"): return "LOW"
        return "MEDIUM"

# ========== TRADE COUNCIL (v29) ==========
class CouncilAction(Enum):
    HOLD="HOLD"; MOVE_TO_BE="MOVE_TO_BE"; TIGHTEN_SL="TIGHTEN_SL"; PARTIAL_TP="PARTIAL_TP"
    ACTIVATE_RUNNER="ACTIVATE_RUNNER"; EXIT_FULL="EXIT_FULL"; VETO_EXIT="VETO_EXIT"

@dataclass
class CouncilVote:
    member: str; action: CouncilAction; confidence: float; reason: str; score_impact: float = 0.0

@dataclass
class CouncilContext:
    symbol: str; side: str; entry_price: float; entry_atr: float
    current_price: float; mark_price: float; current_atr: float
    roe_pct: float; peak_roe: float; drawdown_from_peak: float
    df: pd.DataFrame; ob: Optional[dict] = None
    tp1_hit: bool=False; tp2_hit: bool=False; trail_activated: bool=False
    trail_stop: float=0.0; entry_time: float=0.0; elapsed_minutes: float=0.0
    remaining_qty: float=0.0
    smart_money: dict=field(default_factory=dict); momentum: dict=field(default_factory=dict)
    regime: str="UNKNOWN"; trade_state: str="RANGE_CHOP"
    adx: float=20.0; adx_slope: float=0.0; plus_di: float=20.0; minus_di: float=20.0
    structure: str="NONE"; pullback_type: str="NO_PULLBACK"
    trend_health: int=5; trend_direction: str="NEUTRAL"
    nearest_opposing_zone: Optional[float]=None; zone_strength: float=0.0; is_at_opposing_zone: bool=False

@dataclass
class CouncilDecision:
    action: CouncilAction; confidence: float
    votes: List[CouncilVote]=field(default_factory=list); reason: str=""
    new_sl: Optional[float]=None; new_trail_stop: Optional[float]=None
    partial_ratio: float=0.0; exit_urgency: str="NORMAL"; members_summary: str=""

class TradeManagementCouncil:
    VETO_DRAWDOWN_PCT=3.5; PANIC_DRAWDOWN_PCT=5.0
    TP1_ROE_THRESHOLD=1.2; TP2_ROE_THRESHOLD=2.8; RUNNER_ROE_THRESHOLD=4.0

    @staticmethod
    def _trend_governor(ctx):
        df=ctx.df; side=ctx.side
        try:
            rh=df['high'].iloc[-10:].max(); rl=df['low'].iloc[-10:].min()
            ph=df['high'].iloc[-20:-10].max() if len(df)>=20 else rh
            pl=df['low'].iloc[-20:-10].min() if len(df)>=20 else rl
            hh=rh>ph; hl=rl>pl; lh=rh<ph; ll=rl<pl
            if hh and hl: st="BULLISH"
            elif lh and ll: st="BEARISH"
            else: st="NEUTRAL"
        except: st="NEUTRAL"
        if side=="BUY":
            if st=="BULLISH" and ctx.trend_health>=6: return CouncilVote("TrendGovernor",CouncilAction.HOLD,85,"HH/HL intact",2.0)
            elif st=="BEARISH" or ctx.trend_health<=3: return CouncilVote("TrendGovernor",CouncilAction.EXIT_FULL,80,f"Trend broken: {st}, health={ctx.trend_health}",-5.0)
            else: return CouncilVote("TrendGovernor",CouncilAction.TIGHTEN_SL,60,f"Trend weakening, health={ctx.trend_health}",-1.0)
        else:
            if st=="BEARISH" and ctx.trend_health>=6: return CouncilVote("TrendGovernor",CouncilAction.HOLD,85,"LH/LL intact",2.0)
            elif st=="BULLISH" or ctx.trend_health<=3: return CouncilVote("TrendGovernor",CouncilAction.EXIT_FULL,80,f"Trend broken: {st}, health={ctx.trend_health}",-5.0)
            else: return CouncilVote("TrendGovernor",CouncilAction.TIGHTEN_SL,60,f"Trend weakening, health={ctx.trend_health}",-1.0)

    @staticmethod
    def _liquidity_analyst(ctx):
        df=ctx.df; side=ctx.side; price=ctx.current_price
        try:
            rh=df['high'].iloc[-50:].max(); rl=df['low'].iloc[-50:].min()
            if len(df)>=3:
                last=df.iloc[-1]; prev=df.iloc[-2]
                if side=="BUY":
                    d=(rh-price)/price
                    if d<0.003: return CouncilVote("LiquidityAnalyst",CouncilAction.PARTIAL_TP,75,f"Approaching liquidity high ({d*100:.2f}%)",-2.0)
                    pm=df['low'].iloc[-5:-1].min() if len(df)>=6 else prev['low']
                    if prev['low']<pm and last['close']>prev['low']: return CouncilVote("LiquidityAnalyst",CouncilAction.HOLD,70,"Recent low sweep, bullish",1.5)
                else:
                    d=(price-rl)/price
                    if d<0.003: return CouncilVote("LiquidityAnalyst",CouncilAction.PARTIAL_TP,75,f"Approaching liquidity low ({d*100:.2f}%)",-2.0)
                    pm=df['high'].iloc[-5:-1].max() if len(df)>=6 else prev['high']
                    if prev['high']>pm and last['close']<prev['high']: return CouncilVote("LiquidityAnalyst",CouncilAction.HOLD,70,"Recent high sweep, bearish",1.5)
        except: pass
        return CouncilVote("LiquidityAnalyst",CouncilAction.HOLD,50,"No liquidity event",0.0)

    @staticmethod
    def _structure_analyst(ctx):
        st=ctx.structure; side=ctx.side
        if side=="BUY":
            if st=="bullish_shift": return CouncilVote("StructureAnalyst",CouncilAction.HOLD,80,"Bullish MSS",2.0)
            elif st=="bearish_shift": return CouncilVote("StructureAnalyst",CouncilAction.EXIT_FULL,85,"Bearish CHoCH against long",-4.0)
        else:
            if st=="bearish_shift": return CouncilVote("StructureAnalyst",CouncilAction.HOLD,80,"Bearish MSS",2.0)
            elif st=="bullish_shift": return CouncilVote("StructureAnalyst",CouncilAction.EXIT_FULL,85,"Bullish CHoCH against short",-4.0)
        return CouncilVote("StructureAnalyst",CouncilAction.HOLD,50,"No structure event",0.0)

    @staticmethod
    def _momentum_judge(ctx):
        adx=ctx.adx; slope=ctx.adx_slope; side=ctx.side; mom=ctx.momentum
        mh=mom.get("momentum_health",50); exh=mom.get("exhaustion_risk",0)
        clim=mom.get("climax_risk",0); decay=mom.get("momentum_decay",False)
        di_ok=(side=="BUY" and ctx.plus_di>ctx.minus_di) or (side=="SELL" and ctx.minus_di>ctx.plus_di)
        if exh>70 and decay: return CouncilVote("MomentumJudge",CouncilAction.EXIT_FULL,80,f"Momentum exhausted (exh={exh:.0f}, decay)",-4.0)
        if clim>70: return CouncilVote("MomentumJudge",CouncilAction.TIGHTEN_SL,75,f"Climax risk {clim:.0f}",-2.0)
        if adx>25 and slope>0 and di_ok and mh>55: return CouncilVote("MomentumJudge",CouncilAction.HOLD,80,f"ADX={adx:.1f} rising, DI aligned",2.5)
        if adx<18 or (slope<-2 and adx>20): return CouncilVote("MomentumJudge",CouncilAction.TIGHTEN_SL,65,f"ADX weak/falling ({adx:.1f}, slope={slope:.1f})",-1.5)
        if not di_ok: return CouncilVote("MomentumJudge",CouncilAction.TIGHTEN_SL,70,"DI flipped against position",-2.0)
        return CouncilVote("MomentumJudge",CouncilAction.HOLD,55,"Momentum neutral",0.0)

    @staticmethod
    def _volume_inspector(ctx):
        df=ctx.df
        if len(df)<20: return CouncilVote("VolumeInspector",CouncilAction.HOLD,50,"Insufficient volume data",0.0)
        vol=df['volume']; avg=vol.iloc[-20:].mean(); last=vol.iloc[-1]
        ratio=last/avg if avg>0 else 1.0; side=ctx.side
        pu=df['close'].iloc[-1]>df['close'].iloc[-2]
        if ratio<0.6: return CouncilVote("VolumeInspector",CouncilAction.TIGHTEN_SL,60,f"Volume dying ({ratio:.2f}x avg)",-1.0)
        if ratio>2.5:
            b=abs(df['close'].iloc[-1]-df['open'].iloc[-1]); r=df['high'].iloc[-1]-df['low'].iloc[-1]
            if r>0 and b/r<0.3: return CouncilVote("VolumeInspector",CouncilAction.PARTIAL_TP,70,f"Climax volume {ratio:.2f}x weak body",-1.5)
        if ratio>1.3 and ((side=="BUY" and pu) or (side=="SELL" and not pu)): return CouncilVote("VolumeInspector",CouncilAction.HOLD,70,f"Volume confirms ({ratio:.2f}x)",1.5)
        return CouncilVote("VolumeInspector",CouncilAction.HOLD,50,"Volume neutral",0.0)

    @staticmethod
    def _institutional_flow(ctx):
        sm=ctx.smart_money; side=ctx.side
        if not sm: return CouncilVote("InstitutionalFlow",CouncilAction.HOLD,50,"No institutional data",0.0)
        banker=sm.get("banker_pressure",50); retail=sm.get("retailer_pressure",50)
        dr=sm.get("distribution_risk",0); acc=sm.get("accumulation_strength",0)
        dom=sm.get("smart_money_dominant",False)
        if side=="BUY":
            if dr>65 and retail>banker: return CouncilVote("InstitutionalFlow",CouncilAction.EXIT_FULL,85,f"Distribution risk {dr:.0f}",-5.0)
            if dr>45: return CouncilVote("InstitutionalFlow",CouncilAction.PARTIAL_TP,70,f"Distribution risk rising ({dr:.0f})",-2.0)
            if banker>retail+10 and dom: return CouncilVote("InstitutionalFlow",CouncilAction.HOLD,80,"Institutional accumulation",2.0)
        else:
            if acc>65 and banker>retail: return CouncilVote("InstitutionalFlow",CouncilAction.EXIT_FULL,85,f"Accumulation {acc:.0f} against short",-5.0)
            if acc>45: return CouncilVote("InstitutionalFlow",CouncilAction.PARTIAL_TP,70,f"Accumulation rising ({acc:.0f})",-2.0)
            if retail>banker+10 and dom: return CouncilVote("InstitutionalFlow",CouncilAction.HOLD,80,"Institutional distribution",2.0)
        return CouncilVote("InstitutionalFlow",CouncilAction.HOLD,50,"Flow neutral",0.0)

    @staticmethod
    def _risk_officer(ctx):
        dd=ctx.drawdown_from_peak; roe=ctx.roe_pct
        if dd>=TradeManagementCouncil.PANIC_DRAWDOWN_PCT: return CouncilVote("RiskOfficer",CouncilAction.VETO_EXIT,100,f"PANIC drawdown {dd:.2f}% from peak",-10.0)
        if ctx.peak_roe>8 and dd>=TradeManagementCouncil.VETO_DRAWDOWN_PCT: return CouncilVote("RiskOfficer",CouncilAction.VETO_EXIT,95,f"Protect {ctx.peak_roe:.1f}% profit, dd {dd:.1f}%",-8.0)
        if roe<-2.0 and dd>=2.0: return CouncilVote("RiskOfficer",CouncilAction.EXIT_FULL,80,f"Loss {roe:.1f}% accelerating",-5.0)
        if ctx.is_at_opposing_zone and ctx.zone_strength>=6: return CouncilVote("RiskOfficer",CouncilAction.TIGHTEN_SL,80,f"At strong opposing zone (str={ctx.zone_strength:.1f})",-3.0)
        if roe>=TradeManagementCouncil.TP1_ROE_THRESHOLD and not ctx.tp1_hit: return CouncilVote("RiskOfficer",CouncilAction.MOVE_TO_BE,70,f"ROE {roe:.2f}% → lock BE",1.0)
        return CouncilVote("RiskOfficer",CouncilAction.HOLD,50,"Risk acceptable",0.0)

    @staticmethod
    def _profit_taker(ctx):
        roe=ctx.roe_pct; tp1=ctx.tp1_hit; tp2=ctx.tp2_hit
        th=ctx.trend_health
        cont=ctx.momentum.get("continuation_strength",50); mh=ctx.momentum.get("momentum_health",50)
        reg=ctx.regime
        if not tp1 and roe>=TradeManagementCouncil.TP1_ROE_THRESHOLD:
            if th>=8 and cont>70 and mh>60 and reg in ("STRONG_TREND","EXPANSION","TREND"):
                return CouncilVote("ProfitTaker",CouncilAction.ACTIVATE_RUNNER,75,f"Strong trend (h={th}, cont={cont:.0f}) → run",2.0)
            return CouncilVote("ProfitTaker",CouncilAction.PARTIAL_TP,80,f"TP1 at ROE {roe:.2f}%",2.0)
        if tp1 and not tp2 and roe>=TradeManagementCouncil.TP2_ROE_THRESHOLD:
            if th>=7 and cont>65: return CouncilVote("ProfitTaker",CouncilAction.ACTIVATE_RUNNER,75,"Trail for TP2 (strong trend)",2.0)
            return CouncilVote("ProfitTaker",CouncilAction.PARTIAL_TP,75,f"TP2 at ROE {roe:.2f}%",2.0)
        if tp2:
            if th<=4 or cont<40: return CouncilVote("ProfitTaker",CouncilAction.EXIT_FULL,80,f"Trend dying after TP2 (h={th}, cont={cont:.0f})",0.0)
            return CouncilVote("ProfitTaker",CouncilAction.HOLD,70,"Runner active",1.0)
        return CouncilVote("ProfitTaker",CouncilAction.HOLD,50,"Waiting for targets",0.0)

    @classmethod
    def convene(cls, ctx):
        votes=[cls._trend_governor(ctx),cls._liquidity_analyst(ctx),cls._structure_analyst(ctx),
               cls._momentum_judge(ctx),cls._volume_inspector(ctx),cls._institutional_flow(ctx),cls._profit_taker(ctx)]
        rv=cls._risk_officer(ctx)
        if rv.action==CouncilAction.VETO_EXIT:
            return cls._finalize(CouncilAction.EXIT_FULL,100,votes+[rv],f"🚨 RISK OFFICER VETO: {rv.reason}",exit_urgency="CRITICAL",ctx=ctx)
        ev=[v for v in votes if v.action==CouncilAction.EXIT_FULL]
        if len(ev)>=3 or (len(ev)>=2 and rv.action in (CouncilAction.EXIT_FULL,CouncilAction.VETO_EXIT)):
            reason=" | ".join([v.reason for v in ev[:3]])
            return cls._finalize(CouncilAction.EXIT_FULL,90,votes+[rv],f"🚪 Institutional exit: {reason}",exit_urgency="HIGH",ctx=ctx)
        pv=[v for v in votes if v.action==CouncilAction.PARTIAL_TP]
        if len(pv)>=2:
            reason=" | ".join([v.reason for v in pv[:2]])
            return cls._finalize(CouncilAction.PARTIAL_TP,80,votes+[rv],f"💰 Partial profit: {reason}",ctx=ctx,partial_ratio=0.5)
        tv=[v for v in votes if v.action==CouncilAction.TIGHTEN_SL]
        if len(tv)>=2 or rv.action==CouncilAction.TIGHTEN_SL:
            reason=" | ".join([v.reason for v in tv[:2]] or [rv.reason])
            return cls._finalize(CouncilAction.TIGHTEN_SL,75,votes+[rv],f"🔒 Tighten SL: {reason}",ctx=ctx)
        ruv=[v for v in votes if v.action==CouncilAction.ACTIVATE_RUNNER]
        if len(ruv)>=1 and ctx.trend_health>=7:
            return cls._finalize(CouncilAction.ACTIVATE_RUNNER,75,votes+[rv],f"🏃 Runner activated: {ruv[0].reason}",ctx=ctx)
        if rv.action==CouncilAction.MOVE_TO_BE:
            return cls._finalize(CouncilAction.MOVE_TO_BE,80,votes+[rv],f"🛡️ {rv.reason}",ctx=ctx)
        return cls._finalize(CouncilAction.HOLD,60,votes+[rv],"Consensus: hold position",ctx=ctx)

    @classmethod
    def _finalize(cls, action, confidence, votes, reason, ctx, partial_ratio=0.0, exit_urgency="NORMAL"):
        new_sl=None; new_trail=None
        if action==CouncilAction.MOVE_TO_BE: new_sl=ctx.entry_price
        elif action==CouncilAction.TIGHTEN_SL:
            atr=ctx.current_atr
            if ctx.side=="BUY":
                cand=ctx.current_price-atr*1.0
                new_sl=max(ctx.entry_price,cand,ctx.trail_stop)
            else:
                cand=ctx.current_price+atr*1.0
                tr=ctx.trail_stop if ctx.trail_stop>0 else ctx.entry_price
                new_sl=min(ctx.entry_price,cand,tr)
        summary=" | ".join([f"{v.member}:{v.action.value}({v.confidence:.0f})" for v in votes])
        return CouncilDecision(action=action,confidence=confidence,votes=votes,reason=reason,
                               new_sl=new_sl,new_trail_stop=new_trail,partial_ratio=partial_ratio,
                               exit_urgency=exit_urgency,members_summary=summary)

# ========== UNIFIED POSITION MANAGER ==========
class UnifiedPositionManager:
    def __init__(self, event_bus):
        self.event_bus=event_bus; self.council=TradeManagementCouncil()
        self.last_run=0.0; self.run_interval=3.0
        self.last_council_decision=None; self.last_log=0.0
        self.consecutive_exit_votes=0
    def _build_context(self):
        if not STATE.get("open") or not STATE.get("current_symbol"): return None
        symbol=STATE["current_symbol"]
        df_closed=get_ohlcv_safe(symbol,100)
        if df_closed is None or len(df_closed)<50: return None
        mark=STATE.get("mark_price") or get_ticker_safe(symbol)
        if not mark or mark<=0: return None
        df_live=get_live_hybrid_df(symbol,df_closed,mark)
        atr_now=compute_atr(df_live).iloc[-1] if len(df_live)>14 else mark*0.01
        pd_,md_,adx_now,adx_slope=get_di_components(df_live)
        if pd_ is None: pd_=20.0
        if md_ is None: md_=20.0
        if adx_now is None: adx_now=20.0
        if adx_slope is None: adx_slope=0.0
        sm=SmartMoneyEngine.analyze_smart_money(df_live)
        mom=MomentumFlowEngine.analyze_momentum_flow(df_live)
        reg=MarketRegimeClassifier.classify(df_live)
        struct=detect_structure_shift(df_live) or "NONE"
        pb=trend_engine.analyze_pullback(df_live,STATE["side"],atr_now)
        th=trend_engine.get_trend_health(df_live,STATE["side"])
        td=get_trend_direction(df_live)
        nz=None; zs=0.0; iaz=False
        try:
            nz,zt=find_nearest_opposing_zone(df_live,STATE["side"])
            if nz:
                dist=abs(mark-nz)/mark
                iaz=dist<0.003
                ob=get_orderbook_cached(symbol,10)
                zs=compute_opposing_zone_strength(df_live,ob,atr_now,STATE["side"],nz,zt)
        except: pass
        roe=STATE.get("roe_pct",0.0); peak=STATE.get("peak_roe",0.0)
        dd=max(0.0,peak-roe) if peak>0 else 0.0
        try:
            av=adx_now if adx_now else 20.0
            ns=_state_machine.update(sm,mom,av,reg)
            STATE["trade_state"]=ns
        except: pass
        return CouncilContext(symbol=symbol,side=STATE["side"],entry_price=STATE["entry"],
            entry_atr=STATE.get("entry_atr",atr_now),current_price=mark,mark_price=mark,current_atr=atr_now,
            roe_pct=roe,peak_roe=peak,drawdown_from_peak=dd,df=df_live,ob=None,
            tp1_hit=STATE.get("tp1_hit",False),tp2_hit=STATE.get("tp2_hit",False),
            trail_activated=STATE.get("trail_activated",False),trail_stop=STATE.get("trail_stop",0.0),
            entry_time=STATE.get("entry_time",time.time()),
            elapsed_minutes=(time.time()-STATE.get("entry_time",time.time()))/60,
            remaining_qty=STATE.get("remaining_qty",0),smart_money=sm,momentum=mom,regime=reg,
            trade_state=STATE.get("trade_state","RANGE_CHOP"),adx=adx_now,adx_slope=adx_slope,
            plus_di=pd_,minus_di=md_,structure=struct,pullback_type=pb,trend_health=th,
            trend_direction=td,nearest_opposing_zone=nz,zone_strength=zs,is_at_opposing_zone=iaz)
    def _apply_decision(self, d, ctx):
        action=d.action
        STATE["last_council_decision"]={"action":action.value,"confidence":d.confidence,"reason":d.reason,"votes":d.members_summary,"ts":time.time()}
        STATE["last_council_action"]=action.value
        STATE["last_council_reason"]=d.reason
        STATE["last_council_confidence"]=d.confidence
        if action==CouncilAction.EXIT_FULL:
            log_execution(f"🏛️ [COUNCIL] EXIT_FULL: {d.reason}","WARN")
            log_execution(f"    Votes: {d.members_summary}","INFO")
            close_position_full()
            self.event_bus.emit("lifecycle_change",TradeLifecycleState.CLOSED)
            DASHBOARD_STATE["live_trade_mode"]=False
            self.consecutive_exit_votes=0
            return
        if action==CouncilAction.PARTIAL_TP:
            ratio=d.partial_ratio or 0.5
            log_execution(f"🏛️ [COUNCIL] PARTIAL_TP {ratio*100:.0f}%: {d.reason}","SUCCESS")
            close_partial(ratio); STATE["tp1_hit"]=True; STATE["trail_activated"]=True
            if ctx.side=="BUY": STATE["synthetic_sl"]=max(STATE.get("synthetic_sl",0),ctx.entry_price)
            else:
                cur=STATE.get("synthetic_sl",0)
                STATE["synthetic_sl"]=ctx.entry_price if cur==0 else min(cur,ctx.entry_price)
            STATE["trail_stop"]=STATE["synthetic_sl"]
            return
        if action==CouncilAction.MOVE_TO_BE:
            ns=d.new_sl if d.new_sl is not None else ctx.entry_price
            os=STATE.get("synthetic_sl",0)
            if ctx.side=="BUY":
                if ns>os: STATE["synthetic_sl"]=ns; log_execution(f"🏛️ [COUNCIL] MOVE_TO_BE: {os:.4f} → {ns:.4f}","INFO")
            else:
                if os==0 or ns<os: STATE["synthetic_sl"]=ns; log_execution(f"🏛️ [COUNCIL] MOVE_TO_BE: {os:.4f} → {ns:.4f}","INFO")
            return
        if action==CouncilAction.TIGHTEN_SL:
            ns=d.new_sl
            if ns is not None:
                os=STATE.get("synthetic_sl",0)
                if ctx.side=="BUY" and ns>os:
                    STATE["synthetic_sl"]=ns; STATE["trail_stop"]=max(STATE.get("trail_stop",0),ns)
                    STATE["trail_activated"]=True
                    log_execution(f"🏛️ [COUNCIL] TIGHTEN_SL: {os:.4f} → {ns:.4f}","INFO")
                elif ctx.side=="SELL" and (os==0 or ns<os):
                    STATE["synthetic_sl"]=ns
                    if STATE.get("trail_stop",0)==0: STATE["trail_stop"]=ns
                    else: STATE["trail_stop"]=min(STATE["trail_stop"],ns)
                    STATE["trail_activated"]=True
                    log_execution(f"🏛️ [COUNCIL] TIGHTEN_SL: {os:.4f} → {ns:.4f}","INFO")
            return
        if action==CouncilAction.ACTIVATE_RUNNER:
            STATE["runner_mode"]=True; STATE["trail_activated"]=True; STATE["tp1_hit"]=True
            if ctx.side=="BUY":
                cur=STATE.get("synthetic_sl",0)
                STATE["synthetic_sl"]=max(cur,ctx.entry_price) if cur>0 else ctx.entry_price
                STATE["trail_stop"]=ctx.current_price-ctx.current_atr*1.5
            else:
                cur=STATE.get("synthetic_sl",0)
                STATE["synthetic_sl"]=min(cur,ctx.entry_price) if cur>0 else ctx.entry_price
                STATE["trail_stop"]=ctx.current_price+ctx.current_atr*1.5
            log_execution(f"🏛️ [COUNCIL] ACTIVATE_RUNNER: {d.reason}","SUCCESS")
            return
        if action==CouncilAction.HOLD and STATE.get("trail_activated",False):
            atr=ctx.current_atr; mult=STATE.get("smart_trail_mult",1.5)
            if ctx.side=="BUY":
                nt=ctx.current_price-atr*mult
                if nt>STATE.get("trail_stop",0): STATE["trail_stop"]=nt
            else:
                nt=ctx.current_price+atr*mult
                ot=STATE.get("trail_stop",0)
                if ot==0 or nt<ot: STATE["trail_stop"]=nt
    def run(self):
        if not STATE.get("open"): return
        now=time.time()
        if now-self.last_run<self.run_interval: return
        self.last_run=now
        ctx=self._build_context()
        if ctx is None: return
        if ctx.roe_pct>STATE.get("peak_roe",0.0):
            STATE["peak_roe"]=ctx.roe_pct; STATE["peak_price"]=ctx.current_price
        sl=STATE.get("synthetic_sl",0)
        if sl and sl>0:
            if (ctx.side=="BUY" and ctx.current_price<=sl) or (ctx.side=="SELL" and ctx.current_price>=sl):
                log_execution(f"🛑 Hard SL hit at {ctx.current_price:.4f} (SL={sl:.4f})","WARN")
                close_position_full()
                self.event_bus.emit("lifecycle_change",TradeLifecycleState.CLOSED)
                DASHBOARD_STATE["live_trade_mode"]=False
                return
        trail=STATE.get("trail_stop",0)
        if STATE.get("trail_activated",False) and trail and trail>0:
            if (ctx.side=="BUY" and ctx.current_price<=trail) or (ctx.side=="SELL" and ctx.current_price>=trail):
                log_execution(f"🎯 Trail stop hit at {ctx.current_price:.4f} (trail={trail:.4f})","WARN")
                close_position_full()
                self.event_bus.emit("lifecycle_change",TradeLifecycleState.CLOSED)
                DASHBOARD_STATE["live_trade_mode"]=False
                return
        mgr=STATE.get("dynamic_manager")
        if mgr is not None:
            try:
                ob=get_orderbook_cached(ctx.symbol,10)
                da=mgr.update(ctx.current_price,ctx.df,ob,ctx.current_atr)
                STATE["dyn_trail_active"]=mgr.trailing_activated
                STATE["dyn_tp1_hit"]=mgr.tp1_hit
                STATE["dyn_tp2_hit"]=mgr.tp2_hit
                STATE["dyn_runner"]=mgr.runner_active
                STATE["dyn_drawdown"]=mgr.drawdown
                STATE["dyn_lifecycle"]=mgr.lifecycle
                if da=="EXIT":
                    log_execution(f"⚡ [DYN_MGR] EXIT: {mgr.lifecycle}","WARN")
                    close_position_full()
                    self.event_bus.emit("lifecycle_change",TradeLifecycleState.CLOSED)
                    DASHBOARD_STATE["live_trade_mode"]=False
                    return
                elif da=="PARTIAL" and not STATE.get("tp1_hit",False):
                    log_execution(f"⚡ [DYN_MGR] PARTIAL TP1","SUCCESS")
                    close_partial(0.5); STATE["tp1_hit"]=True; STATE["trail_activated"]=True
                    if ctx.side=="BUY": STATE["synthetic_sl"]=max(STATE.get("synthetic_sl",0),ctx.entry_price)
                    else:
                        cur=STATE.get("synthetic_sl",0)
                        STATE["synthetic_sl"]=ctx.entry_price if cur==0 else min(cur,ctx.entry_price)
                    STATE["trail_stop"]=STATE["synthetic_sl"]
            except Exception as e:
                log_execution(f"[DYN_MGR] error: {e}","WARN")
        decision=self.council.convene(ctx)
        self.last_council_decision=decision
        if now-self.last_log>=8:
            self.last_log=now
            log_execution(f"🏛️ [COUNCIL] {ctx.symbol} {ctx.side} | ROE={ctx.roe_pct:.2f}% DD={ctx.drawdown_from_peak:.2f}% | Action={decision.action.value} (conf={decision.confidence:.0f}) | {decision.reason}","INFO")
            log_execution(f"    Votes: {decision.members_summary}","INFO")
        self._apply_decision(decision,ctx)

# ========== TRADE STATE & PERF ==========
TRADE_STATE={"in_position":False,"symbol":None,"side":None,"entry":0.0,"qty":0.0,
             "tp1_hit":False,"tp2_hit":False,"trail_on":False,"zone":None,
             "location":None,"reason":[],"last_update_ts":0}
PERF={"total_pnl_pct":0.0,"total_pnl_usdt":0.0,"trades":0,"wins":0,"losses":0,"last_trade":None}

GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; CYAN="\033[96m"
MAGENTA="\033[95m"; BLUE="\033[94m"; RESET="\033[0m"; BOLD="\033[1m"
def color_pnl(p): return f"{GREEN}{p:.2f}%{RESET}" if p>=0 else f"{RED}{p:.2f}%{RESET}"
def color_text(t,c): return f"{c}{t}{RESET}"
def safe_json(obj):
    if isinstance(obj,(np.bool_,bool)): return bool(obj)
    if isinstance(obj,(np.integer,)): return int(obj)
    if isinstance(obj,(np.floating,)): return float(obj)
    if isinstance(obj,(pd.Series,pd.DataFrame)): return obj.to_dict() if hasattr(obj,'to_dict') else str(obj)
    if isinstance(obj,dict): return {k:safe_json(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)): return [safe_json(i) for i in obj]
    return obj
def to_json_safe(obj):
    try:
        if obj is None: return {}
        if hasattr(obj,"to_dict"): return safe_json(obj.to_dict(orient="records"))
        if isinstance(obj,(dict,list,str,int,float,bool)): return safe_json(obj)
        return str(obj)
    except: return {}
def safe_get(d,k,default=None):
    if d is None: return default
    return d.get(k,default)
def safe_float(val,default=0.0):
    try: return float(val) if val is not None else default
    except: return default

CACHE={"balance":{"value":0.0,"ts":0},"free_balance":{"value":0.0,"ts":0},"ohlcv":{"value":{},"ts":0},
       "ticker":{"value":{},"ts":0},"orderbook":{"value":{},"ts":0},"dashboard":{"value":None,"ts":0},"decision":{"value":None,"ts":0}}
_last_api_call=0; MIN_API_INTERVAL=0.2
def rate_limit():
    global _last_api_call
    now=time.time(); elapsed=now-_last_api_call
    if elapsed<MIN_API_INTERVAL: time.sleep(MIN_API_INTERVAL-elapsed)
    _last_api_call=time.time()
def cache_get(key,ttl,subkey=None):
    item=CACHE.get(key)
    if item and isinstance(item,dict) and "ts" in item and "value" in item:
        if time.time()-item["ts"]<ttl:
            if subkey:
                v=item["value"]
                if isinstance(v,dict) and subkey in v: return v[subkey]
                return None
            return item["value"]
    return None
def cache_set(key,value,subkey=None):
    if subkey:
        if key not in CACHE or not isinstance(CACHE.get(key),dict) or "value" not in CACHE[key]:
            CACHE[key]={"value":{},"ts":time.time()}
        CACHE[key]["value"][subkey]=value
    else: CACHE[key]={"value":value,"ts":time.time()}
def safe_api_call(func,*args,**kwargs):
    for attempt in range(3):
        try:
            rate_limit()
            return func(*args,**kwargs)
        except Exception as e:
            if "rate limit" in str(e).lower() or "100410" in str(e):
                wait=2**attempt; print(color_text(f"Rate limit hit, waiting {wait}s...",YELLOW))
                time.sleep(wait); continue
            if attempt==2: raise
            time.sleep(1)
    return None

# ========== TELEGRAM ==========
TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID")
_last_tg_msg={}
def _tg_send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url,json={"chat_id":TELEGRAM_CHAT_ID,"text":text,"parse_mode":"HTML","disable_web_page_preview":True},timeout=5)
    except: pass
def send_once(msg,key,cooldown=60):
    now=time.time()
    if key not in _last_tg_msg or now-_last_tg_msg[key]>cooldown:
        _last_tg_msg[key]=now; _tg_send(msg)
def tg_start(balance,mode): send_once(f"🚀 <b>RF v29 Council Edition</b>\nBalance: {balance:.2f} USDT\nMode: {mode}","startup",86400)
def tg_entry(side,symbol,entry,sl,tp,score,reason,entry_type):
    e="🟢" if side=="BUY" else "🔴"
    ets=f"{entry_type} NARRATIVE" if entry_type=="NARRATIVE" else entry_type
    send_once(f"{e} <b>{side} {ets}</b>\n📊 {symbol}\n💰 Entry: {entry:.4f}\n🛑 SL: {sl:.4f}\n🎯 TP: {tp:.4f}\n🧠 Score: {score}\n📌 {reason[:100]}",f"entry_{symbol}",60)
def tg_tp_hit(symbol,tp_level,pnl_pct): send_once(f"🎯 <b>TP{tp_level} HIT</b> on {symbol}\nPnL: {pnl_pct:.2f}%",f"tp_{symbol}_{tp_level}",30)
def tg_sl_hit(symbol,pnl_pct): send_once(f"🛑 <b>STOP LOSS HIT</b> on {symbol}\nPnL: {pnl_pct:.2f}%",f"sl_{symbol}",30)
def tg_close(symbol,pnl_pct,duration_min,side):
    i="✅" if pnl_pct>=0 else "❌"
    send_once(f"{i} <b>CLOSE</b> {symbol} ({side})\nPnL: {pnl_pct:.2f}%\n⏱ {duration_min:.0f} min",f"close_{symbol}",10)
def tg_error(err_msg,error_type="EXECUTION"): send_once(f"🚨 <b>ERROR</b> [{error_type}]\n{err_msg[:200]}",f"err_{error_type}_{err_msg[:50]}",60)

# ========== CONFIG ==========
API_KEY=os.getenv("BINGX_API_KEY","")
API_SECRET=os.getenv("BINGX_API_SECRET","")
PAPER_MODE=os.getenv("PAPER_MODE","True")=="False"
MODE_LIVE=bool(API_KEY and API_SECRET) and not PAPER_MODE
DEFAULT_SYMBOL=os.getenv("SYMBOL","BTC/USDT")
INTERVAL=os.getenv("INTERVAL","15m")
LEVERAGE=10; USE_PPE=True
USE_EXECUTION_QUEUE=os.getenv("USE_EXECUTION_QUEUE","True")=="True"
QUEUE_MAX_SIZE=int(os.getenv("QUEUE_MAX_SIZE","15"))
QUEUE_RE_EVAL_INTERVAL=int(os.getenv("QUEUE_RE_EVAL_INTERVAL","5"))
QUEUE_PROMOTE_INTERVAL=int(os.getenv("QUEUE_PROMOTE_INTERVAL","30"))
GLOBAL_SCAN_INTERVAL=60*20; SCANNER_V2_INTERVAL=60*20; MICRO_SCAN_INTERVAL=5; TOP_LIQUID_COUNT=80
MAX_SPREAD_PERCENT_DEFAULT=0.08; MAX_SPREAD_PERCENT_VOLATILE=0.15
MAX_SCALE_INS=2; SCALE_IN_SIZE_PCT=0.25; SCALE_IN_PROFIT_PCT=0.5
RUNNER_PCT=0.4; TRAIL_ATR_MULT=1.4; ADVERSE_MOVE_ATR_MULT=1.8
MAX_DAILY_LOSS_PCT=5.0; MAX_CONSECUTIVE_LOSSES=3
COOLDOWN_MINUTES_LOSS=10; COOLDOWN_MINUTES_DRAWDOWN=20
SNAPSHOT_INTERVAL=15; BASE_SLEEP=5; KEEP_ALIVE_INTERVAL=300
BALANCE_SAFETY_FACTOR=0.98; INSUFFICIENT_MARGIN_COOLDOWN_SEC=60
SCAN_INTERVAL=900; WATCHLIST_REFRESH=300; RADAR_COOLDOWN_SEC=1800
LAST_ENTRY_PER_SYMBOL={}; INSUFFICIENT_MARGIN_COOLDOWN_UNTIL=None

ex=ccxt.bingx({"apiKey":API_KEY,"secret":API_SECRET,"enableRateLimit":True,"options":{"defaultType":"swap"}})
def normalize_symbol(symbol):
    if not symbol.endswith(":USDT"): return f"{symbol}:USDT"
    return symbol
def set_leverage(symbol,leverage):
    try:
        sym=normalize_symbol(symbol)
        if hasattr(ex,'set_leverage'): ex.set_leverage(leverage,sym)
    except Exception as e: print(color_text(f"set_leverage warning: {e}",YELLOW))

# ========== LIVE HYBRID DF ==========
_live_high={}; _live_low={}; _last_candle_timestamp={}
def get_live_hybrid_df(symbol,base_df,live_price):
    if base_df is None or base_df.empty or live_price is None or live_price<=0: return base_df
    df=base_df.copy(); last_idx=df.index[-1]
    current_ts=df.loc[last_idx,'timestamp'] if 'timestamp' in df.columns else last_idx
    global _last_candle_timestamp,_live_high,_live_low
    prev_ts=_last_candle_timestamp.get(symbol)
    if prev_ts is None or current_ts!=prev_ts:
        _last_candle_timestamp[symbol]=current_ts
        _live_high[symbol]=df.loc[last_idx,'high']
        _live_low[symbol]=df.loc[last_idx,'low']
    else:
        _live_high[symbol]=max(_live_high.get(symbol,df.loc[last_idx,'high']),live_price)
        _live_low[symbol]=min(_live_low.get(symbol,df.loc[last_idx,'low']),live_price)
    df.loc[last_idx,'high']=_live_high[symbol]
    df.loc[last_idx,'low']=_live_low[symbol]
    df.loc[last_idx,'close']=live_price
    return df

# ========== DATA FETCHING ==========
def fetch_ohlcv(symbol,limit=150):
    try:
        sym=normalize_symbol(symbol)
        data=safe_api_call(ex.fetch_ohlcv,sym,INTERVAL,limit=limit)
        if not data or len(data)<100: return None
        df=pd.DataFrame(data,columns=["timestamp","open","high","low","close","volume"])
        for c in ["open","high","low","close","volume"]: df[c]=pd.to_numeric(df[c],errors='coerce').astype(float)
        df=df.dropna()
        if len(df)<100: return None
        if (df['close']==0).any() or (df['high']==0).any() or (df['low']==0).any(): return None
        df=df.sort_index().drop_duplicates(subset=['timestamp']).ffill().bfill()
        if len(df)<100: return None
        return df
    except Exception as e:
        print(color_text(f"fetch_ohlcv error for {symbol}: {e}",YELLOW))
        return None
def fetch_ohlcv_htf(symbol,timeframe='1h',limit=200):
    try:
        sym=normalize_symbol(symbol)
        data=safe_api_call(ex.fetch_ohlcv,sym,timeframe,limit=limit)
        if not data or len(data)<30: return None
        df=pd.DataFrame(data,columns=["timestamp","open","high","low","close","volume"])
        for c in ["open","high","low","close","volume"]: df[c]=pd.to_numeric(df[c],errors='coerce').astype(float)
        df=df.dropna()
        if len(df)<30: return None
        return df.sort_index().drop_duplicates().ffill().bfill()
    except: return None
def fetch_ticker(symbol): return safe_api_call(ex.fetch_ticker,normalize_symbol(symbol))
def fetch_orderbook(symbol,limit=20): return safe_api_call(ex.fetch_order_book,normalize_symbol(symbol),limit)
def get_balance():
    if PAPER_MODE: return paper["balance"]
    bal=safe_api_call(ex.fetch_balance)
    if bal: return bal.get("total",{}).get("USDT",0.0)
    return 0.0
def get_free_balance():
    if PAPER_MODE: return paper["balance"]
    bal=safe_api_call(ex.fetch_balance)
    if bal: return bal.get("free",{}).get("USDT",0.0)
    return 0.0
def get_spread_bps(symbol):
    try:
        ob=get_orderbook_cached(symbol,5)
        if ob and ob['asks'] and ob['bids']:
            ask=ob['asks'][0][0]; bid=ob['bids'][0][0]
            return (ask-bid)/bid*100
    except: pass
    return 100.0
def validate_dataframe(df,min_length=100):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty: return False
    req=["open","high","low","close","volume"]
    if not all(c in df.columns for c in req): return False
    if df[req].iloc[-min_length:].isna().any().any(): return False
    if (df['close'].iloc[-min_length:]==0).any(): return False
    if df['close'].iloc[-min_length:].std()<1e-8: return False
    return True
def get_ohlcv_safe(symbol,limit=120,htf=False):
    ttl=15 if (STATE.get("open") or TRADE_STATE["in_position"]) else 30
    if htf: ttl=max(ttl,45)
    ck=f"ohlcv_{symbol}_{INTERVAL}_{limit}_htf" if htf else f"ohlcv_{symbol}_{INTERVAL}_{limit}"
    cached=cache_get("ohlcv",ttl,ck)
    if cached is not None and len(cached)>=100: return cached
    df=fetch_ohlcv_htf(symbol,'1h',limit) if htf else fetch_ohlcv(symbol,limit)
    if df is not None and validate_dataframe(df,min(limit,100)):
        cache_set("ohlcv",df,ck); return df
    return None
def get_ticker_safe(symbol):
    cached=cache_get("ticker",2,symbol)
    if cached is not None: return cached
    ticker=fetch_ticker(symbol)
    if ticker:
        p=ticker["last"]
        if p and p>0: cache_set("ticker",p,symbol); return p
    return None
def get_balance_safe():
    cached=cache_get("balance",10)
    if cached is not None: return cached
    bal=get_balance(); cache_set("balance",bal); return bal
def get_free_balance_safe():
    cached=cache_get("free_balance",10)
    if cached is not None: return cached
    bal=get_free_balance(); cache_set("free_balance",bal); return bal
def get_orderbook_cached(symbol,limit=20):
    if STATE.get("open") or TRADE_STATE["in_position"]:
        cached=cache_get("orderbook",60,f"{symbol}_{limit}")
        if cached is not None: return cached
        return None
    cached=cache_get("orderbook",1,f"{symbol}_{limit}")
    if cached is not None: return cached
    ob=fetch_orderbook(symbol,limit)
    if ob: cache_set("orderbook",ob,f"{symbol}_{limit}")
    return ob
def fetch_position(symbol):
    if PAPER_MODE: return None
    try:
        sym=normalize_symbol(symbol)
        if hasattr(ex,'fetch_positions'): positions=safe_api_call(ex.fetch_positions,[sym])
        elif hasattr(ex,'fetch_open_positions'): positions=safe_api_call(ex.fetch_open_positions,[sym])
        else: return None
        if not positions: return None
        for pos in positions:
            ps=pos.get('symbol','')
            if normalize_symbol(symbol) in ps and float(pos.get('contracts',0))>0: return pos
        return None
    except Exception as e:
        log_execution(f"[POS_SYNC] fetch_position error: {e}","ERROR"); return None
def get_mark_price(symbol):
    if PAPER_MODE: return get_ticker_safe(symbol)
    pos=fetch_position(symbol)
    if pos and 'markPrice' in pos and pos['markPrice']: return float(pos['markPrice'])
    return get_ticker_safe(symbol)

# ========== TRADE THESIS ==========
@dataclass
class TradeThesis:
    thesis_id: str; symbol: str; side: str; trade_type: str; created_at: float
    entry_reason: List[str]=field(default_factory=list)
    continuation_factors: List[str]=field(default_factory=list)
    invalidation_factors: List[str]=field(default_factory=list)
    risk_factors: List[str]=field(default_factory=list)
    market_context: Dict=field(default_factory=dict)
    confidence: float=0.0; continuation_probability: float=0.5; exhaustion_probability: float=0.0
    thesis_strength: float=0.0; current_status: str="ACTIVE"; last_update: float=field(default_factory=time.time)
class TradeThesisEngine:
    def build_thesis(self,symbol,side,trade_type,market_state,narrative,entry_context):
        reasons=[]; cont=[]; inval=[]; risks=[]
        adx=market_state.get("adx",0); reg=market_state.get("regime","UNKNOWN")
        cp=0.5
        if adx>25: reasons.append("strong_trend_environment"); cont.append("adx_expansion"); cp+=0.1
        if market_state.get("di_dominance",False): reasons.append("di_dominance"); cont.append("persistent_pressure"); cp+=0.1
        if market_state.get("weak_pullback",False): reasons.append("weak_pullback"); cont.append("counter_move_weakness"); cp+=0.1
        if market_state.get("structure_aligned",False): reasons.append("market_structure_alignment"); cp+=0.1
        nc=narrative.get("classification","NEUTRAL")
        if nc in ("TREND_CONTINUATION","INSTITUTIONAL_CONTINUATION"): reasons.append("institutional_narrative_alignment"); cp+=0.1
        if adx>45: risks.append("trend_exhaustion_risk")
        if market_state.get("counter_displacement",0)>1.0: risks.append("counter_displacement_risk")
        if reg=="CHOP": risks.append("choppy_environment")
        inval.extend(["ema_loss","di_flip","failed_continuation","vwap_reclaim","strong_counter_displacement"])
        cf=min(cp,0.95); ts=(len(reasons)*1.2+len(cont)*1.5-len(risks)*0.8)
        return TradeThesis(thesis_id=f"{symbol}_{int(time.time())}",symbol=symbol,side=side,trade_type=trade_type,
                          created_at=time.time(),entry_reason=reasons,continuation_factors=cont,
                          invalidation_factors=inval,risk_factors=risks,market_context=market_state,
                          confidence=round(cf,2),continuation_probability=round(cp,2),exhaustion_probability=0.0,
                          thesis_strength=round(ts,2))
    def update_thesis(self,thesis,market_state):
        cp=thesis.continuation_probability; ep=thesis.exhaustion_probability
        th=market_state.get("trend_health",5)
        if th>=7: cp+=0.05
        elif th<=3: cp-=0.1
        ads=market_state.get("adx_slope",0)
        if ads>0: cp+=0.05
        else: cp-=0.03
        cd=market_state.get("counter_displacement",0)
        if cd>1.2: cp-=0.15; ep+=0.2
        if market_state.get("weak_pullback",False): cp+=0.08
        thesis.continuation_probability=round(max(0,min(1,cp)),2)
        thesis.exhaustion_probability=round(max(0,min(1,ep)),2)
        thesis.last_update=time.time()
        return thesis
_thesis_engine=TradeThesisEngine()

# ========== REJECTION INTELLIGENCE ==========
class RejectionIntelligence:
    @staticmethod
    def is_bearish_rejection(df,atr,zone_price=None):
        if len(df)<1: return False,[]
        last=df.iloc[-1]; body=abs(last['close']-last['open']); r=last['high']-last['low']
        if r==0: return False,[]
        uw=last['high']-max(last['open'],last['close']); wc=uw>=1.5*body
        cnl=(last['close']-last['low'])/r<=0.3
        zf=last['close']<zone_price if zone_price is not None else False
        if len(df)>=3:
            p2=df.iloc[-2]; p3=df.iloc[-3]
            wk=(p2['close']<p2['open'] or p3['close']<p3['open'])
        else: wk=False
        vs=classify_volume(df)
        vo=vs in ("expansion","spike") and df['volume'].iloc[-1]<df['volume'].rolling(20).mean().iloc[-1]*1.2
        pd_,md_,_,_=get_di_components(df)
        do=(md_ is not None and pd_ is not None and md_>pd_ and (md_-pd_)>2)
        ss=(body/r<=0.3 and uw>=2*body and last['close']<last['open'])
        be=False
        if len(df)>=2:
            pv=df.iloc[-2]
            be=(pv['close']>pv['open'] and last['close']<last['open'] and last['high']>pv['high'] and last['low']<pv['low'])
        reasons=[]; sc=0
        if wc: sc+=2; reasons.append("long_upper_wick")
        if cnl: sc+=1; reasons.append("close_near_low")
        if zf: sc+=2; reasons.append("zone_failure")
        if wk: sc+=1; reasons.append("weak_continuation")
        if vo: sc+=1; reasons.append("volume_absorption")
        if do: sc+=2; reasons.append("di_dominance_sell")
        if ss: sc+=1.5; reasons.append("shooting_star")
        if be: sc+=2; reasons.append("bearish_engulfing")
        return sc>=5,reasons
    @staticmethod
    def is_bullish_rejection(df,atr,zone_price=None):
        if len(df)<1: return False,[]
        last=df.iloc[-1]; body=abs(last['close']-last['open']); r=last['high']-last['low']
        if r==0: return False,[]
        lw=min(last['open'],last['close'])-last['low']; wc=lw>=1.5*body
        cnh=(last['high']-last['close'])/r<=0.3
        zf=last['close']>zone_price if zone_price is not None else False
        if len(df)>=3:
            p2=df.iloc[-2]; p3=df.iloc[-3]
            wk=(p2['close']>p2['open'] or p3['close']>p3['open'])
        else: wk=False
        vs=classify_volume(df)
        vo=vs in ("expansion","spike") and df['volume'].iloc[-1]<df['volume'].rolling(20).mean().iloc[-1]*1.2
        pd_,md_,_,_=get_di_components(df)
        do=(pd_ is not None and md_ is not None and pd_>md_ and (pd_-md_)>2)
        ha=(body/r<=0.3 and lw>=2*body and last['close']>last['open'])
        be=False
        if len(df)>=2:
            pv=df.iloc[-2]
            be=(pv['close']<pv['open'] and last['close']>last['open'] and last['high']>pv['high'] and last['low']<pv['low'])
        reasons=[]; sc=0
        if wc: sc+=2; reasons.append("long_lower_wick")
        if cnh: sc+=1; reasons.append("close_near_high")
        if zf: sc+=2; reasons.append("zone_failure")
        if wk: sc+=1; reasons.append("weak_continuation")
        if vo: sc+=1; reasons.append("volume_absorption")
        if do: sc+=2; reasons.append("di_dominance_buy")
        if ha: sc+=1.5; reasons.append("hammer")
        if be: sc+=2; reasons.append("bullish_engulfing")
        return sc>=5,reasons

# ========== MSS VALIDATOR ==========
class MSSValidator:
    @staticmethod
    def validate_structure_shift(df,side,atr):
        if len(df)<10: return False,[],0
        last=df.iloc[-1]; prev=df.iloc[-2]
        body=abs(last['close']-last['open']); pb=abs(prev['close']-prev['open'])
        ds=body/(pb+1e-9) if pb>0 else 1.0; be=ds>=1.5
        ft=False
        if len(df)>=3:
            nc=df.iloc[-1]
            if side=="BUY": ft=nc['close']>nc['open'] and body>pb
            else: ft=nc['close']<nc['open'] and body>pb
        else: ft=True
        pd_,md_,adx,ads=get_di_components(df)
        di_sp=abs(pd_-md_) if pd_ is not None and md_ is not None else 0
        vs=classify_volume(df); vo=vs in ("expansion","spike")
        aa=ads>0 and adx>25
        sc=0; reasons=[]
        if be: sc+=2; reasons.append("body_expansion")
        if ft: sc+=2; reasons.append("follow_through")
        if di_sp>8: sc+=2; reasons.append("di_spread_strong")
        if vo: sc+=1; reasons.append("volume_confirm")
        if aa: sc+=2; reasons.append("adx_accelerating")
        iv=sc>=5
        if adx<20: iv=False; reasons.append("adx_too_low")
        if not be and not ft: iv=False; reasons.append("weak_displacement")
        return iv,reasons,sc

# ========== ADX + DI ==========
class ADXDIIntelligence:
    @staticmethod
    def get_adx_state(df):
        ads=compute_adx(df)
        if ads is None or len(ads)<3: return {"state":"UNKNOWN","value":20,"slope":0,"acceleration":0}
        av=ads.iloc[-1]; ap=ads.iloc[-2]; ap2=ads.iloc[-3] if len(ads)>=3 else ap
        s=av-ap; a=s-(ap-ap2)
        if av<18: st="CHOP"
        elif av<22: st="EMERGING"
        elif av<35: st="STRONG_TREND"
        elif av<45: st="VERY_STRONG"
        else: st="EXHAUSTION"
        return {"state":st,"value":av,"slope":s,"acceleration":a}
    @staticmethod
    def get_di_state(df):
        pd_,md_,_,_=get_di_components(df)
        if pd_ is None or md_ is None: return {"dominant":"NEUTRAL","spread":0,"trend":"NEUTRAL"}
        sp=pd_-md_
        if sp>5: return {"dominant":"BUY","spread":sp,"trend":"BULLISH"}
        elif sp<-5: return {"dominant":"SELL","spread":sp,"trend":"BEARISH"}
        return {"dominant":"NEUTRAL","spread":sp,"trend":"CHOP"}
    @staticmethod
    def is_healthy_trend(df,side):
        adxs=ADXDIIntelligence.get_adx_state(df); dis=ADXDIIntelligence.get_di_state(df)
        if side=="BUY": return adxs["state"] in ("STRONG_TREND","VERY_STRONG") and dis["dominant"]=="BUY" and adxs["slope"]>0
        return adxs["state"] in ("STRONG_TREND","VERY_STRONG") and dis["dominant"]=="SELL" and adxs["slope"]>0

# ========== CONTINUATION PRESSURE ==========
class ContinuationPressureEngine:
    @staticmethod
    def calculate_pressure(df,side,entry_price,atr,entry_time):
        if len(df)<3: return 50,[]
        sc=50; reasons=[]
        bodies=[abs(df['close'].iloc[-i]-df['open'].iloc[-i]) for i in range(1,4)]
        if len(bodies)>=2:
            g=bodies[0]/(bodies[1]+1e-9)
            if g>1.2: sc+=10; reasons.append("body_expansion")
            elif g<0.8: sc-=10; reasons.append("body_contraction")
        adxs=ADXDIIntelligence.get_adx_state(df); dis=ADXDIIntelligence.get_di_state(df)
        if side=="BUY" and adxs["slope"]>0 and dis["dominant"]=="BUY": sc+=15; reasons.append("adx_rising_di_bullish")
        elif side=="SELL" and adxs["slope"]>0 and dis["dominant"]=="SELL": sc+=15; reasons.append("adx_rising_di_bearish")
        elif adxs["slope"]<=0: sc-=10; reasons.append("adx_falling")
        if dis["spread"]>10: sc+=10; reasons.append("di_spread_wide")
        elif abs(dis["spread"])<4: sc-=10; reasons.append("di_tangled")
        vs=classify_volume(df)
        if vs=="expansion": sc+=15; reasons.append("volume_expansion")
        elif vs=="exhaustion": sc-=15; reasons.append("volume_exhaustion")
        lc=df['close'].iloc[-1]
        if side=="BUY" and lc<entry_price: sc-=10; reasons.append("price_below_entry")
        elif side=="SELL" and lc>entry_price: sc-=10; reasons.append("price_above_entry")
        cc=0
        for i in range(1,min(5,len(df))):
            if side=="BUY" and df['close'].iloc[-i]>df['open'].iloc[-i]: cc+=1
            elif side=="SELL" and df['close'].iloc[-i]<df['open'].iloc[-i]: cc+=1
            else: break
        if cc>=3: sc+=10; reasons.append(f"consecutive_{cc}")
        elif cc==0: sc-=5; reasons.append("no_follow_through")
        return max(0,min(100,sc)),reasons

# ========== THESIS FAILURE ==========
class ThesisFailureEngine:
    @staticmethod
    def evaluate_failure(thesis,market_state,current_price,entry_price,side):
        if not thesis: return False,[],0
        fs=0; reasons=[]
        if market_state.get("strong_reclaim",False): fs+=30; reasons.append("strong_reclaim")
        dis=ADXDIIntelligence.get_di_state(market_state.get("df",None))
        if side=="BUY" and dis.get("dominant")=="SELL": fs+=25; reasons.append("di_flip_bearish")
        elif side=="SELL" and dis.get("dominant")=="BUY": fs+=25; reasons.append("di_flip_bullish")
        adxs=ADXDIIntelligence.get_adx_state(market_state.get("df",None))
        if adxs.get("state")=="CHOP" and adxs.get("value",20)<18: fs+=20; reasons.append("adx_collapse")
        lc=market_state.get("last_candle",{})
        if side=="SELL" and lc.get("close",0)>lc.get("open",0):
            b=abs(lc.get("close",0)-lc.get("open",0))
            if b>market_state.get("atr",0)*0.6: fs+=20; reasons.append("strong_bullish_candle")
        elif side=="BUY" and lc.get("close",0)<lc.get("open",0):
            b=abs(lc.get("close",0)-lc.get("open",0))
            if b>market_state.get("atr",0)*0.6: fs+=20; reasons.append("strong_bearish_candle")
        cp=market_state.get("continuation_pressure",50)
        if cp<30: fs+=25; reasons.append("low_continuation_pressure")
        return fs>=50,reasons,fs

# ========== MARKET REGIME CLASSIFIER ==========
class MarketRegimeClassifier:
    @staticmethod
    def classify(df,ob=None):
        if df is None or len(df)<50: return "UNKNOWN"
        adxs=ADXDIIntelligence.get_adx_state(df); dis=ADXDIIntelligence.get_di_state(df)
        atr=compute_atr(df).iloc[-1]; price=df['close'].iloc[-1]
        atrp=(atr/price)*100 if price>0 else 0
        vs=classify_volume(df)
        r20=(df['high'].rolling(20).max()-df['low'].rolling(20).min()).iloc[-1]
        rp=(r20/price)*100 if price>0 else 0
        e20=ema(df['close'],20).iloc[-1]; e50=ema(df['close'],50).iloc[-1]
        pae=price>e20 and e20>e50; pbe=price<e20 and e20<e50
        bu,bd=detect_bos(df,lookback=5); ss=detect_structure_shift(df)
        if adxs["state"] in ("STRONG_TREND","VERY_STRONG") and dis["dominant"]!="NEUTRAL":
            if (pae and dis["dominant"]=="BUY") or (pbe and dis["dominant"]=="SELL"):
                if atrp>2.0: return "EXPANSION"
                else: return "STRONG_TREND"
        if adxs["state"]=="EMERGING" and adxs["slope"]>0: return "WEAK_TREND"
        if adxs["value"]<18 or dis["dominant"]=="NEUTRAL":
            if rp<1.5: return "COMPRESSION"
            else: return "CHOPPY"
        if vs=="expansion" and adxs["value"]>25: return "EXPANSION"
        if vs=="exhaustion" and adxs["value"]>30: return "DISTRIBUTION"
        if (ss=="bullish_shift" and bu) or (ss=="bearish_shift" and bd): return "TRANSITION"
        if vs=="absorption": return "ACCUMULATION"
        return "RANGE"

# ========== CONFIDENCE ENGINE ==========
class ConfidenceEngine:
    @staticmethod
    def calculate_initial_confidence(es,ns,reg,adx,dis,lq):
        base=(es/10)*30+(ns/10)*30
        rm={"STRONG_TREND":20,"WEAK_TREND":10,"EXPANSION":25,"COMPRESSION":5,"CHOPPY":0,"ACCUMULATION":15,"DISTRIBUTION":10,"TRANSITION":10}
        rb=rm.get(reg,5); ab=min(20,max(0,(adx-20)*2)); db=min(15,abs(dis))
        lb={"discount":10,"premium":10,"mid":0}.get(lq,0)
        return min(100,base+rb+ab+db+lb)
    @staticmethod
    def update_live_confidence(cc,cp,tf,ads,dsc):
        nc=cc; nc+=(cp-50)*0.3; nc-=tf*0.5; nc+=ads*2; nc+=dsc*1.5
        return max(0,min(100,nc))
    @staticmethod
    def apply_institutional_modifiers(bc,sm,mom,cs):
        c=bc
        if sm.get("smart_money_dominant",False): c+=10
        else: c-=8
        con=min(100,max(0,cs))
        if con>20: c+=8
        elif con<5: c-=10
        mh=mom.get("momentum_health",50)
        if mh>15: c+=6
        elif mh<0: c-=8
        bp=sm.get("banker_pressure",50); rp=sm.get("retailer_pressure",50)
        if bp>rp: c+=5
        else: c-=6
        dr=sm.get("distribution_risk",0)
        if dr>45: c-=12
        cr=mom.get("climax_risk",0)
        if cr>50: c-=10
        return max(0,min(100,c))

# ========== PRECISION SAFETY ==========
class PrecisionSafety:
    @staticmethod
    def normalize_price(symbol,price):
        try:
            m=ex.market(normalize_symbol(symbol)); p=m['precision']['price']
            return round(price,p)
        except: return price
    @staticmethod
    def normalize_amount(symbol,amount):
        try:
            m=ex.market(normalize_symbol(symbol)); p=m['precision']['amount']
            return math.floor(amount/(10**-p))*(10**-p)
        except: return amount
    @staticmethod
    def adjust_sl_tp(symbol,entry,sl,tp,side,atr):
        md=max(atr*0.5,entry*0.002)
        if side=="BUY":
            if entry-sl<md: sl=entry-md
            if tp-entry<md: tp=entry+md
        else:
            if sl-entry<md: sl=entry+md
            if entry-tp<md: tp=entry-md
        sl=PrecisionSafety.normalize_price(symbol,sl)
        tp=PrecisionSafety.normalize_price(symbol,tp)
        return sl,tp

# ========== CONTINUATION PROBABILITY ==========
@dataclass
class ContinuationEvaluation:
    continuation_probability: float; trend_strength: float; exhaustion_probability: float
    reclaim_risk: float; counter_pressure: float; confidence: float
    reasons: List[str]; should_hold: bool; hold_quality: str
class ContinuationProbabilityEngine:
    HOLD_THRESHOLD=0.62
    def evaluate(self,side,df,market_state,thesis):
        sc=0.0; reasons=[]
        close=df["close"].iloc[-1]
        atr=market_state.get("atr",0); adx=market_state.get("adx",0)
        ads=market_state.get("adx_slope",0); dp=market_state.get("di_plus",0); dm=market_state.get("di_minus",0)
        th=market_state.get("trend_health",5); wp=market_state.get("weak_pullback",False)
        cd=market_state.get("counter_displacement",0); vr=market_state.get("volume_ratio",1.0)
        e20=df["close"].ewm(span=20).mean().iloc[-1]; e50=df["close"].ewm(span=50).mean().iloc[-1]
        ep=0.0; rr=0.0; cp=0.0
        ds=(dp-dm) if side=="BUY" else (dm-dp)
        if ds>8: sc+=2.5; reasons.append("strong_di_pressure")
        elif ds>4: sc+=1.5; reasons.append("moderate_di_pressure")
        else: sc-=2.0; reasons.append("weak_di_pressure")
        if adx>25: sc+=2.5; reasons.append("healthy_adx")
        elif adx>18: sc+=1.0; reasons.append("developing_adx")
        else: sc-=2.5; reasons.append("dead_adx")
        if ads>0: sc+=1.5; reasons.append("adx_expanding")
        else: sc-=1.0; reasons.append("adx_fading")
        if th>=8: sc+=3.0; reasons.append("excellent_trend_health")
        elif th>=6: sc+=2.0; reasons.append("healthy_trend")
        elif th<=3: sc-=3.0; reasons.append("trend_breakdown")
        if wp: sc+=2.0; reasons.append("weak_pullback_detected")
        if cd>1.5: cp+=0.5; sc-=3.0; reasons.append("strong_counter_pressure")
        elif cd>0.8: cp+=0.25; sc-=1.5; reasons.append("moderate_counter_pressure")
        if side=="BUY":
            if close>e20: sc+=1.5; reasons.append("holding_ema20")
            if close>e50: sc+=2.0; reasons.append("holding_ema50")
            if close<e20: rr+=0.2
            if close<e50: rr+=0.4
        else:
            if close<e20: sc+=1.5; reasons.append("holding_ema20")
            if close<e50: sc+=2.0; reasons.append("holding_ema50")
            if close>e20: rr+=0.2
            if close>e50: rr+=0.4
        if atr>0:
            ext=abs(close-e20)/atr
            if ext>3: ep+=0.5; sc-=1.5; reasons.append("overextended")
            elif ext>2: ep+=0.25; reasons.append("extended_move")
        if vr>1.2: sc+=1.5; reasons.append("volume_confirmation")
        elif vr<0.7: sc-=1.5; reasons.append("weak_volume")
        ts=thesis.get("thesis_strength",5) if isinstance(thesis,dict) else 5
        sc+=ts*0.3
        prob=(sc+15)/30; prob=max(0.0,min(1.0,prob))
        conf=min(abs(sc)/15,1.0)
        sh=prob>=self.HOLD_THRESHOLD
        if prob>=0.8: hq="STRONG"
        elif prob>=0.65: hq="HEALTHY"
        elif prob>=0.5: hq="NEUTRAL"
        else: hq="WEAK"
        return ContinuationEvaluation(continuation_probability=round(prob,2),trend_strength=round(th/10,2),
            exhaustion_probability=round(ep,2),reclaim_risk=round(rr,2),counter_pressure=round(cp,2),
            confidence=round(conf,2),reasons=reasons,should_hold=sh,hold_quality=hq)
_continuation_engine=ContinuationProbabilityEngine()

# ========== LIFECYCLE / EVENT BUS ==========
class TradeLifecycleState(Enum):
    IDLE="IDLE"; OPEN_REQUESTED="OPEN_REQUESTED"; OPEN_PENDING_CONFIRMATION="OPEN_PENDING_CONFIRMATION"
    LIVE="LIVE"; PARTIALLY_CLOSED="PARTIALLY_CLOSED"; CLOSING="CLOSING"; CLOSED="CLOSED"
    RECOVERING="RECOVERING"; ERROR_DEGRADED="ERROR_DEGRADED"
class PositionSnapshot:
    def __init__(self):
        self.symbol=None; self.side=None; self.qty=0.0; self.entry_price=0.0; self.mark_price=0.0
        self.unrealized_pnl=0.0; self.realized_pnl=0.0; self.roe_pct=0.0; self.leverage=LEVERAGE
        self.margin=0.0; self.liquidation_price=0.0; self.tp1_hit=False; self.tp2_hit=False
        self.trailing_active=False; self.trailing_stop=0.0; self.sl_price=0.0
        self.partial_closed=False; self.stale=False; self.updated_at=0.0; self.source="unknown"
    def to_dict(self):
        return {"symbol":self.symbol,"side":self.side,"qty":self.qty,"entry_price":self.entry_price,
                "mark_price":self.mark_price,"unrealized_pnl":self.unrealized_pnl,"realized_pnl":self.realized_pnl,
                "roe_pct":self.roe_pct,"leverage":self.leverage,"margin":self.margin,
                "liquidation_price":self.liquidation_price,"tp1_hit":self.tp1_hit,"tp2_hit":self.tp2_hit,
                "trailing_active":self.trailing_active,"trailing_stop":self.trailing_stop,
                "sl_price":self.sl_price,"partial_closed":self.partial_closed,"stale":self.stale,
                "updated_at":self.updated_at,"source":self.source}
class EventBus:
    def __init__(self):
        self._handlers={}; self._queue=qlib.Queue(); self._running=True
        threading.Thread(target=self._process,daemon=True).start()
    def subscribe(self,event_type,handler):
        if event_type not in self._handlers: self._handlers[event_type]=[]
        self._handlers[event_type].append(handler)
    def emit(self,event_type,data=None): self._queue.put((event_type,data))
    def _process(self):
        while self._running:
            try:
                et,dt=self._queue.get(timeout=0.1)
                for h in self._handlers.get(et,[]):
                    try: h(dt)
                    except Exception as e: log_execution(f"[EVENT] handler error: {e}","ERROR")
            except qlib.Empty: continue
            except: continue
class ExchangeSyncService:
    def __init__(self,event_bus):
        self.event_bus=event_bus; self._last_snapshot=PositionSnapshot(); self._last_reconcile=0
    def fetch_live_snapshot(self,symbol):
        if PAPER_MODE: return self._paper_snapshot(symbol)
        try:
            pos=fetch_position(symbol)
            if pos is None:
                if STATE.get("open"): self.event_bus.emit("position_closed_external",{"symbol":symbol})
                return None
            snap=PositionSnapshot(); snap.symbol=symbol
            snap.side='BUY' if pos.get('side','').lower()=='long' else 'SELL'
            snap.qty=safe_float(pos.get('contracts',0)); snap.entry_price=safe_float(pos.get('entryPrice',0))
            snap.mark_price=safe_float(pos.get('markPrice',0)); snap.unrealized_pnl=safe_float(pos.get('unrealizedPnl',0))
            snap.margin=safe_float(pos.get('initialMargin',0)); snap.leverage=safe_float(pos.get('leverage',LEVERAGE))
            snap.liquidation_price=safe_float(pos.get('liquidationPrice',0))
            if snap.margin>0: snap.roe_pct=(snap.unrealized_pnl/snap.margin)*100
            else:
                if snap.side=="BUY": rm=(snap.mark_price-snap.entry_price)/snap.entry_price*100
                else: rm=(snap.entry_price-snap.mark_price)/snap.entry_price*100
                snap.roe_pct=rm*snap.leverage
            snap.updated_at=time.time(); snap.source="rest_sync"
            self._last_snapshot=snap
            return snap
        except Exception as e:
            log_execution(f"[SYNC] REST snapshot error: {e}","ERROR"); return None
    def _paper_snapshot(self,symbol):
        if not STATE.get("open") or STATE.get("current_symbol")!=symbol: return None
        snap=PositionSnapshot(); snap.symbol=symbol; snap.side=STATE["side"]; snap.qty=STATE["qty"]
        snap.entry_price=STATE["entry"]; snap.mark_price=get_ticker_safe(symbol) or snap.entry_price
        snap.unrealized_pnl=(snap.mark_price-snap.entry_price)*snap.qty if snap.side=="BUY" else (snap.entry_price-snap.mark_price)*snap.qty
        snap.margin=snap.entry_price*snap.qty/LEVERAGE
        snap.roe_pct=(snap.unrealized_pnl/snap.margin)*100 if snap.margin else 0
        snap.updated_at=time.time(); snap.source="paper"
        return snap
    def reconcile(self,symbol,local_state):
        now=time.time()
        if now-self._last_reconcile<10: return
        self._last_reconcile=now
        snap=self.fetch_live_snapshot(symbol)
        if snap is None:
            if local_state.get("open"):
                log_execution(f"[RECONCILIATION] Position vanished, marking closed","WARN")
                self.event_bus.emit("force_close_local")
            return
        with _TRADE_LOCK:
            STATE["entry"]=snap.entry_price; STATE["qty"]=snap.qty; STATE["remaining_qty"]=snap.qty
            STATE["side"]=snap.side; STATE["mark_price"]=snap.mark_price
            STATE["unrealized_pnl_usdt"]=snap.unrealized_pnl; STATE["roe_pct"]=snap.roe_pct
            STATE["margin"]=snap.margin; STATE["liquidation_price"]=snap.liquidation_price
            TRADE_STATE.update({"symbol":symbol,"side":snap.side,"entry":snap.entry_price,
                                "qty":snap.qty,"last_update_ts":time.time()})
            if not STATE.get("open"):
                STATE["open"]=True; STATE["current_symbol"]=symbol; STATE["entry_time"]=time.time()
        self.event_bus.emit("reconciled",snap)
class RecoveryGuard:
    def __init__(self,event_bus,exchange_sync):
        self.event_bus=event_bus; self.exchange_sync=exchange_sync
        self.recovery_attempts=0; self.last_recovery=0
    def check_and_recover(self,symbol):
        now=time.time()
        if self.recovery_attempts>5 and now-self.last_recovery<300: return False
        self.event_bus.emit("lifecycle_change",TradeLifecycleState.RECOVERING)
        success=False
        for _ in range(3):
            try:
                snap=self.exchange_sync.fetch_live_snapshot(symbol)
                if snap is not None:
                    self.recovery_attempts=0; self.last_recovery=now
                    self.event_bus.emit("recovery_success",snap); success=True; break
                time.sleep(1)
            except: continue
        if not success:
            self.event_bus.emit("lifecycle_change",TradeLifecycleState.ERROR_DEGRADED)
            self.recovery_attempts+=1; self.last_recovery=now
        return success

# ========== INSTITUTIONAL TREND ENGINE ==========
class TrendState(Enum):
    BULLISH="BULLISH"; BEARISH="BEARISH"; PROBATION_BULLISH="PROBATION_BULLISH"
    PROBATION_BEARISH="PROBATION_BEARISH"; CHOP="CHOP"
class InstitutionalTrendEngine:
    def __init__(self):
        self.trend_state=TrendState.CHOP; self.trend_persistence=0
        self.last_state_change=0; self.state_confidence=0.0
    def analyze_adx_momentum(self,ads):
        if ads is None or len(ads)<10: return {"value":20,"slope":0,"acceleration":0,"state":"UNKNOWN","rising":False}
        cu=ads.iloc[-1]; sl=ads.iloc[-1]-ads.iloc[-4] if len(ads)>=4 else 0
        ac=sl-(ads.iloc[-4]-ads.iloc[-7]) if len(ads)>=7 else 0
        if cu<18: st="CHOP"
        elif cu<25: st="EMERGING"
        elif cu<35: st="HEALTHY"
        elif cu<45: st="STRONG"
        else: st="EXHAUSTION"
        return {"value":cu,"slope":sl,"acceleration":ac,"state":st,"rising":sl>0}
    def analyze_di_pressure(self,df):
        pd_,md_,_,_=get_di_components(df)
        if pd_ is None or md_ is None: return {"dominant":"NEUTRAL","spread":0,"persistent":False}
        sp=pd_-md_
        dom="BUY" if pd_>md_ else "SELL" if md_>pd_ else "NEUTRAL"
        persist=False
        if len(df)>=6:
            bc=0; sc=0
            for i in range(-5,0):
                p,m,_,_=get_di_components(df.iloc[:i+1] if i<0 else df)
                if p is not None and m is not None:
                    if p>m: bc+=1
                    elif m>p: sc+=1
            if dom=="BUY" and bc>=4: persist=True
            elif dom=="SELL" and sc>=4: persist=True
        return {"dominant":dom,"spread":sp,"persistent":persist}
    def analyze_pullback(self,df,side,atr):
        if len(df)<5: return "NO_PULLBACK"
        last=df.iloc[-1]; prev=df.iloc[-5:-1]
        if side=="SELL":
            bcs=[c for i,c in prev.iterrows() if c['close']>c['open']]
            if not bcs and last['close']<=last['open']: return "NO_PULLBACK"
            ab=sum(abs(c['close']-c['open']) for _,c in prev.iterrows())/len(prev)
            uw=sum((c['high']-max(c['close'],c['open'])) for _,c in prev.iterrows())/len(prev)
            vol=df['volume'].iloc[-1]; av=df['volume'].iloc[-10:-1].mean()
            di=self.analyze_di_pressure(df); am=self.analyze_adx_momentum(compute_adx(df))
            wc=(ab<atr*0.4 and uw>ab and vol<av*0.8 and di["dominant"]=="SELL" and am["rising"] and am["state"] in ("HEALTHY","STRONG"))
            if wc: return "WEAK_PULLBACK"
            if last['close']>last['open'] and last['close']>prev['close'].max():
                if vol>av*1.5 and di["dominant"]=="BUY" and not am["rising"]: return "REVERSAL"
            return "STRONG_PULLBACK"
        else:
            bcs=[c for i,c in prev.iterrows() if c['close']<c['open']]
            if not bcs and last['close']>=last['open']: return "NO_PULLBACK"
            ab=sum(abs(c['close']-c['open']) for _,c in prev.iterrows())/len(prev)
            lw=sum((min(c['open'],c['close'])-c['low']) for _,c in prev.iterrows())/len(prev)
            vol=df['volume'].iloc[-1]; av=df['volume'].iloc[-10:-1].mean()
            di=self.analyze_di_pressure(df); am=self.analyze_adx_momentum(compute_adx(df))
            wc=(ab<atr*0.4 and lw>ab and vol<av*0.8 and di["dominant"]=="BUY" and am["rising"] and am["state"] in ("HEALTHY","STRONG"))
            if wc: return "WEAK_PULLBACK"
            if last['close']<last['open'] and last['close']<prev['close'].min():
                if vol>av*1.5 and di["dominant"]=="SELL" and not am["rising"]: return "REVERSAL"
            return "STRONG_PULLBACK"
    def is_chop(self,df):
        adx=compute_adx(df)
        if adx is None or len(adx)<20: return True
        av=adx.iloc[-1]; pd_,md_,_,_=get_di_components(df)
        if pd_ is None or md_ is None: return True
        ds=abs(pd_-md_); atr=compute_atr(df).iloc[-1]
        am=compute_atr(df).rolling(20).mean().iloc[-1] if len(df)>=20 else atr
        af=abs(atr-am)/am<0.1 if am>0 else True
        vs=classify_volume(df)
        lv=vs in ("exhaustion","neutral") and df['volume'].iloc[-1]<df['volume'].rolling(20).mean().iloc[-1]*0.7
        return av<18 and ds<5 and af and lv
    def update_trend_state(self,df,ob):
        ads=compute_adx(df); am=self.analyze_adx_momentum(ads); dp=self.analyze_di_pressure(df)
        ch=self.is_chop(df); now=time.time()
        if ch:
            if self.trend_state!=TrendState.CHOP:
                self.trend_state=TrendState.CHOP; self.last_state_change=now
                self.trend_persistence=0; self.state_confidence=0.0
            return
        bull=(dp["dominant"]=="BUY" and am["rising"] and am["state"] in ("HEALTHY","STRONG"))
        bear=(dp["dominant"]=="SELL" and am["rising"] and am["state"] in ("HEALTHY","STRONG"))
        if bull and not bear: ts=TrendState.BULLISH
        elif bear and not bull: ts=TrendState.BEARISH
        else: ts=TrendState.CHOP
        if ts!=self.trend_state:
            if self.trend_state in (TrendState.BULLISH,TrendState.BEARISH):
                if self.trend_state==TrendState.BULLISH and ts==TrendState.BEARISH: self.trend_state=TrendState.PROBATION_BEARISH
                elif self.trend_state==TrendState.BEARISH and ts==TrendState.BULLISH: self.trend_state=TrendState.PROBATION_BULLISH
                else: self.trend_state=ts
                self.last_state_change=now; self.trend_persistence=0; self.state_confidence=0.3
            elif self.trend_state in (TrendState.PROBATION_BULLISH,TrendState.PROBATION_BEARISH):
                if now-self.last_state_change>3600:
                    self.trend_state=ts; self.state_confidence=0.6
            else:
                self.trend_state=ts; self.last_state_change=now
                self.trend_persistence=0; self.state_confidence=0.5
        else:
            self.trend_persistence+=1
            self.state_confidence=min(1.0,self.state_confidence+0.02)
    def get_trend_health(self,df,side):
        am=self.analyze_adx_momentum(compute_adx(df)); di=self.analyze_di_pressure(df)
        h=5
        if am["rising"]: h+=2
        if am["state"]=="HEALTHY": h+=1
        elif am["state"]=="STRONG": h+=2
        elif am["state"]=="EXHAUSTION": h-=2
        if di["persistent"]: h+=2
        if side=="BUY" and di["dominant"]=="BUY": h+=1
        elif side=="SELL" and di["dominant"]=="SELL": h+=1
        else: h-=2
        return max(0,min(10,h))
trend_engine=InstitutionalTrendEngine()

# ========== TRADE BRAIN ==========
class InstitutionalTradeBrain:
    def __init__(self):
        self.state_machine=TradeStateMachine(); self.last_update=0
        self.current_trade_state="RANGE_CHOP"
    def update(self,smart,momentum,adx,regime):
        self.current_trade_state=self.state_machine.update(smart,momentum,adx,regime)
        self.last_update=time.time()
        return self.current_trade_state
    def get_trail_multiplier(self): return self.state_machine.get_trail_multiplier()
    def should_delay_tp1(self): return self.state_machine.should_delay_tp1()
    def should_aggressive_profit_lock(self): return self.state_machine.should_aggressive_profit_lock()
    def should_hard_exit(self): return self.state_machine.should_hard_exit()
    def get_patience_level(self): return self.state_machine.get_patience_level()

# ========== ORDER VERIFICATION ==========
def verify_order_filled(symbol,order_id,side,expected_qty,timeout=10):
    if PAPER_MODE: return True,expected_qty
    start=time.time(); sym=normalize_symbol(symbol)
    while time.time()-start<timeout:
        try:
            order=safe_api_call(ex.fetch_order,order_id,sym)
            if order:
                status=order.get('status'); filled=order.get('filled',0)
                if status=='closed' and filled>=expected_qty*0.999: return True,filled
                elif status in ('open','partial'):
                    time.sleep(0.5); continue
            time.sleep(0.5)
        except Exception as e:
            log_execution(f"[ORDER_VERIFY] Error: {e}","WARN"); time.sleep(0.5)
    return False,0

# ========== CLOSE FUNCTIONS ==========
def close_partial(ratio):
    global _closing_in_progress
    if _closing_in_progress:
        log_execution("[CLOSE_PARTIAL] Already closing, skipping","WARN"); return
    _closing_in_progress=True
    try:
        if PAPER_MODE:
            if paper["position"]:
                paper["position"]["remaining_qty"]*=(1-ratio)
                STATE["remaining_qty"]*=(1-ratio)
                TRADE_STATE["qty"]=STATE["remaining_qty"]
                log_execution(f"[CLOSE_PARTIAL] Paper partial close {ratio*100:.0f}%","SUCCESS")
            return
        symbol=STATE["current_symbol"]
        qty_to_close=STATE["remaining_qty"]*ratio
        if qty_to_close<=0: return
        side="sell" if STATE["side"]=="BUY" else "buy"
        sym=normalize_symbol(symbol)
        qp=float(ex.amount_to_precision(sym,qty_to_close))
        order=safe_api_call(ex.create_order,sym,"market",side,qp,params={"reduceOnly":True})
        if order is None: log_execution("[CLOSE_PARTIAL] Order failed","ERROR"); return
        oid=order.get('id')
        if not oid: log_execution("[CLOSE_PARTIAL] No order ID","ERROR"); return
        filled,fq=verify_order_filled(symbol,oid,side,qp,timeout=10)
        if filled:
            time.sleep(1)
            pos=fetch_position(symbol)
            if pos is None:
                STATE["open"]=False; TRADE_STATE["in_position"]=False
                DASHBOARD_STATE["live_trade_mode"]=False
                finalize_trade_with_reality(symbol); return
            cq=float(pos.get('contracts',0))
            er=STATE["remaining_qty"]-fq
            if abs(cq-er)<0.0001*max(er,1e-6):
                STATE["remaining_qty"]=cq; TRADE_STATE["qty"]=cq
                log_execution(f"[CLOSE_PARTIAL] Partial confirmed, remaining: {cq:.6f}","SUCCESS")
            else:
                STATE["remaining_qty"]=cq; TRADE_STATE["qty"]=cq
                if cq<=0:
                    STATE["open"]=False; TRADE_STATE["in_position"]=False
                    DASHBOARD_STATE["live_trade_mode"]=False
                    finalize_trade_with_reality(symbol)
            _exchange_sync.reconcile(symbol,STATE)
        else: log_execution("[CLOSE_PARTIAL] Fill timeout","ERROR")
    except Exception as e:
        log_execution(f"[CLOSE_PARTIAL] Error: {traceback.format_exc()}","ERROR")
    finally: _closing_in_progress=False

def close_position_full():
    global _closing_in_progress
    if _closing_in_progress:
        log_execution("[CLOSE] Already closing, skipping","WARN"); return False
    _closing_in_progress=True
    try:
        if PAPER_MODE:
            paper["position"]=None; STATE["open"]=False; TRADE_STATE["in_position"]=False
            DASHBOARD_STATE["live_trade_mode"]=False
            finalize_trade_with_reality(STATE["current_symbol"] if STATE.get("current_symbol") else DEFAULT_SYMBOL)
            log_execution("[CLOSE] Paper position closed","SUCCESS"); return True
        if not STATE["open"]: return False
        symbol=STATE["current_symbol"]; qty_to_close=STATE["remaining_qty"]
        if qty_to_close<=0: return False
        side="sell" if STATE["side"]=="BUY" else "buy"
        sym=normalize_symbol(symbol)
        qp=float(ex.amount_to_precision(sym,qty_to_close))
        for attempt in range(3):
            order=safe_api_call(ex.create_order,sym,"market",side,qp,params={"reduceOnly":True})
            if order is None: time.sleep(1); continue
            oid=order.get('id')
            if not oid: time.sleep(1); continue
            filled,fq=verify_order_filled(symbol,oid,side,qp,timeout=10)
            if filled:
                time.sleep(1)
                pos=fetch_position(symbol)
                if pos is None:
                    STATE["open"]=False; TRADE_STATE["in_position"]=False
                    DASHBOARD_STATE["live_trade_mode"]=False
                    finalize_trade_with_reality(symbol); return True
                else:
                    cq=float(pos.get('contracts',0))
                    if cq<=0:
                        STATE["open"]=False; TRADE_STATE["in_position"]=False
                        DASHBOARD_STATE["live_trade_mode"]=False
                        finalize_trade_with_reality(symbol); return True
                    else:
                        qty_to_close=cq; qp=float(ex.amount_to_precision(sym,qty_to_close)); continue
            else: time.sleep(1); continue
        log_execution("[CLOSE] All attempts failed. Emergency retry.","ERROR")
        try:
            order=safe_api_call(ex.create_order,sym,"market",side,qp,params={"reduceOnly":True})
            if order:
                time.sleep(2)
                pos=fetch_position(symbol)
                if pos is None or float(pos.get('contracts',0))<=0:
                    STATE["open"]=False; TRADE_STATE["in_position"]=False
                    DASHBOARD_STATE["live_trade_mode"]=False
                    finalize_trade_with_reality(symbol); return True
        except Exception as e: log_execution(f"[CLOSE] Emergency failed: {e}","ERROR")
        return False
    except Exception as e:
        log_execution(f"[CLOSE] Error: {traceback.format_exc()}","ERROR"); return False
    finally: _closing_in_progress=False

# ========== LIVE TRADE MANAGER (v29 Fixed) ==========
class LiveTradeManager:
    def __init__(self,event_bus,exchange_sync,recovery_guard):
        self.event_bus=event_bus; self.exchange_sync=exchange_sync; self.recovery=recovery_guard
        self.lifecycle_state=TradeLifecycleState.IDLE
        self.current_snapshot=None; self.last_log_ts=0; self.last_position_sync_ts=0
        self.brain=InstitutionalTradeBrain()
        event_bus.subscribe("reconciled",self._on_reconciled)
        event_bus.subscribe("force_close_local",self._force_close)
        event_bus.subscribe("lifecycle_change",self._set_lifecycle)
    def _set_lifecycle(self,state):
        self.lifecycle_state=state
        log_execution(f"[LIFECYCLE] New state: {state.value}","INFO")
        DASHBOARD_STATE["lifecycle_state"]=state.value
    def _on_reconciled(self,snapshot):
        self.current_snapshot=snapshot
        DASHBOARD_STATE["live_trade_mode"]=True
        # ★★★ FIX: Activate LIVE from any pre-live state ★★★
        if self.lifecycle_state in (TradeLifecycleState.RECOVERING,TradeLifecycleState.OPEN_PENDING_CONFIRMATION,
                                     TradeLifecycleState.OPEN_REQUESTED,TradeLifecycleState.IDLE):
            self.lifecycle_state=TradeLifecycleState.LIVE
            DASHBOARD_STATE["lifecycle_state"]="LIVE"
            log_execution(f"[LIFECYCLE] ✅ Activated LIVE mode for {snapshot.symbol}","SUCCESS")
    def _force_close(self,_):
        if STATE["open"]:
            close_position_full(); self.lifecycle_state=TradeLifecycleState.CLOSED
            DASHBOARD_STATE["live_trade_mode"]=False
    def start_trade(self,symbol,side,entry_price,qty,sl,tp1,tp2):
        self.lifecycle_state=TradeLifecycleState.OPEN_PENDING_CONFIRMATION
        self.event_bus.emit("lifecycle_change",TradeLifecycleState.OPEN_PENDING_CONFIRMATION)
        log_execution(f"[LIFECYCLE] Trade open requested for {symbol} {side}","INFO")
    def set_entry_atr(self,entry_atr):
        STATE["entry_atr"]=entry_atr
        base_sl_mult=1.6
        if STATE["side"]=="BUY": STATE["synthetic_sl"]=STATE["entry"]-entry_atr*base_sl_mult
        else: STATE["synthetic_sl"]=STATE["entry"]+entry_atr*base_sl_mult
        # ★ FIX: guard against zero
        if STATE["synthetic_sl"]<=0:
            STATE["synthetic_sl"]=STATE["entry"]*(0.97 if STATE["side"]=="BUY" else 1.03)
        log_execution(f"[SL_INIT] {STATE['side']} SL={STATE['synthetic_sl']:.4f} (entry={STATE['entry']:.4f}, ATR={entry_atr:.4f})","INFO")
    def manage_live_trade(self):
        """★ SINGLE entry point - delegates everything to Unified Manager"""
        if not (STATE.get("open") and STATE.get("current_symbol")):
            if self.lifecycle_state not in (TradeLifecycleState.IDLE,TradeLifecycleState.CLOSED):
                self.lifecycle_state=TradeLifecycleState.IDLE
                DASHBOARD_STATE["live_trade_mode"]=False
            return
        # ★ Force LIVE if position is open
        if self.lifecycle_state!=TradeLifecycleState.LIVE:
            self.lifecycle_state=TradeLifecycleState.LIVE
            DASHBOARD_STATE["lifecycle_state"]="LIVE"
        now=time.time()
        if now-self.last_position_sync_ts>=10:
            self.exchange_sync.reconcile(STATE["current_symbol"],STATE)
            self.last_position_sync_ts=now
        if _unified_manager is not None:
            _unified_manager.run()
        self._log_live_status()
    def _log_live_status(self):
        now=time.time()
        if now-self.last_log_ts<5: return
        if not STATE.get("open"): return
        self.last_log_ts=now
        roe=STATE.get("roe_pct",0.0); side=STATE.get("side","?")
        di="🟢" if side=="BUY" else "🔴"
        rc=color_pnl(roe)
        ca=STATE.get("last_council_action","HOLD")
        log_execution(f"{BLUE}[LIVE]{RESET} {di} {STATE['current_symbol']} {side} | Entry: {STATE['entry']:.2f} | Mark: {STATE.get('mark_price',0):.2f} | ROE: {rc} | SL: {STATE.get('synthetic_sl',0):.4f} | Trail: {'✅' if STATE.get('trail_activated',False) else '❌'} | TP1: {'✅' if STATE.get('tp1_hit',False) else '❌'} | Council: {ca}","INFO")

# ========== STATE INIT ==========
STATE={"open":False,"side":None,"entry":0.0,"qty":0.0,"remaining_qty":0.0,
    "sl":0.0,"tp1_done":False,"trail_activated":False,"trail_stop":0.0,
    "peak":0.0,"cooldown_until":None,"daily_trades":0,"last_trade_day":None,
    "consecutive_losses":0,"daily_peak_balance":None,"daily_loss_limit_hit":False,
    "current_symbol":None,"balance":0.0,"atr":0.0,"entry_time":None,
    "entry_reasons":[],"trade_score":0,"partial_closed":False,
    "tp1_price":0.0,"tp2_price":0.0,"trade_type":None,"entry_type":None,
    "be_done":False,"classification":None,"location":None,"zone_info":None,
    "runner_active":False,"scale_ins":0,"decision_log":[],
    "tp1_hit":False,"tp2_hit":False,"zone":{},
    "initial_margin":0.0,"real_unrealized_pnl":0.0,"roe_pct":0.0,"leverage":LEVERAGE,
    "smart_tightened":False,"smart_partial_done":False,"smart_exit_triggered":False,
    "mark_price":0.0,"unrealized_pnl_usdt":0.0,"margin":0.0,"liquidation_price":0.0,
    "narrative_classification":None,"narrative_confidence":0.0,"confidence_level":None,
    "continuation_probability":0.5,"hold_quality":"UNKNOWN","counter_pressure":0.0,
    "reclaim_risk":0.0,"trend_strength":0.0,"continuation_reasons":[],
    "trade_thesis":None,"current_confidence":50.0,"market_regime":"UNKNOWN",
    "continuation_pressure":50,"thesis_failure_score":0,"prev_di_spread":0.0,
    "adx_live":0.0,"di_plus_live":0.0,"di_minus_live":0.0,
    "trade_personality":"NEUTRAL","institutional_flow":"NEUTRAL",
    "profit_lock_activated":False,"trail_tightened":False,
    "smart_money":{},"momentum_flow":{},"trade_state":"RANGE_CHOP",
    "delay_tp1":False,"smart_trail_mult":1.5,
    "synthetic_sl":0.0,"synthetic_tp1":0.0,
    "max_price":0.0,"min_price":0.0,"peak_roe":0.0,"peak_price":0.0,
    "peak_unrealized_pnl":0.0,"drawdown_from_peak":0.0,
    "tp1_hold_score":10,"exit_warning":0,"runner_mode":False,"entry_atr":0.0,
    "last_council_action":"N/A","last_council_reason":"","last_council_confidence":0,
    "last_council_decision":None,
    "dyn_trail_active":False,"dyn_tp1_hit":False,"dyn_tp2_hit":False,
    "dyn_runner":False,"dyn_drawdown":0.0,"dyn_lifecycle":"N/A"}
paper={"balance":10000.0,"position":None}
_ACTIVE_TRADE=False; _closing_in_progress=False
_TRADE_LOCK=threading.RLock()

DASHBOARD_STATE={"account":{"balance":0.0,"free_balance":0.0,"available_margin":0.0,"mode":"PAPER"},
    "stats":{"trades":0,"wins":0,"losses":0,"win_rate":0.0},
    "position":None,"logs":[],"errors":[],"live_trade_mode":False,
    "lifecycle_state":"IDLE","live_supervisor":{},"institutional_flow":{}}

def log_execution(msg,level="INFO",debounce_key=None,debounce_sec=60):
    if debounce_key:
        now=time.time()
        last=MEMORY.get("log_debounce",{}).get(debounce_key,0)
        if now-last<debounce_sec: return
        MEMORY.setdefault("log_debounce",{})[debounce_key]=now
    ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if level=="INFO": colored=color_text(msg,CYAN)
    elif level=="SUCCESS": colored=color_text(msg,GREEN)
    elif level=="ERROR": colored=color_text(msg,RED)
    elif level=="WARN": colored=color_text(msg,YELLOW)
    else: colored=msg
    entry=f"[{ts}] {msg}"
    DASHBOARD_STATE["logs"].append(entry)
    if len(DASHBOARD_STATE["logs"])>200: DASHBOARD_STATE["logs"].pop(0)
    print(colored)
    if level=="ERROR":
        DASHBOARD_STATE["errors"].append(entry)
        if len(DASHBOARD_STATE["errors"])>50: DASHBOARD_STATE["errors"].pop(0)
        tg_error(msg,level)

def update_stats(pnl_pct):
    """★ FIXED: sync from PERF (single source of truth)"""
    DASHBOARD_STATE["stats"]={"trades":PERF["trades"],"wins":PERF["wins"],
                               "losses":PERF["losses"],
                               "win_rate":(PERF["wins"]/PERF["trades"]*100) if PERF["trades"] else 0.0}

def open_position(side,amount,symbol):
    global _ACTIVE_TRADE,INSUFFICIENT_MARGIN_COOLDOWN_UNTIL
    sym=normalize_symbol(symbol)
    with _TRADE_LOCK:
        if _ACTIVE_TRADE: log_execution("[OPEN] Another trade already in progress","WARN"); return None
        _ACTIVE_TRADE=True
    try:
        set_leverage(symbol,LEVERAGE)
        amount=float(ex.amount_to_precision(sym,amount))
        bal=safe_api_call(ex.fetch_balance)
        if bal is None:
            with _TRADE_LOCK: _ACTIVE_TRADE=False
            return None
        usdt=bal.get("free",{}).get("USDT",0.0)
        ticker=safe_api_call(ex.fetch_ticker,sym)
        if ticker is None:
            with _TRADE_LOCK: _ACTIVE_TRADE=False
            return None
        price=ticker["last"]
        rm=(amount*price)/LEVERAGE
        if usdt<rm*1.01:
            log_execution(f"[OPEN] Insufficient margin: need {rm:.2f}, have {usdt:.2f}","ERROR")
            with _TRADE_LOCK: _ACTIVE_TRADE=False
            INSUFFICIENT_MARGIN_COOLDOWN_UNTIL=time.time()+INSUFFICIENT_MARGIN_COOLDOWN_SEC
            return None
        max_spread=dynamic_spread_tolerance(symbol); spread=get_spread_bps(symbol)
        if spread>max_spread:
            log_execution(f"[OPEN] Spread {spread:.2f}% > {max_spread}%","WARN")
            with _TRADE_LOCK: _ACTIVE_TRADE=False
            return None
        order=safe_api_call(ex.create_order,sym,"market",side.lower(),amount,params={"leverage":LEVERAGE})
        if order:
            log_execution(f"[OPEN] Order filled: {side} {amount} {symbol} @ {price}","SUCCESS")
            return order
    except Exception as e: log_execution(f"[OPEN] Open position error: {traceback.format_exc()}","ERROR")
    with _TRADE_LOCK: _ACTIVE_TRADE=False
    return None

def dynamic_spread_tolerance(symbol):
    df=get_ohlcv_safe(symbol,50)
    if df is None: return MAX_SPREAD_PERCENT_DEFAULT
    atr=compute_atr(df).iloc[-1]; price=df['close'].iloc[-1]
    atrp=(atr/price)*100 if price>0 else 0.5
    if atrp>2.0: return MAX_SPREAD_PERCENT_VOLATILE
    return MAX_SPREAD_PERCENT_DEFAULT

def finalize_trade_with_reality(symbol):
    """★ FIXED: unified ROE% based PnL"""
    mark,unreal,margin,roe=sync_position_state(symbol)
    if mark is None and not PAPER_MODE: mark=get_ticker_safe(symbol) or STATE.get("mark_price",STATE["entry"])
    entry=STATE["entry"]; side=STATE["side"]; leverage=STATE.get("leverage",LEVERAGE)
    if entry and entry>0:
        if side=="BUY": rmp=(mark-entry)/entry*100
        else: rmp=(entry-mark)/entry*100
    else: rmp=0.0
    pnl_pct=rmp*leverage
    mg=STATE.get("margin",0)
    if mg>0: pnl_usdt=mg*(pnl_pct/100)
    else:
        q=STATE.get("qty",0); pnl_usdt=rmp/100*entry*q if entry else 0
    PERF["total_pnl_pct"]+=pnl_pct; PERF["total_pnl_usdt"]+=pnl_usdt; PERF["trades"]+=1
    if pnl_pct>=0: PERF["wins"]+=1; result="WIN"
    else: PERF["losses"]+=1; result="LOSS"
    PERF["last_trade"]={"result":result,"pnl_pct":pnl_pct}
    update_stats(pnl_pct)
    TRADE_STATE.update({"in_position":False,"symbol":None,"side":None,"entry":0.0,"qty":0.0,
                        "tp1_hit":False,"tp2_hit":False,"trail_on":False,"zone":None,
                        "location":None,"reason":[]})
    DASHBOARD_STATE["live_trade_mode"]=False
    log_execution(f"Trade closed: {result} ROE={pnl_pct:.2f}% | USDT: {pnl_usdt:+.2f}","SUCCESS" if pnl_pct>=0 else "ERROR")
    try: tg_close(STATE["current_symbol"],pnl_pct,(time.time()-STATE["entry_time"])/60,STATE["side"])
    except: pass
    with _TRADE_LOCK:
        STATE["open"]=False; STATE["side"]=None; STATE["current_symbol"]=None
        STATE["tp1_hit"]=False; STATE["tp2_hit"]=False
        STATE["trail_activated"]=False; STATE["profit_lock_activated"]=False
        STATE["runner_mode"]=False; STATE["trail_tightened"]=False
        STATE["partial_closed"]=False; STATE["scale_ins"]=0
        STATE["last_council_action"]="N/A"; STATE["last_council_reason"]=""; STATE["last_council_confidence"]=0
        STATE["peak_roe"]=0.0; STATE["drawdown_from_peak"]=0.0
        if "dynamic_manager" in STATE: del STATE["dynamic_manager"]
    return pnl_usdt,pnl_pct

def get_realized_pnl_for_symbol(symbol,lookback_seconds=30):
    if PAPER_MODE: return 0.0,0.0
    try:
        sym=normalize_symbol(symbol)
        since=int((time.time()-lookback_seconds)*1000)
        trades=safe_api_call(ex.fetch_my_trades,sym,limit=100,params={'since':since})
        if not trades: return 0.0,0.0
        pnl_usdt=0.0
        for t in trades:
            side=t['side'].lower(); qty=t['amount']; price=t['price']
            cost=qty*price
            if side=='buy': pnl_usdt-=cost
            else: pnl_usdt+=cost
        bal=get_balance_safe(); pnl_pct=(pnl_usdt/bal*100) if bal>0 else 0.0
        return pnl_usdt,pnl_pct
    except Exception as e:
        log_execution(f"[REALIZED_PNL] Error: {e}","WARN"); return 0.0,0.0

# ========== INDICATORS ==========
def rma(s,p): return s.ewm(alpha=1/p,adjust=False).mean()
def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def compute_atr(df,period=14):
    if df is None or len(df)<period+1: return pd.Series([0.0]*len(df))
    h=df['high']; l=df['low']; c=df['close']
    tr1=h-l; tr2=(h-c.shift(1)).abs(); tr3=(l-c.shift(1)).abs()
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    atr=rma(tr,period); atr=atr.bfill().ffill().fillna(tr.mean()).clip(lower=1e-8)
    return atr
def compute_adx(df,period=14):
    if df is None or len(df)<period*2: return pd.Series([0.0]*len(df))
    h=df['high']; l=df['low']; c=df['close']
    tr1=h-l; tr2=(h-c.shift(1)).abs(); tr3=(l-c.shift(1)).abs()
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    atr=rma(tr,period)+1e-9
    um=h.diff(); dm=-l.diff()
    pdm=np.where((um>dm)&(um>0),um,0.0); mdm=np.where((dm>um)&(dm>0),dm,0.0)
    pdm=pd.Series(pdm,index=df.index); mdm=pd.Series(mdm,index=df.index)
    pdi=100*rma(pdm,period)/(atr+1e-9); mdi=100*rma(mdm,period)/(atr+1e-9)
    dx=(abs(pdi-mdi)/(pdi+mdi+1e-9))*100
    adx=rma(dx,period)
    return adx.bfill().ffill().fillna(0).clip(0,100)
def compute_rsi(df,period=14):
    if df is None or len(df)<period+1: return pd.Series([50.0]*len(df))
    c=df['close']; delta=c.diff()
    g=delta.clip(lower=0); l=-delta.clip(upper=0)
    ag=rma(g,period)+1e-9; al=rma(l,period)+1e-9
    rs=ag/(al+1e-9); rsi=100-(100/(1+rs))
    return rsi.bfill().ffill().fillna(50).clip(0,100)
def compute_macd(df,fast=12,slow=26,signal=9):
    ef=df['close'].ewm(span=fast,adjust=False).mean(); es=df['close'].ewm(span=slow,adjust=False).mean()
    ml=ef-es; sl=ml.ewm(span=signal,adjust=False).mean()
    return ml,sl,ml-sl
def macd_first_flip(hist):
    if len(hist)<2: return False
    return hist.iloc[-2]<0 and hist.iloc[-1]>0
def volume_pressure_real(df,window=20,threshold=1.2):
    if len(df)<window+1: return False
    vol=df['volume']; m=vol.rolling(window).mean().iloc[-1]; s=vol.rolling(window).std().iloc[-1]
    if s==0: return False
    return (vol.iloc[-1]-m)/s>threshold
def flow_engine(df):
    if len(df)<2: return "neutral"
    last=df.iloc[-1]; body=last['close']-last['open']; vol=last['volume']
    av=df['volume'].rolling(20).mean().iloc[-1] if len(df)>=20 else vol
    if vol>av*1.5: return "aggressive_buy" if body>0 else "aggressive_sell"
    if vol>av and abs(body)<(last['high']-last['low'])*0.3: return "absorption"
    return "neutral"
def orderbook_imbalance(ob,depth=10):
    if not ob or 'bids' not in ob or 'asks' not in ob: return 0.0
    bs=sum([b[1] for b in ob['bids'][:depth]]) if ob['bids'] else 0
    as_=sum([a[1] for a in ob['asks'][:depth]]) if ob['asks'] else 0
    t=bs+as_
    if t==0: return 0.0
    return (bs-as_)/t
def detect_walls(ob,depth=10,threshold=3.0):
    if not ob or 'bids' not in ob or 'asks' not in ob: return False,False
    bs=[b[1] for b in ob['bids'][:depth]]; as_=[a[1] for a in ob['asks'][:depth]]
    bw=any(s>(sum(bs)/len(bs))*threshold for s in bs) if bs else False
    aw=any(s>(sum(as_)/len(as_))*threshold for s in as_) if as_ else False
    return bw,aw
def is_late_move(df,atr,multiplier=1.5):
    if len(df)<1 or atr<=0: return False
    last=df.iloc[-1]
    return (last['high']-last['low'])>multiplier*atr
def early_score(df,ob,atr,side):
    sc=0; reasons=[]
    m,s,h=compute_macd(df)
    if macd_first_flip(h): sc+=2; reasons.append("macd_flip")
    if volume_pressure_real(df): sc+=2; reasons.append("volume_pressure")
    fl=flow_engine(df)
    if side=="BUY" and fl=="aggressive_buy": sc+=2; reasons.append("flow_buy")
    elif side=="SELL" and fl=="aggressive_sell": sc+=2; reasons.append("flow_sell")
    elif fl=="absorption": reasons.append("absorption")
    obi=orderbook_imbalance(ob,depth=10)
    if side=="BUY" and obi>0.2: sc+=2; reasons.append(f"obi_bullish_{obi:.2f}")
    elif side=="SELL" and obi<-0.2: sc+=2; reasons.append(f"obi_bearish_{obi:.2f}")
    bw,aw=detect_walls(ob,depth=10,threshold=3.0)
    if side=="BUY" and bw: sc+=1; reasons.append("bid_wall")
    elif side=="SELL" and aw: sc+=1; reasons.append("ask_wall")
    if is_late_move(df,atr,multiplier=1.5): sc-=3; reasons.append("late_move_penalty")
    return sc,reasons

# ========== RF ENGINE ==========
class RFEngine:
    def __init__(self,period=20,multiplier=3.5):
        self.period=period; self.multiplier=multiplier
    def ema(self,s,length): return s.ewm(span=length,adjust=False).mean()
    def rng_size(self,x):
        n=self.period; q=self.multiplier; w=(n*2)-1
        avrng=self.ema((x-x.shift(1)).abs(),n)
        return self.ema(avrng,w)*q
    def rng_filt(self,x,rng):
        filt=np.zeros(len(x)); hi=np.zeros(len(x)); lo=np.zeros(len(x))
        for i in range(len(x)):
            if i==0: filt[i]=x.iloc[i]
            else:
                prev=filt[i-1]; r=rng.iloc[i]
                if x.iloc[i]-r>prev: filt[i]=x.iloc[i]-r
                elif x.iloc[i]+r<prev: filt[i]=x.iloc[i]+r
                else: filt[i]=prev
            hi[i]=filt[i]+rng.iloc[i]; lo[i]=filt[i]-rng.iloc[i]
        return pd.Series(hi,index=x.index),pd.Series(lo,index=x.index),pd.Series(filt,index=x.index)
    def compute(self,df,src="close"):
        x=df[src]; rng=self.rng_size(x)
        h,l,filt=self.rng_filt(x,rng)
        fdir=np.zeros(len(filt))
        for i in range(1,len(filt)):
            if filt.iloc[i]>filt.iloc[i-1]: fdir[i]=1
            elif filt.iloc[i]<filt.iloc[i-1]: fdir[i]=-1
            else: fdir[i]=fdir[i-1]
        lc=(x>filt)&(pd.Series(fdir)==1); sc=(x<filt)&(pd.Series(fdir)==-1)
        ci=np.zeros(len(x))
        for i in range(1,len(x)):
            if lc.iloc[i]: ci[i]=1
            elif sc.iloc[i]: ci[i]=-1
            else: ci[i]=ci[i-1]
        ls=lc&(pd.Series(ci).shift(1)==-1); ss=sc&(pd.Series(ci).shift(1)==1)
        sig=None
        if ls.iloc[-1]: sig="BUY"
        elif ss.iloc[-1]: sig="SELL"
        trig=bool(ls.iloc[-1] or ss.iloc[-1])
        dist=(x.iloc[-1]-filt.iloc[-1])/x.iloc[-1] if x.iloc[-1]!=0 else 0
        return {"signal":sig,"triggered":trig,"filt":filt.iloc[-1],"h_band":h.iloc[-1],
                "l_band":l.iloc[-1],"distance":dist}

# ========== CANDLE INTELLIGENCE ==========
def candle_metrics(c):
    b=abs(c['close']-c['open']); r=c['high']-c['low']
    uw=c['high']-max(c['open'],c['close']); lw=min(c['open'],c['close'])-c['low']
    return b,r,uw,lw
def is_pinbar(c,atr,side,bmin=0.5,wbr=2.5,wrr=0.6):
    b,r,uw,lw=candle_metrics(c)
    if r==0 or atr<=0: return False
    if side=="BUY": return lw>=wbr*b and lw/r>=wrr and b/atr>=bmin
    return uw>=wbr*b and uw/r>=wrr and b/atr>=bmin
def classify_volume(df,period=20,et=1.8,nt=1.3,ext=0.7):
    if len(df)<period+1: return "neutral"
    vol=df['volume']; av=vol.rolling(period).mean().iloc[-1]
    if av==0: return "neutral"
    r=vol.iloc[-1]/av
    if r>et: return "expansion"
    elif r>nt: return "normal"
    elif r<ext: return "exhaustion"
    return "neutral"
def detect_displacement(df,side,atr,vs,bat=0.8,ver=False):
    if len(df)<2: return False
    last=df.iloc[-1]; b,_,_,_=candle_metrics(last)
    if b/atr<bat: return False
    if side=="BUY" and last['close']<=last['open']: return False
    if side=="SELL" and last['close']>=last['open']: return False
    if ver and vs!="expansion": return False
    return True
def detect_location(df,price,sup,res,threshold=0.003):
    ns=False; nr=False
    if sup:
        if min(abs(price-s)/price for s in sup)<threshold: ns=True
    if res:
        if min(abs(price-r)/price for r in res)<threshold: nr=True
    if ns and not nr: return "LOW"
    elif nr and not ns: return "HIGH"
    return "MID"
def get_liquidity_sweep_for_side(df,side,lookback=5):
    ctx=detect_liquidity_context(df,lookback=lookback)
    if side=="BUY" and ctx=="sell_side_taken": return True
    if side=="SELL" and ctx=="buy_side_taken": return True
    return False
def get_rejection_pinbar(df,side,atr):
    if len(df)<1: return False
    return is_pinbar(df.iloc[-1],atr,side)
def advanced_detect_scenario(df,side,atr,vs):
    if len(df)<3: return "NONE"
    sw=get_liquidity_sweep_for_side(df,side); rj=get_rejection_pinbar(df,side,atr)
    di=detect_displacement(df,side,atr,vs,bat=0.8,ver=False)
    if sw and rj: return "TRAP_REVERSAL"
    elif di and not rj: return "TREND_CONTINUATION"
    return "NONE"
def advanced_decision_engine(scenario,adx,vs,location):
    if scenario=="NONE": return "SKIP",None
    if vs=="exhaustion": return "SKIP",None
    adx=float(adx) if adx is not None else 20.0
    if adx<18: return "SKIP",None
    if scenario=="TRAP_REVERSAL":
        if adx<35: return "ENTER","STRONG"
        return "SKIP",None
    elif scenario=="TREND_CONTINUATION":
        if 20<adx<45: return "ENTER","MEDIUM"
        return "SKIP",None
    return "SKIP",None

# ========== LEGACY SMC ==========
def detect_bos(df,lookback=5):
    if len(df)<lookback+2: return False,False
    rh=df['high'].iloc[-lookback-1:-1].max(); rl=df['low'].iloc[-lookback-1:-1].min()
    cc=df['close'].iloc[-1]
    return cc>rh,cc<rl
def detect_scenario(df):
    if len(df)<30: return "NONE"
    row=df.iloc[-1]
    lc=detect_liquidity_context(df,lookback=10)
    su=(lc=="buy_side_taken"); sd=(lc=="sell_side_taken")
    bu,bd=detect_bos(df)
    vsf=volume_spike(df)
    vsma=df['volume'].iloc[-21:-1].mean() if len(df)>=21 else df['volume'].mean()
    vo=row['volume']>1.5*vsma if vsma>0 else False
    r=row['high']-row['low']
    if r==0: rb=False; rs=False
    else:
        b=abs(row['close']-row['open'])
        lw=min(row['open'],row['close'])-row['low']; uw=row['high']-max(row['open'],row['close'])
        rb=(lw>2*b+1e-9) or (row['close']>row['open'] and b/r>0.5)
        rs=(uw>2*b+1e-9) or (row['close']<row['open'] and b/r>0.5)
    if sd and rb: return "REVERSAL_BUY"
    if su and rs: return "REVERSAL_SELL"
    if bu and vo: return "TREND_BUY"
    if bd and vo: return "TREND_SELL"
    if sd and not rb: return "TRAP_SELL"
    if su and not rs: return "TRAP_BUY"
    return "NONE"
def decision_engine(scenario,rf_signal,adx):
    if scenario=="NONE": return "SKIP"
    if scenario=="REVERSAL_BUY" and rf_signal=="BUY": return "STRONG" if adx<35 else "SKIP"
    if scenario=="REVERSAL_SELL" and rf_signal=="SELL": return "STRONG" if adx<35 else "SKIP"
    if scenario=="TREND_BUY" and rf_signal=="BUY": return "MEDIUM" if 20<adx<45 else "SKIP"
    if scenario=="TREND_SELL" and rf_signal=="SELL": return "MEDIUM" if 20<adx<45 else "SKIP"
    if "TRAP" in scenario: return "STRONG"
    return "SKIP"

def detect_liquidity_context(df,lookback=10):
    sweeps=[]
    for i in range(-lookback,0):
        if i==-1: continue
        pl=df['low'].iloc[i-1]; cl=df['low'].iloc[i]
        lw=min(df['open'].iloc[i],df['close'].iloc[i])-cl
        if cl<pl and lw>0.0001: sweeps.append("sell_side_taken")
        ph=df['high'].iloc[i-1]; ch=df['high'].iloc[i]
        uw=ch-max(df['open'].iloc[i],df['close'].iloc[i])
        if ch>ph and uw>0.0001: sweeps.append("buy_side_taken")
    if len(sweeps)==0: return None
    return sweeps[-1]
def detect_zone_context(price,sup,res,threshold=0.003):
    ns=min([abs(price-s)/price for s in sup])<threshold if sup else False
    nr=min([abs(price-r)/price for r in res])<threshold if res else False
    return {"near_support":ns,"near_resistance":nr}
def detect_structure_shift(df):
    if len(df)<10: return None
    lh=df['high'].iloc[-3]; ph=df['high'].iloc[-6]
    ll=df['low'].iloc[-3]; pl=df['low'].iloc[-6]
    if lh>ph and ll>pl: return "bullish_shift"
    elif lh<ph and ll<pl: return "bearish_shift"
    return None
def get_clustered_zones(df,lookback=120,cluster_pct=0.002):
    highs=df['high'].values[-lookback:]; lows=df['low'].values[-lookback:]
    sh=[highs[i] for i in range(2,len(highs)-2) if highs[i]==max(highs[i-2:i+3])]
    sl=[lows[i] for i in range(2,len(lows)-2) if lows[i]==min(lows[i-2:i+3])]
    def cl(points,pct):
        if not points: return []
        pts=sorted(points); cls=[]; cu=[pts[0]]
        for p in pts[1:]:
            if abs(p-cu[-1])/p<pct: cu.append(p)
            else: cls.append(sum(cu)/len(cu)); cu=[p]
        cls.append(sum(cu)/len(cu))
        return cls
    return cl(sl,cluster_pct),cl(sh,cluster_pct)
def detect_liquidity_cluster(df,lb=20,tol=0.001):
    h=df['high'].iloc[-lb:]; l=df['low'].iloc[-lb:]
    if h.max()==h.min() or l.max()==l.min(): return False,False
    return (h.max()-h.min())/h.mean()<tol,(l.max()-l.min())/l.mean()<tol
def candle_rejection(df,side):
    if len(df)<1: return False
    last=df.iloc[-1]; r=last['high']-last['low']
    if r==0: return False
    b=abs(last['close']-last['open'])
    if side=="BUY":
        lw=min(last['open'],last['close'])-last['low']
        return (lw>1.5*b) or (last['close']>last['open'] and b/r>0.5)
    else:
        uw=last['high']-max(last['open'],last['close'])
        return (uw>1.5*b) or (last['close']<last['open'] and b/r>0.5)
def volume_spike(df):
    if len(df)<21: return False
    av=df['volume'].iloc[-21:-1].mean(); lv=df['volume'].iloc[-1]
    return lv>=1.5*av
def is_late_entry(df,side):
    if len(df)<6: return False
    l5=abs(df['close'].iloc[-1]-df['close'].iloc[-6])/df['close'].iloc[-6]
    if l5>0.008:
        if side=="BUY":
            rh=df['high'].iloc[-5:].max()
            pb=(rh-df['close'].iloc[-1])/(rh-df['close'].iloc[-6]) if (rh-df['close'].iloc[-6])!=0 else 0
            if pb<0.3: return True
        else:
            rl=df['low'].iloc[-5:].min()
            pb=(df['close'].iloc[-1]-rl)/(df['close'].iloc[-6]-rl) if (df['close'].iloc[-6]-rl)!=0 else 0
            if pb<0.3: return True
    return False
def compute_location(df,price,side):
    l50=df['low'].iloc[-50:].min(); h50=df['high'].iloc[-50:].max()
    if h50==l50: return "mid"
    rel=(price-l50)/(h50-l50)
    if side=="BUY":
        if rel<=0.3: return "discount"
        elif rel>=0.7: return "premium"
        return "mid"
    else:
        if rel>=0.7: return "premium"
        elif rel<=0.3: return "discount"
        return "mid"
def swing_points(df,lb=5):
    highs=df['high'].values; lows=df['low'].values
    sh=[]; sl=[]
    for i in range(lb,len(df)-lb):
        if highs[i]==max(highs[i-lb:i+lb+1]): sh.append((i,highs[i]))
        if lows[i]==min(lows[i-lb:i+lb+1]): sl.append((i,lows[i]))
    return sh,sl
def equal_levels(points,tolerance=0.0015):
    if len(points)<2: return False
    avg=sum(points)/len(points)
    return all(abs(p-avg)/avg<tolerance for p in points)
def build_liquidity_pools(df):
    sh,sl=swing_points(df,lb=5)
    rh=[p[1] for p in sh[-3:]] if len(sh)>=3 else [sh[-1][1]] if sh else []
    ph=rh if (len(rh)>=2 and equal_levels(rh)) else ([sh[-1][1]] if sh else [])
    rl=[p[1] for p in sl[-3:]] if len(sl)>=3 else [sl[-1][1]] if sl else []
    pl=rl if (len(rl)>=2 and equal_levels(rl)) else ([sl[-1][1]] if sl else [])
    return {"high_pools":ph,"low_pools":pl}
def detect_sweep(df,pools):
    if len(df)<2: return False,False
    last=df.iloc[-1]; prev=df.iloc[-2]
    sh=False; sl=False
    for h in pools["high_pools"]:
        if last['high']>h and prev['high']<=h and last['close']<last['high']: sh=True; break
    for l in pools["low_pools"]:
        if last['low']<l and prev['low']>=l and last['close']>last['low']: sl=True; break
    return sh,sl
def volume_engine(df):
    av=df['volume'].iloc[-20:].mean() if len(df)>=20 else df['volume'].mean()
    lv=df['volume'].iloc[-1]
    if lv>=1.5*av: return "spike",2
    elif lv<0.7*av: return "exhaustion",-1
    else:
        last=df.iloc[-1]; b=abs(last['close']-last['open']); r=last['high']-last['low']
        if r>0 and b/r<0.4 and lv>av: return "absorption",1
        return "normal",0
def pre_rf_context_boost(df,side):
    if len(df)<3: return 0,[]
    last2=df.iloc[-3:-1]; bo=0; reasons=[]
    if side=="BUY":
        if last2['close'].iloc[-2]<last2['close'].iloc[-1] and last2['close'].iloc[-1]<df['close'].iloc[-1]:
            bo+=1; reasons.append("consecutive_bullish")
        if (last2['close'].iloc[-1]-last2['low'].iloc[-1])/(last2['high'].iloc[-1]-last2['low'].iloc[-1]+1e-9)>0.7:
            bo+=1; reasons.append("strong_bullish_candle")
    else:
        if last2['close'].iloc[-2]>last2['close'].iloc[-1] and last2['close'].iloc[-1]>df['close'].iloc[-1]:
            bo+=1; reasons.append("consecutive_bearish")
        if (last2['high'].iloc[-1]-last2['close'].iloc[-1])/(last2['high'].iloc[-1]-last2['low'].iloc[-1]+1e-9)>0.7:
            bo+=1; reasons.append("strong_bearish_candle")
    return min(bo,2),reasons
def market_intent(df):
    if len(df)<20: return None,0
    rr=df['high'].iloc[-10:].max()-df['low'].iloc[-10:].min()
    ar=(df['high'].rolling(20).max()-df['low'].rolling(20).min()).iloc[-1]
    ab=(rr/ar)<0.5 if ar>0 else False
    vs,_=volume_engine(df)
    if ab and vs=="absorption": return "accumulation",1
    last=df.iloc[-1]; prev=df.iloc[-2]
    if vs=="spike" and last['close']<prev['high'] and last['high']>prev['high']: return "distribution",1
    if len(df)>=3:
        c1=df.iloc[-3]; c2=df.iloc[-2]; c3=df.iloc[-1]
        if c2['high']>c1['high'] and c3['close']<c2['high'] and c3['close']<c3['open']: return "trap",2
        if c2['low']<c1['low'] and c3['close']>c2['low'] and c3['close']>c3['open']: return "trap",2
    return None,0
def compute_sl_tp(entry_price,side,classification,atr,df):
    if classification=="REVERSAL":
        pools=build_liquidity_pools(df)
        if side=="BUY": sl=min(pools["low_pools"])-0.5*atr if pools["low_pools"] else entry_price-atr*1.2
        else: sl=max(pools["high_pools"])+0.5*atr if pools["high_pools"] else entry_price+atr*1.2
        msd=1.2*atr
        if abs(entry_price-sl)<msd: sl=entry_price-msd if side=="BUY" else entry_price+msd
        tp1=entry_price*(1+0.005) if side=="BUY" else entry_price*(1-0.005)
        tp2=entry_price*(1+0.01) if side=="BUY" else entry_price*(1-0.01)
    elif classification=="EARLY_TREND":
        e50=ema(df['close'],50).iloc[-1]
        sl=e50-atr*1.2 if side=="BUY" else e50+atr*1.2
        tp1=entry_price*(1+0.008) if side=="BUY" else entry_price*(1-0.008)
        tp2=entry_price*(1+0.02) if side=="BUY" else entry_price*(1-0.02)
    else:
        sl=entry_price-atr*1.6 if side=="BUY" else entry_price+atr*1.6
        tp1=entry_price*(1+0.008) if side=="BUY" else entry_price*(1-0.008)
        tp2=entry_price*(1+0.02) if side=="BUY" else entry_price*(1-0.02)
    sym=df.symbol if hasattr(df,'symbol') else DEFAULT_SYMBOL
    sl,tp1=PrecisionSafety.adjust_sl_tp(sym,entry_price,sl,tp1,side,atr)
    return sl,tp1,tp2

# ========== EQUAL LEVELS / OB / FVG ==========
def equal_levels_points(highs,lows,tolerance=0.002):
    eqh=[]; eql=[]
    def cl(pts,tol):
        if not pts: return []
        pts=sorted(pts); cls=[]; cu=[pts[0]]
        for p in pts[1:]:
            if abs(p-cu[-1])/cu[-1]<tol: cu.append(p)
            else: cls.append(cu); cu=[p]
        cls.append(cu)
        return cls
    for c in cl(highs,tolerance):
        if len(c)>=2: eqh.append(sum(c)/len(c))
    for c in cl(lows,tolerance):
        if len(c)>=2: eql.append(sum(c)/len(c))
    return eqh,eql
def find_swing_points(df,window=3):
    highs=df['high'].values; lows=df['low'].values
    sh=[]; sl=[]
    for i in range(window,len(df)-window):
        if highs[i]==max(highs[i-window:i+window+1]): sh.append(highs[i])
        if lows[i]==min(lows[i-window:i+window+1]): sl.append(lows[i])
    return sh,sl
def detect_equal_highs_lows(df,lookback=50):
    sub=df.iloc[-lookback:]
    sh,sl=find_swing_points(sub,window=2)
    return equal_levels_points(sh,sl)
def detect_order_block(df,side,lookback=4):
    if len(df)<lookback+2: return None
    atr=compute_atr(df).iloc[-1]
    mv=abs(df['close'].iloc[-1]-df['close'].iloc[-2])
    if mv<atr*1.2: return None
    for i in range(2,lookback+2):
        if i>=len(df): break
        c=df.iloc[-i]
        if side=="BUY" and c['close']<c['open']: return {"low":c['low'],"high":c['high'],"idx":-i}
        elif side=="SELL" and c['close']>c['open']: return {"low":c['low'],"high":c['high'],"idx":-i}
    return None
def detect_fvg(df,threshold=0.001):
    if len(df)<2: return None
    p=df.iloc[-2]; c=df.iloc[-1]
    if c['low']>p['high']*(1+threshold): return ("bullish",p['high'],c['low'])
    elif c['high']<p['low']*(1-threshold): return ("bearish",c['high'],p['low'])
    return None

# ========== SMART ZONES ==========
def compute_zone_strength(df,level,zone_type,atr,ob):
    price=df['close'].iloc[-1]
    ti=[]
    for i in range(max(0,len(df)-30),len(df)):
        ch=df['high'].iloc[i]; clw=df['low'].iloc[i]
        if (zone_type=="support" and abs(clw-level)<atr) or (zone_type=="resistance" and abs(ch-level)<atr): ti.append(i)
    vs=0
    if ti:
        vols=df['volume'].iloc[ti]; av=vols.mean()
        oa=df['volume'].iloc[-30:].mean() if len(df)>=30 else df['volume'].mean()
        vs=min(3.0,av/oa) if oa>0 else 0
    rc=0
    for idx in ti:
        if idx<len(df)-1:
            nc=df['close'].iloc[idx+1]
            if (zone_type=="support" and nc>df['close'].iloc[idx]) or (zone_type=="resistance" and nc<df['close'].iloc[idx]): rc+=1
    rs=min(3.0,rc); ls=0
    if ob:
        obi=orderbook_imbalance(ob)
        if zone_type=="support" and obi>0.1: ls=2
        elif zone_type=="resistance" and obi<-0.1: ls=2
        elif abs(obi)>0.05: ls=1
    ins=0
    bu,bd=detect_bos(df,lookback=5); ss=detect_structure_shift(df)
    if zone_type=="support" and (bu or ss=="bullish_shift"): ins=2
    elif zone_type=="resistance" and (bd or ss=="bearish_shift"): ins=2
    rjs=0
    if len(df)>=1:
        last=df.iloc[-1]; b,r,uw,lw=candle_metrics(last)
        if zone_type=="support" and lw>b*1.5 and abs(last['low']-level)<atr: rjs=2
        elif zone_type=="resistance" and uw>b*1.5 and abs(last['high']-level)<atr: rjs=2
    tot=vs+rs+ls+ins+rjs
    strength=min(10.0,tot*10/10)
    return round(strength,1),{"vol_strength":round(vs,1),"reaction_count":rc,"liquidity_score":ls,
                              "institutional_score":ins,"rejection_score":rjs}
def build_smart_zone_map(symbol,df,ob=None):
    atr=compute_atr(df).iloc[-1]
    sup,res=get_clustered_zones(df,lookback=120,cluster_pct=0.002)
    bz=[]
    for s in sup:
        st,dt=compute_zone_strength(df,s,"support",atr,ob)
        bz.append({"price":s,"strength":st,"details":dt,"type":"support"})
    sz=[]
    for r in res:
        st,dt=compute_zone_strength(df,r,"resistance",atr,ob)
        sz.append({"price":r,"strength":st,"details":dt,"type":"resistance"})
    bz.sort(key=lambda x:x["strength"],reverse=True)
    sz.sort(key=lambda x:x["strength"],reverse=True)
    return {"buy_zones":bz,"sell_zones":sz}
def get_smart_zones(symbol,df,ob):
    key=f"smart_zones_{symbol}"
    cached=MEMORY.get(key)
    if cached and time.time()-cached.get("ts",0)<90: return cached["data"]
    zones=build_smart_zone_map(symbol,df,ob)
    MEMORY[key]={"data":zones,"ts":time.time()}
    return zones

# ========== NARRATIVE ENGINE ==========
def get_di_components(df,period=14):
    if df is None or len(df)<period*2: return None,None,None,0.0
    h=df['high']; l=df['low']; c=df['close']
    tr1=h-l; tr2=(h-c.shift(1)).abs(); tr3=(l-c.shift(1)).abs()
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    atr=rma(tr,period).clip(lower=1e-9)
    um=h.diff(); dm=-l.diff()
    pdm=np.where((um>dm)&(um>0),um,0.0); mdm=np.where((dm>um)&(dm>0),dm,0.0)
    pdm=pd.Series(pdm,index=df.index); mdm=pd.Series(mdm,index=df.index)
    pdi=100*rma(pdm,period)/(atr+1e-9); mdi=100*rma(mdm,period)/(atr+1e-9)
    ads=compute_adx(df,period)
    ac=ads.iloc[-1] if len(ads)>0 else 20.0
    ap=ads.iloc[-2] if len(ads)>1 else ac
    return pdi.iloc[-1],mdi.iloc[-1],ac,ac-ap
def compute_vwap(df):
    tp=(df['high']+df['low']+df['close'])/3
    cv=df['volume'].cumsum(); ctv=(tp*df['volume']).cumsum()
    return ctv/cv
def get_vwap_narrative(df):
    vw=compute_vwap(df); price=df['close'].iloc[-1]
    vl=vw.iloc[-1]; vp=vw.iloc[-2] if len(vw)>1 else vl
    d=(price-vl)/vl if vl!=0 else 0.0
    a=price>vl; b=price<vl
    pa=df['close'].iloc[-2]>vp if len(df)>1 else a
    return {"vwap":vl,"distance":d,"above":a,"below":b,"reclaim":(not pa) and a,"reject":pa and (not a),"slope":vl-vp}
def classify_market_narrative(df,ob,atr,side,rf_signal):
    reasons=[]; sc=0.0
    pdi,mdi,adx,ads=get_di_components(df)
    if pdi is not None:
        if side=="BUY" and pdi>mdi: sc+=2.0; reasons.append("DI+ dominance")
        elif side=="SELL" and mdi>pdi: sc+=2.0; reasons.append("DI- dominance")
        elif abs(pdi-mdi)<5: reasons.append("DI tangled")
    if ads>1.5: sc+=1.5; reasons.append(f"ADX rising ({ads:.1f})")
    elif ads<-1.5: sc-=1.0; reasons.append("ADX falling")
    vn=get_vwap_narrative(df)
    if side=="BUY":
        if vn["above"]: sc+=1.5; reasons.append("VWAP above")
        elif vn["reclaim"]: sc+=2.0; reasons.append("VWAP reclaim")
    else:
        if vn["below"]: sc+=1.5; reasons.append("VWAP below")
        elif vn["reject"]: sc+=2.0; reasons.append("VWAP reject")
    pools=build_liquidity_pools(df)
    sh,sl=detect_sweep(df,pools)
    sweep_detected=(side=="BUY" and sl) or (side=="SELL" and sh)
    if sweep_detected: sc+=2.5; reasons.append("Liquidity sweep")
    sup,res=get_clustered_zones(df,lookback=80,cluster_pct=0.002)
    zone_strength=0.0
    if side=="BUY" and sup:
        ns=max([s for s in sup if s<=df['close'].iloc[-1]],default=None)
        if ns:
            zone_strength=compute_zone_strength(df,ns,"support",atr,ob)[0]
            sc+=zone_strength*0.5; reasons.append(f"Zone strength {zone_strength:.1f}")
    elif side=="SELL" and res:
        nr=min([r for r in res if r>=df['close'].iloc[-1]],default=None)
        if nr:
            zone_strength=compute_zone_strength(df,nr,"resistance",atr,ob)[0]
            sc+=zone_strength*0.5; reasons.append(f"Zone strength {zone_strength:.1f}")
    bu,bd=detect_bos(df); ss=detect_structure_shift(df)
    if (side=="BUY" and (bu or ss=="bullish_shift")): sc+=2.0; reasons.append("Bullish structure")
    elif (side=="SELL" and (bd or ss=="bearish_shift")): sc+=2.0; reasons.append("Bearish structure")
    vs=classify_volume(df)
    if vs in ("expansion","spike"): sc+=1.5; reasons.append("Volume expansion")
    elif vs=="exhaustion": sc-=1.0; reasons.append("Volume exhaustion")
    if candle_rejection(df,side): sc+=1.5; reasons.append("Rejection candle")
    if detect_displacement(df,side,atr,vs,bat=0.8,ver=False): sc+=1.5; reasons.append("Displacement")
    if rf_signal==side: sc+=1.5; reasons.append("RF aligned")
    if adx is not None and adx<18 and pdi is not None and abs(pdi-mdi)<6:
        sc=0; reasons=["CHOP market (ADX<18 + DI tangled)"]
    if sc>=9.0:
        cls="REVERSAL_SNIPER" if (sweep_detected or zone_strength>5) else "TREND_CONTINUATION"
        conf="HIGH"
    elif sc>=7.0:
        cls="TREND_CONTINUATION" if (bu or bd or ss) else ("ACCUMULATION_LONG" if side=="BUY" else "DISTRIBUTION_SHORT")
        conf="MEDIUM"
    elif sc>=5.0:
        cls="FAKE_BREAKOUT" if not sweep_detected else "LOW_CONFIDENCE"
        conf="LOW"
    else:
        cls="CHOP_NO_TRADE"; conf="NO_TRADE"
    return {"classification":cls,"confidence":conf,"narrative_score":round(sc,2),"reasons":reasons,
            "sweep":sweep_detected,"zone_strength":zone_strength,
            "di_dominance":("BUY" if pdi>mdi else "SELL") if pdi is not None else "NEUTRAL",
            "adx_slope":ads,"vwap_reclaim":vn["reclaim"],"vwap_reject":vn["reject"]}
def detect_market_regime(df):
    if len(df)<50: return "RANGE"
    try:
        adx=compute_adx(df).iloc[-1]
        pdi,mdi,_,_=get_di_components(df)
        atr=compute_atr(df).iloc[-1]
        atrs=compute_atr(df)
        aa=atrs.rolling(20).mean().iloc[-1] if len(atrs)>=20 else atr
        ar=atr/aa if aa else 1.0
        e20=ema(df['close'],20).iloc[-1]
        e50=ema(df['close'],50).iloc[-1] if len(df)>=50 else e20
        price=df['close'].iloc[-1]
        dd=abs(pdi-mdi)
        if adx<18 and dd<6: return "CHOP"
        if adx>20 and dd>5:
            st=detect_structure_shift(df)
            ba=pdi>mdi and e20>e50 and price>e20
            bea=mdi>pdi and e20<e50 and price<e20
            if ba or bea: return "TREND"
            if st=="bullish_shift" and pdi>mdi: return "TREND"
            if st=="bearish_shift" and mdi>pdi: return "TREND"
        if adx>20 and ar>1.4: return "EXPANSION"
        if ar<0.7 and adx<25: return "COMPRESSION"
        return "RANGE"
    except: return "RANGE"
def get_trend_direction(df):
    try:
        pdi,mdi,_,_=get_di_components(df)
        e20=ema(df['close'],20).iloc[-1]
        e50=ema(df['close'],50).iloc[-1] if len(df)>=50 else e20
        price=df['close'].iloc[-1]
        st=detect_structure_shift(df)
        if (pdi>mdi and e20>e50 and price>e20) or st=="bullish_shift": return "BULLISH"
        elif (mdi>pdi and e20<e50 and price<e20) or st=="bearish_shift": return "BEARISH"
        return "NEUTRAL"
    except: return "NEUTRAL"
def adjust_narrative_confidence(narr,reg,side,td):
    oc=narr["confidence"]; sc=narr["narrative_score"]
    sa=(td=="BULLISH" and side=="BUY") or (td=="BEARISH" and side=="SELL")
    fc=oc; fcl=narr["classification"]
    if reg=="CHOP": return "NO_TRADE","CHOP_NO_TRADE"
    if oc=="NO_TRADE" or sc<5.0: return "NO_TRADE","CHOP_NO_TRADE"
    if reg=="TREND":
        if sa:
            if oc=="HIGH": fc="HIGH"; fcl="SNIPER"
            elif oc=="MEDIUM": fc="MEDIUM"; fcl="TREND"
            elif oc=="LOW":
                if sc>=5.0: fc="MEDIUM"; fcl="TREND"
                else: fc="NO_TRADE"; fcl="NO_TRADE"
        else:
            if oc=="HIGH": fc="HIGH"; fcl="SNIPER"
            else: fc="NO_TRADE"; fcl="NO_TRADE"
    elif reg in ("EXPANSION","COMPRESSION"):
        if oc=="HIGH": fc="HIGH"; fcl="SNIPER"
        else: fc="NO_TRADE"; fcl="NO_TRADE"
    else:
        if oc=="HIGH": fc="HIGH"; fcl="SNIPER"
        elif oc=="MEDIUM" and sa: fc="NO_TRADE"; fcl="NO_TRADE"
        else: fc="NO_TRADE"; fcl="NO_TRADE"
    return fc,fcl
def evaluate_with_narrative(symbol,side,price,atr_val,df,ob,rf_signal,existing_score=0):
    reg=detect_market_regime(df); td=get_trend_direction(df)
    narr=classify_market_narrative(df,ob,atr_val,side,rf_signal)
    fc,fcl=adjust_narrative_confidence(narr,reg,side,td)
    narr["confidence"]=fc; narr["classification"]=fcl; narr["regime"]=reg
    MEMORY[f"last_narrative_{symbol}"]={**narr,"timestamp":time.time(),"side":side}
    se=fc in ("HIGH","MEDIUM")
    if not se:
        reason=f"{fcl} ({fc}) Regime={reg} Score={narr['narrative_score']:.1f}"
        MEMORY.setdefault("no_entry_feed",[]).append({"time":time.time(),"symbol":symbol,"side":side,
                                                       "reason":reason,"score":narr["narrative_score"]})
        if len(MEMORY["no_entry_feed"])>20: MEMORY["no_entry_feed"]=MEMORY["no_entry_feed"][-20:]
        return False,None,narr
    STATE["narrative_classification"]=fcl
    STATE["narrative_confidence"]=narr["narrative_score"]
    STATE["confidence_level"]=fc
    return True,fcl,narr

# ========== INSTITUTIONAL ENTRY ==========
def check_institutional_entry(symbol,side,df,ob,atr,price):
    isc,ist,idt=InstitutionalIntentEngine.detect(df,ob,symbol)
    if isc<75: return False,None,f"Intent score {isc}"
    MEMORY[f"intent_{symbol}"]=idt
    reasons=[]
    pools=build_liquidity_pools(df)
    sh,sl=detect_sweep(df,pools)
    sok=(side=="BUY" and sl) or (side=="SELL" and sh)
    if not sok: return False,None,"No liquidity sweep"
    reasons.append("Sweep")
    zones=get_smart_zones(symbol,df,ob)
    zok=False; zp=None
    if side=="BUY":
        if zones["buy_zones"] and zones["buy_zones"][0]["strength"]>=5:
            zp=zones["buy_zones"][0]["price"]
            if abs(price-zp)/price<0.003: zok=True
    else:
        if zones["sell_zones"] and zones["sell_zones"][0]["strength"]>=5:
            zp=zones["sell_zones"][0]["price"]
            if abs(price-zp)/price<0.003: zok=True
    if not zok:
        fvg=detect_fvg(df)
        if side=="BUY" and fvg and fvg[0]=="bullish" and fvg[1]<=price<=fvg[2]: zok=True
        elif side=="SELL" and fvg and fvg[0]=="bearish" and fvg[1]<=price<=fvg[2]: zok=True
    if not zok:
        obv=detect_order_block(df,side)
        if side=="BUY" and obv and abs(price-obv["low"])/price<0.003: zok=True
        elif side=="SELL" and obv and abs(price-obv["high"])/price<0.003: zok=True
    if not zok: return False,None,"No strong zone tap"
    ss=detect_structure_shift(df); bu,bd=detect_bos(df)
    cok=(side=="BUY" and (ss=="bullish_shift" or bu)) or (side=="SELL" and (ss=="bearish_shift" or bd))
    if sok and not cok: return False,None,"Reversal requires MSS/CHoCH"
    rjok=candle_rejection(df,side); vs=classify_volume(df)
    dok=detect_displacement(df,side,atr,vs,bat=0.8,ver=False)
    if not (rjok or dok): return False,None,"No rejection/displacement"
    if vs not in ("expansion","spike"): return False,None,"No volume expansion"
    ads=compute_adx(df)
    if len(ads)<3: return False,None,"Insufficient ADX data"
    an=ads.iloc[-1]; ap=ads.iloc[-2]; asl=an-ap
    pdi,mdi,_,_=get_di_components(df)
    dsp=(pdi-mdi) if side=="BUY" else (mdi-pdi)
    if an<18: return False,None,f"ADX too low ({an:.1f})"
    if an>50:
        if not (asl>0 and dsp>8): return False,None,f"Exhaustion: ADX>50"
    elif an>35:
        if not asl>0: return False,None,f"ADX high but falling"
    else:
        if not asl>0: return False,None,f"ADX not rising"
    rf=RFEngine(20,3.5).compute(df)
    if rf["signal"]!=side: return False,None,f"RF signal mismatch"
    if abs(rf["distance"])>0.003: return False,None,f"RF distance too far"
    if zp:
        mfz=abs(price-zp)/zp*100
        if mfz>0.5: return False,None,f"Moved too late"
    lc=df.iloc[-1]
    crp=(lc['high']-lc['low'])/lc['close']*100
    if crp>1.5*(atr/price*100): return False,None,"Large candle, too late"
    return True,"INSTITUTIONAL_SNIPER"," | ".join(reasons)

# ========== DECISION FUNCTIONS ==========
def decision_score_v1(df,ob,atr_val,side):
    es,reasons=early_score(df,ob,atr_val,side)
    ctx=detect_liquidity_context(df)
    sc="TREND"; dr=side
    if ctx=="sell_side_taken" and side=="BUY": sc="REVERSAL"
    elif ctx=="buy_side_taken" and side=="SELL": sc="REVERSAL"
    ts=min(10,max(0,es+2 if sc=="REVERSAL" else es))
    return ts,sc,dr,reasons
def apply_overrides_v1(df,atr_val,score):
    if is_late_move(df,atr_val): score=max(0,score-3)
    return score
def decide_and_execute_v1(symbol,side,total_score,reasons,price,sl,tp1,tp2):
    if total_score<5: return False
    df=get_ohlcv_safe(symbol,100)
    if df is None: return False
    ob=get_orderbook_cached(symbol,10)
    atr_val=compute_atr(df).iloc[-1] if len(df)>14 else price*0.01
    se,cls,narr=evaluate_with_narrative(symbol,side,price,atr_val,df,ob,side)
    if not se: return False
    rs=f"DECISION_V1 score={total_score} reasons={reasons} | NARR={narr['classification']}"
    return execute_entry(side,symbol,price,sl,tp1,tp2,total_score,rs,atr_val,
                         trade_type="DECISION_V1",entry_type="V1",classification=cls)
def decision_score(df,ob,atr_val,side):
    vs=classify_volume(df)
    sc=advanced_detect_scenario(df,side,atr_val,vs)
    es,reasons=early_score(df,ob,atr_val,side)
    tot=es
    if sc=="TRAP_REVERSAL": tot+=3
    elif sc=="TREND_CONTINUATION": tot+=2
    tot=min(10,max(0,tot))
    return tot,sc,side,reasons
def near_key_zone(df,price):
    sup,res=get_clustered_zones(df,lookback=80,cluster_pct=0.002)
    for s in sup:
        if abs(price-s)/price<0.003: return True
    for r in res:
        if abs(price-r)/price<0.003: return True
    return False

# ========== OPPOSING ZONE ==========
def find_nearest_opposing_zone(df,side):
    sup,res=get_clustered_zones(df,lookback=80,cluster_pct=0.002)
    price=df['close'].iloc[-1]
    if side=="BUY":
        v=[r for r in res if r>price]
        if v: return min(v,key=lambda x:x-price),"RESISTANCE"
    else:
        v=[s for s in sup if s<price]
        if v: return max(v,key=lambda x:x),"SUPPORT"
    return None,None
def compute_opposing_zone_strength(df,ob,atr,side,zp,zt):
    sc=0; price=df['close'].iloc[-1]
    dp=abs(price-zp)/price
    if dp<=0.002: sc+=2
    elif dp<=0.005: sc+=1
    last=df.iloc[-1]; b=abs(last['close']-last['open']); r=last['high']-last['low']
    if r>0:
        if side=="BUY":
            uw=last['high']-max(last['open'],last['close'])
            if uw>b*1.5 and price>=zp-0.002*price: sc+=2
        else:
            lw=min(last['open'],last['close'])-last['low']
            if lw>b*1.5 and price<=zp+0.002*price: sc+=2
    vs=classify_volume(df)
    if vs=="exhaustion": sc+=1
    elif vs=="neutral" and df['volume'].iloc[-1]<df['volume'].rolling(20).mean().iloc[-1]*0.8: sc+=1
    if side=="BUY":
        if last['high']>zp and last['close']<zp: sc+=2
    else:
        if last['low']<zp and last['close']>zp: sc+=2
    obi=orderbook_imbalance(ob)
    if side=="BUY" and obi<-0.15: sc+=2
    elif side=="SELL" and obi>0.15: sc+=2
    ads=compute_adx(df)
    if len(ads)>=2 and ads.iloc[-1]<ads.iloc[-2]: sc+=1
    return sc

# ========== SMART DECISION ==========
def detect_exhaustion_zone(df):
    atr=compute_atr(df).iloc[-1]; rsi=compute_rsi(df).iloc[-1]
    vn=get_vwap_narrative(df); last=df.iloc[-1]
    imp=(last['high']-last['low'])>=1.4*atr if atr>0 else False
    stretched=abs(vn["distance"])>=0.012
    rsi_ext=rsi>=70 or rsi<=30
    if not (imp and stretched and rsi_ext): return False,None,None
    if rsi>=70 and vn["distance"]>0.012: return True,last['high'],"TOP"
    elif rsi<=30 and vn["distance"]<-0.012: return True,last['low'],"BOTTOM"
    return False,None,None
def detect_reset(df,zp,zt):
    lc=df['close'].iloc[-1]
    if zt=="TOP": return (zp-lc)/zp>=0.003
    return (lc-zp)/zp>=0.003
def confirm_reversal(df,ob,zt):
    last=df.iloc[-1]
    w=(last['high']-max(last['open'],last['close'])) if zt=="TOP" else (min(last['open'],last['close'])-last['low'])
    b=abs(last['close']-last['open'])
    wr=w>b*1.5 if b>0 else False
    mh=compute_macd(df)[2]; mf=macd_first_flip(mh)
    fl=flow_engine(df)
    fa=(zt=="TOP" and fl=="aggressive_sell") or (zt=="BOTTOM" and fl=="aggressive_buy")
    obi=orderbook_imbalance(ob)
    oa=(zt=="TOP" and obi<-0.2) or (zt=="BOTTOM" and obi>0.2)
    return sum([wr,mf,fa,oa])>=2
def detect_stop_hunt(df):
    pools=build_liquidity_pools(df)
    sh,sl=detect_sweep(df,pools)
    last=df.iloc[-1]
    rc=(sh and last['close']<last['high']) or (sl and last['close']>last['low'])
    if sh and rc and volume_pressure_real(df): return True,"SELL"
    elif sl and rc and volume_pressure_real(df): return True,"BUY"
    return False,None
def choose_mode(df):
    adx=compute_adx(df).iloc[-1] if len(df)>=20 else 20
    return "TREND" if adx>=20 else "RANGE"
def smart_decision(df,ob,symbol):
    mode=choose_mode(df)
    ih,hs=detect_stop_hunt(df)
    if ih and hs: return "STOP_HUNT",hs,{"mode":mode}
    iz,zp,zt=detect_exhaustion_zone(df)
    if iz and zp is not None: STATE["zone"][symbol]=(zp,zt)
    if symbol in STATE["zone"]:
        zp,zt=STATE["zone"][symbol]
        if detect_reset(df,zp,zt) and confirm_reversal(df,ob,zt):
            side="SELL" if zt=="TOP" else "BUY"
            return "EXHAUSTION_ENTRY",side,{"mode":mode,"zone":zp}
    return None,None,None

# ========== WATCHLIST ==========
def record_watchlist_entry(symbol,side,narrative,score,smart_money=None,momentum=None):
    now=time.time(); state="DETECTED"
    if narrative.get("retest"): state="RETEST"
    if narrative.get("rejection"): state="REJECTION"
    if narrative.get("displacement"): state="DISPLACEMENT"
    if narrative.get("sweep") and narrative.get("choch_bos") and narrative.get("retest") and narrative.get("rejection"): state="CONFIRMED"
    rl=[]
    if narrative["sweep"]: rl.append("Sweep")
    if narrative["choch_bos"]: rl.append("CHoCH/BOS")
    if narrative["retest"]: rl.append("ZONE_RETEST")
    if narrative["rejection"]: rl.append("OB")
    if narrative["displacement"]: rl.append("Displacement")
    if narrative["volume_confirmation"]: rl.append("Volume")
    if narrative["rf_alignment"]: rl.append("RF")
    tt="REVERSAL" if (narrative["sweep"] or narrative["retest"]) else "TREND"
    st="WEAK"
    if score>=7: st="STRONG"
    elif score>=4: st="MEDIUM"
    entry={"symbol":symbol,"side":side,"score":round(score,2),"state":state,"reasons":rl,
           "trade_type":tt,"strength":st,"last_update":now}
    if smart_money:
        entry["smart_money_bias"]=smart_money.get("institutional_bias","NEUTRAL")
        entry["smart_money_bias_detailed"]=smart_money.get("institutional_bias_detailed","NEUTRAL")
        entry["distribution_risk"]=round(smart_money.get("distribution_risk",0),1)
        entry["accumulation"]=round(smart_money.get("accumulation_strength",0),1)
    if momentum:
        entry["momentum_expansion"]=momentum.get("trend_expansion",False)
        entry["momentum_decay"]=momentum.get("momentum_decay",False)
        entry["exhaustion_risk"]=round(momentum.get("exhaustion_risk",0),1)
        entry["continuation_strength"]=round(momentum.get("continuation_strength",0),1)
    if "watchlist" not in MEMORY: MEMORY["watchlist"]={}
    MEMORY["watchlist"][symbol]=entry
def cleanup_watchlist(ttl=300):
    now=time.time()
    if "watchlist" not in MEMORY: return
    expired=[s for s,v in MEMORY["watchlist"].items() if now-v["last_update"]>ttl]
    for s in expired: del MEMORY["watchlist"][s]

def evaluate_liquidity_narrative(df,ob,atr,side):
    narr={"sweep":False,"choch_bos":False,"retest":False,"rejection":False,
          "displacement":False,"rf_alignment":False,"volume_confirmation":False}
    price=df['close'].iloc[-1]
    pools=build_liquidity_pools(df)
    sh,sl=detect_sweep(df,pools)
    if side=="BUY" and sl: narr["sweep"]=True
    elif side=="SELL" and sh: narr["sweep"]=True
    bu,bd=detect_bos(df); ss=detect_structure_shift(df)
    if side=="BUY" and (bu or ss=="bullish_shift"): narr["choch_bos"]=True
    elif side=="SELL" and (bd or ss=="bearish_shift"): narr["choch_bos"]=True
    zones=get_smart_zones(df.symbol if hasattr(df,'symbol') else "unknown",df,ob)
    rz=None
    if zones:
        if side=="BUY" and zones["buy_zones"]: rz=zones["buy_zones"][0]
        elif side=="SELL" and zones["sell_zones"]: rz=zones["sell_zones"][0]
    if rz:
        d=abs(price-rz["price"])/price
        if d<0.003: narr["retest"]=True
    if candle_rejection(df,side): narr["rejection"]=True
    vs=classify_volume(df)
    if detect_displacement(df,side,atr,vs): narr["displacement"]=True
    if vs in ("expansion","spike"): narr["volume_confirmation"]=True
    rf=RFEngine(20,3.5).compute(df)
    if rf["signal"]==side and abs(rf["distance"])<0.003: narr["rf_alignment"]=True
    sc=0
    if narr["sweep"]: sc+=2
    if narr["choch_bos"]: sc+=2
    if narr["retest"]: sc+=2
    if narr["rejection"]: sc+=1.5
    if narr["displacement"]: sc+=1.5
    if narr["volume_confirmation"]: sc+=1
    if narr["rf_alignment"]: sc+=2
    return narr,sc

def smart_opportunity_selection():
    cands=[]
    for c in MEMORY.get("scanner_v2_buy",[])[:5]: cands.append({"symbol":c["symbol"],"side":"BUY","score":c["score"],"source":"v2"})
    for c in MEMORY.get("scanner_v2_sell",[])[:5]: cands.append({"symbol":c["symbol"],"side":"SELL","score":c["score"],"source":"v2"})
    for c in MEMORY.get("rf_watchlist",[])[:10]:
        if c.get("rf_signal") in ("BUY","SELL"): cands.append({"symbol":c["symbol"],"side":c["rf_signal"],"score":c["score"],"source":"rf"})
    seen={}
    for cd in cands:
        s=cd["symbol"]
        if s not in seen or cd["score"]>seen[s]["score"]: seen[s]=cd
    cands=list(seen.values()); bs=None; bscore=-1
    for cd in cands[:15]:
        try:
            s=cd["symbol"]; sd=cd["side"]
            df=get_ohlcv_safe(s,100)
            if df is None or not validate_dataframe(df,80): continue
            df.symbol=s
            ob=get_orderbook_cached(s,limit=10)
            atr=compute_atr(df).iloc[-1] if len(df)>14 else df['close'].iloc[-1]*0.01
            narr,ns=evaluate_liquidity_narrative(df,ob,atr,sd)
            sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
            tca=0
            if sm["smart_money_dominant"] and sm["institutional_bias"]==sd: tca+=15
            if mom["trend_expansion"] and mom["flow_bias"]==sd: tca+=10
            if sm["distribution_risk"]>70: tca-=15
            if mom["momentum_decay"]: tca-=12
            if mom["exhaustion_risk"]>70: tca-=10
            ans=ns+(tca/10)
            record_watchlist_entry(s,sd,narr,ans,sm,mom)
            if ans<7: continue
            zones=get_smart_zones(s,df,ob)
            zs=0
            if sd=="BUY" and zones["buy_zones"]: zs=zones["buy_zones"][0]["strength"]
            elif sd=="SELL" and zones["sell_zones"]: zs=zones["sell_zones"][0]["strength"]
            tot=ans+zs*0.5
            if tot>bscore: bscore=tot; bs=(s,sd,tot,narr,zones,df,ob,atr)
        except: continue
    if bs and bscore>=9:
        s,sd,sc,narr,zones,df,ob,atr=bs
        price=df['close'].iloc[-1]
        sl,tp1,tp2=compute_sl_tp(price,sd,"REVERSAL",atr,df)
        rs=f"INST_SWEEP+CHOCH+RETEST | nscore={sc:.1f}"
        return execute_entry(sd,s,price,sl,tp1,tp2,sc,rs,atr,
                             trade_type="INSTITUTIONAL",entry_type="NARRATIVE",classification="SNIPER")
    return False

# ========== MONITOR WATCHLIST ==========
def monitor_watchlist():
    wl=MEMORY.get("rf_watchlist",[])
    for c in wl:
        s=c["symbol"]
        df=get_ohlcv_safe(s,150)
        if df is None or not validate_dataframe(df,100): continue
        ob=get_orderbook_cached(s,limit=10)
        if ob is not None:
            price=df['close'].iloc[-1]
            atr_val=compute_atr(df).iloc[-1] if len(df)>14 else price*0.01
            for st in ("BUY","SELL"):
                se,cls,rs=check_institutional_entry(s,st,df,ob,atr_val,price)
                if se:
                    sen,fc,narr=evaluate_with_narrative(s,st,price,atr_val,df,ob,st)
                    if not sen: continue
                    sl,tp1,tp2=compute_sl_tp(price,st,"REVERSAL",atr_val,df)
                    if execute_entry(st,s,price,sl,tp1,tp2,85,rs,atr_val,
                                     trade_type="INSTITUTIONAL_V3",entry_type="SMART_EARLY",classification=cls): return True
            dec,ds,di=smart_decision(df,ob,s)
            if dec=="STOP_HUNT":
                price=df['close'].iloc[-1]
                atr_val=compute_atr(df).iloc[-1] if len(df)>14 else price*0.01
                sen,cls,narr=evaluate_with_narrative(s,ds,price,atr_val,df,ob,ds)
                if not sen: continue
                sl,tp1,tp2=compute_sl_tp(price,ds,"REVERSAL",atr_val,df)
                rs=f"SMART_STOP_HUNT mode={di.get('mode')}"
                if execute_entry(ds,s,price,sl,tp1,tp2,8,rs,atr_val,
                                 trade_type="SMART",entry_type="STOP_HUNT",classification=cls): return True
        rf=RFEngine(20,3.5).compute(df)
        if not rf["triggered"]: continue
        side=rf["signal"]
        if side is None: continue
        price=df['close'].iloc[-1]
        atr_val=compute_atr(df).iloc[-1] if len(df)>14 else price*0.01
        sen,cls,narr=evaluate_with_narrative(s,side,price,atr_val,df,ob,side)
        if not sen: continue
        if is_late_entry(df,side): continue
        ts,scn,sd,ar=decision_score(df,ob,atr_val,side)
        if ts>=7:
            sl,tp1,tp2=compute_sl_tp(price,sd,"REVERSAL" if scn=="REVERSAL" else "EARLY_TREND",atr_val,df)
            rs=f"UNIFIED_SNIPER ({scn}) score={ts}"
            if execute_entry(sd,s,price,sl,tp1,tp2,ts,rs,atr_val,
                             trade_type="SCENARIO_ENGINE",entry_type="UNIFIED_SNIPER",classification=cls): return True
    return False

# ========== RADAR ==========
def fast_market_filter(df):
    price=df['close'].iloc[-1]; vu=df['volume'].iloc[-1]*price
    atr=compute_atr(df).iloc[-1]
    if vu<1_000_000: return False
    if (atr/price)<0.003: return False
    return True
def accumulation_v2(df):
    e20=df['close'].ewm(span=20).mean(); e50=df['close'].ewm(span=50).mean()
    comp=abs(e20.iloc[-1]-e50.iloc[-1])<df['close'].iloc[-1]*0.002
    tr=(df['high'].rolling(10).max()-df['low'].rolling(10).min())<df['close'].iloc[-1]*0.01
    vd=df['volume'].iloc[-1]<df['volume'].rolling(20).mean().iloc[-1]
    return comp and tr and vd
def detect_sweep_simple(df): return detect_liquidity_context(df) is not None
def radar_score(df):
    sc=0
    if accumulation_v2(df): sc+=3
    if volume_pressure_real(df): sc+=2
    if detect_sweep_simple(df): sc+=2
    if near_key_zone(df,df['close'].iloc[-1]): sc+=2
    return sc
def store_intent_for_symbol(symbol):
    try:
        df=get_ohlcv_safe(symbol,100)
        if df is None or not validate_dataframe(df,30): return
        ob=get_orderbook_cached(symbol,limit=10)
        isc,ist,idt=InstitutionalIntentEngine.detect(df,ob,symbol)
        if isc>=0: MEMORY[f"intent_{symbol}"]={"score":isc,"status":ist,"details":idt}
    except: pass
def rebuild_radar_watchlist():
    symbols=get_usdt_perp_symbols(); cands=[]
    for s in symbols[:150]:
        try:
            df=get_ohlcv_safe(s,100)
            if df is None or not validate_dataframe(df,80) or not fast_market_filter(df): continue
            sc=radar_score(df)
            if sc>0: cands.append({"symbol":s,"score":sc}); store_intent_for_symbol(s)
        except: continue
    cands.sort(key=lambda x:x["score"],reverse=True)
    MEMORY["radar_watchlist"]=cands[:30]; MEMORY["radar_top5"]=cands[:5]
def refresh_radar_watchlist():
    wl=MEMORY.get("radar_watchlist",[]); up=[]
    for e in wl:
        s=e["symbol"]
        try:
            df=get_ohlcv_safe(s,100)
            if df is None or not validate_dataframe(df,80): continue
            sc=radar_score(df)
            if sc>0: up.append({"symbol":s,"score":sc}); store_intent_for_symbol(s)
        except: continue
    up.sort(key=lambda x:x["score"],reverse=True)
    MEMORY["radar_watchlist"]=up[:30]; MEMORY["radar_top5"]=up[:5]

# ========== FRESH LIQUIDITY ==========
class FreshLiquidityRadar:
    @staticmethod
    def compute_liquidity_score(df):
        if len(df)<30: return 0.0,{}
        sc=0.0; det={}
        vol=df['volume']
        va=vol.iloc[-5:].mean()/(vol.iloc[-10:-5].mean()+1e-9)
        vas=min(2.0,va-1.0) if va>1.0 else 0.0
        sc+=vas*2; det["vol_accel"]=round(va,2)
        vr=vol.iloc[-1]/vol.iloc[-20:].mean()
        ves=min(1.5,vr-0.8) if vr>0.8 else 0.0
        sc+=ves*1.5; det["vol_ratio"]=round(vr,2)
        atr=compute_atr(df)
        ar=atr.iloc[-1]/atr.iloc[-20:].mean()
        aes=min(1.5,ar-0.9) if ar>0.9 else 0.0
        sc+=aes*1.5; det["atr_ratio"]=round(ar,2)
        last=df.iloc[-1]; b=abs(last['close']-last['open']); r=last['high']-last['low']
        if r>0:
            br=b/r; di=1.0 if br>0.6 else 0.0
            sc+=di*1.0; det["displacement"]=di
        swc=0
        for i in range(-5,0):
            sub=df.iloc[:i] if i<0 else df
            if len(sub)>=2:
                pools=build_liquidity_pools(sub)
                sh,sl=detect_sweep(sub,pools)
                if sh or sl: swc+=1
        ss=min(2.0,swc/3.0); sc+=ss*2; det["sweep_count"]=swc
        adx=compute_adx(df)
        if len(adx)>=5:
            asl=adx.iloc[-1]-adx.iloc[-4]
            if asl>0:
                sc+=min(1.5,asl/5)*1.0; det["adx_slope"]=round(asl,2)
        return min(10.0,sc),det
    @staticmethod
    def scan(symbols,limit=15):
        cands=[]
        for s in symbols:
            try:
                df=get_ohlcv_safe(s,60)
                if df is None or not validate_dataframe(df,30): continue
                price=df['close'].iloc[-1]; atr=compute_atr(df).iloc[-1]
                atrp=(atr/price)*100 if price>0 else 0
                if atrp<0.2: continue
                sc,det=FreshLiquidityRadar.compute_liquidity_score(df)
                if sc>=3.0: cands.append({"symbol":s,"score":round(sc,2),"details":det})
            except: continue
        cands.sort(key=lambda x:x["score"],reverse=True)
        return cands[:limit]

# ========== SECTOR ==========
SECTOR_MAP={"AI":["FET","AGIX","OCEAN","RNDR","TAO","WLD","PHB","CTXC","NMR","ORAI"],
    "MEME":["DOGE","SHIB","PEPE","FLOKI","BONK","WIF","MEME","BABYDOGE","ELON","SAMO"],
    "LAYER1":["BTC","ETH","SOL","BNB","ADA","AVAX","TON","DOT","ATOM","NEAR","ICP","APT","SUI","KAS","ALGO","XLM","VET","HBAR","FTM","EGLD"],
    "LAYER2":["MATIC","ARB","OP","METIS","BOBA","LRC","SKL","IMX","ZK","POL"],
    "DEFI":["UNI","AAVE","MKR","COMP","CRV","LDO","SNX","BAL","1INCH","SUSHI","CAKE","RUNE","ENJ","YFI"],
    "GAMING":["SAND","MANA","GALA","AXS","ILV","YGG","MAGIC","PRIME","GHST","ALICE","WAXP","CROWN"],
    "INFRASTRUCTURE":["LINK","GRT","FIL","AR","STORJ","ANKR","GNO","LPT","HNT","THETA"],
    "RWA":["ONDO","CFG","RIO","LNDX","PRO","BTRST","DUSK","TRU"],
    "PAYMENT":["XRP","XLM","ALGO","NANO","XDC","AMP","ACH"],
    "PRIVACY":["ZEC","XMR","DASH","KEEP","NU","SCRT","NYM"],
    "STORAGE":["FIL","AR","STORJ","BLZ","SIA","BTT"]}
def get_sector(symbol):
    base=symbol.replace("/USDT","").upper()
    for sec,kws in SECTOR_MAP.items():
        if any(kw in base for kw in kws): return sec
    return "OTHER"
def get_volume_growth(sym):
    df=get_ohlcv_safe(sym,30)
    if df is None or len(df)<20: return 0.0
    vol=df['volume']; ra=vol.iloc[-5:].mean(); oa=vol.iloc[-20:-5].mean()
    if oa==0: return 0.0
    return (ra/oa)-1.0
def get_price_momentum(sym):
    df=get_ohlcv_safe(sym,30)
    if df is None or len(df)<20: return 0.0
    return (df['close'].iloc[-1]-df['close'].iloc[-5])/df['close'].iloc[-5]*100
def select_sector_leaders():
    leaders=[]
    for sec in set(SECTOR_MAP.keys()):
        sis=[s for s in get_usdt_perp_symbols() if get_sector(s)==sec][:20]
        if not sis: continue
        best=None; bscore=-1e9
        for s in sis:
            vg=get_volume_growth(s); mm=get_price_momentum(s)
            sc=vg*10+mm
            if sc>bscore: bscore=sc; best=s
        if best: leaders.append({"symbol":best,"score":round(bscore,2),"sector":sec})
    leaders.sort(key=lambda x:x["score"],reverse=True)
    return leaders[:5]

# ========== WATCHLIST ROTATION ==========
class WatchlistRotation:
    def __init__(self,sym40):
        self.symbols=sym40; self.batch_size=6; self.current_index=0
        self.last_rotate=time.time(); self.rotation_interval=30
    def get_next_batch(self):
        b=[]
        for i in range(self.batch_size):
            idx=(self.current_index+i)%len(self.symbols)
            b.append(self.symbols[idx])
        self.current_index=(self.current_index+self.batch_size)%len(self.symbols)
        self.last_rotate=time.time()
        return b
    def should_rotate(self): return time.time()-self.last_rotate>=self.rotation_interval
def build_40_symbol_universe():
    ss=set()
    for c in MEMORY.get("scanner_v2_buy",[])+MEMORY.get("scanner_v2_sell",[]): ss.add(c["symbol"])
    for c in MEMORY.get("radar_top5",[]): ss.add(c["symbol"])
    for c in MEMORY.get("rf_watchlist",[]): ss.add(c["symbol"])
    sl=list(ss)[:20]
    all_sym=get_usdt_perp_symbols()
    fr=FreshLiquidityRadar.scan(all_sym,limit=20)
    fl=[c["symbol"] for c in fr if c["symbol"] not in ss][:15]
    scl=select_sector_leaders()
    ll=[l["symbol"] for l in scl if l["symbol"] not in ss and l["symbol"] not in fl][:5]
    univ=sl+fl+ll
    seen=set(); uu=[]
    for s in univ:
        if s not in seen: seen.add(s); uu.append(s)
    if len(uu)<40:
        extra=[s for s in all_sym if s not in seen][:40-len(uu)]
        uu.extend(extra)
    return uu[:40]

# ========== EXECUTION QUEUE ==========
class OrderBlockQuality(Enum): FRESH="FRESH"; TESTED="TESTED"; WEAK="WEAK"; BROKEN="BROKEN"; FAKE="FAKE"
class InstitutionalBehaviour(Enum):
    ACCUMULATION="ACCUMULATION"; DISTRIBUTION="DISTRIBUTION"
    RE_ACCUMULATION="RE_ACCUMULATION"; RE_DISTRIBUTION="RE_DISTRIBUTION"; NEUTRAL="NEUTRAL"
class MarketStructure(Enum): BOS="BOS"; CHOCH="CHOCH"; MSS="MSS"; NONE="NONE"
class OpportunityType(Enum):
    INSTITUTIONAL_REVERSAL="INSTITUTIONAL_REVERSAL"; TREND_CONTINUATION="TREND_CONTINUATION"
    BREAKOUT_RETEST="BREAKOUT_RETEST"; DISTRIBUTION_ENTRY="DISTRIBUTION_ENTRY"
    ACCUMULATION_ENTRY="ACCUMULATION_ENTRY"; LOW_QUALITY="LOW_QUALITY"
    FAKE_BREAKOUT="FAKE_BREAKOUT"; WEAK_ORDER_BLOCK="WEAK_ORDER_BLOCK"
class ExecutionState(Enum):
    DISCOVERED="DISCOVERED"; WATCHLIST="WATCHLIST"; GOOD_ZONE="GOOD_ZONE"
    WAITING_TRIGGER="WAITING_TRIGGER"; TRIGGER_DETECTED="TRIGGER_DETECTED"
    ENTRY_VALIDATION="ENTRY_VALIDATION"; READY="READY"; EXECUTED="EXECUTED"
    INVALIDATED="INVALIDATED"; RETURNED_WATCHLIST="RETURNED_WATCHLIST"

@dataclass
class ZoneMetrics:
    order_block_quality: float=50.0; zone_strength: float=50.0
    liquidity_quality: float=50.0; institutional_confidence: float=50.0
    structure_alignment: float=50.0; entry_timing: float=50.0
    trend_alignment: float=50.0; risk_score: float=50.0
    trigger_state: str="WAITING_TRIGGER"
    @property
    def final_zone_score(self):
        w={'order_block_quality':0.20,'zone_strength':0.18,'liquidity_quality':0.15,
           'institutional_confidence':0.15,'structure_alignment':0.12,'entry_timing':0.10,
           'trend_alignment':0.05,'risk_score':0.05}
        sc=0.0
        for a,ww in w.items(): sc+=getattr(self,a,50)*ww
        return round(sc,2)

@dataclass
class ExecutionCandidate:
    symbol: str; side: str; price: float; entry_price: float
    stop_loss: float; take_profit_1: float; take_profit_2: float
    atr: float; df: pd.DataFrame; ob: Any
    zone_metrics: ZoneMetrics=field(default_factory=ZoneMetrics)
    opportunity_type: OpportunityType=OpportunityType.LOW_QUALITY
    market_structure: MarketStructure=MarketStructure.NONE
    institutional_behaviour: InstitutionalBehaviour=InstitutionalBehaviour.NEUTRAL
    state: ExecutionState=ExecutionState.DISCOVERED
    priority_score: float=0.0
    added_at: float=field(default_factory=time.time)
    last_evaluated: float=field(default_factory=time.time)
    evaluation_count: int=0
    original_score: float=0.0
    original_reason: str=""
    signal_type: str=""
    def to_dict(self):
        return {'symbol':self.symbol,'side':self.side,'entry_price':self.entry_price,
                'opportunity_type':self.opportunity_type.value,'market_structure':self.market_structure.value,
                'institutional_behaviour':self.institutional_behaviour.value,
                'zone_score':self.zone_metrics.final_zone_score,'priority_score':self.priority_score,
                'state':self.state.value,'trigger_state':self.zone_metrics.trigger_state,
                'ob_score':self.zone_metrics.order_block_quality,'zone_strength':self.zone_metrics.zone_strength,
                'liquidity':self.zone_metrics.liquidity_quality,'institutional':self.zone_metrics.institutional_confidence,
                'structure':self.zone_metrics.structure_alignment,'timing':self.zone_metrics.entry_timing,
                'trend':self.zone_metrics.trend_alignment,'risk':self.zone_metrics.risk_score,
                'evaluation_count':self.evaluation_count,'last_update':self.last_evaluated}

class ExecutionQueue:
    def __init__(self,max_size=15,re_eval_interval=5.0):
        self._candidates={}; self._max_size=max_size
        self._re_eval_interval=re_eval_interval; self._lock=threading.RLock()
        self.total_evaluations=0; self.total_rejected=0; self.total_executed=0
    def add_candidate(self,cand):
        with self._lock:
            if len(self._candidates)>=self._max_size:
                lo=min([(s,c) for s,c in self._candidates.items() if c.state!=ExecutionState.READY],
                       key=lambda x:x[1].priority_score,default=None)
                if lo:
                    self._candidates.pop(lo[0]); self.total_rejected+=1
                else: return False
            if cand.symbol in self._candidates:
                ex=self._candidates[cand.symbol]
                if cand.zone_metrics.final_zone_score>ex.zone_metrics.final_zone_score:
                    self._candidates[cand.symbol]=cand; return True
                return False
            self._candidates[cand.symbol]=cand
            return True
    def re_evaluate_all(self,data_fetcher):
        if not self._candidates: return
        with self._lock:
            for sym,cand in list(self._candidates.items()):
                df=data_fetcher(sym)
                if df is None or len(df)<30: self._invalidate(sym,"Insufficient data"); continue
                cp=df['close'].iloc[-1]
                atr=compute_atr(df).iloc[-1] if len(df)>14 else cp*0.01
                cand.atr=atr
                if self._is_extended(cand,cp): self._return_to_watchlist(sym,"Extended"); continue
                if self._is_ob_broken(cand,cp): self._invalidate(sym,"OB broken"); continue
                obs,_=self._eval_ob(df,cand.side,atr)
                zs=self._eval_zone(df,cand.side,atr,cand.entry_price)
                lq=self._eval_liq(df,cand.side,atr)
                ins=self._eval_inst(df,cand.side)
                sts,stt=self._eval_struct(df,cand.side)
                tm=self._eval_timing(df,cand.side,atr,cp,cand.entry_price)
                tr=self._eval_trend(df,cand.side)
                rk=self._eval_risk(cand,cp)
                tg=self._detect_trigger(df,cand.side,atr,cand.entry_price)
                m=ZoneMetrics(order_block_quality=obs,zone_strength=zs,liquidity_quality=lq,
                              institutional_confidence=ins,structure_alignment=sts,entry_timing=tm,
                              trend_alignment=tr,risk_score=rk,trigger_state=tg)
                ot=self._classify_opp(m,stt,cand.side,df)
                bh=self._detect_inst_behav(df,cand.side)
                cand.zone_metrics=m; cand.opportunity_type=ot; cand.market_structure=stt
                cand.institutional_behaviour=bh; cand.last_evaluated=time.time()
                cand.evaluation_count+=1; cand.priority_score=m.final_zone_score
                self._update_state(cand,cp)
                self.total_evaluations+=1
                if cand.priority_score<30: self._return_to_watchlist(sym,"Score too low")
    def _is_extended(self,cand,price): return abs(price-cand.entry_price)>cand.atr*1.5
    def _is_ob_broken(self,cand,price):
        if cand.side=="BUY": return price<cand.entry_price-cand.atr*0.8
        return price>cand.entry_price+cand.atr*0.8
    def _eval_ob(self,df,side,atr):
        if len(df)<1: return 30,OrderBlockQuality.WEAK
        last=df.iloc[-1]; b=abs(last['close']-last['open']); r=last['high']-last['low']
        if r==0: return 30,OrderBlockQuality.WEAK
        if side=="BUY":
            lw=min(last['open'],last['close'])-last['low']; ratio=lw/r
            if ratio>0.6 and last['close']>last['open']: return 90,OrderBlockQuality.FRESH
            elif ratio>0.4: return 70,OrderBlockQuality.TESTED
            return 50,OrderBlockQuality.WEAK
        else:
            uw=last['high']-max(last['open'],last['close']); ratio=uw/r
            if ratio>0.6 and last['close']<last['open']: return 90,OrderBlockQuality.FRESH
            elif ratio>0.4: return 70,OrderBlockQuality.TESTED
            return 50,OrderBlockQuality.WEAK
    def _eval_zone(self,df,side,atr,ep):
        t=0; rj=0; vsum=0
        for i in range(max(0,len(df)-30),len(df)-1):
            c=df.iloc[i]
            if side=="BUY":
                if abs(c['low']-ep)<atr*0.5:
                    t+=1
                    if df['close'].iloc[i+1]>c['close']: rj+=1; vsum+=c['volume']
            else:
                if abs(c['high']-ep)<atr*0.5:
                    t+=1
                    if df['close'].iloc[i+1]<c['close']: rj+=1; vsum+=c['volume']
        sc=50
        if t>=4: sc+=25
        elif t>=2: sc+=12
        elif t>=1: sc+=5
        if rj>=3: sc+=20
        elif rj>=2: sc+=10
        av=df['volume'].iloc[-30:].mean()
        if t>0 and av>0:
            atv=vsum/t
            if atv>2*av: sc+=15
            elif atv>1.5*av: sc+=8
        return min(100,max(0,sc))
    def _eval_liq(self,df,side,atr):
        pools=build_liquidity_pools(df)
        sh,sl=detect_sweep(df,pools)
        sh_,hs=detect_stop_hunt(df)
        eh,el=detect_equal_highs_lows(df)
        sc=50
        if side=="BUY":
            if sl: sc+=25
            if el: sc+=10
            if sh_ and hs=="BUY": sc+=20
        else:
            if sh: sc+=25
            if eh: sc+=10
            if sh_ and hs=="SELL": sc+=20
        return min(100,max(0,sc))
    def _eval_inst(self,df,side):
        try:
            sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
        except: return 50
        sc=50
        if sm.get('smart_money_dominant',False):
            sc+=15
            if (side=="BUY" and sm['institutional_bias']=="BUY") or (side=="SELL" and sm['institutional_bias']=="SELL"): sc+=15
        dr=sm.get('distribution_risk',0)
        if side=="BUY" and dr<30: sc+=10
        elif side=="SELL" and dr>60: sc+=10
        ac=sm.get('accumulation_strength',0)
        if side=="BUY" and ac>60: sc+=10
        elif side=="SELL" and ac<40: sc+=10
        if mom.get('trend_expansion',False): sc+=5
        if mom.get('momentum_decay',False): sc-=10
        return min(100,max(0,sc))
    def _eval_struct(self,df,side):
        bu,bd=detect_bos(df); ss=detect_structure_shift(df)
        sc=50; st=MarketStructure.NONE
        if side=="BUY":
            if ss=="bullish_shift": sc=90; st=MarketStructure.MSS
            elif bu: sc=70; st=MarketStructure.BOS
        else:
            if ss=="bearish_shift": sc=90; st=MarketStructure.MSS
            elif bd: sc=70; st=MarketStructure.BOS
        return sc,st
    def _eval_timing(self,df,side,atr,cp,ep):
        d=abs(cp-ep)/ep; sc=50
        if d<0.005: sc+=30
        elif d<0.015: sc+=15
        elif d>0.03: sc-=30
        last=df.iloc[-1]; b=abs(last['close']-last['open']); r=last['high']-last['low']
        if r>0:
            if side=="BUY":
                lw=min(last['open'],last['close'])-last['low']
                if lw/r>0.5 and last['close']>last['open']: sc+=20
            else:
                uw=last['high']-max(last['open'],last['close'])
                if uw/r>0.5 and last['close']<last['open']: sc+=20
        va=df['volume'].iloc[-10:].mean()
        if va>0 and df['volume'].iloc[-1]>1.5*va: sc+=10
        return min(100,max(0,sc))
    def _eval_trend(self,df,side):
        if len(df)<20: return 50
        e20=df['close'].ewm(span=20).mean().iloc[-1]; e50=df['close'].ewm(span=50).mean().iloc[-1]
        p=df['close'].iloc[-1]; sc=50
        if side=="BUY":
            if p>e20>e50: sc+=25
            elif p>e20: sc+=10
            else: sc-=20
        else:
            if p<e20<e50: sc+=25
            elif p<e20: sc+=10
            else: sc-=20
        return min(100,max(0,sc))
    def _eval_risk(self,cand,price):
        sp=get_spread_bps(cand.symbol); sc=50
        if sp<0.05: sc+=20
        elif sp<0.1: sc+=10
        elif sp>0.2: sc-=30
        atrp=(cand.atr/cand.entry_price)*100 if cand.entry_price>0 else 0
        if 0.5<atrp<2.5: sc+=10
        elif atrp>4: sc-=20
        return min(100,max(0,sc))
    def _classify_opp(self,m,st,side,df):
        sc=m.final_zone_score
        if sc>=85 and st!=MarketStructure.NONE: return OpportunityType.INSTITUTIONAL_REVERSAL
        elif sc>=70 and st==MarketStructure.BOS: return OpportunityType.BREAKOUT_RETEST
        elif sc>=60 and st!=MarketStructure.NONE: return OpportunityType.TREND_CONTINUATION
        elif side=="BUY" and m.institutional_confidence>70: return OpportunityType.ACCUMULATION_ENTRY
        elif side=="SELL" and m.institutional_confidence>70: return OpportunityType.DISTRIBUTION_ENTRY
        elif m.order_block_quality<40: return OpportunityType.FAKE_BREAKOUT
        elif m.order_block_quality<50: return OpportunityType.WEAK_ORDER_BLOCK
        return OpportunityType.LOW_QUALITY
    def _detect_inst_behav(self,df,side):
        try:
            sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
        except: return InstitutionalBehaviour.NEUTRAL
        b=sm.get('banker_pressure',50); r=sm.get('retailer_pressure',50)
        dr=sm.get('distribution_risk',0); ac=sm.get('accumulation_strength',0)
        if side=="BUY" and b>r and dr<30 and ac>60: return InstitutionalBehaviour.ACCUMULATION
        if side=="SELL" and b<r and dr>50: return InstitutionalBehaviour.DISTRIBUTION
        if side=="BUY" and dr>50 and ac>50: return InstitutionalBehaviour.RE_ACCUMULATION
        if side=="SELL" and dr<30 and ac>50: return InstitutionalBehaviour.RE_DISTRIBUTION
        return InstitutionalBehaviour.NEUTRAL
    def _detect_trigger(self,df,side,atr,ep):
        pools=build_liquidity_pools(df)
        sh,sl=detect_sweep(df,pools)
        sok=(side=="BUY" and sl) or (side=="SELL" and sh)
        bu,bd=detect_bos(df); ss=detect_structure_shift(df)
        bok=(side=="BUY" and bu) or (side=="SELL" and bd)
        cok=(side=="BUY" and ss=="bullish_shift") or (side=="SELL" and ss=="bearish_shift")
        rjok=candle_rejection(df,side)
        vs=classify_volume(df)
        dok=detect_displacement(df,side,atr,vs,bat=0.8,ver=False)
        d=abs(df['close'].iloc[-1]-ep)/ep
        ne=d<0.003
        if sok and (bok or cok) and rjok: return "MSS_CONFIRMED"
        elif sok and ne and rjok: return "LIQUIDITY_SWEEP"
        elif bok and dok: return "BOS_CONFIRMED"
        elif cok and dok: return "CHOCH_CONFIRMED"
        elif sok and not (bok or cok): return "MITIGATION"
        elif ne and (bok or cok): return "WAITING_TRIGGER"
        elif ne: return "MITIGATION"
        elif dok: return "DISPLACEMENT"
        return "WAITING_TRIGGER"
    def _update_state(self,cand,price):
        sc=cand.zone_metrics.final_zone_score; tg=cand.zone_metrics.trigger_state
        if sc>=85 and tg in ("MSS_CONFIRMED","LIQUIDITY_SWEEP","BOS_CONFIRMED","CHOCH_CONFIRMED"): cand.state=ExecutionState.READY
        elif sc>=70 and tg=="MITIGATION": cand.state=ExecutionState.ENTRY_VALIDATION
        elif sc>=70: cand.state=ExecutionState.WAITING_TRIGGER
        elif sc>=55: cand.state=ExecutionState.GOOD_ZONE
        else: cand.state=ExecutionState.WATCHLIST
    def get_best_candidate(self):
        with self._lock:
            ready=[c for c in self._candidates.values() if c.state==ExecutionState.READY]
            if not ready: return None
            return max(ready,key=lambda c:c.priority_score)
    def _invalidate(self,sym,reason):
        if sym in self._candidates:
            self._candidates[sym].state=ExecutionState.INVALIDATED
            self._candidates.pop(sym,None); self.total_rejected+=1
    def _return_to_watchlist(self,sym,reason):
        if sym in self._candidates: self._candidates[sym].state=ExecutionState.RETURNED_WATCHLIST
    def cleanup(self):
        with self._lock:
            now=time.time(); tr=[]
            for s,c in self._candidates.items():
                if c.state in (ExecutionState.EXECUTED,ExecutionState.INVALIDATED,ExecutionState.RETURNED_WATCHLIST): tr.append(s)
                elif now-c.added_at>3600: tr.append(s)
            for s in tr: self._candidates.pop(s,None)
    def get_status(self):
        with self._lock:
            return {'total_candidates':len(self._candidates),
                    'ready':sum(1 for c in self._candidates.values() if c.state==ExecutionState.READY),
                    'total_evaluations':self.total_evaluations,'total_rejected':self.total_rejected,
                    'total_executed':self.total_executed,
                    'candidates':[c.to_dict() for c in self._candidates.values()],
                    'best_score':max([c.priority_score for c in self._candidates.values()]) if self._candidates else 0}

queue=ExecutionQueue(max_size=QUEUE_MAX_SIZE,re_eval_interval=QUEUE_RE_EVAL_INTERVAL)
_last_queue_promote=0; _last_queue_eval=0

# ========== GLOBAL DISCOVERY ==========
def global_discovery_scan():
    log_execution("[DISCOVERY] Starting global scan...","INFO")
    st=time.time(); all_sym=get_usdt_perp_symbols()[:200]; cands=[]
    buy,sell=smart_scanner_v2()
    for b in buy[:5]: cands.append({"symbol":b["symbol"],"score":b["score"],"side":"BUY","source":"scanner_v2"}); store_intent_for_symbol(b["symbol"])
    for s in sell[:5]: cands.append({"symbol":s["symbol"],"score":s["score"],"side":"SELL","source":"scanner_v2"}); store_intent_for_symbol(s["symbol"])
    rf_c=scan_market_rf(top_n=20)
    for r in rf_c[:10]:
        side=r.get("rf_signal")
        if side in ("BUY","SELL"): cands.append({"symbol":r["symbol"],"score":r["score"]*10,"side":side,"source":"rf"}); store_intent_for_symbol(r["symbol"])
    fr=FreshLiquidityRadar.scan(all_sym,limit=15)
    for f in fr:
        cands.append({"symbol":f["symbol"],"score":f["score"]*2,"side":"BUY","source":"fresh"})
        cands.append({"symbol":f["symbol"],"score":f["score"]*2,"side":"SELL","source":"fresh"})
        store_intent_for_symbol(f["symbol"])
    random.shuffle(all_sym)
    for s in all_sym[:10]:
        if not any(c["symbol"]==s for c in cands):
            cands.append({"symbol":s,"score":0,"side":"BUY","source":"random"})
            cands.append({"symbol":s,"score":0,"side":"SELL","source":"random"})
            store_intent_for_symbol(s)
    cands.sort(key=lambda x:x["score"],reverse=True)
    top=cands[:40]
    for item in top:
        s=item["symbol"]; sd=item["side"]
        narr={"sweep":False,"choch_bos":False,"retest":False,"rejection":False,"displacement":False,
              "volume_confirmation":False,"rf_alignment":False}
        if item["source"]=="scanner_v2": narr["sweep"]=True
        elif item["source"]=="rf": narr["rf_alignment"]=True
        elif item["source"]=="fresh": narr["volume_confirmation"]=True
        record_watchlist_entry(s,sd,narr,item["score"]); store_intent_for_symbol(s)
    MEMORY["radar_top5"]=[{"symbol":c["symbol"],"score":c["score"]} for c in top[:5]]
    log_execution(f"[DISCOVERY] Done in {time.time()-st:.1f}s","INFO")

def promote_to_queue():
    if not USE_EXECUTION_QUEUE: return
    if STATE.get("open") or TRADE_STATE.get("in_position"): return
    wl=[]
    for src in (MEMORY.get("watchlist",{}).values(),MEMORY.get("rf_watchlist",[]),
                MEMORY.get("scanner_v2_buy",[]),MEMORY.get("scanner_v2_sell",[])):
        if isinstance(src,dict):
            for it in src.values():
                if isinstance(it,dict) and "symbol" in it: wl.append(it)
        elif isinstance(src,list):
            for it in src:
                if isinstance(it,dict) and "symbol" in it: wl.append(it)
    best_per={}
    for it in wl:
        s=it.get('symbol')
        if not s: continue
        sc=it.get('score',0); sd=it.get('side','BUY')
        if s not in best_per or sc>best_per[s]['score']: best_per[s]={'score':sc,'side':sd,'source':it.get('source','unknown')}
    sorted_items=sorted(best_per.items(),key=lambda x:x[1]['score'],reverse=True)
    for s,dt in sorted_items[:30]:
        if s in queue._candidates: continue
        df=get_ohlcv_safe(s,100)
        if df is None or len(df)<30: continue
        price=df['close'].iloc[-1]
        atr=compute_atr(df).iloc[-1] if len(df)>14 else price*0.01
        ob=get_orderbook_cached(s,limit=10)
        sd=dt.get('side','BUY')
        sl,tp1,tp2=compute_sl_tp(price,sd,"REVERSAL",atr,df)
        isc,_,_=InstitutionalIntentEngine.detect(df,ob,s)
        m=ZoneMetrics()
        cand=ExecutionCandidate(symbol=s,side=sd,price=price,entry_price=price,stop_loss=sl,
                                take_profit_1=tp1,take_profit_2=tp2,atr=atr,df=df,ob=ob,
                                zone_metrics=m,original_score=dt.get('score',0),
                                original_reason='Watchlist promotion',signal_type=dt.get('source','watchlist'))
        cand.priority_score=isc
        queue.add_candidate(cand)

def process_queue_entry():
    if not USE_EXECUTION_QUEUE: return
    if STATE.get("open") or TRADE_STATE.get("in_position"): return
    best=queue.get_best_candidate()
    if best is None: return
    if best.priority_score<80: return
    log_execution(f"[QUEUE] Attempting entry: {best.symbol} {best.side} (Score: {best.priority_score:.1f})","INFO")
    success=execute_entry(best.side,best.symbol,best.price,best.stop_loss,best.take_profit_1,
                          best.take_profit_2,best.original_score,
                          f"QUEUE: {best.opportunity_type.value} (Zone: {best.zone_metrics.final_zone_score})",
                          best.atr,best.opportunity_type.value,"EXECUTION_QUEUE",best.opportunity_type.value)
    if success:
        with queue._lock:
            if best.symbol in queue._candidates: queue._candidates[best.symbol].state=ExecutionState.EXECUTED
        queue.total_executed+=1

# ========== MEMORY ==========
MEMORY={"candidates":[],"top_candidates":[],"regime":"NEUTRAL","last_scan":0,"scanned_count":0,
    "health":{"api":"OK","errors":0,"status":"RUNNING"},"rf_watchlist":[],"rf_dashboard":[],
    "scanner_v2_buy":[],"scanner_v2_sell":[],"scanner_v2_last_scan":0,
    "radar_watchlist":[],"radar_top5":[],"log_debounce":{},"watchlist":{},
    "no_entry_feed":[],"decision_log":[]}

# ========== SCANNER V2 ==========
def get_usdt_perp_symbols():
    try:
        ex.load_markets(); markets=ex.markets; symbols=[]
        for s in markets:
            if "USDT" in s and markets[s].get('swap') and markets[s].get('active'):
                symbols.append(s.replace(":USDT",""))
        return symbols[:200]
    except Exception as e:
        log_execution(f"Failed to load markets: {e}","ERROR"); return [DEFAULT_SYMBOL]
def rf_proximity_score(rf,adx_val,vol_ok,rsi_val,atr_pct):
    d=abs(rf["distance"]) if rf["distance"] else 1.0
    prox=max(0.0,1.0-(d/0.015))
    if adx_val<18: tr=0.2
    elif adx_val<=30: tr=1.0
    elif adx_val<=40: tr=0.6
    else: tr=0.2
    if 30<=rsi_val<=70: rs=0.5
    elif 20<=rsi_val<30 or 70<rsi_val<=80: rs=0.3
    else: rs=0.0
    vs=1.0 if vol_ok else 0.0
    vb=0.3 if 0.5<=atr_pct<=2.0 else 0.0
    tb=1.2 if rf["triggered"] else 0.0
    return float((prox*0.35)+(tr*0.25)+(vs*0.15)+(rs*0.1)+(vb*0.05)+tb)
def scan_market_rf(top_n=40):
    symbols=get_usdt_perp_symbols()
    if not symbols: return []
    rf_engine=RFEngine(period=20,multiplier=3.5); results=[]
    for sym in symbols[:150]:
        try:
            df=get_ohlcv_safe(sym,120,htf=False)
            if df is None or not validate_dataframe(df,100): continue
            try:
                atr_series=compute_atr(df,14); adx_series=compute_adx(df,14); rsi_series=compute_rsi(df,14)
                atr_val=float(atr_series.iloc[-1]); adx_val=float(adx_series.iloc[-1]); rsi_val=float(rsi_series.iloc[-1])
                if rsi_val==0 or rsi_val is None or math.isnan(rsi_val): continue
                if atr_val==0 or atr_val is None or math.isnan(atr_val): continue
                if adx_val is None or math.isnan(adx_val): adx_val=20.0
                atr_pct=(atr_val/df['close'].iloc[-1])*100 if df['close'].iloc[-1]>0 else 0
            except: continue
            rf=rf_engine.compute(df)
            if rf["signal"] is None and abs(rf.get("distance",1.0))>0.015: continue
            av=df['volume'].iloc[-20:].mean(); vo=df['volume'].iloc[-1]>=av*0.7
            atr_pct=(atr_val/df['close'].iloc[-1])*100 if df['close'].iloc[-1]>0 else 0
            sc=rf_proximity_score(rf,adx_val,vo,rsi_val,atr_pct)
            if sc<0.3: continue
            status="TRIGGERED" if rf["triggered"] else ("READY" if sc>=0.6 else "PROXIMITY")
            results.append({"symbol":sym,"score":round(sc,3),"rf_signal":rf["signal"],
                            "rf_triggered":rf["triggered"],"rf_distance":round(rf.get("distance",0),4),
                            "adx":round(adx_val,1),"rsi":round(rsi_val,1),"atrp":round(atr_pct,2),"status":status})
        except: continue
    results=sorted(results,key=lambda x:x["score"],reverse=True)
    return results[:top_n]
def smart_scanner_v2():
    symbols=get_usdt_perp_symbols()[:150]; bc=[]; sc=[]
    for sym in symbols:
        try:
            df=get_ohlcv_safe(sym,150)
            if df is None or len(df)<100: continue
            price=df['close'].iloc[-1]
            rf_engine=RFEngine(period=20,multiplier=3.5); rf=rf_engine.compute(df)
            if rf["distance"] is None: continue
            rp=abs(rf["distance"])
            vma=df['volume'].iloc[-21:-1].mean()
            if df['volume'].iloc[-1]<0.5*vma: continue
            av=compute_atr(df).iloc[-1]
            ap=(av/price)*100 if price>0 else 0
            if ap<0.2: continue
            lc=detect_liquidity_context(df,lookback=10)
            sup,res=get_clustered_zones(df,lookback=120,cluster_pct=0.002)
            zc=detect_zone_context(price,sup,res,threshold=0.003)
            sct=detect_structure_shift(df)
            rb=candle_rejection(df,"BUY"); rs=candle_rejection(df,"SELL")
            vsf=volume_spike(df); loc=compute_location(df,price,"BUY")
            sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
            smb=0; sms=0
            if sm["smart_money_dominant"]:
                if sm["institutional_bias"]=="BUY": smb+=2.5
                elif sm["institutional_bias"]=="SELL": sms+=2.5
            if sm["distribution_risk"]>70: sms+=1.5; smb-=2.0
            if sm["accumulation_strength"]>60: smb+=1.5; sms-=2.0
            if sm["retail_euphoria"]: smb-=1.5; sms-=1.5
            if mom["trend_expansion"]:
                if mom["flow_bias"]=="BUY": smb+=2.0
                elif mom["flow_bias"]=="SELL": sms+=2.0
            if mom["momentum_decay"]: smb-=1.5; sms-=1.5
            if mom["exhaustion_risk"]>70: smb-=2.0; sms-=2.0
            if mom["climax_risk"]>70: smb-=1.5; sms-=1.5
            if mom["greed_state"]: smb-=1.0; sms-=1.0
            bsb=0
            if lc=="sell_side_taken": bsb+=2
            if zc["near_support"]: bsb+=2
            if sct=="bullish_shift": bsb+=1.5
            if rp<0.0015: bsb+=2
            elif rp<0.003: bsb+=1
            if rb: bsb+=1.5
            if vsf: bsb+=1
            bss=0
            if lc=="buy_side_taken": bss+=2
            if zc["near_resistance"]: bss+=2
            if sct=="bearish_shift": bss+=1.5
            if rp<0.0015: bss+=2
            elif rp<0.003: bss+=1
            if rs: bss+=1.5
            if vsf: bss+=1
            fsb=bsb+smb; fss=bss+sms
            if fsb>=5: bc.append({"symbol":sym,"score":round(fsb,2),"rf_prox":round(rp*100,3),
                "liquidity":lc,"zone":zc,"structure":sct,"rejection":rb,"volume_spike":vsf,"location":loc,
                "smart_money":{"bias":sm["institutional_bias"],"bias_detailed":sm.get("institutional_bias_detailed","NEUTRAL"),
                "dominant":sm["smart_money_dominant"],"distribution_risk":round(sm["distribution_risk"],1),
                "accumulation":round(sm["accumulation_strength"],1)},
                "momentum":{"expansion":mom["trend_expansion"],"decay":mom["momentum_decay"],
                "exhaustion_risk":round(mom["exhaustion_risk"],1),"greed":mom["greed_state"]}})
            if fss>=5: sc.append({"symbol":sym,"score":round(fss,2),"rf_prox":round(rp*100,3),
                "liquidity":lc,"zone":zc,"structure":sct,"rejection":rs,"volume_spike":vsf,
                "location":compute_location(df,price,"SELL"),
                "smart_money":{"bias":sm["institutional_bias"],"bias_detailed":sm.get("institutional_bias_detailed","NEUTRAL"),
                "dominant":sm["smart_money_dominant"],"distribution_risk":round(sm["distribution_risk"],1),
                "accumulation":round(sm["accumulation_strength"],1)},
                "momentum":{"expansion":mom["trend_expansion"],"decay":mom["momentum_decay"],
                "exhaustion_risk":round(mom["exhaustion_risk"],1),"greed":mom["greed_state"]}})
        except: continue
    return sorted(bc,key=lambda x:x["score"],reverse=True)[:10], sorted(sc,key=lambda x:x["score"],reverse=True)[:10]

# ========== EXECUTE ENTRY (FINAL) ==========
def execute_entry(side,symbol,price,sl,tp1,tp2,score,reason,atr_val,trade_type,entry_type,classification):
    if STATE.get("open") or TRADE_STATE.get("in_position"):
        log_execution(f"[ENTRY] Already in position, skipping {symbol}","WARN"); return False
    free_bal=get_free_balance_safe() if not PAPER_MODE else paper["balance"]
    usable=free_bal*BALANCE_SAFETY_FACTOR
    if PAPER_MODE: balance=paper["balance"]
    else: balance=usable
    if classification in ("SNIPER","INSTITUTIONAL_SNIPER"): mp=0.40; tl="STRONG"
    elif classification=="TREND": mp=0.30; tl="NORMAL"
    elif classification=="LOW": mp=0.15; tl="LOW_CONF"
    else: mp=0.30; tl="NORMAL"
    margin=balance*mp; notional=margin*LEVERAGE; qty=notional/price
    log_execution(f"[SIZING] Free={free_bal:.2f} Usable={balance:.2f} Type={tl} Margin={margin:.2f} Qty={qty:.6f}","INFO")
    df=get_ohlcv_safe(symbol,100)
    pdi,mdi,_,_=get_di_components(df) if df is not None else (None,None,None,None)
    di_dom=False
    if pdi is not None and mdi is not None: di_dom=(side=="BUY" and pdi>mdi) or (side=="SELL" and mdi>pdi)
    wp=False
    if df is not None:
        last=df.iloc[-1]
        if side=="BUY":
            if last['close']<last['open'] and abs(last['close']-last['open'])<atr_val*0.3: wp=True
        else:
            if last['close']>last['open'] and abs(last['close']-last['open'])<atr_val*0.3: wp=True
    sa=False; ss=detect_structure_shift(df) if df is not None else None
    if side=="BUY" and ss=="bullish_shift": sa=True
    elif side=="SELL" and ss=="bearish_shift": sa=True
    cd=0.0
    if df is not None:
        last=df.iloc[-1]
        if side=="SELL" and last['close']>last['open']:
            b=abs(last['close']-last['open'])
            if b>atr_val*0.6: cd=b/atr_val
        elif side=="BUY" and last['close']<last['open']:
            b=abs(last['close']-last['open'])
            if b>atr_val*0.6: cd=b/atr_val
    ms={"adx":compute_adx(df).iloc[-1] if df is not None else 20.0,"regime":MEMORY.get("regime","UNKNOWN"),
        "di_dominance":di_dom,"weak_pullback":wp,"structure_aligned":sa,"counter_displacement":cd,
        "trend_health":trend_engine.get_trend_health(df,side) if df is not None else 5}
    narr={"classification":classification}; ec={"price":price,"atr":atr_val}
    thesis=_thesis_engine.build_thesis(symbol,side,trade_type,ms,narr,ec)
    STATE["trade_thesis"]=thesis.__dict__
    rc=MarketRegimeClassifier.classify(df) if df is not None else "UNKNOWN"
    ds=abs(pdi-mdi) if pdi is not None else 0
    ic=ConfidenceEngine.calculate_initial_confidence(score,0,rc,ms["adx"],ds,"mid")
    if df is not None:
        sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
        ic=ConfidenceEngine.apply_institutional_modifiers(ic,sm,mom,mom.get("continuation_strength",50))
    ii=MEMORY.get(f"intent_{symbol}",{}); is_=ii.get("score",0)
    if is_>=85: ic+=15
    elif is_>=75: ic+=10
    ic=min(100,ic)
    STATE["current_confidence"]=ic; STATE["market_regime"]=rc
    if PAPER_MODE:
        paper["position"]={"side":side,"entry":price,"qty":qty,"remaining_qty":qty}
        STATE.update({"open":True,"side":side,"entry":price,"qty":qty,"remaining_qty":qty,"sl":sl,
            "current_symbol":symbol,"tp1_done":False,"trail_activated":False,"peak":0.0,"atr":atr_val,
            "entry_time":time.time(),"entry_reasons":[reason],"trade_score":score,"partial_closed":False,
            "tp1_price":tp1,"tp2_price":tp2,"trade_type":trade_type,"entry_type":entry_type,"be_done":False,
            "tp1_hit":False,"tp2_hit":False,"trail_stop":0.0,"roe_pct":0.0,"mark_price":price,
            "narrative_classification":STATE.get("narrative_classification",""),
            "narrative_confidence":STATE.get("narrative_confidence",0.0),
            "confidence_level":STATE.get("confidence_level",""),"trade_thesis":thesis.__dict__,
            "current_confidence":ic,"market_regime":rc,"adx_live":ms["adx"],
            "di_plus_live":pdi if pdi else 0,"di_minus_live":mdi if mdi else 0,
            "trade_personality":"NEUTRAL","institutional_flow":"NEUTRAL",
            "synthetic_sl":sl,"synthetic_tp1":tp1,"max_price":price,"min_price":price,
            "peak_roe":0.0,"peak_price":price,"peak_unrealized_pnl":0.0,"drawdown_from_peak":0.0,
            "tp1_hold_score":10,"exit_warning":0,"runner_mode":False,"entry_atr":atr_val,
            "last_council_action":"N/A","last_council_reason":"","last_council_confidence":0})
        TRADE_STATE.update({"in_position":True,"symbol":symbol,"side":side,"entry":price,"qty":qty,
                            "tp1_hit":False,"trail_on":False,"last_update_ts":time.time()})
        _live_manager.start_trade(symbol,side,price,qty,sl,tp1,tp2)
        _live_manager.set_entry_atr(atr_val)
        STATE["dynamic_manager"]=DynamicTradeManager(symbol,side,price,qty,atr_val,sl,tp1,tp2)
        update_position_dashboard(symbol,side,price,qty)
        log_execution(f"📗 PAPER {entry_type} {side} {qty:.6f} @ {price} | {reason}","SUCCESS")
        tg_entry(side,symbol,price,sl,tp1,score,reason,entry_type)
        return True
    sym=normalize_symbol(symbol)
    market=ex.market(sym)
    min_qty=market['limits']['amount']['min']
    if qty<min_qty: log_execution(f"SKIP: qty {qty:.6f} below min {min_qty}","WARN"); return False
    precision=market['precision']['amount']
    qty=math.floor(qty/precision)*precision
    if qty<=0: return False
    order=open_position(side,qty,symbol)
    if order:
        STATE.update({"open":True,"side":side,"entry":price,"qty":qty,"remaining_qty":qty,"sl":sl,
            "current_symbol":symbol,"tp1_done":False,"trail_activated":False,"peak":0.0,"atr":atr_val,
            "entry_time":time.time(),"entry_reasons":[reason],"trade_score":score,"partial_closed":False,
            "tp1_price":tp1,"tp2_price":tp2,"trade_type":trade_type,"entry_type":entry_type,"be_done":False,
            "tp1_hit":False,"tp2_hit":False,"trail_stop":0.0,"roe_pct":0.0,"mark_price":price,
            "narrative_classification":STATE.get("narrative_classification",""),
            "narrative_confidence":STATE.get("narrative_confidence",0.0),
            "confidence_level":STATE.get("confidence_level",""),"trade_thesis":thesis.__dict__,
            "current_confidence":ic,"market_regime":rc,"adx_live":ms["adx"],
            "di_plus_live":pdi if pdi else 0,"di_minus_live":mdi if mdi else 0,
            "trade_personality":"NEUTRAL","institutional_flow":"NEUTRAL",
            "synthetic_sl":sl,"synthetic_tp1":tp1,"max_price":price,"min_price":price,
            "peak_roe":0.0,"peak_price":price,"peak_unrealized_pnl":0.0,"drawdown_from_peak":0.0,
            "tp1_hold_score":10,"exit_warning":0,"runner_mode":False,"entry_atr":atr_val,
            "last_council_action":"N/A","last_council_reason":"","last_council_confidence":0})
        TRADE_STATE.update({"in_position":True,"symbol":symbol,"side":side,"entry":price,"qty":qty,
                            "tp1_hit":False,"trail_on":False,"last_update_ts":time.time()})
        _live_manager.start_trade(symbol,side,price,qty,sl,tp1,tp2)
        _live_manager.set_entry_atr(atr_val)
        STATE["dynamic_manager"]=DynamicTradeManager(symbol,side,price,qty,atr_val,sl,tp1,tp2)
        update_position_dashboard(symbol,side,price,qty)
        log_execution(f"📗 LIVE {entry_type} {side} {qty:.6f} @ {price} | {reason}","SUCCESS")
        tg_entry(side,symbol,price,sl,tp1,score,reason,entry_type)
        time.sleep(1); sync_position_state(symbol)
        return True
    return False

# ========== SYNC STATE ==========
def sync_position_state(symbol=None):
    if PAPER_MODE:
        if STATE.get("open"):
            price=get_ticker_safe(STATE["current_symbol"])
            if price:
                if STATE["side"]=="BUY": rp=(price-STATE["entry"])/STATE["entry"]*100
                else: rp=(STATE["entry"]-price)/STATE["entry"]*100
                roe=rp*LEVERAGE
                STATE["roe_pct"]=roe; STATE["mark_price"]=price
                if STATE["side"]=="BUY": STATE["unrealized_pnl_usdt"]=(price-STATE["entry"])*STATE["qty"]
                else: STATE["unrealized_pnl_usdt"]=(STATE["entry"]-price)*STATE["qty"]
                return price,0.0,0.0,roe
        return None,None,None,None
    if not symbol and STATE.get("open"): symbol=STATE["current_symbol"]
    if not symbol: return None,None,None,None
    snap=_exchange_sync.fetch_live_snapshot(symbol)
    if snap is None:
        if STATE.get("open"):
            log_execution(f"[POS_SYNC] Position closed externally on {symbol}, cleaning state","WARN")
            with _TRADE_LOCK:
                STATE["open"]=False; TRADE_STATE["in_position"]=False
                _live_manager.lifecycle_state=TradeLifecycleState.CLOSED
                DASHBOARD_STATE["live_trade_mode"]=False
        return None,None,None,None
    with _TRADE_LOCK:
        if not STATE.get("open"):
            STATE["open"]=True; STATE["side"]=snap.side; STATE["entry"]=snap.entry_price
            STATE["qty"]=snap.qty; STATE["remaining_qty"]=snap.qty
            STATE["current_symbol"]=symbol; STATE["entry_time"]=time.time()
            TRADE_STATE.update({"in_position":True,"symbol":symbol,"side":snap.side,
                                "entry":snap.entry_price,"qty":snap.qty,"last_update_ts":time.time()})
            _live_manager.start_trade(symbol,snap.side,snap.entry_price,snap.qty,0.0,0.0,0.0)
        else:
            STATE["entry"]=snap.entry_price; STATE["qty"]=snap.qty; STATE["remaining_qty"]=snap.qty
            STATE["side"]=snap.side
            TRADE_STATE.update({"entry":snap.entry_price,"qty":snap.qty,"side":snap.side})
        STATE["margin"]=snap.margin; STATE["unrealized_pnl_usdt"]=snap.unrealized_pnl
        STATE["roe_pct"]=snap.roe_pct; STATE["leverage"]=snap.leverage
        STATE["mark_price"]=snap.mark_price; STATE["liquidation_price"]=snap.liquidation_price
    return snap.mark_price,snap.unrealized_pnl,snap.margin,snap.roe_pct

# ========== INSTANTIATE MANAGERS ==========
_event_bus=EventBus()
_exchange_sync=ExchangeSyncService(_event_bus)
_recovery_guard=RecoveryGuard(_event_bus,_exchange_sync)
_live_manager=LiveTradeManager(_event_bus,_exchange_sync,_recovery_guard)
_unified_manager=UnifiedPositionManager(_event_bus)
_state_machine=TradeStateMachine()
_brain=InstitutionalTradeBrain()

# ========== VWAP / EXHAUSTION ==========
def vwap_features(df):
    vw=compute_vwap(df); price=df['close'].iloc[-1]
    d=(price-vw.iloc[-1])/vw.iloc[-1] if vw.iloc[-1]!=0 else 0.0
    s=vw.iloc[-1]-vw.iloc[-5] if len(vw)>=5 else 0.0
    return {"vwap":vw.iloc[-1],"distance":d,"slope":s}

# ========== DASHBOARD ==========
app=Flask(__name__)
def update_position_dashboard(symbol,side,entry,qty,pnl=0.0):
    DASHBOARD_STATE["position"]={"symbol":symbol,"side":side,"entry":round(entry,4),"qty":qty,
        "pnl":round(pnl,2),"sl":round(STATE.get("synthetic_sl",0),4),
        "tp1":round(STATE.get("synthetic_tp1",0),4),"tp2":round(STATE.get("tp2_price",0),4),
        "tp1_done":STATE.get("tp1_hit",False),"trailing_active":STATE.get("trail_activated",False),
        "regime":MEMORY.get("regime","UNKNOWN"),"trade_type":STATE.get("trade_type","N/A"),
        "entry_type":STATE.get("entry_type","N/A"),"classification":STATE.get("classification","N/A"),
        "location":STATE.get("location","N/A"),"zone":STATE.get("zone_info","N/A"),
        "score":STATE.get("trade_score",0),
        "narrative_classification":STATE.get("narrative_classification",""),
        "narrative_confidence":STATE.get("narrative_confidence",0.0),
        "confidence_level":STATE.get("confidence_level",""),
        "current_confidence":STATE.get("current_confidence",50.0),
        "market_regime":STATE.get("market_regime","UNKNOWN"),
        "continuation_pressure":STATE.get("continuation_pressure",50),
        "trade_state":STATE.get("trade_state","RANGE_CHOP"),
        "trail_multiplier":STATE.get("smart_trail_mult",1.5),
        "delay_tp1":STATE.get("delay_tp1",False),
        "council_action":STATE.get("last_council_action","N/A"),
        "council_reason":STATE.get("last_council_reason",""),
        "council_confidence":STATE.get("last_council_confidence",0)}
def clear_position_dashboard(): DASHBOARD_STATE["position"]=None

@app.route("/")
def dashboard():
    rf_items=MEMORY.get("rf_dashboard",[])[:20]
    rf_html="".join([f"<div>{i['icon']} {i['symbol']} | {i['status']} | score={i['score']:.2f} | ADX={i['adx']:.1f}</div>" for i in rf_items])
    html=f"""<!DOCTYPE html><html><head><title>RF v29 Council</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>body{{background:#0b0f14;color:#e6edf3;font-family:Consolas;margin:0}}
.header{{padding:14px 16px;background:#111827;color:#00ff9f;font-size:22px}}
.section{{padding:12px 14px;border-bottom:1px solid #1f2937}}
.title{{color:#9ca3af;margin-bottom:6px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.card{{background:#111827;border-radius:10px;padding:10px}}
.green{{color:#00ffa6}}.red{{color:#ff4d4d}}.blue{{color:#3498db}}
.log,.err{{max-height:220px;overflow:auto;white-space:pre-wrap;font-size:12px}}
.council-box{{background:linear-gradient(145deg,#0a1a0a,#0a0f0a);border:1px solid #2ecc71;border-radius:12px;padding:12px;margin-top:8px}}
</style></head><body>
<div class="header">🏛️ RF v29 Council Edition</div>
<div class="section"><div class="title">💰 ACCOUNT</div><div class="grid">
<div class="card">Balance<div id="bal">-</div></div>
<div class="card">Free<div id="free_bal">-</div></div>
<div class="card">Mode<div id="mode">-</div></div>
<div class="card">Trades<div id="trades">0</div></div>
<div class="card">Wins<div id="wins" class="green">0</div></div>
<div class="card">Losses<div id="losses" class="red">0</div></div>
<div class="card">WinRate<div id="winrate">0%</div></div>
</div></div>
<div class="section"><div class="title">📊 P&L</div><div class="grid">
<div class="card">Total ROE%<div id="total_pnl" class="green">0%</div></div>
<div class="card">USDT<div id="total_pnl_usdt">0.00</div></div>
<div class="card">Last Trade<div id="last_trade">N/A</div></div>
</div></div>
<div class="section"><div class="title">📍 POSITION</div>
<div id="pos" class="card">No active trade</div>
</div>
<div class="section"><div class="title">🏛️ COUNCIL</div>
<div id="council" class="council-box">No active session</div>
</div>
<div class="section"><div class="title">📡 RF SIGNALS</div>
<div id="rfSignals" class="card">{rf_html or 'None'}</div>
</div>
<div class="section"><div class="title">📜 LOGS</div><div id="logs" class="card log"></div></div>
<div class="section"><div class="title">🚨 ERRORS</div><div id="errors" class="card err"></div></div>
<div class="section"><div class="title">🎮 MANUAL</div>
<button onclick="manualTrade('BUY')">BUY</button>
<button onclick="manualTrade('SELL')">SELL</button>
<button onclick="manualClose()">CLOSE</button>
</div>
<script>
async function fetchData(){{
  try{{const r=await fetch('/data');const d=await r.json();updateUI(d);}}catch(e){{}}
}}
function updateUI(d){{
  document.getElementById("bal").innerText=d.balance.toFixed(2);
  document.getElementById("free_bal").innerText=d.free_balance.toFixed(2);
  document.getElementById("mode").innerText=d.mode;
  document.getElementById("trades").innerText=d.stats.trades;
  document.getElementById("wins").innerText=d.stats.wins;
  document.getElementById("losses").innerText=d.stats.losses;
  document.getElementById("winrate").innerText=d.stats.win_rate.toFixed(1)+"%";
  document.getElementById("total_pnl").innerHTML=d.total_pnl||"0%";
  document.getElementById("total_pnl_usdt").innerHTML=d.total_pnl_usdt?d.total_pnl_usdt.toFixed(2):"0.00";
  document.getElementById("last_trade").innerText=d.last_trade||"N/A";
  if(d.position){{
    let pc=d.position.pnl>=0?"green":"red";
    document.getElementById("pos").innerHTML=`
      <div><b>${{d.position.symbol}}</b> | ${{d.position.side}} | ${{d.position.entry_type}}</div>
      <div>Entry: ${{d.position.entry}} | ROE: <span class="${{pc}}">${{d.position.pnl}}%</span></div>
      <div>SL: ${{d.position.sl}} | TP1: ${{d.position.tp1}}</div>
      <div>TP1: ${{d.position.tp1_done}} | Trail: ${{d.position.trailing_active}}</div>`;
  }} else document.getElementById("pos").innerHTML="No active trade";
  if(d.council&&d.council.active){{
    document.getElementById("council").innerHTML=`
      <div style="font-size:18px;color:#2ecc71"><b>🏛️ ${{d.council.last_action}}</b> (conf: ${{d.council.last_confidence.toFixed(0)}})</div>
      <div style="margin-top:6px;color:#9ca3af">${{d.council.last_reason}}</div>
      <div style="margin-top:6px;font-size:11px;color:#6b7280">${{d.council.members_summary||''}}</div>`;
  }} else document.getElementById("council").innerHTML="No active session";
  document.getElementById("logs").innerHTML=(d.logs||[]).slice(-20).join("<br>");
  document.getElementById("errors").innerHTML=(d.errors||[]).slice(-5).join("<br>");
}}
async function manualTrade(s){{await fetch('/trade',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{side:s}})}});}}
async function manualClose(){{await fetch('/close',{{method:'POST'}});}}
setInterval(fetchData,6000);fetchData();
</script></body></html>"""
    return html

@app.route("/data")
def data():
    cached=cache_get("dashboard",5)
    if cached is not None: return jsonify(safe_json(cached))
    try:
        bal=get_balance_safe(); fb=get_free_balance_safe()
        mode="LIVE" if MODE_LIVE else "PAPER"
        perf=get_dashboard_metrics()
        pos=None
        if STATE["open"] and STATE.get("current_symbol"):
            pos={"symbol":STATE["current_symbol"],"side":STATE["side"],"entry":round(STATE["entry"],4),
                "qty":STATE["qty"],"pnl":round(STATE.get("roe_pct",0),2),
                "sl":round(STATE.get("synthetic_sl",0),4),"tp1":round(STATE.get("synthetic_tp1",0),4),
                "tp2":round(STATE.get("tp2_price",0),4),"tp1_done":STATE.get("tp1_hit",False),
                "trailing_active":STATE.get("trail_activated",False),
                "entry_type":STATE.get("entry_type","N/A"),
                "classification":STATE.get("classification","N/A"),
                "current_confidence":STATE.get("current_confidence",50.0),
                "market_regime":STATE.get("market_regime","UNKNOWN"),
                "trade_state":STATE.get("trade_state","RANGE_CHOP")}
        council_data={"active":STATE.get("open",False),
                     "last_action":STATE.get("last_council_action","N/A"),
                     "last_reason":STATE.get("last_council_reason",""),
                     "last_confidence":STATE.get("last_council_confidence",0),
                     "members_summary":(STATE.get("last_council_decision") or {}).get("votes","")}
        payload={"balance":bal,"free_balance":fb,"mode":mode,
                 "stats":DASHBOARD_STATE["stats"],"position":pos,
                 "logs":DASHBOARD_STATE["logs"][-30:],"errors":DASHBOARD_STATE["errors"][-10:],
                 "total_pnl":perf["total_pnl"],"total_pnl_usdt":perf["total_pnl_usdt"],
                 "last_trade":perf["last_trade"],"council":council_data,
                 "rf_dashboard":MEMORY.get("rf_dashboard",[])[:20],
                 "live_trade_mode":DASHBOARD_STATE.get("live_trade_mode",False),
                 "lifecycle_state":_live_manager.lifecycle_state.value}
        safe_payload=safe_json(payload); cache_set("dashboard",safe_payload)
        return jsonify(safe_payload),200
    except Exception as e:
        log_execution(f"/data error: {traceback.format_exc()}","ERROR")
        return jsonify({"error":str(e)}),200

def get_dashboard_metrics():
    wr=(PERF["wins"]/PERF["trades"]*100) if PERF["trades"] else 0
    tp=PERF["total_pnl_pct"]*100
    lt=PERF["last_trade"]; ltt="N/A"
    if lt:
        sg="+" if lt["pnl_pct"]>=0 else ""
        ltt=f'{lt["result"]} ({sg}{lt["pnl_pct"]:.2f}%)'
    return {"winrate":f"{wr:.1f}%","total_pnl":f"{tp:+.2f}%","total_pnl_usdt":PERF["total_pnl_usdt"],
            "last_trade":ltt,"trades":PERF["trades"],"wins":PERF["wins"],"losses":PERF["losses"]}

@app.route("/trade",methods=["POST"])
def manual_trade():
    data=request.json; side=data.get("side")
    if not side or side not in ["BUY","SELL"]: return jsonify({"error":"Invalid side"}),400
    if STATE["open"]: return jsonify({"error":"Position open"}),400
    price=get_ticker_safe(DEFAULT_SYMBOL)
    if not price or price<=0: return jsonify({"error":"No price"}),400
    df=get_ohlcv_safe(DEFAULT_SYMBOL,100)
    if df is None: return jsonify({"error":"No data"}),500
    atr=compute_atr(df).iloc[-1]
    sl=price-atr*1.6 if side=="BUY" else price+atr*1.6
    tp1=price*1.006 if side=="BUY" else price*0.994
    tp2=price*1.02 if side=="BUY" else price*0.98
    ok=execute_entry(side,DEFAULT_SYMBOL,price,sl,tp1,tp2,80,"Manual",atr,"HYBRID","MANUAL","SNIPER")
    return jsonify({"message":"Done" if ok else "Failed"}),200 if ok else 500

@app.route("/close",methods=["POST"])
def manual_close():
    if not STATE["open"]: return jsonify({"error":"No position"}),400
    close_position_full()
    return jsonify({"message":"Closed"}),200

@app.route("/health")
def health(): return jsonify({"ok":True})

def keep_alive():
    while True:
        time.sleep(KEEP_ALIVE_INTERVAL)
        try: requests.get(f"http://localhost:{os.environ.get('PORT',8000)}/health",timeout=5)
        except: pass

_last_cleanup=0
def hourly_cleanup():
    global _last_cleanup
    if time.time()-_last_cleanup<3600: return
    CACHE["ohlcv"]["value"].clear(); CACHE["ticker"]["value"].clear()
    CACHE["orderbook"]["value"].clear(); gc.collect()
    _last_cleanup=time.time()

_last_snapshot_time=0
def print_snapshot():
    global _last_snapshot_time
    now=time.time()
    if now-_last_snapshot_time<SNAPSHOT_INTERVAL: return
    _last_snapshot_time=now
    bal=get_balance_safe(); fb=get_free_balance_safe()
    mode="LIVE" if MODE_LIVE else "PAPER"
    perf=get_dashboard_metrics()
    print("\n"+"="*70)
    print(color_text(f"🏛️ RF v29 Council Edition ({mode}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",BOLD))
    print(f"💰 Balance: {color_text(f'{bal:.2f} USDT',GREEN)}   Free: {color_text(f'{fb:.2f} USDT',GREEN)}")
    print(f"📊 Total PnL: {color_text(perf['total_pnl'],GREEN if perf['total_pnl'].startswith('+') else RED)} | Last: {perf['last_trade']}")
    print(f"🧠 Regime: {color_text(MEMORY.get('regime','RANGE'),CYAN)}")
    if STATE["open"]:
        roe=STATE.get("roe_pct",0.0)
        print(f"📊 POSITION: {STATE['current_symbol']} {STATE['side']} ({STATE.get('entry_type','?')})")
        print(f"   Entry: {STATE['entry']:.4f} | ROE: {color_pnl(roe)}")
        print(f"   SL: {STATE.get('synthetic_sl',0):.4f} | TP1: {STATE.get('synthetic_tp1',0):.4f}")
        print(f"   🏛️ Council: {color_text(STATE.get('last_council_action','N/A'),MAGENTA)} | {STATE.get('last_council_reason','')[:80]}")
        print(f"   Lifecycle: {color_text(_live_manager.lifecycle_state.value,BLUE)}")
    else: print("📊 POSITION: None")
    print("="*70+"\n")

def build_rf_dashboard():
    dash=[]
    cands=scan_market_rf(top_n=30)
    for c in cands:
        dash.append({"symbol":c["symbol"],"status":c.get("status","PROXIMITY"),
                     "icon":"🔔" if c["rf_triggered"] else "📡","score":c["score"],
                     "adx":c["adx"],"rsi":c["rsi"],"atrp":c["atrp"],"signal":c["rf_signal"] or "N/A"})
    MEMORY["rf_dashboard"]=dash
    return dash

def run_scanner_v2():
    try:
        buy,sell=smart_scanner_v2()
        MEMORY["scanner_v2_buy"]=buy; MEMORY["scanner_v2_sell"]=sell
        MEMORY["scanner_v2_last_scan"]=time.time()
    except Exception as e: log_execution(f"Scanner v2 error: {traceback.format_exc()}","ERROR")

def update_institutional_flow_scanner():
    try:
        df=get_ohlcv_safe(DEFAULT_SYMBOL,100)
        if df is None or not validate_dataframe(df,80): return
        sm=SmartMoneyEngine.analyze_smart_money(df); mom=MomentumFlowEngine.analyze_momentum_flow(df)
        DASHBOARD_STATE["institutional_flow"]={"banker_pressure":sm["banker_pressure"],
            "retailer_pressure":sm["retailer_pressure"],"hot_money":sm["hot_money_pressure"],
            "institutional_bias":sm["institutional_bias"],
            "institutional_bias_detailed":sm.get("institutional_bias_detailed","NEUTRAL"),
            "flow_alignment":sm["flow_alignment"],"distribution_risk":sm["distribution_risk"],
            "momentum_health":mom["momentum_health"],"continuation_strength":mom["continuation_strength"],
            "exhaustion_risk":mom["exhaustion_risk"],"climax_risk":mom["climax_risk"],
            "greed_state":mom["greed_state"],"smart_money_dominant":sm["smart_money_dominant"]}
    except: pass

def live_institutional_updater():
    while True:
        try:
            if STATE.get("open"): time.sleep(5); continue
            update_institutional_flow_scanner()
        except: pass
        time.sleep(5)

SNIPER_MODE=True; CANDIDATE_SCAN_INTERVAL=15

def sync_all_states():
    if PAPER_MODE:
        MEMORY["position_status"]="OPEN" if STATE.get("open") else "CLOSED"
        return
    symbol=STATE.get("current_symbol") if STATE.get("open") else None
    if not symbol:
        MEMORY["position_status"]="CLOSED"
        return
    snap=_exchange_sync.fetch_live_snapshot(symbol)
    if snap is None:
        with _TRADE_LOCK: STATE["open"]=False; TRADE_STATE["in_position"]=False
        MEMORY["position_status"]="CLOSED"

# ========== MAIN LOOP (SIMPLIFIED - COUNCIL ONLY) ==========
def main_loop_sniper():
    global INSUFFICIENT_MARGIN_COOLDOWN_UNTIL,_last_queue_promote,_last_queue_eval
    last_scan=0; last_scanner_v2=0; last_radar_scan=0; last_radar_refresh=0
    last_candidate_scan=0; last_flow_update=0; last_universe_build=0
    last_discovery_scan=0; last_priority_update=0
    watchlist_rotation=None
    try:
        ex.load_markets(); log_execution(f"Markets loaded","INFO")
    except Exception as e: log_execution(f"Failed to load markets: {e}","ERROR")
    tg_start(get_balance_safe(),"LIVE" if MODE_LIVE else "PAPER")
    run_scanner_v2()
    threading.Thread(target=live_institutional_updater,daemon=True).start()
    _last_queue_promote=time.time(); _last_queue_eval=time.time()

    while True:
        try:
            now=time.time()
            sync_all_states()
            if now-last_discovery_scan>GLOBAL_SCAN_INTERVAL:
                global_discovery_scan(); last_discovery_scan=now
            if now-last_priority_update>300:
                WatchlistPriorityManager.update_priorities(); last_priority_update=now
            if USE_EXECUTION_QUEUE:
                if now-_last_queue_promote>QUEUE_PROMOTE_INTERVAL:
                    promote_to_queue(); _last_queue_promote=now
                if now-_last_queue_eval>QUEUE_RE_EVAL_INTERVAL:
                    queue.re_evaluate_all(lambda s:get_ohlcv_safe(s,100))
                    _last_queue_eval=now
                if not (STATE.get("open") or TRADE_STATE.get("in_position")): process_queue_entry()
                if now%60<1: queue.cleanup()
            if now-last_universe_build>1800:
                universe=build_40_symbol_universe()
                watchlist_rotation=WatchlistRotation(universe)
                last_universe_build=now
            if now-last_flow_update>60:
                update_institutional_flow_scanner(); last_flow_update=now

            # ★ SINGLE TRADE PATH - Council only
            if TRADE_STATE["in_position"] or STATE["open"]:
                _live_manager.manage_live_trade()
                sym=STATE.get("current_symbol")
                if sym:
                    price=get_ticker_safe(sym)
                    if price and price>0:
                        df=get_ohlcv_safe(sym,50)
                        if df is not None:
                            update_position_dashboard(sym,STATE["side"],STATE["entry"],STATE["qty"],STATE.get("roe_pct",0.0))
                print_snapshot(); hourly_cleanup()
                time.sleep(BASE_SLEEP)
                continue

            # ★ NEW ENTRY DISCOVERY
            sync_position_state()
            if STATE.get("open"): continue
            if INSUFFICIENT_MARGIN_COOLDOWN_UNTIL and time.time()<INSUFFICIENT_MARGIN_COOLDOWN_UNTIL:
                time.sleep(1); continue
            if now-last_scan>=GLOBAL_SCAN_INTERVAL:
                cands=scan_market_rf(top_n=40)
                MEMORY["top_candidates"]=cands; MEMORY["rf_watchlist"]=cands[:30]
                build_rf_dashboard(); MEMORY["last_scan"]=now; MEMORY["scanned_count"]=len(cands)
                last_scan=now
            if now-last_scanner_v2>=SCANNER_V2_INTERVAL:
                run_scanner_v2(); last_scanner_v2=now
            if SNIPER_MODE:
                if now-last_radar_scan>=SCAN_INTERVAL: rebuild_radar_watchlist(); last_radar_scan=now
                if now-last_radar_refresh>=WATCHLIST_REFRESH: refresh_radar_watchlist(); last_radar_refresh=now
            if now-last_candidate_scan>=CANDIDATE_SCAN_INTERVAL:
                if watchlist_rotation and watchlist_rotation.should_rotate(): watchlist_rotation.get_next_batch()
                smart_opportunity_selection(); last_candidate_scan=now
            if emergency_kill_switch_active(): time.sleep(60); continue
            print_snapshot(); hourly_cleanup()
            time.sleep(BASE_SLEEP)
        except Exception as e:
            log_execution(f"Main loop error: {traceback.format_exc()}","ERROR")
            time.sleep(BASE_SLEEP)

def emergency_kill_switch_active():
    if STATE["daily_loss_limit_hit"]: return True
    bal=get_balance_safe(); today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if STATE["last_trade_day"]!=today:
        STATE["daily_peak_balance"]=bal; STATE["daily_loss_limit_hit"]=False
        STATE["last_trade_day"]=today
    else:
        if STATE["daily_peak_balance"] is None: STATE["daily_peak_balance"]=bal
        else:
            if bal>STATE["daily_peak_balance"]: STATE["daily_peak_balance"]=bal
            lp=(STATE["daily_peak_balance"]-bal)/STATE["daily_peak_balance"]*100
            if lp>=MAX_DAILY_LOSS_PCT:
                STATE["daily_loss_limit_hit"]=True
                log_execution(f"Daily loss limit hit: {lp:.1f}%","ERROR")
                return True
    return False

main_loop=main_loop_sniper

def safe_main_loop():
    while True:
        try: main_loop()
        except Exception as e:
            tb=traceback.format_exc()
            print(f"CRITICAL EXCEPTION: {tb}")
            try: log_execution(f"CRITICAL EXCEPTION: {tb}","ERROR")
            except: pass
            time.sleep(5)

if __name__=="__main__":
    threading.Thread(target=keep_alive,daemon=True).start()
    threading.Thread(target=safe_main_loop,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8000)),debug=False,use_reloader=False)
