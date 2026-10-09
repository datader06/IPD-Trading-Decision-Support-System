"""Pluggable model registry for the walk-forward layer. To add a model, add one entry to MODELS (a zero-argument factory returning an
estimator with fit / predict_proba). Hyperparameters are fixed here, never tuned on results. Seed 42 everywhere."""
SEED = 42


def _scaled(est):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), est)


def _logreg():
    from sklearn.linear_model import LogisticRegression
    return _scaled(LogisticRegression(C=0.3, penalty="l2", max_iter=2000, random_state=SEED))


def _random_forest():
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=10, random_state=SEED, n_jobs=1)


def _hist_gb():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_depth=2, max_iter=60, learning_rate=0.05, l2_regularization=1.0, early_stopping=False,
                                          random_state=SEED)


def _xgboost():
    from xgboost import XGBClassifier
    return XGBClassifier(tree_method="hist", max_depth=2, n_estimators=120, learning_rate=0.05, subsample=1.0, random_state=SEED,
                         n_jobs=1, eval_metric="logloss", verbosity=0)


def _extra_trees():
    from sklearn.ensemble import ExtraTreesClassifier
    return ExtraTreesClassifier(n_estimators=300, max_depth=3, min_samples_leaf=10, random_state=SEED, n_jobs=1)


def _adaboost():
    from sklearn.ensemble import AdaBoostClassifier
    from sklearn.tree import DecisionTreeClassifier
    return AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=1), n_estimators=100, learning_rate=0.5, random_state=SEED)


def _knn():
    from sklearn.neighbors import KNeighborsClassifier
    return _scaled(KNeighborsClassifier(n_neighbors=25, weights="distance"))


def _naive_bayes():
    from sklearn.naive_bayes import GaussianNB
    return _scaled(GaussianNB())


MODELS = {"logreg": _logreg, "random_forest": _random_forest, "hist_gb": _hist_gb, "xgboost": _xgboost,
          "extra_trees": _extra_trees, "adaboost": _adaboost, "knn": _knn, "naive_bayes": _naive_bayes}
DEFAULT = ("logreg", "random_forest", "hist_gb", "xgboost")  # the Experiment 3 set


def build(name):
    if name not in MODELS:
        raise ValueError(f"unknown model {name!r}; registered: {sorted(MODELS)}")
    return MODELS[name]()


def resolve(spec):
    """'all' | 'default' | comma-separated names -> tuple of registered names."""
    if spec in (None, "", "default"):
        return DEFAULT
    return tuple(MODELS) if spec == "all" else tuple(s.strip() for s in spec.split(","))
