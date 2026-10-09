"""Experiment 3: ML win-rate filter on the final algorithm export (baselines v5). Offline, deterministic, 2026 holdout never touched.

  python scripts/run_ml_baseline_v5.py [--data=data/algo_v5/ml_dataset_baseline_v5.csv] [--tag=exp3_v5] [--pool=v5|v6] [--models=default|all|a,b] [--draws=10000]

Writes results/ml_core/<tag>_<sha8>/ : dataset.csv, manifest.json, exclusions.csv, oof_predictions.csv, topk.csv, verdict.csv, summary.json.
Design and success criteria: docs/EXPERIMENT_3_PREREGISTRATION.md.
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
from ml_core import model_registry as MR  # noqa: E402
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
    out = Path(arg("out", str(ROOT / "results" / "ml_core" / f"{arg('tag', 'exp3_v5')}_{manifest['sha256'][:8]}")))
    out.mkdir(parents=True, exist_ok=True)
    if arg("pool") == "v6":  # FINAL baseline v6 = v5 + zone strength 2 on DIT15 only (STATUS 19); reproduces the 205 final trades
        df = df[(df["strategy"] != "DIT15") | (df["legout_strength_score"] == 2)].reset_index(drop=True)
        manifest = dict(manifest, pool="v6", rows_used=len(df), rows_by_strategy=df["strategy"].value_counts().to_dict(),
                        rows_by_split=df["split"].value_counts().to_dict())
    dev = df[df["split"] != "holdout"].reset_index(drop=True)
    holdout_n = int((df["split"] == "holdout").sum())
    df.to_csv(out / "dataset.csv", index=False)
    excl.to_csv(out / "exclusions.csv", index=False)
    print(f"[{time.time() - t0:5.1f}s] {len(df)} rows ({len(dev)} dev, {holdout_n} holdout not used); excluded {len(excl)}", flush=True)

    fams = MR.resolve(arg("models"))
    oof = W.walk_forward(dev, A.FEATURE_COLUMNS, TEST_YEARS, families=fams)
    oof.to_csv(out / "oof_predictions.csv", index=False)
    summ = W.summarise(oof, families=fams, n_draws=int(arg("draws", 10000)))
    summ.to_csv(out / "topk.csv", index=False)
    verdict = W.edge_verdict(summ, families=fams)
    verdict.to_csv(out / "verdict.csv", index=False)
    summary = dict(tag=arg("tag", "exp3_v5"), manifest=manifest, test_years=list(TEST_YEARS), models=list(fams), n_oof=len(oof),
                   base_win_rate=float(oof["label"].mean()), holdout_rows_not_used=holdout_n,
                   any_improvement_established=bool(verdict["win_rate_improvement_established"].any()),
                   power=W.power_table(float(oof["label"].mean()), int((summ[(summ.scope == "ALL") & (summ.top_pct == 50)]["n_taken"]).iloc[0])),
                   n_train_by_year={int(y): int(g["n_train"].iloc[0]) for y, g in oof.groupby("test_year")}, seconds=round(time.time() - t0, 1))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(verdict.round(3).to_string(index=False))
    print(f"[{time.time() - t0:5.1f}s] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
