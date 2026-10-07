"""Corporate-action / abnormal-gap flags (Phase A, A6).

Finding (7 Oct 2026): the Kite daily frames ARE adjusted for splits (NESTLEIND 1:10 on 2024-01-05, TATASTEEL 1:10 on 2022-07-28,
IRCTC 1:5 on 2021-10-28 show no gap). What remains in the 503-ticker DIT15 frames are a few abnormal one-day moves (listing-day
artifacts, demergers, other unadjusted events).

Rule: a daily bar whose close differs from the previous close by more than ABNORMAL_MOVE (35 %, the threshold already used in
scripts/run_qit_kite.py item 5) is a flagged event day. NSE price bands make a genuine 35 % one-day move very rare, so a flag means
"prices before and after this day may not be comparable". A trade is excluded (not deleted: kept in the file with
ca_excluded=True and listed in the report) when a flagged day falls in [HTF base start - CA_PAD_DAYS, trade end], where
trade end = exit time if resolved, else the end of the 90-day horizon. The pad covers the 14-bar ATR used for zone sizes.
"""
import numpy as np
import pandas as pd

ABNORMAL_MOVE = 0.35
CA_PAD_DAYS = 30


def flag_days(daily):
    """Sorted array (datetime64, normalized) of flagged dates in a daily frame."""
    if len(daily) < 2:
        return np.array([], dtype="datetime64[ns]")
    c = daily["close"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = c[1:] / c[:-1] - 1.0
    bad = ~np.isfinite(r) | (np.abs(r) > ABNORMAL_MOVE)
    days = pd.to_datetime(daily["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]")[1:]
    return np.sort(days[bad])


def last_flag_before(flags, t):
    """Latest flagged date <= t (as pd.Timestamp), or None."""
    if len(flags) == 0:
        return None
    i = int(np.searchsorted(flags, np.datetime64(pd.Timestamp(t)), side="right")) - 1
    return pd.Timestamp(flags[i]) if i >= 0 else None


def window_has_flag(flags, start, end):
    """True if any flagged date lies in [start, end]."""
    if len(flags) == 0:
        return False
    a = np.datetime64(pd.Timestamp(start).normalize())
    b = np.datetime64(pd.Timestamp(end))
    i = int(np.searchsorted(flags, a, side="left"))
    return i < len(flags) and flags[i] <= b
