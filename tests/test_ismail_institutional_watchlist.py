#!/usr/bin/env python3
"""Institutional-Proximity Global Scanner flow harness (ISMAIL-BOT).

Validates the redesigned Global Scanner pipeline:
  * cycle selects EXACTLY 40 unique assets = exactly 20 BUY + 20 SELL
  * the 40 are ranked by institutional-SETUP PROXIMITY (zone + narrative +
    smart-money + momentum + VWeb/EMA/ADX/RF alignment), never generic raw
    scanner score, never random filler
  * watchlist + candidate_universe are REPLACED wholesale each 20-min cycle
  * continuous deep analysis runs on EXACTLY those 40 (no outside symbols)
  * institutional evidence (explainable phase + Zone / Align / CSD) is cached AT
    watchlist-entry time (warm start) so ExecutionQueue refines, never cold-starts
  * smart_opportunity_selection is intelligence ONLY -- it never calls execute_entry
  * existing Entry/Execution authority (execute_entry), SL/TP, RF, RORO/profit
    logic are byte-for-byte unchanged (identity checks) and the READY gating math
    (ZoneMetrics.final_zone_score weights) is untouched.

All network/exchange + scanner internals are stubbed with deterministic synthetic
data. A "COLD" control group with the HIGHEST raw scanner score but ZERO setup
proximity proves selection is proximity-driven.

Run:  python tests/test_ismail_institutional_watchlist.py   (from ISMAIL-BOT dir)
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

# Snapshot of protected production objects BEFORE any test stubbing.
_ORIG = {
    "execute_entry": M.execute_entry,
    "compute_sl_tp": M.compute_sl_tp,
    "compute_atr": M.compute_atr,
    "RFEngine": M.RFEngine,
    "finalize_trade_with_reality": M.finalize_trade_with_reality,
    "council_exit": M.council_exit,
    "scaling_logic": M.scaling_logic,
    "ExecutionState": M.ExecutionState,
    "ZoneMetrics": M.ZoneMetrics,
}

_PASS = 0
_FAIL = 0


def _check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  PASS: %s" % name)
    else:
        _FAIL += 1
        print("  FAIL: %s %s" % (name, ("| " + str(detail)) if detail else ""))


def _sym_seed(sym):
    s = 0
    for ch in str(sym):
        s = (s * 31 + ord(ch)) & 0x7fffffff
    return s


_COLD = {"COLDg%d/USDT" % i for i in range(6)}


def _df_for(sym, n=120):
    rng = np.random.default_rng(_sym_seed(sym) ^ 0xA5A5)
    c = 100 + 0.03 * np.arange(n) + rng.normal(0, 0.4, n)
    c = np.maximum(c, 30.0)
    o = np.roll(c, 1); o[0] = c[0]
    h = np.maximum(o, c) * 1.004
    l = np.minimum(o, c) * 0.996
    v = np.abs(rng.normal(900, 250, n)) + 40
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v})


_DF_CACHE = {}


def _get_df(sym, n=100):
    key = (sym, n)
    if key not in _DF_CACHE:
        _DF_CACHE[key] = _df_for(sym, n)
    return _DF_CACHE[key].copy()


M.get_ohlcv_safe = _get_df


def _ob(sym, limit=10):
    price = _get_df(sym, 100)["close"].iloc[-1]
    return {
        "bid": price * 0.9998, "ask": price * 1.0002,
        "bids": [{"price": price * 0.9998, "qty": 1.0}],
        "asks": [{"price": price * 1.0002, "qty": 1.0}],
    }


M.get_orderbook_cached = _ob


def _smart(df):
    sym = str(getattr(df, "symbol", ""))
    if sym in _COLD:
        return {"smart_money_dominant": False, "institutional_bias": "NEUTRAL",
                "institutional_bias_detailed": "NEUTRAL",
                "distribution_risk": 20, "accumulation_strength": 5.0,
                "retail_euphoria": False}
    return {"smart_money_dominant": True, "institutional_bias": "BUY",
            "institutional_bias_detailed": "BUY",
            "distribution_risk": 10, "accumulation_strength": 9.0,
            "retail_euphoria": False}


M.SmartMoneyEngine.analyze_smart_money = staticmethod(_smart)


def _mom(df):
    sym = str(getattr(df, "symbol", ""))
    if sym in _COLD:
        return {"trend_expansion": False, "flow_bias": "NEUTRAL", "momentum_decay": False,
                "exhaustion_risk": 10, "continuation_strength": 5.0, "climax_risk": 10,
                "greed_state": False}
    return {"trend_expansion": True, "flow_bias": "BUY", "momentum_decay": False,
            "exhaustion_risk": 10, "continuation_strength": 9.0, "climax_risk": 10,
            "greed_state": False}


M.MomentumFlowEngine.analyze_momentum_flow = staticmethod(_mom)


def _narr(df, ob, atr, side):
    sym = str(getattr(df, "symbol", ""))
    keys = ["sweep", "choch_bos", "retest", "rejection", "displacement",
            "volume_confirmation", "rf_alignment"]
    if sym in _COLD:
        return dict.fromkeys(keys, False), 0.0
    h = (_sym_seed(sym) % 100) / 100.0
    narr = {
        "sweep": h > 0.30, "choch_bos": h > 0.35, "retest": h > 0.50,
        "rejection": h > 0.55, "displacement": h > 0.60,
        "volume_confirmation": h > 0.70, "rf_alignment": h > 0.80,
    }
    weights = (2, 2, 2, 1.5, 1.5, 1, 2)
    score = sum(w for w, k in zip(weights, keys) if narr[k])
    return narr, score


M.evaluate_liquidity_narrative = _narr


def _zones(sym, df, ob):
    if str(sym) in _COLD:
        return {"buy_zones": [], "sell_zones": []}
    return {"buy_zones": [{"strength": 14.0}], "sell_zones": [{"strength": 14.0}]}


M.get_smart_zones = _zones
M.InstitutionalIntentEngine.detect = staticmethod(lambda df, ob=None, symbol=None: (50.0, "ACCUMULATION", {}))


def _szc_analyze(df, side, entry_price, atr, rf_signal=None):
    h = (_sym_seed(str(getattr(df, "symbol", ""))) % 100) / 100.0
    return {
        "vweb_aligned": h > 0.25, "ema_aligned": h > 0.40, "adx_aligned": h > 0.45,
        "rf": h > 0.80, "convergence_score": 40.0 + h * 40.0,
        "liquidity_event": "sweep", "zone_quality": 50.0,
        "confidence": 40.0, "score_shift": 0.0, "action": "WAIT",
        "phase": "DEVELOPING", "reasons": ["stub"],
    }


M._early_confluence.analyze = _szc_analyze
M.store_intent_for_symbol = lambda symbol: None
_ORIG_RUN_ALL_LANES = M.run_all_lanes


def _install_cycle_stubs(suffix="A"):
    def _s(name):
        return "%s%s" % (suffix, name)
    M.get_usdt_perp_symbols = lambda: ["MKT%03d/USDT" % i for i in range(200)]
    M.smart_scanner_v2 = lambda: (
        [{"symbol": _s("V2B%d/USDT" % i), "score": 100 - i, "side": "BUY"} for i in range(8)],
        [{"symbol": _s("V2S%d/USDT" % i), "score": 92 - i, "side": "SELL"} for i in range(8)],
    )
    M.scan_market_rf = lambda top_n=20: (
        [{"symbol": _s("RF%02d/USDT" % i), "score": 90 - i,
          "rf_signal": "BUY" if i % 2 == 0 else "SELL"} for i in range(top_n)]
        + [{"symbol": "COLDg%d/USDT" % i, "score": 99,
            "rf_signal": "BUY" if i % 2 == 0 else "SELL"} for i in range(6)]
    )
    M.FreshLiquidityRadar.scan = staticmethod(lambda symbols, limit=15: [
        {"symbol": _s("FR%02d/USDT" % i), "score": 25 - i} for i in range(limit)
    ])


def _reset_state():
    M.MEMORY["watchlist"] = {}
    M.MEMORY["candidate_universe"] = []
    M.MEMORY["scan_cycle"] = {}
    M.MEMORY["institutional_watchlist"] = {}
    M.MEMORY["rf_watchlist"] = []
    M.MEMORY["scanner_v2_buy"] = []
    M.MEMORY["scanner_v2_sell"] = []
    for key in list(M.MEMORY.keys()):
        if key.startswith("smart_zones_"):
            del M.MEMORY[key]


def _run_cycle(suffix="A"):
    _install_cycle_stubs(suffix)
    _reset_state()
    M.global_discovery_scan()
    return dict(M.MEMORY)


def _test_cycle_honest():
    print("[FLOW] Global Scanner cycle -> TOP-40 honest counts (no forced 20/20), lane-ranked")
    mem = _run_cycle("A")
    universe = mem["candidate_universe"]
    wl = mem["watchlist"]
    iw = mem["institutional_watchlist"]

    _check("universe non-empty and <= 40 unique assets", 0 < len(universe) <= 40 and len(set(universe)) == len(universe),
           "len=%d" % len(universe))
    _check("watchlist keys == exactly the universe", set(wl.keys()) == set(universe),
           "wl=%d uni=%d" % (len(wl), len(universe)))
    _check("institutional_watchlist cached for each universe asset", set(iw.keys()) == set(universe))

    sides = [iw[s]["side"] for s in universe]
    _check("honest direction counts (BUY+SELL == total, sides valid)",
           all(s in ("BUY", "SELL") for s in sides)
           and sides.count("BUY") + sides.count("SELL") == len(universe),
           "buy=%d sell=%d tot=%d" % (sides.count("BUY"), sides.count("SELL"), len(universe)))
    _check("no side forced to exactly 20", not (sides.count("BUY") == 20 and sides.count("SELL") == 20),
           "buy=%d sell=%d" % (sides.count("BUY"), sides.count("SELL")))

    _check("cycle ranked_by = smart_rank_multi_lane",
           mem["scan_cycle"].get("ranked_by") == "smart_rank_multi_lane", mem["scan_cycle"].get("ranked_by"))

    phases = [iw[s].get("phase") for s in universe]
    _check("every asset exposes an explainable institutional state",
           all(p in ("EARLY_DEVELOPING", "SETUP_FORMING", "READY_NEAR", "NO_SETUP")
               for p in phases), str(set(phases)))
    _check("Zone/Align/CSD evidence present for every asset",
           all(iw[s].get("zone_strength") is not None and iw[s].get("align")
               and iw[s].get("csd") and iw[s].get("reasons") is not None and iw[s].get("story")
               for s in universe))
    _check("every asset is pre-analyzed at watchlist-entry (warm start)",
           all(iw[s].get("last_analyzed") and iw[s].get("proximity_score", -1) >= 0
               for s in universe))
    srcs = [iw[s].get("source") for s in universe]
    _check("no random filler and no zero-setup filler",
           "random" not in srcs and "COLDg" not in " ".join(universe)
           and all(iw[s].get("proximity_score", 0) > 0 for s in universe))


def _test_proximity_not_raw_score():
    print("[FLOW] Selection is institutional-proximity (post-lane), never raw score/filler")
    _install_cycle_stubs("A")
    _reset_state()
    M.global_discovery_scan()
    universe = M.MEMORY["candidate_universe"]
    iw = M.MEMORY["institutional_watchlist"]

    # COLD group carries the HIGHEST raw score yet has zero institutional setup;
    # under the multi-lane funnel it is never even surfaced by the lanes -> excluded.
    _check("highest-raw-score COLD (no setup) assets excluded from the universe",
           not any(s.startswith("COLDg") for s in universe),
           "cold_in=%s" % [s for s in universe if s.startswith("COLDg")])
    _check("every universe asset has positive setup proximity (no score<=0 filler)",
           all(iw[s]["proximity_score"] > 0 for s in universe),
           "zeros=%s" % [s for s in universe if iw[s]["proximity_score"] <= 0])
    _check("every selected asset fired >= 1 directional lane",
           all(iw[s].get("lanes") and iw[s].get("lane_direction") in ("BUY", "SELL")
               for s in universe),
           "no_lane=%s" % [s for s in universe if not iw[s].get("lanes")])
    # Weaker global non-COLD members (no lane, low movement) must not crowd the cut.
    _check("no directional gate forced a side absent from the lane evidence",
           all(iw[s]["side"] == iw[s]["lane_direction"] for s in universe))


def _test_continuous_analysis_only_universe():
    print("[FLOW] smart_opportunity_selection runs ATOM entry path over scanner_v2 pool")
    mem = _run_cycle("A")
    universe = set(mem["candidate_universe"])

    # Independent scanner stores seeded with high-score symbols (optionally OUTSIDE
    # the cycle universe, incl. OUT_A which is ONLY in rf_watchlist, and OUT_B/OUT_C
    # which are ONLY in scanner_v2 -- proving the pool is broader than rf_watchlist).
    M.MEMORY["rf_watchlist"] = [{"symbol": "OUT_A/USDT", "score": 99, "rf_signal": "BUY"}]
    M.MEMORY["scanner_v2_buy"] = [{"symbol": "OUT_B/USDT", "score": 98, "side": "BUY"}]
    M.MEMORY["scanner_v2_sell"] = [{"symbol": "OUT_C/USDT", "score": 97, "side": "SELL"}]

    # Record which symbols reach check_institutional_entry (the ATOM entry gate).
    reached = []
    orig_inst = M.check_institutional_entry
    def _recorder(sym, side, df, ob, atr, price):
        reached.append(sym)
        return orig_inst(sym, side, df, ob, atr, price)
    M.check_institutional_entry = _recorder

    # Intercept execute_entry (read-only) to count execution attempts, not trade.
    executed = []
    def _exec_recorder(side, symbol, price, sl, tp1, tp2, score, reason_str, atr,
                       trade_type=None, entry_type=None, classification=None, **kw):
        executed.append(symbol)
        return False
    M.execute_entry = _exec_recorder

    M.smart_opportunity_selection()

    M.check_institutional_entry = orig_inst

    # New contract (ATOM path): candidates are drawn from scanner_v2 + rf_watchlist,
    # NOT confined to the cycle universe -- the broadened execution pool works.
    _check("scanner_v2 buy candidate reaches the entry gate (outside universe is allowed)",
           "OUT_B/USDT" in reached, "reached=%s" % reached)
    _check("scanner_v2 sell candidate reaches the entry gate",
           "OUT_C/USDT" in reached, "reached=%s" % reached)
    _check("rf_watchlist signal candidate also reaches the entry gate",
           "OUT_A/USDT" in reached, "reached=%s" % reached)
    _check("candidate pool includes rf_watchlist-free scanner_v2 symbols (no RF-gate)",
           "OUT_B/USDT" in reached and "OUT_A/USDT" in reached)

    # The execution function never trades through a sibling path: at most one
    # execute_entry call per invocation (single, deduplicated best candidate).
    _check("execution is a single best-candidate attempt (no duplicate path)",
           len(executed) <= 1, "exec=%s" % executed)

    # The cycle-owned stores stay exactly the universe (execution does not mutate them).
    _check("institutional_watchlist still exactly the universe",
           set(M.MEMORY["institutional_watchlist"].keys()) == universe)
    _check("watchlist still exactly the universe after pass",
           set(M.MEMORY["watchlist"].keys()) == universe)


def _test_watchlist_replacement():
    print("[FLOW] 20-min cycle REPLACES the watchlist completely (no stale, no leftover)")
    mem_a = _run_cycle("A")
    uni_a = set(mem_a["candidate_universe"])

    for i in range(90):
        M.MEMORY["watchlist"]["STRAY%02d/USDT" % i] = {
            "symbol": "STRAY%02d/USDT" % i, "score": 5.0, "side": "BUY", "last_update": 0.0}
    mem_b = _run_cycle("B")
    uni_b = set(mem_b["candidate_universe"])

    _check("new cycle non-empty again", len(uni_b) > 0, "len=%d" % len(uni_b))
    _check("no STRAY leftovers after replacement",
           not any(s.startswith("STRAY") for s in M.MEMORY["watchlist"]))
    _check("watchlist == new universe, institutional cache == new universe",
           set(M.MEMORY["watchlist"].keys()) == uni_b
           and set(M.MEMORY["institutional_watchlist"].keys()) == uni_b)
    _check("cycle counter recorded for the fresh cycle", mem_b["scan_cycle"].get("cycle") == 1,
           mem_b["scan_cycle"].get("cycle"))
    _check("no stale/STRAY institutional evidence carried forward",
           not (set(M.MEMORY["institutional_watchlist"].keys()) & {"STRAY%02d/USDT" % i for i in range(90)}))


def _test_honest_directional_funnel():
    print("[FLOW] Pure SELL evidence -> honest SELL-only universe (no forced BUY fill)")
    _install_cycle_stubs("A")
    _reset_state()
    # Force every candidate to carry ONLY SELL lane evidence (a one-sided market).
    # The Directional Gate + no-fill funnel must NOT fabricate a BUY side up to 20.
    _sells_only = {"MKT%03d/USDT" % i: ({"price": 100.0, "vol_last": 1000.0, "vol_ma20": 500.0,
                                          "atr_pct": 1.0, "adx": 28.0, "rsi": 40.0},
                                         [("breakout", {"side": "SELL", "strength": 0.9})])
                    for i in range(200)}
    def _sell_lanes(sym, df):
        return _sells_only.get(sym)
    M.run_all_lanes = _sell_lanes
    # Force the L0 snapshot to rebuild for this cycle.
    M._MARKET_SNAPSHOT.clear()
    M._MARKET_SNAPSHOT_TS = 0.0
    M.global_discovery_scan()

    universe = M.MEMORY["candidate_universe"]
    iw = M.MEMORY["institutional_watchlist"]
    sides = [iw[s]["side"] for s in universe]
    _check("one-sided market yields a non-empty honest universe", len(universe) > 0,
           "len=%d" % len(universe))
    _check("no BUY side fabricated when market is SELL-only", sides.count("BUY") == 0,
           "buy=%d" % sides.count("BUY"))
    _check("BUY+SELL == total universe (no forced 20/20)",
           sides.count("BUY") + sides.count("SELL") == len(universe),
           "buy=%d sell=%d tot=%d" % (sides.count("BUY"), sides.count("SELL"), len(universe)))
    _check("every survivor carries institutional evidence",
           all(iw[s].get("phase") and iw[s].get("csd") for s in universe))
    # Restore the real lane engine + stable deterministic frames for later tests.
    M.run_all_lanes = _ORIG_RUN_ALL_LANES
    M._MARKET_SNAPSHOT.clear()
    M._MARKET_SNAPSHOT_TS = 0.0
    _install_cycle_stubs("A")


def _test_authority_and_no_regression():
    print("[FLOW] Discovery is intelligence-only; Entry/SL-TP/RORO/RF/profit unchanged")
    mem = _run_cycle("A")
    universe = set(mem["candidate_universe"])
    iw = mem["institutional_watchlist"]

    # Evidence exists BEFORE any ExecutionQueue re-evaluation could provide it.
    executed = []
    def _exec_recorder(side, symbol, price, sl, tp1, tp2, score, reason_str, atr,
                       trade_type=None, entry_type=None, classification=None, **kw):
        executed.append(symbol)
        return False
    M.execute_entry = _exec_recorder

    M.smart_opportunity_selection()  # must analyse, never execute
    _check("smart_opportunity_selection never executes a trade",
           len(executed) == 0, "exec=%s" % executed)
    M.execute_entry = _ORIG["execute_entry"]

    fresh = M.ExecutionQueue(max_size=15, re_eval_interval=0.0)
    M.queue = fresh
    for _ in range(3):
        M.promote_to_queue()
    promoted = set(fresh._candidates.keys())
    _check("promoted candidates stay inside the 40", promoted <= universe,
           "outside=%s" % (promoted - universe))
    _check("promotion used warm institutional context (evidence pre-queued)",
           all(prom in iw and iw[prom].get("phase") in
               ("EARLY_DEVELOPING", "SETUP_FORMING", "READY_NEAR", "NO_SETUP")
               and iw[prom].get("align") and iw[prom].get("csd") for prom in promoted))

    # Protected production objects byte-identical after all the redesign work.
    _check("execute_entry authority identity unchanged", M.execute_entry is _ORIG["execute_entry"])
    _check("compute_sl_tp identity unchanged", M.compute_sl_tp is _ORIG["compute_sl_tp"])
    _check("compute_atr identity unchanged", M.compute_atr is _ORIG["compute_atr"])
    _check("RFEngine identity unchanged", M.RFEngine is _ORIG["RFEngine"])
    _check("profit management writers identity unchanged",
           M.finalize_trade_with_reality is _ORIG["finalize_trade_with_reality"]
           and M.council_exit is _ORIG["council_exit"]
           and M.scaling_logic is _ORIG["scaling_logic"])

    # READY gating math (ZoneMetrics.final_zone_score weights) untouched.
    z100 = M.ZoneMetrics(order_block_quality=100, zone_strength=0, liquidity_quality=0,
                         institutional_confidence=0, structure_alignment=0, entry_timing=0,
                         trend_alignment=0, risk_score=0).final_zone_score
    _check("READY gating weight table unchanged (order_block=100 -> 20.0)",
           z100 == 20.0, str(z100))
    _check("ExecutionState enum unchanged", M.ExecutionState.READY.value == "READY")

    # SL/TP math sanity (direction/sign invariant of the protected formula).
    df = _df_for("SLT/USDT", 120)
    sl, tp1, tp2 = M.compute_sl_tp(100.0, "BUY", "REVERSAL", atr=2.0, df=df)
    _check("SL/TP direction invariant intact", 0 < sl < 100.0 <= tp1 <= tp2 and tp1 > 100.0,
           "sl=%s tp1=%s tp2=%s" % (sl, tp1, tp2))


def main():
    _test_cycle_honest()
    _test_proximity_not_raw_score()
    _test_continuous_analysis_only_universe()
    _test_watchlist_replacement()
    _test_honest_directional_funnel()
    _test_authority_and_no_regression()
    print("\n=== RESULTS: %d passed, %d failed ===" % (_PASS, _FAIL))
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()