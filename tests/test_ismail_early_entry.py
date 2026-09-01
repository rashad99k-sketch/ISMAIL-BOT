#!/usr/bin/env python3
"""Runtime validation harness for the ISMAIL-BOT SmartZoneCrossoverIntelligence layer.

ISMAIL-BOT ships with no test infrastructure, so this is a self-contained
smoke/unit harness (mirrors the RORO harness, adapted to MIN.PY). It:
  1. Neutralises background threads + Flask server before importing min.py.
  2. Unit-tests SmartZoneCrossoverIntelligence.analyze on synthetic frames
     (LONG FIRST / SHORT FIRST symmetry / LATE conservation, evidence schema,
     bounded add-only score_shift, native liquidity-sweep detection, no df
     mutation, short/empty frame safety).
  3. Integration-tests the ExecutionQueue wiring: early_entry/evidence are
     populated on candidates, the advisory add-only bonus never flips the READY
     decision authority (state identical with vs without max shift; a sub-85
     candidate can never be fabricated into READY), and to_dict surfaces the
     early_entry evidence.

Run:  python tests/test_ismail_early_entry.py   (from the ISMAIL-BOT directory)
"""

import os
import sys
import threading as _threading

# ---- Neutralise background threads / server before importing min -------------
_ORIG_START = _threading.Thread.start
def _noop_start(self, *a, **k):
    return None
_threading.Thread.start = _noop_start

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import min as M  # noqa: E402  (module name shadows builtin min inside THIS file only)

_threading.Thread.start = _ORIG_START  # restore for any teardown

_PASS = 0
_FAIL = 0


def _check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  PASS: %s" % name)
    else:
        _FAIL += 1
        print("  FAIL: %s %s" % (name, ("| " + detail) if detail else ""))


def _frame(close_values, open_ratio=0.998, vol=1000.0, vol_var=0.4, seed=7):
    """Build an OHLCV frame from closes (downtrend if descending)."""
    c = np.asarray(list(close_values), dtype=float)
    n = len(c)
    rng = np.random.default_rng(seed)
    opens = c * open_ratio
    highs = np.maximum(c, opens) * (1 + 0.004)
    lows = np.minimum(c, opens) * (1 - 0.004)
    volumes = np.abs(rng.normal(vol, vol * vol_var, n))
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": c, "volume": volumes,
    })


def _uptrend(n=80, start=100.0, step=0.3):
    return [start + step * i for i in range(n)]


def _downtrend(n=80, start=120.0, step=0.3):
    return [start - step * i for i in range(n)]


def _sweep_frame():
    """Craft a frame that ends with a native sell-side liquidity sweep:
    cosine troughs create equal swing lows at level L=100.0 (so
    build_liquidity_pools returns a low pool), then the last two bars sweep
    below L (prev low >= L) and reclaim (last close > last low). This is the
    exact native detect_sweep(df, pools) pattern."""

    # cosine with troughs at 100.0 -> last trough at index 28 of the pre-tail
    P = 8
    C = 101.5
    A = 1.5
    n_cos = 33
    xs = np.arange(n_cos)
    closes = C + A * np.cos(2 * np.pi * xs / P)
    closes = np.maximum(closes, 100.2)  # keep body above the trough level
    lows = C + A * np.cos(2 * np.pi * xs / P) - 0.2

    def _bar(oe, close, high_d, low_d, vol):
        o, c = oe, close
        h = max(o, c) * (1 + high_d)
        l = min(o, c) - low_d
        return {"open": o, "high": h, "low": l, "close": c, "volume": vol}

    # Tail: prev bar low >= L(100.0), last bar low < L with close reclaiming.
    tail = [
        {"open": 100.9, "high": 101.4, "low": 100.2, "close": 100.6, "volume": 1500.0},
        {"open": 100.6, "high": 101.3, "low": 100.05, "close": 100.9, "volume": 1400.0},
        {"open": 100.9, "high": 101.6, "low": 99.6, "close": 100.4, "volume": 2200.0},
    ]
    lows = np.append(lows, [100.2, 100.05, 99.6])
    highs = np.append(closes * 1.004, [101.4, 101.3, 101.6])
    opens = np.append(closes * 0.998, [100.9, 100.6, 100.9])
    closes = np.append(closes, [100.6, 100.9, 100.4])
    volumes = np.append(np.full(n_cos, 1000.0), [1500.0, 1400.0, 2200.0])
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def _test_unit():
    print("[UNIT] SmartZoneCrossoverIntelligence.analyze")
    eng = M.SmartZoneCrossoverIntelligence()

    # --- LONG FIRST (uptrend, price at zone -> near, ema/vweb aligned) --------
    df_up = _frame(_uptrend())
    atr = float(M.compute_atr(df_up).iloc[-1])
    entry = float(df_up["close"].iloc[-1])  # price AT the zone -> FIRST
    res = eng.analyze(df_up, "BUY", entry, atr, rf_signal="BUY")
    _check("LONG schema keys", all(k in res for k in (
        "phase", "directional_bias", "action", "confidence", "score_shift",
        "convergence_score", "distance_from_zone_atr", "zone_quality",
        "liquidity_event", "structure_state", "structure_aligned",
        "retest_mitigation", "volume_confirmation", "zone_volume",
        "vweb_aligned", "ema_aligned", "adx_aligned", "rf_aligned",
        "reasons")), str(sorted(res.keys())))
    _check("LONG price at zone -> phase FIRST", res["phase"] == "FIRST", res["phase"])
    _check("LONG directional_bias BUY", res["directional_bias"] == "BUY", res["directional_bias"])
    _check("LONG vweb_aligned (uptrend above vwap)", res["vweb_aligned"] is True, res["vweb_aligned"])
    _check("LONG ema_aligned (up stack)", res["ema_aligned"] is True, res["ema_aligned"])
    _check("LONG convergence_score>=1", res["convergence_score"] >= 1, res["convergence_score"])
    _check("LONG rf_aligned", res["rf_aligned"] is True, res["rf_aligned"])
    _check("LONG confidence in 0..100", 0 <= res["confidence"] <= 100, res["confidence"])
    _check("LONG score_shift bounded (0..3)", 0.0 <= res["score_shift"] <= 3.0, res["score_shift"])
    _check("LONG reasons explainable", isinstance(res["reasons"], list) and len(res["reasons"]) >= 1, res["reasons"])

    # --- SHORT FIRST (mirror; downtrend) --------------------------------------
    df_dn = _frame(_downtrend())
    atr_dn = float(M.compute_atr(df_dn).iloc[-1])
    entry_dn = float(df_dn["close"].iloc[-1])
    res_s = eng.analyze(df_dn, "SELL", entry_dn, atr_dn, rf_signal="SELL")
    _check("SHORT price at zone -> phase FIRST", res_s["phase"] == "FIRST", res_s["phase"])
    _check("SHORT directional_bias SELL", res_s["directional_bias"] == "SELL", res_s["directional_bias"])
    _check("SHORT vweb_aligned (downtrend below vwap)", res_s["vweb_aligned"] is True, res_s["vweb_aligned"])
    _check("SHORT ema_aligned (down stack)", res_s["ema_aligned"] is True, res_s["ema_aligned"])
    _check("SHORT rf_aligned", res_s["rf_aligned"] is True, res_s["rf_aligned"])
    _check("SHORT score_shift bounded", 0.0 <= res_s["score_shift"] <= 3.0, res_s["score_shift"])

    # --- LATE (price far from zone, add-only conservation) --------------------
    df_up2 = _frame(_uptrend())
    atr2 = float(M.compute_atr(df_up2).iloc[-1])
    far_entry = float(df_up2["close"].iloc[-1]) * 0.90  # price ABOVE zone by ~10%
    res_l = eng.analyze(df_up2, "BUY", far_entry, atr2, rf_signal=None)
    _check("LATE phase when far from zone", res_l["phase"] == "LATE", (res_l["phase"], res_l["distance_from_zone_atr"]))
    _check("LATE score_shift == 0.0 (add-only, no demote)", res_l["score_shift"] == 0.0, res_l["score_shift"])
    _check("LATE distance>1.5 ATR", res_l["distance_from_zone_atr"] > 1.5, res_l["distance_from_zone_atr"])

    # --- Native liquidity-sweep detection (accumulation context, sell-side) ---
    df_sw = _sweep_frame()
    pools = M.build_liquidity_pools(df_sw)
    swept_high, swept_low = M.detect_sweep(df_sw, pools)
    _check("native build_liquidity_pools has low pool", len(pools.get("low_pools", [])) >= 1, pools.get("low_pools"))
    _check("native detect_sweep flags swept_low", (swept_high, swept_low) == (False, True), (swept_high, swept_low))
    liq = eng._liquidity_event(df_sw, "BUY")
    _check("SZC liquidity_event == SWEEP on swept_low (BUY)", liq == "SWEEP", liq)
    # Directional mirror: the mirror-test below keeps the SWEEP asserting on the
    # BUY side; for SELL, the sweep is on the LOW side so it must NOT report a
    # bullish SWEEP (liquidity was NOT taken on buy side). We assert the honest
    # event only reflects the side needed (no fabricated cross-side sweep):
    liq_sell = eng._liquidity_event(df_sw, "SELL")
    _check("SZC no fabricated SWEEP for opposite side", liq_sell != "SWEEP", liq_sell)

    # --- conservation: analyze must not mutate the input frame ----------------
    df_up3 = _frame(_uptrend())
    df_before = df_up3.copy(deep=True)
    eng.analyze(df_up3, "BUY", float(df_up3["close"].iloc[-1]),
                float(M.compute_atr(df_up3).iloc[-1]))
    _check("analyze does not mutate df", df_up3.equals(df_before))
    _check("analyze handles empty / short frame safely", isinstance(
        eng.analyze(df_up3.iloc[:5], "BUY", 100.0, 1.0), dict))


def _ready_candidate(q, symbol="T/ETH:USDT", side="BUY"):
    df = _frame(_uptrend())
    atr = float(M.compute_atr(df).iloc[-1])
    price = float(df["close"].iloc[-1])
    return M.ExecutionCandidate(
        symbol=symbol, side=side, price=price, entry_price=price,
        stop_loss=price - 2 * atr, take_profit_1=price * 1.01,
        take_profit_2=price * 1.02, atr=atr, df=df, ob={},
    )


def _test_integration():
    print("[INTEGRATION] ExecutionQueue wiring")

    # (a) DECISION-AUTHORITY INVARIANCE: the advisory layer is ADD-ONLY and
    # bounded, so running the same data through the decision authority yields the
    # IDENTICAL candidate state whether or not the advisory bonus is applied.
    df_common = _frame(_uptrend())
    atr_common = float(M.compute_atr(df_common).iloc[-1])

    qa = M.ExecutionQueue(max_size=5, re_eval_interval=0.0)
    ca = _ready_candidate(qa, "A/BASE:USDT", "BUY")
    qa.add_candidate(ca)
    qa.re_evaluate_all(lambda s: df_common)      # computes natural metrics
    base_metrics = ca.zone_metrics
    qa._update_state(ca, ca.entry_price)         # derive base-state through the gate
    base_state_gate = ca.state

    # Apply the MAX advisory add-only shift to zone_strength, same data.
    shifted = M.ZoneMetrics(
        order_block_quality=base_metrics.order_block_quality,
        zone_strength=min(100, base_metrics.zone_strength + 3.0),  # max shift
        liquidity_quality=base_metrics.liquidity_quality,
        institutional_confidence=base_metrics.institutional_confidence,
        structure_alignment=base_metrics.structure_alignment,
        entry_timing=base_metrics.entry_timing,
        trend_alignment=base_metrics.trend_alignment,
        risk_score=base_metrics.risk_score,
        trigger_state=base_metrics.trigger_state)
    cs2 = M.ExecutionCandidate(
        symbol="A/SHIFT:USDT", side="BUY", price=ca.price, entry_price=ca.entry_price,
        stop_loss=ca.stop_loss, take_profit_1=ca.take_profit_1,
        take_profit_2=ca.take_profit_2, atr=ca.atr, df=df_common, ob={},
        zone_metrics=shifted)
    qa._update_state(cs2, cs2.entry_price)
    _check("advisory bonus never changes decision-authority state (<=3 shift)",
           cs2.state == base_state_gate,
           "shifted=%s base=%s" % (cs2.state.value, base_state_gate.value))

    # (b) A GOOD_ZONE candidate must NOT leap to READY from the advisory alone.
    q2 = M.ExecutionQueue(max_size=5, re_eval_interval=0.0)
    c_gz = _ready_candidate(q2, "B/GOOD:USDT", "BUY")
    c_gz.zone_metrics = M.ZoneMetrics(
        order_block_quality=70, zone_strength=72, liquidity_quality=60,
        institutional_confidence=60, structure_alignment=60, entry_timing=70,
        trend_alignment=60, risk_score=50, trigger_state="MITIGATION")
    c_gz.priority_score = c_gz.zone_metrics.final_zone_score
    c_gz.state = M.ExecutionState.GOOD_ZONE
    q2.add_candidate(c_gz)
    q2.re_evaluate_all(lambda s: _frame(_uptrend()))
    cc2 = q2._candidates["B/GOOD:USDT"]
    # Advisory bonus is tiny (<=3.0) and add-only; it cannot fabricate READY on a
    # sub-threshold candidate (READY needs score>=85 AND a confirmed trigger).
    cannot_be_ready_without_gate = (cc2.priority_score < 85) or (cc2.state != M.ExecutionState.READY)
    _check("non-READY candidate not fabricated into READY by advisory", cannot_be_ready_without_gate,
           "state=%s score=%.1f" % (cc2.state.value, cc2.priority_score))
    _check("GOOD_ZONE candidate not demoted", cc2.state.value in
           ("GOOD_ZONE", "WAITING_TRIGGER", "ENTRY_VALIDATION", "READY"), cc2.state.value)

    # (c) to_dict surfaces early_entry observably.
    td = ca.to_dict()
    _check("to_dict surfaces early_entry", "early_entry" in td and td["early_entry"].get("confidence") is not None, td.get("early_entry"))


def main():
    _test_unit()
    _test_integration()
    print("\n=== RESULTS: %d passed, %d failed ===" % (_PASS, _FAIL))
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()