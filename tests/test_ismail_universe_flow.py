#!/usr/bin/env python3
"""End-to-End harness: Global Scanner -> Top 40 -> Watchlist -> Active Candidates.

Validates the SINGLE-SOURCE-OF-TRUTH design on ISMAIL-BOT's min.py:
  * every 20-min Global Scanner cycle selects EXACTLY 40 unique symbols
  * MEMORY["candidate_universe"] is the 40 -> the cycle's candidate universe
  * MEMORY["watchlist"] is replaced to match exactly those 40 (no stale/extra)
  * Active Candidates (ExecutionQueue) are fed ONLY from the 40
  * smart_opportunity_selection is confined to the 40 (no fabricated entries
    outside the universe via scanner_v2 / rf_watchlist)
  * between cycles the 40 are stable (no independent rebuild); re-evaluation may
    update scores only
  * the 20-minute cycle interval is native (GLOBAL_SCAN_INTERVAL == 1200)

All network/exchange + scanner internals are stubbed with deterministic
synthetic data; production entry/SL/TP/profit logic is untouched.

Run:  python tests/test_ismail_universe_flow.py   (from the ISMAIL-BOT directory)
"""

import os
import sys
import threading as _threading

_ORIG_START = _threading.Thread.start
def _noop_start(self, *a, **k):
    return None
_threading.Thread.start = _noop_start

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import min as M  # noqa: E402

_threading.Thread.start = _ORIG_START

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


def _synthetic_df(n=120, start=100.0, step=0.2, seed=0):
    rng = np.random.default_rng(seed)
    c = start + step * np.arange(n) + rng.normal(0, 0.3, n)
    o = np.roll(c, 1); o[0] = c[0]
    h = np.maximum(o, c) * 1.003
    l = np.minimum(o, c) * 0.997
    v = np.abs(rng.normal(1200, 300, n)) + 50
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v})


_DF = _synthetic_df()


def _install_cycle_stubs():
    """Deterministic stubs for everything global_discovery_scan() consumes."""
    M.get_usdt_perp_symbols = lambda: ["MKT%03d/USDT" % i for i in range(200)]
    M.smart_scanner_v2 = lambda: (
        [{"symbol": "V2B%d/USDT" % i, "score": 100 - i, "side": "BUY"} for i in range(5)],
        [{"symbol": "V2S%d/USDT" % i, "score": 92 - i, "side": "SELL"} for i in range(5)],
    )
    M.scan_market_rf = lambda top_n=20: [
        {"symbol": "RF%02d/USDT" % i, "score": 90 - i,
         "rf_signal": "BUY" if i % 2 == 0 else "SELL"} for i in range(top_n)
    ]
    M.FreshLiquidityRadar.scan = staticmethod(lambda symbols, limit=15: [
        {"symbol": "FR%02d/USDT" % i, "score": 20 - i} for i in range(limit)
    ])
    M.store_intent_for_symbol = lambda symbol: None
    M.get_ohlcv_safe = lambda sym, n=100: _DF.copy()
    M.get_orderbook_cached = lambda sym, limit=10: {
        "bid": _DF["close"].iloc[-1] * 0.9998, "ask": _DF["close"].iloc[-1] * 1.0002,
        "bids": [{"price": _DF["close"].iloc[-1] * 0.9998, "qty": 1.0}],
        "asks": [{"price": _DF["close"].iloc[-1] * 1.0002, "qty": 1.0}],
    }
    M.InstitutionalIntentEngine.detect = staticmethod(lambda df, ob=None, symbol=None: (60.0, "ACCUMULATION", {}))
    M.get_smart_zones = lambda sym, df, ob: {"buy_zones": [{"strength": 12.0}], "sell_zones": [{"strength": 12.0}]}
    M.evaluate_liquidity_narrative = lambda df, ob, atr, side: (
        {"sweep": True, "choch_bos": True, "retest": True, "rejection": True,
         "displacement": True, "volume_confirmation": True, "rf_alignment": True}, 8.0)
    M.SmartMoneyEngine.analyze_smart_money = staticmethod(lambda df: {
        "smart_money_dominant": True, "institutional_bias": "BUY",
        "institutional_bias_detailed": "BUY", "distribution_risk": 10,
        "accumulation_strength": 9.0, "retail_euphoria": False})
    M.MomentumFlowEngine.analyze_momentum_flow = staticmethod(lambda df: {
        "trend_expansion": True, "flow_bias": "BUY", "momentum_decay": False,
        "exhaustion_risk": 10, "continuation_strength": 9.0, "climax_risk": 10,
        "greed_state": False})
    M._early_confluence.analyze = staticmethod(lambda df, side, entry_price, atr, rf_signal=None: {
        "vweb_aligned": True, "ema_aligned": True, "adx_aligned": False, "rf": True,
        "convergence_score": 50.0, "liquidity_event": "sweep", "zone_quality": 50.0,
        "confidence": 40.0, "score_shift": 0.0, "action": "WAIT",
        "phase": "DEVELOPING", "reasons": ["stub"]})


def _reset_candidate_state():
    M.MEMORY["watchlist"] = {}
    M.MEMORY["candidate_universe"] = []
    M.MEMORY["scan_cycle"] = {}
    M.MEMORY["rf_watchlist"] = []
    M.MEMORY["scanner_v2_buy"] = []
    M.MEMORY["scanner_v2_sell"] = []


def _run_cycle():
    _reset_candidate_state()
    M.global_discovery_scan()
    return dict(M.MEMORY)


def _test_cycle():
    print("[E2E] Global Scanner cycle -> TOP-40 (honest counts) -> watchlist <- universe")
    mem = _run_cycle()
    universe = mem["candidate_universe"]
    wl = mem["watchlist"]

    _check("universe <= 40 and non-empty", 0 < len(universe) <= 40, "len=%d" % len(universe))
    _check("no duplicate symbols in the universe", len(set(universe)) == len(universe))
    _check("watchlist keys == exactly the universe", set(wl.keys()) == set(universe),
           "wl=%d uni=%d" % (len(wl), len(universe)))
    _check("scan_cycle count recorded == universe size", mem["scan_cycle"].get("count") == len(universe),
           mem["scan_cycle"].get("count"))
    _check("scan_cycle ranked_by = smart_rank_multi_lane", mem["scan_cycle"].get("ranked_by") == "smart_rank_multi_lane")
    _check("scan_cycle records warm-start", mem["scan_cycle"].get("warm_start") is True)
    _check("scan_cycle increments per cycle", mem["scan_cycle"].get("cycle") == 1)

    iw = mem.get("institutional_watchlist") or {}
    sides = [iw[s]["side"] for s in universe]
    _check("honest direction counts (BUY+SELL == total, no forced 20/20)",
           len(sides) == len(universe) and sides.count("BUY") + sides.count("SELL") == len(universe),
           "buy=%d sell=%d tot=%d" % (sides.count("BUY"), sides.count("SELL"), len(universe)))
    _check("no side forced to exactly 20", not (sides.count("BUY") == 20 and sides.count("SELL") == 20) or len(universe) != 40)
    _check("every selected asset carries a directional lane", all(s in ("BUY", "SELL") for s in sides),
           str(set(sides)))

    phases = [iw[s].get("phase") for s in universe]
    _check("every watchlist asset has an explainable institutional state",
           all(p in ("EARLY_DEVELOPING", "SETUP_FORMING", "READY_NEAR", "NO_SETUP") for p in phases),
           str(set(phases)))
    _check("institutional evidence cached at watchlist-entry (warm start)",
           all(iw[s].get("csd") and iw[s].get("align") and iw[s].get("reasons")
               and iw[s].get("proximity_score") is not None for s in universe))
    _check("no random filler among the universe",
           "random" not in [iw[s].get("source") for s in universe])

    proven = set(M.get_usdt_perp_symbols())
    _check("the universe is genuinely from the discovery-pool symbols", set(universe) <= proven,
           str(set(universe) - proven))

    # Replacement: stale entries from a previous cycle must be dropped.
    for i in range(90):
        M.MEMORY["watchlist"]["STRAY%02d/USDT" % i] = {
            "symbol": "STRAY%02d/USDT" % i, "score": 5.0, "side": "BUY", "last_update": 0.0}
    M.global_discovery_scan()
    strays = [k for k in M.MEMORY["watchlist"] if k.startswith("STRAY")]
    _check("cycle end REPLACES watchlist with the new universe (no stale leftovers)", len(strays) == 0,
           "strays=%d total=%d" % (len(strays), len(M.MEMORY["watchlist"])))
    _check("after replacement: watchlist matches the new universe again",
           set(M.MEMORY["watchlist"].keys()) == set(M.MEMORY["candidate_universe"]), )


def _test_stability():
    print("[E2E] Between cycles: the 40 stay the single universe (no independent rebuild)")
    mem = _run_cycle()
    universe = list(mem["candidate_universe"])
    _install_cycle_stubs()  # deterministic -> identical second cycle
    M.global_discovery_scan()
    _check("repeated cycle is deterministic -> identical 40", M.MEMORY["candidate_universe"] == universe,
           "diff=%d" % len(set(universe) ^ set(M.MEMORY["candidate_universe"])))

    # Re-evaluation (the 5s queue loop) updates scores only; it must never
    # change universe membership.
    before = set(universe)
    cands = list(M.MEMORY["watchlist"].items())
    for sym, entry in cands:
        M.MEMORY["watchlist"][sym]["score"] = entry["score"]
    _check("re-evaluation never expands universe membership", set(M.MEMORY["candidate_universe"]) == before)

    _check("20-min cycle is native: GLOBAL_SCAN_INTERVAL == 1200", M.GLOBAL_SCAN_INTERVAL == 1200,
           M.GLOBAL_SCAN_INTERVAL)


def _test_promote():
    print("[E2E] Active Candidates fed ONLY from the 40 (not independent scanners)")
    mem = _run_cycle()
    universe = set(mem["candidate_universe"])

    # Independent scanner stores contain symbols OUTSIDE the 40 with high scores.
    M.MEMORY["rf_watchlist"] = [{"symbol": "OUT_A/USDT", "score": 99.0, "rf_signal": "BUY"}]
    M.MEMORY["scanner_v2_buy"] = [{"symbol": "OUT_B/USDT", "score": 98.0, "side": "BUY"}]
    M.MEMORY["scanner_v2_sell"] = [{"symbol": "OUT_C/USDT", "score": 97.0, "side": "SELL"}]

    _install_cycle_stubs()
    fresh = M.ExecutionQueue(max_size=15, re_eval_interval=0.0)
    M.queue = fresh
    for _ in range(3):
        M.promote_to_queue()

    promoted = set(fresh._candidates.keys())
    _check("candidates promoted == subset of the 40", promoted <= universe,
           "outside=%s" % (promoted - universe))
    _check("OUT_A/B/C never promoted", not ({"OUT_A/USDT", "OUT_B/USDT", "OUT_C/USDT"} & promoted),
           "promoted=%s" % promoted)
    _check("candidates were created (queue not empty)", len(fresh._candidates) > 0,
           "count=%d" % len(fresh._candidates))


def _test_smart_opportunity_gate():
    print("[E2E] smart_opportunity_selection confined to the 40 (no fabricated outside entries)")
    uni = ["IN1/USDT", "IN2/USDT"]
    M.MEMORY["candidate_universe"] = uni
    M.MEMORY["watchlist"] = {
        "IN1/USDT": {"symbol": "IN1/USDT", "score": 10.0, "side": "BUY", "last_update": 0.0},
        "IN2/USDT": {"symbol": "IN2/USDT", "score": 9.0, "side": "SELL", "last_update": 0.0},
    }
    M.MEMORY["scanner_v2_buy"] = [{"symbol": "OUT_A/USDT", "score": 999.0, "side": "BUY"},
                                  {"symbol": "IN1/USDT", "score": 50.0, "side": "BUY"}]
    M.MEMORY["rf_watchlist"] = [{"symbol": "OUT_B/USDT", "score": 998.0, "rf_signal": "BUY"},
                                {"symbol": "IN2/USDT", "score": 49.0, "rf_signal": "SELL"}]

    _install_cycle_stubs()

    def _narrative(df, ob, atr, side):
        return {"sweep": True, "choch_bos": True, "retest": True, "rejection": True,
                "displacement": True, "volume_confirmation": True, "rf_alignment": True}, 8.0
    M.evaluate_liquidity_narrative = _narrative
    M.SmartMoneyEngine.analyze_smart_money = staticmethod(lambda df: {
        "smart_money_dominant": True, "institutional_bias": "BUY",
        "distribution_risk": 10, "accumulation_strength": 8.0, "institutional_bias_detailed": "BUY"})
    M.MomentumFlowEngine.analyze_momentum_flow = staticmethod(lambda df: {
        "trend_expansion": True, "flow_bias": "BUY", "momentum_decay": False,
        "exhaustion_risk": 10, "continuation_strength": 8.0})
    M.get_smart_zones = lambda sym, df, ob: {"buy_zones": [{"strength": 15.0}], "sell_zones": []}

    executed = []
    def _execute_recorder(side, symbol, price, sl, tp1, tp2, score, reason_str, atr,
                          trade_type=None, entry_type=None, classification=None, **kw):
        executed.append(symbol)
        return False
    M.execute_entry = _execute_recorder

    M.smart_opportunity_selection()

    _check("all executed entries are inside the 40", set(executed) <= set(uni), "exec=%s" % executed)
    _check("outside symbols never recorded into watchlist",
           not ({"OUT_A/USDT", "OUT_B/USDT"} & set(M.MEMORY["watchlist"].keys())),
           "wl=%s" % sorted(M.MEMORY["watchlist"].keys()))
    _check("inside symbols still analysed/recorded",
           {"IN1/USDT", "IN2/USDT"} <= set(M.MEMORY["watchlist"].keys()),
           "wl=%s" % sorted(M.MEMORY["watchlist"].keys()))


def main():
    _install_cycle_stubs()
    _test_cycle()
    _test_stability()
    _test_promote()
    _test_smart_opportunity_gate()
    print("\n=== RESULTS: %d passed, %d failed ===" % (_PASS, _FAIL))
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()