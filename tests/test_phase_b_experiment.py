"""Unit tests for src/ml/experiment.py (fold checks, model selection, T1 / T2, arms, controls, champion, strict subset).
Synthetic data only: no project data, files, Phase A outputs or frozen folds.
Run: python -m pytest tests/test_phase_b_experiment.py -q
"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import experiment as X  # noqa: E402
from ml import models as M  # noqa: E402
from ml import registry as R  # noqa: E402
from ml import splits as S  # noqa: E402
from ml import thresholds as T  # noqa: E402

COST = "cost_in_r_rt0.20"
SCEN = ["gross", "rt0.10", "rt0.20", "rt0.30"]
FAST = ("logreg",)
TWO = ("logreg", "hist_gb")


def make_frame(seed=0, per_half=420):
    rng = np.random.default_rng(seed)
    starts = pd.date_range("2021-01-01", "2026-07-01", freq="6MS")
    parts = []
    for a, b in zip(starts[:-1], starts[1:]):
        steps = (b - a).days * 24 * 60 // 15
        parts.append(pd.DataFrame(dict(entry_time=a + pd.to_timedelta(rng.integers(0, steps, per_half) * 15, unit="min"))))
    df = pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    n = len(df)
    feats = rng.normal(size=(n, len(R.MODEL_COLUMNS)))
    for j, c in enumerate(R.MODEL_COLUMNS):
        df[c] = feats[:, j]
    df[COST] = rng.uniform(0.1, 0.5, n)
    pwin = 1 / (1 + np.exp(-(-0.8 + 0.7 * feats[:, 0] - 0.5 * feats[:, 1])))
    out = np.where(rng.random(n) < 0.12, "AMBIGUOUS", np.where(rng.random(n) < pwin, "WIN", "LOSS"))
    df["outcome"] = out
    df["label_status"] = out
    df["is_training_label"] = np.isin(out, ["WIN", "LOSS"])
    df["label"] = np.where(out == "WIN", 1.0, np.where(out == "LOSS", 0.0, np.nan))
    entry = rng.uniform(100, 500, n)
    risk = entry * rng.uniform(0.005, 0.02, n)
    df["entry_price"], df["risk"], df["fill_price"] = entry, risk, entry
    df["r_gross"] = np.where(out == "WIN", 2.0, np.where(out == "LOSS", -1.0, np.nan))
    df["exit_price"] = np.where(np.isin(out, ["WIN", "LOSS"]), entry + df["r_gross"].fillna(0) * risk, np.nan)
    df["fill_time"] = df["entry_time"]
    df["exit_time"] = df["entry_time"] + pd.to_timedelta(rng.integers(1, 72, n), unit="h")
    df["ticker"] = rng.choice([f"T{i}" for i in range(40)], n)
    df["htf_key"] = [f"k{i // 2}" for i in range(n)]
    df["row_id"] = [f"r{i:05d}" for i in range(n)]
    df["is_b0"] = rng.random(n) < 0.08
    return df


TD = pd.bdate_range("2020-10-01", "2027-01-31").to_numpy(dtype="datetime64[ns]")


@pytest.fixture(scope="module")
def df():
    return make_frame()


@pytest.fixture(scope="module")
def frozen(df):
    folds, d = S.build_folds(S.prepare(df[df.entry_time < S.CFG.holdout_start]), S.CFG, TD)
    return S.assignments(folds, d)


@pytest.fixture(scope="module")
def checked(df, frozen):
    return X.build_checked_folds(df, frozen, TD)


@pytest.fixture(scope="module")
def run(df, frozen):
    return X.run_experiment(df, frozen, trading_days=TD, families=TWO, n_draws=20)


def _p_take_equal(a, b):
    cols = [c for c in a["oof"].columns if c.startswith(("p_", "take_"))]
    return cols and all(np.array_equal(a["oof"][c].to_numpy(), b["oof"][c].to_numpy()) for c in cols)


# 1. fold-role equality and holdout exclusion --------------------------------------------------------------------------------
def test_rebuilt_roles_equal_the_frozen_assignments(checked, frozen):
    folds, d = checked
    rebuilt = S.assignments(folds, d)
    key = lambda t: set(map(tuple, t[["fold", "row_id", "role"]].itertuples(index=False, name=None)))  # noqa: E731
    assert key(rebuilt) == key(frozen) and len(rebuilt) == len(frozen)
    assert [f.name for f in folds] == [w[0] for w in S.WINDOWS]


def test_any_difference_from_the_frozen_assignments_is_rejected(df, frozen):
    for bad in (frozen.iloc[1:], pd.concat([frozen, frozen.iloc[:1]]),
                frozen.assign(role=np.where(np.arange(len(frozen)) == 0, "embargo", frozen["role"]))):
        with pytest.raises(ValueError, match="do not match the frozen"):
            X.build_checked_folds(df, bad, TD)


def test_holdout_rows_are_dropped_before_anything_is_built(df, checked, run):
    folds, d = checked
    n_hold = int((df.entry_time >= S.CFG.holdout_start).sum())
    assert n_hold > 0 and len(d) == len(df) - n_hold and d.entry_time.max() < S.CFG.holdout_start
    assert run["meta"]["holdout_rows_excluded"] == n_hold and run["meta"]["n_rows_used"] == len(d)
    assert run["oof"].entry_time.max() < S.CFG.holdout_start
    for f in folds:
        for role, idx in f.idx.items():
            assert (d["entry_time"].to_numpy()[idx] < np.datetime64(S.CFG.holdout_start)).all()


def test_scrambling_the_holdout_changes_nothing(df, frozen, run):
    dh = df.copy()
    m = dh.entry_time >= S.CFG.holdout_start
    dh.loc[m, "label"] = 1 - dh.loc[m, "label"].fillna(0)
    dh.loc[m, "r_gross"] = 123.0
    dh.loc[m, list(R.MODEL_COLUMNS)] = 99.0
    base = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    other = X.run_experiment(dh, frozen, trading_days=TD, families=FAST, n_draws=10)
    assert _p_take_equal(base, other) and base["pooled"] == other["pooled"]


# 2. fit / validation resolved only -----------------------------------------------------------------------------------------
def test_fit_validation_and_pool_rows_are_resolved_only_while_test_keeps_unresolved(checked):
    folds, d = checked
    out, ok = d["outcome"].to_numpy(dtype=object), d["is_training_label"].to_numpy()
    for f in folds:
        for role in ("fit", "validation", "pool"):
            assert np.isin(out[f.idx[role]], ["WIN", "LOSS"]).all() and ok[f.idx[role]].all()
        assert (out[f.idx["test"]] == "AMBIGUOUS").any()
        assert not (set(f.idx["fit"]) & set(f.idx["test"])) and not (set(f.idx["pool"]) & set(f.idx["test"]))


def test_ambiguous_rows_are_predicted_but_never_fitted(run, df):
    oof = run["oof"]
    assert (oof.outcome == "AMBIGUOUS").sum() > 0  # unresolved test rows get a probability and a take decision
    for fam in TWO:
        assert oof[f"p_{fam}"].notna().all() and ((oof[f"p_{fam}"] >= 0) & (oof[f"p_{fam}"] <= 1)).all()
        assert oof[f"take_{fam}"].dtype == bool


# 3. test-label independence ------------------------------------------------------------------------------------------------
def test_model_step_has_no_test_label_argument():
    params = inspect.signature(X.fit_select_predict).parameters
    assert list(params) == ["family", "X_fit", "y_fit", "X_val", "y_val", "X_pool", "y_pool", "X_test"]


def test_flipping_test_labels_leaves_that_folds_predictions_and_takes_unchanged(df, frozen):
    base = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    fold0 = base["meta"]["folds"][0]
    ids = set(base["oof"][base["oof"].fold == fold0].row_id)
    flipped = df.copy()
    m = flipped.row_id.isin(ids) & flipped.is_training_label
    flipped.loc[m, "label"] = 1 - flipped.loc[m, "label"]
    flipped.loc[m, "outcome"] = np.where(flipped.loc[m, "outcome"] == "WIN", "LOSS", "WIN")
    other = X.run_experiment(flipped, frozen, trading_days=TD, families=FAST, n_draws=10)
    a, b = (r["oof"][r["oof"].fold == fold0] for r in (base, other))
    assert np.array_equal(a["p_logreg"].to_numpy(), b["p_logreg"].to_numpy())
    assert np.array_equal(a["take_logreg"].to_numpy(), b["take_logreg"].to_numpy())
    assert a["outcome"].tolist() != b["outcome"].tolist()  # the evaluation did see the flipped labels
    assert base["folds"][0]["models"]["logreg"]["config"] == other["folds"][0]["models"]["logreg"]["config"]
    assert base["folds"][0]["L_pool"] == other["folds"][0]["L_pool"]


# 4. model selection --------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small():
    rng = np.random.default_rng(1)
    Xa = rng.normal(size=(450, 6))
    y = (Xa[:, 0] - 0.5 * Xa[:, 1] + rng.normal(size=450) > 0.2).astype(int)
    return Xa[:250], y[:250], Xa[250:340], y[250:340], Xa[:340], y[:340], Xa[340:]


@pytest.mark.parametrize("family", M.FAMILIES)
def test_selected_configuration_has_the_lowest_validation_log_loss(family, small):
    out = X.fit_select_predict(family, *small)
    cands = out["candidates"]
    assert [c["config"] for c in cands] == [c.name for c in M.frozen_configs(family)]
    best = min(c["val_log_loss"] for c in cands)
    assert out["val_log_loss"] == best and out["config"] == next(c["config"] for c in cands if c["val_log_loss"] == best)
    assert out["p_test"].shape == (len(small[-1]),) and ((out["p_test"] >= 0) & (out["p_test"] <= 1)).all()
    assert out["p_val"].shape == (len(small[3]),)
    assert (out["best_rounds"] is not None) == (family == "xgboost")


def test_validation_ties_keep_the_first_frozen_configuration(small, monkeypatch):
    import sklearn.metrics
    monkeypatch.setattr(sklearn.metrics, "log_loss", lambda *a, **k: 0.5)
    assert X.fit_select_predict("random_forest", *small)["config"] == M.frozen_configs("random_forest")[0].name


def test_selection_is_deterministic(small):
    a, b = X.fit_select_predict("hist_gb", *small), X.fit_select_predict("hist_gb", *small)
    assert a["config"] == b["config"] and np.array_equal(a["p_test"], b["p_test"])


def test_run_records_candidates_for_every_fold_and_family(run):
    for fr in run["folds"]:
        for fam in TWO:
            m = fr["models"][fam]
            assert [c["config"] for c in m["candidates"]] == [c.name for c in M.frozen_configs(fam)]
            assert m["config"] in [c["config"] for c in m["candidates"]]
            assert m["val_log_loss"] == min(c["val_log_loss"] for c in m["candidates"])


# 5. T1 versus T2 -----------------------------------------------------------------------------------------------------------
def test_t1_take_mask_is_the_expected_value_rule_with_training_stage_l(run):
    oof = run["oof"]
    for fr in run["folds"]:
        sub = oof[oof.fold == fr["fold"]]
        for fam in TWO:
            expected = T.apply_t1(sub[f"p_{fam}"].to_numpy(), sub[COST].to_numpy(), fr["L_pool"])
            assert np.array_equal(sub[f"take_{fam}"].to_numpy(), expected)
            assert fr["models"][fam]["n_take_t1"] == int(expected.sum())
        assert fr["L_pool"] > 0 and fr["L_fit"] > 0
    assert run["folds"][0]["L_pool"] == pytest.approx(1.0)  # synthetic LOSS rows are exactly -1R


def test_t2_is_a_separate_secondary_arm_that_never_replaces_t1(run):
    grid = set(T.T2_GRID)
    oof = run["oof"]
    for fr in run["folds"]:
        sub = oof[oof.fold == fr["fold"]]
        for fam in TWO:
            t2 = fr["models"][fam]["t2"]
            thr = t2["threshold"]
            if thr is not None:
                assert thr in grid or 0 < thr < 1  # a grid value or the supplied break-even candidate
                exp = sub[f"p_{fam}"].to_numpy() > thr
            else:
                exp = np.zeros(len(sub), dtype=bool)
            assert np.array_equal(sub[f"take_t2_{fam}"].to_numpy(), exp)
            assert fr["models"][fam]["n_take_t2"] == int(exp.sum())
            assert t2["min_takes"] >= T.T2_MIN_TAKES_FLOOR
            assert set(fr["models"][fam]["arms"]) == {"ML", "ML_on_B0", "ML_T2"}
    # the two decision rules are different take sets
    assert not np.array_equal(oof["take_logreg"].to_numpy(), oof["take_t2_logreg"].to_numpy())


def test_champion_ignores_t2(run):
    ml = {f: run["pooled"]["models"][f]["arms"]["ML"]["rt0.20"] for f in TWO}
    assert run["champion"] == X.select_champion(ml)  # decided from the T1 arm at the primary scenario only
    assert run["champion"]["champion"] in TWO


# 6. arms and controls ------------------------------------------------------------------------------------------------------
def test_baseline_and_ml_arm_counts(run):
    oof, pooled = run["oof"], run["pooled"]
    assert pooled["baselines"]["B1"]["rt0.20"]["n_taken"] == len(oof)
    assert pooled["baselines"]["B0"]["gross"]["n_taken"] == int(oof.is_b0.sum())
    for fam in TWO:
        take = oof[f"take_{fam}"].to_numpy(dtype=bool)
        arms = pooled["models"][fam]["arms"]
        assert arms["ML"]["gross"]["n_taken"] == int(take.sum())
        assert arms["ML_on_B0"]["gross"]["n_taken"] == int((take & oof.is_b0.to_numpy()).sum())
        assert arms["ML_on_B0"]["gross"]["n_taken"] <= min(arms["ML"]["gross"]["n_taken"], pooled["baselines"]["B0"]["gross"]["n_taken"])
        for arm in arms.values():
            assert list(arm) == SCEN
        assert sum(fr["models"][fam]["n_take_t1"] for fr in run["folds"]) == int(take.sum())
    for fr in run["folds"]:
        assert fr["baselines"]["B1"]["gross"]["n_taken"] == fr["n_test"]


def test_all_four_cost_scenarios_use_the_same_take_set(run):
    arm = run["pooled"]["models"]["logreg"]["arms"]["ML"]
    assert len({arm[s]["n_taken"] for s in SCEN}) == 1 and len({arm[s]["n_resolved_taken"] for s in SCEN}) == 1
    totals = [arm[s]["total_r"] for s in SCEN]
    assert totals == sorted(totals, reverse=True)  # higher costs lower the total on the identical trades


def test_b2_random_filter_matches_ml_take_counts_per_fold(run):
    for fam in TWO:
        b2 = run["b2"][fam]
        want = {fr["fold"]: fr["models"][fam]["n_take_t1"] for fr in run["folds"]}
        assert b2["n_take_by_fold"] == want
        assert (b2["draws"]["gross"]["n_taken"] == sum(want.values())).all()
        assert 0.0 <= b2["ml_expectancy_percentile"] <= 1.0
        lo, hi = b2["expectancy_p05_p95"]
        assert lo <= b2["expectancy_mean"] <= hi
        assert b2["draws"]["rt0.20"]["expectancy"].shape == (run["meta"]["n_draws"],)


# 7. champion selection -----------------------------------------------------------------------------------------------------
def _m(n=150, exp=0.1, tot=15.0, dd=10.0, pf=1.2):
    return dict(n_resolved_taken=n, expectancy=exp, total_r=tot, max_dd=dd, profit_factor=pf)


def test_champion_needs_at_least_100_resolved_takes():
    res = X.select_champion({"logreg": _m(n=99, exp=0.9), "hist_gb": _m(n=100, exp=0.1)})
    assert res["champion"] == "hist_gb"
    assert [r["family"] for r in res["ranking"]] == ["hist_gb", "logreg"] and not res["ranking"][1]["eligible"]
    assert X.select_champion({"logreg": _m(n=100)})["champion"] == "logreg"
    assert X.select_champion({"logreg": _m(n=99)}, min_resolved_takes=50)["champion"] == "logreg"


def test_champion_ranking_order_expectancy_then_total_r_then_drawdown_then_pf_then_family():
    assert X.select_champion({"logreg": _m(exp=0.1), "hist_gb": _m(exp=0.2)})["champion"] == "hist_gb"
    assert X.select_champion({"logreg": _m(tot=10), "hist_gb": _m(tot=20)})["champion"] == "hist_gb"
    assert X.select_champion({"logreg": _m(dd=5), "hist_gb": _m(dd=9)})["champion"] == "logreg"
    assert X.select_champion({"logreg": _m(pf=1.1), "hist_gb": _m(pf=1.4)})["champion"] == "hist_gb"
    assert X.select_champion({"xgboost": _m(), "random_forest": _m()})["champion"] == "random_forest"  # frozen family order
    assert X.select_champion({"logreg": _m(exp=0.3, tot=1, dd=99, pf=0.5), "hist_gb": _m(exp=0.2, tot=99, dd=1, pf=9)})["champion"] == "logreg"


def test_champion_nan_profit_factor_ranks_last_on_that_key_only():
    assert X.select_champion({"logreg": _m(pf=np.nan), "hist_gb": _m(pf=0.5)})["champion"] == "hist_gb"
    assert X.select_champion({"logreg": _m(pf=np.nan, exp=0.3), "hist_gb": _m(pf=2.0, exp=0.1)})["champion"] == "logreg"
    assert X.select_champion({"logreg": _m(pf=np.nan), "hist_gb": _m(pf=np.nan)})["champion"] == "logreg"


def test_champion_none_when_nobody_is_eligible():
    res = X.select_champion({"logreg": _m(n=10), "hist_gb": _m(exp=np.nan)})
    assert res["champion"] is None and "100" in res["reason"] and len(res["ranking"]) == 2
    assert X.select_champion({})["champion"] is None


# 8. strict subset ----------------------------------------------------------------------------------------------------------
def test_exclusion_removes_rows_from_every_role_and_keeps_the_rest(checked):
    folds, d = checked
    ex = set(d.row_id.iloc[::17])
    out = X._apply_exclusion(folds, d, ex)
    ids = d.row_id.to_numpy()
    for f in folds:
        for role, idx in f.idx.items():
            kept = out[f.name][role]
            assert not set(ids[kept]) & ex and list(kept) == [i for i in idx if ids[i] not in ex]
    same = X._apply_exclusion(folds, d, set())
    assert all(np.array_equal(same[f.name][r], f.idx[r]) for f in folds for r in f.idx)


def test_strict_subset_run_keeps_folds_and_drops_the_flagged_rows(df, frozen, checked):
    _, d = checked
    ex = set(d[(d.entry_time >= "2023-01-01") & (d.entry_time < "2025-12-31")].row_id.iloc[::12])
    full = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    sub = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10, exclude_row_ids=ex)
    assert sub["meta"]["n_excluded_by_request"] == len(ex) and sub["meta"]["folds"] == full["meta"]["folds"]
    assert not set(sub["oof"].row_id) & ex and set(sub["oof"].row_id) == set(full["oof"].row_id) - ex
    assert len(sub["oof"]) == len(full["oof"]) - len(ex)


def test_minimum_sample_check_stops_the_run(df, frozen, checked):
    _, d = checked
    first = d[(d.entry_time >= "2023-01-01") & (d.entry_time < "2023-07-01")].row_id
    with pytest.raises(ValueError, match="minimum-sample checks failed"):
        X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=2, exclude_row_ids=set(first))


# 9. invalid inputs ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("col", ["risk", "outcome", "label", "row_id", "exit_time"])
def test_missing_required_column_is_rejected(df, frozen, col):
    with pytest.raises(ValueError, match="missing columns"):
        X.run_experiment(df.drop(columns=[col]), frozen, trading_days=TD, families=FAST, n_draws=2)


def test_missing_cost_or_baseline_column_is_rejected(df, frozen):
    with pytest.raises(ValueError, match="missing column"):
        X.run_experiment(df.drop(columns=[COST]), frozen, trading_days=TD, families=FAST, n_draws=2)
    with pytest.raises(ValueError, match="missing column"):
        X.run_experiment(df.drop(columns=["is_b0"]), frozen, trading_days=TD, families=FAST, n_draws=2)
    with pytest.raises(ValueError, match="missing column"):
        X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=2, baseline_column="nope")


def test_forbidden_feature_column_is_rejected(df, frozen):
    with pytest.raises(ValueError, match="forbidden columns"):
        X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=2, feature_columns=list(R.MODEL_COLUMNS) + ["outcome"])


def test_duplicate_row_ids_and_unknown_family_are_rejected(df, frozen):
    dup = df.copy()
    dup.loc[1, "row_id"] = dup.loc[0, "row_id"]
    with pytest.raises(ValueError, match="row_id must be unique"):
        X.build_checked_folds(dup, frozen, TD)
    with pytest.raises(ValueError, match="unknown model family"):
        X.run_experiment(df, frozen, trading_days=TD, families=("svm",), n_draws=2)


# 10. repeated indices and determinism --------------------------------------------------------------------------------------
def test_repeated_dataframe_indices_are_supported(df, frozen):
    dup = df.set_axis(np.arange(len(df)) % 7)
    assert not dup.index.is_unique
    a = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    b = X.run_experiment(dup, frozen, trading_days=TD, families=FAST, n_draws=10)
    assert _p_take_equal(a, b) and a["pooled"] == b["pooled"] and a["champion"] == b["champion"]


def test_rerun_is_deterministic(df, frozen):
    a = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    b = X.run_experiment(df, frozen, trading_days=TD, families=FAST, n_draws=10)
    assert _p_take_equal(a, b) and a["pooled"] == b["pooled"] and a["champion"] == b["champion"]
    assert a["folds"][0]["models"]["logreg"]["candidates"] == b["folds"][0]["models"]["logreg"]["candidates"]
    for s in SCEN:
        for k, v in a["b2"]["logreg"]["draws"][s].items():
            assert np.array_equal(v, b["b2"]["logreg"]["draws"][s][k], equal_nan=True)


# 11. no file / project-data dependency -------------------------------------------------------------------------------------
def test_module_has_no_file_io_paths_or_strategy_names():
    src = inspect.getsource(X)
    for token in ("read_csv", "to_csv", "open(", "results/", "candidates.csv", "labeled.csv", "fold_assignments", "DIT15", "WIT", "MIT",
                  "nogit-", "argparse", "sys.argv"):
        assert token not in src


def test_supplied_trading_calendar_is_used_instead_of_the_project_file(df, frozen, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("project calendar must not be loaded when trading_days is supplied")
    monkeypatch.setattr(S, "default_trading_days", boom)
    folds, _ = X.build_checked_folds(df, frozen, TD)
    assert len(folds) == 6
