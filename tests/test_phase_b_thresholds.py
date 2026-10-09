"""Unit tests for src/ml/thresholds.py (frozen T1 rule and secondary T2 search). Small deterministic synthetic arrays only; no project
data, Phase A outputs, folds or trading data.
Run: python -m pytest tests/test_phase_b_thresholds.py -q
"""
import inspect
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import thresholds as T  # noqa: E402


# 1. training loss magnitude ------------------------------------------------------------------------------------------------
def test_l_is_mean_absolute_r_of_loss_rows_only():
    outcome = np.array(["WIN", "LOSS", "LOSS", "AMBIGUOUS", "WIN"])
    r = np.array([2.0, -1.0, -1.5, 0.0, 2.0])
    assert T.compute_l_from_training(outcome, r) == pytest.approx(1.25)


def test_l_ignores_win_and_unresolved_rows():
    outcome = np.array(["LOSS", "WIN", "AMBIGUOUS", "CENSORED", "LOSS"])
    a = T.compute_l_from_training(outcome, np.array([-1.0, 2.0, 0.0, 0.0, -1.2]))
    b = T.compute_l_from_training(outcome, np.array([-1.0, 99.0, np.nan, np.nan, -1.2]))  # other rows are never read
    assert a == b == pytest.approx(1.1)


def test_l_uses_absolute_value_and_custom_label():
    assert T.compute_l_from_training(np.array(["L", "L", "W"]), np.array([-1.0, 1.0, 2.0]), loss_label="L") == 1.0


def test_l_rejects_mismatched_lengths_and_bad_shapes():
    with pytest.raises(ValueError):
        T.compute_l_from_training(np.array(["LOSS", "WIN"]), np.array([-1.0]))
    with pytest.raises(ValueError):
        T.compute_l_from_training(np.array([["LOSS"]]), np.array([[-1.0]]))


def test_l_rejects_input_without_loss_rows():
    with pytest.raises(ValueError, match="no LOSS rows"):
        T.compute_l_from_training(np.array(["WIN", "WIN", "AMBIGUOUS"]), np.array([2.0, 2.0, 0.0]))
    with pytest.raises(ValueError, match="no LOSS rows"):
        T.compute_l_from_training(np.array([]), np.array([]))


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_l_rejects_non_finite_loss_r(bad):
    with pytest.raises(ValueError, match="NaN or infinite"):
        T.compute_l_from_training(np.array(["LOSS", "LOSS"]), np.array([-1.0, bad]))


def test_l_rejects_all_zero_losses():
    with pytest.raises(ValueError, match="not positive"):
        T.compute_l_from_training(np.array(["LOSS", "LOSS"]), np.array([0.0, 0.0]))


# 2. T1 break-even ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("L,c", [(1.0, 0.5), (1.1, 0.1), (1.25, 0.0), (1.0, 0.07), (2.0, 1.0)])
def test_breakeven_matches_algebra_and_zeroes_the_expected_value(L, c):
    be = T.t1_breakeven(L, c)
    assert be == pytest.approx((L + c) / (2.0 + L), rel=0, abs=1e-15)
    ev = T.t1_expected_value(np.array([be]), np.array([c]), L)[0]
    assert abs(ev) < 1e-12


def test_breakeven_uses_supplied_w_and_is_not_clipped():
    assert T.t1_breakeven(1.0, 0.5, W=3.0) == pytest.approx(1.5 / 4.0)
    assert T.t1_breakeven(1.0, 5.0) > 1.0  # no probability can qualify


@pytest.mark.parametrize("kw", [dict(L=0.0, c=0.1), dict(L=-1.0, c=0.1), dict(L=np.nan, c=0.1), dict(L=np.inf, c=0.1),
                                dict(L=1.0, c=-0.1), dict(L=1.0, c=np.nan), dict(L=1.0, c=np.inf),
                                dict(L=1.0, c=0.1, W=0.0), dict(L=1.0, c=0.1, W=-2.0), dict(L=1.0, c=0.1, W=np.nan)])
def test_breakeven_rejects_invalid_inputs(kw):
    with pytest.raises(ValueError):
        T.t1_breakeven(**kw)


def test_breakeven_is_only_a_reference_decisions_go_through_apply_t1():
    L, c = 1.1, 0.1
    be = T.t1_breakeven(L, c)
    p = np.array([be])
    ev = T.t1_expected_value(p, np.array([c]), L)
    assert T.apply_t1(p, np.array([c]), L)[0] == bool(ev[0] > 0)  # the EV inequality is authoritative
    # at the break-even itself, rounding in the EV can make it positive although p > be is False: do not compare p with be
    assert not (p[0] > be)
    assert T.apply_t1(p, np.array([c]), L)[0]
    assert "decide takes" in (T.__doc__ or "") or "do not decide takes" in (T.__doc__ or "")


# 3. T1 expected value ------------------------------------------------------------------------------------------------------
def test_expected_value_matches_the_frozen_formula():
    p = np.array([0.0, 0.25, 0.5, 0.9, 1.0])
    c = np.array([0.1, 0.0, 0.2, 0.05, 0.3])
    L = 1.2
    assert np.allclose(T.t1_expected_value(p, c, L), p * 2.0 - (1 - p) * L - c, rtol=0, atol=1e-15)


def test_expected_value_signs():
    L, c = 1.0, np.array([0.5])
    assert T.t1_expected_value(np.array([0.9]), c, L)[0] > 0
    assert T.t1_expected_value(np.array([0.1]), c, L)[0] < 0
    assert T.t1_expected_value(np.array([0.5]), c, L)[0] == 0.0  # exactly representable: 1.0 - 0.5 - 0.5
    assert abs(T.t1_expected_value(np.array([0.5 + 1e-12]), c, L)[0] - 3e-12) < 1e-15


def test_w_is_fixed_at_two():
    assert T.W_FIXED == 2.0
    assert T.t1_expected_value(np.array([1.0]), np.array([0.0]), 1.0)[0] == 2.0  # p=1 pays exactly W


# 4. T1 application ---------------------------------------------------------------------------------------------------------
def test_apply_t1_is_strictly_greater_than_zero():
    L, c = 1.0, np.full(3, 0.5)  # break-even is exactly 0.5 and EV(0.5) is exactly 0
    mask = T.apply_t1(np.array([0.4999999, 0.5, 0.5000001]), c, L)
    assert mask.tolist() == [False, False, True]
    assert mask.dtype == bool


def test_apply_t1_does_not_round_probabilities():
    mask = T.apply_t1(np.array([0.5 + 1e-12, 0.5 - 1e-12]), np.full(2, 0.5), 1.0)
    assert mask.tolist() == [True, False]


def test_apply_t1_supports_per_row_costs():
    p = np.full(4, 0.5)
    c = np.array([0.0, 0.4, 0.5, 0.9])
    assert T.apply_t1(p, c, 1.0).tolist() == [True, True, False, False]


def test_apply_t1_accepts_probability_bounds_and_lists():
    assert T.apply_t1([0.0, 1.0], [0.1, 0.1], 1.0).tolist() == [False, True]


@pytest.mark.parametrize("p", [[1.0000001], [-0.1], [np.nan], [np.inf], [-np.inf]])
def test_apply_t1_rejects_bad_probabilities(p):
    with pytest.raises(ValueError):
        T.apply_t1(p, [0.1], 1.0)


@pytest.mark.parametrize("c", [[-0.01], [np.nan], [np.inf]])
def test_apply_t1_rejects_bad_costs(c):
    with pytest.raises(ValueError):
        T.apply_t1([0.5], c, 1.0)


def test_apply_t1_rejects_mismatched_lengths_and_bad_l():
    with pytest.raises(ValueError, match="same length"):
        T.apply_t1([0.5, 0.6], [0.1], 1.0)
    with pytest.raises(ValueError):
        T.apply_t1(np.zeros((2, 2)), np.zeros((2, 2)), 1.0)
    for bad_l in (0.0, -1.0, np.nan, np.inf):
        with pytest.raises(ValueError):
            T.apply_t1([0.5], [0.1], bad_l)


def test_w_cannot_be_changed_through_apply_t1():
    for fn in (T.apply_t1, T.t1_expected_value):
        assert "W" not in inspect.signature(fn).parameters
        with pytest.raises(TypeError):
            fn([0.5], [0.1], 1.0, W=3.0)
        with pytest.raises(TypeError):
            fn([0.5], [0.1], 1.0, 3.0)


# 5. T2 grid ----------------------------------------------------------------------------------------------------------------
def test_t2_grid_is_the_frozen_46_value_list():
    g = T.T2_GRID
    assert len(g) == 46
    assert g[0] == 0.15 and g[-1] == 0.60
    assert list(g) == sorted(g) and len(set(g)) == 46
    assert all(round(b - a, 10) == 0.01 for a, b in zip(g, g[1:]))
    assert g == tuple(round(0.15 + 0.01 * i, 2) for i in range(46))


def test_t2_candidates_are_sorted_and_deduplicated():
    assert T.t2_candidate_thresholds() == list(T.T2_GRID)
    assert T.t2_candidate_thresholds(0.25) == list(T.T2_GRID)  # already in the grid
    extra = T.t2_candidate_thresholds(0.3305)
    assert len(extra) == 47 and extra == sorted(extra) and 0.3305 in extra
    assert T.t2_candidate_thresholds(0.9)[-1] == 0.9 and T.t2_candidate_thresholds(0.9)[:-1] == list(T.T2_GRID)
    with pytest.raises(ValueError):
        T.t2_candidate_thresholds(np.nan)
    with pytest.raises(ValueError):
        T.t2_candidate_thresholds(np.inf)


# 6. T2 validation selection -----------------------------------------------------------------------------------------------
def _case(groups):
    """groups: list of (count, p, net_r) -> p, net_r, resolved (all resolved)."""
    p = np.concatenate([np.full(n, pv) for n, pv, _ in groups])
    r = np.concatenate([np.full(n, rv) for n, _, rv in groups])
    return p, r, np.ones(len(p), dtype=bool)


def test_min_takes_is_max_of_30_and_ten_percent_rounded_up():
    assert T.t2_min_takes(1) == 30 and T.t2_min_takes(100) == 30 and T.t2_min_takes(300) == 30
    assert T.t2_min_takes(301) == 31 and T.t2_min_takes(400) == 40 and T.t2_min_takes(405) == 41
    assert T.t2_min_takes(0) == 30


def test_t2_uses_only_resolved_rows():
    p, r, res = _case([(30, 0.55, 1.0), (70, 0.10, -1.0)])
    base = T.select_t2(p, r, res)
    # add unresolved rows with the highest possible p and NaN net R: they must not be read or counted
    p2 = np.concatenate([p, np.ones(50)])
    r2 = np.concatenate([r, np.full(50, np.nan)])
    res2 = np.concatenate([res, np.zeros(50, dtype=bool)])
    out = T.select_t2(p2, r2, res2)
    assert (out.threshold, out.n_taken, out.expectancy, out.min_takes) == (base.threshold, base.n_taken, base.expectancy, base.min_takes)
    assert out.n_taken == 30 and out.min_takes == 30  # the 10% share follows the resolved count (100), not the 150 total rows


def test_t2_min_takes_follows_resolved_count():
    p, r, res = _case([(100, 0.55, 1.0), (300, 0.10, -1.0)])  # 400 resolved -> need 40
    assert T.select_t2(p, r, res).min_takes == 40


def test_t2_rejects_candidates_below_the_minimum_takes():
    p, r, res = _case([(10, 0.55, 2.0), (50, 0.30, 0.2), (40, 0.10, -1.0)])  # need 30
    out = T.select_t2(p, r, res)
    by_t = {t: (n, e, ok) for t, n, e, ok in out.candidates}
    assert by_t[0.30] == (10, 2.0, False) and by_t[0.54] == (10, 2.0, False)  # best expectancy but only 10 takes
    assert by_t[0.15][2] and by_t[0.15][0] == 60
    assert (out.threshold, out.n_taken) == (0.15, 60)
    assert out.expectancy == pytest.approx((10 * 2.0 + 50 * 0.2) / 60)
    assert by_t[0.55] == (0, None, False) and by_t[0.60] == (0, None, False)


def test_t2_highest_expectancy_wins_over_more_takes():
    p, r, res = _case([(30, 0.55, 1.0), (40, 0.40, -0.5), (30, 0.10, -1.0)])
    out = T.select_t2(p, r, res)
    low = {t: (n, e) for t, n, e, _ in out.candidates}[0.15]
    assert low[0] == 70 and low[1] == pytest.approx(10 / 70)
    assert (out.threshold, out.n_taken, out.expectancy) == (0.40, 30, 1.0)  # first threshold excluding the 0.40 group


def test_t2_expectancy_tie_breaks_by_more_takes():
    p, r, res = _case([(30, 0.55, 1.0), (20, 0.40, 1.0), (50, 0.10, -1.0)])
    out = T.select_t2(p, r, res)
    table = {t: (n, e, ok) for t, n, e, ok in out.candidates}
    assert table[0.40] == (30, 1.0, True) and table[0.15] == (50, 1.0, True)  # same expectancy, different take counts
    assert (out.threshold, out.n_taken, out.expectancy) == (0.15, 50, 1.0)


def test_t2_remaining_tie_breaks_by_lower_threshold():
    p, r, res = _case([(40, 0.55, 1.0), (60, 0.20, -1.0)])
    out = T.select_t2(p, r, res)
    ties = [t for t, n, e, ok in out.candidates if ok and e == 1.0 and n == 40]
    assert len(ties) > 5 and min(ties) == 0.20  # identical take sets at 0.20 .. 0.54
    assert (out.threshold, out.n_taken, out.expectancy) == (0.20, 40, 1.0)


def test_t2_takes_are_strictly_above_the_threshold():
    p, r, res = _case([(30, 0.30, 1.0), (70, 0.10, -1.0)])
    by_t = {t: n for t, n, _, _ in T.select_t2(p, r, res).candidates}
    assert by_t[0.29] == 30 and by_t[0.30] == 0  # p == t is not a take


def test_t2_returns_no_threshold_when_no_candidate_is_eligible():
    p, r, res = _case([(100, 0.01, 1.0)])
    out = T.select_t2(p, r, res)
    assert out.threshold is None and out.n_taken == 0 and math.isnan(out.expectancy) and out.min_takes == 30
    assert len(out.candidates) == 46 and not any(ok for *_, ok in out.candidates)
    p2, r2, res2 = _case([(20, 0.55, 1.0), (80, 0.10, -1.0)])  # only 20 takes possible, 30 needed
    assert T.select_t2(p2, r2, res2).threshold is None


def test_t2_is_deterministic():
    rng = np.random.default_rng(3)
    p = rng.uniform(0, 1, 300)
    r = np.where(rng.random(300) < p * 0.8, 1.9, -1.1)
    res = rng.random(300) > 0.1
    a, b = T.select_t2(p, r, res, 0.33), T.select_t2(p, r, res, 0.33)
    assert (a.threshold, a.expectancy, a.n_taken, a.min_takes) == (b.threshold, b.expectancy, b.n_taken, b.min_takes)
    assert a.candidates == b.candidates
    assert [c[0] for c in a.candidates] == sorted(c[0] for c in a.candidates)


def test_t2_input_validation():
    p, r, res = _case([(40, 0.55, 1.0), (60, 0.10, -1.0)])
    with pytest.raises(ValueError, match="boolean mask"):
        T.select_t2(p, r, res.astype(int))
    with pytest.raises(ValueError, match="equal length"):
        T.select_t2(p, r[:-1], res)
    with pytest.raises(ValueError, match="in \\[0, 1\\]"):
        T.select_t2(np.where(np.arange(100) == 0, 1.5, p), r, res)
    with pytest.raises(ValueError, match="NaN or infinite"):
        T.select_t2(np.where(np.arange(100) == 0, np.nan, p), r, res)
    bad_r = r.copy()
    bad_r[0] = np.nan
    with pytest.raises(ValueError, match="every resolved row"):
        T.select_t2(p, bad_r, res)
    T.select_t2(p, bad_r, np.arange(100) != 0)  # a NaN on an unresolved row is fine
    with pytest.raises(ValueError, match="no resolved"):
        T.select_t2(p, r, np.zeros(100, dtype=bool))


# 7. T2 break-even candidate -------------------------------------------------------------------------------------------------
def test_select_t2_evaluates_an_explicit_break_even_as_another_candidate():
    p, r, res = _case([(30, 0.331, 1.0), (30, 0.3302, -1.0), (40, 0.10, 0.0)])
    without = T.select_t2(p, r, res)
    assert 0.3305 not in [c[0] for c in without.candidates]
    assert without.expectancy == 0.0 and without.threshold == 0.15  # no grid value isolates the 0.331 group

    be = 0.3305  # supplied explicitly by the caller (the thresholds module does not compute the scalar cost)
    out = T.select_t2(p, r, res, t1_breakeven_value=be)
    table = {t: (n, e, ok) for t, n, e, ok in out.candidates}
    assert len(out.candidates) == 47 and table[be] == (30, 1.0, True)
    assert (out.threshold, out.n_taken, out.expectancy) == (be, 30, 1.0)


def test_select_t2_break_even_equal_to_a_grid_value_is_not_duplicated():
    p, r, res = _case([(40, 0.55, 1.0), (60, 0.10, -1.0)])
    assert len(T.select_t2(p, r, res, t1_breakeven_value=0.25).candidates) == 46


def test_select_t2_rejects_a_non_finite_break_even():
    p, r, res = _case([(40, 0.55, 1.0), (60, 0.10, -1.0)])
    with pytest.raises(ValueError):
        T.select_t2(p, r, res, t1_breakeven_value=np.nan)


def test_thresholds_module_does_not_compute_the_t2_scalar_cost():
    src = inspect.getsource(T)
    assert "cost_in_r" not in src.replace("per-row cost in R", "") and "mean(training" not in src
    assert "t1_breakeven_value" in inspect.signature(T.select_t2).parameters


# 8. no project dependencies ------------------------------------------------------------------------------------------------
def test_module_imports_nothing_from_the_project():
    src = inspect.getsource(T)
    for name in ("portfolio", "costs", "splits", "registry", "features", "labels", "models", "pandas", "candidates"):
        assert f"import {name}" not in src and f"from ml import {name}" not in src
    assert "read_csv" not in src and "results/" not in src and "DIT15" not in src
