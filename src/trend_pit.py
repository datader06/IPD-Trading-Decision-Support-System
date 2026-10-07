"""Point-in-time trend (Phase A, A1/A3/A6). Same rule as legacy mtf_zones._compute_trend_events /
_classify_trend_from_events (RULES R11); only WHEN information is known changes.

Legacy timing problems fixed here:
  - a zone-break event was stamped with the breaking bar's LABEL (its start); it is now stamped with the bar's close_time;
  - the query used `trend_df.timestamp <= query`, which includes a bar that is still forming; it now uses close_time <= query;
  - the all-time-high override compared against the max close of the (possibly trimmed) trend frame; it now compares against
    every close known by the query time: closed trend bars plus daily closes (daily history from 2012) (A3);
  - optional reset at a flagged corporate-action day (src/corp_actions.py): prices before that day are not comparable, so trend
    zones whose base starts before it, and closes before it, are ignored for queries after it (A6).
The state machine itself (2 same-direction breaks confirm; 1 opposite break drops to sideways; ATH forces up) is copied unchanged.
"""
import numpy as np
import pandas as pd


class TrendContext:
    """Precomputed trend events for one ticker, queryable at any time T without look-ahead."""

    def __init__(self, trend_df, trend_zones, daily=None, ca_flags=None, ath_full=True, ca_reset=True):
        self.ct = trend_df["close_time"].to_numpy(dtype="datetime64[ns]")
        self.ts = trend_df["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.close = trend_df["close"].to_numpy(dtype=float)
        self.ca = ca_flags if (ca_reset and ca_flags is not None) else np.array([], dtype="datetime64[ns]")
        self.ath_full = ath_full
        if daily is not None and ath_full:
            self.d_ct = daily["close_time"].to_numpy(dtype="datetime64[ns]")
            self.d_day = pd.to_datetime(daily["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
            self.d_close = daily["close"].to_numpy(dtype=float)
        else:
            self.d_ct = None
        # events: (event close_time, direction, base start timestamp of the broken zone)
        ev = []
        for z in trend_zones:
            start = z.leg_end_index + 1
            if start >= len(self.close):
                continue
            seg = self.close[start:]
            hits = np.nonzero(seg < z.distal_line)[0] if z.type == "demand" else np.nonzero(seg > z.distal_line)[0]
            if len(hits) == 0:
                continue
            j = start + int(hits[0])
            ev.append((self.ct[j], "up" if z.type == "supply" else "down", self.ts[z.base_start_index]))
        ev.sort(key=lambda e: e[0])  # stable, like legacy events.sort(key=lambda e: e[0])
        self.ev_time = np.array([e[0] for e in ev], dtype="datetime64[ns]")
        self.ev_dir = [e[1] for e in ev]
        self.ev_base = np.array([e[2] for e in ev], dtype="datetime64[ns]")

    def _reset_point(self, t):
        if len(self.ca) == 0:
            return None
        i = int(np.searchsorted(self.ca, t, side="right")) - 1
        return self.ca[i] if i >= 0 else None

    def ath_at(self, t):
        """True if the last closed trend close at t is >= every close known by t (since the last reset)."""
        t = np.datetime64(pd.Timestamp(t))
        n = int(np.searchsorted(self.ct, t, side="right"))
        if n == 0:
            return None
        lo = 0
        r = self._reset_point(t)
        if r is not None:
            lo = int(np.searchsorted(self.ts, r, side="left"))
        if lo >= n:
            return None
        last = self.close[n - 1]
        ref = self.close[lo:n].max()
        if self.d_ct is not None:
            m = int(np.searchsorted(self.d_ct, t, side="right"))
            dlo = 0 if r is None else int(np.searchsorted(self.d_day, r, side="left"))
            if m > dlo:
                ref = max(ref, self.d_close[dlo:m].max())
        return bool(last >= ref)

    def classify(self, t):
        """'up' / 'sideways' / 'down' at time t using only information closed by t; None if no trend bar has closed."""
        ath = self.ath_at(t)
        if ath is None:
            return None
        if ath:
            return "up"
        t64 = np.datetime64(pd.Timestamp(t))
        r = self._reset_point(t64)
        state, pending_dir, pending_count = "sideways", None, 0
        for k in range(len(self.ev_dir)):
            if self.ev_time[k] > t64:
                break
            if r is not None and (self.ev_time[k] <= r or self.ev_base[k] < r):
                continue
            direction = self.ev_dir[k]
            if state == direction:
                pending_dir, pending_count = None, 0
                continue
            if state == "sideways":
                pending_count = pending_count + 1 if direction == pending_dir else 1
                pending_dir = direction
                if pending_count >= 2:
                    state = direction
                    pending_dir, pending_count = None, 0
            else:
                state = "sideways"
                pending_dir, pending_count = direction, 1
        return state


def blocks(zone_type, trend):
    """Legacy asymmetric filter (R11): demand blocked only by 'down', supply only by 'up'."""
    return (zone_type == "demand" and trend == "down") or (zone_type == "supply" and trend == "up")
