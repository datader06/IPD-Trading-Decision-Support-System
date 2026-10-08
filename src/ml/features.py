"""Phase B Tier-1 feature extraction (frozen registry: src/ml/registry.py). No labels, models or validation code here.

Point-in-time rules (the entry bar's own OHLC is NEVER read):
  * 15m data: only bars with row position < entry_idx, where entry_idx = position of entry_time in the 15m frame
    (searchsorted). The frame is only used for its timestamp at entry_idx, never its prices.
  * LTF zone data: bars at positions <= ltf leg_end (< entry_idx, checked).
  * Daily data: only bars dated strictly before the entry date (asof.daily_index_asof, intraday mode) = D-1.
  * HTF zone data: bars at positions <= htf leg_end, which must be <= D-1 (checked).
  * NIFTY: same D-1 rule, own 63 / 200 prior bars.
ATR is the legacy causal Wilder ATR (sd_zones.wilder_atr): the value at position p uses bars <= p only, so truncating
later data does not change it (tested).

Row selection (Phase A pool definition) is in select_pool; per-row feature failures return an exclusion reason instead of
imputing: the exclusion log lists every excluded row with its exact reason.
"""
import ast
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT / "src"), str(ROOT / "legacy" / "handoff" / "handoff" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import asof  # noqa: E402
import bars as B  # noqa: E402
import corp_actions as CA  # noqa: E402
import costs  # noqa: E402
import sd_zones as sz  # noqa: E402
from ml import registry as R  # noqa: E402

FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
NIFTY_DIR = ROOT / "data" / "cache" / "kite" / "NIFTY50" / "day"
ENTRY_FROM = pd.Timestamp("2021-01-01")
ORDER_KEY = ["ticker", "type", "entry_time", "entry_price", "stop"]
RS_BARS = 63
DMA_BARS = 200
APPROACH_BARS = 8
COST = costs.round_trip("rt0.20", 0.20)

# exclusion reasons (exact strings used in the log)
EX_NOT_POOL = "not_in_pool"
EX_BEFORE_2021 = "entry_before_2021-01-01"
EX_PHASE_A_CA = "phase_a_corporate_action_excluded"
EX_DUP = "duplicate_order"
EX_NO_FRAME = "no_frames_for_ticker"
EX_ENTRY_NOT_IN_FRAME = "entry_time_not_in_15m_frame"
EX_KEY_MISMATCH = "zone_key_close_time_mismatch"
EX_ENTRY_BEFORE_LEG = "entry_not_after_ltf_leg_end"
EX_HTF_AFTER_D1 = "htf_leg_end_after_D-1"
EX_WARMUP_15M = "warmup_15m_lt_9_bars"
EX_ATR = "atr_unavailable"
EX_NO_D1 = "no_daily_bar_before_entry_date"
EX_WARMUP_STOCK = "warmup_stock_lt_63_prior_daily_bars"
EX_WARMUP_NIFTY = "warmup_nifty_insufficient_bars"
EX_CA_63 = "corporate_action_in_63d_lookback"
EX_TREND = "trend_state_missing"


def load_nifty(nifty_dir=NIFTY_DIR):
    files = sorted(Path(nifty_dir).glob("*.csv"))
    df = pd.concat([pd.read_csv(f, parse_dates=["timestamp"]) for f in files], ignore_index=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)[["timestamp", "close"]]


def _parse_key(k):
    return tuple(ast.literal_eval(k)) if isinstance(k, str) else tuple(k)


class TickerData:
    """Arrays for one ticker. ATR arrays can be injected (tests); otherwise computed with the legacy causal Wilder ATR."""

    def __init__(self, d1, m15, nifty, atr_d=None, atr15=None):
        self.d_dates = pd.to_datetime(d1["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
        self.d_close = d1["close"].to_numpy(dtype=float)
        self.d_close_time = d1["close_time"].to_numpy(dtype="datetime64[ns]") if "close_time" in d1 else None
        self.atr_d = (np.asarray(atr_d, dtype=float) if atr_d is not None
                      else sz.wilder_atr(d1.reset_index(drop=True)).to_numpy(dtype=float))
        self.m_ts = m15["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.m_open = m15["open"].to_numpy(dtype=float)
        self.m_close = m15["close"].to_numpy(dtype=float)
        self.m_close_time = m15["close_time"].to_numpy(dtype="datetime64[ns]") if "close_time" in m15 else None
        self.atr15 = (np.asarray(atr15, dtype=float) if atr15 is not None
                      else sz.wilder_atr(m15.reset_index(drop=True)).to_numpy(dtype=float))
        self.n_dates = pd.to_datetime(nifty["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]")
        self.n_close = nifty["close"].to_numpy(dtype=float)
        self.ca = CA.flag_days(d1)

    @classmethod
    def from_ticker(cls, ticker, nifty, frames_dir=FRAMES):
        d1 = B.load_frame(frames_dir, ticker, "1d")
        m15 = B.load_frame(frames_dir, ticker, "15m")
        if d1.empty or m15.empty:
            return None
        return cls(d1, m15, nifty)


def compute_features(row, td, check_keys=True, require_entry_bar=True):
    """Tier-1 features for one candidate row (dict-like). Returns (features dict | None, exclusion reason | None).
    Reads only data at positions / dates allowed by the module docstring. require_entry_bar=False lets the leakage tests
    pass frames truncated BEFORE the entry bar (entry_idx is then just the frame length); production always requires it."""
    t = pd.Timestamp(row["entry_time"])
    t64 = np.datetime64(t)
    i = int(np.searchsorted(td.m_ts, t64, side="left"))  # entry bar position; its prices are never read
    lk, hk = _parse_key(row["ltf_key"]), _parse_key(row["htf_key"])
    ls, le, he = lk[2], lk[3], hk[3]
    if require_entry_bar and (i >= len(td.m_ts) or td.m_ts[i] != t64):
        return None, EX_ENTRY_NOT_IN_FRAME
    if check_keys and td.m_close_time is not None and td.d_close_time is not None:
        if (td.m_close_time[le] != np.datetime64(pd.Timestamp(row["T_L"]))
                or td.d_close_time[he] != np.datetime64(pd.Timestamp(row["T_H"]))):
            return None, EX_KEY_MISMATCH
    if i <= le:
        return None, EX_ENTRY_BEFORE_LEG
    if i < APPROACH_BARS + 1:
        return None, EX_WARMUP_15M
    j = asof.daily_index_asof(td.d_dates, t)  # D-1
    if j < 0:
        return None, EX_NO_D1
    if he > j:
        return None, EX_HTF_AFTER_D1
    a15_leg, a15_prev, ad_he, ad_j = td.atr15[le], td.atr15[i - 1], td.atr_d[he], td.atr_d[j]
    if not all(np.isfinite(x) and x > 0 for x in (a15_leg, a15_prev, ad_he, ad_j)):
        return None, EX_ATR
    if j < RS_BARS:
        return None, EX_WARMUP_STOCK
    k = asof.daily_index_asof(td.n_dates, t)
    if k < max(DMA_BARS - 1, RS_BARS):
        return None, EX_WARMUP_NIFTY
    if CA.window_has_flag(td.ca, pd.Timestamp(td.d_dates[j - RS_BARS]), pd.Timestamp(td.d_dates[j])):
        return None, EX_CA_63
    state = row["trend_entry"]
    if state not in ("up", "down", "sideways"):
        return None, EX_TREND

    demand = row["type"] == "demand"
    prox, dist = float(row["htf_proximal"]), float(row["htf_distal"])
    entry, risk = float(row["entry_price"]), float(row["risk"])
    body = np.abs(td.m_close[ls:le + 1] - td.m_open[ls:le + 1]).sum()
    move = td.m_close[i - 1] - td.m_close[i - 1 - APPROACH_BARS]
    f = {
        "ltf_base_count": float(row["ltf_base_count"]),
        "htf_base_count": float(row["htf_base_count"]),
        "htf_strong_legout": float(bool(row["htf_strong_legout"])),
        "ltf_leg_body_atr": body / a15_leg,
        "htf_zone_width_atr": abs(prox - dist) / ad_he,
        "overlap_frac": float(row["overlap_frac"]),
        "ltf_pos_in_htf": (entry - dist) / (prox - dist),
        "wick_fresh_fail": float(bool(row["wick_fresh_fail"])),
        "log_ltf_age_bars": math.log(i - le),
        "trend_up": float(state == "up"),
        "trend_down": float(state == "down"),
        "risk_atr_d": risk / ad_j,
        "approach_speed_atr": (-move if demand else move) / a15_prev,
        "cost_in_r_rt0.20": COST.cost_r(entry, entry, risk),
        "type_demand": float(demand),
        "nifty_above_200dma": float(td.n_close[k] > td.n_close[k - DMA_BARS + 1:k + 1].mean()),
        "stock_rs63": (td.d_close[j] / td.d_close[j - RS_BARS] - 1.0) - (td.n_close[k] / td.n_close[k - RS_BARS] - 1.0),
        "is_0915_bar": float(t.hour == 9 and t.minute == 15),
    }
    return {c: f[c] for c in R.MODEL_COLUMNS}, None


def _log_row(r, reason, stage):
    return dict(ticker=r["ticker"], type=r["type"], entry_time=r["entry_time"], entry_price=r["entry_price"], stop=r["stop"],
                htf_formed_at=r["htf_formed_at"], reason=reason, stage=stage)


def select_pool(df, entry_from=ENTRY_FROM):
    """Phase A pool definition applied in a fixed order. Returns (pool DataFrame, exclusion log DataFrame)."""
    df = df.copy()
    log = []

    def drop(frame, mask, reason):
        for r in frame[mask].to_dict("records"):
            log.append(_log_row(r, reason, "pool"))
        return frame[~mask]

    df = drop(df, ~(df["relaxed_selected"].astype(bool) | df["is_b0"].astype(bool)), EX_NOT_POOL)
    df = drop(df, df["entry_time"] < entry_from, EX_BEFORE_2021)
    df = drop(df, df["ca_excluded"].astype(bool), EX_PHASE_A_CA)
    df = df.sort_values(["entry_time", "ticker", "htf_formed_at", "type"], kind="mergesort")
    df = drop(df, df.duplicated(ORDER_KEY, keep="first"), EX_DUP)
    return df.reset_index(drop=True), pd.DataFrame(log)


def row_id(r):
    return (f"{r['ticker']}|{r['type']}|{pd.Timestamp(r['entry_time']):%Y%m%d%H%M}|"
            f"{float(r['entry_price']):.4f}|{float(r['stop']):.4f}")


META_FROM_CANDIDATES = ("trend_htf_fail", "trend_entry_fail", "htf_strict_fail", "htf_cap_fail", "ltf_cap_fail", "entry_price",
                        "stop", "target", "risk", "shares", "outcome", "exit_reason", "decided_interval", "fill_time",
                        "fill_price", "exit_time", "exit_price", "r_gross", "mtm_r")


def build_ticker(ticker, rows, td):
    """rows: DataFrame of one ticker's pool rows. Returns (dataset dict list, exclusion dict list)."""
    out, ex = [], []
    for r in rows.to_dict("records"):
        if td is None:
            ex.append(_log_row(r, EX_NO_FRAME, "features"))
            continue
        feats, reason = compute_features(r, td)
        if reason:
            ex.append(_log_row(r, reason, "features"))
            continue
        rec = {
            "row_id": row_id(r), "ticker": r["ticker"], "type": r["type"], "htf_key": r["htf_key"], "ltf_key": r["ltf_key"],
            "entry_time": r["entry_time"], "T_L": r["T_L"], "T_H": r["T_H"], "htf_formed_at": r["htf_formed_at"],
            "ltf_formed_at": r["ltf_formed_at"], "trend_entry_state": r["trend_entry"], "is_b0": r["is_b0"],
            "relaxed_selected": r["relaxed_selected"],
        }
        for c in META_FROM_CANDIDATES:
            rec[c] = r[c]
        rec.update(feats)
        out.append(rec)
    return out, ex
