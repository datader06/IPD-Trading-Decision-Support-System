"""MIT on Kite daily frames: legacy pipeline (unmodified), entries >= 2024-01-01, heuristic exit.

Steps 3-6: needs data/cache/kite_frames (see fetch_kite_daily.py). Saves results/<hash>/trades_mit_kite_2024_heuristic.csv.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
sys.path.insert(0, str(LEGACY / "code"))
import offline_loader  # noqa: E402  (legacy, unmodified)

FRAMES = ROOT / "data" / "cache" / "kite_frames"
_from = [a.split("=")[1] for a in sys.argv if a.startswith("--from=")]
ENTRY_FROM = pd.Timestamp(_from[0] if _from else "2024-01-01")  # explicit date filter, not relative to today (--from=YYYY-MM-DD)
SPLIT = pd.Timestamp("2026-01-01")
SKIP = {"HFCL.NS"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base_flags  # noqa: E402
TAG = _base_flags.resolve()  # "" = legacy base logic (--legacy-base); "_v2_cap5" = V2 default


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
    unresolved = len(d) - n
    return (f"{label}: n={len(d)} wins={w} losses={n - w} unresolved={unresolved} "
            f"win%={100 * w / n if n else float('nan'):.1f} boot95={boot_ci(w, n)} "
            f"avgR={r.mean() if n else float('nan'):+.3f} totalRs={res['pnl'].sum():+,.0f}" + ("  SAMPLE<30" if len(d) < 30 else ""))


def main():
    tickers = [t for t in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if t not in SKIP]
    have = [t for t in tickers if (FRAMES / f"{t}__1d.csv").exists()]
    print(f"universe (excl. HFCL.NS) {len(tickers)}, with Kite frame {len(have)}")

    # item 5: >35% close-to-close moves (print only, nothing adjusted)
    moves = []
    for t in have:
        d = pd.read_csv(FRAMES / f"{t}__1d.csv", parse_dates=["timestamp"])
        ch = d["close"] / d["close"].shift(1) - 1
        for i in ch.index[ch.abs() > 0.35]:
            moves.append((t, d.loc[i, "timestamp"], d.loc[i - 1, "close"], d.loc[i, "close"], ch[i]))
    print(f"\nDAILY CLOSE MOVES > 35% vs previous close (likely splits/bonus, unadjusted): {len(moves)} ticker-days in {len({m[0] for m in moves})} tickers")
    for t, ts, p0, p1, c in sorted(moves, key=lambda m: (m[0], m[1])):
        print(f"  {t} {ts:%Y-%m-%d} {p0:.2f} -> {p1:.2f} ({100 * c:+.0f}%)")

    # item 3/4: legacy pipeline
    offline_loader.install(data_dir=str(FRAMES))
    if TAG:
        sys.path.insert(0, str(ROOT / "src"))
        import base_candles, sd_zones, mtf_zones  # noqa: E402
        base_candles.install(sd_zones, mtf_zones)
        print(f"BASE LOGIC V2 ON (LTF cap {__import__('os').environ.get('DZ_LTF_CAP', 'config default')})", flush=True)
    if _from:  # legacy MIT keeps only the last 750 daily bars (mtf_zones.py:261, ltf_window=750); drop that limit for a long history
        from dataclasses import replace
        import mtf_zones as _mz
        _mz.COMBOS["mit"] = replace(_mz.COMBOS["mit"], ltf_window=None)
        print("ltf_window override: 750 -> None (all daily history) because --from was given", flush=True)
    import mtf_backtest as bt  # noqa: E402
    print(f"\nlegacy LOOKBACK_DAYS['mit'] = {bt.LOOKBACK_DAYS['mit']} (mtf_backtest.py:43, applied only in main() lines 357-360); "
          f"this runner calls build_trades_for_ticker directly, so it is NOT applied.")
    print(f"filter used: entry_time >= pd.Timestamp('{ENTRY_FROM:%Y-%m-%d}'), no upper bound; trend filter " + ("OFF (--no-trend: counter-trend trades allowed)" if "--no-trend" in sys.argv else "ON (legacy main default)"))
    trades, errors = [], []
    for i, t in enumerate(have, 1):
        try:
            trades += bt.build_trades_for_ticker(t, "mit", apply_trend_filter=("--no-trend" not in sys.argv))
        except Exception as e:
            errors.append((t, repr(e)[:80]))
        if i % 50 == 0:
            print(f"  pipeline {i}/{len(have)} tickers, {len(trades)} raw signals", flush=True)
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    raw = len(df)
    df = df[df["entry_time"] >= ENTRY_FROM].sort_values(["entry_time", "ticker"]).reset_index(drop=True)
    df["split"] = np.where(df["entry_time"] < SPLIT, "train", "holdout")
    out = ROOT / "results" / git_hash()
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"trades_mit_kite_2024{TAG}_heuristic.csv", index=False)
    print(f"\nerrors {len(errors)} {errors[:3]}; raw signals {raw}, kept {len(df)} (entry >= 2024-01-01)")

    print("\nMIT on Kite daily, heuristic exit (win=+2R, loss=-1R, gross, no costs)")
    print(line("ALL    ", df))
    for y in (2024, 2025, 2026):
        print(line(f"YEAR {y}", df[df["entry_time"].dt.year == y]))
    print(line("TRAIN (<2026-01-01)", df[df.split == "train"]))
    print(line("HOLDOUT (2026)     ", df[df.split == "holdout"]))
    print("per-year n add up:", sum((df["entry_time"].dt.year == y).sum() for y in (2024, 2025, 2026)), "of", len(df))


if __name__ == "__main__":
    main()
