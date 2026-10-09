"""Read-only HTTP API for the frontend.

Kite access goes through src/kite_client.KiteReadOnly, which only exposes instruments() and historical_data()
(CLAUDE.md: never place, modify or read orders, positions or holdings). The access token stays on this server; the browser
never sees it, and no endpoint returns it.

Run from the repo root:  uvicorn api.main:app --port 8000
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI(title="IPD Trading API", docs_url="/api/docs", openapi_url="/api/openapi.json")

INTERVALS = {"15m": "15minute", "60m": "60minute", "1d": "day"}
MAX_DAYS = {"15m": 200, "60m": 400, "1d": 2000}
EPOCH = pd.Timestamp("1970-01-01")


class KiteUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def _kite():
    """One shared read-only client. Any login/import problem becomes KiteUnavailable (HTTP 503), never a crash."""
    try:
        from src.kite_client import KiteReadOnly
        return KiteReadOnly()
    except SystemExit as e:  # KiteReadOnly exits with "run kite_login.py" when the key/token is missing or expired
        raise KiteUnavailable("Kite is not logged in. Run kite_login.py, then restart the API.") from e
    except ImportError as e:
        raise KiteUnavailable(f"Kite dependencies are missing: {e.name}") from e


def _kite_or_503():
    try:
        return _kite()
    except KiteUnavailable as e:
        _kite.cache_clear()
        raise HTTPException(status_code=503, detail=str(e)) from e


@lru_cache(maxsize=1)
def _nse_equities(day: str) -> pd.DataFrame:
    df = _kite_or_503().instruments("NSE")
    df = df[(df["instrument_type"] == "EQ") & (df["segment"] == "NSE")]
    return df[["tradingsymbol", "name", "instrument_token"]].reset_index(drop=True)


@app.get("/api/health")
def health():
    try:
        _kite()
        return {"ok": True, "kite": True}
    except KiteUnavailable as e:
        _kite.cache_clear()
        return {"ok": True, "kite": False, "detail": str(e)}


@app.get("/api/symbols")
def symbols(q: str = Query("", max_length=20), limit: int = Query(15, ge=1, le=50)):
    df = _nse_equities(f"{datetime.now():%Y%m%d}")
    q = q.strip().upper()
    if q:
        hit = df[df["tradingsymbol"].str.upper().str.startswith(q)]
        if len(hit) < limit:
            more = df[df["tradingsymbol"].str.upper().str.contains(q, regex=False) & ~df.index.isin(hit.index)]
            hit = pd.concat([hit, more])
    else:
        hit = df
    return [{"symbol": r.tradingsymbol, "name": r.name} for r in hit.head(limit).itertuples()]


@app.get("/api/candles")
def candles(symbol: str = Query(..., max_length=30), interval: str = Query("15m"), days: int = Query(30, ge=1)):
    if interval not in INTERVALS:
        raise HTTPException(status_code=400, detail=f"interval must be one of {sorted(INTERVALS)}")
    days = min(days, MAX_DAYS[interval])
    df = _nse_equities(f"{datetime.now():%Y%m%d}")
    row = df[df["tradingsymbol"].str.upper() == symbol.strip().upper()]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"{symbol} is not an NSE equity")
    now = datetime.now()
    # Round `to` so repeated calls hit the disk cache (its file name contains the range) without serving stale intraday bars.
    to_dt = now.replace(hour=23, minute=59, second=59, microsecond=0) if interval == "1d" else now.replace(
        minute=now.minute - now.minute % 15, second=0, microsecond=0)
    from_dt = (to_dt - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        bars = _kite_or_503().historical_data(int(row.iloc[0]["instrument_token"]), from_dt, to_dt, INTERVALS[interval],
                                              symbol=row.iloc[0]["tradingsymbol"])
    except HTTPException:
        raise
    except Exception as e:  # Kite refused the range or is rate limited; report, don't crash
        raise HTTPException(status_code=502, detail=f"Kite error: {type(e).__name__}") from e
    t = ((pd.to_datetime(bars["timestamp"]) - EPOCH) // pd.Timedelta("1s")).astype(int)
    return {
        "symbol": row.iloc[0]["tradingsymbol"],
        "interval": interval,
        "candles": [
            {"time": int(ts), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": int(v)}
            for ts, o, h, l, c, v in zip(t, bars["open"], bars["high"], bars["low"], bars["close"], bars["volume"])
        ],
    }


_COLS = {
    "ticker": ("ticker",),
    "type": ("type",),
    "entry_time": ("entry_time",),
    "entry_price": ("entry_price",),
    "stop": ("stop",),
    "target": ("target",),
    "outcome": ("outcome_final", "outcome"),
    "r": ("r_final", "r_gross", "r"),
}


@app.get("/api/trades")
def trades(combo: str = Query("dit15", pattern="^(dit15|wit|mit)$"), limit: int = Query(300, ge=1, le=2000)):
    """Trade lists from results/**/*.csv written by the backtest scripts. Empty list (not an error) when none exist."""
    files = sorted((ROOT / "results").glob(f"**/*{combo}*final*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"combo": combo, "source": None, "rows": [], "error": None}
    try:
        df = pd.read_csv(files[0])
        if df.empty:
            return {"combo": combo, "source": files[0].name, "rows": [], "error": "The trade file is empty."}
        out = pd.DataFrame({k: next((df[c] for c in cands if c in df.columns), None) for k, cands in _COLS.items()})
        out = out.dropna(axis=1, how="all")
        if out.empty:
            return {"combo": combo, "source": files[0].name, "rows": [],
                    "error": "The trade file has none of the expected columns (ticker, type, entry_time, entry_price, stop, target, outcome)."}
        if "entry_time" in out.columns:
            out = out.sort_values("entry_time", ascending=False)
        out = out.head(limit).astype(object)
        out = out.where(out.notna(), None)
        return {"combo": combo, "source": files[0].name, "rows": out.to_dict("records"), "error": None}
    except Exception as e:  # unreadable or malformed file: report it, never a 500
        return {"combo": combo, "source": files[0].name, "rows": [], "error": f"Could not read {files[0].name}: {type(e).__name__}"}
