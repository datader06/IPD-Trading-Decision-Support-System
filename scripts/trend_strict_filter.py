"""Experimental rule (user, 5 Oct 2026): take a trade only if the trend is IN FAVOUR: demand needs an UP trend, supply needs a DOWN trend.

The legacy filter (mtf_zones.filter_zones_by_trend_3tf) only blocks a confirmed COUNTER-trend (demand in down, supply in up), so SIDEWAYS passes.
This script labels every already-taken trade with the trend at its HTF zone formation (same functions, same trend frame, same flags as the run),
checks that no trade is counter-trend (it must reproduce the legacy filter), then keeps only up/down-aligned trades. No strategy re-run, no network.
Usage: python scripts/trend_strict_filter.py <dit15|wit|mit> [--strict-htf]   (--workers=N, default 3)
"""
import multiprocessing as mp
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
COMBO = [a for a in sys.argv[1:] if not a.startswith("--")][0]
SRC = {"dit15": ("results/4d02f6d/trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv", "kite_frames_dit15_long"),
       "wit": ("results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv", "kite_frames_wit_long"),
       "mit": ("results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv", "kite_frames")}[COMBO]
FRAMES = ROOT / "data" / "cache" / SRC[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _base_flags  # noqa: E402  (sets DZ_STRICT_HTF etc. from argv, same as the run)
_base_flags.resolve()
mtz = sz = None


def _low_priority():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _init():
    global mtz, sz
    _low_priority()
    sys.path.insert(0, str(LEGACY / "code"))
    sys.path.insert(0, str(ROOT / "src"))
    import offline_loader
    offline_loader.install(data_dir=str(FRAMES))
    import mtf_zones as _m
    import sd_zones as _s
    import base_candles as _b
    if COMBO == "dit15":
        _m.COMBOS["dit15"] = replace(_m.COMBOS["dit"], ltf_interval="15m", ltf_resample=None, ltf_source="intraday",
                                     ltf_fetch_period="1400d", trend_fetch_period="1400d", htf_window=None)
    elif COMBO == "wit":
        _m.COMBOS["wit"] = replace(_m.COMBOS["wit"], trend_window=None)
    elif COMBO == "mit":
        _m.COMBOS["mit"] = replace(_m.COMBOS["mit"], ltf_window=None)
    _b.install(_s, _m)
    mtz, sz = _m, _s


def _work(args):
    ticker, rows = args
    spec = mtz.COMBOS[COMBO]
    trend_df = mtz._build_frame(ticker, spec.trend_source, spec.trend_interval, spec.trend_fetch_period, spec.trend_resample, spec.trend_window)
    zones = mtz.detect_zones(trend_df, config=spec.trend_config, allow_wick_to_wick=False)
    events = mtz._compute_trend_events(trend_df, zones)
    return [(i, mtz._classify_trend_from_events(trend_df, events, pd.Timestamp(hf))) for i, hf in rows]


def boot_ci(w, n):
    x = np.random.default_rng(12345).binomial(n, w / n, 5000) / n
    lo, hi = np.percentile(x, [2.5, 97.5])
    return f"{100 * lo:.0f}-{100 * hi:.0f}"


def main():
    arg = [a.split("=")[1] for a in sys.argv if a.startswith("--workers=")]
    workers = int(arg[0]) if arg else 3
    _low_priority()
    src = ROOT / SRC[0]
    d = pd.read_csv(src, parse_dates=["entry_time", "htf_formed_at"])
    jobs = [(t, [(i, r.htf_formed_at) for i, r in g.iterrows()]) for t, g in d.groupby("ticker")]
    lab = {}
    with mp.Pool(workers, initializer=_init) as pool:
        for part in pool.imap_unordered(_work, jobs, chunksize=1):
            lab.update(dict(part))
    d["trend_label"] = [lab[i] for i in d.index]
    d["trend_aligned"] = ((d.type == "demand") & (d.trend_label == "up")) | ((d.type == "supply") & (d.trend_label == "down"))
    counter = ((d.type == "demand") & (d.trend_label == "down")) | ((d.type == "supply") & (d.trend_label == "up"))
    out = src.with_name(src.stem + "_trendlabels.csv")
    d.to_csv(out, index=False)
    print(f"{COMBO}: {len(d)} trades; trend labels {d.trend_label.value_counts(dropna=False).to_dict()}")
    print(f"sanity (legacy filter must have removed all counter-trend trades): counter-trend trades found = {int(counter.sum())} (expect 0)")
    print(f"aligned (demand+up / supply+down) = {int(d.trend_aligned.sum())}, sideways/none = {int((~d.trend_aligned & ~counter).sum())}")
    a = d.exit_outcome == "AMBIGUOUS"
    d["fo"] = np.where(a, d.outcome, d.exit_outcome)
    d["fr"] = np.where(a, np.where(d.fo == "win", 2.0, -1.0), d.exit_r)
    d["fp"] = d.fr * d.shares * d.risk

    def row(l, s):
        n = len(s)
        if n == 0:
            print(f"  {l:28} n=0")
            return
        w = int((s.fo == "win").sum())
        print(f"  {l:28} n={n:3} W={w:3} L={n - w:3} {100 * w / n:5.1f}% [{boot_ci(w, n) if w else '0-0'}] avgR={s.fr.mean():+.3f} Rs={s.fp.sum():+,.0f}" + (" <30" if n < 30 else ""))
    for wl, m in (("2021+", d.entry_time >= "2021-01-01"), ("2024+", d.entry_time >= "2024-01-01")):
        s = d[m]
        print(f"\n{COMBO} {wl}")
        row("all trades (current rule)", s)
        row("trend-aligned only (NEW rule)", s[s.trend_aligned])
        row("sideways only (removed)", s[~s.trend_aligned])
        k = s[s.trend_aligned]
        row("  NEW train (<2026)", k[k.entry_time < "2026-01-01"])
        row("  NEW holdout (2026)", k[k.entry_time >= "2026-01-01"])
        for y in range(max(2021, int(s.entry_time.dt.year.min())), 2027):
            row(f"  NEW year {y}", k[k.entry_time.dt.year == y])
        xa, xb = (k.fo == "win").values, (s[~s.trend_aligned].fo == "win").values
        if len(xa) and len(xb):
            rng = np.random.default_rng(5)
            ds = np.array([rng.choice(xa, len(xa)).mean() - rng.choice(xb, len(xb)).mean() for _ in range(4000)]) * 100
            print(f"  aligned minus sideways win%: {100 * (xa.mean() - xb.mean()):+.1f} pts, boot95 [{np.percentile(ds, 2.5):+.0f},{np.percentile(ds, 97.5):+.0f}]")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
