"""Experiment 5, part B (descriptive): hand-made strength-2 rule versus ML top-50% selection on the v5 pool's out-of-fold test rows.

  python scripts/rule_vs_model.py [--run=results/ml_core/exp3_v5_f381ac0a]

Reads the Experiment 3 out-of-fold predictions (read-only). The rule was chosen in-sample on the same years, so its row is labelled in-sample.
Writes rule_vs_model.csv next to the run.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml_core import walkforward as W  # noqa: E402


def main():
    run = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--run=")), ROOT / "results" / "ml_core" / "exp3_v5_f381ac0a"))
    oof = pd.read_csv(run / "oof_predictions.csv", parse_dates=["entry_time"])
    d = oof["strategy"] == "DIT15"
    rows = []

    def add(name, mask, basis):
        n = int(mask.sum())
        w = int(oof.loc[mask, "label"].sum())
        lo, hi = W.wilson(w, n)
        rows.append(dict(selection=name, basis=basis, n=n, wins=w, win_rate=w / n if n else np.nan, ci_lo=lo, ci_hi=hi,
                         avg_r=float(oof.loc[mask, "r_gross"].mean()) if n else np.nan))

    add("All DIT15 test trades", d.to_numpy(), "reference")
    add("Strength-2 rule (hand-made)", (d & (oof["legout_strength_score"] == 2)).to_numpy(), "IN-SAMPLE (rule chosen on these years)")
    add("Strength-1 (rule drops these)", (d & (oof["legout_strength_score"] < 2)).to_numpy(), "IN-SAMPLE")
    for fam in [c[2:] for c in oof.columns if c.startswith("p_")]:
        take = W.select_topk(oof, f"p_{fam}", 0.5)
        add(f"ML top-50%: {fam}", d.to_numpy() & take, "out-of-fold (ranked across all strategies)")
    t = pd.DataFrame(rows)
    t.to_csv(run / "rule_vs_model.csv", index=False)
    pd.set_option("display.width", 200)
    print(t.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
