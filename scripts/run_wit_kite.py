"""WIT on Kite frames: unmodified legacy pipeline (daily + 60m resampled to 2h by legacy code), multiprocessing.

Reads data/cache/kite_frames/{ticker}__1d.csv and __60m.csv. Entries kept: entry_time >= 2024-01-01 (explicit date).
Saves results/<hash>/trades_wit_kite_2024_heuristic.csv and prints heuristic summary.
"""
import json
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
_fr = [a.split("=")[1] for a in sys.argv if a.startswith("--frames=")]
FRAMES = ROOT / "data" / "cache" / (_fr[0] if _fr else "kite_frames")  # --frames=kite_frames_wit_long for a 2021 run
_from = [a.split("=")[1] for a in sys.argv if a.startswith("--from=")]
ENTRY_FROM = pd.Timestamp(_from[0] if _from else "2024-01-01")  # --from=YYYY-MM-DD
SPLIT = pd.Timestamp("2026-01-01")
SKIP = {"HFCL.NS"}
bt = None
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base_flags  # noqa: E402
TAG = _base_flags.resolve()  # "" = legacy base logic (--legacy-base); "_v2_cap5" = V2 default


def _low_priority():
    """Run below normal priority so the PC stays responsive (Windows only; ignored elsewhere)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _init():
    global bt
    _low_priority()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(LEGACY / "code"))
    import offline_loader  # legacy, unmodified
    offline_loader.install(data_dir=str(FRAMES))
    if TAG:
        sys.path.insert(0, str(ROOT / "src"))
        import base_candles, sd_zones, mtf_zones
        base_candles.install(sd_zones, mtf_zones)
    if _from:  # legacy WIT keeps only the last 750 daily bars for the trend frame (mtf_zones.py:254, trend_window=750): lift it for a long history
        from dataclasses import replace
        import mtf_zones as _mz
        _mz.COMBOS["wit"] = replace(_mz.COMBOS["wit"], trend_window=None)
    import mtf_backtest
    bt = mtf_backtest


def _work(t):
    try:
        return t, bt.build_trades_for_ticker(t, "wit", apply_trend_filter=True), None
    except Exception as e:
        return t, [], repr(e)[:80]


def git_hash():
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()


def boot_ci(wins, n, reps=5000):
    if n == 0:
        return "n/a"
    x = np.random.default_rng(12345).binomial(n, wins / n, reps) / n
    lo, hi = np.percentile(x, [2.5, 97.5])
    return f"[{100 * lo:.0f}-{100 * hi:.0f}]"


def line(label, d):
    res = d[d["outcome"].isin(["win", "loss"])]
    n, w = len(res), int((res["outcome"] == "win").sum())
    r = np.where(res["outcome"] == "win", 2.0, -1.0)
    return (f"{label}: n={len(d)} wins={w} losses={n - w} unresolved={len(d) - n} win%={100 * w / n if n else float('nan'):.1f} "
            f"boot95={boot_ci(w, n)} avgR={r.mean() if n else float('nan'):+.3f} totalRs={res['pnl'].sum():+,.0f}"
            + ("  SAMPLE<30" if len(d) < 30 else ""))


def main():
    tickers = [t for t in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if t not in SKIP]
    have = [t for t in tickers if (FRAMES / f"{t}__1d.csv").exists() and (FRAMES / f"{t}__60m.csv").exists()]
    arg = [a.split("=")[1] for a in sys.argv if a.startswith("--workers=")]
    workers = int(arg[0]) if arg else max(1, mp.cpu_count() // 2)  # default: half the cores
    _low_priority()
    print(f"universe (excl. HFCL.NS) {len(tickers)}, with 1d+60m Kite frames {len(have)}; workers {workers}", flush=True)
    print(f"filter used: entry_time >= pd.Timestamp('{ENTRY_FROM:%Y-%m-%d}'), no upper bound; trend filter ON; frames {FRAMES.name}" + ("; trend_window 750 -> None (mtf_zones.py:254) because --from was given" if _from else ""), flush=True)
    trades, errors = [], []
    with mp.Pool(workers, initializer=_init) as pool:
        for i, (t, tr, err) in enumerate(pool.imap_unordered(_work, have, chunksize=1), 1):
            trades += tr
            if err:
                errors.append((t, err))
            if i % 50 == 0:
                print(f"  pipeline {i}/{len(have)} tickers, {len(trades)} raw signals", flush=True)
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    raw = len(df)
    df = df[df["entry_time"] >= ENTRY_FROM].sort_values(["entry_time", "ticker"]).reset_index(drop=True)
    df["split"] = np.where(df["entry_time"] < SPLIT, "train", "holdout")
    out = ROOT / "results" / git_hash()
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"trades_wit_kite_2024{TAG}_heuristic.csv", index=False)
    print(f"\nerrors {len(errors)} {errors[:3]}; raw signals {raw}, kept {len(df)} (entry >= 2024-01-01)")
    print("\nWIT on Kite data, heuristic exit (win=+2R, loss=-1R, gross)")
    print(line("ALL    ", df))
    for y in (2024, 2025, 2026):
        print(line(f"YEAR {y}", df[df["entry_time"].dt.year == y]))
    print(line("TRAIN  ", df[df.split == "train"]))
    print(line("HOLDOUT", df[df.split == "holdout"]))
    print("per-year n add up:", sum((df["entry_time"].dt.year == y).sum() for y in (2024, 2025, 2026)), "of", len(df))


if __name__ == "__main__":
    main()
