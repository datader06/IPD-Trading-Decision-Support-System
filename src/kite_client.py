"""Read-only Kite Connect client: instruments() and historical_data() only, with rate limit, retry and disk cache."""
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from kiteconnect import KiteConnect
from kiteconnect import exceptions as kex

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "kite"

# Documented limits.
# Rate: "Historical candle: 3req/second"
#   source: https://kite.trade/docs/connect/v3/exceptions/ (rate limit table); HTTP 429 = rate limited.
MAX_REQUESTS_PER_SECOND = 3
# Verified 2026-10-02: a 200-day 15minute request (2023-01-01 .. 2023-07-20) is accepted.
# Max days per request, Kite staff (sujith) post Jan 2018, edited May 2020, "All intervals are in days":
#   https://kite.trade/forum/discussion/3105/historical-api-frequency-and-limit-on-number-of-candles-fetched
MAX_DAYS_PER_REQUEST = {
    "minute": 60,
    "3minute": 100,
    "5minute": 100,
    "10minute": 100,
    "15minute": 200,
    "30minute": 200,
    "60minute": 400,
    "day": 2000,
}
# Token expiry/invalidation = TokenException with HTTP 403 (same docs page as above).

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1.0
_FMT = "%Y-%m-%d %H:%M:%S"
_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


def cache_path(symbol, interval, from_dt, to_dt):
    name = re.sub(r"[^A-Za-z0-9_&-]", "_", str(symbol))
    return CACHE_DIR / name / interval / f"{from_dt:%Y%m%d%H%M}_{to_dt:%Y%m%d%H%M}.csv"


class KiteReadOnly:
    def __init__(self):
        load_dotenv(ROOT / ".env")
        api_key = os.getenv("KITE_API_KEY")
        token = os.getenv("KITE_ACCESS_TOKEN")
        if not api_key or not token:
            sys.exit("run kite_login.py")
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(token)
        self._last_call = 0.0

    # ---- internals -------------------------------------------------
    def _throttle(self):
        gap = 1.0 / MAX_REQUESTS_PER_SECOND
        wait = self._last_call + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _call(self, fn, *args, **kwargs):
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            try:
                return fn(*args, **kwargs)
            except kex.TokenException:
                sys.exit("run kite_login.py")
            except (requests.exceptions.RequestException, kex.KiteException) as e:
                code = getattr(e, "code", None)
                retryable = isinstance(e, requests.exceptions.RequestException) or code == 429 or (
                    isinstance(code, int) and code >= 500
                )
                if not retryable or attempt == MAX_RETRIES:
                    raise
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))

    def _fetch_chunk(self, token, start, end, interval):
        """One request; if Kite rejects the range as too long, halve it and retry."""
        try:
            return self._call(self._kite.historical_data, token, start.strftime(_FMT), end.strftime(_FMT), interval)
        except kex.InputException as e:
            if (end - start) > timedelta(days=1) and re.search(r"limit|exceed|too long|days", str(e), re.I):
                mid = start + (end - start) / 2
                return (self._fetch_chunk(token, start, mid, interval)
                        + self._fetch_chunk(token, mid + timedelta(seconds=1), end, interval))
            raise

    # ---- public API ------------------------------------------------
    def instruments(self, exchange):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"instruments_{exchange}_{datetime.now():%Y%m%d}.csv"
        if path.exists():
            return pd.read_csv(path)
        df = pd.DataFrame(self._call(self._kite.instruments, exchange))
        df.to_csv(path, index=False)
        return df

    def historical_data(self, instrument_token, from_dt, to_dt, interval, symbol=None):
        """Naive IST wall-clock OHLCV. `symbol` is used only for the cache folder name."""
        if interval not in MAX_DAYS_PER_REQUEST:
            raise ValueError(f"unsupported interval {interval}")
        path = cache_path(symbol or instrument_token, interval, from_dt, to_dt)
        if path.exists():
            return pd.read_csv(path, parse_dates=["timestamp"])
        step = timedelta(days=MAX_DAYS_PER_REQUEST[interval])
        rows, start = [], from_dt
        while start < to_dt:
            end = min(start + step, to_dt)
            rows += self._fetch_chunk(instrument_token, start, end, interval)
            start = end + timedelta(seconds=1)
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["timestamp"] = [d.replace(tzinfo=None) for d in df["date"]]
        df = df[_COLS].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
