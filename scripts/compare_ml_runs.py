"""Cross-run leaderboard: puts every ML run (Experiment 1 primary / strict-HTF, Experiment 2 and any later ml_core run) on one table
with the same metrics and the same preregistered edge test, so models and deterministic-layer versions can be compared side by side.

  python scripts/compare_ml_runs.py [--out=results/ml_core/leaderboard.csv] [extra run dirs containing per_strategy.csv ...]

Read-only on every run folder. Edge test (rt0.20, pooled stream): >= 100 resolved takes, net expectancy > 0, expectancy above the 95th
percentile of matched random filters, and the month-block bootstrap interval of ML minus B1 above zero. Anything else = no edge.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXP1 = ROOT / "results" / "nogit-145d6302" / "phase_b" / "experiment_1"
COLS = ["n_taken", "n_resolved", "win_rate", "expectancy", "profit_factor", "total_r", "max_dd"]


def edge_rows(run, label, tbl, b2, boot):
    """tbl: columns arm, scenario + COLS (pooled stream). b2: {family: percentile}. boot: {family: ci_lo of ML minus B1}."""
    out = []
    for fam, pct in b2.items():
        r = tbl[(tbl.arm == f"ML:{fam}") & (tbl.scenario == "rt0.20")]
        if r.empty:
            continue
        r = r.iloc[0]
        a, b = (r.n_resolved or 0) >= 100, bool(r.expectancy > 0)
        c, d = bool(pct is not None and pct >= 0.95), bool(boot.get(fam) is not None and boot[fam] > 0)
        out.append(dict(run=run, label=label, family=fam, n_resolved=r.n_resolved, expectancy_rt020=r.expectancy,
                        random_filter_percentile=pct, boot_ci_lo_vs_B1=boot.get(fam), min_100_takes=a, expectancy_positive=b,
                        above_95th_random=c, boot_excludes_zero=d, edge_established=bool(a and b and c and d)))
    return out


def exp1(variant):
    pooled = pd.read_csv(EXP1 / "report" / f"{variant}_pooled.csv")
    pooled = pooled.rename(columns={"n_taken": "n_taken", "n_resolved": "n_resolved"})
    res = json.loads((EXP1 / variant / "results.json").read_text())
    b2 = {f: v.get("ml_expectancy_percentile") for f, v in res["b2"].items()}
    boot = pd.read_csv(EXP1 / "report" / f"{variant}_boot.csv")
    boot = boot[(boot.scenario == "rt0.20") & (boot.metric == "expectancy") & (boot.versus == "B1")]
    ci = {r.family: r.ci_lo for r in boot.itertuples()}
    return pooled, b2, ci


def main():
    rows, edge = [], []
    for variant, label in (("primary", "Experiment 1 primary (DIT15, Tier-1 features)"),
                           ("strict_htf", "Experiment 1 strict-HTF (DIT15 sensitivity)")):
        pooled, b2, ci = exp1(variant)
        t = pooled.assign(run=f"exp1_{variant}", label=label, strategy="DIT15")
        rows.append(t)
        edge += edge_rows(f"exp1_{variant}", label, pooled, b2, ci)
    runs = [Path(a) for a in sys.argv[1:] if not a.startswith("--")] or sorted((ROOT / "results" / "ml_core").glob("*_*"))
    for run in runs:
        if not (run / "per_strategy.csv").exists():
            continue
        s = json.loads((run / "summary.json").read_text())
        label = f"{run.name} (pooled {', '.join(s['meta'].get('families', []))}; features {s['feature_version']})"
        t = pd.read_csv(run / "per_strategy.csv").rename(columns={"n_resolved_taken": "n_resolved"})
        rows.append(t.assign(run=run.name, label=label))
        allt = t[t.strategy == "ALL"]
        bt = pd.read_csv(run / "bootstrap.csv")
        bt = bt[(bt.versus == "B1") & bt.arm.str.startswith("ML:")]
        ci = {r.arm.split(":", 1)[1]: r.ci_lo for r in bt.itertuples()}
        b2 = {f: v["ml_expectancy_percentile"] for f, v in s["b2"].items()}
        edge += edge_rows(run.name, label, allt, b2, ci)
    out = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), ROOT / "results" / "ml_core" / "leaderboard.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    long = pd.concat(rows, ignore_index=True)
    long[["run", "label", "strategy", "arm", "scenario"] + COLS].to_csv(out, index=False)
    e = pd.DataFrame(edge)
    e.to_csv(out.with_name("edge_check.csv"), index=False)
    pd.set_option("display.width", 220)
    print(e.drop(columns="label").round(3).to_string(index=False))
    print(f"\nwrote {out} and {out.with_name('edge_check.csv')}")


if __name__ == "__main__":
    main()
