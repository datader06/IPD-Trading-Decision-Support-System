"""DIT variant "dit15" on Kite frames: unmodified legacy pipeline with the combo spec overridden in this runner.

HTF daily (legacy window 750), trend 2h resampled by legacy code from the 60m frames, LTF = Kite 15m bars, no resampling.
Reads data/cache/kite_frames/{ticker}__1d.csv, __60m.csv, __15m.csv. Entries kept: entry_time >= 2024-01-01 (explicit date).
Saves results/<hash>/trades_dit15_kite_2024_heuristic.csv.
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
FRAMES = ROOT / "data" / "cache" / "kite_frames"
ENTRY_FROM = pd.Timestamp("2024-01-01")
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
    import mtf_zones as mtz
    from dataclasses import replace
    # Legacy "dit" (mtf_zones.py:236-245): ltf_interval="60m" (l.240), ltf_window=None (l.241), ltf_fetch_period="729d" (l.242),
    # trend_fetch_period="729d" (l.244), htf_window=750 (l.239). Overridden: LTF interval and the two fetch periods.
    # The fetch periods only cut history when fetching live (start = now - N days); the frozen loader ignores them, so
    # all frame data from 2023-01-01 is used. 1400d (> 1371 days since 2023-01-01) is set to document that intent.
    mtz.COMBOS["dit15"] = replace(mtz.COMBOS["dit"], ltf_interval="15m", ltf_resample=None, ltf_source="intraday",
                                  ltf_fetch_period="1400d", trend_fetch_period="1400d")
    if TAG:  # after the dit15 override so the new configs reach dit15 too
        sys.path.insert(0, str(ROOT / "src"))
        import base_candles, sd_zones
        base_candles.install(sd_zones, mtz)
    import mtf_backtest
    bt = mtf_backtest


def _work(t):
    try:
        return t, bt.build_trades_for_ticker(t, "dit15", apply_trend_filter=True), None
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
    have = [t for t in tickers if (FRAMES / f"{t}__1d.csv").exists() and (FRAMES / f"{t}__60m.csv").exists() and (FRAMES / f"{t}__15m.csv").exists()]
    arg = [a.split("=")[1] for a in sys.argv if a.startswith("--workers=")]
    workers = int(arg[0]) if arg else max(1, mp.cpu_count() // 2)  # default: half the cores
    _low_priority()
    print(f"universe (excl. HFCL.NS) {len(tickers)}, with 1d+60m+15m Kite frames {len(have)}; workers {workers}", flush=True)
    print("filter used: entry_time >= pd.Timestamp('2024-01-01'), no upper bound; trend filter ON; trend 2h via legacy resampling, LTF 15m native", flush=True)
    trades, errors = [], []
    # Crash safety: each finished ticker is pickled to data/cache/checkpoints/dit15{TAG}/; a rerun skips finished tickers.
    # The folder is wiped if config.py or src/base_candles.py changed (different logic = different trades).
    import hashlib
    import pickle
    ck = ROOT / "data" / "cache" / "checkpoints" / f"dit15{TAG}"
    sig = hashlib.md5((ROOT / "config.py").read_bytes() + (ROOT / "src" / "base_candles.py").read_bytes()).hexdigest()
    if ck.exists() and (ck / "SIGNATURE").read_text() != sig:
        for f in ck.glob("*.pkl"):
            f.unlink()
    ck.mkdir(parents=True, exist_ok=True)
    (ck / "SIGNATURE").write_text(sig)
    safe = lambda t: t.replace("&", "_AMP_")  # noqa: E731
    done = {}
    for t in have:
        f = ck / f"{safe(t)}.pkl"
        if f.exists():
            done[t] = pickle.load(open(f, "rb"))
    for t, tr in done.items():
        trades += tr
    todo = [t for t in have if t not in done]
    print(f"checkpoint: {len(done)} tickers already done, {len(todo)} to run", flush=True)
    with mp.Pool(workers, initializer=_init) as pool:
        for i, (t, tr, err) in enumerate(pool.imap_unordered(_work, todo, chunksize=1), 1 + len(done)):
            trades += tr
            if err:
                errors.append((t, err))
            else:
                pickle.dump(tr, open(ck / f"{safe(t)}.pkl", "wb"))
            if i % 50 == 0:
                print(f"  pipeline {i}/{len(have)} tickers, {len(trades)} raw signals", flush=True)
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    raw = len(df)
    df = df[df["entry_time"] >= ENTRY_FROM].sort_values(["entry_time", "ticker"]).reset_index(drop=True)
    df["split"] = np.where(df["entry_time"] < SPLIT, "train", "holdout")
    out = ROOT / "results" / git_hash()
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"trades_dit15_kite_2024{TAG}_heuristic.csv", index=False)
    print(f"\nerrors {len(errors)} {errors[:3]}; raw signals {raw}, kept {len(df)} (entry >= 2024-01-01)")
    print("\nDIT15 on Kite data, heuristic exit (win=+2R, loss=-1R, gross)")
    print(line("ALL    ", df))
    for y in (2024, 2025, 2026):
        print(line(f"YEAR {y}", df[df["entry_time"].dt.year == y]))
    print(line("TRAIN  ", df[df.split == "train"]))
    print(line("HOLDOUT", df[df.split == "holdout"]))
    print("per-year n add up:", sum((df["entry_time"].dt.year == y).sum() for y in (2024, 2025, 2026)), "of", len(df))


if __name__ == "__main__":
    main()
