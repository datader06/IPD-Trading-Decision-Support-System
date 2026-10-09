"""Unit tests for src/ml/evaluate.py (take-set evaluation, classifier metrics, B2 random filter). Synthetic data only; no project data,
files, Phase A outputs or folds.
Run: python -m pytest tests/test_phase_b_evaluate.py -q
"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import costs  # noqa: E402
import portfolio as P  # noqa: E402
from ml import evaluate as E  # noqa: E402

SCEN = ["gross", "rt0.10", "rt0.20", "rt0.30"]
T0 = pd.Timestamp("2024-03-01 09:15")


def _row(outcome, r, entry=100.0, risk=2.0, fill=None, ticker="A", fill_h=0, exit_h=5):
    fill = entry if fill is None else fill
    resolved = outcome in ("WIN", "LOSS")
    return dict(outcome=outcome, r_gross=r if resolved else np.nan, fill_price=fill,
                exit_price=fill + r * risk if resolved else np.nan, risk=risk, ticker=ticker, entry_price=entry,
                fill_time=T0 + pd.Timedelta(hours=fill_h), exit_time=T0 + pd.Timedelta(hours=exit_h))


@pytest.fixture(scope="module")
def frame():
    rng = np.random.default_rng(5)
    n = 80
    out = rng.choice(list(E.OUTCOMES), size=n, p=[.3, .4, .15, .05, .05, .05])
    entry = rng.uniform(100, 500, n)
    risk = entry * rng.uniform(.005, .02, n)
    fill = entry + rng.choice([0.0, 0.1], n)
    rg = np.where(out == "WIN", rng.choice([2.0, 2.4], n, p=[.9, .1]), np.where(out == "LOSS", rng.choice([-1.0, -1.8], n, p=[.9, .1]), np.nan))
    ft = T0 + pd.to_timedelta(rng.integers(0, 300, n), unit="h")
    df = pd.DataFrame(dict(outcome=out, r_gross=rg, fill_price=fill,
                           exit_price=np.where(np.isin(out, ["WIN", "LOSS"]), fill + rg * risk, np.nan), risk=risk,
                           fill_time=ft, exit_time=ft + pd.to_timedelta(rng.integers(1, 60, n), unit="h"),
                           ticker=rng.choice(list("ABCD"), n), entry_price=entry))
    df.index = rng.integers(0, 6, n)  # repeated, unordered index labels
    return df


@pytest.fixture(scope="module")
def take(frame):
    return np.random.default_rng(9).random(len(frame)) < 0.6


def _phase_a_columns(sub, base_g):
    """Phase A add_costs loop (scripts/run_phase_a.py): net R for resolved rows only, NaN elsewhere."""
    for cm in costs.scenarios(0.0):
        v = np.full(len(sub), np.nan)
        for i in np.flatnonzero(sub.outcome.isin(["WIN", "LOSS"]).to_numpy()):
            v[i] = cm.net_r(base_g[i], sub.fill_price.iat[i], sub.exit_price.iat[i], sub.risk.iat[i])
        sub[f"r_{cm.name}"] = v
    return sub


# 1. scenarios and agreement with portfolio semantics ----------------------------------------------------------------------
def test_all_four_scenarios_are_reported(frame, take):
    res = E.evaluate_take_set(frame, take)
    assert list(res) == SCEN
    assert all(isinstance(v, (int, float, np.integer, np.floating)) for s in res.values() for v in s.values())


@pytest.mark.parametrize("name", SCEN)
def test_metrics_agree_with_portfolio_summary(frame, take, name):
    res = E.evaluate_take_set(frame, take)[name]
    sub = frame[take].copy()
    base_g = sub["r_gross"].to_numpy().copy()
    sub = _phase_a_columns(sub, base_g)
    col = "r_gross" if name == "gross" else f"r_{name}"
    if name == "gross":
        sub["r_gross"] = base_g
    s = P.summary(sub, col)
    assert res["expectancy"] == pytest.approx(s["expectancy_r"], abs=1e-12)
    assert res["profit_factor"] == pytest.approx(s["profit_factor"], abs=1e-12)
    assert res["total_r"] == pytest.approx(s["total_r"], abs=1e-12)
    assert res["max_dd"] == pytest.approx(s["max_dd_r"], abs=1e-12)
    assert res["win_rate"] == pytest.approx(s["win_rate"] / 100, abs=1e-12)
    for k in ("WIN", "LOSS", "AMBIGUOUS", "CENSORED", "OPEN", "NOFILL"):
        assert res[k] == s[k]
    assert res["n_taken"] == s["n"] == int(take.sum())


def test_net_r_uses_actual_prices_and_the_cost_formula():
    df = pd.DataFrame([_row("WIN", 2.0, entry=100.0, risk=2.0), _row("LOSS", -1.0, entry=100.0, risk=2.0, fill_h=1, exit_h=6)])
    res = E.evaluate_take_set(df, np.array([True, True]))
    cost = 0.002 / 2 * 0 + (0.20 / 2 / 100) * (100.0 + 104.0) / 2.0  # WIN: fill 100, exit 104
    cost_l = (0.20 / 2 / 100) * (100.0 + 98.0) / 2.0               # LOSS: fill 100, exit 98
    assert res["rt0.20"]["total_r"] == pytest.approx((2.0 - cost) + (-1.0 - cost_l))
    assert res["gross"]["total_r"] == pytest.approx(1.0)


def test_actual_r_is_used_never_plus2_or_minus1():
    df = pd.DataFrame([_row("WIN", 2.6, fill_h=0, exit_h=3), _row("LOSS", -3.5, fill_h=1, exit_h=4)])
    res = E.evaluate_take_set(df, np.array([True, True]))["gross"]
    assert res["total_r"] == pytest.approx(-0.9) and res["expectancy"] == pytest.approx(-0.45)


@pytest.mark.parametrize("name", SCEN[1:])
def test_costs_lower_every_scenario_in_order(frame, take, name):
    res = E.evaluate_take_set(frame, take)
    order = SCEN
    assert res[order[order.index(name)]]["total_r"] < res[order[order.index(name) - 1]]["total_r"]


def test_portfolio_ordering_exit_then_fill_then_ticker_then_entry():
    # drawdown depends on the order: with exit order W, L, L the curve is +2 -1 -1 (dd 2); in input order it would differ
    rows = [_row("LOSS", -1.0, ticker="B", fill_h=0, exit_h=9), _row("LOSS", -1.0, ticker="A", fill_h=0, exit_h=8),
            _row("WIN", 2.0, ticker="C", fill_h=0, exit_h=1)]
    res = E.evaluate_take_set(pd.DataFrame(rows), np.ones(3, dtype=bool))["gross"]
    assert res["max_dd"] == 2.0 and res["total_r"] == 0.0
    # identical exit and fill times: ticker decides. A, B (losses) before C (win) gives 0 -> -1 -> -2 -> 0 (dd 2); win first would give dd 0
    tie = pd.DataFrame([_row("WIN", 2.0, ticker="C", exit_h=5), _row("LOSS", -1.0, ticker="B", exit_h=5),
                        _row("LOSS", -1.0, ticker="A", exit_h=5)])
    assert E.evaluate_take_set(tie, np.ones(3, dtype=bool))["gross"]["max_dd"] == 2.0
    # then entry price breaks a remaining tie (same ticker): lower entry price first
    tie2 = pd.DataFrame([_row("WIN", 2.0, ticker="A", entry=200.0, exit_h=5), _row("LOSS", -1.0, ticker="A", entry=100.0, exit_h=5)])
    assert E.evaluate_take_set(tie2, np.ones(2, dtype=bool))["gross"]["max_dd"] == 1.0  # loss (entry 100) first: 0 -> -1 -> +1


# 2. repeated indices -------------------------------------------------------------------------------------------------------
def test_repeated_dataframe_indices_are_supported(frame, take):
    assert not frame.index.is_unique
    a = E.evaluate_take_set(frame, take)
    b = E.evaluate_take_set(frame.reset_index(drop=True), take)
    c = E.evaluate_take_set(frame.set_axis(np.zeros(len(frame), dtype=int)), take)
    assert a == b == c


# 3. unresolved rows --------------------------------------------------------------------------------------------------------
def test_unresolved_counts_are_visible_and_excluded_from_r():
    rows = [_row("WIN", 2.0, exit_h=1), _row("LOSS", -1.0, exit_h=2), _row("AMBIGUOUS", 0.0, exit_h=3),
            _row("CENSORED", 0.0, exit_h=4), _row("OPEN", 0.0, exit_h=5), _row("NOFILL", 0.0, exit_h=6)]
    df = pd.DataFrame(rows)
    res = E.evaluate_take_set(df, np.ones(6, dtype=bool))["gross"]
    assert (res["n_rows"], res["n_taken"], res["n_resolved_taken"]) == (6, 6, 2)
    assert [res[k] for k in E.OUTCOMES] == [1, 1, 1, 1, 1, 1]
    assert res["win_rate"] == 0.5 and res["expectancy"] == 0.5 and res["total_r"] == 1.0 and res["profit_factor"] == 2.0
    assert res["max_dd"] == 1.0 and res["take_rate"] == 1.0  # R series from resolved rows only: +2 then -1


def test_untaken_rows_are_not_counted():
    df = pd.DataFrame([_row("WIN", 2.0), _row("AMBIGUOUS", 0.0), _row("LOSS", -1.0, exit_h=6)])
    res = E.evaluate_take_set(df, np.array([True, False, False]))["gross"]
    assert (res["n_taken"], res["WIN"], res["LOSS"], res["AMBIGUOUS"]) == (1, 1, 0, 0) and res["take_rate"] == pytest.approx(1 / 3)
    assert np.isnan(res["profit_factor"])  # no negative R: Phase A leaves PF undefined


def test_unknown_outcome_and_missing_columns_are_rejected():
    df = pd.DataFrame([_row("WIN", 2.0)])
    with pytest.raises(ValueError, match="unknown outcome"):
        E.Prepared(df.assign(outcome="MAYBE"))
    with pytest.raises(ValueError, match="missing columns"):
        E.Prepared(df.drop(columns=["risk"]))
    bad = df.copy()
    bad["exit_price"] = np.nan
    with pytest.raises(ValueError, match="resolved rows lack"):
        E.Prepared(bad)


# 4. ambiguity bounds -------------------------------------------------------------------------------------------------------
def test_gross_ambiguity_bounds_follow_phase_a():
    rows = [_row("WIN", 2.0, exit_h=1), _row("LOSS", -1.0, exit_h=2)] + [_row("AMBIGUOUS", 0.0, exit_h=3 + i) for i in range(3)]
    df = pd.DataFrame(rows)
    r = E.evaluate_take_set(df, np.ones(5, dtype=bool))["gross"]
    s = P.summary(df.assign(r_gross=df["r_gross"]), "r_gross")
    assert r["total_r_amb_best"] == pytest.approx(1.0 + 2.0 * 3) == pytest.approx(s["total_r_amb_best"])
    assert r["total_r_amb_worst"] == pytest.approx(1.0 - 1.0 * 3) == pytest.approx(s["total_r_amb_worst"])
    assert r["win_rate_amb_best"] == pytest.approx(s["win_rate_amb_best"] / 100) == pytest.approx(4 / 5)
    assert r["win_rate_amb_worst"] == pytest.approx(s["win_rate_amb_worst"] / 100) == pytest.approx(1 / 5)


def test_net_ambiguity_bounds_subtract_the_scenario_cost_and_bracket_the_total():
    rows = [_row("WIN", 2.0, exit_h=1), _row("AMBIGUOUS", 0.0, entry=100.0, risk=2.0, fill=100.0, exit_h=3)]
    r = E.evaluate_take_set(pd.DataFrame(rows), np.ones(2, dtype=bool))
    for name, pct in (("rt0.10", 0.10), ("rt0.20", 0.20), ("rt0.30", 0.30)):
        cost = (pct / 2 / 100) * 200.0 / 2.0
        assert r[name]["total_r_amb_best"] == pytest.approx(r[name]["total_r"] + 2.0 - cost)
        assert r[name]["total_r_amb_worst"] == pytest.approx(r[name]["total_r"] - 1.0 - cost)
        assert r[name]["total_r_amb_worst"] < r[name]["total_r"] < r[name]["total_r_amb_best"]
    assert r["gross"]["total_r_amb_best"] == pytest.approx(r["gross"]["total_r"] + 2.0)
    # the Phase A summary would add the gross +2 / -1 to a net total; the evaluator does not
    sub = pd.DataFrame(rows).assign(**{"r_rt0.20": [r["rt0.20"]["total_r"], np.nan]})
    assert P.summary(sub, "r_rt0.20")["total_r_amb_best"] != pytest.approx(r["rt0.20"]["total_r_amb_best"])


def test_no_ambiguous_rows_gives_bounds_equal_to_the_totals():
    df = pd.DataFrame([_row("WIN", 2.0), _row("LOSS", -1.0, exit_h=6)])
    r = E.evaluate_take_set(df, np.ones(2, dtype=bool))["rt0.20"]
    assert r["total_r_amb_best"] == r["total_r_amb_worst"] == pytest.approx(r["total_r"])
    assert r["win_rate_amb_best"] == r["win_rate_amb_worst"] == r["win_rate"]


# 5. empty take set ---------------------------------------------------------------------------------------------------------
def test_empty_take_set():
    df = pd.DataFrame([_row("WIN", 2.0), _row("AMBIGUOUS", 0.0), _row("LOSS", -1.0, exit_h=6)])
    for name, r in E.evaluate_take_set(df, np.zeros(3, dtype=bool)).items():
        assert (r["n_taken"], r["n_resolved_taken"], r["take_rate"]) == (0, 0, 0.0)
        assert all(r[k] == 0 for k in E.OUTCOMES)
        assert np.isnan(r["win_rate"]) and np.isnan(r["expectancy"]) and np.isnan(r["profit_factor"])
        assert r["total_r"] == 0.0 and r["max_dd"] == 0.0 and r["total_r_amb_best"] == 0.0 and r["total_r_amb_worst"] == 0.0


def test_frame_without_any_rows_or_resolved_rows():
    amb_only = pd.DataFrame([_row("AMBIGUOUS", 0.0)])
    r = E.evaluate_take_set(amb_only, np.ones(1, dtype=bool))["gross"]
    assert r["AMBIGUOUS"] == 1 and r["n_resolved_taken"] == 0 and np.isnan(r["expectancy"])
    assert r["total_r_amb_best"] == 2.0 and r["total_r_amb_worst"] == -1.0


# 6. ML metrics -------------------------------------------------------------------------------------------------------------
def test_ml_metrics_match_sklearn_on_resolved_rows(frame, take):
    outcome = frame["outcome"].to_numpy()
    p = np.random.default_rng(2).uniform(0.02, 0.98, len(frame))
    m = E.ml_metrics(outcome, p, take, base_rate=0.3)
    res = np.isin(outcome, ["WIN", "LOSS"])
    y = (outcome[res] == "WIN").astype(int)
    assert m["n_resolved"] == int(res.sum()) and m["n_pos"] == int(y.sum()) and m["n_neg"] == int((1 - y).sum())
    assert m["roc_auc"] == pytest.approx(roc_auc_score(y, p[res]))
    assert m["pr_auc"] == pytest.approx(average_precision_score(y, p[res]))
    assert m["brier"] == pytest.approx(brier_score_loss(y, p[res]))
    assert m["log_loss"] == pytest.approx(log_loss(y, p[res], labels=[0, 1]))
    assert m["brier_base_rate"] == pytest.approx(brier_score_loss(y, np.full(len(y), 0.3)))
    tr = take[res]
    tp = int((tr & (y == 1)).sum())
    assert m["predicted_positive"] == int(take.sum()) and m["predicted_positive_resolved"] == int(tr.sum())
    assert m["precision"] == pytest.approx(tp / tr.sum()) and m["recall"] == pytest.approx(tp / y.sum())
    assert m["base_rate_observed"] == pytest.approx(y.mean())


def test_ml_metrics_ignore_unresolved_rows_in_scores_but_count_them_as_predicted():
    outcome = np.array(["WIN", "LOSS", "AMBIGUOUS", "CENSORED"], dtype=object)
    p = np.array([0.9, 0.2, 0.99, 0.99])
    m = E.ml_metrics(outcome, p, np.array([True, False, True, True]))
    assert m["n_resolved"] == 2 and m["roc_auc"] == 1.0 and m["precision"] == 1.0 and m["recall"] == 1.0
    assert m["predicted_positive"] == 3 and m["predicted_positive_resolved"] == 1


def test_ml_metrics_undefined_values_are_nan_not_errors():
    only_win = E.ml_metrics(np.array(["WIN", "WIN"], dtype=object), np.array([0.6, 0.7]), np.array([True, False]))
    assert np.isnan(only_win["roc_auc"]) and only_win["pr_auc"] == 1.0 and only_win["recall"] == 0.5
    none_taken = E.ml_metrics(np.array(["WIN", "LOSS"], dtype=object), np.array([0.6, 0.4]), np.zeros(2, dtype=bool))
    assert np.isnan(none_taken["precision"]) and none_taken["recall"] == 0.0 and none_taken["predicted_positive"] == 0
    assert "brier_base_rate" not in none_taken


@pytest.mark.parametrize("p", [np.array([0.5, 1.2]), np.array([0.5, np.nan]), np.array([0.5, -0.1]), np.array([0.5])])
def test_ml_metrics_reject_bad_probabilities(p):
    with pytest.raises(ValueError):
        E.ml_metrics(np.array(["WIN", "LOSS"], dtype=object), p, np.ones(2, dtype=bool))


def test_ml_metrics_reject_bad_base_rate():
    with pytest.raises(ValueError):
        E.ml_metrics(np.array(["WIN", "LOSS"], dtype=object), np.array([0.6, 0.4]), np.ones(2, dtype=bool), base_rate=1.5)


# 7. B2 random filter -------------------------------------------------------------------------------------------------------
def test_random_filter_is_deterministic_and_exact_size():
    a, b, c = (E.random_filter_take(100, 25, s) for s in (7, 7, 8))
    assert a.dtype == bool and a.sum() == 25 and np.array_equal(a, b) and not np.array_equal(a, c)
    assert E.random_filter_take(10, 0, 1).sum() == 0 and E.random_filter_take(10, 10, 1).all()
    for bad in (-1, 11):
        with pytest.raises(ValueError):
            E.random_filter_take(10, bad, 1)


def test_evaluate_random_filter_is_reproducible_and_scores_like_any_take_set(frame):
    a, b = E.evaluate_random_filter(frame, 30, 4), E.evaluate_random_filter(frame, 30, 4)
    assert a == b and a["gross"]["n_taken"] == 30
    assert a != E.evaluate_random_filter(frame, 30, 5)
    mask = E.random_filter_take(len(frame), 30, 4)
    assert a == E.evaluate_take_set(frame, mask)


# 8. grouped sampling -------------------------------------------------------------------------------------------------------
def test_grouped_random_sampling_draws_exact_counts_per_group():
    groups = np.array(list("xyz" * 20))
    m = E.random_filter_take(60, {"x": 5, "y": 0, "z": 20}, 3, groups=groups)
    assert [int(m[groups == g].sum()) for g in "xyz"] == [5, 0, 20]
    assert np.array_equal(m, E.random_filter_take(60, {"z": 20, "x": 5, "y": 0}, 3, groups=groups))  # mapping order is irrelevant
    assert E.random_filter_take(60, {"x": 5}, 3, groups=groups).sum() == 5  # missing groups take nothing


def test_grouped_sampling_rejects_bad_requests():
    groups = np.array(list("xy" * 5))
    with pytest.raises(ValueError, match="must lie"):
        E.random_filter_take(10, {"x": 6}, 1, groups=groups)
    with pytest.raises(ValueError, match="one label per row"):
        E.random_filter_take(10, {"x": 1}, 1, groups=groups[:-1])


# 9. random distribution reproducibility ------------------------------------------------------------------------------------
def test_random_filter_distribution_is_reproducible(frame):
    d1 = E.random_filter_distribution(frame, 25, 20, seed=3)
    d2 = E.random_filter_distribution(frame, 25, 20, seed=3)
    assert list(d1) == SCEN
    for s in SCEN:
        for k, v in d1[s].items():
            assert v.shape == (20,) and np.array_equal(v, d2[s][k], equal_nan=True)
    assert not np.array_equal(d1["rt0.20"]["total_r"], E.random_filter_distribution(frame, 25, 20, seed=4)["rt0.20"]["total_r"])
    assert (d1["gross"]["n_taken"] == 25).all()


def test_each_draw_is_reproducible_alone(frame):
    d = E.random_filter_distribution(frame, 25, 6, seed=11)
    prep = E.Prepared(frame)
    for k in range(6):
        single = E.evaluate(prep, E.random_filter_take(len(frame), 25, [11, k]))
        assert d["rt0.20"]["total_r"][k] == single["rt0.20"]["total_r"]
        assert d["gross"]["max_dd"][k] == single["gross"]["max_dd"]


def test_distribution_supports_groups(frame):
    groups = np.array(list("ab" * (len(frame) // 2)))
    d = E.random_filter_distribution(frame, {"a": 7, "b": 5}, 5, seed=1, groups=groups)
    assert (d["gross"]["n_taken"] == 12).all()


# 10. invalid take masks ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [np.ones(79, dtype=bool), np.ones(81, dtype=bool), np.ones(80, dtype=int), np.ones(80, dtype=float),
                                 np.ones((80, 1), dtype=bool)])
def test_invalid_take_masks_are_rejected(frame, bad):
    with pytest.raises(ValueError, match="boolean array"):
        E.evaluate_take_set(frame, bad)
    with pytest.raises(ValueError, match="boolean array"):
        E.evaluate(E.Prepared(frame), bad)


# 11. no project-data / file dependencies -----------------------------------------------------------------------------------
def test_module_has_no_dataset_paths_strategy_names_or_file_io():
    src = inspect.getsource(E)
    for token in ("read_csv", "to_csv", "open(", "results/", "candidates.csv", "labeled.csv", "DIT15", "WIT", "MIT", "nogit-"):
        assert token not in src
    for name in ("registry", "features", "labels", "splits", "models", "thresholds"):
        assert f"import {name}" not in src and f"from ml import {name}" not in src
