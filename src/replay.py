"""Offline, deterministic exit replay (Phase A, A7).

Same trade rules as src/exits.py (CLAUDE.md standing exit rule), but with no network: 15m bars from the frozen frames,
and a 1-minute drill-down only from minute files already in data/cache/kite/<SYM>/minute/. Identical inputs give identical
outputs. Kite is not installed on this machine, so the online replay cannot run anyway.

Outcome classes (exactly one per trade):
  WIN        target reached after the fill, before the stop.
  LOSS       stop reached after the fill (or a gap through the stop, booked at the open, R < -1).
  AMBIGUOUS  the order of fill/stop/target inside one bar cannot be settled. reason says why:
             "stop+target in same bar", "target in fill bar (could be pre-entry)", "gap-fill opens beyond the stop",
             MINUTE_NOT_CACHED / MINUTE_INCOMPLETE (15m bar ambiguous, no usable minute data), INTRADAY_DATA_GAP (a day with
             missing 15m bars whose daily bar shows that a level may have been hit in the missing part).
             Never converted to a win or a loss.
  OPEN       filled, neither stop nor target within the full 90-day horizon (no time exit in the strategy; mtm_r recorded).
  CENSORED   unresolved and the data ends before the horizon ends (cannot be known yet).
  NOFILL     the entry level is never traded within the full horizon (should not happen for pipeline candidates: their entry
             bar comes from the same 15m data; a NOFILL means a bar-mapping problem and is counted, not hidden).

Mechanics (unchanged from src/exits.minute_replay):
  fill = first bar at/after scan_start that trades through the entry; at the open if it gaps beyond the entry.
  In the fill bar only the stop counts; a target touch in the fill bar is AMBIGUOUS (it may have come before the fill).
  Later bars: gap beyond the stop -> loss at the open; gap beyond the target -> win booked at the target; stop and target in the
  same bar -> AMBIGUOUS. A 15m-AMBIGUOUS bar is replaced by its 1-minute bars (same rules, same state), then 15m continues.
Horizon: bars with timestamp in [scan_start, scan_start.normalize() + 90 days), as in scripts/replay_common.py.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MINUTE_DIR = ROOT / "data" / "cache" / "kite"
HORIZON_DAYS = 90
WIN, LOSS, AMBIGUOUS, OPEN, CENSORED, NOFILL = "WIN", "LOSS", "AMBIGUOUS", "OPEN", "CENSORED", "NOFILL"
_DRILL = "DRILL"


class MinuteCache:
    """All cached Kite minute files of one symbol, merged. Read-only, offline."""

    def __init__(self, ticker, root=MINUTE_DIR):
        sym = re.sub(r"[^A-Za-z0-9_&-]", "_", ticker.replace(".NS", ""))
        files = sorted((Path(root) / sym / "minute").glob("*.csv"))
        if files:
            df = pd.concat([pd.read_csv(f, parse_dates=["timestamp"]) for f in files], ignore_index=True)
            df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
            self.ts = df["timestamp"].to_numpy(dtype="datetime64[ns]")
            self.o, self.h, self.l, self.c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        else:
            self.ts = np.array([], dtype="datetime64[ns]")

    def bars(self, start, end):
        a = int(np.searchsorted(self.ts, start, side="left"))
        b = int(np.searchsorted(self.ts, end, side="left"))
        if b <= a:
            return None
        return self.ts[a:b], self.o[a:b], self.h[a:b], self.l[a:b], self.c[a:b]


class _State:
    __slots__ = ("filled", "fill", "fill_time", "gap")

    def __init__(self):
        self.filled, self.fill, self.fill_time, self.gap = False, None, None, False


def _bar(state, o, h, l, t, demand, entry, stop, target, final):
    """Apply one bar. Returns None (continue) or (label, exit_time, exit_price, detail). `final` = 1-minute level (no drill)."""
    if not state.filled:
        if not ((l <= entry) if demand else (h >= entry)):
            return None
        gap = (o < entry) if demand else (o > entry)
        state.filled, state.fill, state.fill_time, state.gap = True, (o if gap else entry), t, bool(gap)
        if gap and ((o <= stop) if demand else (o >= stop)):
            return (AMBIGUOUS, t, None, "gap-fill opens beyond the stop")
        s0 = (l <= stop) if demand else (h >= stop)
        t0 = (h >= target) if demand else (l <= target)
        if s0 and t0:
            return (AMBIGUOUS if final else _DRILL, t, None, "stop+target in fill bar")
        if t0:
            return (AMBIGUOUS if final else _DRILL, t, None, "target in fill bar (could be pre-entry)")
        if s0:
            return (LOSS, t, float(stop), "stop in fill bar")
        return None
    if (o <= stop) if demand else (o >= stop):
        return (LOSS, t, float(o), "gap through stop")
    if (o >= target) if demand else (o <= target):
        return (WIN, t, float(target), "gap through target (booked at target)")
    s = (l <= stop) if demand else (h >= stop)
    g = (h >= target) if demand else (l <= target)
    if s and g:
        return (AMBIGUOUS if final else _DRILL, t, None, "stop+target in same bar")
    if s:
        return (LOSS, t, float(stop), "")
    if g:
        return (WIN, t, float(target), "")
    return None


def replay(bars15, trade, minute=None, incomplete_days=None, daily_hl=None, horizon_days=HORIZON_DAYS, data_end=None):
    """Replay one trade.

    bars15: dict of numpy arrays ts, o, h, l, c, ct (15m frame, sorted). trade: dict with type, entry_price, stop, target, risk,
    scan_start. minute: MinuteCache or None. incomplete_days: {date: missing slots}. daily_hl: {date: (high, low)}.
    data_end: last close_time in the data (default: last 15m close_time).
    """
    demand = trade["type"] == "demand"
    entry, stop, target = float(trade["entry_price"]), float(trade["stop"]), float(trade["target"])
    risk = abs(entry - stop)
    sign = 1.0 if demand else -1.0
    scan = np.datetime64(pd.Timestamp(trade["scan_start"]))
    hz_end = np.datetime64(pd.Timestamp(trade["scan_start"]).normalize() + pd.Timedelta(days=horizon_days))
    ts, o, h, l, c, ct = (bars15[k] for k in ("ts", "o", "h", "l", "c", "ct"))
    data_end = np.datetime64(pd.Timestamp(data_end)) if data_end is not None else (ct[-1] if len(ct) else scan)
    inc = incomplete_days or {}
    res = dict(outcome=None, reason="", decided_interval="15minute", fill_time=None, fill_price=None, gap_fill=False,
               exit_time=None, exit_price=None, r=None, mtm_r=None, minute_used=False)
    st = _State()
    a = int(np.searchsorted(ts, scan, side="left"))
    b = int(np.searchsorted(ts, hz_end, side="left"))

    def done(label, t, px, detail, interval="15minute"):
        res.update(outcome=label, reason=detail, exit_time=pd.Timestamp(t) if t is not None else None, exit_price=px,
                   decided_interval=interval, fill_time=pd.Timestamp(st.fill_time) if st.fill_time is not None else None,
                   fill_price=st.fill, gap_fill=st.gap)
        if label in (WIN, LOSS) and px is not None:
            res["r"] = sign * (px - st.fill) / risk
        return res

    def gap_check(day):
        """End of a day with missing 15m bars and no event in the bars we have: the daily bar shows whether the missing part
        reached a level the trade was waiting for (entry if unfilled; stop or target if filled)."""
        if day not in inc or daily_hl is None or day not in daily_hl:
            return False
        dh, dl = daily_hl[day]
        if not st.filled:
            return (dl <= entry) if demand else (dh >= entry)
        return (dl <= stop or dh >= target) if demand else (dh >= stop or dl <= target)

    k = a
    while k < b:
        day = pd.Timestamp(ts[k]).normalize()
        was_filled = st.filled
        r = _bar(st, o[k], h[k], l[k], ts[k], demand, entry, stop, target, final=False)
        if r is not None and r[0] == _DRILL:
            m = None if minute is None else minute.bars(ts[k], ts[k] + np.timedelta64(15, "m"))
            if m is None:
                return done(AMBIGUOUS, ts[k], None, f"MINUTE_NOT_CACHED ({r[3]})")
            mts, mo, mh, ml, _ = m
            if mh.max() < h[k] - 1e-9 or ml.min() > l[k] + 1e-9:
                return done(AMBIGUOUS, ts[k], None, f"MINUTE_INCOMPLETE ({r[3]})")
            # re-run this 15m bar at 1 minute from the state it started with
            if not was_filled:
                st = _State()
            res["minute_used"] = True
            rr = None
            for j in range(len(mts)):
                rr = _bar(st, mo[j], mh[j], ml[j], mts[j], demand, entry, stop, target, final=True)
                if rr is not None:
                    break
            if rr is not None:
                return done(rr[0], rr[1], rr[2], rr[3], "1minute")
            r = None
        elif r is not None:
            return done(*r)
        # end of day: incomplete-data check
        last_of_day = (k + 1 >= b) or (pd.Timestamp(ts[k + 1]).normalize() != day)
        if last_of_day and gap_check(day):
            return done(AMBIGUOUS, ts[k], None, "INTRADAY_DATA_GAP")
        k += 1
    # loop ended without a terminal event
    horizon_complete = b < len(ts) or data_end >= hz_end
    if not st.filled:
        if horizon_complete:
            return done(NOFILL, None, None, "entry never traded within horizon")
        return done(CENSORED, None, None, "data ends before horizon, not filled")
    if horizon_complete:
        res.update(outcome=OPEN, reason="no stop/target within horizon", fill_time=pd.Timestamp(st.fill_time),
                   fill_price=st.fill, gap_fill=st.gap, mtm_r=sign * (c[b - 1] - st.fill) / risk)
        return res
    res.update(outcome=CENSORED, reason="data ends before horizon", fill_time=pd.Timestamp(st.fill_time),
               fill_price=st.fill, gap_fill=st.gap, mtm_r=sign * (c[b - 1] - st.fill) / risk)
    return res


def arrays(df15):
    """numpy view of a 15m frame for replay()."""
    return dict(ts=df15["timestamp"].to_numpy(dtype="datetime64[ns]"), o=df15["open"].to_numpy(dtype=float),
                h=df15["high"].to_numpy(dtype=float), l=df15["low"].to_numpy(dtype=float),
                c=df15["close"].to_numpy(dtype=float), ct=df15["close_time"].to_numpy(dtype="datetime64[ns]"))
