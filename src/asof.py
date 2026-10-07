"""Point-in-time (as-of) lookups (Phase A, A1/A5).

Rule: a value computed from a bar is known only at that bar's close_time (src/bars.py). For an intraday decision on date D,
daily information comes from D-1 (the last daily bar dated strictly before D), unless the caller states that the decision is
made after D's close (decision_after_close=True, e.g. an HTF zone confirmed at 15:30).
"""
import numpy as np
import pandas as pd


def last_closed_index(close_times, t):
    """Index of the last bar with close_time <= t, or -1. close_times must be sorted ascending."""
    ct = np.asarray(close_times, dtype="datetime64[ns]")
    return int(np.searchsorted(ct, np.datetime64(pd.Timestamp(t)), side="right")) - 1


def daily_index_asof(daily_dates, t, decision_after_close=False):
    """Index into a sorted array of daily dates (normalized) of the daily bar usable at time t, or -1.
    Intraday decision (default): last date strictly before t's date. After-close decision: last date <= t's date."""
    d = np.asarray(daily_dates, dtype="datetime64[ns]")
    day = np.datetime64(pd.Timestamp(t).normalize())
    side = "right" if decision_after_close else "left"
    return int(np.searchsorted(d, day, side=side)) - 1


def daily_value_asof(daily, column, t, decision_after_close=False):
    """Value of `column` in a daily frame (timestamp = date) usable at time t; NaN if none."""
    i = daily_index_asof(pd.to_datetime(daily["timestamp"]).dt.normalize().to_numpy(), t, decision_after_close)
    return daily[column].iloc[i] if i >= 0 else np.nan


def asof_join_daily(event_times, daily, columns, decision_after_close=False):
    """For each event time, the daily `columns` as of that time (vectorized daily_value_asof). Returns a DataFrame."""
    dates = pd.to_datetime(daily["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
    days = pd.to_datetime(pd.Series(event_times)).dt.normalize().to_numpy(dtype="datetime64[ns]")
    idx = np.searchsorted(dates, days, side="right" if decision_after_close else "left") - 1
    out = {}
    for c in columns:
        v = daily[c].to_numpy()
        out[c] = np.where(idx >= 0, v[np.clip(idx, 0, len(v) - 1)], np.nan) if len(v) else np.full(len(idx), np.nan)
    return pd.DataFrame(out, index=pd.Series(event_times).index)
