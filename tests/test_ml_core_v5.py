"""Experiment 3 (baselines v5) checks: no leakage across the year boundary, holdout untouched, deterministic, features exclude outcomes."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml_core import adapters as A  # noqa: E402
from ml_core import walkforward as W  # noqa: E402

RUN = ROOT / "results" / "ml_core" / "exp3_v5_f381ac0a"
pytestmark = pytest.mark.skipif(not (RUN / "dataset.csv").exists(), reason="Experiment 3 not run")


@pytest.fixture(scope="module")
def dev():
    d = pd.read_csv(RUN / "dataset.csv", parse_dates=["entry_time", "exit_time"])
    return d[d["split"] != "holdout"].reset_index(drop=True)


def test_features_exclude_outcomes_and_ids():
    bad = {"label", "r_gross", "exit_time", "label_win", "label_R", "label_outcome", "split", "row_id", "ticker", "strategy", "entry_time"}
    assert not (set(A.FEATURE_COLUMNS) & bad)


def test_dataset_matches_source_labels():
    raw = pd.read_csv(A.DEFAULT_PATH)
    ds = pd.read_csv(RUN / "dataset.csv")
    assert len(ds) == len(raw) - 1  # one row has no daily history (documented exclusion)
    assert set(ds["split"]) == {"train", "holdout"}


def test_training_rows_never_reach_the_test_year(dev):
    for y in (2023, 2024, 2025):
        ts = pd.Timestamp(f"{y}-01-01")
        tr = W.train_mask(dev, ts)
        assert (dev.loc[tr, "exit_time"] < ts).all()
        assert (dev.loc[tr, "entry_time"] < ts - pd.Timedelta(days=W.EMBARGO_DAYS)).all()


def test_holdout_never_scored():
    oof = pd.read_csv(RUN / "oof_predictions.csv", parse_dates=["entry_time"])
    assert (oof["entry_time"] < pd.Timestamp("2026-01-01")).all() and (oof["split"] == "train").all()


def test_walk_forward_is_deterministic(dev):
    a = W.walk_forward(dev, A.FEATURE_COLUMNS, (2024,), families=("logreg", "random_forest"))
    b = W.walk_forward(dev, A.FEATURE_COLUMNS, (2024,), families=("logreg", "random_forest"))
    assert np.allclose(a["p_logreg"], b["p_logreg"]) and np.allclose(a["p_random_forest"], b["p_random_forest"])


def test_topk_selection_sizes(dev):
    oof = W.walk_forward(dev, A.FEATURE_COLUMNS, (2024, 2025), families=("logreg",))
    take = W.select_topk(oof, "p_logreg", 0.5)
    exp = sum(int(np.ceil(0.5 * n)) for n in oof.groupby("test_year").size())
    assert take.sum() == exp


def test_registry_builds_every_model_and_rejects_unknown():
    from ml_core import model_registry as MR
    for name in MR.MODELS:
        m = MR.build(name)
        assert hasattr(m, "fit") and hasattr(m, "predict_proba")
    with pytest.raises(ValueError):
        MR.build("nope")
    assert MR.resolve("all") == tuple(MR.MODELS) and MR.resolve("default") == MR.DEFAULT


def test_first_four_zoo_models_reproduce_experiment_3():
    zoo = sorted((ROOT / "results" / "ml_core").glob("exp4_zoo_*"))
    if not zoo:
        pytest.skip("Experiment 4 not run")
    a = pd.read_csv(RUN / "verdict.csv").set_index("family")
    b = pd.read_csv(zoo[-1] / "verdict.csv").set_index("family")
    for fam in a.index:
        assert abs(a.loc[fam, "lift_pts"] - b.loc[fam, "lift_pts"]) < 1e-9 and abs(a.loc[fam, "auc"] - b.loc[fam, "auc"]) < 1e-9


def test_v6_rule_reproduces_final_baseline_trades():
    final = ROOT / "data" / "algo_v6" / "v6_trades_min_strength_2_only_DIT15.csv"
    if not final.exists():
        pytest.skip("v6 trade list not present")
    ex = pd.read_csv(A.DEFAULT_PATH, parse_dates=["entry_time"])
    rule = ex[(ex["combo"] != "DIT15") | (ex["legout_strength_score"] == 2)]
    v6 = pd.read_csv(final, parse_dates=["entry_time"])
    assert len(rule) == len(v6) == 205
    m = rule.merge(v6, on=["combo", "ticker", "entry_time"], how="outer", indicator=True)
    assert (m["_merge"] == "both").all()
    assert int(rule["label_win"].sum()) == 91  # STATUS section 19: 91 wins of 205
