"""Baseline v1 final lists. No network.

outcome_final = replay win/loss (source 15m or 1m); if still AMBIGUOUS -> saved legacy heuristic outcome (source heuristic).
A real replay outcome is never overwritten. R/Rs: replay trades use the replay R (gaps included); heuristic-scored use +2/-1.
Writes results/<HEAD>/baseline_v1_{dit15,wit,mit}.csv and prints the tables (also saved to baseline_v1_tables.txt).
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SRC = {"dit15": ROOT / "results/b47e89b/trades_dit15_kite_2024_final.csv",
       "wit": ROOT / "results/12d4238/trades_wit_kite_2024_final.csv",
       "mit": ROOT / "results/b47e89b/trades_mit_kite_2024_final.csv"}
REVIEW = {k: ROOT / f"results/b47e89b/review_{k}.csv" for k in SRC}
SPLIT = pd.Timestamp("2026-01-01")
SRC_NAME = {"15minute": "15m", "1minute": "1m"}


def boot_ci(wins, n, reps=5000):
    if n == 0:
        return "n/a"
    x = np.random.default_rng(12345).binomial(n, wins / n, reps) / n
    lo, hi = np.percentile(x, [2.5, 97.5])
    return f"{100 * lo:.0f}-{100 * hi:.0f}"


def build(key):
    d = pd.read_csv(SRC[key], parse_dates=["entry_time"])
    rv = pd.read_csv(REVIEW[key], parse_dates=["entry_time"])
    assert len(d) == len(rv) and set(zip(d.ticker, d.entry_time)) == set(zip(rv.ticker, rv.entry_time)), f"{key}: trade set differs from review file"
    real = d["exit_outcome"].isin(["win", "loss"])
    d["outcome_final"] = np.where(real, d["exit_outcome"], d["heuristic_outcome"])
    d["outcome_source"] = np.where(real, d["exit_interval"].map(SRC_NAME), "heuristic")
    assert d["outcome_final"].isin(["win", "loss"]).all(), f"{key}: unresolved trade after heuristic fallback"
    d["r_final"] = np.where(real, d["exit_r"], d["heuristic_r"])
    d["pnl_final"] = np.where(real, d["exit_pnl"], d["heuristic_pnl"])
    return d.sort_values("entry_time").reset_index(drop=True)


def line(label, d):
    n = len(d)
    w = int((d["outcome_final"] == "win").sum())
    l = int((d["outcome_final"] == "loss").sum())
    h = int((d["outcome_source"] == "heuristic").sum())
    assert w + l == n
    return (f"  {label:20} n={n:3} wins={w:3} losses={l:3} win%={100 * w / n if n else float('nan'):5.1f} boot95=[{boot_ci(w, n)}] "
            f"avgR={d['r_final'].mean() if n else float('nan'):+.3f} totalRs={d['pnl_final'].sum():+9,.0f} "
            f"heuristic-scored={h} ({100 * h / n if n else 0:.0f}% of n)" + ("  SAMPLE<30" if n < 30 else ""))


def main():
    h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    out_dir = ROOT / "results" / h
    out_dir.mkdir(parents=True, exist_ok=True)
    text = []
    for key in ("dit15", "wit", "mit"):
        d = build(key)
        d.to_csv(out_dir / f"baseline_v1_{key}.csv", index=False)
        src = d["outcome_source"].value_counts().to_dict()
        text.append(f"{key.upper()} ({len(d)} trades; source counts {src}; file results/{h}/baseline_v1_{key}.csv)")
        for lab, sub in (("ALL", d), ("2024", d[d.entry_time.dt.year == 2024]), ("2025", d[d.entry_time.dt.year == 2025]),
                         ("2026", d[d.entry_time.dt.year == 2026]), ("TRAIN (<2026-01-01)", d[d.entry_time < SPLIT]),
                         ("HOLDOUT (2026)", d[d.entry_time >= SPLIT])):
            text.append(line(lab, sub))
        text.append(f"  per-year n add up: {sum((d.entry_time.dt.year == y).sum() for y in (2024, 2025, 2026))} of {len(d)}")
        text.append("")
    txt = "\n".join(text)
    (out_dir / "baseline_v1_tables.txt").write_text(txt, encoding="utf-8")
    print(f"HEAD {h}\n" + txt)


if __name__ == "__main__":
    main()
