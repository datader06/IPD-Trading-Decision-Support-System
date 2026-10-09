"""Experiment 6: P&L-oriented ML (expected-R filter and ML sizing) on the final baseline v6. Offline, deterministic, 2026 holdout never used.

  python scripts/run_ml_pnl.py [--data=data/algo_v5/ml_dataset_baseline_v5.csv] [--tag=exp6_pnl] [--draws=10000]

Design and success criteria: docs/EXPERIMENT_6_PREREGISTRATION.md. Writes results/ml_core/<tag>_<sha8>/.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml_core import adapters as A  # noqa: E402
from ml_core import pnl as P  # noqa: E402
from ml_core import walkforward as W  # noqa: E402

TEST_YEARS = (2023, 2024, 2025)


def arg(name, default=None):
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


def main():
    t0 = time.time()
    path = Path(arg("data", str(A.DEFAULT_PATH)))
    df, excl, manifest = A.load_baseline_v5(path)
    raw = pd.read_csv(path, parse_dates=["entry_time"])[["combo", "ticker", "entry_time", "label_rs"]].rename(columns={"combo": "strategy", "label_rs": "rs"})
    df = df.merge(raw, on=["strategy", "ticker", "entry_time"], how="left")
    df = df[(df["strategy"] != "DIT15") | (df["legout_strength_score"] == 2)].reset_index(drop=True)  # baseline v6 (STATUS 19)
    dev = df[df["split"] != "holdout"].reset_index(drop=True)
    out = Path(arg("out", str(ROOT / "results" / "ml_core" / f"{arg('tag', 'exp6_pnl')}_{manifest['sha256'][:8]}")))
    out.mkdir(parents=True, exist_ok=True)
    oof = P.walk_forward_pnl(dev, A.FEATURE_COLUMNS, TEST_YEARS)
    oof.to_csv(out / "oof_predictions.csv", index=False)
    table, verdict = P.summarise(oof, n_draws=int(arg("draws", 10000)))
    table.to_csv(out / "pnl_table.csv", index=False)
    verdict.to_csv(out / "verdict.csv", index=False)
    summary = dict(tag=arg("tag", "exp6_pnl"), pool="v6", rows_dev=len(dev), n_test=len(oof), test_years=list(TEST_YEARS),
                   n_train_by_year={int(y): int(g["n_train"].iloc[0]) for y, g in oof.groupby("test_year")},
                   any_improvement=bool(verdict["improved"].any()), holdout_rows_not_used=int((df["split"] == "holdout").sum()),
                   source_sha256=manifest["sha256"], seconds=round(time.time() - t0, 1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    pd.set_option("display.width", 220)
    print(table[table.scope == "pooled"].round(3).to_string(index=False))
    print(verdict.round(3).to_string(index=False))
    print(f"[{time.time() - t0:5.1f}s] wrote {out}")


if __name__ == "__main__":
    main()
