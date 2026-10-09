"""One-table summary of every walk-forward run (Experiment 3 / 4 and algorithm-version runs) under results/ml_core/ that has topk.csv + verdict.csv.

  python scripts/compare_ml_versions.py [--out=results/ml_core/versions.csv]

For each run: algorithm version label, rows, test rows, base win rate, models compared, the best top-50% lift and AUC among them,
the number of models passing the preregistered criteria, and the power note (smallest detectable lift). Read-only on run folders.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LABELS = {"exp3_v5": "Final algorithm v5 (4 models)", "exp4_zoo": "Final algorithm v5 (8 models)", "ver_phaseA_b0": "Previous algorithm, Phase A B0 (4 models)"}


def main():
    rows = []
    for run in sorted((ROOT / "results" / "ml_core").iterdir()):
        if not (run / "verdict.csv").exists() or not (run / "summary.json").exists():
            continue
        s = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        v = pd.read_csv(run / "verdict.csv")
        best = v.loc[v["lift_pts"].idxmax()]
        by = s["manifest"].get("rows_by_strategy", {})
        rows.append(dict(run=run.name, algorithm_version=LABELS.get(s["tag"], s["tag"]), rows_used=s["manifest"]["rows_used"],
                         rows_by_strategy="; ".join(f"{k} {n}" for k, n in by.items()), test_rows=s["n_oof"], models=len(v),
                         base_win_rate=s["base_win_rate"], best_model=best["family"], best_top50_lift_pts=best["lift_pts"],
                         best_auc=float(v["auc"].max()), models_passing=int(v["win_rate_improvement_established"].sum()),
                         min_detectable_lift_pts=s["power"]["min_detectable_lift_pts"]))
    out = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), ROOT / "results" / "ml_core" / "versions.csv"))
    t = pd.DataFrame(rows)
    t.to_csv(out, index=False)
    pd.set_option("display.width", 220)
    print(t.drop(columns=["run"]).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
