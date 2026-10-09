"""Strategy-agnostic ML run (Experiment 2): pooled DIT15 + WIT + MIT, frozen model families, walk-forward out-of-fold evaluation.

  python scripts/run_ml_core.py [--tag=algo_v2] [--src.DIT15=path --src.WIT=path --src.MIT=path] [--strategies=DIT15,WIT,MIT] [--out=DIR] [--families=logreg,random_forest,hist_gb,xgboost]

Offline only (cached frames, frozen candidate files). Writes results/ml_core/exp2_<dataset_id>/ :
  dataset.csv, dataset_manifest.json, exclusions.csv, oof_predictions.csv, per_strategy.csv, auc.csv, bootstrap.csv, summary.json.
The 2026 holdout is never fitted, validated, tested or scored. Design: docs/EXPERIMENT_2_PREREGISTRATION.md.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import experiment as X  # noqa: E402
from ml import models as M  # noqa: E402
from ml import splits as S  # noqa: E402
from ml_core import compare as C  # noqa: E402
from ml_core import dataset as D  # noqa: E402


def arg(name, default=None):
    for a in sys.argv[1:]:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o)
    return o


def main():
    t0 = time.time()
    strategies = tuple(arg("strategies", "DIT15,WIT,MIT").split(","))
    families = tuple(arg("families", ",".join(M.FAMILIES)).split(","))
    overrides = {a[6:].split("=", 1)[0]: Path(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--src.")}  # --src.WIT=path
    tag = arg("tag", "exp2")  # label for this deterministic-layer version, e.g. --tag=algo_v2
    df, manifest, excl = D.build_dataset(sources=overrides or None, strategies=strategies)
    out = Path(arg("out", str(ROOT / "results" / "ml_core" / f"{tag}_{manifest['dataset_id']}")))
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "dataset.csv", index=False)
    excl.to_csv(out / "exclusions.csv", index=False)
    (out / "dataset_manifest.json").write_text(json.dumps(clean(manifest), indent=1), encoding="utf-8")
    print(f"[{time.time() - t0:5.1f}s] dataset {manifest['dataset_id']}: {manifest['rows_by_strategy']}", flush=True)

    cfg = S.WFConfig(n_features=len(D.FEATURE_COLUMNS))
    td = S.default_trading_days()
    work = S.prepare(df[pd.to_datetime(df["entry_time"]) < cfg.holdout_start])
    folds, work = S.build_folds(work, cfg, td)
    assign = S.assignments(folds, work)  # self-consistent: folds rebuilt and leakage-checked inside run_experiment
    res = X.run_experiment(df, assign, feature_columns=D.FEATURE_COLUMNS, cost_column="cost_in_r_rt0.20", baseline_column="is_b0",
                           trading_days=td, families=families, cfg=cfg)
    oof = res["oof"]
    oof.to_csv(out / "oof_predictions.csv", index=False)
    print(f"[{time.time() - t0:5.1f}s] experiment done: {len(oof)} out-of-fold rows", flush=True)

    tbl = C.per_strategy_table(oof, families)
    tbl.to_csv(out / "per_strategy.csv", index=False)
    auc = C.per_strategy_auc(oof, families)
    auc.to_csv(out / "auc.csv", index=False)
    boot = C.month_block_bootstrap(oof, families)
    boot.to_csv(out / "bootstrap.csv", index=False)
    summary = dict(dataset_id=manifest["dataset_id"], feature_version=D.FEATURE_VERSION, meta=res["meta"], champion=res["champion"],
                   b2={f: {k: v for k, v in res["b2"][f].items() if k != "draws"} for f in families},
                   pooled_ml_metrics={f: res["pooled"]["models"][f]["ml"] for f in families},
                   holdout_rows_not_scored=int((pd.to_datetime(df["entry_time"]) >= cfg.holdout_start).sum()),
                   seconds=round(time.time() - t0, 1))
    (out / "summary.json").write_text(json.dumps(clean(summary), indent=1), encoding="utf-8")
    print(f"[{time.time() - t0:5.1f}s] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
