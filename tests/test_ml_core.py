"""ml_core checks: the pooled DIT15 rows reproduce the frozen Experiment 1 dataset, and the features never read the entry day or later."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import features as F  # noqa: E402
from ml_core import dataset as D  # noqa: E402
from ml_core import strategies as ST  # noqa: E402

RUN = ROOT / "results" / "ml_core" / "exp2_6c6e182c"
LABELED = ROOT / "results" / "nogit-145d6302" / "phase_b" / "tier1" / "labeled.csv"
pytestmark = pytest.mark.skipif(not (RUN / "dataset.csv").exists(), reason="Experiment 2 dataset not built")


def test_dit15_rows_match_experiment_1_dataset():
    ds = pd.read_csv(RUN / "dataset.csv")
    mine = set(ds.loc[ds["strategy"] == "DIT15", "row_id"].str.replace("DIT15|", "", regex=False))
    frozen = set(pd.read_csv(LABELED)["row_id"])
    assert mine == frozen


def test_feature_columns_not_forbidden_and_present():
    from ml import registry as R
    R.assert_no_forbidden(D.FEATURE_COLUMNS)
    ds = pd.read_csv(RUN / "dataset.csv")
    assert set(D.FEATURE_COLUMNS) <= set(ds.columns)
    assert not ds[D.FEATURE_COLUMNS].isna().any().any()


@pytest.mark.parametrize("strategy", ["DIT15", "WIT", "MIT"])
def test_features_ignore_entry_day_and_later(strategy):
    """Truncating the daily frame and NIFTY at D-1 must not change any feature value."""
    raw = pd.read_csv(ST.SOURCES[strategy], parse_dates=["entry_time"])
    pool, _ = F.select_pool(raw)
    nifty = F.load_nifty()
    checked = 0
    for r in pool.head(60).to_dict("records"):
        td = D._td(r["ticker"], nifty)
        if td is None:
            continue
        full, why = D.agnostic_features(r, td)
        if why:
            continue
        t = pd.Timestamp(r["entry_time"])
        cut = int(np.searchsorted(td["dates"], np.datetime64(t.normalize()), side="left"))
        ncut = int(np.searchsorted(td["n_dates"], np.datetime64(t.normalize()), side="left"))
        short = dict(td, dates=td["dates"][:cut], close=td["close"][:cut], atr=td["atr"][:cut], n_dates=td["n_dates"][:ncut],
                     n_close=td["n_close"][:ncut])
        part, why2 = D.agnostic_features(r, short)
        assert why2 is None and part == full
        checked += 1
    assert checked >= 5


def test_holdout_rows_never_scored():
    oof = pd.read_csv(RUN / "oof_predictions.csv", parse_dates=["entry_time"])
    assert (oof["entry_time"] < pd.Timestamp("2026-01-01")).all()
    assert oof["entry_time"].min() >= pd.Timestamp("2023-01-01")
