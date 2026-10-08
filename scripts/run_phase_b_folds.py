"""Phase B step 3: walk-forward fold construction and leakage checks (no model, no thresholds).

  python scripts/run_phase_b_folds.py [--labeled=results/nogit-145d6302/phase_b/labels/labeled.csv] [--out=DIR]

Writes to <run folder>/phase_b/folds/: folds.csv (one row per fold), fold_assignments.csv (fold, row_id, role),
manifest.json, report.txt. Exits with an error if any leakage check fails. The 2026 holdout is only counted, never inspected.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import registry as R  # noqa: E402
from ml import splits as S  # noqa: E402

DEF_LABELED = "results/nogit-145d6302/phase_b/labels/labeled.csv"
COLS = ["row_id", "ticker", "htf_key", "entry_time", "exit_time", "label_status", "is_training_label", "label", "is_b0"]


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    lab_path = ROOT / arg("labeled", DEF_LABELED)
    out = Path(arg("out") or lab_path.parent.parent / "folds")
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(lab_path, usecols=COLS, parse_dates=["entry_time", "exit_time"])
    td = S.default_trading_days()
    folds, d = S.build_folds(df, S.CFG, td)
    tab = S.fold_table(folds, d, S.CFG)
    asg = S.assignments(folds, d)
    checks = S.check_folds(folds, d, S.CFG, td)
    failed = {k: v for k, v in checks.items() if not v[0]}
    # determinism: a second construction must be identical
    folds2, d2 = S.build_folds(df, S.CFG, td)
    deterministic = S.fold_table(folds2, d2, S.CFG).equals(tab) and S.assignments(folds2, d2).equals(asg)
    tab.to_csv(out / "folds.csv", index=False)
    asg.to_csv(out / "fold_assignments.csv", index=False)
    hold = d[d["entry_time"] >= S.CFG.holdout_start]
    manifest = dict(
        labeled_file=str(lab_path.relative_to(ROOT)), labeled_sha256=sha256(lab_path), registry_version=R.REGISTRY_VERSION,
        config=dict(windows=[list(w) for w in S.CFG.windows], dev_start=str(S.CFG.dev_start.date()),
                    holdout_start=str(S.CFG.holdout_start.date()), val_months=S.CFG.val_months, embargo_days=S.CFG.embargo_days,
                    n_features=S.CFG.n_features, min_train_resolved=S.CFG.min_train_resolved,
                    min_wins_per_feature=S.CFG.min_wins_per_feature, min_test_resolved=S.CFG.min_test_resolved),
        rows_total=len(d), rows_before_dev_start=int((d["entry_time"] < S.CFG.dev_start).sum()),
        holdout_rows=len(hold), holdout_first_entry=str(hold["entry_time"].min()), holdout_last_entry=str(hold["entry_time"].max()),
        checks_total=len(checks), checks_failed=sorted(failed), deterministic=bool(deterministic),
        folds_sha256=sha256(out / "folds.csv"), assignments_sha256=sha256(out / "fold_assignments.csv"),
        model_fitting_labels="WIN=1, LOSS=0 only (is_training_label)",
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    L = []
    p = L.append
    p(f"PHASE B WALK-FORWARD FOLDS  labeled {lab_path.relative_to(ROOT)}  rows {len(d)}")
    p(f"expanding window from {S.CFG.dev_start.date()}; validation = last {S.CFG.val_months} months of the training window; embargo "
      f"{S.CFG.embargo_days} trading days (NIFTY calendar); purge = outcome (exit_time) at or after the boundary; "
      f"holdout from {S.CFG.holdout_start.date()} ({len(hold)} rows, never used)")
    p("\nFOLD DEFINITIONS")
    for r in tab.itertuples():
        p(f"  {r.fold}: fit {r.fit_period} | validation {r.validation_period} | test {r.test_period}"
          f" | embargo from {r.test_embargo_start} (validation boundary: {r.val_embargo_start})")
    p("\nROW COUNTS (resolved = WIN + LOSS; fit/validation/pool are resolved rows only)")
    p(f"  {'fold':<8}{'fit':>6}{'(W/L)':>11}{'valid':>7}{'(W/L)':>10}{'pool':>6}{'(W/L)':>11}{'test rows':>11}{'resolved':>9}{'(W/L)':>10}"
      f"{'AMB':>5}{'CENS':>6}")
    for r in tab.itertuples():
        p(f"  {r.fold:<8}{r.fit_n:>6}{f'({r.fit_wins}/{r.fit_losses})':>11}{r.val_n:>7}{f'({r.val_wins}/{r.val_losses})':>10}"
          f"{r.pool_n:>6}{f'({r.pool_wins}/{r.pool_losses})':>11}{r.test_rows:>11}{r.test_resolved:>9}"
          f"{f'({r.test_wins}/{r.test_losses})':>10}{r.test_ambiguous:>5}{r.test_censored:>6}")
    p("\nPURGE / EMBARGO / SIBLING COUNTS (resolved rows removed at each boundary)")
    p(f"  {'fold':<8}{'test: embargo':>14}{'purged':>8}{'sibling':>9}{'valid: embargo':>16}{'purged':>8}{'sibling':>9}"
      f"{'unresolved excl.':>18}{'test rows exiting in 2026':>27}")
    for r in tab.itertuples():
        p(f"  {r.fold:<8}{r.embargo_n:>14}{r.purged_n:>8}{r.sibling_removed_n:>9}{r.val_embargo_n:>16}{r.val_purged_n:>8}"
          f"{r.val_sibling_n:>9}{r.unresolved_excluded_n:>18}{r.test_rows_exiting_in_holdout:>27}")
    need = S.CFG.min_wins_per_feature * S.CFG.n_features
    p(f"\nMINIMUM SAMPLE RULES (train >= {S.CFG.min_train_resolved} resolved, wins >= {need} = {S.CFG.min_wins_per_feature} x "
      f"{S.CFG.n_features} features, test >= {S.CFG.min_test_resolved} resolved)")
    for r in tab.itertuples():
        p(f"  {r.fold}: pool resolved {'OK' if r.pool_ok_resolved else 'FAIL'}, pool wins {'OK' if r.pool_ok_wins else 'FAIL'} "
          f"| fit resolved {'OK' if r.fit_ok_resolved else 'FAIL'}, fit wins {'OK' if r.fit_ok_wins else 'FAIL'} "
          f"| test resolved {'OK' if r.test_ok_resolved else 'FAIL'}")
    bad_rules = tab[~(tab[["pool_ok_resolved", "pool_ok_wins", "fit_ok_resolved", "fit_ok_wins", "test_ok_resolved"]].all(axis=1))]
    p(f"  folds failing a minimum rule: {list(bad_rules['fold']) if len(bad_rules) else 'none'}")
    p(f"\nLEAKAGE CHECKS: {len(checks)} run, {len(failed)} failed; deterministic rebuild: {deterministic}")
    for k, (okk, detail) in checks.items():
        if not okk:
            p(f"  FAILED {k}: {detail}")
    p("  checked per fold: roles disjoint; only WIN/LOSS rows fitted; max training entry before the embargo start; max training "
      "outcome before the test start (purge); embargo spans exactly 5 trading days; purged rows really cross the boundary; test rows "
      "inside the window; validation = last 6 months; fit ends before the validation boundary with embargo and purge; no HTF-zone "
      "group on both sides; expanding pools; and across folds: chronological, windows end by the holdout start, no holdout row in "
      "any role.")
    (out / "report.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nsaved {out}")
    if failed:
        raise SystemExit(f"{len(failed)} leakage checks failed")


if __name__ == "__main__":
    main()
