"""Phase B Tier-1 feature tests: frozen registry, formulas, point-in-time boundaries, exclusions, determinism, dataset integrity.

Synthetic tests always run. Real-data tests need data/cache/kite_frames_dit15_long, the NIFTY daily file, the Phase A source
(results/nogit-145d6302/phase_a/pit_refetch/candidates.csv) and the generated dataset (results/.../phase_b/tier1); they skip
otherwise.   Run: python -m pytest tests/test_phase_b_features.py -q
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import asof  # noqa: E402
import bars as B  # noqa: E402
from ml import features as F  # noqa: E402
from ml import registry as R  # noqa: E402

SRC = ROOT / "results" / "nogit-145d6302" / "phase_a" / "pit_refetch" / "candidates.csv"
OUT = ROOT / "results" / "nogit-145d6302" / "phase_b" / "tier1"
need_real = pytest.mark.skipif(not (F.FRAMES.exists() and SRC.exists() and OUT.exists() and F.NIFTY_DIR.exists()),
                               reason="real data / Phase A source / dataset missing")


# ------------------------------------------------------------------------------------------------ synthetic world
def make_world(seed=0, n_d=420, n_sess=60):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_d)

    def walk(n, scale, start):
        return start * np.exp(np.cumsum(rng.normal(0, scale, n)))

    def ohlc(c):
        o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.001, len(c)))
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.002, len(c))))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.002, len(c))))
        return o, h, l

    c = walk(n_d, 0.01, 100.0)
    o, h, l = ohlc(c)
    d1 = B.add_close_time(pd.DataFrame(dict(timestamp=dates, open=o, high=h, low=l, close=c)), "1d")
    nifty = pd.DataFrame(dict(timestamp=dates, close=walk(n_d, 0.008, 10000.0)))
    ts = [d + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(minutes=15 * k) for d in dates[-n_sess:] for k in range(25)]
    c15 = walk(len(ts), 0.002, 100.0)
    o15, h15, l15 = ohlc(c15)
    m15 = B.add_close_time(pd.DataFrame(dict(timestamp=ts, open=o15, high=h15, low=l15, close=c15)), "15m")
    return d1, m15, nifty


def make_row(d1, m15, i, kind="demand", trend="up"):
    entry_ts = m15.timestamp[i]
    j = int(np.searchsorted(d1.timestamp.values.astype("datetime64[ns]"), np.datetime64(entry_ts.normalize()), side="left")) - 1
    he, le = j - 5, i - 30
    ls = le - 1
    prox, dist, entry, risk = (110.0, 100.0, 108.0, 1.5) if kind == "demand" else (100.0, 110.0, 102.0, 1.5)
    return dict(ticker="SYN", type=kind, entry_time=entry_ts, ltf_key=str((le - 6, le - 2, ls, le)),
                htf_key=str((he - 5, he - 3, he - 1, he)), T_L=m15.close_time[le], T_H=d1.close_time[he],
                ltf_base_count=3, htf_base_count=4, htf_strong_legout=True, overlap_frac=0.8, htf_proximal=prox,
                htf_distal=dist, entry_price=entry, risk=risk, wick_fresh_fail=False, trend_entry=trend)


def indices(d1, m15, nifty, row):
    t = pd.Timestamp(row["entry_time"])
    i = int(np.searchsorted(m15.timestamp.values.astype("datetime64[ns]"), np.datetime64(t)))
    j = asof.daily_index_asof(pd.to_datetime(d1.timestamp).dt.normalize().to_numpy("datetime64[ns]"), t)
    k = asof.daily_index_asof(pd.to_datetime(nifty.timestamp).dt.normalize().to_numpy("datetime64[ns]"), t)
    return i, j, k


I_ENTRY = 25 * 40 + 3  # session 40, bar 3 -> 09:60 = 10:00


# ------------------------------------------------------------------------------------------------ registry
def test_registry_is_frozen():
    assert len(R.FEATURES) == 17 and len(R.MODEL_COLUMNS) == 18
    assert R.MODEL_COLUMNS == [
        "ltf_base_count", "htf_base_count", "htf_strong_legout", "ltf_leg_body_atr", "htf_zone_width_atr", "overlap_frac",
        "ltf_pos_in_htf", "wick_fresh_fail", "log_ltf_age_bars", "trend_up", "trend_down", "risk_atr_d", "approach_speed_atr",
        "cost_in_r_rt0.20", "type_demand", "nifty_above_200dma", "stock_rs63", "is_0915_bar"]
    assert [f["name"] for f in R.FEATURES if len(f["columns"]) == 2] == ["trend_entry"]
    R.assert_no_forbidden(R.MODEL_COLUMNS)
    assert not set(R.MODEL_COLUMNS) & set(R.META_COLUMNS)
    with pytest.raises(ValueError):
        R.assert_no_forbidden(R.MODEL_COLUMNS + ["r_gross"])
    for bad in ("outcome", "exit_price", "fill_price", "entry_price", "ticker", "shares"):
        assert bad in R.FORBIDDEN


# ------------------------------------------------------------------------------------------------ formulas
@pytest.mark.parametrize("kind", ["demand", "supply"])
def test_formulas_with_controlled_atr(kind):
    d1, m15, nifty = make_world(1)
    n_d, n15 = len(d1), len(m15)
    atr_d, atr15 = np.arange(n_d) * 0.1 + 1.0, np.arange(n15) * 0.01 + 1.0  # distinct per index: wrong index gives wrong value
    td = F.TickerData(d1, m15, nifty, atr_d=atr_d, atr15=atr15)
    row = make_row(d1, m15, I_ENTRY, kind, trend="down")
    f, why = F.compute_features(row, td)
    assert why is None
    i, j, k = indices(d1, m15, nifty, row)
    assert i == I_ENTRY
    le, ls = i - 30, i - 31
    he = j - 5
    body = (m15.close[ls:le + 1] - m15.open[ls:le + 1]).abs().sum()
    assert f["ltf_leg_body_atr"] == pytest.approx(body / atr15[le])
    assert f["htf_zone_width_atr"] == pytest.approx(10.0 / atr_d[he])
    assert f["risk_atr_d"] == pytest.approx(1.5 / atr_d[j])
    assert f["ltf_pos_in_htf"] == pytest.approx(0.8)
    assert f["log_ltf_age_bars"] == pytest.approx(math.log(30))
    move = m15.close[i - 1] - m15.close[i - 9]  # 8 completed close-to-close intervals
    assert f["approach_speed_atr"] == pytest.approx((-move if kind == "demand" else move) / atr15[i - 1])
    assert f["cost_in_r_rt0.20"] == pytest.approx(0.002 * row["entry_price"] / 1.5)
    assert (f["trend_up"], f["trend_down"]) == (0.0, 1.0)
    assert f["type_demand"] == (1.0 if kind == "demand" else 0.0)
    assert f["is_0915_bar"] == 0.0 and f["htf_strong_legout"] == 1.0 and f["wick_fresh_fail"] == 0.0
    assert f["ltf_base_count"] == 3 and f["htf_base_count"] == 4 and f["overlap_frac"] == 0.8


def test_trend_dummies_and_0915_flag():
    d1, m15, nifty = make_world(2)
    td = F.TickerData(d1, m15, nifty, atr_d=np.ones(len(d1)), atr15=np.ones(len(m15)))
    for state, want in (("up", (1.0, 0.0)), ("down", (0.0, 1.0)), ("sideways", (0.0, 0.0))):
        f, why = F.compute_features(make_row(d1, m15, 25 * 41, trend=state), td)  # bar 0 of a session = 09:15
        assert why is None and (f["trend_up"], f["trend_down"]) == want and f["is_0915_bar"] == 1.0
    assert F.compute_features(make_row(d1, m15, I_ENTRY, trend="n/a"), td)[1] == F.EX_TREND


def test_nifty_200dma_uses_d_minus_1():
    d1, m15, nifty = make_world(3)
    td_args = dict(atr_d=np.ones(len(d1)), atr15=np.ones(len(m15)))
    row = make_row(d1, m15, I_ENTRY)
    i, j, k = indices(d1, m15, nifty, row)
    up, down = nifty.copy(), nifty.copy()
    up["close"] = np.linspace(100, 200, len(nifty))
    down["close"] = np.linspace(200, 100, len(nifty))
    assert F.compute_features(row, F.TickerData(d1, m15, up, **td_args))[0]["nifty_above_200dma"] == 1.0
    assert F.compute_features(row, F.TickerData(d1, m15, down, **td_args))[0]["nifty_above_200dma"] == 0.0
    # only the entry-day NIFTY close changes: must not matter
    spike = up.copy()
    day = np.datetime64(pd.Timestamp(row["entry_time"]).normalize())
    spike.loc[spike.timestamp.values.astype("datetime64[ns]") >= day, "close"] = 1.0
    assert F.compute_features(row, F.TickerData(d1, m15, spike, **td_args))[0]["nifty_above_200dma"] == 1.0


def test_stock_rs63_uses_each_series_own_bars():
    d1, m15, nifty = make_world(4)
    row = make_row(d1, m15, I_ENTRY)
    nifty_gap = nifty.drop(index=[360, 361]).reset_index(drop=True)  # NIFTY calendar differs from the stock calendar
    td = F.TickerData(d1, m15, nifty_gap, atr_d=np.ones(len(d1)), atr15=np.ones(len(m15)))
    f, why = F.compute_features(row, td)
    assert why is None
    i, j, k = indices(d1, m15, nifty_gap, row)
    want = (d1.close[j] / d1.close[j - 63] - 1) - (nifty_gap.close[k] / nifty_gap.close[k - 63] - 1)
    assert f["stock_rs63"] == pytest.approx(want)
    assert d1.timestamp[j - 63] != nifty_gap.timestamp[k - 63]  # the two windows really start on different dates


# ------------------------------------------------------------------------------------------------ point-in-time
def _perturbed(d1, m15, nifty, i, entry_ts, seed=9, include_prev=False):
    rng = np.random.default_rng(seed)
    day = np.datetime64(entry_ts.normalize())
    a, b, c = d1.copy(), m15.copy(), nifty.copy()
    start = i - 1 if include_prev else i
    for col in ("open", "high", "low", "close"):
        b.loc[start:, col] = b.loc[start:, col].to_numpy() * rng.uniform(1.5, 3.0, len(b) - start)
        m = a.timestamp.values.astype("datetime64[ns]") >= day
        a.loc[m, col] = a.loc[m, col].to_numpy() * rng.uniform(1.5, 3.0, int(m.sum()))
    mn = c.timestamp.values.astype("datetime64[ns]") >= day
    c.loc[mn, "close"] = c.loc[mn, "close"].to_numpy() * rng.uniform(1.5, 3.0, int(mn.sum()))
    return a, b, c


@pytest.mark.parametrize("kind", ["demand", "supply"])
def test_no_future_information_in_features(kind):
    """ATR computed from the data: scrambling the entry bar and everything after it (15m), the entry date and after (daily and
    NIFTY) must leave every feature unchanged."""
    d1, m15, nifty = make_world(5)
    row = make_row(d1, m15, I_ENTRY, kind)
    base, why = F.compute_features(row, F.TickerData(d1, m15, nifty))
    assert why is None
    a, b, c = _perturbed(d1, m15, nifty, I_ENTRY, pd.Timestamp(row["entry_time"]))
    got, why2 = F.compute_features(row, F.TickerData(a, b, c))
    assert why2 is None and got == base
    # sanity: the test can detect leakage; scrambling the last completed bar DOES change the approach feature
    a2, b2, c2 = _perturbed(d1, m15, nifty, I_ENTRY, pd.Timestamp(row["entry_time"]), include_prev=True)
    assert F.compute_features(row, F.TickerData(a2, b2, c2))[0]["approach_speed_atr"] != base["approach_speed_atr"]


def test_entry_bar_and_entry_day_daily_bar_never_read():
    d1, m15, nifty = make_world(6)
    row = make_row(d1, m15, I_ENTRY)
    base = F.compute_features(row, F.TickerData(d1, m15, nifty))[0]
    b = m15.copy()
    b.loc[I_ENTRY, ["open", "high", "low", "close"]] = [1e6, 2e6, 1.0, 5e5]  # absurd entry bar
    a = d1.copy()
    day = np.datetime64(pd.Timestamp(row["entry_time"]).normalize())
    a.loc[a.timestamp.values.astype("datetime64[ns]") == day, ["open", "high", "low", "close"]] = [1e6, 2e6, 1.0, 5e5]
    assert F.compute_features(row, F.TickerData(a, b, nifty))[0] == base


def test_truncation_equivalence_synthetic():
    d1, m15, nifty = make_world(7)
    row = make_row(d1, m15, I_ENTRY)
    base = F.compute_features(row, F.TickerData(d1, m15, nifty))[0]
    t = pd.Timestamp(row["entry_time"])
    cut = F.TickerData(d1[d1.timestamp < t.normalize()].reset_index(drop=True), m15.iloc[:I_ENTRY].reset_index(drop=True),
                       nifty[nifty.timestamp < t.normalize()].reset_index(drop=True))
    got, why = F.compute_features(row, cut, require_entry_bar=False)
    assert why is None and got == base


# ------------------------------------------------------------------------------------------------ exclusions
def test_exclusion_reasons():
    d1, m15, nifty = make_world(8)
    ones = dict(atr_d=np.ones(len(d1)), atr15=np.ones(len(m15)))
    row = make_row(d1, m15, I_ENTRY)
    assert F.compute_features(row, F.TickerData(d1, m15, nifty, **ones))[1] is None
    # stock warm-up: fewer than 63 prior daily bars
    sd1, sm15, snif = make_world(8, n_d=60, n_sess=20)
    srow = make_row(sd1, sm15, 25 * 15 + 3)
    assert F.compute_features(srow, F.TickerData(sd1, sm15, snif, atr_d=np.ones(len(sd1)), atr15=np.ones(len(sm15))))[1] \
        == F.EX_WARMUP_STOCK
    # NIFTY warm-up
    short = nifty.iloc[-150:].reset_index(drop=True)
    assert F.compute_features(row, F.TickerData(d1, m15, short, **ones))[1] == F.EX_WARMUP_NIFTY
    # corporate-action day inside the 63-bar lookback
    i, j, k = indices(d1, m15, nifty, row)
    ca = d1.copy()
    ca.loc[j - 20:, "close"] = ca.loc[j - 20:, "close"].to_numpy() * 2.0
    assert F.compute_features(row, F.TickerData(ca, m15, nifty, **ones))[1] == F.EX_CA_63
    # entry bar missing / entry not after the leg
    off = dict(row, entry_time=pd.Timestamp(row["entry_time"]) + pd.Timedelta(minutes=1))
    assert F.compute_features(off, F.TickerData(d1, m15, nifty, **ones))[1] == F.EX_ENTRY_NOT_IN_FRAME
    early = dict(row, ltf_key=str((1, 2, 3, I_ENTRY)), T_L=m15.close_time[I_ENTRY])
    assert F.compute_features(early, F.TickerData(d1, m15, nifty, **ones))[1] == F.EX_ENTRY_BEFORE_LEG
    # zone keys that do not match the stored close times
    bad = dict(row, T_L=pd.Timestamp(row["T_L"]) + pd.Timedelta(minutes=15))
    assert F.compute_features(bad, F.TickerData(d1, m15, nifty, **ones))[1] == F.EX_KEY_MISMATCH
    # HTF leg end not before D-1
    j_row = dict(row, htf_key=str((1, 2, 3, j + 1)), T_H=d1.close_time[j + 1])
    assert F.compute_features(j_row, F.TickerData(d1, m15, nifty, **ones))[1] == F.EX_HTF_AFTER_D1


def test_select_pool_order_and_log():
    t0 = pd.Timestamp("2022-01-03 10:00")

    def r(ticker="A", entry=t0, htf="2021-12-01", pool=True, ca=False, price=10.0):
        return dict(ticker=ticker, type="demand", entry_time=entry, entry_price=price, stop=9.0,
                    htf_formed_at=pd.Timestamp(htf), relaxed_selected=pool, is_b0=False, ca_excluded=ca)

    df = pd.DataFrame([r(), r(htf="2021-11-01"), r(ticker="B", entry=pd.Timestamp("2020-12-31 10:00")),
                       r(ticker="C", pool=False), r(ticker="D", ca=True), r(ticker="E")])
    pool, log = F.select_pool(df)
    assert sorted(pool.ticker) == ["A", "E"]
    a = pool[pool.ticker == "A"].iloc[0]
    assert a.htf_formed_at == pd.Timestamp("2021-11-01")  # duplicate: earliest htf_formed_at kept
    reasons = dict(zip(log.ticker, log.reason))
    assert reasons["B"] == F.EX_BEFORE_2021 and reasons["C"] == F.EX_NOT_POOL
    assert reasons["D"] == F.EX_PHASE_A_CA and (log.reason == F.EX_DUP).sum() == 1


def test_build_ticker_deterministic_and_logs_exclusions():
    d1, m15, nifty = make_world(10)
    td = F.TickerData(d1, m15, nifty)
    good = make_row(d1, m15, I_ENTRY)
    bad = make_row(d1, m15, I_ENTRY + 25)
    bad["trend_entry"] = None
    rows = []
    for r in (good, bad):
        r = dict(r, htf_formed_at=pd.Timestamp("2020-06-01"), ltf_formed_at=pd.Timestamp("2021-01-01"), is_b0=True,
                 relaxed_selected=True, trend_htf_fail=False, trend_entry_fail=False, htf_strict_fail=False, htf_cap_fail=False,
                 ltf_cap_fail=False, stop=106.5, target=111.0, shares=100, outcome="LOSS", exit_reason="", decided_interval="15minute",
                 fill_time=pd.NaT, fill_price=np.nan, exit_time=pd.NaT, exit_price=np.nan, r_gross=-1.0, mtm_r=np.nan)
        rows.append(r)
    df = pd.DataFrame(rows)
    a = F.build_ticker("SYN", df, td)
    b = F.build_ticker("SYN", df, td)
    assert len(a[0]) == 1 and len(a[1]) == 1 and a[1][0]["reason"] == F.EX_TREND
    assert pd.DataFrame(a[0]).equals(pd.DataFrame(b[0])) and a[1] == b[1]
    assert a[0][0]["row_id"].startswith("SYN|demand|")
    assert F.build_ticker("SYN", df, None)[1][0]["reason"] == F.EX_NO_FRAME


# ------------------------------------------------------------------------------------------------ real data
@need_real
def test_dataset_integrity_and_manifest():
    m = json.load(open(OUT / "manifest.json"))
    ds = pd.read_csv(OUT / "features.csv")
    ex = pd.read_csv(OUT / "exclusions.csv")
    assert m["registry_version"] == R.REGISTRY_VERSION and m["source_code_hash"] == "cd73bf8d"
    assert list(ds.columns) == R.META_COLUMNS + R.MODEL_COLUMNS and m["model_columns"] == R.MODEL_COLUMNS
    assert len(ds) == m["rows_dataset"] == m["rows_pool"] - int((ex.stage == "features").sum())
    assert ds["row_id"].is_unique and m["duplicate_row_ids"] == 0
    X = ds[R.MODEL_COLUMNS].to_numpy(dtype=float)
    assert np.isfinite(X).all() and m["nan_cells"] == 0 and m["inf_cells"] == 0
    assert ex.reason.value_counts().to_dict() == m["exclusions"]
    assert pd.to_datetime(ds.entry_time).min() >= pd.Timestamp("2021-01-01")
    assert set(ex[ex.stage == "features"].reason) <= {F.EX_WARMUP_STOCK, F.EX_CA_63}  # nothing else silently dropped
    assert {"WIN", "LOSS", "AMBIGUOUS"} <= set(ds.outcome)  # outcome fields preserved, nothing relabelled


@need_real
def test_real_data_truncation_and_reproduction():
    ds = pd.read_csv(OUT / "features.csv", parse_dates=["entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at"])
    cand = pd.read_csv(SRC, parse_dates=["entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at", "fill_time", "exit_time"])
    cand["row_id"] = [F.row_id(r) for r in cand.to_dict("records")]
    cand = cand.drop_duplicates("row_id").set_index("row_id")
    nifty = F.load_nifty()
    for tk in ("ADANIPORTS.NS", "RVNL.NS"):
        d1 = B.load_frame(F.FRAMES, tk, "1d")
        m15 = B.load_frame(F.FRAMES, tk, "15m")
        full = F.TickerData(d1, m15, nifty)
        rows = ds[ds.ticker == tk].head(4)
        assert len(rows) >= 2
        for r in rows.to_dict("records"):
            c = cand.loc[r["row_id"]].to_dict()
            f_full, why = F.compute_features(c, full)
            assert why is None
            for col in R.MODEL_COLUMNS:  # reproduces the saved dataset
                assert f_full[col] == pytest.approx(r[col], rel=1e-9, abs=1e-12), (r["row_id"], col)
            t = pd.Timestamp(c["entry_time"])
            i = int(np.searchsorted(m15.timestamp.values.astype("datetime64[ns]"), np.datetime64(t)))
            cut = F.TickerData(d1[d1.timestamp < t.normalize()].reset_index(drop=True), m15.iloc[:i].reset_index(drop=True),
                               nifty[nifty.timestamp < t.normalize()].reset_index(drop=True))
            f_cut, why2 = F.compute_features(c, cut, require_entry_bar=False)
            assert why2 is None and f_cut == f_full  # data after the decision time cannot change a feature
