"""Timeframe-agnostic dataset: pooled candidates of several strategies with labels and 'tier2-agnostic-v1' features.

Every feature is computed from the candidates file plus daily bars dated strictly before the entry date (D-1) and the NIFTY daily
series, so it means the same thing for DIT15 (15m entry), WIT (2h) and MIT (daily). Nothing reads the entry bar or later.
The 15m-specific Tier-1 features (leg body, approach speed, 09:15 flag, LTF age in bars, wick-fresh flag) are not used.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml import features as F  # noqa: E402  (frozen Tier-1 module: pool selection, nifty, ids, frames)
from ml import labels as L  # noqa: E402
from ml_core import strategies as ST  # noqa: E402

FEATURE_VERSION = "tier2-agnostic-v1"
FEATURE_COLUMNS = [
    "ltf_base_count", "htf_strong_legout", "ltf_strong_legout", "overlap_frac", "ltf_pos_in_htf",
    "htf_zone_width_atr", "risk_atr_d", "trend_up", "trend_down", "trend_htf_up", "trend_htf_down", "type_demand",
    "cost_in_r_rt0.20", "nifty_above_200dma", "stock_rs63", "log_ltf_age_days", "log_htf_age_days", "strat_wit", "strat_mit",
]
META = ("ticker", "type", "T_L", "T_H", "is_b0", "relaxed_selected", "entry_price", "entry_time",
        "stop", "target", "risk", "outcome", "exit_reason", "fill_time", "fill_price", "exit_time", "exit_price", "r_gross")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _td(ticker, nifty):
    d1 = F.B.load_frame(F.FRAMES, ticker, "1d")
    if d1.empty:
        return None
    return dict(
        dates=pd.to_datetime(d1["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]"),
        close=d1["close"].to_numpy(dtype=float), atr=F.sz.wilder_atr(d1.reset_index(drop=True)).to_numpy(dtype=float),
        ca=F.CA.flag_days(d1),
        n_dates=pd.to_datetime(nifty["timestamp"]).dt.normalize().to_numpy(dtype="datetime64[ns]"),
        n_close=nifty["close"].to_numpy(dtype=float))


def agnostic_features(row, td):
    """(features dict | None, exclusion reason | None) for one candidate row. Uses D-1 daily data only."""
    t = pd.Timestamp(row["entry_time"])
    j = F.asof.daily_index_asof(td["dates"], t)
    if j < 0:
        return None, "no_daily_bar_before_entry_date"
    if j < F.RS_BARS:
        return None, "warmup_stock_lt_63_prior_daily_bars"
    k = F.asof.daily_index_asof(td["n_dates"], t)
    if k < max(F.DMA_BARS - 1, F.RS_BARS):
        return None, "warmup_nifty_insufficient_bars"
    a = td["atr"][j]
    if not (np.isfinite(a) and a > 0):
        return None, "atr_unavailable"
    if F.CA.window_has_flag(td["ca"], pd.Timestamp(td["dates"][j - F.RS_BARS]), pd.Timestamp(td["dates"][j])):
        return None, "corporate_action_in_63d_lookback"
    if row["trend_entry"] not in ("up", "down", "sideways") or row["trend_htf"] not in ("up", "down", "sideways"):
        return None, "trend_state_missing"
    prox, dist = float(row["htf_proximal"]), float(row["htf_distal"])
    entry, risk = float(row["entry_price"]), float(row["risk"])
    n, c = td["n_close"], td["close"]
    day = pd.Timedelta(days=1)
    f = {
        "ltf_base_count": float(row["ltf_base_count"]), 
        "htf_strong_legout": float(bool(row["htf_strong_legout"])), "ltf_strong_legout": float(bool(row["ltf_strong_legout"])),
        "overlap_frac": float(row["overlap_frac"]), "ltf_pos_in_htf": (entry - dist) / (prox - dist),
        "htf_zone_width_atr": abs(prox - dist) / a, "risk_atr_d": risk / a,
        "trend_up": float(row["trend_entry"] == "up"), "trend_down": float(row["trend_entry"] == "down"),
        "trend_htf_up": float(row["trend_htf"] == "up"), "trend_htf_down": float(row["trend_htf"] == "down"),
        "type_demand": float(row["type"] == "demand"), "cost_in_r_rt0.20": F.COST.cost_r(entry, entry, risk),
        "nifty_above_200dma": float(n[k] > n[k - F.DMA_BARS + 1:k + 1].mean()),
        "stock_rs63": (c[j] / c[j - F.RS_BARS] - 1.0) - (n[k] / n[k - F.RS_BARS] - 1.0),
        "log_ltf_age_days": math.log1p(max((t - pd.Timestamp(row["T_L"])) / day, 0.0)),
        "log_htf_age_days": math.log1p(max((t - pd.Timestamp(row["T_H"])) / day, 0.0)),
    }
    return f, None


def build_dataset(sources=None, strategies=ST.STRATEGY_ORDER):
    """Pooled labeled dataset for the given strategies. Returns (DataFrame, manifest dict, exclusions DataFrame)."""
    sources = {**ST.SOURCES, **(sources or {})}
    nifty = F.load_nifty()
    rows, excl, src_info = [], [], {}
    for s in strategies:
        raw = pd.read_csv(sources[s], parse_dates=["entry_time"])
        pool, plog = F.select_pool(raw)
        excl += [dict(r, strategy=s) for r in plog.to_dict("records")]
        tds, n_ok = {}, 0
        for r in pool.to_dict("records"):
            tk = r["ticker"]
            if tk not in tds:
                tds[tk] = _td(tk, nifty)
            td = tds[tk]
            if td is None:
                excl.append(dict(ticker=tk, strategy=s, entry_time=r["entry_time"], reason="no_frames_for_ticker", stage="features"))
                continue
            feats, why = agnostic_features(r, td)
            if why:
                excl.append(dict(ticker=tk, strategy=s, entry_time=r["entry_time"], reason=why, stage="features"))
                continue
            lab, status, is_train = L.label_from_outcome(r["outcome"])
            rec = {m: r.get(m) for m in META}
            rec.update(row_id=f"{s}|{F.row_id(r)}", strategy=s, htf_key=f"{s}:{r['htf_key']}", label=lab, label_status=status,
                       is_training_label=is_train, strat_wit=float(s == "WIT"), strat_mit=float(s == "MIT"))
            rec.update(feats)
            rows.append(rec)
            n_ok += 1
        src_info[s] = dict(path=str(Path(sources[s]).relative_to(ROOT)), sha256=_sha(sources[s]), rows_in_file=len(raw),
                           pool_rows=len(pool), rows_used=n_ok)
    df = pd.DataFrame(rows)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df = df.sort_values(["entry_time", "strategy", "ticker", "row_id"], kind="mergesort").reset_index(drop=True)
    manifest = dict(feature_version=FEATURE_VERSION, feature_columns=FEATURE_COLUMNS, strategies=list(strategies), sources=src_info,
                    rows=len(df), rows_by_strategy=df["strategy"].value_counts().to_dict(),
                    label_counts=df["label_status"].value_counts().to_dict())
    key = {k: v["sha256"] for k, v in src_info.items()}
    key["feature_version"] = FEATURE_VERSION
    manifest["dataset_id"] = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:8]
    return df, manifest, pd.DataFrame(excl)
