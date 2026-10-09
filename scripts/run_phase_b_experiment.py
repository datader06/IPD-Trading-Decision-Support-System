"""Experiment 1 runner (DIT15 Phase-B frozen files; design frozen in docs/EXPERIMENT_1_PREREGISTRATION.md).

  python scripts/run_phase_b_experiment.py [--check-only] [--out=DIR] [--n-draws=1000]

Steps (any failed check stops the run before anything is trained):
  1. verify the frozen files (SHA-256), versions, row counts, fold assignments and the 240-row strict HTF subset; print the scope;
  2. primary experiment (all rows before the 2026 holdout), strict sensitivity (same folds, the 240 rows removed, full re-run incl.
     tuning), a second identical primary run (determinism) and the shuffled-label sanity check;
  3. write structured results under results/nogit-145d6302/phase_b/experiment_1/ (refuses to write into a non-empty folder).
The 2026 holdout is dropped by src/ml/experiment.py before anything is built and is never scored. No bootstrap or report yet.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import runinfo  # noqa: E402
from ml import evaluate as E  # noqa: E402
from ml import experiment as X  # noqa: E402
from ml import models as M  # noqa: E402
from ml import registry as R  # noqa: E402
from ml import splits as S  # noqa: E402

RUN = ROOT / "results" / "nogit-145d6302"
P_CAND = RUN / "phase_a" / "pit" / "candidates.csv"
P_RUNINFO = RUN / "phase_a" / "pit" / "run_info.txt"
TIER1 = RUN / "phase_b" / "tier1"
P_FEAT, P_LAB = TIER1 / "features.csv", TIER1 / "labeled.csv"
P_MAN, P_FOLDS = TIER1 / "manifest.json", TIER1 / "folds"
P_PREREG = ROOT / "docs" / "EXPERIMENT_1_PREREGISTRATION.md"
DEF_OUT = RUN / "phase_b" / "experiment_1"

EXPECTED = {  # frozen SHA-256 values (tier1/manifest.json, tier1/folds/manifest.json, verified before Experiment 1)
    P_CAND: "a11902073480111b3430d62935e3cb786723f7d9b44bb4893e357d52c44a98d9",
    P_FEAT: "f0300790ba81611bdab7478676d6d27efe60efce7af26b260b86ad48066d5633",
    P_LAB: "55b768e3216e0453f0ff18a9ad010a3ab39733419a48574698447dc22d442744",
    P_FOLDS / "fold_assignments.csv": "2ac965ac1bd55259270532bb0fbcbfd0f9d1e95619eca8a028546b0264d482b7",
    P_FOLDS / "folds.csv": "338469d83e95a2010c678da8c98300e3bf87aa6a1b9c7dbf57f36f7b60b40b3e",
}
PHASE_A_HASH = "e5e09db7"
REGISTRY_HASH = "cd73bf8d"
N_ROWS, N_HOLDOUT, N_STRICT = 4552, 781, 240
VERSIONS = {"scikit-learn": "1.4.0", "xgboost": "2.0.3"}
SANITY_SEED = M.SEED


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")


def clean(o):
    """JSON-safe copy: numpy scalars / arrays, timestamps, NaN / inf -> None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(o))
    return o


def canon(o):
    return json.dumps(clean(o), sort_keys=True)


# ---------------------------------------------------------------------------------------------------------------------------
def htf_d1_flag(df, trading_days):
    """True where the HTF zone's leg_end date is the trading day just before the entry date (NIFTY calendar)."""
    days = np.asarray(trading_days, dtype="datetime64[ns]")
    ed = pd.to_datetime(df["entry_time"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
    k = np.searchsorted(days, ed, side="left") - 1
    prev = days[np.clip(k, 0, None)]
    hf = pd.to_datetime(df["htf_formed_at"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
    return (k >= 0) & (hf == prev)


def load_inputs():
    lab = pd.read_csv(P_LAB, parse_dates=["entry_time", "exit_time", "fill_time", "htf_formed_at"], float_precision="round_trip")
    feat = pd.read_csv(P_FEAT, float_precision="round_trip")
    frozen = pd.read_csv(P_FOLDS / "fold_assignments.csv")
    return lab, feat, frozen


def checks():
    """Returns (ok, list of (name, passed, detail), context). Nothing is trained here."""
    res = []

    def add(name, passed, detail=""):
        res.append((name, bool(passed), str(detail)))

    import sklearn
    import xgboost
    add("scikit-learn version", sklearn.__version__ == VERSIONS["scikit-learn"], sklearn.__version__)
    add("xgboost version", xgboost.__version__ == VERSIONS["xgboost"], xgboost.__version__)
    add("preregistration present", P_PREREG.exists(), rel(P_PREREG) if P_PREREG.exists() else "missing")
    for p, want in EXPECTED.items():
        got = sha256(p) if p.exists() else "missing"
        add(f"sha256 {rel(p)}", got == want, got[:12])
    man = json.loads(P_MAN.read_text(encoding="utf-8"))
    fman = json.loads((P_FOLDS / "manifest.json").read_text(encoding="utf-8"))
    add("tier1 manifest hashes", man["features_sha256"] == EXPECTED[P_FEAT] and man["labeled_sha256"] == EXPECTED[P_LAB]
        and man["source_sha256"] == EXPECTED[P_CAND], "features / labeled / source")
    add("folds manifest hashes", fman["labeled_sha256"] == EXPECTED[P_LAB] and fman["folds_sha256"] == EXPECTED[P_FOLDS / "folds.csv"]
        and fman["assignments_sha256"] == EXPECTED[P_FOLDS / "fold_assignments.csv"], "labeled / folds / assignments")
    info = P_RUNINFO.read_text(encoding="utf-8") if P_RUNINFO.exists() else ""
    add("phase A run_info code_hash", f"code_hash={PHASE_A_HASH}" in info, PHASE_A_HASH)
    add("phase A measured code hash (current tree)", runinfo.code_hash() == PHASE_A_HASH, runinfo.code_hash())
    add("registry SOURCE_CODE_HASH (documented discrepancy, unchanged)", R.SOURCE_CODE_HASH == REGISTRY_HASH,
        f"registry {R.SOURCE_CODE_HASH} vs measured {PHASE_A_HASH}")
    ctx = {}
    if all(r[1] for r in res):
        lab, feat, frozen = load_inputs()
        td = S.default_trading_days()
        hold = lab["entry_time"] >= S.CFG.holdout_start
        add("labeled rows", len(lab) == N_ROWS, len(lab))
        add("holdout rows", int(hold.sum()) == N_HOLDOUT, int(hold.sum()))
        add("features / labeled identity", list(feat["row_id"]) == list(lab["row_id"])
            and all((feat[c] == lab[c]).all() for c in R.MODEL_COLUMNS), f"{len(R.MODEL_COLUMNS)} model columns bit-identical")
        add("frozen assignments contain no holdout rows",
            not (pd.to_datetime(frozen["entry_time"]) >= S.CFG.holdout_start).any(), len(frozen))
        flag = htf_d1_flag(lab, td)
        add("strict HTF D-1 subset size", int(flag.sum()) == N_STRICT, int(flag.sum()))
        ctx = dict(lab=lab, frozen=frozen, td=td, flag=flag, exclude=set(lab.loc[flag, "row_id"]))
        try:
            ctx["folds"], ctx["d"] = X.build_checked_folds(lab, frozen, td)
            add("fold rebuild == frozen roles; leakage checks pass; holdout dropped", True,
                f"{len(ctx['folds'])} folds, {len(ctx['d'])} rows used")
        except Exception as e:  # noqa: BLE001
            add("fold rebuild == frozen roles; leakage checks pass; holdout dropped", False, e)
    return all(r[1] for r in res), res, ctx


def print_scope(ctx, n_draws, out):
    lab, flag, d = ctx["lab"], ctx["flag"], ctx.get("d")
    hold = lab["entry_time"] >= S.CFG.holdout_start
    ex_dev = lab[flag & ~hold]
    print("\n=== EXPERIMENT 1 SCOPE ===")
    print(f"labeled rows {len(lab)} | holdout (never used) {int(hold.sum())} | development rows {int((~hold).sum())}")
    print(f"primary dataset: all {int((~hold).sum())} pre-2026 rows; strict sensitivity removes {len(ex_dev)} of the {int(flag.sum())} "
          f"flagged rows that lie before 2026 ({int((flag & hold).sum())} flagged rows are in the holdout)")
    print(f"folds {[f.name for f in ctx['folds']]} | models {list(M.FAMILIES)} | grids "
          f"{ {f: [c.value for c in M.frozen_configs(f)] for f in M.FAMILIES} }")
    print(f"decision rule T1 (primary), T2 secondary; champion at {X.PRIMARY_SCENARIO} with >= {X.MIN_RESOLVED_TAKES} resolved takes; "
          f"B2 draws {n_draws}; seed {M.SEED}")
    print("steps: primary run -> strict run -> second primary run (determinism) -> shuffled-label sanity check")
    print(f"output folder: {rel(out)}")


# ---------------------------------------------------------------------------------------------------------------------------
def equal_results(a, b):
    """Exact comparison of two run_experiment results (predictions, takes, metrics, selections, B2 draws, champion)."""
    pc = [c for c in a["oof"].columns if c.startswith(("p_", "take_"))]
    same_oof = a["oof"].shape == b["oof"].shape and list(a["oof"]["row_id"]) == list(b["oof"]["row_id"]) and all(
        np.array_equal(a["oof"][c].to_numpy(), b["oof"][c].to_numpy()) for c in pc)
    body = lambda r: canon(dict(folds=r["folds"], pooled=r["pooled"], champion=r["champion"], meta=r["meta"],  # noqa: E731
                                b2={f: {k: v for k, v in x.items() if k != "draws"} for f, x in r["b2"].items()}))
    same_draws = all(np.array_equal(a["b2"][f]["draws"][s][m], b["b2"][f]["draws"][s][m], equal_nan=True)
                     for f in a["b2"] for s in a["b2"][f]["draws"] for m in a["b2"][f]["draws"][s])
    return dict(oof_predictions_and_takes=bool(same_oof), metrics_selections_champion=body(a) == body(b), b2_draws=bool(same_draws))


def shuffled_label_check(ctx, families=M.FAMILIES):
    """Fit / validation / pool labels are permuted (fixed seeds); the pipeline then predicts the test rows. The pooled out-of-fold
    ROC-AUC against the true test labels must lie inside the 95% null band around 0.5 (normal approximation to the AUC null)."""
    folds, d = ctx["folds"], ctx["d"]
    cols = list(R.MODEL_COLUMNS)
    Xa, y_all = d[cols].to_numpy(dtype=float), d["label"].to_numpy()
    outcome = d["outcome"].to_numpy(dtype=object)
    out = {}
    for fam in families:
        p_all, o_all = [], []
        for fi, f in enumerate(folds):
            idx = f.idx
            ys = {}
            for j, role in enumerate(("fit", "validation", "pool")):
                y = y_all[idx[role]].astype(int)
                ys[role] = np.random.default_rng([SANITY_SEED, fi, j]).permutation(y)
            r = X.fit_select_predict(fam, Xa[idx["fit"]], ys["fit"], Xa[idx["validation"]], ys["validation"], Xa[idx["pool"]],
                                     ys["pool"], Xa[idx["test"]])
            p_all.append(r["p_test"])
            o_all.append(outcome[idx["test"]])
        p, o = np.concatenate(p_all), np.concatenate(o_all)
        m = E.ml_metrics(o, p, np.zeros(len(o), dtype=bool))
        n1, n0 = m["n_pos"], m["n_neg"]
        se = float(np.sqrt((n1 + n0 + 1) / (12.0 * n1 * n0)))
        lo, hi = 0.5 - 1.96 * se, 0.5 + 1.96 * se
        out[fam] = dict(roc_auc=m["roc_auc"], band=[lo, hi], se=se, n_pos=n1, n_neg=n0, passed=bool(lo <= m["roc_auc"] <= hi))
    return out


# ---------------------------------------------------------------------------------------------------------------------------
def pooled_table(dataset, res):
    rows = []
    for arm_set, models in (("baseline", res["pooled"]["baselines"]),):
        for arm, by_scen in models.items():
            for scen, m in by_scen.items():
                rows.append(dict(dataset=dataset, family="-", arm=arm, scenario=scen, **m))
    for fam, v in res["pooled"]["models"].items():
        for arm, by_scen in v["arms"].items():
            for scen, m in by_scen.items():
                rows.append(dict(dataset=dataset, family=fam, arm=arm, scenario=scen, **m))
    return pd.DataFrame(rows)


def selections_table(dataset, res):
    rows = []
    for fr in res["folds"]:
        for fam, m in fr["models"].items():
            rows.append(dict(dataset=dataset, fold=fr["fold"], family=fam, config=m["config"], val_log_loss=m["val_log_loss"],
                             best_rounds=m["best_rounds"], L_fit=fr["L_fit"], L_pool=fr["L_pool"], n_fit=fr["n_fit"],
                             n_validation=fr["n_validation"], n_pool=fr["n_pool"], n_test=fr["n_test"], n_take_t1=m["n_take_t1"],
                             t2_threshold=m["t2"]["threshold"], t2_expectancy=m["t2"]["expectancy"], n_take_t2=m["n_take_t2"],
                             auc=m["ml"]["roc_auc"], pr_auc=m["ml"]["pr_auc"], brier=m["ml"]["brier"], log_loss=m["ml"]["log_loss"]))
    return pd.DataFrame(rows)


def write_run(out, name, res):
    d = out / name
    d.mkdir(parents=True)
    res["oof"].to_csv(d / "oof_predictions.csv", index=False)
    pooled_table(name, res).to_csv(d / "pooled_metrics.csv", index=False)
    selections_table(name, res).to_csv(d / "fold_selections.csv", index=False)
    summary = dict(meta=res["meta"], champion=res["champion"], folds=res["folds"], pooled=res["pooled"],
                   b2={f: {k: v for k, v in x.items() if k != "draws"} for f, x in res["b2"].items()})
    (d / "results.json").write_text(json.dumps(clean(summary), indent=1), encoding="utf-8")
    arrays = {f"{f}__{s}__{m}": v for f, x in res["b2"].items() for s, ms in x["draws"].items() for m, v in ms.items()}
    np.savez_compressed(d / "b2_draws.npz", **arrays)
    with open(d / "experiment_log.jsonl", "w", encoding="utf-8") as fh:  # every configuration tried (append-only record)
        for fr in res["folds"]:
            for fam, m in fr["models"].items():
                for c in m["candidates"]:
                    fh.write(json.dumps(clean(dict(dataset=name, fold=fr["fold"], family=fam, **c))) + "\n")


def main():
    n_draws = int(arg("n-draws", X.N_DRAWS))
    out = Path(arg("out", DEF_OUT))
    out = out if out.is_absolute() else ROOT / out
    print("EXPERIMENT 1: validation and hash checks")
    ok, res, ctx = checks()
    for name, passed, detail in res:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    if not ok:
        print("\nA check failed: nothing was run.")
        return 1
    if "folds" not in ctx:
        print("\nfold rebuild unavailable: nothing was run.")
        return 1
    print_scope(ctx, n_draws, out)
    if "--check-only" in sys.argv:
        print("\n--check-only: stopping before any model is trained.")
        return 0
    if out.exists() and any(out.iterdir()):
        print(f"\noutput folder {rel(out)} is not empty: refusing to overwrite.")
        return 1

    lab, frozen, td, ex = ctx["lab"], ctx["frozen"], ctx["td"], ctx["exclude"]
    t0 = time.time()
    tick = lambda msg: print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)  # noqa: E731
    run_kw = dict(trading_days=td, n_draws=n_draws)
    tick("primary run")
    primary = X.run_experiment(lab, frozen, **run_kw)
    tick(f"primary done; champion {primary['champion']['champion']}")
    tick("strict sensitivity run (full re-run, 240 rows removed from the frozen fold roles)")
    strict = X.run_experiment(lab, frozen, exclude_row_ids=ex, **run_kw)
    tick(f"strict done; champion {strict['champion']['champion']}")
    tick("second identical primary run (determinism)")
    again = X.run_experiment(lab, frozen, **run_kw)
    determinism = equal_results(primary, again)
    tick(f"determinism: {determinism}")
    strict_ok = dict(
        flagged_total=int(ctx["flag"].sum()), flagged_in_development_data=len(ex & set(ctx["d"]["row_id"])),
        none_left_in_strict_oof=not (set(strict["oof"]["row_id"]) & ex),
        same_folds=strict["meta"]["folds"] == primary["meta"]["folds"],
        oof_rows_primary=len(primary["oof"]), oof_rows_strict=len(strict["oof"]))
    tick("shuffled-label sanity check")
    sanity = shuffled_label_check(ctx)
    for fam, s in sanity.items():
        print(f"    {fam}: AUC {s['roc_auc']:.4f} band [{s['band'][0]:.4f}, {s['band'][1]:.4f}] -> {'PASS' if s['passed'] else 'FAIL'}")

    out.mkdir(parents=True, exist_ok=True)
    write_run(out, "primary", primary)
    write_run(out, "strict_htf", strict)
    flagged = lab.loc[ctx["flag"], ["row_id", "ticker", "entry_time", "htf_formed_at"]]
    flagged.to_csv(out / "strict_subset_rows.csv", index=False)
    (out / "determinism.json").write_text(json.dumps(clean(determinism), indent=1), encoding="utf-8")
    (out / "shuffled_label_check.json").write_text(json.dumps(clean(sanity), indent=1), encoding="utf-8")
    import sklearn
    import xgboost
    manifest = dict(
        experiment="Experiment 1", preregistration=rel(P_PREREG), preregistration_sha256=sha256(P_PREREG),
        inputs={rel(p): dict(sha256=sha256(p), expected=h) for p, h in EXPECTED.items()},
        phase_a_measured_code_hash=PHASE_A_HASH, registry_source_code_hash=R.SOURCE_CODE_HASH,
        hash_note="registry SOURCE_CODE_HASH (cd73bf8d) differs from the measured Phase A hash (e5e09db7); documented, not changed",
        versions=dict(scikit_learn=sklearn.__version__, xgboost=xgboost.__version__, numpy=np.__version__, pandas=pd.__version__),
        scope=dict(labeled_rows=len(lab), holdout_rows_excluded=primary["meta"]["holdout_rows_excluded"],
                   primary_rows_used=primary["meta"]["n_rows_used"], strict_flagged_rows=int(ctx["flag"].sum()),
                   strict_oof_rows=len(strict["oof"]), primary_oof_rows=len(primary["oof"])),
        seed=M.SEED, n_draws=n_draws, champion=dict(primary=primary["champion"]["champion"], strict=strict["champion"]["champion"]),
        determinism=determinism, strict_subset_checks=strict_ok, shuffled_label_check=sanity,
        seconds=round(time.time() - t0, 1))
    outputs = {rel(p): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    manifest["output_sha256"] = outputs
    (out / "manifest.json").write_text(json.dumps(clean(manifest), indent=1), encoding="utf-8")
    tick(f"written to {rel(out)}")

    problems = [k for k, v in determinism.items() if not v] + [f"sanity:{f}" for f, s in sanity.items() if not s["passed"]] + [
        k for k in ("none_left_in_strict_oof", "same_folds") if not strict_ok[k]]
    print("\nchampion (primary):", primary["champion"]["champion"], "| strict:", strict["champion"]["champion"])
    print("PROBLEMS:" if problems else "all post-run checks passed", problems if problems else "")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
