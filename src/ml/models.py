"""Frozen model layer for Experiment 1: configurations, construction, fitting and native probabilities.

Strategy-agnostic: it only sees a feature matrix, a 0/1 target and (for XGBoost) validation rows. It knows nothing about
strategies, datasets, folds, thresholds or trading metrics; those live in other modules.

Global rules: seed 42, one thread, no class weights, no resampling, native probabilities (no calibration). The grids below are
the frozen Experiment 1 grids and are not meant to be extended. Choosing among configurations (validation log-loss) is the
caller's job.
"""
from dataclasses import dataclass

import numpy as np

SEED = 42
FAMILIES = ("logreg", "random_forest", "hist_gb", "xgboost")

_GRIDS = {
    "logreg": ("C", (0.01, 0.1, 1.0)),
    "random_forest": ("max_depth", (3, 6)),
    "hist_gb": ("max_iter", (100, 200)),
    "xgboost": ("max_depth", (2, 3)),
}
XGB_MAX_ROUNDS = 500
XGB_EARLY_STOPPING_ROUNDS = 30


@dataclass(frozen=True)
class ModelConfig:
    family: str
    param: str   # name of the one grid parameter
    value: float

    @property
    def name(self):
        return f"{self.family}:{self.param}={self.value:g}"


def frozen_configs(family=None):
    """All frozen configurations, in fixed order (family order, then ascending grid value); optionally one family."""
    families = FAMILIES if family is None else (family,)
    out = []
    for f in families:
        if f not in _GRIDS:
            raise ValueError(f"unknown model family {f!r}; expected one of {FAMILIES}")
        param, values = _GRIDS[f]
        out.extend(ModelConfig(f, param, v) for v in values)
    return out


def _check_config(config):
    if config.family not in _GRIDS:
        raise ValueError(f"unknown model family {config.family!r}")
    param, values = _GRIDS[config.family]
    if config.param != param or config.value not in values:
        raise ValueError(f"{config.name} is not a frozen configuration")


def make_model(config, n_rounds=None):
    """Unfitted estimator for a frozen configuration. n_rounds (XGBoost only) fixes the number of rounds and disables early
    stopping, for refitting with the round count found on validation."""
    _check_config(config)
    f, v = config.family, config.value
    if f != "xgboost" and n_rounds is not None:
        raise ValueError("n_rounds applies to xgboost only")
    if f == "logreg":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        return Pipeline([("scale", StandardScaler()),
                         ("clf", LogisticRegression(penalty="l2", C=v, solver="lbfgs", max_iter=1000, class_weight=None,
                                                    random_state=SEED))])
    if f == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(n_estimators=500, min_samples_leaf=30, max_depth=int(v), class_weight=None,
                                      n_jobs=1, random_state=SEED)
    if f == "hist_gb":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_depth=3, max_leaf_nodes=7, min_samples_leaf=50, learning_rate=0.05,
                                              l2_regularization=1.0, early_stopping=False, max_iter=int(v),
                                              class_weight=None, random_state=SEED)
    from xgboost import XGBClassifier
    kw = dict(tree_method="hist", learning_rate=0.05, subsample=1.0, max_depth=int(v), eval_metric="logloss", n_jobs=1,
              random_state=SEED)
    if n_rounds is None:
        return XGBClassifier(n_estimators=XGB_MAX_ROUNDS, early_stopping_rounds=XGB_EARLY_STOPPING_ROUNDS, **kw)
    return XGBClassifier(n_estimators=int(n_rounds), **kw)


def _matrix(X, name="X"):
    a = np.asarray(X, dtype=float)
    if a.ndim != 2:
        raise ValueError(f"{name} must be 2-dimensional")
    if not np.isfinite(a).all():
        raise ValueError(f"{name} contains NaN or infinite values (rows are excluded upstream, never imputed)")
    return a


def _target(y, n, name="y"):
    a = np.asarray(y)
    if a.ndim != 1 or len(a) != n:
        raise ValueError(f"{name} must be 1-dimensional with one value per row")
    if not np.isin(a, (0, 1)).all():
        raise ValueError(f"{name} must contain only 0 and 1")
    a = a.astype(int)
    if len(np.unique(a)) != 2:
        raise ValueError(f"{name} needs both classes")
    return a


@dataclass
class FittedModel:
    config: ModelConfig
    estimator: object
    n_features: int
    best_rounds: int = None   # xgboost: number of rounds kept (use as n_rounds when refitting without validation)


def fit(config, X, y, X_val=None, y_val=None, n_rounds=None):
    """Fit on the supplied training rows only. XGBoost needs X_val / y_val for early stopping (used for stopping, nothing else)
    unless n_rounds is given. The other families ignore validation data and reject it, so it cannot be used by accident."""
    X = _matrix(X)
    y = _target(y, len(X))
    est = make_model(config, n_rounds=n_rounds)
    best = None
    if config.family == "xgboost":
        if n_rounds is None:
            if X_val is None or y_val is None:
                raise ValueError("xgboost early stopping needs X_val and y_val")
            Xv = _matrix(X_val, "X_val")
            if Xv.shape[1] != X.shape[1]:
                raise ValueError("X_val has a different number of features than X")
            yv = _target(y_val, len(Xv), "y_val")
            est.fit(X, y, eval_set=[(Xv, yv)], verbose=False)
            best = int(est.best_iteration) + 1
        else:
            if X_val is not None or y_val is not None:
                raise ValueError("validation data is not used when n_rounds is given")
            est.fit(X, y, verbose=False)
            best = int(n_rounds)
    else:
        if X_val is not None or y_val is not None:
            raise ValueError(f"{config.family} does not use validation data during fitting")
        est.fit(X, y)
    return FittedModel(config, est, X.shape[1], best)


def predict_proba(model, X):
    """Native probability of class 1 for each row, shape (n,). No calibration."""
    X = _matrix(X)
    if X.shape[1] != model.n_features:
        raise ValueError(f"expected {model.n_features} features, got {X.shape[1]}")
    return np.asarray(model.estimator.predict_proba(X)[:, 1], dtype=float)
