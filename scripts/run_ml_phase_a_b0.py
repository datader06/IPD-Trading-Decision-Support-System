"""Version A of the algorithm-version comparison: the previous algorithm's Phase A strict B0 trades through the same walk-forward protocol
as Experiment 3 (docs/EXPERIMENT_4_PREREGISTRATION.md, appendix A).

  python scripts/run_ml_phase_a_b0.py [--from=results/ml_core/exp2_6c6e182c] [--tag=ver_phaseA_b0]

Reads the frozen Experiment 2 dataset (read-only), keeps strict B0 rows that are resolved WIN/LOSS and entered before 2026, and writes the same
output files as run_ml_baseline_v5.py into results/ml_core/<tag>_<id>/.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml_core import dataset as D  # noqa: E402
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
    src = Path(arg("from", str(ROOT / "results" / "ml_core" / "exp2_6c6e182c")))
    ds = pd.read_csv(src / "dataset.csv", parse_dates=["entry_time", "exit_time"])
    b0 = ds[ds["is_b0"].astype(bool) & ds["label_status"].isin(["WIN", "LOSS"]) & (ds["entry_time"] < "2026-01-01")].copy()
    b0["label"] = b0["label"].astype(int)
    b0["split"] = "train"
    b0 = b0.reset_index(drop=True)
    manifest = json.loads((src / "dataset_manifest.json").read_text(encoding="utf-8"))
    out = Path(arg("out", str(ROOT / "results" / "ml_core" / f"{arg('tag', 'ver_phaseA_b0')}_{manifest['dataset_id']}")))
    out.mkdir(parents=True, exist_ok=True)
    fams = MR.resolve(arg("models"))
    oof = W.walk_forward(b0, D.FEATURE_COLUMNS, TEST_YEARS, families=fams)
    oof.to_csv(out / "oof_predictions.csv", index=False)
    b0.to_csv(out / "dataset.csv", index=False)
    summ = W.summarise(oof, families=fams, n_draws=int(arg("draws", 10000)))
    summ.to_csv(out / "topk.csv", index=False)
    verdict = W.edge_verdict(summ, families=fams)
    verdict.to_csv(out / "verdict.csv", index=False)
    n50 = int(summ[(summ.scope == "ALL") & (summ.top_pct == 50)]["n_taken"].iloc[0])
    summary = dict(tag=arg("tag", "ver_phaseA_b0"), manifest=dict(source=str(src.relative_to(ROOT)), sha256=manifest["dataset_id"],
                   rows_used=len(b0), rows_by_strategy=b0["strategy"].value_counts().to_dict(), feature_version=D.FEATURE_VERSION),
                   test_years=list(TEST_YEARS), models=list(fams), n_oof=len(oof), base_win_rate=float(oof["label"].mean()),
                   holdout_rows_not_used=int((ds["entry_time"] >= "2026-01-01").sum()),
                   any_improvement_established=bool(verdict["win_rate_improvement_established"].any()),
                   power=W.power_table(float(oof["label"].mean()), n50),
                   n_train_by_year={int(y): int(g["n_train"].iloc[0]) for y, g in oof.groupby("test_year")}, seconds=round(time.time() - t0, 1))
    (out / "manifest.json").write_text(json.dumps(summary["manifest"], indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(verdict.round(3).to_string(index=False))
    print(f"[{time.time() - t0:5.1f}s] {len(b0)} rows, {len(oof)} test rows -> {out}", flush=True)


if __name__ == "__main__":
    main()
