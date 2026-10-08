"""Common replay helpers shared by Phase A (candidates_mtf, comparison scripts) and Phase B (src/ml/labels.py).

Moved here unchanged from src/ml/labels.py so that Phase A code does not depend on the ML package. Nothing in this file is
ML-specific: it builds the inputs of src/replay.replay for one ticker, replays one candidate row exactly as
candidates._replay_all does (15m replay first, then the cached 1-minute drill-down only for MINUTE_NOT_CACHED bars), and compares
a fresh replay with the stored Phase A fields.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import bars as B  # noqa: E402
import replay as RP  # noqa: E402


class ReplayContext:
    """Frames-derived inputs of src/replay.replay for one ticker (same construction as candidates._replay_all)."""

    def __init__(self, ticker, d1, m15, minute_factory=None):
        self.ticker = ticker
        self.arr = RP.arrays(m15)
        self.inc = B.intraday_incomplete_days(m15, d1)
        self.dhl = {pd.Timestamp(t).normalize(): (h, l) for t, h, l in zip(d1["timestamp"], d1["high"], d1["low"])}
        self.data_end = m15["close_time"].to_numpy(dtype="datetime64[ns]")[-1]
        self._minute_factory = minute_factory or (lambda: RP.MinuteCache(ticker))
        self._minute = None

    def minute(self):
        if self._minute is None:
            self._minute = self._minute_factory()
        return self._minute


def replay_row(row, ctx):
    """Replay one candidate exactly as Phase A does: first without minute data, then (only for MINUTE_NOT_CACHED) with it."""
    tr = dict(type=row["type"], entry_price=row["entry_price"], stop=row["stop"], target=row["target"], risk=row["risk"],
              scan_start=pd.Timestamp(row["entry_time"]))
    res = RP.replay(ctx.arr, tr, minute=None, incomplete_days=ctx.inc, daily_hl=ctx.dhl, data_end=ctx.data_end)
    if res["outcome"] == RP.AMBIGUOUS and res["reason"].startswith("MINUTE_NOT_CACHED"):
        res = RP.replay(ctx.arr, tr, minute=ctx.minute(), incomplete_days=ctx.inc, daily_hl=ctx.dhl, data_end=ctx.data_end)
    return res


def _same(a, b, rtol=1e-9):
    if a is None or (isinstance(a, float) and np.isnan(a)) or a is pd.NaT:
        return b is None or (isinstance(b, float) and np.isnan(b)) or b is pd.NaT
    if b is None or (isinstance(b, float) and np.isnan(b)) or b is pd.NaT:
        return False
    if isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
        return bool(np.isclose(float(a), float(b), rtol=rtol, atol=1e-12))
    return a == b


def check_row(row, res):
    """'match' if the fresh replay equals the stored Phase A fields, else 'mismatch:<fields>'."""
    pairs = {
        "outcome": (row["outcome"], res["outcome"]),
        "reason": ("" if pd.isna(row["exit_reason"]) else row["exit_reason"], res["reason"] or ""),
        "interval": (row["decided_interval"], res["decided_interval"]),
        "fill_time": (row["fill_time"], res["fill_time"]),
        "fill_price": (row["fill_price"], res["fill_price"]),
        "exit_time": (row["exit_time"], res["exit_time"]),
        "exit_price": (row["exit_price"], res["exit_price"]),
        "r": (row["r_gross"], res["r"]),
        "mtm_r": (row["mtm_r"], res["mtm_r"]),
    }
    bad = [k for k, (a, b) in pairs.items() if not _same(a, b)]
    return "match" if not bad else "mismatch:" + ",".join(bad)
