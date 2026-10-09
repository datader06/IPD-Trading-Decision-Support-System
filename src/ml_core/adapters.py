"""Adapter for the final-algorithm ML export (data/algo_v5/ml_dataset_baseline_v5.csv) -> the ml_core standard frame.

Standard frame columns: row_id, strategy, ticker, type, entry_time, exit_time, label (1 win / 0 loss), r_gross, split, plus FEATURE_COLUMNS.
Every feature is either a column of the export (known at entry) or computed from daily bars dated before the entry date and NIFTY daily.
No outcome, exit or label column is ever a feature.
"""
import hashlib
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml import features as F  # noqa: E402
from ml_core import dataset as D  # noqa: E402

DEFAULT_PATH = ROOT / "data" / "algo_v5" / "ml_dataset_baseline_v5.csv"
VERSION = "algo-v5-features-v1"
FILE_FEATURES = ["ltf_risk_pct", "htf_risk_pct", "overlap_frac", "trend_strength_atr", "htf_strong_legout", "ltf_strong_legout",
                 "legout_exciting_candles", "legout_gap", "legout_strength_score", "ltf_base_count", "htf_base_count",
                 "time_at_base_score", "ema_all"]
FEATURE_COLUMNS = FILE_FEATURES + ["ema_count", "type_demand", "strat_wit", "strat_mit", "risk_atr_d", "stock_rs63",
                                   "nifty_above_200dma", "log_htf_age_days"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _daily_features(row, td):
    """(risk_atr_d, stock_rs63, nifty_above_200dma) from D-1 daily data, or (None, reason)."""
    t = pd.Timestamp(row["entry_time"])
    j = F.asof.daily_index_asof(td["dates"], t)
    if j < F.RS_BARS:
        return None, "warmup_stock_lt_63_prior_daily_bars"
    k = F.asof.daily_index_asof(td["n_dates"], t)
    if k < max(F.DMA_BARS - 1, F.RS_BARS):
        return None, "warmup_nifty_insufficient_bars"
    a = td["atr"][j]
    if not (np.isfinite(a) and a > 0):
        return None, "atr_unavailable"
    n, c = td["n_close"], td["close"]
    return (float(row["risk"]) / a, (c[j] / c[j - F.RS_BARS] - 1.0) - (n[k] / n[k - F.RS_BARS] - 1.0),
            float(n[k] > n[k - F.DMA_BARS + 1:k + 1].mean())), None


def load_baseline_v5(path=DEFAULT_PATH):
    """Returns (standard frame, exclusions DataFrame, manifest dict)."""
    raw = pd.read_csv(path, parse_dates=["entry_time", "after_entry_exit_time"])
    nifty = F.load_nifty()
    ema = [c for c in raw.columns if c.startswith("ema_") and c != "ema_all"]
    tds, rows, excl = {}, [], []
    for r in raw.to_dict("records"):
        tk = r["ticker"]
        if tk not in tds:
            tds[tk] = D._td(tk, nifty)
        if tds[tk] is None:
            excl.append(dict(ticker=tk, entry_time=r["entry_time"], reason="no_frames_for_ticker"))
            continue
        day, why = _daily_features(r, tds[tk])
        if why:
            excl.append(dict(ticker=tk, entry_time=r["entry_time"], reason=why))
            continue
        rec = dict(row_id=f"{r['combo']}|{tk}|{r['type']}|{pd.Timestamp(r['entry_time']):%Y%m%d%H%M}|{r['entry_price']:.4f}",
                   strategy=r["combo"], ticker=tk, type=r["type"], entry_time=r["entry_time"], exit_time=r["after_entry_exit_time"],
                   label=int(r["label_win"]), r_gross=float(r["label_R"]), split=r["split"], htf_key=f"{r['combo']}:{tk}:{r['htf_formed_at']}")
        for c in FILE_FEATURES:
            v = r[c]
            rec[c] = 0.0 if pd.isna(v) else float(v)  # one missing base count each: documented constant 0
        rec["ema_count"] = float(sum(bool(r[c]) for c in ema))
        rec["type_demand"] = float(r["type"] == "demand")
        rec["strat_wit"], rec["strat_mit"] = float(r["combo"] == "WIT"), float(r["combo"] == "MIT")
        rec["risk_atr_d"], rec["stock_rs63"], rec["nifty_above_200dma"] = day
        rec["log_htf_age_days"] = math.log1p(max((pd.Timestamp(r["entry_time"]) - pd.Timestamp(r["htf_formed_at"])) / pd.Timedelta(days=1), 0.0))
        rows.append(rec)
    df = pd.DataFrame(rows).sort_values(["entry_time", "strategy", "ticker"], kind="mergesort").reset_index(drop=True)
    manifest = dict(source=str(Path(path).relative_to(ROOT)), sha256=sha256(path), rows_in_file=len(raw), rows_used=len(df),
                    rows_by_strategy=df["strategy"].value_counts().to_dict(), rows_by_split=df["split"].value_counts().to_dict(),
                    feature_version=VERSION, feature_columns=FEATURE_COLUMNS)
    return df, pd.DataFrame(excl), manifest
