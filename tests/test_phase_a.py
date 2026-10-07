"""Phase A regression tests (docs/PHASE_A_PLAN.md section 6).

Fast synthetic tests always run. Real-data tests need data/cache/kite_frames_dit15_long (gitignored) and are skipped without it;
the legacy-reproduction test also needs data/cache/checkpoints/dit15_v2_cap5_sh_lw (the 4d02f6d run).
Run: python -m pytest tests/test_phase_a.py -q          (add -m "not slow" for the synthetic part only)
"""
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import asof  # noqa: E402
import bars as B  # noqa: E402
import corp_actions as CA  # noqa: E402
import costs  # noqa: E402
import portfolio as P  # noqa: E402
import replay as RP  # noqa: E402
from trend_pit import TrendContext  # noqa: E402

FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
CKPT = ROOT / "data" / "cache" / "checkpoints" / "dit15_v2_cap5_sh_lw"
need_frames = pytest.mark.skipif(not FRAMES.exists(), reason="kite_frames_dit15_long missing")
T = pd.Timestamp


# ---------------------------------------------------------------------------------------------- helpers
def day60(date, starts=("09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"), base=100.0):
    rows = [dict(timestamp=T(f"{date} {s}"), open=base, high=base + 1, low=base - 1, close=base) for s in starts]
    return B.add_close_time(pd.DataFrame(rows), "60m")


def frame15(rows):
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return B.add_close_time(df, "15m")


def trade(kind="demand", entry=100.0, stop=98.0, target=104.0, scan="2025-01-01 09:15"):
    return dict(type=kind, entry_price=entry, stop=stop, target=target, risk=abs(entry - stop), scan_start=T(scan))


def run(rows, tr, **kw):
    return RP.replay(RP.arrays(frame15(rows)), tr, **kw)


# ---------------------------------------------------------------------------------------------- A2 / A1 bar times
def test_close_times():
    d = B.add_close_time(pd.DataFrame(dict(timestamp=[T("2025-01-01")], open=[1], high=[1], low=[1], close=[1])), "1d")
    assert d.close_time[0] == T("2025-01-01 15:30")
    h = day60("2025-01-01")
    assert h.close_time.iloc[0] == T("2025-01-01 10:15")
    assert h.close_time.iloc[-1] == T("2025-01-01 15:30")  # 15:15 bar is 15 minutes long
    s = B.add_close_time(pd.DataFrame(dict(timestamp=[T("2025-11-01 18:15")], open=[1], high=[1], low=[1], close=[1])), "60m")
    assert s.close_time[0] == T("2025-11-01 19:15")  # special session: start + interval


def test_2h_session_alignment_normal_day():
    b = B.resample_2h_session(day60("2025-01-01"))
    assert list(b.timestamp.dt.strftime("%H:%M")) == ["09:15", "11:15", "13:15", "15:15"]
    assert list(b.close_time.dt.strftime("%H:%M")) == ["11:15", "13:15", "15:15", "15:30"]
    assert list(b.n_bars) == [2, 2, 2, 1]


def test_2h_session_partial_day_and_special_session():
    part = day60("2025-01-02", starts=("09:15", "10:15", "11:15", "12:15", "13:15", "14:15"))  # 15:15 missing (Aug-Oct 2026 data)
    spec = B.add_close_time(pd.DataFrame([dict(timestamp=T("2025-01-03 18:15"), open=1, high=1, low=1, close=1)]), "60m")
    b = B.resample_2h_session(pd.concat([part, spec], ignore_index=True))
    assert list(b.timestamp.dt.strftime("%m-%d %H:%M")) == ["01-02 09:15", "01-02 11:15", "01-02 13:15", "01-03 17:15"]
    assert b.close_time.iloc[2] == T("2025-01-02 15:15")
    assert b.close_time.iloc[3] == T("2025-01-03 19:15")


def test_legacy_2h_bins_are_clock_hours():
    """Documents the legacy convention that A2 replaces: 08:00 bin holds only the 09:15 hour; labels precede the data."""
    b = B.resample_2h_legacy(day60("2025-01-01"))
    assert list(b.timestamp.dt.strftime("%H:%M")) == ["08:00", "10:00", "12:00", "14:00"]
    assert b.close_time.iloc[1] == T("2025-01-01 12:15")  # label 10:00, really closes 12:15


def test_entry_inside_forming_2h_bar_sees_only_closed_bars():
    b = B.resample_2h_session(pd.concat([day60("2025-01-01"), day60("2025-01-02")], ignore_index=True))
    t_d = T("2025-01-02 10:30")
    usable = b[B.closed_mask(b.close_time, t_d)]
    assert usable.timestamp.max() == T("2025-01-01 15:15")  # the 09:15 bin of 01-02 closes 11:15: not usable
    leg = b[b.timestamp <= t_d]                              # the legacy test would include it
    assert leg.timestamp.max() == T("2025-01-02 09:15")


# ---------------------------------------------------------------------------------------------- A1 trend / A3 ATH
def _trend_df(closes, start="2025-01-01"):
    """One 2h bar per row on consecutive session slots, with close_time."""
    ts = []
    d = T(start)
    while len(ts) < len(closes):
        for s in ("09:15", "11:15", "13:15", "15:15"):
            ts.append(T(f"{d.date()} {s}"))
        d += pd.Timedelta(days=1)
    ts = ts[:len(closes)]
    df = pd.DataFrame(dict(timestamp=ts, open=closes, high=np.array(closes) + 1, low=np.array(closes) - 1, close=closes))
    df["close_time"] = [min(t + pd.Timedelta(hours=2), t.normalize() + pd.Timedelta(hours=15, minutes=30)) for t in ts]
    return df


def _zone(kind, base_start, leg_end, distal):
    return SimpleNamespace(type=kind, base_start_index=base_start, leg_end_index=leg_end, distal_line=distal)


def test_forming_bar_break_not_used():
    # high early close (no ATH), two supply zones broken at bars 6 and 9; bar 9 is still forming at the query time
    closes = [200, 150, 150, 150, 150, 150, 161, 150, 150, 171, 150, 150]
    df = _trend_df(closes)
    zones = [_zone("supply", 1, 2, 160.0), _zone("supply", 3, 4, 170.0)]
    ctx = TrendContext(df, zones, ath_full=False, ca_reset=False)
    q = df.timestamp[9] + pd.Timedelta(minutes=15)       # inside bar 9
    assert ctx.classify(q) == "sideways"                 # only one closed break
    assert ctx.classify(df.close_time[9]) == "up"        # after bar 9 closes: two breaks
    sys.path.insert(0, str(ROOT / "legacy" / "handoff" / "handoff" / "code"))
    import candidates
    mtz = candidates.engine().mtz
    ev = [(T(df.timestamp[6]), "up"), (T(df.timestamp[9]), "up")]  # legacy stamps events with the bar label
    assert mtz._classify_trend_from_events(df[["timestamp", "open", "high", "low", "close"]], ev, q) == "up"  # the leak


def test_ath_ignores_unclosed_and_future_bars():
    closes = [100, 101, 102, 103, 110, 104]
    df = _trend_df(closes)
    ctx = TrendContext(df, [], ath_full=False, ca_reset=False)
    assert ctx.ath_at(df.close_time[3]) is True
    assert ctx.ath_at(df.timestamp[4] + pd.Timedelta(minutes=30)) is True   # bar 4 (110) still forming: not seen
    assert ctx.ath_at(df.close_time[5]) is False
    longer = _trend_df(closes + [500])                                       # appending later data changes nothing earlier
    assert TrendContext(longer, [], ath_full=False, ca_reset=False).ath_at(df.close_time[3]) is True


def test_ath_uses_daily_history_only_up_to_previous_close():
    df = _trend_df([100, 101, 102, 103], start="2025-01-02")
    daily = B.add_close_time(pd.DataFrame(dict(timestamp=[T("2025-01-01"), T("2025-01-02")], open=[0, 0], high=[0, 0],
                                               low=[0, 0], close=[150.0, 999.0])), "1d")
    ctx = TrendContext(df, [], daily=daily, ath_full=True, ca_reset=False)
    assert ctx.ath_at(df.close_time[1]) is False   # 150 from 01-01 is known; 999 (01-02 close) is not, intraday 01-02
    ctx2 = TrendContext(df, [], daily=daily.iloc[:1].assign(close=[90.0]), ath_full=True, ca_reset=False)
    assert ctx2.ath_at(df.close_time[1]) is True


def test_ca_reset_ignores_prices_before_flag():
    df = _trend_df([100, 101, 102, 103], start="2025-01-02")
    daily = B.add_close_time(pd.DataFrame(dict(timestamp=[T("2024-12-30"), T("2024-12-31"), T("2025-01-01")],
                                               open=[0] * 3, high=[0] * 3, low=[0] * 3, close=[500.0, 500.0, 120.0])), "1d")
    flags = CA.flag_days(daily)
    assert list(pd.to_datetime(flags)) == [T("2025-01-01")]
    on = TrendContext(df, [], daily=daily, ca_flags=flags, ath_full=True, ca_reset=True)
    off = TrendContext(df, [], daily=daily, ca_flags=flags, ath_full=True, ca_reset=False)
    assert on.ath_at(df.close_time[1]) is False    # 120 (01-01 close, after the flag) still above 101
    assert on.ath_at(df.close_time[3]) is False
    assert off.ath_at(df.close_time[3]) is False   # 500 before the flag blocks it without the reset
    daily2 = daily.assign(close=[500.0, 500.0, 99.0])
    assert TrendContext(df, [], daily=daily2, ca_flags=CA.flag_days(daily2), ath_full=True, ca_reset=True).ath_at(df.close_time[3])


def test_ca_window():
    f = np.array([np.datetime64("2025-03-10")], dtype="datetime64[ns]")
    assert CA.window_has_flag(f, T("2025-03-01"), T("2025-03-10 10:00"))
    assert not CA.window_has_flag(f, T("2025-03-11"), T("2025-04-01"))


# ---------------------------------------------------------------------------------------------- A5 regime as-of
def test_daily_asof_never_sees_same_day_close():
    daily = pd.DataFrame(dict(timestamp=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]), close=[1.0, 2.0, 3.0]))
    assert asof.daily_value_asof(daily, "close", T("2025-01-02 11:00")) == 1.0
    assert asof.daily_value_asof(daily, "close", T("2025-01-02 15:30"), decision_after_close=True) == 2.0
    assert np.isnan(asof.daily_value_asof(daily, "close", T("2025-01-01 10:00")))
    j = asof.asof_join_daily(pd.Series([T("2025-01-02 09:15"), T("2025-01-04 10:00")]), daily, ["close"])
    assert list(j.close) == [1.0, 3.0]


# ---------------------------------------------------------------------------------------------- A7 replay
def test_replay_win_loss_and_r():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104)]
    r = run(rows, trade())
    assert (r["outcome"], r["r"]) == ("WIN", 2.0)
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-01 09:30", 100.5, 100.6, 97.5, 98)]
    assert run(rows, trade())["outcome"] == "LOSS"


def test_replay_gap_through_stop_books_open():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-02 09:15", 96, 97, 95, 96)]
    r = run(rows, trade())
    assert r["outcome"] == "LOSS" and r["exit_price"] == 96 and r["r"] == pytest.approx(-2.0)


def test_ambiguous_stays_ambiguous_without_minutes():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-01 09:30", 100.5, 105, 97, 100)]
    r = run(rows, trade())
    assert r["outcome"] == "AMBIGUOUS" and r["reason"].startswith("MINUTE_NOT_CACHED")
    rows = [("2025-01-01 09:15", 103, 105, 99.5, 104)]          # target in the fill bar (may be before the fill)
    assert run(rows, trade())["outcome"] == "AMBIGUOUS"
    rows = [("2025-01-01 09:15", 97, 99, 96, 98)]               # gap-fill opens beyond the stop
    assert run(rows, trade())["reason"] == "gap-fill opens beyond the stop"


class _FakeMinutes:
    def __init__(self, rows):
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
        self.ts = pd.to_datetime(df.timestamp).to_numpy(dtype="datetime64[ns]")
        self.o, self.h, self.l, self.c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))

    bars = RP.MinuteCache.bars


def test_minute_drilldown_resolves_and_keeps_true_ties():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-01 09:30", 100.5, 105, 97, 100)]
    m = _FakeMinutes([("2025-01-01 09:30", 100.5, 105, 100.4, 104.8), ("2025-01-01 09:31", 104.8, 104.9, 97, 100)])
    r = run(rows, trade(), minute=m)
    assert (r["outcome"], r["decided_interval"]) == ("WIN", "1minute")
    tie = _FakeMinutes([("2025-01-01 09:30", 100.5, 105, 97, 100)])
    assert run(rows, trade(), minute=tie)["outcome"] == "AMBIGUOUS"
    part = _FakeMinutes([("2025-01-01 09:30", 100.5, 103, 99, 100)])  # does not cover the 15m range
    assert run(rows, trade(), minute=part)["reason"].startswith("MINUTE_INCOMPLETE")


def test_open_censored_nofill():
    flat = [(f"2025-01-{d:02d} 09:15", 101, 101.5, 100.5, 101) for d in range(1, 10)]
    filled = [("2024-12-31 09:15", 101, 101, 99.9, 100.5)] + flat
    late = [("2025-06-01 09:15", 101, 101, 101, 101)]
    r = run(filled + late, trade(scan="2024-12-31 09:15"))
    assert r["outcome"] == "OPEN" and r["mtm_r"] is not None
    assert run(filled, trade(scan="2024-12-31 09:15"))["outcome"] == "CENSORED"
    assert run(flat + late, trade(scan="2025-01-01 09:15"))["outcome"] == "NOFILL"


def test_intraday_data_gap():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-02 09:15", 101, 102, 100.5, 101)]
    tr = trade()
    daily_hl = {T("2025-01-01"): (101, 100), T("2025-01-02"): (102, 97.0)}  # the missing part of 01-02 reached the stop
    r = run(rows, tr, incomplete_days={T("2025-01-02"): 24}, daily_hl=daily_hl)
    assert (r["outcome"], r["reason"]) == ("AMBIGUOUS", "INTRADAY_DATA_GAP")
    assert run(rows, tr, incomplete_days={}, daily_hl=daily_hl)["outcome"] != "AMBIGUOUS"


def test_replay_deterministic():
    rows = [("2025-01-01 09:15", 101, 101, 100, 100.5), ("2025-01-01 09:30", 100.5, 104.5, 100.2, 104)]
    assert run(rows, trade()) == run(rows, trade())


# ---------------------------------------------------------------------------------------------- A8 / A9
def test_costs_deterministic():
    cm = costs.round_trip("rt0.20", 0.20)
    assert cm.cost_r(100, 104, 2) == pytest.approx(0.10 / 100 * 204 / 2)
    assert cm.net_r(2.0, 100, 104, 2) == pytest.approx(2.0 - 0.102)
    assert costs.scenarios()[0].cost_r(100, 104, 2) == 0
    with pytest.raises(ValueError):
        cm.cost_r(100, 100, 0)


def test_drawdown_and_capital_order_independent():
    assert P.max_drawdown([2, -1, -1, 2, -1]) == 2.0
    df = pd.DataFrame(dict(ticker=list("ABCD"), entry_price=[100.0] * 4, shares=[600, 600, 300, 300], fill_price=[100.0] * 4,
                           fill_time=pd.to_datetime(["2025-01-01 10:00"] * 2 + ["2025-01-02 10:00"] * 2),
                           exit_time=pd.to_datetime(["2025-01-03", "2025-01-03", "2025-01-04", "2025-01-04"])))
    a = P.capital_constrained(df)
    b = P.capital_constrained(df.iloc[::-1]).reindex(df.index)
    assert list(a) == list(b) == [True, False, True, False]


# ---------------------------------------------------------------------------------------------- real data
@need_frames
@pytest.mark.slow
@pytest.mark.skipif(not CKPT.exists(), reason="4d02f6d checkpoints missing")
@pytest.mark.parametrize("ticker", ["ADANIPORTS.NS", "HDFCBANK.NS", "RVNL.NS"])
def test_legacy_mode_reproduces_4d02f6d(ticker):
    import candidates as CD
    f = CKPT / f"{ticker}.pkl"
    if not f.exists():
        pytest.skip("no checkpoint")
    old = pickle.load(open(f, "rb"))
    new = [r for r in CD.build(ticker, mode=CD.LEGACY, do_replay=False) if r["is_b0"]]
    k = lambda L: sorted((str(T(x["entry_time"])), x["type"], round(x["entry_price"], 4), round(x["stop"], 4), x["shares"]) for x in L)  # noqa: E731
    assert k(new) == k(old)


DECISION = ["type", "htf_key", "ltf_key", "entry_time", "entry_price", "stop", "target", "trend_htf", "trend_entry",
            "trend_htf_fail", "trend_entry_fail", "wick_fresh_fail", "htf_strict_fail", "htf_cap_fail", "ltf_cap_fail", "is_b0",
            "relaxed_selected"]


@need_frames
@pytest.mark.slow
def test_candidates_deterministic_and_append_stable():
    import candidates as CD
    tk, cut = "ADANIPORTS.NS", T("2024-01-01")
    fr = CD.load_frames(tk)
    a = CD.build(tk, frames=fr, do_replay=False)
    assert a == CD.build(tk, frames=fr, do_replay=False)
    b = CD.build(tk, frames=B.truncate_frames(fr, cut), do_replay=False)
    pick = lambda rows: sorted(tuple(str(r[c]) for c in DECISION) for r in rows if r["entry_time"] < cut)  # noqa: E731
    assert len(pick(a)) > 0
    assert pick(a) == pick(b)


@need_frames
@pytest.mark.slow
def test_entry_time_decisions_use_no_bar_closing_after_t_d():
    """Recompute each decision of a few candidates on data cut at T_d (entry bar, forming 60m/2h bars and the entry day's
    daily bar removed). Point-in-time mode must give identical decisions."""
    import candidates as CD
    tk = "ADANIPORTS.NS"
    fr = CD.load_frames(tk)
    full = CD.TickerContext(tk, fr, CD.PIT)
    rows = [r for r in CD.build(tk, frames=fr, do_replay=False)][:4]
    assert rows
    for r in rows:
        t_d = r["entry_time"]
        cut = {"15m": fr["15m"][fr["15m"].close_time <= t_d], "60m": fr["60m"][fr["60m"].close_time <= t_d],
               "1d": fr["1d"][fr["1d"].timestamp < t_d.normalize()]}
        cut = {k: v.reset_index(drop=True) for k, v in cut.items()}
        c = CD.TickerContext(tk, cut, CD.PIT)
        assert full.trend_at(t_d) == c.trend_at(t_d), r["entry_time"]
        hz = [z for z in full.htf_rel + full.htf_b0 if CD.zkey(z)[1:] == tuple(r["htf_key"])][0]
        hz2 = [z for z in c.htf_rel + c.htf_b0 if CD.zkey(z)[1:] == tuple(r["htf_key"])][0]
        assert full.wick_fail(hz, t_d) == c.wick_fail(hz2, t_d)
        assert full.trend_at(full.t_formation(hz)) == c.trend_at(c.t_formation(hz2))
