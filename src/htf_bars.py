"""Weekly / monthly bars with explicit close times (Phase A hardening for WIT and MIT).

Grouping is exactly the legacy one (mtf_zones._resample: pandas 'W' = weeks ending Sunday, 'ME' = calendar months, label = period
END date at midnight), so zones, labels and the label-based matching semantics are unchanged. What is added:
  close_time  = close_time of the period's last daily bar (last trading day 15:30), so "known at" is explicit: a weekly or monthly
                bar is usable at time T only if close_time <= T (the label, a Sunday or a month-end date, is NOT the close time:
                a month-end label at midnight is earlier than that day's 15:30 close);
  incomplete final period: when the data ends before the period does (the last daily bar is earlier than the last possible trading
                day of the period), close_time is pushed past the label (label + 1 day) so the unfinished bar is never "closed".
No end-anchored windows: frames start at the first daily bar. trim_last() exists only to reproduce the legacy windows in legacy mode.
"""
import pandas as pd

OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}


def period_frame(d1, rule):
    """Weekly ('W') or monthly ('ME') bars from daily bars (with close_time). Columns: timestamp (label), OHLC, close_time."""
    if d1.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "close_time"])
    d = d1.set_index("timestamp")
    agg = d.resample(rule).agg({**OHLC, "close_time": "max"})
    out = agg.dropna(subset=["open", "high", "low", "close"]).reset_index()
    last_day = pd.Timestamp(d1["timestamp"].max()).normalize()
    back = out["timestamp"].dt.weekday.map({5: 1, 6: 2}).fillna(0).astype(int)  # a weekend label: its last trading day is Fri
    complete = last_day >= (out["timestamp"].dt.normalize() - pd.to_timedelta(back, unit="D"))
    out["close_time"] = out["close_time"].where(complete, out["timestamp"].dt.normalize() + pd.Timedelta(days=1))
    return out


def trim_last(df, n):
    """Legacy end-anchored window (mtf_zones._build_frame): keep the last n bars. Legacy mode only."""
    if n and len(df) > n:
        return df.iloc[-n:].reset_index(drop=True)
    return df
