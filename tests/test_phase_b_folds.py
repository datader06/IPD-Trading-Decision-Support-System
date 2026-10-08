"""Phase B walk-forward fold tests: chronology, embargo, purge, sibling handling, holdout isolation, minimum-sample rules,
determinism, and the leakage checks themselves (they must FAIL on corrupted folds). Synthetic data always runs; the real-data
tests use the labeled dataset and the generated fold files (skipped when missing).
Run: python -m pytest tests/test_phase_b_folds.py -q
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import splits as S  # noqa: E402

T = pd.Timestamp
LAB = ROOT / "results" / "nogit-145d6302" / "phase_b" / "labels" / "labeled.csv"
FOLDS = ROOT / "results" / "nogit-145d6302" / "phase_b" / "folds"
need_real = pytest.mark.skipif(not (LAB.exists() and (FOLDS / "folds.csv").exists()), reason="labeled dataset / folds missing")

CAL = pd.bdate_range("2020-06-01", "2026-12-31").to_numpy(dtype="datetime64[ns]")


def make_df(start="2021-01-04", end="2026-03-01", step=1, hold_hours=2, ambiguous_every=0):
    days = pd.bdate_range(start, end)[::step]
    rows = []
    for i, d in enumerate(days):
        status = "WIN" if i % 3 == 0 else "LOSS"
        if ambiguous_every and i % ambiguous_every == 1:
            status = "AMBIGUOUS"
        e = d + pd.Timedelta(hours=10)
        rows.append(dict(row_id=f"R{i:05d}", ticker=f"T{i % 7}", htf_key=f"({i},)", entry_time=e,
                         exit_time=e + pd.Timedelta(hours=hold_hours), label_status=status,
                         is_training_label=status in ("WIN", "LOSS"), label=1 if status == "WIN" else 0 if status == "LOSS" else None))
    return pd.DataFrame(rows)


def add_row(df, rid, entry, exit_, status="LOSS", ticker="TX", htf="(x,)"):
    r = dict(row_id=rid, ticker=ticker, htf_key=htf, entry_time=T(entry), exit_time=T(exit_), label_status=status,
             is_training_label=status in ("WIN", "LOSS"), label=1 if status == "WIN" else 0 if status == "LOSS" else None)
    return pd.concat([df, pd.DataFrame([r])], ignore_index=True)


def folds_of(df, cfg=S.CFG):
    f, d = S.build_folds(df, cfg, CAL)
    return {x.name: x for x in f}, d


def ids(d, f, role):
    return set(d["row_id"].to_numpy()[f.idx[role]])


# ------------------------------------------------------------------------------------------------ embargo / calendar
def test_embargo_start_counts_trading_days_not_calendar_days():
    assert S.embargo_start(CAL, "2023-07-01", 5) == T("2023-06-26")  # Sat boundary: Fri 30, Thu 29, Wed 28, Tue 27, Mon 26
    assert S.embargo_start(CAL, "2023-07-03", 5) == T("2023-06-26")  # boundary is a Monday: the 5 trading days before it
    holiday = np.array([d for d in CAL if d != np.datetime64("2023-06-28")], dtype="datetime64[ns]")  # a market holiday
    assert S.embargo_start(holiday, "2023-07-01", 5) == T("2023-06-23")
    with pytest.raises(ValueError):
        S.embargo_start(CAL[:3], "2020-06-03", 5)


def test_embargo_drops_exactly_the_rows_entered_in_the_five_trading_days_before_the_test():
    f, d = folds_of(make_df())
    k = f["2024H1"]
    assert k.test_embargo_start == T("2023-12-25")  # Mon 25 .. Fri 29 Dec: the 5 trading days before Mon 2024-01-01
    emb = d.set_index("row_id").loc[sorted(ids(d, k, "embargo"))]
    assert emb.entry_time.min() >= k.test_embargo_start and emb.entry_time.max() < k.test_start
    assert len(emb) == 5  # synthetic calendar: one resolved row per business day, 5 business days
    pool_entries = d.iloc[k.idx["pool"]].entry_time
    assert pool_entries.max() < k.test_embargo_start
    assert not ((pool_entries >= k.test_embargo_start) & (pool_entries < k.test_start)).any()


# ------------------------------------------------------------------------------------------------ purge
def test_purge_removes_trades_whose_outcome_reaches_the_test_start():
    df = make_df(end="2025-12-31")
    df = add_row(df, "LONG", "2022-12-01 10:00", "2023-01-03 10:00")  # entered long before the embargo, outcome after test start
    df = add_row(df, "SAFE", "2022-12-01 11:00", "2022-12-30 15:00")  # outcome ends before the test start
    df = add_row(df, "EDGE", "2022-12-01 12:00", "2023-01-01 00:00")  # outcome exactly at the test start: purged
    f, d = folds_of(df)
    k = f["2023H1"]
    assert {"LONG", "EDGE"} <= ids(d, k, "purged") and "SAFE" not in ids(d, k, "purged")
    assert "SAFE" in set(d.row_id.to_numpy()[k.idx["pool"]]) and not ({"LONG", "EDGE"} & set(d.row_id.to_numpy()[k.idx["pool"]]))
    assert d.iloc[k.idx["pool"]].exit_time.max() < k.test_start
    assert all(r[0] for r in S.check_folds(list(f.values()), d, S.CFG, CAL).values())


def test_purge_at_the_validation_boundary():
    df = add_row(make_df(end="2025-12-31"), "VX", "2022-06-01 10:00", "2022-07-05 10:00")  # reaches the 2023H1 validation start
    f, d = folds_of(df)
    k = f["2023H1"]
    assert "VX" in ids(d, k, "val_purged") and "VX" not in set(d.row_id.to_numpy()[k.idx["fit"]])
    assert "VX" in set(d.row_id.to_numpy()[k.idx["pool"]])  # still valid for the final refit: its outcome ends before the test start


# ------------------------------------------------------------------------------------------------ roles / ordering
def test_roles_are_chronological_and_disjoint():
    f, d = folds_of(make_df())
    names = list(f)
    assert names == ["2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2"]
    for a, b in zip(list(f.values()), list(f.values())[1:]):
        assert a.test_end == b.test_start
    for k in f.values():
        fit, val, test = ids(d, k, "fit"), ids(d, k, "validation"), ids(d, k, "test")
        assert not fit & val and not (fit | val) & test
        assert d.iloc[k.idx["fit"]].exit_time.max() < k.val_start <= d.iloc[k.idx["validation"]].entry_time.min()
        assert d.iloc[k.idx["validation"]].entry_time.max() < k.test_embargo_start
        assert d.iloc[k.idx["test"]].entry_time.min() >= k.test_start
    assert all(r[0] for r in S.check_folds(list(f.values()), d, S.CFG, CAL).values())


def test_unresolved_rows_are_never_fitted_but_stay_in_test_windows():
    f, d = folds_of(make_df(ambiguous_every=5))
    for k in f.values():
        tr = d.iloc[k.idx["pool"]]
        assert set(tr.label_status) <= {"WIN", "LOSS"} and tr.is_training_label.all()
        te = d.iloc[k.idx["test"]]
        assert (te.label_status == "AMBIGUOUS").any()  # kept for later evaluation, counted separately
        assert len(k.idx["unresolved_excluded"]) > 0
    tab = S.fold_table(list(f.values()), d, S.CFG)
    assert (tab.test_rows > tab.test_resolved).all() and (tab.test_ambiguous > 0).all()


def test_holdout_2026_is_never_used():
    f, d = folds_of(make_df(end="2026-06-30"))
    hold = set(np.flatnonzero((d.entry_time >= S.CFG.holdout_start).to_numpy()))
    assert len(hold) > 50
    for k in f.values():
        for role in S.ROLES + ("pool",):
            assert not set(k.idx[role]) & hold
        assert k.test_end <= S.CFG.holdout_start
    asg = S.assignments(list(f.values()), d)
    assert pd.to_datetime(asg.entry_time).max() < S.CFG.holdout_start
    with pytest.raises(ValueError):  # a window reaching into 2026 is rejected
        S.build_folds(make_df(), replace(S.CFG, windows=(("bad", "2025-07-01", "2026-02-01"),)), CAL)


def test_dev_trade_exiting_in_2026_is_reported_not_hidden():
    df = add_row(make_df(end="2025-12-20"), "XYR", "2025-12-30 10:00", "2026-01-05 10:00")
    f, d = folds_of(df)
    k = f["2025H2"]
    assert "XYR" in ids(d, k, "test")  # holdout membership is by entry_time
    tab = S.fold_table(list(f.values()), d, S.CFG)
    assert int(tab.set_index("fold").loc["2025H2", "test_rows_exiting_in_holdout"]) == 1


def test_siblings_of_one_htf_zone_stay_on_one_side():
    df = make_df(end="2025-12-31")
    df = add_row(df, "S1", "2022-11-01 10:00", "2022-11-01 12:00", ticker="ZZ", htf="(sib,)")  # group starts in training
    df = add_row(df, "S2", "2023-02-01 10:00", "2023-02-01 12:00", ticker="ZZ", htf="(sib,)")  # later member inside the test window
    df = add_row(df, "N1", "2023-02-02 10:00", "2023-02-02 12:00", ticker="ZZ", htf="(new,)")  # whole group inside the test window
    f, d = folds_of(df)
    k = f["2023H1"]
    assert "S2" in ids(d, k, "sibling_removed") and "S2" not in ids(d, k, "test")
    assert "N1" in ids(d, k, "test")
    assert "S1" in set(d.row_id.to_numpy()[k.idx["pool"]])
    assert all(r[0] for r in S.check_folds(list(f.values()), d, S.CFG, CAL).values())


def test_minimum_sample_rules_flag_small_folds():
    need = S.CFG.min_wins_per_feature * S.CFG.n_features
    assert need == 180 and S.CFG.min_train_resolved == 300 and S.CFG.min_test_resolved == 100
    f, d = folds_of(make_df(step=40))  # about one resolved row per 8 weeks: far below every minimum
    tab = S.fold_table(list(f.values()), d, S.CFG)
    assert not tab.pool_ok_resolved.any() and not tab.pool_ok_wins.any() and not tab.test_ok_resolved.any()
    f, d = folds_of(make_df())  # one row per business day: flags must equal the thresholds exactly
    tab = S.fold_table(list(f.values()), d, S.CFG)
    assert tab.pool_ok_wins.tolist() == (tab.pool_wins >= need).tolist()
    assert tab.pool_ok_resolved.tolist() == ((tab.pool_wins + tab.pool_losses) >= 300).tolist()
    assert tab.test_ok_resolved.tolist() == (tab.test_resolved >= 100).tolist()
    assert (not tab.pool_ok_wins.iloc[0]) and tab.pool_ok_wins.iloc[-1]  # the first, smallest window fails the wins rule here


def test_construction_is_deterministic_and_independent_of_row_order():
    df = make_df(ambiguous_every=7)
    f1, d1 = folds_of(df)
    f2, d2 = folds_of(df.sample(frac=1.0, random_state=3).reset_index(drop=True))
    t1, t2 = S.fold_table(list(f1.values()), d1, S.CFG), S.fold_table(list(f2.values()), d2, S.CFG)
    assert t1.equals(t2)
    key = lambda a: a.sort_values(["fold", "role", "row_id"]).reset_index(drop=True)  # noqa: E731
    assert key(S.assignments(list(f1.values()), d1)).equals(key(S.assignments(list(f2.values()), d2)))


# ------------------------------------------------------------------------------------------------ the checks must catch leaks
def _failed(f, d):
    return {k for k, v in S.check_folds(list(f.values()), d, S.CFG, CAL).items() if not v[0]}


def test_checks_catch_a_test_row_in_training():
    f, d = folds_of(make_df())
    k = f["2024H1"]
    k.idx["pool"] = np.append(k.idx["pool"], k.idx["test"][0])
    bad = _failed(f, d)
    assert any("no_test_information" in n or "roles_disjoint" in n or "purge_respected" in n for n in bad)


def test_checks_catch_an_embargo_violation():
    f, d = folds_of(make_df())
    k = f["2024H1"]
    k.idx["pool"] = np.append(k.idx["pool"], k.idx["embargo"][0])  # an embargoed row sneaks back in
    assert any("embargo_respected" in n or "no_test_information" in n for n in _failed(f, d))


def test_checks_catch_a_purge_violation():
    df = add_row(make_df(end="2025-12-31"), "LONG", "2022-12-01 10:00", "2023-01-03 10:00")
    f, d = folds_of(df)
    k = f["2023H1"]
    k.idx["pool"] = np.append(k.idx["pool"], k.idx["purged"][0])
    assert any("purge_respected" in n for n in _failed(f, d))


def test_checks_catch_a_holdout_row_in_a_fold():
    f, d = folds_of(make_df(end="2026-06-30"))
    hold = int(np.flatnonzero((d.entry_time >= S.CFG.holdout_start).to_numpy())[0])
    f["2025H2"].idx["fit"] = np.append(f["2025H2"].idx["fit"], hold)
    assert any("holdout" in n for n in _failed(f, d))


def test_checks_catch_an_unresolved_row_in_training():
    f, d = folds_of(make_df(ambiguous_every=5))
    k = f["2024H1"]
    k.idx["fit"] = np.append(k.idx["fit"], k.idx["unresolved_excluded"][0])
    assert any("only_resolved_rows_are_fitted" in n for n in _failed(f, d))


# ------------------------------------------------------------------------------------------------ real dataset
@need_real
def test_real_dataset_timestamps_obey_every_rule():
    df = pd.read_csv(LAB, usecols=["row_id", "ticker", "htf_key", "entry_time", "exit_time", "label_status", "is_training_label",
                                   "label", "is_b0"], parse_dates=["entry_time", "exit_time"])
    td = S.default_trading_days()
    f, d = S.build_folds(df, S.CFG, td)
    checks = S.check_folds(f, d, S.CFG, td)
    assert len(checks) >= 80 and all(v[0] for v in checks.values()), {k: v for k, v in checks.items() if not v[0]}
    for k in f:
        pool = d.iloc[k.idx["pool"]]
        assert pool.entry_time.max() < k.test_embargo_start and pool.exit_time.max() < k.test_start
        assert set(pool.label_status) <= {"WIN", "LOSS"}
        assert d.iloc[k.idx["test"]].entry_time.between(k.test_start, k.test_end, inclusive="left").all()
        assert k.test_end <= S.CFG.holdout_start
    hold = d[d.entry_time >= S.CFG.holdout_start]
    used = set().union(*[set(k.idx[r]) for k in f for r in S.ROLES + ("pool",)])
    assert len(hold) == 781 and not (set(hold.index) & used)
    tab = S.fold_table(f, d, S.CFG)
    assert tab[["pool_ok_resolved", "pool_ok_wins", "fit_ok_resolved", "fit_ok_wins", "test_ok_resolved"]].all().all()
    assert (tab.test_resolved >= 100).all() and (tab.pool_n >= 300).all() and (tab.pool_wins >= 180).all()


@need_real
def test_fold_files_match_a_fresh_construction():
    df = pd.read_csv(LAB, usecols=["row_id", "ticker", "htf_key", "entry_time", "exit_time", "label_status", "is_training_label",
                                   "label", "is_b0"], parse_dates=["entry_time", "exit_time"])
    td = S.default_trading_days()
    f, d = S.build_folds(df, S.CFG, td)
    tab = S.fold_table(f, d, S.CFG)
    saved = pd.read_csv(FOLDS / "folds.csv")
    for col in ("fold", "fit_n", "val_n", "pool_n", "test_rows", "test_resolved", "test_wins", "test_losses", "embargo_n",
                "purged_n", "val_embargo_n", "val_purged_n", "sibling_removed_n"):
        assert saved[col].tolist() == tab[col].tolist(), col
    asg = pd.read_csv(FOLDS / "fold_assignments.csv", parse_dates=["entry_time"])
    assert asg.entry_time.max() < S.CFG.holdout_start
    fresh = S.assignments(f, d)
    key = lambda a: a.sort_values(["fold", "role", "row_id"]).reset_index(drop=True)[["fold", "row_id", "role"]]  # noqa: E731
    assert key(asg).equals(key(fresh))
    m = json.load(open(FOLDS / "manifest.json"))
    assert m["checks_failed"] == [] and m["deterministic"] is True and m["holdout_rows"] == 781
    assert m["config"]["embargo_days"] == 5 and m["config"]["val_months"] == 6
