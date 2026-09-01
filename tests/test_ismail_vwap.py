#!/usr/bin/env python3
"""Verification harness: VWeb == the exact TradingView VWAP.

TradingView built-in VWAP:
    VWAP = cumsum(TypicalPrice * Volume) / cumsum(Volume)
    TypicalPrice = (High + Low + Close) / 3
    default anchor = "Session" (UTC day for crypto -> cumulative sums reset at
    each new UTC-day session boundary).

Tests compute_tv_session_vwap() equals a hand-computed session-anchored VWAP,
proves the UTC-day reset, proves it DIFFERS from plain window-cumulative VWAP
exactly when the window crosses a session boundary, and confirms
SmartZoneCrossoverIntelligence._vweb_aligned uses it as the VWeb alignment.

Run:  python tests/test_ismail_vwap.py   (from the ISMAIL-BOT directory)
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


def _norm(series):
    return float(np.asarray(series, dtype=float)[-1])


def _two_session_frame():
    d1 = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
    d2 = pd.Timestamp("2026-01-02 00:00:00", tz="UTC")
    def _ms(day, h):
        return int((day + pd.Timedelta(hours=h)).value // 1_000_000)
    rows = []
    prices = [100, 101, 102, 103]
    vols = [100, 200, 300, 400]
    for h, (p, v) in enumerate(zip(prices, vols)):
        rows.append([_ms(d1, h), p, p, p, p, v])
    prices2 = [104, 105, 106]
    vols2 = [500, 600, 700]
    for h, (p, v) in enumerate(zip(prices2, vols2)):
        rows.append([_ms(d2, h), p, p, p, p, v])
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def _test_formula_anchor():
    print("[VWAP] exact TradingView VWAP formula + Session/UTC-day anchor")
    df = _two_session_frame()

    tv = M.compute_tv_session_vwap(df)

    # Day-1 manual session VWAP (HLC3 == price here):
    # (100*100 + 101*200 + 102*300 + 103*400) / 1000 = 102.0
    d1_last = _norm(tv.iloc[:4])
    _check("day-1 session VWAP == manual 102.0", abs(d1_last - 102.0) < 1e-9, d1_last)

    # Day-2 manual session VWAP:
    # (104*500 + 105*600 + 106*700) / 1800 = 105.1111...
    expected_d2 = (104 * 500 + 105 * 600 + 106 * 700) / 1800.0
    d2_last = _norm(tv.iloc[4:])
    _check("day-2 session VWAP == manual %.6f" % expected_d2,
           abs(d2_last - expected_d2) < 1e-6, d2_last)

    # Plain window-cumulative VWAP over the same window:
    whole = (100*100 + 101*200 + 102*300 + 103*400 + 104*500 + 105*600 + 106*700) / 2800.0
    plain_last = _norm(M.compute_vwap(df))
    _check("plain cumulative differs precisely at session crossing (%s vs %.4f)"
           % (plain_last, expected_d2), abs(plain_last - whole) < 1e-9, plain_last)
    _check("TV VWAP resets at UTC-day boundary (not window-cumulative)",
           abs(plain_last - d2_last) > 1e-9, "plain=%.6f tv=%.6f" % (plain_last, d2_last))

    # Fallback: no 'timestamp' column -> identical to compute_vwap.
    df_nt = df.drop(columns=["timestamp"])
    _check("no-timestamp fallback == compute_vwap",
           np.allclose(M.compute_tv_session_vwap(df_nt), M.compute_vwap(df_nt)))

    # Zero-volume candle -> no NaN (forward-filled, exactly like TV skipping vol=0).
    dfz = df.copy()
    dfz.loc[len(dfz)] = [dfz.iloc[-1]["timestamp"] + 3600000, 107, 107, 107, 107, 0]
    tvz = M.compute_tv_session_vwap(dfz)
    _check("zero-volume candle is safe (no NaN)", not tvz.isna().any(), tvz.tail(2).tolist())


def _test_szc_evidence():
    print("[VWAP] SZC VWeb evidence uses the TradingView VWAP")
    eng = M.SmartZoneCrossoverIntelligence()

    # Uptrend, single session, price ends ABOVE its session VWAP.
    day = pd.Timestamp("2026-01-03 00:00:00", tz="UTC")
    n = 48
    ts = [int((day + pd.Timedelta(minutes=5 * i)).value // 1_000_000) for i in range(n)]
    closes = 100.0 + 0.1 * np.arange(n)
    df_up = pd.DataFrame({
        "timestamp": ts, "open": closes, "high": closes * 1.002,
        "low": closes * 0.998, "close": closes,
        "volume": np.full(n, 1000.0)})

    d = dict(df_up)  # BUY
    _check("BUY aligned above session VWAP", eng._vweb_aligned(df_up, "BUY") is True)
    _check("BUY not aligned below session VWAP", eng._vweb_aligned(df_up, "SELL") is False)

    # Downtrend below its session VWAP -> SELL side aligned.
    df_dn = df_up.copy()
    df_dn["close"] = closes[::-1]
    _check("SELL aligned below session VWAP", eng._vweb_aligned(df_dn, "SELL") is True)
    _check("SELL not aligned above session VWAP", eng._vweb_aligned(df_dn, "BUY") is False)

    # Full analyze() wiring with a session-aware frame (evidence + convergence).
    atr = float(M.compute_atr(df_up).iloc[-1])
    res = eng.analyze(df_up, "BUY", float(df_up["close"].iloc[-1]), atr, rf_signal="BUY")
    _check("analyze surfaces TV-VWAP-based vweb_aligned",
           res.get("vweb_aligned") is True and "vweb_aligned" in res, res.get("vweb_aligned"))


def main():
    _test_formula_anchor()
    _test_szc_evidence()
    print("\n=== RESULTS: %d passed, %d failed ===" % (_PASS, _FAIL))
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()