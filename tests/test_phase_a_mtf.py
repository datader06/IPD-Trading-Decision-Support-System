"""WIT / MIT hardening tests: period bars with close times, point-in-time trend for the daily (WIT) and weekly (MIT) trend frames,
decision times, replay start rules, legacy-mode reproduction of the stored results, append-stability, truncation, determinism.
Synthetic tests always run; real-data tests need the frozen frames and the stored 2021+ results (skipped otherwise).
Run: python -m pytest tests/test_phase_a_mtf.py -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import bars as B  # noqa: E402
import candidates_mtf as M  # noqa: E402
import htf_bars as HB  # noqa: E402
from trend_pit import TrendContext  # noqa: E402

T = pd.Timestamp
OLD = {"wit": ROOT / "results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv",
       "mit": ROOT / "results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv"}
need_real = pytest.mark.skipif(not (M.FRAMES.exists() and OLD["wit"].exists() and OLD["mit"].exists()), reason="frames / stored results missing")


def daily(dates, base=100.0):
    df = pd.DataFrame(dict(timestamp=pd.to_datetime(dates), open=base, high=base + 1, low=base - 1, close=base))
    return B.add_close_time(df, "1d")


def zone(kind, base_start, leg_end, distal):
    return SimpleNamespace(type=kind, base_start_index=base_start, leg_end_index=leg_end, distal_line=distal)


# ------------------------------------------------------------------------------------------------ weekly / monthly bars
def test_weekly_close_time_is_last_trading_day_not_the_sunday_label():
    d = daily(["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-13", "2025-01-14", "2025-01-15", "2025-01-16", "2025-01-17"])
    w = HB.period_frame(d, "W")
    assert list(w.timestamp.dt.strftime("%Y-%m-%d")) == ["2025-01-12", "2025-01-19"]  # Sunday labels (legacy grouping)
    assert w.close_time[0] == T("2025-01-09 15:30")                                     # Friday was a holiday: closes Thursday
    assert w.close_time[1] == T("2025-01-17 15:30")                                     # complete week: data ends Friday
    assert (w.close_time < w.timestamp + pd.Timedelta(days=1)).all()


def test_monthly_close_time_and_month_end_label_before_the_close():
    d = daily(pd.bdate_range("2024-01-01", "2024-03-29"))  # 2024-01-31 (Wed) and 2024-02-29 (Thu) are trading days
    m = HB.period_frame(d, "ME")
    assert list(m.timestamp.dt.strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-31"]
    assert m.close_time[0] == T("2024-01-31 15:30") and m.timestamp[0] == T("2024-01-31 00:00")  # label midnight is BEFORE the close
    assert m.close_time[2] == T("2024-03-29 15:30")  # month ends on a Sunday: last trading day Friday 29, data ends there -> complete


def test_incomplete_final_period_is_never_closed():
    d = daily(pd.bdate_range("2024-01-01", "2024-02-14"))  # data ends mid-February, mid-week (Wed)
    m, w = HB.period_frame(d, "ME"), HB.period_frame(d, "W")
    assert m.close_time.iloc[-1] > m.timestamp.iloc[-1]    # pushed past the label
    assert w.close_time.iloc[-1] > w.timestamp.iloc[-1]
    assert (m.close_time.iloc[:-1] <= m.timestamp.iloc[:-1] + pd.Timedelta(days=1)).all()
    # the same weekly grouping as the legacy resample
    legacy = d.set_index("timestamp").resample("W").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    assert w[["timestamp", "open", "high", "low", "close"]].equals(legacy)


def test_trim_last_is_only_the_legacy_window():
    d = daily(pd.bdate_range("2024-01-01", periods=50))
    assert len(HB.trim_last(d, 30)) == 30 and HB.trim_last(d, 30).timestamp.iloc[-1] == d.timestamp.iloc[-1]
    assert len(HB.trim_last(d, None)) == 50 and len(HB.trim_last(d, 400)) == 50


# ------------------------------------------------------------------------------------------------ trend: no forming bars
def _daily_trend_world():
    closes = [200] + [150] * 10 + [161] + [150] * 3 + [171] + [150] * 5
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    df = pd.DataFrame(dict(timestamp=dates, open=closes, high=np.array(closes) + 1, low=np.array(closes) - 1, close=closes))
    return B.add_close_time(df, "1d")


def test_wit_daily_trend_bar_of_the_entry_day_is_not_visible():
    df = _daily_trend_world()
    zones = [zone("supply", 1, 2, 160.0), zone("supply", 3, 4, 170.0)]  # broken by bars 11 and 15
    ctx = TrendContext(df, zones, ath_full=False, ca_reset=False)
    entry_day_10am = df.timestamp[15] + pd.Timedelta(hours=10)
    assert ctx.classify(entry_day_10am) == "sideways"     # bar 15 (the second break) closes at 15:30: not yet known
    assert ctx.classify(df.close_time[15]) == "up"
    legacy_events = [(df.timestamp[11], "up"), (df.timestamp[15], "up")]  # legacy stamps events with the bar label (midnight)
    sys.path.insert(0, str(ROOT / "legacy" / "handoff" / "handoff" / "code"))
    mtz = M.CD.engine().mtz
    assert mtz._classify_trend_from_events(df[["timestamp", "open", "high", "low", "close"]], legacy_events, entry_day_10am) == "up"  # the leak


def test_mit_weekly_trend_uses_only_closed_weeks_and_the_formation_query_excludes_the_month_end_week():
    d = daily(pd.bdate_range("2024-01-01", "2024-04-30"))
    w = HB.period_frame(d, "W")
    k = int(w.index[w.timestamp == T("2024-02-04")][0])  # the week 29 Jan - 2 Feb: spans the January month end
    assert w.close_time[k] == T("2024-02-02 15:30")
    # two supply breaks: weeks k and k+1
    c = w.copy()
    c.loc[:, "close"] = 100.0
    c.loc[0, "close"] = 3e9  # an early high so the all-time-high override cannot fire
    c.loc[k, "close"] = 2e9
    c.loc[k + 1, "close"] = 2.9e9
    z = [zone("supply", 0, 1, 1.5e9), zone("supply", 0, 1, 2.5e9)]  # first broken in week k, second only in week k+1
    ctx = TrendContext(c, z, ath_full=False, ca_reset=False)
    assert ctx.classify(T("2024-01-31 00:00")) != "up"                # month-end formation query: the Jan 29 - Feb 2 week is not closed
    assert ctx.classify(T("2024-02-07 11:00")) != "up"                # Wednesday of the next week: week k closed, k+1 not
    assert ctx.classify(c.close_time[k + 1] + pd.Timedelta(minutes=1)) == "up"


def test_decision_times_and_replay_start_rules():
    wit_pit = SimpleNamespace(combo="wit", mode=M.PIT)
    mit_pit = SimpleNamespace(combo="mit", mode=M.PIT)
    wit_leg = SimpleNamespace(combo="wit", mode=M.LEGACY)
    f = M.MtfContext.decision_time
    assert f(wit_pit, "2025-03-05 11:15") == T("2025-03-05 11:15")                       # start of the entry 2h bar
    assert f(mit_pit, "2025-03-05 00:00") == T("2025-03-05 09:15")                       # entry day 09:15
    assert f(wit_leg, "2025-03-05 10:00") == T("2025-03-05 10:00")                       # legacy keeps the label
    s = M.MtfContext.scan_start
    assert s(wit_pit, "2025-03-05 13:15") == T("2025-03-05 13:15")
    assert s(SimpleNamespace(combo="wit", mode=M.LEGACY), "2025-03-05 10:00") == T("2025-03-05 10:15")  # first 60m bar start >= label
    assert s(SimpleNamespace(combo="mit", mode=M.PIT), "2025-03-05 00:00") == T("2025-03-05 09:15")


def test_2h_wit_ltf_is_session_aligned_in_hardened_mode_only():
    h = B.add_close_time(pd.DataFrame(dict(timestamp=[T(f"2025-03-05 {s}") for s in ("09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15")],
                                           open=1.0, high=2.0, low=0.5, close=1.5)), "60m")
    assert list(B.resample_2h_session(h).timestamp.dt.strftime("%H:%M")) == ["09:15", "11:15", "13:15", "15:15"]
    assert list(B.resample_2h_legacy(h).timestamp.dt.strftime("%H:%M")) == ["08:00", "10:00", "12:00", "14:00"]


# ------------------------------------------------------------------------------------------------ real data
def _old_trades(combo):
    o = pd.read_csv(OLD[combo], parse_dates=["entry_time"])
    return o[o.entry_time >= M.pd.Timestamp("2021-01-01")]


@need_real
@pytest.mark.slow
@pytest.mark.parametrize("combo", ["wit", "mit"])
def test_legacy_mode_reproduces_the_stored_2021_results(combo):
    o = _old_trades(combo)
    for t in list(o.ticker.unique()[:4]) + ["RELIANCE.NS"]:
        rows = M.build(t, combo, mode=M.LEGACY, do_replay=False)
        new = sorted((str(r["entry_time"]), r["type"], round(r["entry_price"], 4), round(r["stop"], 4)) for r in rows)
        old = sorted((str(x.entry_time), x.type, round(x.entry_price, 4), round(x.stop, 4)) for x in o[o.ticker == t].itertuples())
        assert new == old, t


DECISION = ["type", "htf_key", "ltf_key", "entry_bar", "entry_time", "entry_price", "stop", "target", "trend_htf", "trend_entry", "scan_start"]


@need_real
@pytest.mark.slow
@pytest.mark.parametrize("combo", ["wit", "mit"])
def test_hardened_mode_is_deterministic_and_append_stable(combo):
    t = _old_trades(combo).ticker.value_counts().index[0]
    fr = M.load_frames(t)
    a = M.build(t, combo, frames=fr, do_replay=False)
    assert a == M.build(t, combo, frames=fr, do_replay=False)
    assert len(a) > 0
    # cut the data mid-history; a ticker with a single trade is cut 45 days after it (so something is left to compare)
    cut = a[len(a) // 2]["entry_time"] if len(a) > 1 else a[-1]["entry_time"] + pd.Timedelta(days=45)
    cut_fr = B.truncate_frames(fr, cut)
    b = M.build(t, combo, frames=cut_fr, do_replay=False)
    pick = lambda rows: sorted(tuple(str(r[c]) for c in DECISION) for r in rows if r["entry_time"] < cut)  # noqa: E731
    assert len(pick(a)) > 0 and pick(a) == pick(b)


@need_real
@pytest.mark.slow
@pytest.mark.parametrize("combo", ["wit", "mit"])
def test_trend_states_at_decision_times_do_not_depend_on_later_data(combo):
    t = _old_trades(combo).ticker.value_counts().index[0]
    fr = M.load_frames(t)
    full = M.MtfContext(t, fr, combo, M.PIT)
    rows = M.b0_trades(full)[:3]
    assert rows
    for r in rows:
        t_d = r["entry_time"]
        cut = B.truncate_frames(fr, t_d.normalize() if combo == "mit" else t_d)  # bars starting before the decision time/day
        part = M.MtfContext(t, cut, combo, M.PIT)
        assert full.trend_at(t_d) == part.trend_at(t_d)
        assert full.trend_at(r["htf_formed_at"]) == part.trend_at(r["htf_formed_at"])
