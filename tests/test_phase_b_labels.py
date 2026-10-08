"""Phase B label tests: target-before-stop, stop-before-target, same-bar ambiguity, censoring/open/nofill, row retention,
Phase A traceability and the generated labeled dataset.
Synthetic tests always run; real-data tests need the Tier-1 dataset, the labeled dataset and the Phase A source (skip otherwise).
Run: python -m pytest tests/test_phase_b_labels.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import bars as B  # noqa: E402
import replay as RP  # noqa: E402
from ml import features as F  # noqa: E402
from ml import labels as L  # noqa: E402
from ml import registry as R  # noqa: E402

T = pd.Timestamp
SRC = ROOT / "results" / "nogit-145d6302" / "phase_a" / "pit_refetch" / "candidates.csv"
FEAT = ROOT / "results" / "nogit-145d6302" / "phase_b" / "tier1" / "features.csv"
LAB = ROOT / "results" / "nogit-145d6302" / "phase_b" / "labels"
need_real = pytest.mark.skipif(not (SRC.exists() and FEAT.exists() and (LAB / "labeled.csv").exists()),
                               reason="Phase A source / Tier-1 / labeled dataset missing")


# ------------------------------------------------------------------------------------------------ synthetic helpers
def ctx_from(rows, minute=None):
    m15 = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    m15["timestamp"] = pd.to_datetime(m15["timestamp"])
    m15 = B.add_close_time(m15, "15m")
    g = m15.groupby(m15["timestamp"].dt.normalize())  # daily high/low consistent with the 15m bars (no phantom intraday gap)
    d1 = pd.DataFrame(dict(timestamp=list(g.groups), high=g["high"].max().to_numpy(), low=g["low"].min().to_numpy()))
    return L.ReplayContext("SYN", d1, m15, minute_factory=(lambda: minute) if minute is not None else None)


def cand(kind="demand", entry=100.0, stop=98.0, target=104.0, scan="2025-01-01 09:15"):
    return dict(type=kind, entry_price=entry, stop=stop, target=target, risk=abs(entry - stop), entry_time=T(scan))


def label_of(rows, row=None, minute=None):
    ctx = ctx_from(rows, minute)
    res = L.replay_row(row or cand(), ctx)
    return res, L.label_from_outcome(res["outcome"])


class FakeMinutes:
    def __init__(self, rows):
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
        self.ts = pd.to_datetime(df.timestamp).to_numpy(dtype="datetime64[ns]")
        self.o, self.h, self.l, self.c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))

    bars = RP.MinuteCache.bars


FILL = ("2025-01-01 09:15", 101, 101, 100, 100.5)  # trades into the entry (100) without touching stop or target


# ------------------------------------------------------------------------------------------------ mapping
def test_label_mapping():
    assert L.label_from_outcome("WIN") == (1, "WIN", True)
    assert L.label_from_outcome("LOSS") == (0, "LOSS", True)
    for s in ("AMBIGUOUS", "CENSORED", "OPEN", "NOFILL"):
        assert L.label_from_outcome(s) == (None, s, False)
    with pytest.raises(ValueError):
        L.label_from_outcome("win")
    assert set(L.STATUSES) == {"WIN", "LOSS", "AMBIGUOUS", "CENSORED", "OPEN", "NOFILL"}


def test_replay_helpers_come_from_the_common_module():
    import replay_context as RC  # src/replay_context.py: shared with Phase A, which must not import src/ml
    assert L.ReplayContext is RC.ReplayContext and L.replay_row is RC.replay_row and L.check_row is RC.check_row


def test_label_columns_are_never_model_inputs():
    assert not set(L.LABEL_COLUMNS) & set(R.MODEL_COLUMNS)
    with pytest.raises(ValueError):
        R.assert_no_forbidden(R.MODEL_COLUMNS + ["label"])
    for c in L.LABEL_COLUMNS:
        assert c in R.FORBIDDEN


# ------------------------------------------------------------------------------------------------ replay scenarios
@pytest.mark.parametrize("kind,rows,tag", [
    ("demand", [FILL, ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104)], "target before stop"),
    ("supply", [("2025-01-01 09:15", 99, 100, 99, 99.5), ("2025-01-01 09:30", 99.5, 99.8, 95.5, 96)], "supply target"),
])
def test_target_before_stop_is_label_1(kind, rows, tag):
    row = cand(kind, entry=100.0, stop=98.0 if kind == "demand" else 102.0, target=104.0 if kind == "demand" else 96.0)
    res, (lab, status, train) = label_of(rows, row)
    assert (res["outcome"], lab, status, train) == ("WIN", 1, "WIN", True)
    assert res["r"] == pytest.approx(2.0)


@pytest.mark.parametrize("kind", ["demand", "supply"])
def test_stop_before_target_is_label_0(kind):
    if kind == "demand":
        rows, row = [FILL, ("2025-01-01 09:30", 100.5, 100.6, 97.5, 98)], cand()
    else:
        rows, row = [("2025-01-01 09:15", 99, 100, 99, 99.5), ("2025-01-01 09:30", 99.5, 102.5, 99.4, 102)], \
            cand("supply", 100.0, 102.0, 96.0)
    res, (lab, status, train) = label_of(rows, row)
    assert (res["outcome"], lab, status, train) == ("LOSS", 0, "LOSS", True)
    assert res["r"] == pytest.approx(-1.0)


def test_gap_through_stop_is_still_label_0_with_r_below_minus_1():
    rows = [FILL, ("2025-01-02 09:15", 96, 97, 95, 96)]
    res, (lab, _, _) = label_of(rows)
    assert lab == 0 and res["r"] == pytest.approx(-2.0)


def test_same_bar_stop_and_target_is_ambiguous_with_no_label():
    rows = [FILL, ("2025-01-01 09:30", 100.5, 105, 97, 100)]
    res, (lab, status, train) = label_of(rows)  # no minute data cached
    assert (res["outcome"], lab, status, train) == ("AMBIGUOUS", None, "AMBIGUOUS", False)
    assert res["reason"].startswith("MINUTE_NOT_CACHED")
    # minute data settles it: target first -> WIN -> label 1; a true tie inside one minute stays AMBIGUOUS
    won = FakeMinutes([("2025-01-01 09:30", 100.5, 105, 100.4, 104.8), ("2025-01-01 09:31", 104.8, 104.9, 97, 100)])
    res2, (lab2, status2, _) = label_of(rows, minute=won)
    assert (res2["outcome"], lab2, status2) == ("WIN", 1, "WIN") and res2["decided_interval"] == "1minute"
    tie = FakeMinutes([("2025-01-01 09:30", 100.5, 105, 97, 100)])
    res3, (lab3, status3, train3) = label_of(rows, minute=tie)
    assert (res3["outcome"], lab3, status3, train3) == ("AMBIGUOUS", None, "AMBIGUOUS", False)


def test_target_in_fill_bar_and_gap_fill_beyond_stop_are_ambiguous():
    res, (lab, status, _) = label_of([("2025-01-01 09:15", 103, 105, 99.5, 104)])  # may have been reached before the fill
    assert (lab, status) == (None, "AMBIGUOUS") and "target in fill bar" in res["reason"]
    res, (lab, status, _) = label_of([("2025-01-01 09:15", 97, 99, 96, 98)])        # opens through the stop
    assert (lab, status) == (None, "AMBIGUOUS") and res["reason"] == "gap-fill opens beyond the stop"


def test_censored_open_nofill_have_no_label():
    flat = [(f"2025-01-{d:02d} 09:15", 101, 101.5, 100.5, 101) for d in range(2, 10)]
    filled = [("2024-12-31 09:15", 101, 101, 99.9, 100.5)] + flat
    row = cand(scan="2024-12-31 09:15")
    res, (lab, status, train) = label_of(filled, row)  # data ends long before the 90-day horizon
    assert (res["outcome"], lab, status, train) == ("CENSORED", None, "CENSORED", False) and res["mtm_r"] is not None
    res, (lab, status, train) = label_of(filled + [("2025-06-01 09:15", 101, 101, 101, 101)], row)
    assert (res["outcome"], lab, status, train) == ("OPEN", None, "OPEN", False)
    res, (lab, status, train) = label_of(flat + [("2025-06-01 09:15", 101, 101, 101, 101)], cand(scan="2025-01-02 09:15"))
    assert (res["outcome"], lab, status, train) == ("NOFILL", None, "NOFILL", False)
    res, (lab, status, _) = label_of(flat, cand(scan="2025-01-02 09:15"))  # never filled, horizon incomplete
    assert (res["outcome"], lab, status) == ("CENSORED", None, "CENSORED")


def test_replay_is_deterministic():
    rows = [FILL, ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104)]
    assert label_of(rows)[0] == label_of(rows)[0]


# ------------------------------------------------------------------------------------------------ row handling / check
def _stored(res, row):
    return dict(row, outcome=res["outcome"], exit_reason=res["reason"], decided_interval=res["decided_interval"],
                fill_time=res["fill_time"], fill_price=res["fill_price"], exit_time=res["exit_time"],
                exit_price=res["exit_price"], r_gross=res["r"], mtm_r=res["mtm_r"])


def test_label_rows_keeps_every_row_and_preserves_phase_a_fields():
    ctx = ctx_from([FILL, ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104), ("2025-01-02 09:15", 101, 101, 100, 100.5),
                    ("2025-01-02 09:30", 100.5, 100.6, 97.5, 98), ("2025-01-03 09:15", 101, 101, 100, 100.5),
                    ("2025-01-03 09:30", 100.5, 105, 97, 100)])
    rows = []
    for scan in ("2025-01-01 09:15", "2025-01-02 09:15", "2025-01-03 09:15"):
        c = cand(scan=scan)
        rows.append(_stored(L.replay_row(c, ctx), c))
    out = L.label_rows(rows, ctx, src_row_of=lambda r: 7)
    assert [o["label_status"] for o in out] == ["WIN", "LOSS", "AMBIGUOUS"]
    assert [o["label"] for o in out] == [1, 0, None] and [o["is_training_label"] for o in out] == [True, True, False]
    assert all(o["replay_check"] == "match" and o["phase_a_src_row"] == 7 for o in out)
    for o, r in zip(out, rows):  # nothing about the Phase A outcome changed
        assert o["outcome"] == r["outcome"] and o["exit_reason"] == r["exit_reason"] and o["r_gross"] == r["r_gross"] \
            or (pd.isna(o["r_gross"]) and pd.isna(r["r_gross"]))


def test_check_row_flags_a_changed_outcome_or_reason():
    ctx = ctx_from([FILL, ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104)])
    c = cand()
    stored = _stored(L.replay_row(c, ctx), c)
    assert L.check_row(stored, L.replay_row(c, ctx)) == "match"
    assert L.check_row(dict(stored, outcome="LOSS"), L.replay_row(c, ctx)).startswith("mismatch:outcome")
    assert "r" in L.check_row(dict(stored, r_gross=1.0), L.replay_row(c, ctx))


# ------------------------------------------------------------------------------------------------ real data
@need_real
def test_labeled_dataset_integrity_and_phase_a_comparison():
    feats = pd.read_csv(FEAT, float_precision="round_trip")
    lab = pd.read_csv(LAB / "labeled.csv", parse_dates=["entry_time", "fill_time", "exit_time"], float_precision="round_trip")
    src = pd.read_csv(SRC, parse_dates=["entry_time", "fill_time", "exit_time"])
    m = json.load(open(LAB / "manifest.json"))
    assert len(lab) == len(feats) == m["rows"] and lab["row_id"].is_unique  # every candidate kept
    assert set(lab["row_id"]) == set(feats["row_id"])
    for c in R.MODEL_COLUMNS:  # feature values untouched
        assert np.array_equal(lab[c].to_numpy(), feats[c].to_numpy())
    assert list(lab.columns) == list(feats.columns) + L.LABEL_COLUMNS
    # label only for resolved WIN / LOSS
    assert (lab.loc[lab.outcome == "WIN", "label"] == 1).all() and (lab.loc[lab.outcome == "LOSS", "label"] == 0).all()
    assert lab.loc[~lab.outcome.isin(["WIN", "LOSS"]), "label"].isna().all()
    assert (lab["label_status"] == lab["outcome"]).all()
    assert (lab["is_training_label"] == lab["outcome"].isin(["WIN", "LOSS"])).all()
    # every label traces back to the Phase A row with the same identity and outcome
    s = src.iloc[lab["phase_a_src_row"]].reset_index(drop=True)
    assert [F.row_id(r) for r in s.to_dict("records")] == lab["row_id"].tolist()
    assert (s["outcome"].to_numpy() == lab["outcome"].to_numpy()).all()
    assert (s["htf_key"].to_numpy() == lab["htf_key"].to_numpy()).all()
    # counts reconcile with Phase A: pool outcomes - rows excluded at the feature stage = dataset outcomes
    pool, _ = F.select_pool(src)
    kept = set(lab["row_id"])
    dropped = pool[~pool.apply(F.row_id, axis=1).isin(kept)]
    for k in L.STATUSES:
        assert (pool.outcome == k).sum() - (dropped.outcome == k).sum() == (lab.label_status == k).sum()
    assert m["status_counts"] == {k: int((lab.label_status == k).sum()) for k in L.STATUSES}
    assert set(lab.replay_check) == {"match"}  # fresh replay with the unchanged replay code equals the stored Phase A fields


@need_real
def test_labels_reproduce_from_features_for_sample_tickers():
    feats = pd.read_csv(FEAT, parse_dates=["entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at", "fill_time", "exit_time"])
    lab = pd.read_csv(LAB / "labeled.csv").set_index("row_id")
    for tk in ("ADANIPORTS.NS", "RVNL.NS"):
        d1, m15 = B.load_frame(F.FRAMES, tk, "1d"), B.load_frame(F.FRAMES, tk, "15m")
        ctx = L.ReplayContext(tk, d1, m15)
        out = L.label_rows(feats[feats.ticker == tk].to_dict("records"), ctx)
        assert len(out) >= 3
        for o in out:
            w = lab.loc[o["row_id"]]
            assert o["label_status"] == w["label_status"] and o["replay_check"] == "match"
            assert (pd.isna(o["label"]) and pd.isna(w["label"])) or o["label"] == w["label"]
