"""Bar loading and bar-time conventions (Phase A, A1/A2/A4).

Every frame gets an explicit `close_time`: the moment the bar's OHLC is final. A decision at time T may only use bars with
close_time <= T. Kite labels a bar by its START (intraday) or its date (daily), so the label is never the close time.

Conventions (NSE cash session 09:15-15:30 IST, naive wall-clock timestamps as stored by src/kite_client.py):
  daily       close_time = date 15:30
  15m / 60m   close_time = start + interval, capped at 15:30 when the bar starts inside the regular session
              (Kite's last 60m bar 15:15-15:30 is 15 minutes long). Bars outside the regular session (muhurat / special
              sessions, e.g. 18:15) close at start + interval.
  2h          session-aligned bins anchored at 09:15 of each date: 09:15-11:15, 11:15-13:15, 13:15-15:15, 15:15-15:30 (stub).
              This is the TradingView convention for NSE. close_time = latest close_time of the 60m bars inside the bin.
              Legacy used pandas resample('2h') on clock hours: bins 08:00 / 10:00 / 12:00 / 14:00, i.e. a one-hour first bar,
              labels before the open, and a label (start) that a `timestamp <= T` test treats as if the bar were already closed.
No end-anchored windows: a frame always starts at its first stored bar (or an explicit start date), so appending later data
never changes earlier bars, ATR seeds or zones (A4).
"""
from pathlib import Path

import numpy as np
import pandas as pd

SESSION_OPEN = pd.Timedelta(hours=9, minutes=15)
SESSION_CLOSE = pd.Timedelta(hours=15, minutes=30)
INTERVALS = {"15m": pd.Timedelta(minutes=15), "60m": pd.Timedelta(minutes=60), "1m": pd.Timedelta(minutes=1)}
TWO_HOURS = pd.Timedelta(hours=2)
REGULAR_15M_SLOTS = 25  # 09:15 .. 15:15


def add_close_time(df, interval):
    """Return a copy of df (timestamp, open, high, low, close) with a close_time column (see module docstring)."""
    out = df.copy()
    ts = pd.to_datetime(out["timestamp"])
    out["timestamp"] = ts
    day = ts.dt.normalize()
    if interval == "1d":
        out["close_time"] = day + SESSION_CLOSE
        return out
    end = ts + INTERVALS[interval]
    session_end = day + SESSION_CLOSE
    inside = ts < session_end
    out["close_time"] = end.where(~inside | (end <= session_end), session_end)
    return out


def load_frame(frames_dir, ticker, interval, start=None, end=None):
    """Read {ticker}__{interval}.csv (legacy frame format) with close_time. `start`/`end` bound by timestamp (end exclusive)."""
    path = Path(frames_dir) / f"{ticker}__{interval}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "close_time"])
    df = pd.read_csv(path, parse_dates=["timestamp"])[["timestamp", "open", "high", "low", "close"]]
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("timestamp").drop_duplicates("timestamp")
    if start is not None:
        df = df[df["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["timestamp"] < pd.Timestamp(end)]
    return add_close_time(df.reset_index(drop=True), interval)


def resample_2h_session(df60):
    """Session-aligned 2h bars from 60m bars (with close_time). Output: timestamp (bin start), OHLC, close_time, n_bars."""
    if df60.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "close_time", "n_bars"])
    ts = pd.to_datetime(df60["timestamp"])
    day = ts.dt.normalize()
    k = ((ts - day - SESSION_OPEN) // TWO_HOURS).astype(int)
    start = day + SESSION_OPEN + k * TWO_HOURS
    g = df60.assign(_bin=start).groupby("_bin", sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "close_time": g["close_time"].max(), "n_bars": g["open"].size(),
    }).reset_index().rename(columns={"_bin": "timestamp"})
    return out[["timestamp", "open", "high", "low", "close", "close_time", "n_bars"]]


def resample_2h_legacy(df60):
    """Legacy clock-hour 2h bars exactly as mtf_zones._resample(df, '2h'), plus the true close_time of each bin."""
    d = df60.set_index("timestamp")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "close_time": "max"}
    out = d.resample("2h").agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out[["timestamp", "open", "high", "low", "close", "close_time"]]


def intraday_incomplete_days(df15, daily):
    """Dates whose regular-session 15m coverage is partial: 1..24 of the 25 slots 09:15..15:15 present, or a daily bar exists
    (inside the 15m data span) with no 15m bar at all. Special-session-only dates (no regular slot, e.g. muhurat) are not flagged.
    Returns {date: missing_slot_count}."""
    if df15.empty:
        return {}
    ts = pd.to_datetime(df15["timestamp"])
    tod = ts - ts.dt.normalize()
    regular = (tod >= SESSION_OPEN) & (tod < SESSION_CLOSE)
    cnt = ts[regular].dt.normalize().value_counts()
    out = {d: REGULAR_15M_SLOTS - int(n) for d, n in cnt.items() if n < REGULAR_15M_SLOTS}
    lo, hi = ts.min().normalize(), ts.max().normalize()
    have = set(ts.dt.normalize().unique())
    for d in pd.to_datetime(daily["timestamp"]).dt.normalize():
        if lo <= d <= hi and d not in have:
            out[d] = REGULAR_15M_SLOTS
    return out


def truncate_frames(frames, cutoff):
    """Copy of {interval: frame} keeping only bars whose timestamp < cutoff (used by append-stability tests)."""
    c = pd.Timestamp(cutoff)
    return {k: v[v["timestamp"] < c].reset_index(drop=True) for k, v in frames.items()}


def closed_mask(close_times, t):
    """Boolean mask of bars whose close_time <= t."""
    return np.asarray(close_times) <= np.datetime64(pd.Timestamp(t))
