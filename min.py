# ⬆️⬆️⬆️ [الجزء 2 ينتهي عند dynamic_spread_tolerance] ⬆️⬆️⬆️

# ========== RF SCANNER ==========
def get_usdt_perp_symbols():
    try:
        ex.load_markets()
        markets = ex.markets
        symbols = []
        for s in markets:
            if "USDT" in s and markets[s].get('swap') and markets[s].get('active'):
                clean = s.replace(":USDT", "")
                symbols.append(clean)
        return symbols[:200]
    except Exception as e:
        log_execution(f"Failed to load markets: {e}", "ERROR")
        return [DEFAULT_SYMBOL]

def rf_proximity_score(rf, adx_val, vol_ok, rsi_val, atr_pct):
    dist = abs(rf["distance"]) if rf["distance"] else 1.0
    proximity = max(0.0, 1.0 - (dist / 0.015))
    if adx_val < 18:
        trend = 0.2
    elif 18 <= adx_val <= 30:
        trend = 1.0
    elif 30 < adx_val <= 40:
        trend = 0.6
    else:
        trend = 0.2
    if 30 <= rsi_val <= 70:
        rsi_score = 0.5
    elif 20 <= rsi_val < 30 or 70 < rsi_val <= 80:
        rsi_score = 0.3
    else:
        rsi_score = 0.0
    vol_score = 1.0 if vol_ok else 0.0
    vol_boost = 0.3 if 0.5 <= atr_pct <= 2.0 else 0.0
    trigger_boost = 1.2 if rf["triggered"] else 0.0
    score = (proximity * 0.35) + (trend * 0.25) + (vol_score * 0.15) + (rsi_score * 0.1) + (vol_boost * 0.05) + trigger_boost
    return float(score)

def scan_market_rf(top_n=40):
    symbols = get_usdt_perp_symbols()
    if not symbols:
        return []
    rf_engine = RFEngine(period=20, multiplier=3.5)
    results = []
    for sym in symbols[:150]:
        try:
            df = get_ohlcv_safe(sym, 120, htf=False)
            if df is None or not validate_dataframe(df, 100):
                continue
            try:
                atr_series = compute_atr(df, 14)
                adx_series = compute_adx(df, 14)
                rsi_series = compute_rsi(df, 14)
                atr_val = float(atr_series.iloc[-1])
                adx_val = float(adx_series.iloc[-1])
                rsi_val = float(rsi_series.iloc[-1])
                if rsi_val == 0 or rsi_val is None or math.isnan(rsi_val):
                    continue
                if atr_val == 0 or atr_val is None or math.isnan(atr_val):
                    continue
                if adx_val is None or math.isnan(adx_val):
                    adx_val = 20.0
                atr_pct = (atr_val / df['close'].iloc[-1]) * 100 if df['close'].iloc[-1] > 0 else 0
            except Exception:
                continue
            rf = rf_engine.compute(df)
            if rf["signal"] is None and abs(rf.get("distance", 1.0)) > 0.015:
                continue
            avg_vol = df['volume'].iloc[-20:].mean()
            vol_ok = df['volume'].iloc[-1] >= avg_vol * 0.7
            atr_pct = (atr_val / df['close'].iloc[-1]) * 100 if df['close'].iloc[-1] > 0 else 0
            score = rf_proximity_score(rf, adx_val, vol_ok, rsi_val, atr_pct)
            if score < 0.3:
                continue
            if rf["triggered"]:
                status = "TRIGGERED"
            elif score >= 0.6:
                status = "READY"
            else:
                status = "PROXIMITY"
            results.append({
                "symbol": sym, "score": round(score, 3),
                "rf_signal": rf["signal"], "rf_triggered": rf["triggered"],
                "rf_distance": round(rf.get("distance", 0), 4),
                "adx": round(adx_val, 1), "rsi": round(rsi_val, 1),
                "atrp": round(atr_pct, 2), "status": status
            })
        except Exception:
            continue
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results[:top_n]

# ========== SMART SCANNER v2 ==========
def smart_scanner_v2():
    symbols = get_usdt_perp_symbols()[:150]
    buy_candidates = []
    sell_candidates = []
    for sym in symbols:
        try:
            df = get_ohlcv_safe(sym, 150)
            if df is None or len(df) < 100:
                continue
            price = df['close'].iloc[-1]
            rf_engine = RFEngine(period=20, multiplier=3.5)
            rf = rf_engine.compute(df)
            if rf["distance"] is None:
                continue
            rf_prox = abs(rf["distance"])
            vol_ma = df['volume'].iloc[-21:-1].mean()
            if df['volume'].iloc[-1] < 0.5 * vol_ma:
                continue
            atr_val = compute_atr(df).iloc[-1]
            atr_pct = (atr_val / price) * 100 if price > 0 else 0
            if atr_pct < 0.2:
                continue
            liquidity_ctx = detect_liquidity_context(df, lookback=10)
            supports, resistances = get_clustered_zones(df, lookback=120, cluster_pct=0.002)
            zone_ctx = detect_zone_context(price, supports, resistances, threshold=0.003)
            structure_ctx = detect_structure_shift(df)
            rejection_buy = candle_rejection(df, "BUY")
            rejection_sell = candle_rejection(df, "SELL")
            vol_spike_flag = volume_spike(df)
            location = compute_location(df, price, "BUY")

            smart_money = SmartMoneyEngine.analyze_smart_money(df)
            momentum = MomentumFlowEngine.analyze_momentum_flow(df)

            score_mod_buy = 0
            score_mod_sell = 0

            if smart_money["smart_money_dominant"]:
                if smart_money["institutional_bias"] == "BUY":
                    score_mod_buy += 2.5
                elif smart_money["institutional_bias"] == "SELL":
                    score_mod_sell += 2.5
            if smart_money["distribution_risk"] > 70:
                score_mod_sell += 1.5
                score_mod_buy -= 2.0
            if smart_money["accumulation_strength"] > 60:
                score_mod_buy += 1.5
                score_mod_sell -= 2.0
            if smart_money["retail_euphoria"]:
                score_mod_buy -= 1.5
                score_mod_sell -= 1.5

            if momentum["trend_expansion"]:
                if momentum["flow_bias"] == "BUY":
                    score_mod_buy += 2.0
                elif momentum["flow_bias"] == "SELL":
                    score_mod_sell += 2.0
            if momentum["momentum_decay"]:
                score_mod_buy -= 1.5
                score_mod_sell -= 1.5
            if momentum["exhaustion_risk"] > 70:
                score_mod_buy -= 2.0
                score_mod_sell -= 2.0
            if momentum["climax_risk"] > 70:
                score_mod_buy -= 1.5
                score_mod_sell -= 1.5
            if momentum["greed_state"]:
                score_mod_buy -= 1.0
                score_mod_sell -= 1.0

            base_score_buy = 0
            if liquidity_ctx == "sell_side_taken":
                base_score_buy += 2
            if zone_ctx["near_support"]:
                base_score_buy += 2
            if structure_ctx == "bullish_shift":
                base_score_buy += 1.5
            if rf_prox < 0.0015:
                base_score_buy += 2
            elif rf_prox < 0.003:
                base_score_buy += 1
            if rejection_buy:
                base_score_buy += 1.5
            if vol_spike_flag:
                base_score_buy += 1

            base_score_sell = 0
            if liquidity_ctx == "buy_side_taken":
                base_score_sell += 2
            if zone_ctx["near_resistance"]:
                base_score_sell += 2
            if structure_ctx == "bearish_shift":
                base_score_sell += 1.5
            if rf_prox < 0.0015:
                base_score_sell += 2
            elif rf_prox < 0.003:
                base_score_sell += 1
            if rejection_sell:
                base_score_sell += 1.5
            if vol_spike_flag:
                base_score_sell += 1

            final_score_buy = base_score_buy + score_mod_buy
            final_score_sell = base_score_sell + score_mod_sell

            if final_score_buy >= 5:
                buy_candidates.append({
                    "symbol": sym, "score": round(final_score_buy, 2),
                    "rf_prox": round(rf_prox*100, 3),
                    "liquidity": liquidity_ctx, "zone": zone_ctx,
                    "structure": structure_ctx, "rejection": rejection_buy,
                    "volume_spike": vol_spike_flag, "location": location,
                    "smart_money": {
                        "bias": smart_money["institutional_bias"],
                        "bias_detailed": smart_money.get("institutional_bias_detailed", "NEUTRAL"),
                        "dominant": smart_money["smart_money_dominant"],
                        "distribution_risk": round(smart_money["distribution_risk"], 1),
                        "accumulation": round(smart_money["accumulation_strength"], 1)
                    },
                    "momentum": {
                        "expansion": momentum["trend_expansion"],
                        "decay": momentum["momentum_decay"],
                        "exhaustion_risk": round(momentum["exhaustion_risk"], 1),
                        "greed": momentum["greed_state"]
                    }
                })
            if final_score_sell >= 5:
                sell_candidates.append({
                    "symbol": sym, "score": round(final_score_sell, 2),
                    "rf_prox": round(rf_prox*100, 3),
                    "liquidity": liquidity_ctx, "zone": zone_ctx,
                    "structure": structure_ctx, "rejection": rejection_sell,
                    "volume_spike": vol_spike_flag,
                    "location": compute_location(df, price, "SELL"),
                    "smart_money": {
                        "bias": smart_money["institutional_bias"],
                        "bias_detailed": smart_money.get("institutional_bias_detailed", "NEUTRAL"),
                        "dominant": smart_money["smart_money_dominant"],
                        "distribution_risk": round(smart_money["distribution_risk"], 1),
                        "accumulation": round(smart_money["accumulation_strength"], 1)
                    },
                    "momentum": {
                        "expansion": momentum["trend_expansion"],
                        "decay": momentum["momentum_decay"],
                        "exhaustion_risk": round(momentum["exhaustion_risk"], 1),
                        "greed": momentum["greed_state"]
                    }
                })
        except Exception as e:
            continue
    buy_sorted = sorted(buy_candidates, key=lambda x: x["score"], reverse=True)[:10]
    sell_sorted = sorted(sell_candidates, key=lambda x: x["score"], reverse=True)[:10]
    return buy_sorted, sell_sorted

# ========== INSTITUTIONAL LIQUIDITY NARRATIVE ENGINE ==========
def equal_levels_points(highs, lows, tolerance=0.002):
    eq_highs = []
    eq_lows = []
    def cluster(points, tol):
        if not points:
            return []
        points = sorted(points)
        clusters = []
        current = [points[0]]
        for p in points[1:]:
            if abs(p - current[-1]) / current[-1] < tol:
                current.append(p)
            else:
                clusters.append(current)
                current = [p]
        clusters.append(current)
        return clusters
    high_clusters = cluster(highs, tolerance)
    low_clusters = cluster(lows, tolerance)
    for cl in high_clusters:
        if len(cl) >= 2:
            eq_highs.extend([sum(cl)/len(cl)])
    for cl in low_clusters:
        if len(cl) >= 2:
            eq_lows.extend([sum(cl)/len(cl)])
    return eq_highs, eq_lows

def find_swing_points(df, window=3):
    highs = df['high'].values
    lows = df['low'].values
    swing_highs = []
    swing_lows = []
    for i in range(window, len(df)-window):
        if highs[i] == max(highs[i-window:i+window+1]):
            swing_highs.append(highs[i])
        if lows[i] == min(lows[i-window:i+window+1]):
            swing_lows.append(lows[i])
    return swing_highs, swing_lows

def detect_equal_highs_lows(df, lookback=50):
    sub = df.iloc[-lookback:]
    sh, sl = find_swing_points(sub, window=2)
    return equal_levels_points(sh, sl)

def detect_order_block(df, side, lookback=4):
    if len(df) < lookback+2:
        return None
    atr = compute_atr(df).iloc[-1]
    move = abs(df['close'].iloc[-1] - df['close'].iloc[-2])
    if move < atr * 1.2:
        return None
    for i in range(2, lookback+2):
        if i >= len(df):
            break
        candle = df.iloc[-i]
        if side == "BUY" and candle['close'] < candle['open']:
            return {"low": candle['low'], "high": candle['high'], "idx": -i}
        elif side == "SELL" and candle['close'] > candle['open']:
            return {"low": candle['low'], "high": candle['high'], "idx": -i}
    return None

def detect_fvg(df, threshold=0.001):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if curr['low'] > prev['high'] * (1+threshold):
        return ("bullish", prev['high'], curr['low'])
    elif curr['high'] < prev['low'] * (1-threshold):
        return ("bearish", curr['high'], prev['low'])
    return None

def evaluate_liquidity_narrative(df, ob, atr, side):
    narrative = {"sweep": False, "choch_bos": False, "retest": False, "rejection": False,
                 "displacement": False, "rf_alignment": False, "volume_confirmation": False}
    price = df['close'].iloc[-1]
    pools = build_liquidity_pools(df)
    swept_h, swept_l = detect_sweep(df, pools)
    if side == "BUY" and swept_l:
        narrative["sweep"] = True
    elif side == "SELL" and swept_h:
        narrative["sweep"] = True
    bos_up, bos_down = detect_bos(df)
    struct_shift = detect_structure_shift(df)
    choch = struct_shift is not None
    if side == "BUY" and (bos_up or (choch and struct_shift == "bullish_shift")):
        narrative["choch_bos"] = True
    elif side == "SELL" and (bos_down or (choch and struct_shift == "bearish_shift")):
        narrative["choch_bos"] = True
    zones = get_smart_zones(df.symbol if hasattr(df, 'symbol') else "unknown", df, ob)
    required_zone = None
    if zones:
        if side == "BUY" and zones["buy_zones"]:
            required_zone = zones["buy_zones"][0]
        elif side == "SELL" and zones["sell_zones"]:
            required_zone = zones["sell_zones"][0]
    if required_zone:
        dist = abs(price - required_zone["price"]) / price
        if dist < 0.003:
            narrative["retest"] = True
    if candle_rejection(df, side):
        narrative["rejection"] = True
    vol_state = classify_volume(df)
    if detect_displacement(df, side, atr, vol_state):
        narrative["displacement"] = True
    if vol_state in ("expansion", "spike"):
        narrative["volume_confirmation"] = True
    rf = RFEngine(20, 3.5).compute(df)
    if rf["signal"] == side and abs(rf["distance"]) < 0.003:
        narrative["rf_alignment"] = True
    score = 0
    if narrative["sweep"]: score += 2
    if narrative["choch_bos"]: score += 2
    if narrative["retest"]: score += 2
    if narrative["rejection"]: score += 1.5
    if narrative["displacement"]: score += 1.5
    if narrative["volume_confirmation"]: score += 1
    if narrative["rf_alignment"]: score += 2
    return narrative, score

def smart_opportunity_selection():
    candidates = []
    for c in MEMORY.get("scanner_v2_buy", [])[:5]:
        candidates.append({"symbol": c["symbol"], "side": "BUY", "score": c["score"], "source": "v2"})
    for c in MEMORY.get("scanner_v2_sell", [])[:5]:
        candidates.append({"symbol": c["symbol"], "side": "SELL", "score": c["score"], "source": "v2"})
    for c in MEMORY.get("rf_watchlist", [])[:10]:
        if c.get("rf_signal") in ("BUY", "SELL"):
            candidates.append({"symbol": c["symbol"], "side": c["rf_signal"], "score": c["score"], "source": "rf"})
    seen = {}
    for cand in candidates:
        sym = cand["symbol"]
        if sym not in seen or cand["score"] > seen[sym]["score"]:
            seen[sym] = cand
    candidates = list(seen.values())
    best_setup = None
    best_score = -1
    for cand in candidates[:15]:
        try:
            sym = cand["symbol"]
            side = cand["side"]
            df = get_ohlcv_safe(sym, 100)
            if df is None or not validate_dataframe(df, 80):
                continue
            df.symbol = sym
            ob = get_orderbook_cached(sym, limit=10)
            atr = compute_atr(df).iloc[-1] if len(df) > 14 else df['close'].iloc[-1] * 0.01
            narrative, nscore = evaluate_liquidity_narrative(df, ob, atr, side)
            smart_money = SmartMoneyEngine.analyze_smart_money(df)
            momentum = MomentumFlowEngine.analyze_momentum_flow(df)
            total_confidence_adjust = 0
            if smart_money["smart_money_dominant"] and smart_money["institutional_bias"] == side:
                total_confidence_adjust += 15
            if momentum["trend_expansion"] and momentum["flow_bias"] == side:
                total_confidence_adjust += 10
            if smart_money["distribution_risk"] > 70:
                total_confidence_adjust -= 15
            if momentum["momentum_decay"]:
                total_confidence_adjust -= 12
            if momentum["exhaustion_risk"] > 70:
                total_confidence_adjust -= 10
            adjusted_nscore = nscore + (total_confidence_adjust / 10)
            record_watchlist_entry(sym, side, narrative, adjusted_nscore, smart_money, momentum)
            if adjusted_nscore < 7:
                continue
            zones = get_smart_zones(sym, df, ob)
            zone_strength = 0
            if side == "BUY" and zones["buy_zones"]:
                zone_strength = zones["buy_zones"][0]["strength"]
            elif side == "SELL" and zones["sell_zones"]:
                zone_strength = zones["sell_zones"][0]["strength"]
            total = adjusted_nscore + zone_strength * 0.5
            if total > best_score:
                best_score = total
                best_setup = (sym, side, total, narrative, zones, df, ob, atr)
        except Exception:
            continue
    if best_setup and best_score >= 9:
        sym, side, score, narrative, zones, df, ob, atr = best_setup
        price = df['close'].iloc[-1]
        leg_class = "REVERSAL"
        sl, tp1, tp2 = compute_sl_tp(price, side, leg_class, atr, df)
        reason_str = f"INST_SWEEP+CHOCH+RETEST | nscore={score:.1f}"
        ok = execute_entry(side, sym, price, sl, tp1, tp2, score, reason_str, atr,
                           trade_type="INSTITUTIONAL", entry_type="NARRATIVE", classification="SNIPER")
        if ok:
            return True
    return False

def record_watchlist_entry(symbol, side, narrative, score, smart_money=None, momentum=None):
    now = time.time()
    state = "DETECTED"
    if narrative.get("retest"):
        state = "RETEST"
    if narrative.get("rejection"):
        state = "REJECTION"
    if narrative.get("displacement"):
        state = "DISPLACEMENT"
    if narrative.get("sweep") and narrative.get("choch_bos") and narrative.get("retest") and narrative.get("rejection"):
        state = "CONFIRMED"
    reasons_list = []
    if narrative["sweep"]: reasons_list.append("Sweep")
    if narrative["choch_bos"]: reasons_list.append("CHoCH/BOS")
    if narrative["retest"]: reasons_list.append("ZONE_RETEST")
    if narrative["rejection"]: reasons_list.append("OB")
    if narrative["displacement"]: reasons_list.append("Displacement")
    if narrative["volume_confirmation"]: reasons_list.append("Volume")
    if narrative["rf_alignment"]: reasons_list.append("RF")
    trade_type = "REVERSAL" if (narrative["sweep"] or narrative["retest"]) else "TREND"
    strength = "WEAK"
    if score >= 7:
        strength = "STRONG"
    elif score >= 4:
        strength = "MEDIUM"
    entry = {
        "symbol": symbol, "side": side, "score": round(score, 2),
        "state": state, "reasons": reasons_list,
        "trade_type": trade_type, "strength": strength,
        "last_update": now
    }
    if smart_money:
        entry["smart_money_bias"] = smart_money.get("institutional_bias", "NEUTRAL")
        entry["smart_money_bias_detailed"] = smart_money.get("institutional_bias_detailed", "NEUTRAL")
        entry["distribution_risk"] = round(smart_money.get("distribution_risk", 0), 1)
        entry["accumulation"] = round(smart_money.get("accumulation_strength", 0), 1)
    if momentum:
        entry["momentum_expansion"] = momentum.get("trend_expansion", False)
        entry["momentum_decay"] = momentum.get("momentum_decay", False)
        entry["exhaustion_risk"] = round(momentum.get("exhaustion_risk", 0), 1)
        entry["continuation_strength"] = round(momentum.get("continuation_strength", 0), 1)
    if "watchlist" not in MEMORY:
        MEMORY["watchlist"] = {}
    MEMORY["watchlist"][symbol] = entry

def cleanup_watchlist(ttl=300):
    now = time.time()
    if "watchlist" not in MEMORY:
        return
    expired = [sym for sym, v in MEMORY["watchlist"].items() if now - v["last_update"] > ttl]
    for sym in expired:
        del MEMORY["watchlist"][sym]

# ========== VWAP ENGINE ==========
def compute_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    cum_vol = df['volume'].cumsum()
    cum_tp_vol = (tp * df['volume']).cumsum()
    vwap = cum_tp_vol / cum_vol
    return vwap

def vwap_features(df):
    vwap = compute_vwap(df)
    price = df['close'].iloc[-1]
    distance = (price - vwap.iloc[-1]) / vwap.iloc[-1] if vwap.iloc[-1] != 0 else 0.0
    slope = vwap.iloc[-1] - vwap.iloc[-5] if len(vwap) >= 5 else 0.0
    return {"vwap": vwap.iloc[-1], "distance": distance, "slope": slope}

def detect_exhaustion_zone(df):
    atr = compute_atr(df).iloc[-1]
    rsi = compute_rsi(df).iloc[-1]
    vw = vwap_features(df)
    last = df.iloc[-1]
    impulse = (last['high'] - last['low']) >= 1.4 * atr if atr > 0 else False
    stretched = abs(vw["distance"]) >= 0.012
    rsi_extreme = rsi >= 70 or rsi <= 30
    if not (impulse and stretched and rsi_extreme):
        return False, None, None
    if rsi >= 70 and vw["distance"] > 0.012:
        return True, last['high'], "TOP"
    elif rsi <= 30 and vw["distance"] < -0.012:
        return True, last['low'], "BOTTOM"
    return False, None, None

def detect_reset(df, zone_price, zone_type):
    last_close = df['close'].iloc[-1]
    if zone_type == "TOP":
        drop = (zone_price - last_close) / zone_price
        return drop >= 0.003
    else:
        rise = (last_close - zone_price) / zone_price
        return rise >= 0.003

def confirm_reversal(df, ob, zone_type):
    last = df.iloc[-1]
    wick = (last['high'] - max(last['open'], last['close'])) if zone_type == "TOP" else (min(last['open'], last['close']) - last['low'])
    body = abs(last['close'] - last['open'])
    wick_reject = wick > body * 1.5 if body > 0 else False
    macd_hist = compute_macd(df)[2]
    macd_flip = macd_first_flip(macd_hist)
    flow = flow_engine(df)
    flow_agree = (zone_type == "TOP" and flow == "aggressive_sell") or (zone_type == "BOTTOM" and flow == "aggressive_buy")
    obi = orderbook_imbalance(ob)
    obi_agree = (zone_type == "TOP" and obi < -0.2) or (zone_type == "BOTTOM" and obi > 0.2)
    score = sum([wick_reject, macd_flip, flow_agree, obi_agree])
    return score >= 2

def detect_stop_hunt(df):
    pools = build_liquidity_pools(df)
    swept_high, swept_low = detect_sweep(df, pools)
    last = df.iloc[-1]
    inside = last['close'] < last['high'] and last['close'] > last['low']
    reclaim = (swept_high and last['close'] < last['high']) or (swept_low and last['close'] > last['low'])
    volume_ok = volume_pressure_real(df)
    if swept_high and reclaim and volume_ok:
        return True, "SELL"
    elif swept_low and reclaim and volume_ok:
        return True, "BUY"
    return False, None

def choose_mode(df):
    adx = compute_adx(df).iloc[-1] if len(df) >= 20 else 20
    return "TREND" if adx >= 20 else "RANGE"

def smart_decision(df, ob, symbol):
    mode = choose_mode(df)
    is_hunt, hunt_side = detect_stop_hunt(df)
    if is_hunt and hunt_side:
        return "STOP_HUNT", hunt_side, {"mode": mode}
    is_zone, zone_price, zone_type = detect_exhaustion_zone(df)
    if is_zone and zone_price is not None:
        STATE["zone"][symbol] = (zone_price, zone_type)
    if symbol in STATE["zone"]:
        zone_price, zone_type = STATE["zone"][symbol]
        if detect_reset(df, zone_price, zone_type) and confirm_reversal(df, ob, zone_type):
            side = "SELL" if zone_type == "TOP" else "BUY"
            return "EXHAUSTION_ENTRY", side, {"mode": mode, "zone": zone_price}
    return None, None, None

# ========== OPPOSING ZONE SMART EXIT ENGINE ==========
def find_nearest_opposing_zone(df, side):
    supports, resistances = get_clustered_zones(df, lookback=80, cluster_pct=0.002)
    price = df['close'].iloc[-1]
    if side == "BUY":
        valid = [r for r in resistances if r > price]
        if valid:
            nearest = min(valid, key=lambda x: x - price)
            return nearest, "RESISTANCE"
    else:
        valid = [s for s in supports if s < price]
        if valid:
            nearest = max(valid, key=lambda x: x)
            return nearest, "SUPPORT"
    return None, None

def compute_opposing_zone_strength(df, ob, atr, side, zone_price, zone_type):
    score = 0
    price = df['close'].iloc[-1]
    dist_pct = abs(price - zone_price) / price
    if dist_pct <= 0.002:
        score += 2
    elif dist_pct <= 0.005:
        score += 1
    last = df.iloc[-1]
    body = abs(last['close'] - last['open'])
    range_ = last['high'] - last['low']
    if range_ > 0:
        if side == "BUY":
            upper_wick = last['high'] - max(last['open'], last['close'])
            if upper_wick > body * 1.5 and price >= zone_price - 0.002*price:
                score += 2
        else:
            lower_wick = min(last['open'], last['close']) - last['low']
            if lower_wick > body * 1.5 and price <= zone_price + 0.002*price:
                score += 2
    vol_state = classify_volume(df)
    if vol_state == "exhaustion":
        score += 1
    elif vol_state == "neutral" and df['volume'].iloc[-1] < df['volume'].rolling(20).mean().iloc[-1] * 0.8:
        score += 1
    if side == "BUY":
        if last['high'] > zone_price and last['close'] < zone_price:
            score += 2
    else:
        if last['low'] < zone_price and last['close'] > zone_price:
            score += 2
    obi = orderbook_imbalance(ob)
    if side == "BUY" and obi < -0.15:
        score += 2
    elif side == "SELL" and obi > 0.15:
        score += 2
    adx_series = compute_adx(df)
    if len(adx_series) >= 2:
        if adx_series.iloc[-1] < adx_series.iloc[-2]:
            score += 1
    return score

def opposing_zone_smart_exit(df, ob, atr, side, entry_price, current_price, state):
    zone_price, zone_type = find_nearest_opposing_zone(df, side)
    if zone_price is None:
        return "HOLD", None
    strength = compute_opposing_zone_strength(df, ob, atr, side, zone_price, zone_type)
    if strength >= 6:
        if not state.get("smart_exit_triggered"):
            return "EXIT", None
    elif strength >= 4:
        if not state.get("smart_partial_done") and not state.get("smart_exit_triggered"):
            return "PARTIAL", None
    elif strength >= 2:
        if not state.get("smart_tightened"):
            return "TIGHTEN", 0.8
    return "HOLD", None

# ========== NARRATIVE + CONTEXT ENGINE v1 ==========
def get_di_components(df, period=14):
    if df is None or len(df) < period*2:
        return None, None, None, 0.0
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = rma(tr, period)
    atr = atr.clip(lower=1e-9)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    plus_di = 100 * rma(plus_dm, period) / (atr + 1e-9)
    minus_di = 100 * rma(minus_dm, period) / (atr + 1e-9)
    adx_series = compute_adx(df, period)
    adx_current = adx_series.iloc[-1] if len(adx_series) > 0 else 20.0
    adx_prev = adx_series.iloc[-2] if len(adx_series) > 1 else adx_current
    adx_slope = adx_current - adx_prev
    return plus_di.iloc[-1], minus_di.iloc[-1], adx_current, adx_slope

def get_vwap_narrative(df):
    vwap = compute_vwap(df)
    price = df['close'].iloc[-1]
    vwap_last = vwap.iloc[-1]
    vwap_prev = vwap.iloc[-2] if len(vwap) > 1 else vwap_last
    distance = (price - vwap_last) / vwap_last if vwap_last != 0 else 0.0
    above = price > vwap_last
    below = price < vwap_last
    prev_above = df['close'].iloc[-2] > vwap_prev if len(df) > 1 else above
    reclaim = (not prev_above) and above
    reject = prev_above and (not above)
    return {
        "vwap": vwap_last, "distance": distance,
        "above": above, "below": below,
        "reclaim": reclaim, "reject": reject,
        "slope": vwap_last - vwap_prev
    }

def compute_enhanced_zone_strength(df, level, zone_type, atr, ob, sweep_detected=False):
    price = df['close'].iloc[-1]
    touches = 0
    rejection_count = 0
    volume_at_touches = []
    for i in range(max(0, len(df)-60), len(df)):
        candle_high = df['high'].iloc[i]
        candle_low = df['low'].iloc[i]
        if zone_type == "support":
            if abs(candle_low - level) < atr * 0.5:
                touches += 1
                if i < len(df)-1:
                    next_close = df['close'].iloc[i+1]
                    if next_close > df['close'].iloc[i]:
                        rejection_count += 1
                        volume_at_touches.append(df['volume'].iloc[i])
        else:
            if abs(candle_high - level) < atr * 0.5:
                touches += 1
                if i < len(df)-1:
                    next_close = df['close'].iloc[i+1]
                    if next_close < df['close'].iloc[i]:
                        rejection_count += 1
                        volume_at_touches.append(df['volume'].iloc[i])
    vol_score = 0.0
    if volume_at_touches:
        avg_vol_touch = sum(volume_at_touches) / len(volume_at_touches)
        avg_vol_overall = df['volume'].iloc[-60:].mean()
        if avg_vol_overall > 0:
            vol_score = min(3.0, avg_vol_touch / avg_vol_overall)
    strength = touches * 1.5 + rejection_count * 2.0 + vol_score
    if sweep_detected:
        strength += 2.0
    last = df.iloc[-1]
    body, range_, upper_wick, lower_wick = candle_metrics(last)
    if zone_type == "support" and lower_wick > body * 1.5 and abs(last['low'] - level) < atr:
        strength += 2.0
    elif zone_type == "resistance" and upper_wick > body * 1.5 and abs(last['high'] - level) < atr:
        strength += 2.0
    return min(10.0, strength)

def classify_market_narrative(df, ob, atr, side, rf_signal):
    reasons = []
    score = 0.0
    plus_di, minus_di, adx, adx_slope = get_di_components(df)
    if plus_di is not None:
        if side == "BUY" and plus_di > minus_di:
            score += 2.0
            reasons.append("DI+ dominance")
        elif side == "SELL" and minus_di > plus_di:
            score += 2.0
            reasons.append("DI- dominance")
        elif abs(plus_di - minus_di) < 5:
            reasons.append("DI tangled")
    if adx_slope > 1.5:
        score += 1.5
        reasons.append(f"ADX rising ({adx_slope:.1f})")
    elif adx_slope < -1.5:
        score -= 1.0
        reasons.append("ADX falling")
    vwap_n = get_vwap_narrative(df)
    if side == "BUY":
        if vwap_n["above"]:
            score += 1.5
            reasons.append("VWAP above")
        elif vwap_n["reclaim"]:
            score += 2.0
            reasons.append("VWAP reclaim")
    else:
        if vwap_n["below"]:
            score += 1.5
            reasons.append("VWAP below")
        elif vwap_n["reject"]:
            score += 2.0
            reasons.append("VWAP reject")
    pools = build_liquidity_pools(df)
    swept_h, swept_l = detect_sweep(df, pools)
    sweep_detected = (side == "BUY" and swept_l) or (side == "SELL" and swept_h)
    if sweep_detected:
        score += 2.5
        reasons.append("Liquidity sweep")
    supports, resistances = get_clustered_zones(df, lookback=80, cluster_pct=0.002)
    zone_strength = 0.0
    if side == "BUY" and supports:
        nearest_sup = max([s for s in supports if s <= df['close'].iloc[-1]], default=None)
        if nearest_sup:
            zone_strength = compute_enhanced_zone_strength(df, nearest_sup, "support", atr, ob, sweep_detected)
            score += zone_strength * 0.5
            reasons.append(f"Zone strength {zone_strength:.1f}")
    elif side == "SELL" and resistances:
        nearest_res = min([r for r in resistances if r >= df['close'].iloc[-1]], default=None)
        if nearest_res:
            zone_strength = compute_enhanced_zone_strength(df, nearest_res, "resistance", atr, ob, sweep_detected)
            score += zone_strength * 0.5
            reasons.append(f"Zone strength {zone_strength:.1f}")
    bos_up, bos_down = detect_bos(df)
    struct_shift = detect_structure_shift(df)
    if (side == "BUY" and (bos_up or struct_shift == "bullish_shift")):
        score += 2.0
        reasons.append("Bullish structure")
    elif (side == "SELL" and (bos_down or struct_shift == "bearish_shift")):
        score += 2.0
        reasons.append("Bearish structure")
    vol_state = classify_volume(df)
    if vol_state in ("expansion", "spike"):
        score += 1.5
        reasons.append("Volume expansion")
    elif vol_state == "exhaustion":
        score -= 1.0
        reasons.append("Volume exhaustion")
    if candle_rejection(df, side):
        score += 1.5
        reasons.append("Rejection candle")
    if detect_displacement(df, side, atr, vol_state, body_atr_threshold=0.8, volume_expansion_required=False):
        score += 1.5
        reasons.append("Displacement")
    if rf_signal == side:
        score += 1.5
        reasons.append("RF aligned")
    if adx is not None and adx < 18 and plus_di is not None and abs(plus_di - minus_di) < 6:
        score = 0
        reasons = ["CHOP market (ADX<18 + DI tangled)"]
    if score >= 9.0:
        classification = "REVERSAL_SNIPER" if (sweep_detected or zone_strength > 5) else "TREND_CONTINUATION"
        confidence = "HIGH"
    elif score >= 7.0:
        classification = "TREND_CONTINUATION" if (bos_up or bos_down or struct_shift) else "ACCUMULATION_LONG" if side == "BUY" else "DISTRIBUTION_SHORT"
        confidence = "MEDIUM"
    elif score >= 5.0:
        classification = "FAKE_BREAKOUT" if not sweep_detected else "LOW_CONFIDENCE"
        confidence = "LOW"
    else:
        classification = "CHOP_NO_TRADE"
        confidence = "NO_TRADE"
    return {
        "classification": classification, "confidence": confidence,
        "narrative_score": round(score, 2), "reasons": reasons,
        "sweep": sweep_detected, "zone_strength": zone_strength,
        "di_dominance": ("BUY" if plus_di > minus_di else "SELL") if plus_di is not None else "NEUTRAL",
        "adx_slope": adx_slope,
        "vwap_reclaim": vwap_n["reclaim"],
        "vwap_reject": vwap_n["reject"]
    }

def detect_market_regime(df):
    if len(df) < 50:
        return "RANGE"
    try:
        adx = compute_adx(df).iloc[-1]
        plus_di, minus_di, _, _ = get_di_components(df)
        vwap_n = get_vwap_narrative(df)
        atr = compute_atr(df).iloc[-1]
        atr_avg = compute_atr(df).rolling(20).mean().iloc[-1] if len(compute_atr(df))>=20 else atr
        atr_ratio = atr / atr_avg if atr_avg else 1.0
        ema20 = ema(df['close'], 20).iloc[-1]
        ema50 = ema(df['close'], 50).iloc[-1] if len(df)>=50 else ema20
        price = df['close'].iloc[-1]
        di_delta = abs(plus_di - minus_di)
        if adx < 18 and di_delta < 6:
            return "CHOP"
        if adx > 20 and di_delta > 5:
            struct = detect_structure_shift(df)
            bullish_aligned = plus_di > minus_di and ema20 > ema50 and price > ema20
            bearish_aligned = minus_di > plus_di and ema20 < ema50 and price < ema20
            if bullish_aligned or bearish_aligned:
                return "TREND"
            if struct == "bullish_shift" and plus_di > minus_di:
                return "TREND"
            if struct == "bearish_shift" and minus_di > plus_di:
                return "TREND"
        if adx > 20 and atr_ratio > 1.4:
            return "EXPANSION"
        if atr_ratio < 0.7 and adx < 25:
            return "COMPRESSION"
        return "RANGE"
    except:
        return "RANGE"

def get_trend_direction(df):
    try:
        plus_di, minus_di, _, _ = get_di_components(df)
        ema20 = ema(df['close'], 20).iloc[-1]
        ema50 = ema(df['close'], 50).iloc[-1] if len(df)>=50 else ema20
        price = df['close'].iloc[-1]
        struct = detect_structure_shift(df)
        if (plus_di > minus_di and ema20 > ema50 and price > ema20) or struct == "bullish_shift":
            return "BULLISH"
        elif (minus_di > plus_di and ema20 < ema50 and price < ema20) or struct == "bearish_shift":
            return "BEARISH"
        return "NEUTRAL"
    except:
        return "NEUTRAL"

def adjust_narrative_confidence(narrative, regime, side, trend_direction):
    orig_conf = narrative["confidence"]
    score = narrative["narrative_score"]
    side_aligned = False
    if (trend_direction == "BULLISH" and side == "BUY") or (trend_direction == "BEARISH" and side == "SELL"):
        side_aligned = True
    final_conf = orig_conf
    final_class = narrative["classification"]
    if regime == "CHOP":
        return "NO_TRADE", "CHOP_NO_TRADE"
    if orig_conf == "NO_TRADE" or score < 5.0:
        return "NO_TRADE", "CHOP_NO_TRADE"
    if regime == "TREND":
        if side_aligned:
            if orig_conf == "HIGH":
                final_conf = "HIGH"
                final_class = "SNIPER"
            elif orig_conf == "MEDIUM":
                final_conf = "MEDIUM"
                final_class = "TREND"
            elif orig_conf == "LOW":
                if score >= 5.0:
                    final_conf = "MEDIUM"
                    final_class = "TREND"
                else:
                    final_conf = "NO_TRADE"
                    final_class = "NO_TRADE"
        else:
            if orig_conf == "HIGH":
                final_conf = "HIGH"
                final_class = "SNIPER"
            else:
                final_conf = "NO_TRADE"
                final_class = "NO_TRADE"
    elif regime in ("EXPANSION", "COMPRESSION"):
        if orig_conf == "HIGH":
            final_conf = "HIGH"
            final_class = "SNIPER"
        else:
            final_conf = "NO_TRADE"
            final_class = "NO_TRADE"
    else:
        if orig_conf == "HIGH":
            final_conf = "HIGH"
            final_class = "SNIPER"
        elif orig_conf == "MEDIUM" and side_aligned:
            final_conf = "NO_TRADE"
            final_class = "NO_TRADE"
        else:
            final_conf = "NO_TRADE"
            final_class = "NO_TRADE"
    return final_conf, final_class

def evaluate_with_narrative(symbol, side, price, atr_val, df, ob, rf_signal, existing_score=0):
    regime = detect_market_regime(df)
    trend_dir = get_trend_direction(df)
    narrative = classify_market_narrative(df, ob, atr_val, side, rf_signal)
    final_conf, final_class = adjust_narrative_confidence(narrative, regime, side, trend_dir)
    narrative["confidence"] = final_conf
    narrative["classification"] = final_class
    narrative["regime"] = regime
    MEMORY[f"last_narrative_{symbol}"] = {**narrative, "timestamp": time.time(), "side": side}
    should_enter = final_conf in ("HIGH", "MEDIUM")
    if not should_enter:
        reason = f"{final_class} ({final_conf}) Regime={regime} Score={narrative['narrative_score']:.1f}"
        MEMORY.setdefault("no_entry_feed", []).append({
            "time": time.time(), "symbol": symbol, "side": side,
            "reason": reason, "score": narrative["narrative_score"]
        })
        if len(MEMORY["no_entry_feed"]) > 20:
            MEMORY["no_entry_feed"] = MEMORY["no_entry_feed"][-20:]
        return False, None, narrative
    STATE["narrative_classification"] = final_class
    STATE["narrative_confidence"] = narrative["narrative_score"]
    STATE["confidence_level"] = final_conf
    return True, final_class, narrative

def narrative_debug():
    debug_data = []
    for key, val in MEMORY.items():
        if key.startswith("last_narrative_"):
            debug_data.append({
                "symbol": key.replace("last_narrative_", ""),
                "side": val.get("side"),
                "classification": val.get("classification"),
                "confidence": val.get("confidence"),
                "score": val.get("narrative_score"),
                "reasons": val.get("reasons"),
                "timestamp": val.get("timestamp")
            })
    radar_candidates = MEMORY.get("radar_top5", [])
    for cand in radar_candidates:
        sym = cand["symbol"]
        if not any(d["symbol"] == sym for d in debug_data):
            df = get_ohlcv_safe(sym, 100)
            if df is not None:
                ob = get_orderbook_cached(sym, 10)
                atr = compute_atr(df).iloc[-1] if len(df) > 14 else df['close'].iloc[-1] * 0.01
                side = "BUY"
                narrative = classify_market_narrative(df, ob, atr, side, None)
                debug_data.append({
                    "symbol": sym, "side": "analysis",
                    "classification": narrative["classification"],
                    "confidence": narrative["confidence"],
                    "score": narrative["narrative_score"],
                    "reasons": narrative["reasons"][:5],
                    "timestamp": time.time()
                })
    return jsonify({"narrative_debug": debug_data})

# ========== SMART INSTITUTIONAL ENTRY ENGINE ==========
def check_institutional_entry(symbol, side, df, ob, atr, price):
    intent_score, intent_status, intent_details = InstitutionalIntentEngine.detect(df, ob, symbol)
    if intent_score < 75:
        log_execution(f"[INTENT] {symbol} {side} intent score {intent_score} < 75 – abort.", "WARN")
        return False, None, f"Intent score {intent_score}"
    MEMORY[f"intent_{symbol}"] = intent_details
    log_execution(f"[INTENT] {symbol} {side} score={intent_score} status={intent_status}", "SUCCESS")

    reasons = []
    pools = build_liquidity_pools(df)
    swept_high, swept_low = detect_sweep(df, pools)
    sweep_ok = (side == "BUY" and swept_low) or (side == "SELL" and swept_high)
    if not sweep_ok:
        return False, None, "No liquidity sweep"
    reasons.append("Sweep")
    zones = get_smart_zones(symbol, df, ob)
    zone_ok = False
    zone_price = None
    if side == "BUY":
        if zones["buy_zones"] and zones["buy_zones"][0]["strength"] >= 5:
            zone_price = zones["buy_zones"][0]["price"]
            if abs(price - zone_price) / price < 0.003:
                zone_ok = True
                reasons.append(f"Buy zone {zone_price:.4f}")
    else:
        if zones["sell_zones"] and zones["sell_zones"][0]["strength"] >= 5:
            zone_price = zones["sell_zones"][0]["price"]
            if abs(price - zone_price) / price < 0.003:
                zone_ok = True
                reasons.append(f"Sell zone {zone_price:.4f}")
    if not zone_ok:
        fvg = detect_fvg(df)
        if side == "BUY" and fvg and fvg[0] == "bullish":
            if price >= fvg[1] and price <= fvg[2]:
                zone_ok = True
                reasons.append("Bullish FVG")
        elif side == "SELL" and fvg and fvg[0] == "bearish":
            if price >= fvg[1] and price <= fvg[2]:
                zone_ok = True
                reasons.append("Bearish FVG")
    if not zone_ok:
        ob_level = detect_order_block(df, side)
        if side == "BUY" and ob_level:
            if abs(price - ob_level["low"]) / price < 0.003:
                zone_ok = True
                reasons.append("Bullish OB")
        elif side == "SELL" and ob_level:
            if abs(price - ob_level["high"]) / price < 0.003:
                zone_ok = True
                reasons.append("Bearish OB")
    if not zone_ok:
        return False, None, "No strong zone tap"
    struct_shift = detect_structure_shift(df)
    bos_up, bos_down = detect_bos(df)
    choch_ok = False
    if side == "BUY" and (struct_shift == "bullish_shift" or bos_up):
        choch_ok = True
        reasons.append("Bullish MSS/CHoCH")
    elif side == "SELL" and (struct_shift == "bearish_shift" or bos_down):
        choch_ok = True
        reasons.append("Bearish MSS/CHoCH")
    if sweep_ok and not choch_ok:
        return False, None, "Reversal requires MSS/CHoCH confirmation"
    elif not sweep_ok and not choch_ok:
        reasons.append("No MSS/CHoCH")
    rejection_ok = candle_rejection(df, side)
    vol_state = classify_volume(df)
    displacement_ok = detect_displacement(df, side, atr, vol_state, body_atr_threshold=0.8, volume_expansion_required=False)
    if not (rejection_ok or displacement_ok):
        return False, None, "No rejection/displacement candle"
    if rejection_ok:
        reasons.append("Rejection candle")
    if displacement_ok:
        reasons.append("Displacement")
    volume_ok = vol_state in ("expansion", "spike")
    if not volume_ok:
        return False, None, "No volume expansion"
    reasons.append(f"Volume {vol_state}")
    adx_series = compute_adx(df)
    if len(adx_series) < 3:
        return False, None, "Insufficient ADX data"
    adx_now = adx_series.iloc[-1]
    adx_prev = adx_series.iloc[-2]
    adx_slope = adx_now - adx_prev
    plus_di, minus_di, _, _ = get_di_components(df)
    di_spread = (plus_di - minus_di) if side == "BUY" else (minus_di - plus_di)
    if adx_now < 18:
        return False, None, f"ADX too low ({adx_now:.1f})"
    if adx_now > 50:
        if adx_slope > 0 and di_spread > 8:
            reasons.append(f"Strong trend ADX={adx_now:.1f}")
        else:
            return False, None, f"Exhaustion risk: ADX>50"
    elif adx_now > 35:
        if adx_slope > 0:
            reasons.append(f"Strong trend ADX={adx_now:.1f}")
        else:
            return False, None, f"ADX high but falling"
    else:
        if adx_slope > 0:
            reasons.append(f"Healthy ADX={adx_now:.1f} rising")
        else:
            return False, None, f"ADX not rising"
    rf = RFEngine(20, 3.5).compute(df)
    if rf["signal"] != side:
        return False, None, f"RF signal mismatch"
    if abs(rf["distance"]) > 0.003:
        return False, None, f"RF distance too far"
    reasons.append("RF aligned")
    if zone_price:
        move_from_zone = abs(price - zone_price) / zone_price * 100
        if move_from_zone > 0.5:
            return False, None, f"Price moved {move_from_zone:.2f}% from zone"
    last_candle = df.iloc[-1]
    candle_range_pct = (last_candle['high'] - last_candle['low']) / last_candle['close'] * 100
    if candle_range_pct > 1.5 * (atr / price * 100):
        return False, None, "Large displacement candle"
    reason_str = " | ".join(reasons)
    return True, "INSTITUTIONAL_SNIPER", reason_str

# ========== DECISION FUNCTIONS ==========
def decision_score_v1(df, ob, atr_val, side):
    es, reasons = early_score(df, ob, atr_val, side)
    ctx = detect_liquidity_context(df)
    scenario = "TREND"
    direction = side
    if ctx == "sell_side_taken" and side == "BUY":
        scenario = "REVERSAL"
    elif ctx == "buy_side_taken" and side == "SELL":
        scenario = "REVERSAL"
    total_score = min(10, max(0, es + 2 if scenario == "REVERSAL" else es))
    return total_score, scenario, direction, reasons

def apply_overrides_v1(df, atr_val, score):
    if is_late_move(df, atr_val):
        score = max(0, score - 3)
    return score

def decide_and_execute_v1(symbol, side, total_score, reasons, price, sl, tp1, tp2):
    if total_score < 5:
        return False
    df = get_ohlcv_safe(symbol, 100)
    if df is None:
        return False
    ob = get_orderbook_cached(symbol, 10)
    atr_val = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
    should_enter, classification, narrative = evaluate_with_narrative(symbol, side, price, atr_val, df, ob, side)
    if not should_enter:
        return False
    reason_str = f"DECISION_V1 score={total_score} | NARR={narrative['classification']}"
    return execute_entry(side, symbol, price, sl, tp1, tp2, total_score, reason_str, atr_val,
                         trade_type="DECISION_V1", entry_type="V1", classification=classification)

def decision_score(df, ob, atr_val, side):
    vol_state = classify_volume(df)
    scenario = advanced_detect_scenario(df, side, atr_val, vol_state)
    es, reasons = early_score(df, ob, atr_val, side)
    total = es
    if scenario == "TRAP_REVERSAL":
        total += 3
    elif scenario == "TREND_CONTINUATION":
        total += 2
    total = min(10, max(0, total))
    direction = side
    return total, scenario, direction, reasons

def near_key_zone(df, price):
    supports, resistances = get_clustered_zones(df, lookback=80, cluster_pct=0.002)
    for s in supports:
        if abs(price - s) / price < 0.003:
            return True
    for r in resistances:
        if abs(price - r) / price < 0.003:
            return True
    return False

# ========== MONITOR WATCHLIST ==========
def monitor_watchlist():
    watchlist = MEMORY.get("rf_watchlist", [])
    for c in watchlist:
        sym = c["symbol"]
        df = get_ohlcv_safe(sym, 150)
        if df is None or not validate_dataframe(df, 100):
            continue
        ob = get_orderbook_cached(sym, limit=10)
        if ob is not None:
            price = df['close'].iloc[-1]
            atr_val = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
            for side_try in ("BUY", "SELL"):
                should_enter, classification, reason_str = check_institutional_entry(sym, side_try, df, ob, atr_val, price)
                if should_enter:
                    should_enter_narr, final_class, narrative = evaluate_with_narrative(sym, side_try, price, atr_val, df, ob, side_try)
                    if not should_enter_narr:
                        continue
                    sl, tp1, tp2 = compute_sl_tp(price, side_try, "REVERSAL", atr_val, df)
                    ok = execute_entry(side_try, sym, price, sl, tp1, tp2, 85, reason_str, atr_val,
                                       trade_type="INSTITUTIONAL_V3", entry_type="SMART_EARLY", classification=classification)
                    if ok:
                        return True
            decision, dec_side, dec_info = smart_decision(df, ob, sym)
            if decision == "STOP_HUNT":
                price = df['close'].iloc[-1]
                atr_val = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
                should_enter, classification, narrative = evaluate_with_narrative(sym, dec_side, price, atr_val, df, ob, dec_side)
                if not should_enter:
                    continue
                sl, tp1, tp2 = compute_sl_tp(price, dec_side, "REVERSAL", atr_val, df)
                reason_str = f"SMART_STOP_HUNT | NARR={narrative['classification']}"
                ok = execute_entry(dec_side, sym, price, sl, tp1, tp2, 8, reason_str, atr_val,
                                   trade_type="SMART", entry_type="STOP_HUNT", classification=classification)
                if ok:
                    return True
            elif decision == "EXHAUSTION_ENTRY":
                price = df['close'].iloc[-1]
                atr_val = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
                should_enter, classification, narrative = evaluate_with_narrative(sym, dec_side, price, atr_val, df, ob, dec_side)
                if not should_enter:
                    continue
                sl, tp1, tp2 = compute_sl_tp(price, dec_side, "REVERSAL", atr_val, df)
                reason_str = f"SMART_EXHAUSTION | NARR={narrative['classification']}"
                ok = execute_entry(dec_side, sym, price, sl, tp1, tp2, 8, reason_str, atr_val,
                                   trade_type="SMART", entry_type="EXHAUSTION", classification=classification)
                if ok:
                    return True
        rf_engine = RFEngine(period=20, multiplier=3.5)
        rf = rf_engine.compute(df)
        if not rf["triggered"]:
            continue
        side = rf["signal"]
        if side is None:
            continue
        price = df['close'].iloc[-1]
        atr_val = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
        adx_series = compute_adx(df)
        adx_val = adx_series.iloc[-1] if adx_series is not None else 20.0
        volume_state = classify_volume(df)
        should_enter, classification, narrative = evaluate_with_narrative(sym, side, price, atr_val, df, ob, side)
        if not should_enter:
            continue
        if is_late_entry(df, side):
            continue
        ob_v1 = get_orderbook_cached(sym, limit=10)
        if ob_v1 is not None:
            total_v1, scn_v1, dir_v1, reasons_v1 = decision_score_v1(df, ob_v1, atr_val, side)
            total_v1 = apply_overrides_v1(df, atr_val, total_v1)
            if dir_v1 and total_v1 >= 5:
                sl_v1, tp1_v1, tp2_v1 = compute_sl_tp(price, dir_v1,
                                                       "REVERSAL" if scn_v1 in ("TRAP","REVERSAL") else "EARLY_TREND",
                                                       atr_val, df)
                ok = decide_and_execute_v1(sym, dir_v1, total_v1, reasons_v1, price, sl_v1, tp1_v1, tp2_v1)
                if ok:
                    return True
        ob = get_orderbook_cached(sym, limit=10)
        if ob is not None:
            total_score, scenario_name, scenario_dir, all_reasons = decision_score(df, ob, atr_val, side)
            if total_score >= 7:
                sl, tp1, tp2 = compute_sl_tp(price, scenario_dir, "REVERSAL" if scenario_name=="REVERSAL" else "EARLY_TREND", atr_val, df)
                reason_str = f"UNIFIED_SNIPER ({scenario_name}) score={total_score} | NARR={narrative['classification']}"
                ok = execute_entry(scenario_dir, sym, price, sl, tp1, tp2, total_score, reason_str, atr_val,
                                   trade_type="SCENARIO_ENGINE", entry_type="UNIFIED_SNIPER", classification=classification)
                if ok:
                    return True
            elif total_score >= 5:
                sl, tp1, tp2 = compute_sl_tp(price, scenario_dir, "EARLY_TREND", atr_val, df)
                reason_str = f"UNIFIED_EARLY ({scenario_name}) score={total_score} | NARR={narrative['classification']}"
                ok = execute_entry(scenario_dir, sym, price, sl, tp1, tp2, total_score, reason_str, atr_val,
                                   trade_type="SCENARIO_ENGINE", entry_type="UNIFIED_EARLY", classification=classification)
                if ok:
                    return True
        ob = get_orderbook_cached(sym, limit=10)
        if ob is None:
            continue
        else:
            early_score_val, early_reasons = early_score(df, ob, atr_val, side)
            if early_score_val >= 6:
                sl, tp1, tp2 = compute_sl_tp(price, side, "EARLY_TREND", atr_val, df)
                reason_str = f"EARLY_SNIPER | NARR={narrative['classification']}"
                ok = execute_entry(side, sym, price, sl, tp1, tp2, early_score_val, reason_str, atr_val,
                                   trade_type="EARLY_ENGINE", entry_type="EARLY_SNIPER", classification=classification)
                if ok:
                    return True
            elif early_score_val >= 4:
                sl, tp1, tp2 = compute_sl_tp(price, side, "EARLY_TREND", atr_val, df)
                reason_str = f"EARLY_ENTRY | NARR={narrative['classification']}"
                ok = execute_entry(side, sym, price, sl, tp1, tp2, early_score_val, reason_str, atr_val,
                                   trade_type="EARLY_ENGINE", entry_type="EARLY_ENTRY", classification=classification)
                if ok:
                    return True
        supports, resistances = get_clustered_zones(df, lookback=120, cluster_pct=0.002)
        location = detect_location(df, price, supports, resistances, threshold=0.003)
        if side == "BUY" and location != "LOW":
            continue
        if side == "SELL" and location != "HIGH":
            continue
        scenario = advanced_detect_scenario(df, side, atr_val, volume_state)
        if scenario == "NONE":
            continue
        decision, adv_class = advanced_decision_engine(scenario, adx_val, volume_state, location)
        if decision != "ENTER":
            continue
        if scenario == "TRAP_REVERSAL":
            leg_class = "REVERSAL"
        elif scenario == "TREND_CONTINUATION":
            leg_class = "EARLY_TREND"
        else:
            leg_class = "TREND_CONTINUATION"
        sl, tp1, tp2 = compute_sl_tp(price, side, leg_class, atr_val, df)
        reason_str = f"ADV SMC {adv_class} | {scenario} | RF {side} | Loc {location}"
        trade_type = "SMC_ADV"
        TRADE_STATE["zone"] = "support" if side=="BUY" else "resistance"
        TRADE_STATE["location"] = location
        TRADE_STATE["reason"] = [scenario, adv_class, location, narrative['classification']]
        ok = execute_entry(side, sym, price, sl, tp1, tp2, 0, reason_str, atr_val, trade_type, adv_class, classification)
        if ok:
            return True
    return False

# ========== TRADE MANAGEMENT HELPERS ==========
UPDATE_INTERVAL_SEC = 5

def get_last_price(symbol):
    return get_ticker_safe(symbol)

def update_trailing_simple(current_price):
    if not TRADE_STATE["trail_on"]:
        return False
    entry = TRADE_STATE["entry"]
    side = TRADE_STATE["side"]
    if "trail_stop" not in TRADE_STATE:
        if side == "BUY":
            TRADE_STATE["trail_stop"] = entry * 1.005
        else:
            TRADE_STATE["trail_stop"] = entry * 0.995
    if side == "BUY":
        new_stop = current_price * 0.995
        if new_stop > TRADE_STATE["trail_stop"]:
            TRADE_STATE["trail_stop"] = new_stop
        if current_price <= TRADE_STATE["trail_stop"]:
            return True
    else:
        new_stop = current_price * 1.005
        if new_stop < TRADE_STATE["trail_stop"]:
            TRADE_STATE["trail_stop"] = new_stop
        if current_price >= TRADE_STATE["trail_stop"]:
            return True
    return False

def stop_hit(current_price):
    if not STATE["open"]:
        return False
    side = STATE["side"]
    sl = STATE.get("synthetic_sl", 0.0)
    if side == "BUY" and current_price <= sl:
        return True
    if side == "SELL" and current_price >= sl:
        return True
    return False

def get_dashboard_metrics():
    winrate = (PERF["wins"] / PERF["trades"] * 100) if PERF["trades"] else 0
    total_pnl = PERF["total_pnl_pct"] * 100
    last = PERF["last_trade"]
    last_txt = "N/A"
    if last:
        sign = "+" if last["pnl_pct"] >= 0 else ""
        last_txt = f'{last["result"]} ({sign}{last["pnl_pct"]:.2f}%)'
    return {
        "winrate": f"{winrate:.1f}%",
        "total_pnl": f"{total_pnl:+.2f}%",
        "total_pnl_usdt": PERF["total_pnl_usdt"],
        "last_trade": last_txt,
        "trades": PERF["trades"],
        "wins": PERF["wins"],
        "losses": PERF["losses"]
    }

def manage_take_profit(price, atr):
    return "HOLD"

def scaling_logic(symbol, df, ind):
    if not STATE["open"] or STATE.get("scale_ins", 0) >= MAX_SCALE_INS:
        return False
    pnl_pct = (df['close'].iloc[-1] - STATE["entry"])/STATE["entry"]*100 if STATE["side"]=="BUY" else (STATE["entry"]-df['close'].iloc[-1])/STATE["entry"]*100
    if pnl_pct < SCALE_IN_PROFIT_PCT:
        return False
    if abs(df['close'].iloc[-1] - STATE["entry"])/STATE["entry"] < 0.005:
        additional_qty = STATE["qty"] * SCALE_IN_SIZE_PCT
        sym_norm = normalize_symbol(symbol)
        try:
            market = ex.market(sym_norm)
            precision = market['precision']['amount']
            qty = math.floor(additional_qty / precision) * precision
        except:
            qty = additional_qty
        if qty > 0:
            order = open_position(STATE["side"], qty, symbol)
            if order:
                STATE["qty"] += qty
                STATE["remaining_qty"] += qty
                STATE["scale_ins"] = STATE.get("scale_ins", 0) + 1
                log_execution(f"Scaled in {qty:.6f} at {df['close'].iloc[-1]:.4f}", "SUCCESS")
                return True
    return False

def council_exit(df, price):
    adx_series = compute_adx(df)
    adx = adx_series.iloc[-1] if adx_series is not None else 0
    if adx < 18:
        log_execution(f"Exit: ADX dropped to {adx:.1f}", "WARN")
        close_position_full()
        return True
    if STATE["side"] == "BUY" and price < STATE.get("synthetic_sl", 0):
        log_execution(f"Stop loss hit at {price:.4f}", "WARN")
        try:
            tg_sl_hit(STATE["current_symbol"], (price - STATE["entry"])/STATE["entry"]*100)
        except:
            pass
        close_position_full()
        return True
    elif STATE["side"] == "SELL" and price > STATE.get("synthetic_sl", 0):
        log_execution(f"Stop loss hit at {price:.4f}", "WARN")
        try:
            tg_sl_hit(STATE["current_symbol"], (STATE["entry"]-price)/STATE["entry"]*100)
        except:
            pass
        close_position_full()
        return True
    return False

def update_pnl_and_learning(pnl_pct):
    duration = (time.time() - STATE.get("entry_time", time.time())) / 60
    log_execution(f"CLOSE {STATE['current_symbol']} ({STATE['side']}) PnL: {pnl_pct:.2f}% in {duration:.1f} min",
                  "SUCCESS" if pnl_pct >= 0 else "ERROR")
    update_stats(pnl_pct)
    if pnl_pct < 0:
        STATE["consecutive_losses"] += 1
        cooldown = COOLDOWN_MINUTES_DRAWDOWN if STATE["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES else COOLDOWN_MINUTES_LOSS
        STATE["cooldown_until"] = datetime.now(timezone.utc) + timedelta(minutes=cooldown)
    else:
        STATE["consecutive_losses"] = 0

def cooldown_active():
    return STATE["cooldown_until"] and datetime.now(timezone.utc) < STATE["cooldown_until"]

def emergency_kill_switch_active():
    if STATE["daily_loss_limit_hit"]:
        return True
    bal = get_balance_safe()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if STATE["last_trade_day"] != today:
        STATE["daily_peak_balance"] = bal
        STATE["daily_loss_limit_hit"] = False
        STATE["last_trade_day"] = today
    else:
        if STATE["daily_peak_balance"] is None:
            STATE["daily_peak_balance"] = bal
        else:
            if bal > STATE["daily_peak_balance"]:
                STATE["daily_peak_balance"] = bal
            loss_pct = (STATE["daily_peak_balance"] - bal) / STATE["daily_peak_balance"] * 100
            if loss_pct >= MAX_DAILY_LOSS_PCT:
                STATE["daily_loss_limit_hit"] = True
                log_execution(f"Daily loss limit hit: {loss_pct:.1f}%", "ERROR")
                return True
    return False

def trailing_stop_new(price, atr):
    return False

# ========== RADAR FUNCTIONS ==========
def fast_market_filter(df):
    price = df['close'].iloc[-1]
    vol_usdt = df['volume'].iloc[-1] * price
    atr = compute_atr(df).iloc[-1]
    if vol_usdt < 1_000_000:
        return False
    if (atr / price) < 0.003:
        return False
    return True

def accumulation_v2(df):
    ema20 = df['close'].ewm(span=20).mean()
    ema50 = df['close'].ewm(span=50).mean()
    compression = abs(ema20.iloc[-1] - ema50.iloc[-1]) < df['close'].iloc[-1] * 0.002
    tight_range = (df['high'].rolling(10).max() - df['low'].rolling(10).min()) < df['close'].iloc[-1] * 0.01
    volume_dry = df['volume'].iloc[-1] < df['volume'].rolling(20).mean().iloc[-1]
    return compression and tight_range and volume_dry

def detect_sweep_simple(df):
    ctx = detect_liquidity_context(df)
    return ctx is not None

def radar_score(df):
    score = 0
    if accumulation_v2(df):
        score += 3
    if volume_pressure_real(df):
        score += 2
    if detect_sweep_simple(df):
        score += 2
    if near_key_zone(df, df['close'].iloc[-1]):
        score += 2
    return score

def store_intent_for_symbol(symbol):
    try:
        df = get_ohlcv_safe(symbol, 100)
        if df is None or not validate_dataframe(df, 30):
            return
        ob = get_orderbook_cached(symbol, limit=10)
        intent_score, intent_status, intent_details = InstitutionalIntentEngine.detect(df, ob, symbol)
        if intent_score >= 0:
            MEMORY[f"intent_{symbol}"] = {
                "score": intent_score, "status": intent_status, "details": intent_details
            }
            log_execution(f"[INTENT] Stored for {symbol}: score={intent_score}, status={intent_status}", "INFO", debounce_key=f"intent_store_{symbol}", debounce_sec=60)
    except Exception as e:
        log_execution(f"[INTENT_STORE] Error for {symbol}: {e}", "WARN")

def rebuild_radar_watchlist():
    symbols = get_usdt_perp_symbols()
    candidates = []
    for sym in symbols[:150]:
        try:
            df = get_ohlcv_safe(sym, 100)
            if df is None or not validate_dataframe(df, 80) or not fast_market_filter(df):
                continue
            score = radar_score(df)
            if score > 0:
                candidates.append({"symbol": sym, "score": score})
                store_intent_for_symbol(sym)
        except Exception:
            continue
    candidates.sort(key=lambda x: x["score"], reverse=True)
    MEMORY["radar_watchlist"] = candidates[:30]
    MEMORY["radar_top5"] = candidates[:5]
    log_execution(f"Radar rebuilt: {len(candidates)} candidates, top5: {[c['symbol'] for c in MEMORY['radar_top5']]}", "INFO")

def refresh_radar_watchlist():
    wl = MEMORY.get("radar_watchlist", [])
    updated = []
    for entry in wl:
        sym = entry["symbol"]
        try:
            df = get_ohlcv_safe(sym, 100)
            if df is None or not validate_dataframe(df, 80):
                continue
            score = radar_score(df)
            if score > 0:
                updated.append({"symbol": sym, "score": score})
                store_intent_for_symbol(sym)
        except Exception:
            continue
    updated.sort(key=lambda x: x["score"], reverse=True)
    MEMORY["radar_watchlist"] = updated[:30]
    MEMORY["radar_top5"] = updated[:5]
    log_execution(f"Radar refreshed: {len(updated)} symbols remain in watchlist", "INFO")

def radar_entry_scan():
    if not MEMORY.get("radar_top5"):
        return
    now = time.time()
    for entry in MEMORY["radar_top5"]:
        sym = entry["symbol"]
        last = LAST_ENTRY_PER_SYMBOL.get(sym, 0)
        if now - last < RADAR_COOLDOWN_SEC:
            continue
        df = get_ohlcv_safe(sym, 120)
        if df is None or not validate_dataframe(df, 80):
            continue
        price = df['close'].iloc[-1]
        atr_val = compute_atr(df).iloc[-1]
        ob = get_orderbook_cached(sym, limit=10)
        if ob is None:
            continue
        for side_try in ("BUY", "SELL"):
            should_enter, classification, reason_str = check_institutional_entry(sym, side_try, df, ob, atr_val, price)
            if should_enter:
                should_enter_narr, final_class, narrative = evaluate_with_narrative(sym, side_try, price, atr_val, df, ob, side_try)
                if not should_enter_narr:
                    continue
                sl, tp1, tp2 = compute_sl_tp(price, side_try, "REVERSAL", atr_val, df)
                ok = execute_entry(side_try, sym, price, sl, tp1, tp2, 85, reason_str, atr_val,
                                   trade_type="RADAR_INST", entry_type="SMART_EARLY", classification=classification)
                if ok:
                    LAST_ENTRY_PER_SYMBOL[sym] = now
                    return True
        decision, dec_side, dec_info = smart_decision(df, ob, sym)
        if decision == "STOP_HUNT":
            should_enter, classification, narrative = evaluate_with_narrative(sym, dec_side, price, atr_val, df, ob, dec_side)
            if not should_enter:
                continue
            sl, tp1, tp2 = compute_sl_tp(price, dec_side, "REVERSAL", atr_val, df)
            reason_str = f"RADAR_STOP_HUNT | NARR={narrative['classification']}"
            ok = execute_entry(dec_side, sym, price, sl, tp1, tp2, 8, reason_str, atr_val,
                               trade_type="RADAR_SMART", entry_type="RADAR_STOP_HUNT", classification=classification)
            if ok:
                LAST_ENTRY_PER_SYMBOL[sym] = now
                return True
        elif decision == "EXHAUSTION_ENTRY":
            should_enter, classification, narrative = evaluate_with_narrative(sym, dec_side, price, atr_val, df, ob, dec_side)
            if not should_enter:
                continue
            sl, tp1, tp2 = compute_sl_tp(price, dec_side, "REVERSAL", atr_val, df)
            reason_str = f"RADAR_EXHAUSTION | NARR={narrative['classification']}"
            ok = execute_entry(dec_side, sym, price, sl, tp1, tp2, 8, reason_str, atr_val,
                               trade_type="RADAR_SMART", entry_type="RADAR_EXHAUSTION", classification=classification)
            if ok:
                LAST_ENTRY_PER_SYMBOL[sym] = now
                return True
        total_v1, scn_v1, dir_v1, reasons_v1 = decision_score_v1(df, ob, atr_val, "BUY")
        total_v1 = apply_overrides_v1(df, atr_val, total_v1)
        if dir_v1 and total_v1 >= 5:
            should_enter, classification, narrative = evaluate_with_narrative(sym, dir_v1, price, atr_val, df, ob, dir_v1)
            if not should_enter:
                continue
            sl_v1, tp1_v1, tp2_v1 = compute_sl_tp(price, dir_v1,
                                                   "REVERSAL" if scn_v1 in ("TRAP","REVERSAL") else "EARLY_TREND",
                                                   atr_val, df)
            ok = decide_and_execute_v1(sym, dir_v1, total_v1, reasons_v1, price, sl_v1, tp1_v1, tp2_v1)
            if ok:
                LAST_ENTRY_PER_SYMBOL[sym] = now
                return True
        total_score, scenario_name, scenario_dir, all_reasons = decision_score(df, ob, atr_val, "BUY")
        if total_score >= 7:
            should_enter, classification, narrative = evaluate_with_narrative(sym, scenario_dir, price, atr_val, df, ob, scenario_dir)
            if not should_enter:
                continue
            sl, tp1, tp2 = compute_sl_tp(price, scenario_dir, "EARLY_TREND", atr_val, df)
            reason_str = f"RADAR_UNIFIED_SNIPER ({scenario_name}) score={total_score}"
            ok = execute_entry(scenario_dir, sym, price, sl, tp1, tp2, total_score, reason_str, atr_val,
                               trade_type="RADAR_SCENARIO", entry_type="RADAR_SNIPER", classification=classification)
            if ok:
                LAST_ENTRY_PER_SYMBOL[sym] = now
                return True
        elif total_score >= 5:
            should_enter, classification, narrative = evaluate_with_narrative(sym, scenario_dir, price, atr_val, df, ob, scenario_dir)
            if not should_enter:
                continue
            sl, tp1, tp2 = compute_sl_tp(price, scenario_dir, "EARLY_TREND", atr_val, df)
            reason_str = f"RADAR_UNIFIED_EARLY ({scenario_name}) score={total_score}"
            ok = execute_entry(scenario_dir, sym, price, sl, tp1, tp2, total_score, reason_str, atr_val,
                               trade_type="RADAR_SCENARIO", entry_type="RADAR_EARLY", classification=classification)
            if ok:
                LAST_ENTRY_PER_SYMBOL[sym] = now
                return True
        for side in ("BUY", "SELL"):
            es, reasons = early_score(df, ob, atr_val, side)
            if es >= 6:
                should_enter, classification, narrative = evaluate_with_narrative(sym, side, price, atr_val, df, ob, side)
                if not should_enter:
                    continue
                sl, tp1, tp2 = compute_sl_tp(price, side, "EARLY_TREND", atr_val, df)
                reason_str = f"RADAR_EARLY ({','.join(reasons)}) score={es}"
                ok = execute_entry(side, sym, price, sl, tp1, tp2, es, reason_str, atr_val,
                                   trade_type="RADAR_EARLY", entry_type="RADAR_SNIPER", classification=classification)
                if ok:
                    LAST_ENTRY_PER_SYMBOL[sym] = now
                    return True
    return False

def compute_zone_strength(df, level, zone_type, atr, ob):
    price = df['close'].iloc[-1]
    dist_pct = abs(price - level) / price
    touch_indices = []
    for i in range(max(0, len(df)-30), len(df)):
        candle_high = df['high'].iloc[i]
        candle_low = df['low'].iloc[i]
        if (zone_type == "support" and abs(candle_low - level) < atr) or \
           (zone_type == "resistance" and abs(candle_high - level) < atr):
            touch_indices.append(i)
    vol_strength = 0
    if touch_indices:
        volumes = df['volume'].iloc[touch_indices]
        avg_vol = volumes.mean()
        overall_avg = df['volume'].iloc[-30:].mean() if len(df) >= 30 else df['volume'].mean()
        vol_strength = min(3.0, avg_vol / overall_avg) if overall_avg > 0 else 0
    reaction_count = 0
    for idx in touch_indices:
        if idx < len(df)-1:
            next_close = df['close'].iloc[idx+1]
            if (zone_type == "support" and next_close > df['close'].iloc[idx]) or \
               (zone_type == "resistance" and next_close < df['close'].iloc[idx]):
                reaction_count += 1
    reaction_score = min(3.0, reaction_count)
    liquidity_score = 0
    if ob:
        obi = orderbook_imbalance(ob)
        if zone_type == "support" and obi > 0.1:
            liquidity_score = 2
        elif zone_type == "resistance" and obi < -0.1:
            liquidity_score = 2
        elif abs(obi) > 0.05:
            liquidity_score = 1
    inst_score = 0
    bos_up, bos_down = detect_bos(df, lookback=5)
    struct_shift = detect_structure_shift(df)
    if zone_type == "support" and (bos_up or struct_shift == "bullish_shift"):
        inst_score = 2
    elif zone_type == "resistance" and (bos_down or struct_shift == "bearish_shift"):
        inst_score = 2
    rejection_score = 0
    if len(df) >= 1:
        last = df.iloc[-1]
        body, range_, upper_wick, lower_wick = candle_metrics(last)
        if zone_type == "support" and lower_wick > body * 1.5 and abs(last['low'] - level) < atr:
            rejection_score = 2
        elif zone_type == "resistance" and upper_wick > body * 1.5 and abs(last['high'] - level) < atr:
            rejection_score = 2
    total = vol_strength + reaction_score + liquidity_score + inst_score + rejection_score
    strength = min(10.0, total * 10 / 10)
    return round(strength, 1), {
        "vol_strength": round(vol_strength, 1),
        "reaction_count": reaction_count,
        "liquidity_score": liquidity_score,
        "institutional_score": inst_score,
        "rejection_score": rejection_score
    }

def build_smart_zone_map(symbol, df, ob=None):
    atr = compute_atr(df).iloc[-1]
    supports, resistances = get_clustered_zones(df, lookback=120, cluster_pct=0.002)
    buy_zones = []
    for sup in supports:
        strength, details = compute_zone_strength(df, sup, "support", atr, ob)
        buy_zones.append({"price": sup, "strength": strength, "details": details, "type": "support"})
    sell_zones = []
    for res in resistances:
        strength, details = compute_zone_strength(df, res, "resistance", atr, ob)
        sell_zones.append({"price": res, "strength": strength, "details": details, "type": "resistance"})
    buy_zones.sort(key=lambda x: x["strength"], reverse=True)
    sell_zones.sort(key=lambda x: x["strength"], reverse=True)
    return {"buy_zones": buy_zones, "sell_zones": sell_zones}

def get_smart_zones(symbol, df, ob):
    key = f"smart_zones_{symbol}"
    cached = MEMORY.get(key)
    if cached and time.time() - cached.get("ts", 0) < 90:
        return cached["data"]
    zones = build_smart_zone_map(symbol, df, ob)
    MEMORY[key] = {"data": zones, "ts": time.time()}
    return zones

# ========== NEW LIQUIDITY DISCOVERY LAYER ==========
class FreshLiquidityRadar:
    @staticmethod
    def compute_liquidity_score(df):
        if len(df) < 30:
            return 0.0, {}
        score = 0.0
        details = {}
        vol = df['volume']
        vol_accel = vol.iloc[-5:].mean() / (vol.iloc[-10:-5].mean() + 1e-9)
        vol_accel_score = min(2.0, vol_accel - 1.0) if vol_accel > 1.0 else 0.0
        score += vol_accel_score * 2
        details["vol_accel"] = round(vol_accel, 2)
        vol_ratio = vol.iloc[-1] / vol.iloc[-20:].mean()
        vol_exp_score = min(1.5, vol_ratio - 0.8) if vol_ratio > 0.8 else 0.0
        score += vol_exp_score * 1.5
        details["vol_ratio"] = round(vol_ratio, 2)
        atr = compute_atr(df)
        atr_ratio = atr.iloc[-1] / atr.iloc[-20:].mean()
        atr_exp_score = min(1.5, atr_ratio - 0.9) if atr_ratio > 0.9 else 0.0
        score += atr_exp_score * 1.5
        details["atr_ratio"] = round(atr_ratio, 2)
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        range_ = last['high'] - last['low']
        if range_ > 0:
            body_ratio = body / range_
            displacement = 1.0 if body_ratio > 0.6 else 0.0
            score += displacement * 1.0
            details["displacement"] = displacement
        sweep_count = 0
        for i in range(-5, 0):
            sub_df = df.iloc[:i] if i < 0 else df
            if len(sub_df) >= 2:
                pools = build_liquidity_pools(sub_df)
                swept_h, swept_l = detect_sweep(sub_df, pools)
                if swept_h or swept_l:
                    sweep_count += 1
        sweep_score = min(2.0, sweep_count / 3.0)
        score += sweep_score * 2
        details["sweep_count"] = sweep_count
        adx = compute_adx(df)
        if len(adx) >= 5:
            adx_slope = adx.iloc[-1] - adx.iloc[-4]
            if adx_slope > 0:
                score += min(1.5, adx_slope / 5) * 1.0
                details["adx_slope"] = round(adx_slope, 2)
        final_score = min(10.0, score)
        return final_score, details

    @staticmethod
    def scan(symbols, limit=15):
        candidates = []
        for sym in symbols:
            try:
                df = get_ohlcv_safe(sym, 60)
                if df is None or not validate_dataframe(df, 30):
                    continue
                price = df['close'].iloc[-1]
                atr = compute_atr(df).iloc[-1]
                atr_pct = (atr / price) * 100 if price > 0 else 0
                if atr_pct < 0.2:
                    continue
                score, details = FreshLiquidityRadar.compute_liquidity_score(df)
                if score >= 3.0:
                    candidates.append({"symbol": sym, "score": round(score, 2), "details": details})
            except Exception:
                continue
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

# ========== SECTOR CLASSIFICATION ==========
SECTOR_MAP = {
    "AI": ["FET", "AGIX", "OCEAN", "RNDR", "TAO", "WLD", "PHB", "CTXC", "NMR", "ORAI"],
    "MEME": ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "MEME", "BABYDOGE", "ELON", "SAMO"],
    "LAYER1": ["BTC", "ETH", "SOL", "BNB", "ADA", "AVAX", "TON", "DOT", "ATOM", "NEAR", "ICP", "APT", "SUI", "KAS", "ALGO", "XLM", "VET", "HBAR", "FTM", "EGLD"],
    "LAYER2": ["MATIC", "ARB", "OP", "METIS", "BOBA", "LRC", "SKL", "IMX", "ZK", "POL"],
    "DEFI": ["UNI", "AAVE", "MKR", "COMP", "CRV", "LDO", "SNX", "BAL", "1INCH", "SUSHI", "CAKE", "RUNE", "ENJ", "YFI"],
    "GAMING": ["SAND", "MANA", "GALA", "AXS", "ILV", "YGG", "MAGIC", "PRIME", "GHST", "ALICE", "WAXP", "CROWN"],
    "INFRASTRUCTURE": ["LINK", "GRT", "FIL", "AR", "STORJ", "ANKR", "GNO", "LPT", "HNT", "THETA"],
    "RWA": ["ONDO", "CFG", "RIO", "LNDX", "PRO", "BTRST", "DUSK", "TRU"],
    "PAYMENT": ["XRP", "XLM", "ALGO", "NANO", "XDC", "AMP", "ACH"],
    "PRIVACY": ["ZEC", "XMR", "DASH", "KEEP", "NU", "SCRT", "NYM"],
    "STORAGE": ["FIL", "AR", "STORJ", "BLZ", "SIA", "BTT"]
}

def get_sector(symbol):
    base = symbol.replace("/USDT", "").upper()
    for sector, keywords in SECTOR_MAP.items():
        if any(kw in base for kw in keywords):
            return sector
    return "OTHER"

def get_volume_growth(sym):
    df = get_ohlcv_safe(sym, 30)
    if df is None or len(df) < 20:
        return 0.0
    vol = df['volume']
    recent_avg = vol.iloc[-5:].mean()
    older_avg = vol.iloc[-20:-5].mean()
    if older_avg == 0:
        return 0.0
    return (recent_avg / older_avg) - 1.0

def get_price_momentum(sym):
    df = get_ohlcv_safe(sym, 30)
    if df is None or len(df) < 20:
        return 0.0
    return (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100

def select_sector_leaders():
    sectors = set(SECTOR_MAP.keys())
    leaders = []
    for sector in sectors:
        symbols_in_sector = [s for s in get_usdt_perp_symbols() if get_sector(s) == sector][:20]
        if not symbols_in_sector:
            continue
        best = None
        best_score = -1e9
        for sym in symbols_in_sector:
            vol_growth = get_volume_growth(sym)
            momentum = get_price_momentum(sym)
            score = vol_growth * 10 + momentum
            if score > best_score:
                best_score = score
                best = sym
        if best:
            leaders.append({"symbol": best, "score": round(best_score, 2), "sector": sector})
    leaders.sort(key=lambda x: x["score"], reverse=True)
    return leaders[:5]

# ========== WATCHLIST ROTATION ENGINE ==========
class WatchlistRotation:
    def __init__(self, symbols_40):
        self.symbols = symbols_40
        self.batch_size = 6
        self.current_index = 0
        self.last_rotate = time.time()
        self.rotation_interval = 30

    def get_next_batch(self):
        batch = []
        for i in range(self.batch_size):
            idx = (self.current_index + i) % len(self.symbols)
            batch.append(self.symbols[idx])
        self.current_index = (self.current_index + self.batch_size) % len(self.symbols)
        self.last_rotate = time.time()
        return batch

    def should_rotate(self):
        return time.time() - self.last_rotate >= self.rotation_interval

def build_40_symbol_universe():
    strong_set = set()
    for c in MEMORY.get("scanner_v2_buy", []) + MEMORY.get("scanner_v2_sell", []):
        strong_set.add(c["symbol"])
    for c in MEMORY.get("radar_top5", []):
        strong_set.add(c["symbol"])
    for c in MEMORY.get("rf_watchlist", []):
        strong_set.add(c["symbol"])
    strong_list = list(strong_set)[:20]
    all_symbols = get_usdt_perp_symbols()
    fresh_radar = FreshLiquidityRadar.scan(all_symbols, limit=20)
    fresh_list = [c["symbol"] for c in fresh_radar if c["symbol"] not in strong_set][:15]
    sector_leaders = select_sector_leaders()
    leader_list = [l["symbol"] for l in sector_leaders if l["symbol"] not in strong_set and l["symbol"] not in fresh_list][:5]
    universe = strong_list + fresh_list + leader_list
    seen = set()
    unique_universe = []
    for sym in universe:
        if sym not in seen:
            seen.add(sym)
            unique_universe.append(sym)
    if len(unique_universe) < 40:
        extra = [s for s in all_symbols if s not in seen][:40 - len(unique_universe)]
        unique_universe.extend(extra)
    return unique_universe[:40]

# ========== EXECUTION QUEUE ==========
class OrderBlockQuality(Enum):
    FRESH = "FRESH"
    TESTED = "TESTED"
    WEAK = "WEAK"
    BROKEN = "BROKEN"
    FAKE = "FAKE"

class InstitutionalBehaviour(Enum):
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    RE_ACCUMULATION = "RE_ACCUMULATION"
    RE_DISTRIBUTION = "RE_DISTRIBUTION"
    NEUTRAL = "NEUTRAL"

class MarketStructure(Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"
    MSS = "MSS"
    NONE = "NONE"

class OpportunityType(Enum):
    INSTITUTIONAL_REVERSAL = "INSTITUTIONAL_REVERSAL"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    DISTRIBUTION_ENTRY = "DISTRIBUTION_ENTRY"
    ACCUMULATION_ENTRY = "ACCUMULATION_ENTRY"
    LOW_QUALITY = "LOW_QUALITY"
    FAKE_BREAKOUT = "FAKE_BREAKOUT"
    WEAK_ORDER_BLOCK = "WEAK_ORDER_BLOCK"

class ExecutionState(Enum):
    DISCOVERED = "DISCOVERED"
    WATCHLIST = "WATCHLIST"
    GOOD_ZONE = "GOOD_ZONE"
    WAITING_TRIGGER = "WAITING_TRIGGER"
    TRIGGER_DETECTED = "TRIGGER_DETECTED"
    ENTRY_VALIDATION = "ENTRY_VALIDATION"
    READY = "READY"
    EXECUTED = "EXECUTED"
    INVALIDATED = "INVALIDATED"
    RETURNED_WATCHLIST = "RETURNED_WATCHLIST"

@dataclass
class ZoneMetrics:
    order_block_quality: float = 50.0
    zone_strength: float = 50.0
    liquidity_quality: float = 50.0
    institutional_confidence: float = 50.0
    structure_alignment: float = 50.0
    entry_timing: float = 50.0
    trend_alignment: float = 50.0
    risk_score: float = 50.0
    trigger_state: str = "WAITING_TRIGGER"

    @property
    def final_zone_score(self) -> float:
        weights = {
            'order_block_quality': 0.20, 'zone_strength': 0.18,
            'liquidity_quality': 0.15, 'institutional_confidence': 0.15,
            'structure_alignment': 0.12, 'entry_timing': 0.10,
            'trend_alignment': 0.05, 'risk_score': 0.05
        }
        score = 0.0
        for attr, w in weights.items():
            score += getattr(self, attr, 50) * w
        return round(score, 2)

@dataclass
class ExecutionCandidate:
    symbol: str
    side: str
    price: float
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    atr: float
    df: pd.DataFrame
    ob: Any
    zone_metrics: ZoneMetrics = field(default_factory=ZoneMetrics)
    opportunity_type: OpportunityType = OpportunityType.LOW_QUALITY
    market_structure: MarketStructure = MarketStructure.NONE
    institutional_behaviour: InstitutionalBehaviour = InstitutionalBehaviour.NEUTRAL
    state: ExecutionState = ExecutionState.DISCOVERED
    priority_score: float = 0.0
    added_at: float = field(default_factory=time.time)
    last_evaluated: float = field(default_factory=time.time)
    evaluation_count: int = 0
    original_score: float = 0.0
    original_reason: str = ""
    signal_type: str = ""

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol, 'side': self.side, 'entry_price': self.entry_price,
            'opportunity_type': self.opportunity_type.value,
            'market_structure': self.market_structure.value,
            'institutional_behaviour': self.institutional_behaviour.value,
            'zone_score': self.zone_metrics.final_zone_score,
            'priority_score': self.priority_score,
            'state': self.state.value,
            'trigger_state': self.zone_metrics.trigger_state,
            'ob_score': self.zone_metrics.order_block_quality,
            'zone_strength': self.zone_metrics.zone_strength,
            'liquidity': self.zone_metrics.liquidity_quality,
            'institutional': self.zone_metrics.institutional_confidence,
            'structure': self.zone_metrics.structure_alignment,
            'timing': self.zone_metrics.entry_timing,
            'trend': self.zone_metrics.trend_alignment,
            'risk': self.zone_metrics.risk_score,
            'evaluation_count': self.evaluation_count,
            'last_update': self.last_evaluated
        }

class ExecutionQueue:
    def __init__(self, max_size: int = 15, re_eval_interval: float = 5.0):
        self._candidates: Dict[str, ExecutionCandidate] = {}
        self._max_size = max_size
        self._re_eval_interval = re_eval_interval
        self._lock = threading.RLock()
        self.total_evaluations = 0
        self.total_rejected = 0
        self.total_executed = 0
        self._last_promote = 0

    def add_candidate(self, candidate: ExecutionCandidate) -> bool:
        with self._lock:
            if len(self._candidates) >= self._max_size:
                lowest = min(
                    [(s, c) for s, c in self._candidates.items() if c.state != ExecutionState.READY],
                    key=lambda x: x[1].priority_score, default=None
                )
                if lowest:
                    self._candidates.pop(lowest[0])
                    self.total_rejected += 1
                else:
                    return False
            if candidate.symbol in self._candidates:
                existing = self._candidates[candidate.symbol]
                if candidate.zone_metrics.final_zone_score > existing.zone_metrics.final_zone_score:
                    self._candidates[candidate.symbol] = candidate
                    return True
                return False
            self._candidates[candidate.symbol] = candidate
            return True

    def re_evaluate_all(self, data_fetcher):
        if not self._candidates:
            return
        with self._lock:
            for symbol, cand in list(self._candidates.items()):
                df = data_fetcher(symbol)
                if df is None or len(df) < 30:
                    self._invalidate(symbol, "Insufficient data")
                    continue
                current_price = df['close'].iloc[-1]
                atr = compute_atr(df).iloc[-1] if len(df) > 14 else current_price * 0.01
                cand.atr = atr
                if self._is_extended(cand, current_price):
                    self._return_to_watchlist(symbol, "Price extended")
                    continue
                if self._is_order_block_broken(cand, current_price):
                    self._invalidate(symbol, "Order block broken")
                    continue
                ob_score, ob_type = self._evaluate_order_block(df, cand.side, atr)
                zone_score = self._evaluate_zone_strength(df, cand.side, atr, cand.entry_price)
                liq_score = self._evaluate_liquidity(df, cand.side, atr)
                inst_score = self._evaluate_institutional(df, cand.side)
                struct_score, struct_type = self._evaluate_structure(df, cand.side)
                timing_score = self._evaluate_timing(df, cand.side, atr, current_price, cand.entry_price)
                trend_score = self._evaluate_trend_alignment(df, cand.side)
                risk_score = self._evaluate_risk(cand, current_price)
                trigger_state = self._detect_trigger_state(df, cand.side, atr, cand.entry_price)
                metrics = ZoneMetrics(
                    order_block_quality=ob_score, zone_strength=zone_score,
                    liquidity_quality=liq_score, institutional_confidence=inst_score,
                    structure_alignment=struct_score, entry_timing=timing_score,
                    trend_alignment=trend_score, risk_score=risk_score,
                    trigger_state=trigger_state
                )
                opp_type = self._classify_opportunity(metrics, struct_type, cand.side, df)
                behaviour = self._detect_institutional_behaviour(df, cand.side)
                cand.zone_metrics = metrics
                cand.opportunity_type = opp_type
                cand.market_structure = struct_type
                cand.institutional_behaviour = behaviour
                cand.last_evaluated = time.time()
                cand.evaluation_count += 1
                cand.priority_score = metrics.final_zone_score
                self._update_state(cand, current_price)
                self.total_evaluations += 1
                if cand.priority_score < 30:
                    self._return_to_watchlist(symbol, "Score too low")

    def _is_extended(self, cand, price):
        return abs(price - cand.entry_price) > cand.atr * 1.5

    def _is_order_block_broken(self, cand, price):
        if cand.side == "BUY":
            return price < cand.entry_price - cand.atr * 0.8
        else:
            return price > cand.entry_price + cand.atr * 0.8

    def _evaluate_order_block(self, df, side, atr):
        if len(df) < 1:
            return 30, OrderBlockQuality.WEAK
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        range_ = last['high'] - last['low']
        if range_ == 0:
            return 30, OrderBlockQuality.WEAK
        if side == "BUY":
            lower_wick = min(last['open'], last['close']) - last['low']
            ratio = lower_wick / range_
            if ratio > 0.6 and last['close'] > last['open']:
                return 90, OrderBlockQuality.FRESH
            elif ratio > 0.4:
                return 70, OrderBlockQuality.TESTED
            else:
                return 50, OrderBlockQuality.WEAK
        else:
            upper_wick = last['high'] - max(last['open'], last['close'])
            ratio = upper_wick / range_
            if ratio > 0.6 and last['close'] < last['open']:
                return 90, OrderBlockQuality.FRESH
            elif ratio > 0.4:
                return 70, OrderBlockQuality.TESTED
            else:
                return 50, OrderBlockQuality.WEAK

    def _evaluate_zone_strength(self, df, side, atr, entry_price):
        touches = 0
        rejections = 0
        vol_sum = 0
        for i in range(max(0, len(df)-30), len(df)-1):
            candle = df.iloc[i]
            if side == "BUY":
                if abs(candle['low'] - entry_price) < atr * 0.5:
                    touches += 1
                    if df['close'].iloc[i+1] > candle['close']:
                        rejections += 1
                        vol_sum += candle['volume']
            else:
                if abs(candle['high'] - entry_price) < atr * 0.5:
                    touches += 1
                    if df['close'].iloc[i+1] < candle['close']:
                        rejections += 1
                        vol_sum += candle['volume']
        score = 50
        if touches >= 4: score += 25
        elif touches >= 2: score += 12
        elif touches >= 1: score += 5
        if rejections >= 3: score += 20
        elif rejections >= 2: score += 10
        avg_vol = df['volume'].iloc[-30:].mean()
        if touches > 0 and avg_vol > 0:
            avg_touch_vol = vol_sum / touches
            if avg_touch_vol > 2 * avg_vol: score += 15
            elif avg_touch_vol > 1.5 * avg_vol: score += 8
        return min(100, max(0, score))

    def _evaluate_liquidity(self, df, side, atr):
        pools = self._build_liquidity_pools(df)
        swept_high, swept_low = self._detect_sweep(df, pools)
        stop_hunt, hunt_side = self._detect_stop_hunt(df)
        eq_highs, eq_lows = self._detect_equal_highs_lows(df)
        score = 50
        if side == "BUY":
            if swept_low: score += 25
            if eq_lows: score += 10
            if stop_hunt and hunt_side == "BUY": score += 20
        else:
            if swept_high: score += 25
            if eq_highs: score += 10
            if stop_hunt and hunt_side == "SELL": score += 20
        return min(100, max(0, score))

    def _evaluate_institutional(self, df, side):
        try:
            smart = SmartMoneyEngine.analyze_smart_money(df)
            mom = MomentumFlowEngine.analyze_momentum_flow(df)
        except:
            return 50
        score = 50
        if smart.get('smart_money_dominant', False):
            score += 15
            if (side == "BUY" and smart['institutional_bias'] == "BUY") or \
               (side == "SELL" and smart['institutional_bias'] == "SELL"):
                score += 15
        dist = smart.get('distribution_risk', 0)
        if side == "BUY" and dist < 30: score += 10
        elif side == "SELL" and dist > 60: score += 10
        acc = smart.get('accumulation_strength', 0)
        if side == "BUY" and acc > 60: score += 10
        elif side == "SELL" and acc < 40: score += 10
        if mom.get('trend_expansion', False): score += 5
        if mom.get('momentum_decay', False): score -= 10
        return min(100, max(0, score))

    def _evaluate_structure(self, df, side):
        bos_up, bos_down = self._detect_bos(df)
        struct_shift = self._detect_structure_shift(df)
        score = 50
        struct_type = MarketStructure.NONE
        if side == "BUY":
            if struct_shift == "bullish_shift":
                score = 90
                struct_type = MarketStructure.MSS
            elif bos_up:
                score = 70
                struct_type = MarketStructure.BOS
        else:
            if struct_shift == "bearish_shift":
                score = 90
                struct_type = MarketStructure.MSS
            elif bos_down:
                score = 70
                struct_type = MarketStructure.BOS
        return score, struct_type

    def _evaluate_timing(self, df, side, atr, current_price, entry_price):
        dist = abs(current_price - entry_price) / entry_price
        score = 50
        if dist < 0.005: score += 30
        elif dist < 0.015: score += 15
        elif dist > 0.03: score -= 30
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        range_ = last['high'] - last['low']
        if range_ > 0:
            if side == "BUY":
                lower_wick = min(last['open'], last['close']) - last['low']
                if lower_wick / range_ > 0.5 and last['close'] > last['open']:
                    score += 20
            else:
                upper_wick = last['high'] - max(last['open'], last['close'])
                if upper_wick / range_ > 0.5 and last['close'] < last['open']:
                    score += 20
        vol_avg = df['volume'].iloc[-10:].mean()
        if vol_avg > 0 and df['volume'].iloc[-1] > 1.5 * vol_avg:
            score += 10
        return min(100, max(0, score))

    def _evaluate_trend_alignment(self, df, side):
        if len(df) < 20:
            return 50
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        price = df['close'].iloc[-1]
        score = 50
        if side == "BUY":
            if price > ema20 > ema50: score += 25
            elif price > ema20: score += 10
            else: score -= 20
        else:
            if price < ema20 < ema50: score += 25
            elif price < ema20: score += 10
            else: score -= 20
        return min(100, max(0, score))

    def _evaluate_risk(self, cand, price):
        spread = get_spread_bps(cand.symbol)
        score = 50
        if spread < 0.05: score += 20
        elif spread < 0.1: score += 10
        elif spread > 0.2: score -= 30
        atr_pct = (cand.atr / cand.entry_price) * 100 if cand.entry_price > 0 else 0
        if 0.5 < atr_pct < 2.5: score += 10
        elif atr_pct > 4: score -= 20
        return min(100, max(0, score))

    def _classify_opportunity(self, metrics, struct_type, side, df):
        score = metrics.final_zone_score
        if score >= 85 and struct_type != MarketStructure.NONE:
            return OpportunityType.INSTITUTIONAL_REVERSAL
        elif score >= 70 and struct_type == MarketStructure.BOS:
            return OpportunityType.BREAKOUT_RETEST
        elif score >= 60 and struct_type != MarketStructure.NONE:
            return OpportunityType.TREND_CONTINUATION
        elif side == "BUY" and metrics.institutional_confidence > 70:
            return OpportunityType.ACCUMULATION_ENTRY
        elif side == "SELL" and metrics.institutional_confidence > 70:
            return OpportunityType.DISTRIBUTION_ENTRY
        elif metrics.order_block_quality < 40:
            return OpportunityType.FAKE_BREAKOUT
        elif metrics.order_block_quality < 50:
            return OpportunityType.WEAK_ORDER_BLOCK
        return OpportunityType.LOW_QUALITY

    def _detect_institutional_behaviour(self, df, side):
        try:
            smart = SmartMoneyEngine.analyze_smart_money(df)
            mom = MomentumFlowEngine.analyze_momentum_flow(df)
        except:
            return InstitutionalBehaviour.NEUTRAL
        banker = smart.get('banker_pressure', 50)
        retail = smart.get('retailer_pressure', 50)
        dist = smart.get('distribution_risk', 0)
        acc = smart.get('accumulation_strength', 0)
        if side == "BUY" and banker > retail and dist < 30 and acc > 60:
            return InstitutionalBehaviour.ACCUMULATION
        if side == "SELL" and banker < retail and dist > 50:
            return InstitutionalBehaviour.DISTRIBUTION
        if side == "BUY" and dist > 50 and acc > 50:
            return InstitutionalBehaviour.RE_ACCUMULATION
        if side == "SELL" and dist < 30 and acc > 50:
            return InstitutionalBehaviour.RE_DISTRIBUTION
        return InstitutionalBehaviour.NEUTRAL

    def _detect_trigger_state(self, df, side, atr, entry_price):
        pools = self._build_liquidity_pools(df)
        swept_high, swept_low = self._detect_sweep(df, pools)
        sweep_ok = (side == "BUY" and swept_low) or (side == "SELL" and swept_high)
        bos_up, bos_down = self._detect_bos(df)
        struct_shift = self._detect_structure_shift(df)
        bos_ok = (side == "BUY" and bos_up) or (side == "SELL" and bos_down)
        choch_ok = (side == "BUY" and struct_shift == "bullish_shift") or (side == "SELL" and struct_shift == "bearish_shift")
        rejection_ok = candle_rejection(df, side)
        vol_state = classify_volume(df)
        displacement_ok = detect_displacement(df, side, atr, vol_state, body_atr_threshold=0.8, volume_expansion_required=False)
        dist = abs(df['close'].iloc[-1] - entry_price) / entry_price
        near_entry = dist < 0.003
        if sweep_ok and (bos_ok or choch_ok) and rejection_ok:
            return "MSS_CONFIRMED"
        elif sweep_ok and near_entry and rejection_ok:
            return "LIQUIDITY_SWEEP"
        elif bos_ok and displacement_ok:
            return "BOS_CONFIRMED"
        elif choch_ok and displacement_ok:
            return "CHOCH_CONFIRMED"
        elif sweep_ok and not (bos_ok or choch_ok):
            return "MITIGATION"
        elif near_entry and (bos_ok or choch_ok):
            return "WAITING_TRIGGER"
        elif near_entry:
            return "MITIGATION"
        elif displacement_ok:
            return "DISPLACEMENT"
        else:
            return "WAITING_TRIGGER"

    def _update_state(self, cand, price):
        score = cand.zone_metrics.final_zone_score
        trigger = cand.zone_metrics.trigger_state
        if score >= 85 and trigger in ("MSS_CONFIRMED", "LIQUIDITY_SWEEP", "BOS_CONFIRMED", "CHOCH_CONFIRMED"):
            cand.state = ExecutionState.READY
        elif score >= 70 and trigger == "MITIGATION":
            cand.state = ExecutionState.ENTRY_VALIDATION
        elif score >= 70:
            cand.state = ExecutionState.WAITING_TRIGGER
        elif score >= 55:
            cand.state = ExecutionState.GOOD_ZONE
        else:
            cand.state = ExecutionState.WATCHLIST

    def _detect_bos(self, df, lookback=5):
        if len(df) < lookback+2:
            return False, False
        recent_high = df['high'].iloc[-lookback-1:-1].max()
        recent_low = df['low'].iloc[-lookback-1:-1].min()
        close = df['close'].iloc[-1]
        return close > recent_high, close < recent_low

    def _detect_structure_shift(self, df):
        if len(df) < 10:
            return None
        if df['high'].iloc[-3] > df['high'].iloc[-6] and df['low'].iloc[-3] > df['low'].iloc[-6]:
            return "bullish_shift"
        if df['high'].iloc[-3] < df['high'].iloc[-6] and df['low'].iloc[-3] < df['low'].iloc[-6]:
            return "bearish_shift"
        return None

    def _build_liquidity_pools(self, df):
        if len(df) < 10:
            return {"high_pools": [], "low_pools": []}
        highs = df['high'].values
        lows = df['low'].values
        sh = [highs[i] for i in range(2, len(df)-2) if highs[i] == max(highs[i-2:i+3])]
        sl = [lows[i] for i in range(2, len(df)-2) if lows[i] == min(lows[i-2:i+3])]
        return {"high_pools": sh[-3:], "low_pools": sl[-3:]}

    def _detect_sweep(self, df, pools):
        if len(df) < 2:
            return False, False
        last, prev = df.iloc[-1], df.iloc[-2]
        swept_high = any(last['high'] > h and prev['high'] <= h for h in pools['high_pools'])
        swept_low = any(last['low'] < l and prev['low'] >= l for l in pools['low_pools'])
        return swept_high, swept_low

    def _detect_stop_hunt(self, df):
        pools = self._build_liquidity_pools(df)
        swept_high, swept_low = self._detect_sweep(df, pools)
        last = df.iloc[-1]
        if swept_high and last['close'] < last['high']:
            return True, "SELL"
        if swept_low and last['close'] > last['low']:
            return True, "BUY"
        return False, None

    def _detect_equal_highs_lows(self, df, lookback=50):
        if len(df) < lookback:
            return False, False
        sub = df.iloc[-lookback:]
        highs = sub['high'].values
        lows = sub['low'].values
        sh = [highs[i] for i in range(2, len(sub)-2) if highs[i] == max(highs[i-2:i+3])]
        sl = [lows[i] for i in range(2, len(sub)-2) if lows[i] == min(lows[i-2:i+3])]
        def eq(points, tol=0.002):
            if len(points) < 2:
                return False
            avg = sum(points) / len(points)
            return all(abs(p - avg) / avg < tol for p in points)
        eq_high = eq(sh[-3:]) if len(sh) >= 3 else False
        eq_low = eq(sl[-3:]) if len(sl) >= 3 else False
        return eq_high, eq_low

    def get_best_candidate(self) -> Optional[ExecutionCandidate]:
        with self._lock:
            ready = [c for c in self._candidates.values() if c.state == ExecutionState.READY]
            if not ready:
                return None
            return max(ready, key=lambda c: c.priority_score)

    def _invalidate(self, symbol, reason):
        if symbol in self._candidates:
            self._candidates[symbol].state = ExecutionState.INVALIDATED
            self._candidates.pop(symbol, None)
            self.total_rejected += 1
            log_execution(f"[QUEUE] {symbol} invalidated: {reason}", "WARN")

    def _return_to_watchlist(self, symbol, reason):
        if symbol in self._candidates:
            self._candidates[symbol].state = ExecutionState.RETURNED_WATCHLIST
            log_execution(f"[QUEUE] {symbol} returned to Watchlist: {reason}", "WARN")

    def cleanup(self):
        with self._lock:
            now = time.time()
            to_remove = []
            for symbol, cand in self._candidates.items():
                if cand.state in (ExecutionState.EXECUTED, ExecutionState.INVALIDATED, ExecutionState.RETURNED_WATCHLIST):
                    to_remove.append(symbol)
                elif now - cand.added_at > 3600:
                    if cand.priority_score >= 40:
                        self._return_to_watchlist(symbol, "Expired")
                    to_remove.append(symbol)
            for sym in to_remove:
                self._candidates.pop(sym, None)

    def get_status(self) -> dict:
        with self._lock:
            return {
                'total_candidates': len(self._candidates),
                'discovered': sum(1 for c in self._candidates.values() if c.state == ExecutionState.DISCOVERED),
                'watchlist': sum(1 for c in self._candidates.values() if c.state == ExecutionState.WATCHLIST),
                'good_zone': sum(1 for c in self._candidates.values() if c.state == ExecutionState.GOOD_ZONE),
                'waiting_trigger': sum(1 for c in self._candidates.values() if c.state == ExecutionState.WAITING_TRIGGER),
                'trigger_detected': sum(1 for c in self._candidates.values() if c.state == ExecutionState.TRIGGER_DETECTED),
                'entry_validation': sum(1 for c in self._candidates.values() if c.state == ExecutionState.ENTRY_VALIDATION),
                'ready': sum(1 for c in self._candidates.values() if c.state == ExecutionState.READY),
                'total_evaluations': self.total_evaluations,
                'total_rejected': self.total_rejected,
                'total_executed': self.total_executed,
                'candidates': [c.to_dict() for c in self._candidates.values()],
                'best_score': max([c.priority_score for c in self._candidates.values()]) if self._candidates else 0
            }

queue = ExecutionQueue(max_size=QUEUE_MAX_SIZE, re_eval_interval=QUEUE_RE_EVAL_INTERVAL)
_last_queue_promote = 0
_last_queue_eval = 0

# ========== GLOBAL DISCOVERY SCANNER ==========
def global_discovery_scan():
    log_execution("[DISCOVERY] Starting global discovery scan...", "INFO")
    start_time = time.time()
    all_symbols = get_usdt_perp_symbols()[:200]
    candidates = []
    buy, sell = smart_scanner_v2()
    for b in buy[:5]:
        candidates.append({"symbol": b["symbol"], "score": b["score"], "side": "BUY", "source": "scanner_v2"})
        store_intent_for_symbol(b["symbol"])
    for s in sell[:5]:
        candidates.append({"symbol": s["symbol"], "score": s["score"], "side": "SELL", "source": "scanner_v2"})
        store_intent_for_symbol(s["symbol"])
    rf_candidates = scan_market_rf(top_n=20)
    for r in rf_candidates[:10]:
        side = r.get("rf_signal")
        if side in ("BUY", "SELL"):
            candidates.append({"symbol": r["symbol"], "score": r["score"]*10, "side": side, "source": "rf"})
            store_intent_for_symbol(r["symbol"])
    fresh = FreshLiquidityRadar.scan(all_symbols, limit=15)
    for f in fresh:
        candidates.append({"symbol": f["symbol"], "score": f["score"]*2, "side": "BUY", "source": "fresh"})
        candidates.append({"symbol": f["symbol"], "score": f["score"]*2, "side": "SELL", "source": "fresh"})
        store_intent_for_symbol(f["symbol"])
    random.shuffle(all_symbols)
    for sym in all_symbols[:10]:
        if not any(c["symbol"] == sym for c in candidates):
            candidates.append({"symbol": sym, "score": 0, "side": "BUY", "source": "random"})
            candidates.append({"symbol": sym, "score": 0, "side": "SELL", "source": "random"})
            store_intent_for_symbol(sym)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:40]
    for item in top_candidates:
        sym = item["symbol"]
        side = item["side"]
        narrative = {
            "sweep": False, "choch_bos": False, "retest": False, "rejection": False,
            "displacement": False, "volume_confirmation": False, "rf_alignment": False
        }
        if item["source"] == "scanner_v2":
            narrative["sweep"] = True
        elif item["source"] == "rf":
            narrative["rf_alignment"] = True
        elif item["source"] == "fresh":
            narrative["volume_confirmation"] = True
        record_watchlist_entry(sym, side, narrative, item["score"])
        store_intent_for_symbol(sym)
    radar_top = [{"symbol": c["symbol"], "score": c["score"]} for c in top_candidates[:5]]
    MEMORY["radar_top5"] = radar_top
    elapsed = time.time() - start_time
    log_execution(f"[DISCOVERY] Scan completed in {elapsed:.1f}s, {len(top_candidates)} candidates added to watchlist.", "INFO")

def promote_to_queue():
    if not USE_EXECUTION_QUEUE:
        return
    if STATE.get("open") or TRADE_STATE.get("in_position"):
        return
    watchlist = []
    for source in (MEMORY.get("watchlist", {}).values(),
                   MEMORY.get("rf_watchlist", []),
                   MEMORY.get("scanner_v2_buy", []),
                   MEMORY.get("scanner_v2_sell", [])):
        if isinstance(source, dict):
            for item in source.values():
                if isinstance(item, dict) and "symbol" in item:
                    watchlist.append(item)
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict) and "symbol" in item:
                    watchlist.append(item)
    best_per_symbol = {}
    for item in watchlist:
        sym = item.get('symbol')
        if not sym:
            continue
        score = item.get('score', 0)
        side = item.get('side', 'BUY')
        if sym not in best_per_symbol or score > best_per_symbol[sym]['score']:
            best_per_symbol[sym] = {'score': score, 'side': side, 'source': item.get('source', 'unknown')}
    sorted_items = sorted(best_per_symbol.items(), key=lambda x: x[1]['score'], reverse=True)
    for sym, data in sorted_items[:30]:
        if sym in queue._candidates:
            continue
        df = get_ohlcv_safe(sym, 100)
        if df is None or len(df) < 30:
            continue
        price = df['close'].iloc[-1]
        atr = compute_atr(df).iloc[-1] if len(df) > 14 else price * 0.01
        ob = get_orderbook_cached(sym, limit=10)
        side = data.get('side', 'BUY')
        sl, tp1, tp2 = compute_sl_tp(price, side, "REVERSAL", atr, df)
        intent_score, _, _ = InstitutionalIntentEngine.detect(df, ob, sym)
        metrics = ZoneMetrics()
        candidate = ExecutionCandidate(
            symbol=sym, side=side, price=price, entry_price=price,
            stop_loss=sl, take_profit_1=tp1, take_profit_2=tp2,
            atr=atr, df=df, ob=ob, zone_metrics=metrics,
            original_score=data.get('score', 0),
            original_reason=data.get('reason', 'Watchlist promotion'),
            signal_type=data.get('source', 'watchlist')
        )
        candidate.priority_score = intent_score
        queue.add_candidate(candidate)
        log_execution(f"[QUEUE] Promoted {sym} {side} from watchlist (Intent: {intent_score:.1f})", "INFO", debounce_key=f"promote_{sym}", debounce_sec=60)

def process_queue_entry():
    if not USE_EXECUTION_QUEUE:
        return
    if STATE.get("open") or TRADE_STATE.get("in_position"):
        return
    best = queue.get_best_candidate()
    if best is None:
        return
    if best.priority_score < 80:
        return
    log_execution(f"[QUEUE] Attempting entry for {best.symbol} {best.side} (Score: {best.priority_score:.1f})", "INFO")
    success = execute_entry(
        best.side, best.symbol, best.price, best.stop_loss,
        best.take_profit_1, best.take_profit_2,
        best.original_score,
        f"QUEUE: {best.opportunity_type.value} (Zone Score: {best.zone_metrics.final_zone_score})",
        best.atr,
        best.opportunity_type.value,
        "EXECUTION_QUEUE",
        best.opportunity_type.value
    )
    if success:
        with queue._lock:
            if best.symbol in queue._candidates:
                queue._candidates[best.symbol].state = ExecutionState.EXECUTED
        queue.total_executed += 1
        log_execution(f"[QUEUE] Trade executed for {best.symbol}", "SUCCESS")

# ========== FLASK DASHBOARD ==========
app = Flask(__name__)

def update_position_dashboard(symbol, side, entry, qty, pnl=0.0):
    DASHBOARD_STATE["position"] = {
        "symbol": symbol, "side": side,
        "entry": round(entry, 4), "qty": qty, "pnl": round(pnl, 2),
        "sl": round(STATE.get("synthetic_sl", 0), 4),
        "tp1": round(STATE.get("synthetic_tp1", 0), 4),
        "tp2": round(STATE.get("tp2_price", 0), 4),
        "tp1_done": STATE.get("tp1_hit", False),
        "trailing_active": STATE.get("trail_activated", False),
        "regime": MEMORY.get("regime", "UNKNOWN"),
        "trade_type": STATE.get("trade_type", "N/A"),
        "entry_type": STATE.get("entry_type", "N/A"),
        "classification": STATE.get("classification", "N/A"),
        "location": STATE.get("location", "N/A"),
        "zone": STATE.get("zone_info", "N/A"),
        "score": STATE.get("trade_score", 0),
        "narrative_classification": STATE.get("narrative_classification", ""),
        "narrative_confidence": STATE.get("narrative_confidence", 0.0),
        "confidence_level": STATE.get("confidence_level", ""),
        "current_confidence": STATE.get("current_confidence", 50.0),
        "market_regime": STATE.get("market_regime", "UNKNOWN"),
        "continuation_pressure": STATE.get("continuation_pressure", 50),
        "trade_state": STATE.get("trade_state", "RANGE_CHOP"),
        "trail_multiplier": STATE.get("smart_trail_mult", 1.5),
        "delay_tp1": STATE.get("delay_tp1", False)
    }

def clear_position_dashboard():
    DASHBOARD_STATE["position"] = None

@app.route("/")
def dashboard():
    return "<h1>RF v28 (FIXED)</h1><p>See <a href='/data'>/data</a> for live state.</p>"

@app.route("/data")
def data():
    cached = cache_get("dashboard", 5)
    if cached is not None:
        return jsonify(safe_json(cached))
    try:
        bal = get_balance_safe()
        free_bal = get_free_balance_safe()
        avail_margin = free_bal
        mode = "LIVE" if MODE_LIVE else "PAPER"
        DASHBOARD_STATE["account"]["balance"] = bal
        DASHBOARD_STATE["account"]["free_balance"] = free_bal
        DASHBOARD_STATE["account"]["available_margin"] = avail_margin
        DASHBOARD_STATE["account"]["mode"] = mode
        perf = get_dashboard_metrics()
        pos = None
        if STATE["open"] and STATE.get("current_symbol"):
            roe = STATE.get("roe_pct", 0.0)
            pos = {
                "symbol": STATE["current_symbol"], "side": STATE["side"],
                "entry": round(STATE["entry"],4),
                "qty": STATE.get("qty", 0),
                "pnl": round(roe, 2),
                "sl": round(STATE.get("synthetic_sl",0),4),
                "tp1": round(STATE.get("synthetic_tp1",0),4),
                "tp2": round(STATE.get("tp2_price",0),4),
                "tp1_done": STATE.get("tp1_hit", False),
                "trailing_active": STATE.get("trail_activated", False),
                "regime": MEMORY.get("regime", "UNKNOWN"),
                "trade_type": STATE.get("trade_type", "N/A"),
                "entry_type": STATE.get("entry_type", "N/A"),
                "classification": STATE.get("classification", "N/A"),
                "location": STATE.get("location", "N/A"),
                "zone": STATE.get("zone_info", "N/A"),
                "score": STATE.get("trade_score", 0),
                "narrative_classification": STATE.get("narrative_classification", ""),
                "narrative_confidence": STATE.get("narrative_confidence", 0.0),
                "confidence_level": STATE.get("confidence_level", ""),
                "current_confidence": STATE.get("current_confidence", 50.0),
                "market_regime": STATE.get("market_regime", "UNKNOWN"),
                "continuation_pressure": STATE.get("continuation_pressure", 50),
                "trade_state": STATE.get("trade_state", "RANGE_CHOP"),
                "trail_multiplier": STATE.get("smart_trail_mult", 1.5),
                "delay_tp1": STATE.get("delay_tp1", False)
            }
        else:
            pos = DASHBOARD_STATE["position"]
        health = MEMORY["health"].copy()
        health["errors"] = len(DASHBOARD_STATE["errors"])
        top5 = MEMORY.get("top_candidates", [])[:5] if "top_candidates" in MEMORY else []
        cleanup_watchlist()
        watchlist_data = MEMORY.get("watchlist", {})
        no_entry_feed = MEMORY.get("no_entry_feed", [])[-5:]
        live_data = {}
        supervisor_data = None
        if DASHBOARD_STATE.get("live_trade_mode", False) and STATE.get("open"):
            supervisor_data = {
                "side": STATE["side"],
                "entry_price": STATE["entry"],
                "mark_price": STATE.get("mark_price", 0),
                "unrealized_pnl": STATE.get("unrealized_pnl_usdt", 0),
                "roe_pct": STATE.get("roe_pct", 0),
                "liquidation_price": STATE.get("liquidation_price", 0),
                "position_size": STATE.get("qty", 0),
                "leverage": LEVERAGE,
                "tp1_hit": STATE.get("tp1_hit", False),
                "tp2_hit": STATE.get("tp2_hit", False),
                "trailing_active": STATE.get("trail_activated", False),
                "adx": STATE.get("adx_live", 0),
                "di_plus": STATE.get("di_plus_live", 0),
                "di_minus": STATE.get("di_minus_live", 0),
                "continuation_pressure": STATE.get("continuation_pressure", 50),
                "trend_strength": STATE.get("trend_strength", 0),
                "thesis_failure_score": STATE.get("thesis_failure_score", 0),
                "current_confidence": STATE.get("current_confidence", 50),
                "trade_personality": STATE.get("trade_personality", "NEUTRAL"),
                "institutional_flow": STATE.get("institutional_flow", "NEUTRAL"),
                "reclaim_risk": STATE.get("reclaim_risk", 0),
                "trade_state": STATE.get("trade_state", "RANGE_CHOP"),
                "trail_multiplier": STATE.get("smart_trail_mult", 1.5),
                "delay_tp1": STATE.get("delay_tp1", False)
            }
            live_data["live_trade_mode"] = True
            live_data["supervisor"] = supervisor_data
            live_data["lifecycle_state"] = _live_manager.lifecycle_state.value
        else:
            live_data["live_trade_mode"] = False

        institutional_flow_data = DASHBOARD_STATE.get("institutional_flow", {})
        if not institutional_flow_data and STATE.get("smart_money"):
            mf = STATE.get("momentum_flow", {})
            institutional_flow_data = {
                "banker_pressure": STATE["smart_money"].get("banker_pressure", 0),
                "retailer_pressure": STATE["smart_money"].get("retailer_pressure", 0),
                "hot_money": STATE["smart_money"].get("hot_money_pressure", 0),
                "institutional_bias": STATE["smart_money"].get("institutional_bias", "NEUTRAL"),
                "institutional_bias_detailed": STATE["smart_money"].get("institutional_bias_detailed", "NEUTRAL"),
                "flow_alignment": STATE["smart_money"].get("flow_alignment", 0),
                "distribution_risk": STATE["smart_money"].get("distribution_risk", 0),
                "momentum_health": mf.get("momentum_health", 0),
                "continuation_strength": mf.get("continuation_strength", 0),
                "exhaustion_risk": mf.get("exhaustion_risk", 0),
                "climax_risk": mf.get("climax_risk", 0),
                "greed_state": mf.get("greed_state", False),
                "smart_money_dominant": STATE["smart_money"].get("smart_money_dominant", False)
            }

        intent_data = {}
        target_symbol = STATE.get("current_symbol")
        if not target_symbol:
            radar = MEMORY.get("radar_top5", [])
            if radar:
                target_symbol = radar[0].get("symbol")
            else:
                target_symbol = DEFAULT_SYMBOL
        if target_symbol:
            intent_data = MEMORY.get(f"intent_{target_symbol}", {})
            if not intent_data:
                store_intent_for_symbol(target_symbol)
                intent_data = MEMORY.get(f"intent_{target_symbol}", {})
        if not intent_data:
            intent_data = {"score": 0, "status": "NEUTRAL", "details": {}}

        dynamic_trade_data = {}
        if STATE.get("open") and "dynamic_manager" in STATE:
            mgr = STATE["dynamic_manager"]
            dynamic_trade_data = {
                "roe": mgr.calculate_roe(STATE.get("mark_price", STATE["entry"])),
                "trailing_active": mgr.trailing_activated,
                "tp1_hit": mgr.tp1_hit,
                "tp2_hit": mgr.tp2_hit,
                "runner_active": mgr.runner_active,
                "drawdown": mgr.drawdown,
                "lifecycle": mgr.lifecycle
            }
        else:
            dynamic_trade_data = {
                "roe": 0.0, "trailing_active": False, "tp1_hit": False,
                "tp2_hit": False, "runner_active": False,
                "drawdown": 0.0, "lifecycle": "N/A"
            }

        payload = {
            "balance": bal, "free_balance": free_bal, "avail_margin": avail_margin,
            "mode": mode, "stats": DASHBOARD_STATE["stats"], "position": pos,
            "logs": DASHBOARD_STATE["logs"][-30:],
            "errors": DASHBOARD_STATE["errors"][-10:],
            "top5": top5, "candidates": MEMORY.get("top_candidates", []),
            "scanned_count": len(MEMORY.get("top_candidates", [])),
            "last_scan": MEMORY["last_scan"], "regime": MEMORY["regime"],
            "health": health, "rf_dashboard": MEMORY.get("rf_dashboard", [])[:20],
            "total_pnl": perf["total_pnl"], "total_pnl_usdt": perf["total_pnl_usdt"],
            "last_trade": perf["last_trade"],
            "scanner_v2_buy": MEMORY.get("scanner_v2_buy", []),
            "scanner_v2_sell": MEMORY.get("scanner_v2_sell", []),
            "watchlist": watchlist_data, "no_entry_feed": no_entry_feed,
            "continuation_probability": STATE.get("continuation_probability", 0.5),
            "hold_quality": STATE.get("hold_quality", "UNKNOWN"),
            "counter_pressure": STATE.get("counter_pressure", 0.0),
            "reclaim_risk": STATE.get("reclaim_risk", 0.0),
            "trend_strength": STATE.get("trend_strength", 0.0),
            "continuation_reasons": STATE.get("continuation_reasons", []),
            "trade_thesis": STATE.get("trade_thesis", {}),
            "current_confidence": STATE.get("current_confidence", 50.0),
            "market_regime": STATE.get("market_regime", "UNKNOWN"),
            "continuation_pressure": STATE.get("continuation_pressure", 50),
            "thesis_failure_score": STATE.get("thesis_failure_score", 0),
            "institutional_flow": institutional_flow_data,
            "last_live_refresh": DASHBOARD_STATE.get("last_live_refresh", time.time()),
            "intent_engine": intent_data,
            "dynamic_trade": dynamic_trade_data,
            **live_data
        }
        if USE_EXECUTION_QUEUE:
            queue_status = queue.get_status()
            payload['queue'] = {
                'enabled': True,
                'total': queue_status['total_candidates'],
                'ready': queue_status['ready'],
                'best_score': queue_status['best_score'],
                'candidates': queue_status['candidates'][:15]
            }
        else:
            payload['queue'] = {'enabled': False}
        safe_payload = safe_json(payload)
        cache_set("dashboard", safe_payload)
        return jsonify(safe_payload), 200
    except Exception as e:
        log_execution(f"/data error: {traceback.format_exc()}", "ERROR")
        return jsonify({"error": str(e)}), 200

@app.route("/queue")
def queue_endpoint():
    if not USE_EXECUTION_QUEUE:
        return jsonify({"enabled": False})
    status = queue.get_status()
    return jsonify(safe_json(status))

@app.route("/decision")
def decision_endpoint():
    decisions = MEMORY.get("decision_log", [])[-50:]
    return jsonify({"data": decisions})

@app.route("/trade", methods=["POST"])
def manual_trade():
    data = request.json
    side = data.get("side")
    if not side or side not in ["BUY","SELL"]:
        return jsonify({"error": "Invalid side"}),400
    if STATE["open"]:
        return jsonify({"error": "Position open"}),400
    sync_position_state(DEFAULT_SYMBOL)
    if STATE["open"]:
        return jsonify({"error": "Already in position (synced with exchange)"}),400
    if INSUFFICIENT_MARGIN_COOLDOWN_UNTIL and time.time() < INSUFFICIENT_MARGIN_COOLDOWN_UNTIL:
        return jsonify({"error": "Insufficient margin cooldown active"}),400
    price = get_ticker_safe(DEFAULT_SYMBOL)
    if not price or price <= 0:
        return jsonify({"error": "No price"}),400
    df = get_ohlcv_safe(DEFAULT_SYMBOL, 100)
    if df is None:
        return jsonify({"error": "No data"}),500
    atr = compute_atr(df).iloc[-1]
    sl = price - atr*1.6 if side=="BUY" else price + atr*1.6
    tp1 = price*1.006 if side=="BUY" else price*0.994
    tp2 = price*1.02 if side=="BUY" else price*0.98
    classification = "SNIPER"
    ok = execute_entry(side, DEFAULT_SYMBOL, price, sl, tp1, tp2, 80, "Manual override", atr, "HYBRID", "MANUAL", classification)
    return jsonify({"message": "Done" if ok else "Failed"}),200 if ok else 500

@app.route("/close", methods=["POST"])
def manual_close():
    if not STATE["open"]:
        return jsonify({"error": "No position"}),400
    price = get_ticker_safe(STATE["current_symbol"])
    if price:
        finalize_trade_with_reality(STATE["current_symbol"])
    else:
        close_position_full()
        finalize_trade_with_reality(STATE["current_symbol"])
    return jsonify({"message": "Closed"}),200

@app.route("/health")
def health():
    return jsonify({"ok": True})

app.add_url_rule('/narrative-debug', 'narrative_debug', narrative_debug)

def keep_alive():
    while True:
        time.sleep(KEEP_ALIVE_INTERVAL)
        try:
            requests.get(f"http://localhost:{os.environ.get('PORT', 8000)}/health", timeout=5)
        except:
            pass

_last_cleanup = 0
def hourly_cleanup():
    global _last_cleanup
    if time.time() - _last_cleanup < 3600:
        return
    CACHE["ohlcv"]["value"].clear()
    CACHE["ticker"]["value"].clear()
    CACHE["orderbook"]["value"].clear()
    gc.collect()
    _last_cleanup = time.time()

_last_snapshot_time = 0
def print_snapshot():
    global _last_snapshot_time
    now = time.time()
    if now - _last_snapshot_time < SNAPSHOT_INTERVAL:
        return
    _last_snapshot_time = now
    bal = get_balance_safe()
    free_bal = get_free_balance_safe()
    mode = "LIVE" if MODE_LIVE else "PAPER"
    perf = get_dashboard_metrics()
    print("\n" + "="*70)
    print(color_text(f"🔥 RF v28 (FIXED) ({mode}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", BOLD))
    print(f"💰 Balance: {color_text(f'{bal:.2f} USDT', GREEN)}  Free: {color_text(f'{free_bal:.2f} USDT', GREEN)}")
    print(f"📊 Total PnL: {perf['total_pnl']} | Last Trade: {perf['last_trade']}")
    if STATE["open"]:
        roe = STATE.get("roe_pct", 0.0)
        roe_colored = color_pnl(roe)
        lifecycle = _live_manager.lifecycle_state.value
        print(f"📊 POSITION: {STATE['current_symbol']} {STATE['side']} | ROE: {roe_colored} | Lifecycle: {lifecycle}")
        print(f"   SL: {STATE.get('synthetic_sl',0):.4f} | TP1: {STATE.get('synthetic_tp1',0):.4f}")
    else:
        print("📊 POSITION: None")
    print("="*70 + "\n")

def build_rf_dashboard():
    dashboard = []
    candidates = scan_market_rf(top_n=30)
    for c in candidates:
        dashboard.append({
            "symbol": c["symbol"], "status": c.get("status", "PROXIMITY"),
            "icon": "🔔" if c["rf_triggered"] else "📡",
            "score": c["score"], "adx": c["adx"], "rsi": c["rsi"],
            "atrp": c["atrp"], "signal": c["rf_signal"] or "N/A"
        })
    MEMORY["rf_dashboard"] = dashboard
    return dashboard

def run_scanner_v2():
    try:
        buy, sell = smart_scanner_v2()
        MEMORY["scanner_v2_buy"] = buy
        MEMORY["scanner_v2_sell"] = sell
        MEMORY["scanner_v2_last_scan"] = time.time()
        log_execution(f"[SCANNER] TOP BUY: {len(buy)} | TOP SELL: {len(sell)}", "INFO")
    except Exception as e:
        log_execution(f"Smart Scanner v2 error: {traceback.format_exc()}", "ERROR")

# ========== SNIPER V2 ==========
SNIPER_ZONES = {}

def is_pivot_high(df, lookback=3):
    if len(df) < lookback * 2 + 1:
        return False
    current_high = df['high'].iloc[-1]
    left_highs = df['high'].iloc[-(lookback+1):-1]
    if any(current_high <= h for h in left_highs):
        return False
    return True

def is_pivot_low(df, lookback=3):
    if len(df) < lookback * 2 + 1:
        return False
    current_low = df['low'].iloc[-1]
    left_lows = df['low'].iloc[-(lookback+1):-1]
    if any(current_low >= l for l in left_lows):
        return False
    return True

def detect_strong_pivot(df, side, atr):
    if len(df) < 20:
        return False, []
    reasons = []
    strong = False
    if side == "TOP":
        move_up = df['high'].iloc[-1] - df['low'].iloc[-6] if len(df) >= 6 else 0
        if move_up > atr * 1.5:
            reasons.append("strong_move_up")
            strong = True
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        upper_wick = last['high'] - max(last['open'], last['close'])
        if upper_wick > body:
            reasons.append("rejection_wick")
            strong = True
        ema50 = ema(df['close'], 50).iloc[-1]
        distance = abs(last['close'] - ema50) / ema50 if ema50 > 0 else 0
        if distance > atr / last['close']:
            reasons.append("overextended")
            strong = True
    else:
        move_down = df['high'].iloc[-6] - df['low'].iloc[-1] if len(df) >= 6 else 0
        if move_down > atr * 1.5:
            reasons.append("strong_move_down")
            strong = True
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        lower_wick = min(last['open'], last['close']) - last['low']
        if lower_wick > body:
            reasons.append("rejection_wick")
            strong = True
        ema50 = ema(df['close'], 50).iloc[-1]
        distance = abs(last['close'] - ema50) / ema50 if ema50 > 0 else 0
        if distance > atr / last['close']:
            reasons.append("overextended")
            strong = True
    return strong, reasons

def check_sniper_confirmation(df, zone_type):
    if len(df) < 2:
        return False, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body = abs(last['close'] - last['open'])
    range_ = last['high'] - last['low']
    confirm = 0
    if zone_type == 'TOP':
        upper_wick = last['high'] - max(last['open'], last['close'])
        if range_ > 0 and upper_wick > body * 0.5:
            confirm += 1
    else:
        lower_wick = min(last['open'], last['close']) - last['low']
        if range_ > 0 and lower_wick > body * 0.5:
            confirm += 1
    if zone_type == 'TOP':
        zone_high = SNIPER_ZONES.get(df.symbol if hasattr(df, 'symbol') else '', {}).get('high', last['high']+1)
        if last['high'] > zone_high and last['close'] < zone_high:
            confirm += 1
    else:
        zone_low = SNIPER_ZONES.get(df.symbol if hasattr(df, 'symbol') else '', {}).get('low', last['low']-1)
        if last['low'] < zone_low and last['close'] > zone_low:
            confirm += 1
    if zone_type == 'TOP':
        if last['close'] < last['open'] and prev['close'] > prev['open']:
            confirm += 1
    else:
        if last['close'] > last['open'] and prev['close'] < prev['open']:
            confirm += 1
    return confirm >= 2, confirm

def sniper_engine_v2():
    symbols = [c["symbol"] for c in MEMORY.get("radar_top5", [])] if MEMORY.get("radar_top5") else get_usdt_perp_symbols()[:20]
    for sym in symbols:
        df = get_ohlcv_safe(sym, 150)
        if df is None or not validate_dataframe(df, 100):
            continue
        price = df['close'].iloc[-1]
        atr_val = compute_atr(df).iloc[-1]
        df.symbol = sym
        if sym not in SNIPER_ZONES or SNIPER_ZONES[sym]["state"] in ("IDLE", "EXPIRED"):
            if is_pivot_high(df, lookback=3):
                strong_top, reasons_top = detect_strong_pivot(df, "TOP", atr_val)
                if strong_top:
                    zone = {
                        "type": "TOP", "price": df['high'].iloc[-1],
                        "high": df['high'].iloc[-1],
                        "low": df['high'].iloc[-1] - atr_val * 0.5,
                        "time": time.time(), "state": "WAIT",
                        "confirm_count": 0, "reasons": reasons_top
                    }
                    SNIPER_ZONES[sym] = zone
                    continue
            if is_pivot_low(df, lookback=3):
                strong_bottom, reasons_bottom = detect_strong_pivot(df, "BOTTOM", atr_val)
                if strong_bottom:
                    zone = {
                        "type": "BOTTOM", "price": df['low'].iloc[-1],
                        "low": df['low'].iloc[-1],
                        "high": df['low'].iloc[-1] + atr_val * 0.5,
                        "time": time.time(), "state": "WAIT",
                        "confirm_count": 0, "reasons": reasons_bottom
                    }
                    SNIPER_ZONES[sym] = zone
                    continue
        if sym in SNIPER_ZONES:
            zone = SNIPER_ZONES[sym]
            if zone["state"] == "WAIT":
                if zone["type"] == "TOP":
                    if zone["low"] <= price <= zone["high"]:
                        zone["state"] = "READY"
                    elif price > zone["high"] + atr_val * 0.2:
                        zone["state"] = "EXPIRED"
                else:
                    if zone["low"] <= price <= zone["high"]:
                        zone["state"] = "READY"
                    elif price < zone["low"] - atr_val * 0.2:
                        zone["state"] = "EXPIRED"
                continue
            if zone["state"] == "READY":
                confirmed, conf_count = check_sniper_confirmation(df, zone["type"])
                if confirmed:
                    side = "SELL" if zone["type"] == "TOP" else "BUY"
                    ob = get_orderbook_cached(sym, limit=10)
                    should_enter, classification, narrative = evaluate_with_narrative(sym, side, price, atr_val, df, ob, side)
                    if not should_enter:
                        continue
                    sl = zone["high"] + atr_val * 0.4 if side == "SELL" else zone["low"] - atr_val * 0.4
                    tp1 = price * (1 - 0.004) if side == "SELL" else price * (1 + 0.004)
                    tp2 = price * (1 - 0.01) if side == "SELL" else price * (1 + 0.01)
                    reason_str = f"SNIPER_V2 {zone['type']} conf={conf_count}"
                    ok = execute_entry(side, sym, price, sl, tp1, tp2, 9, reason_str, atr_val,
                                       trade_type="SNIPER_V2", entry_type="STRONG_PIVOT", classification=classification)
                    if ok:
                        zone["state"] = "USED"
                        SNIPER_ZONES.pop(sym, None)
                        return True
                elif conf_count >= 1:
                    continue
                else:
                    if time.time() - zone["time"] > 3600:
                        zone["state"] = "EXPIRED"
                    continue
            if zone["state"] == "EXPIRED":
                SNIPER_ZONES.pop(sym, None)
    return False

def update_institutional_flow_scanner():
    try:
        df = get_ohlcv_safe(DEFAULT_SYMBOL, 100)
        if df is None or not validate_dataframe(df, 80):
            return
        smart = SmartMoneyEngine.analyze_smart_money(df)
        mom = MomentumFlowEngine.analyze_momentum_flow(df)
        DASHBOARD_STATE["institutional_flow"] = {
            "banker_pressure": smart["banker_pressure"],
            "retailer_pressure": smart["retailer_pressure"],
            "hot_money": smart["hot_money_pressure"],
            "institutional_bias": smart["institutional_bias"],
            "institutional_bias_detailed": smart.get("institutional_bias_detailed", "NEUTRAL"),
            "flow_alignment": smart["flow_alignment"],
            "distribution_risk": smart["distribution_risk"],
            "momentum_health": mom["momentum_health"],
            "continuation_strength": mom["continuation_strength"],
            "exhaustion_risk": mom["exhaustion_risk"],
            "climax_risk": mom["climax_risk"],
            "greed_state": mom["greed_state"],
            "smart_money_dominant": smart["smart_money_dominant"]
        }
        DASHBOARD_STATE["last_live_refresh"] = time.time()
    except Exception as e:
        log_execution(f"[SCANNER] Error: {e}", "ERROR")

def live_institutional_updater():
    while True:
        try:
            if STATE.get("open"):
                time.sleep(5)
                continue
            update_institutional_flow_scanner()
        except Exception as e:
            log_execution(f"[LIVE_UPDATER] Error: {e}", "ERROR")
        time.sleep(5)

MEMORY = {
    "candidates": [], "top_candidates": [], "regime": "NEUTRAL",
    "last_scan": 0, "scanned_count": 0,
    "health": {"api": "OK", "errors": 0, "status": "RUNNING"},
    "rf_watchlist": [], "rf_dashboard": [],
    "scanner_v2_buy": [], "scanner_v2_sell": [], "scanner_v2_last_scan": 0,
    "radar_watchlist": [], "radar_top5": [],
    "log_debounce": {}, "watchlist": {}, "no_entry_feed": [], "decision_log": []
}

SNIPER_MODE = True
CANDIDATE_SCAN_INTERVAL = 15

def sync_position_with_exchange(symbol):
    try:
        if hasattr(ex, 'fetch_positions'):
            positions = safe_api_call(ex.fetch_positions, [normalize_symbol(symbol)])
        elif hasattr(ex, 'fetch_open_positions'):
            positions = safe_api_call(ex.fetch_open_positions, [normalize_symbol(symbol)])
        else:
            return None
        if not positions:
            return None
        for pos in positions:
            pos_sym = pos.get('symbol', pos.get('info', {}).get('symbol', ''))
            if normalize_symbol(symbol) in pos_sym and float(pos.get('contracts', 0)) > 0:
                return pos
        return None
    except Exception as e:
        log_execution(f"[SYNC] error: {e}", "ERROR")
        return None

def get_realized_pnl(symbol, limit=100):
    try:
        trades = safe_api_call(ex.fetch_my_trades, normalize_symbol(symbol), limit=limit)
        if not trades:
            return 0.0, 0.0
        buy_value = 0.0
        sell_value = 0.0
        for trade in trades:
            side = trade['side'].lower()
            qty = trade['amount']
            price = trade['price']
            cost = qty * price
            if side == 'buy':
                buy_value += cost
            elif side == 'sell':
                sell_value += cost
        pnl = sell_value - buy_value
        balance = get_balance_safe()
        pnl_pct = (pnl / balance * 100) if balance > 0 else 0.0
        return pnl, pnl_pct
    except Exception as e:
        return 0.0, 0.0

def sync_all_states():
    if PAPER_MODE:
        MEMORY["position_status"] = "OPEN" if STATE.get("open") else "CLOSED"
        MEMORY["total_pnl"] = PERF.get("total_pnl_usdt", 0.0)
        MEMORY["total_pnl_pct"] = PERF.get("total_pnl_pct", 0.0) * 100
        return
    symbol = STATE.get("current_symbol") if STATE.get("open") else None
    if not symbol:
        return
    real_pos = sync_position_with_exchange(symbol)
    if real_pos is None and STATE.get("open"):
        with _TRADE_LOCK:
            STATE["open"] = False
            TRADE_STATE["in_position"] = False
        log_execution(f"[SYNC] Position on {symbol} closed externally", "WARN")

def execute_entry(side, symbol, price, sl, tp1, tp2, score, reason, atr_val, trade_type, entry_type, classification):
    if STATE.get("open") or TRADE_STATE.get("in_position"):
        log_execution(f"[ENTRY] Already in position, skipping {symbol}", "WARN")
        return False
    free_bal = get_free_balance_safe() if not PAPER_MODE else paper["balance"]
    usable_balance = free_bal * BALANCE_SAFETY_FACTOR
    if PAPER_MODE:
        balance = paper["balance"]
    else:
        balance = usable_balance

    if classification in ("SNIPER", "INSTITUTIONAL_SNIPER"):
        margin_percent = 0.40
        trade_type_label = "STRONG"
    elif classification == "TREND":
        margin_percent = 0.30
        trade_type_label = "NORMAL"
    elif classification == "LOW":
        margin_percent = 0.15
        trade_type_label = "LOW_CONF"
    else:
        margin_percent = 0.30
        trade_type_label = "NORMAL"

    margin = balance * margin_percent
    notional = margin * LEVERAGE
    qty = notional / price
    log_execution(f"[SIZING] Margin={margin:.2f} Notional={notional:.2f} Qty={qty:.6f}", "INFO")

    df = get_ohlcv_safe(symbol, 100)
    plus_di, minus_di, _, _ = get_di_components(df) if df is not None else (None, None, None, None)
    di_dominance = False
    if plus_di is not None and minus_di is not None:
        di_dominance = (side == "BUY" and plus_di > minus_di) or (side == "SELL" and minus_di > plus_di)
    weak_pullback = False
    if df is not None:
        last = df.iloc[-1]
        if side == "BUY":
            if last['close'] < last['open'] and abs(last['close'] - last['open']) < atr_val * 0.3:
                weak_pullback = True
        else:
            if last['close'] > last['open'] and abs(last['close'] - last['open']) < atr_val * 0.3:
                weak_pullback = True
    structure_aligned = False
    struct_shift = detect_structure_shift(df) if df is not None else None
    if side == "BUY" and struct_shift == "bullish_shift":
        structure_aligned = True
    elif side == "SELL" and struct_shift == "bearish_shift":
        structure_aligned = True
    counter_displacement = 0.0
    if df is not None:
        last = df.iloc[-1]
        if side == "SELL" and last['close'] > last['open']:
            body = abs(last['close'] - last['open'])
            if body > atr_val * 0.6:
                counter_displacement = body / atr_val
        elif side == "BUY" and last['close'] < last['open']:
            body = abs(last['close'] - last['open'])
            if body > atr_val * 0.6:
                counter_displacement = body / atr_val
    market_state = {
        "adx": compute_adx(df).iloc[-1] if df is not None else 20.0,
        "regime": MEMORY.get("regime", "UNKNOWN"),
        "di_dominance": di_dominance,
        "weak_pullback": weak_pullback,
        "structure_aligned": structure_aligned,
        "counter_displacement": counter_displacement,
        "trend_health": trend_engine.get_trend_health(df, side) if df is not None else 5
    }
    narrative = {"classification": classification}
    entry_context = {"price": price, "atr": atr_val}
    thesis = _thesis_engine.build_thesis(symbol, side, trade_type, market_state, narrative, entry_context)
    STATE["trade_thesis"] = thesis.__dict__

    regime_class = MarketRegimeClassifier.classify(df) if df is not None else "UNKNOWN"
    di_spread = abs(plus_di - minus_di) if plus_di is not None else 0
    location_quality = "mid"
    initial_conf = ConfidenceEngine.calculate_initial_confidence(score, narrative.get("narrative_score", 0), regime_class, market_state["adx"], di_spread, location_quality)

    if df is not None:
        smart_money = SmartMoneyEngine.analyze_smart_money(df)
        momentum = MomentumFlowEngine.analyze_momentum_flow(df)
        dominance_weight = 0.7 if smart_money["smart_money_dominant"] else 0.3
        initial_conf += (dominance_weight - 0.5) * 12
        if momentum["trend_expansion"]:
            initial_conf += 8
        if momentum["momentum_decay"]:
            initial_conf -= 12
        dist_risk = smart_money["distribution_risk"] / 100.0
        initial_conf -= dist_risk * 15
        if smart_money["retail_euphoria"]:
            initial_conf -= 10
        continuation_strength = momentum.get("continuation_strength", 50)
        initial_conf = ConfidenceEngine.apply_institutional_modifiers(initial_conf, smart_money, momentum, continuation_strength)
        initial_conf = max(0, min(95, initial_conf))

    intent_info = MEMORY.get(f"intent_{symbol}", {})
    intent_score = intent_info.get("score", 0)
    if intent_score >= 85:
        initial_conf += 15
    elif intent_score >= 75:
        initial_conf += 10
    initial_conf = min(100, initial_conf)

    STATE["current_confidence"] = initial_conf
    STATE["market_regime"] = regime_class

    if PAPER_MODE:
        paper["position"] = {"side": side, "entry": price, "qty": qty, "remaining_qty": qty}
        STATE.update({
            "open": True, "side": side, "entry": price, "qty": qty, "remaining_qty": qty,
            "sl": sl, "current_symbol": symbol, "tp1_done": False, "trail_activated": False,
            "peak": 0.0, "atr": atr_val, "entry_time": time.time(), "entry_reasons": [reason],
            "trade_score": score, "partial_closed": False, "tp1_price": tp1, "tp2_price": tp2,
            "trade_type": trade_type, "entry_type": entry_type, "be_done": False,
            "tp1_hit": False, "tp2_hit": False, "trail_stop": 0.0,
            "smart_tightened": False, "smart_partial_done": False, "smart_exit_triggered": False,
            "roe_pct": 0.0, "mark_price": price,
            "narrative_classification": STATE.get("narrative_classification", ""),
            "narrative_confidence": STATE.get("narrative_confidence", 0.0),
            "confidence_level": STATE.get("confidence_level", ""),
            "trade_thesis": thesis.__dict__,
            "current_confidence": initial_conf,
            "market_regime": regime_class,
            "adx_live": market_state["adx"],
            "di_plus_live": plus_di if plus_di else 0,
            "di_minus_live": minus_di if minus_di else 0,
            "trade_personality": "NEUTRAL",
            "institutional_flow": "NEUTRAL",
            "synthetic_sl": sl, "synthetic_tp1": tp1,
            "max_price": price, "min_price": price,
            "peak_roe": 0.0, "peak_price": price,
            "peak_unrealized_pnl": 0.0, "drawdown_from_peak": 0.0,
            "tp1_hold_score": 10, "exit_warning": 0,
            "runner_mode": False, "entry_atr": atr_val
        })
        TRADE_STATE.update({
            "in_position": True, "symbol": symbol, "side": side, "entry": price, "qty": qty,
            "tp1_hit": False, "trail_on": False, "last_update_ts": time.time()
        })
        _live_manager.start_trade(symbol, side, price, qty, sl, tp1, tp2)
        _live_manager.set_entry_atr(atr_val)  # Forces → LIVE here
        STATE["dynamic_manager"] = DynamicTradeManager(symbol, side, price, qty, atr_val, sl, tp1, tp2)
        update_position_dashboard(symbol, side, price, qty)
        log_execution(f"PAPER {entry_type} {side} {qty:.6f} @ {price} | {reason}", "SUCCESS")
        try:
            tg_entry(side, symbol, price, sl, tp1, score, reason, entry_type)
        except:
            pass
        return True

    sym = normalize_symbol(symbol)
    market = ex.market(sym)
    min_qty = market['limits']['amount']['min']
    if qty < min_qty:
        log_execution(f"SKIP: qty {qty:.6f} below minimum {min_qty}", "WARN")
        return False
    precision = market['precision']['amount']
    qty = math.floor(qty / precision) * precision
    if qty <= 0:
        log_execution(f"SKIP: qty rounded to zero", "WARN")
        return False
    order = open_position(side, qty, symbol)
    if order:
        STATE.update({
            "open": True, "side": side, "entry": price, "qty": qty, "remaining_qty": qty,
            "sl": sl, "current_symbol": symbol, "tp1_done": False, "trail_activated": False,
            "peak": 0.0, "atr": atr_val, "entry_time": time.time(), "entry_reasons": [reason],
            "trade_score": score, "partial_closed": False, "tp1_price": tp1, "tp2_price": tp2,
            "trade_type": trade_type, "entry_type": entry_type, "be_done": False,
            "tp1_hit": False, "tp2_hit": False, "trail_stop": 0.0,
            "smart_tightened": False, "smart_partial_done": False, "smart_exit_triggered": False,
            "roe_pct": 0.0, "mark_price": price,
            "narrative_classification": STATE.get("narrative_classification", ""),
            "narrative_confidence": STATE.get("narrative_confidence", 0.0),
            "confidence_level": STATE.get("confidence_level", ""),
            "trade_thesis": thesis.__dict__,
            "current_confidence": initial_conf,
            "market_regime": regime_class,
            "adx_live": market_state["adx"],
            "di_plus_live": plus_di if plus_di else 0,
            "di_minus_live": minus_di if minus_di else 0,
            "trade_personality": "NEUTRAL",
            "institutional_flow": "NEUTRAL",
            "synthetic_sl": sl, "synthetic_tp1": tp1,
            "max_price": price, "min_price": price,
            "peak_roe": 0.0, "peak_price": price,
            "peak_unrealized_pnl": 0.0, "drawdown_from_peak": 0.0,
            "tp1_hold_score": 10, "exit_warning": 0,
            "runner_mode": False, "entry_atr": atr_val
        })
        TRADE_STATE.update({
            "in_position": True, "symbol": symbol, "side": side, "entry": price, "qty": qty,
            "tp1_hit": False, "trail_on": False, "last_update_ts": time.time()
        })
        _live_manager.start_trade(symbol, side, price, qty, sl, tp1, tp2)
        _live_manager.set_entry_atr(atr_val)  # Forces → LIVE here
        STATE["dynamic_manager"] = DynamicTradeManager(symbol, side, price, qty, atr_val, sl, tp1, tp2)
        update_position_dashboard(symbol, side, price, qty)
        log_execution(f"LIVE {entry_type} {side} {qty:.6f} @ {price} | {reason}", "SUCCESS")
        try:
            tg_entry(side, symbol, price, sl, tp1, score, reason, entry_type)
        except:
            pass
        time.sleep(1)
        sync_position_state(symbol)
        return True
    else:
        return False

# ========== MAIN LOOP ==========
def main_loop_sniper():
    global INSUFFICIENT_MARGIN_COOLDOWN_UNTIL, _last_queue_promote, _last_queue_eval
    last_scan = 0
    last_scanner_v2 = 0
    last_radar_scan = 0
    last_radar_refresh = 0
    last_candidate_scan = 0
    last_flow_update = 0
    last_universe_build = 0
    last_discovery_scan = 0
    last_priority_update = 0
    watchlist_rotation = None
    try:
        ex.load_markets()
        log_execution(f"Markets loaded", "INFO")
    except Exception as e:
        log_execution(f"Failed to load markets: {e}", "ERROR")
    try:
        tg_start(get_balance_safe(), "LIVE" if MODE_LIVE else "PAPER")
    except:
        pass
    run_scanner_v2()
    updater_thread = threading.Thread(target=live_institutional_updater, daemon=True, name="live_institutional_updater")
    updater_thread.start()

    _last_queue_promote = time.time()
    _last_queue_eval = time.time()

    while True:
        try:
            now = time.time()
            sync_all_states()

            if now - last_discovery_scan > GLOBAL_SCAN_INTERVAL:
                global_discovery_scan()
                last_discovery_scan = now

            if now - last_priority_update > 300:
                WatchlistPriorityManager.update_priorities()
                last_priority_update = now

            if USE_EXECUTION_QUEUE:
                if now - _last_queue_promote > QUEUE_PROMOTE_INTERVAL:
                    promote_to_queue()
                    _last_queue_promote = now
                if now - _last_queue_eval > QUEUE_RE_EVAL_INTERVAL:
                    queue.re_evaluate_all(lambda sym: get_ohlcv_safe(sym, 100))
                    _last_queue_eval = now
                if not (STATE.get("open") or TRADE_STATE.get("in_position")):
                    process_queue_entry()
                if now % 60 < 1:
                    queue.cleanup()

            if now - last_universe_build > 1800:
                universe = build_40_symbol_universe()
                watchlist_rotation = WatchlistRotation(universe)
                last_universe_build = now

            if now - last_flow_update > 60:
                update_institutional_flow_scanner()
                last_flow_update = now

            if not (TRADE_STATE["in_position"] or STATE["open"]):
                sync_position_state()
                if STATE.get("open"):
                    continue
            if TRADE_STATE["in_position"] or STATE["open"]:
                _live_manager.manage_live_trade()
            else:
                if INSUFFICIENT_MARGIN_COOLDOWN_UNTIL and time.time() < INSUFFICIENT_MARGIN_COOLDOWN_UNTIL:
                    time.sleep(1)
                    continue
                if now - last_scan >= GLOBAL_SCAN_INTERVAL:
                    cands = scan_market_rf(top_n=40)
                    MEMORY["top_candidates"] = cands
                    MEMORY["rf_watchlist"] = cands[:30]
                    build_rf_dashboard()
                    MEMORY["last_scan"] = now
                    MEMORY["scanned_count"] = len(cands)
                    last_scan = now
                if now - last_scanner_v2 >= SCANNER_V2_INTERVAL:
                    run_scanner_v2()
                    last_scanner_v2 = now
                if SNIPER_MODE:
                    if now - last_radar_scan >= SCAN_INTERVAL:
                        rebuild_radar_watchlist()
                        last_radar_scan = now
                    if now - last_radar_refresh >= WATCHLIST_REFRESH:
                        refresh_radar_watchlist()
                        last_radar_refresh = now
                if not (INSUFFICIENT_MARGIN_COOLDOWN_UNTIL and time.time() < INSUFFICIENT_MARGIN_COOLDOWN_UNTIL):
                    if now - last_candidate_scan >= CANDIDATE_SCAN_INTERVAL:
                        smart_opportunity_selection()
                        last_candidate_scan = now
                    time.sleep(1)
                else:
                    time.sleep(1)
                continue
            if STATE["open"] and STATE.get("current_symbol"):
                sym = STATE["current_symbol"]
                price = get_ticker_safe(sym)
                if price and price > 0:
                    df = get_ohlcv_safe(sym, 50)
                    if df is not None:
                        if council_exit(df, price):
                            finalize_trade_with_reality(sym)
                            clear_position_dashboard()
                            STATE["open"] = False
                            TRADE_STATE["in_position"] = False
                            continue
                        atr = compute_atr(df).iloc[-1]
                        scaling_logic(sym, df, None)
                        current_pnl = STATE.get("roe_pct", 0.0)
                        update_position_dashboard(sym, STATE["side"], STATE["entry"], STATE["qty"], current_pnl)
            if emergency_kill_switch_active():
                if STATE["open"]:
                    close_position_full()
                    clear_position_dashboard()
                    TRADE_STATE["in_position"] = False
                time.sleep(60)
                continue
            print_snapshot()
            hourly_cleanup()
            time.sleep(BASE_SLEEP)
        except Exception as e:
            log_execution(f"Main loop error: {traceback.format_exc()}", "ERROR")
            time.sleep(BASE_SLEEP)

main_loop = main_loop_sniper

def safe_main_loop():
    while True:
        try:
            main_loop()
        except Exception as e:
            tb = traceback.format_exc()
            print(f"CRITICAL EXCEPTION: {tb}")
            try:
                log_execution(f"CRITICAL EXCEPTION: {tb}", "ERROR")
            except Exception as log_err:
                print(f"Failed to log: {log_err}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=safe_main_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False, use_reloader=False)
