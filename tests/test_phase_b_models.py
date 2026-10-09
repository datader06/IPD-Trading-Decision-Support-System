"""Unit tests for src/ml/models.py (frozen Experiment 1 model layer). Small deterministic synthetic data only; no project data.
Run: python -m pytest tests/test_phase_b_models.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import NotFittedError
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import models as M  # noqa: E402

N_FEAT = 6
CONFIGS = M.frozen_configs()
IDS = [c.name for c in CONFIGS]


@pytest.fixture(scope="module")
def data():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, N_FEAT))
    y = (X[:, 0] + 0.5 * rng.normal(size=300) > 0.3).astype(int)
    return X[:200], y[:200], X[200:], y[200:]


def _fit(c, d, **kw):
    Xt, yt, Xv, yv = d
    return M.fit(c, Xt, yt, Xv, yv, **kw) if c.family == "xgboost" else M.fit(c, Xt, yt, **kw)


def _is_fitted(est):
    from sklearn.utils.validation import check_is_fitted
    try:
        check_is_fitted(est)
        return True
    except NotFittedError:
        return False


# 1. enumeration ------------------------------------------------------------------------------------------------------------
def test_nine_frozen_configurations_with_expected_values():
    assert len(CONFIGS) == 9
    got = {f: [c.value for c in CONFIGS if c.family == f] for f in M.FAMILIES}
    assert M.FAMILIES == ("logreg", "random_forest", "hist_gb", "xgboost")
    assert got == {"logreg": [0.01, 0.1, 1.0], "random_forest": [3, 6], "hist_gb": [100, 200], "xgboost": [2, 3]}
    assert {c.family: c.param for c in CONFIGS} == {"logreg": "C", "random_forest": "max_depth", "hist_gb": "max_iter",
                                                    "xgboost": "max_depth"}


def test_enumeration_order_is_deterministic():
    assert IDS == [c.name for c in M.frozen_configs()]
    assert [c.family for c in CONFIGS] == ["logreg"] * 3 + ["random_forest"] * 2 + ["hist_gb"] * 2 + ["xgboost"] * 2
    assert [c.name for c in M.frozen_configs("random_forest")] == ["random_forest:max_depth=3", "random_forest:max_depth=6"]


# 2. invalid configurations -------------------------------------------------------------------------------------------------
def test_unknown_family_is_rejected():
    with pytest.raises(ValueError):
        M.frozen_configs("svm")
    with pytest.raises(ValueError):
        M.make_model(M.ModelConfig("svm", "C", 1.0))


@pytest.mark.parametrize("cfg", [M.ModelConfig("logreg", "C", 10.0), M.ModelConfig("random_forest", "max_depth", 4),
                                 M.ModelConfig("hist_gb", "max_iter", 150), M.ModelConfig("xgboost", "max_depth", 5),
                                 M.ModelConfig("logreg", "max_depth", 3)])
def test_values_outside_frozen_grids_are_rejected(cfg):
    with pytest.raises(ValueError):
        M.make_model(cfg)
    with pytest.raises(ValueError):
        M.fit(cfg, np.zeros((4, 2)), np.array([0, 1, 0, 1]))


# 3. construction -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", CONFIGS, ids=IDS)
def test_all_configurations_construct_unfitted(cfg):
    est = M.make_model(cfg)
    assert not _is_fitted(est)


def test_frozen_hyperparameters_are_present():
    lr = M.make_model(M.ModelConfig("logreg", "C", 0.1))
    assert isinstance(lr.named_steps["scale"], StandardScaler)
    clf = lr.named_steps["clf"]
    assert isinstance(clf, LogisticRegression)
    assert (clf.C, clf.penalty, clf.solver, clf.class_weight, clf.random_state) == (0.1, "l2", "lbfgs", None, 42)

    rf = M.make_model(M.ModelConfig("random_forest", "max_depth", 6))
    assert isinstance(rf, RandomForestClassifier)
    assert (rf.n_estimators, rf.min_samples_leaf, rf.max_depth, rf.class_weight, rf.n_jobs, rf.random_state) == (500, 30, 6, None, 1, 42)

    hgb = M.make_model(M.ModelConfig("hist_gb", "max_iter", 200))
    assert isinstance(hgb, HistGradientBoostingClassifier)
    assert (hgb.max_depth, hgb.max_leaf_nodes, hgb.min_samples_leaf, hgb.learning_rate, hgb.l2_regularization) == (3, 7, 50, 0.05, 1.0)
    assert (hgb.early_stopping, hgb.max_iter, hgb.class_weight, hgb.random_state) == (False, 200, None, 42)

    xgb = M.make_model(M.ModelConfig("xgboost", "max_depth", 3))
    assert isinstance(xgb, XGBClassifier)
    assert (xgb.tree_method, xgb.learning_rate, xgb.subsample, xgb.max_depth) == ("hist", 0.05, 1.0, 3)
    assert (xgb.n_estimators, xgb.early_stopping_rounds, xgb.n_jobs, xgb.random_state) == (500, 30, 1, 42)


# 4. input validation -------------------------------------------------------------------------------------------------------
LR = M.ModelConfig("logreg", "C", 1.0)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_x_is_rejected(data, bad):
    Xt, yt, _, _ = data
    X = Xt.copy()
    X[3, 1] = bad
    with pytest.raises(ValueError, match="NaN or infinite"):
        M.fit(LR, X, yt)


def test_non_binary_y_is_rejected(data):
    Xt, yt, _, _ = data
    y = yt.copy()
    y[0] = 2
    with pytest.raises(ValueError, match="only 0 and 1"):
        M.fit(LR, Xt, y)


def test_single_class_y_is_rejected(data):
    Xt, _, _, _ = data
    with pytest.raises(ValueError, match="both classes"):
        M.fit(LR, Xt, np.zeros(len(Xt), dtype=int))


def test_mismatched_row_counts_are_rejected(data):
    Xt, yt, _, _ = data
    with pytest.raises(ValueError, match="one value per row"):
        M.fit(LR, Xt, yt[:-1])


def test_x_must_be_two_dimensional(data):
    _, yt, _, _ = data
    with pytest.raises(ValueError, match="2-dimensional"):
        M.fit(LR, np.zeros(len(yt)), yt)


# 5. fit and predict --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", CONFIGS, ids=IDS)
def test_every_configuration_fits_and_predicts_valid_probabilities(cfg, data):
    m = _fit(cfg, data)
    assert _is_fitted(m.estimator)
    Xv = data[2]
    p = M.predict_proba(m, Xv)
    assert p.shape == (len(Xv),)
    assert np.isfinite(p).all()
    assert ((p >= 0) & (p <= 1)).all()
    assert p.std() > 0  # not a constant prediction


# 6. validation-data contract -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", [c for c in CONFIGS if c.family != "xgboost"], ids=[c.name for c in CONFIGS if c.family != "xgboost"])
def test_non_xgboost_models_reject_validation_data(cfg, data):
    Xt, yt, Xv, yv = data
    with pytest.raises(ValueError, match="does not use validation data"):
        M.fit(cfg, Xt, yt, Xv, yv)
    with pytest.raises(ValueError, match="does not use validation data"):
        M.fit(cfg, Xt, yt, X_val=Xv)


def test_xgboost_requires_validation_data_for_early_stopping(data):
    Xt, yt, Xv, yv = data
    cfg = M.ModelConfig("xgboost", "max_depth", 2)
    with pytest.raises(ValueError, match="needs X_val and y_val"):
        M.fit(cfg, Xt, yt)
    with pytest.raises(ValueError, match="needs X_val and y_val"):
        M.fit(cfg, Xt, yt, X_val=Xv)


def test_xgboost_validation_data_is_checked(data):
    Xt, yt, Xv, yv = data
    cfg = M.ModelConfig("xgboost", "max_depth", 2)
    with pytest.raises(ValueError, match="different number of features"):
        M.fit(cfg, Xt, yt, Xv[:, :-1], yv)
    with pytest.raises(ValueError, match="both classes"):
        M.fit(cfg, Xt, yt, Xv, np.zeros(len(Xv), dtype=int))


@pytest.mark.parametrize("cfg", M.frozen_configs("xgboost"), ids=[c.name for c in M.frozen_configs("xgboost")])
def test_xgboost_early_stops_with_validation_data(cfg, data):
    m = _fit(cfg, data)
    assert 1 <= m.best_rounds < M.XGB_MAX_ROUNDS  # stopped before the 500-round cap on this noisy synthetic target
    assert m.best_rounds == int(m.estimator.best_iteration) + 1


# 7. XGBoost pool refit -----------------------------------------------------------------------------------------------------
def test_best_rounds_recorded_and_fixed_round_refit_needs_no_validation(data):
    Xt, yt, Xv, _ = data
    cfg = M.ModelConfig("xgboost", "max_depth", 3)
    first = _fit(cfg, data)
    n = first.best_rounds
    refit = M.fit(cfg, np.vstack([Xt, Xv[:50]]), np.concatenate([yt, data[3][:50]]), n_rounds=n)
    assert refit.best_rounds == n
    assert refit.estimator.get_params()["n_estimators"] == n
    assert refit.estimator.get_params()["early_stopping_rounds"] is None
    assert len(refit.estimator.get_booster().get_dump()) == n
    p = M.predict_proba(refit, Xv)
    assert p.shape == (len(Xv),) and ((p >= 0) & (p <= 1)).all()


def test_fixed_round_refit_rejects_validation_data_and_non_xgboost_n_rounds(data):
    Xt, yt, Xv, yv = data
    with pytest.raises(ValueError, match="not used when n_rounds"):
        M.fit(M.ModelConfig("xgboost", "max_depth", 2), Xt, yt, Xv, yv, n_rounds=10)
    with pytest.raises(ValueError, match="xgboost only"):
        M.fit(LR, Xt, yt, n_rounds=10)
    with pytest.raises(ValueError, match="xgboost only"):
        M.make_model(M.ModelConfig("hist_gb", "max_iter", 100), n_rounds=10)


# 8. determinism ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", CONFIGS, ids=IDS)
def test_same_data_gives_identical_probabilities(cfg, data):
    a = M.predict_proba(_fit(cfg, data), data[2])
    b = M.predict_proba(_fit(cfg, data), data[2])
    assert np.array_equal(a, b)


# 9. feature-count guard ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", CONFIGS[::3], ids=IDS[::3])
def test_predict_rejects_wrong_feature_count(cfg, data):
    m = _fit(cfg, data)
    Xv = data[2]
    with pytest.raises(ValueError, match="expected 6 features"):
        M.predict_proba(m, Xv[:, :-1])
    with pytest.raises(ValueError, match="expected 6 features"):
        M.predict_proba(m, np.hstack([Xv, Xv[:, :1]]))
