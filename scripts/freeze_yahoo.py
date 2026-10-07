"""Freeze Yahoo bars for the WIT/MIT universe into data/cache/yahoo/ using the unmodified legacy mtf_zones._fetch.

Fetches per ticker: daily (period max) and 60m (period 730d, the WIT ltf_fetch_period). Resumable: existing files are kept.
Usage: python scripts/freeze_yahoo.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY_CODE = ROOT / "legacy" / "handoff" / "handoff" / "code"
OUT = ROOT / "data" / "cache" / "yahoo"
sys.path.insert(0, str(LEGACY_CODE))
import mtf_zones as mtz  # noqa: E402  (legacy, unmodified)

FETCHES = [("1d", "max"), ("60m", "730d")]  # (interval label, period) exactly as legacy COMBOS wit/mit
RETRIES = 3
PAUSE = 3.0
COLS = ["timestamp", "open", "high", "low", "close"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tickers = json.load(open(LEGACY_CODE / "webapp" / "universe_live.json"))["tickers"]
    man_path = OUT / "MANIFEST.csv"
    manifest = {}
    if man_path.exists():
        for r in pd.read_csv(man_path).itertuples():
            manifest[(r.ticker, r.interval)] = r._asdict()
    failed = []
    for i, t in enumerate(tickers, 1):
        for interval, period in FETCHES:
            path = OUT / f"{t}__{interval}.csv"
            if path.exists() and (t, interval) in manifest:
                continue
            df = None
            for attempt in range(RETRIES):
                mtz._fetch_cache.pop((t, period, interval), None)
                try:
                    df = mtz._fetch(t, period, interval)
                except Exception:
                    df = None
                if df is not None and len(df):
                    break
                time.sleep(PAUSE)
            if df is None or df.empty:
                failed.append((t, interval))
                continue
            df[COLS].to_csv(path, index=False)
            manifest[(t, interval)] = dict(ticker=t, interval=interval, first=df["timestamp"].min(),
                                           last=df["timestamp"].max(), rows=len(df),
                                           fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if i % 25 == 0:
            print(f"{i}/{len(tickers)} done, failed so far {len(failed)}", flush=True)
            pd.DataFrame(list(manifest.values()))[["ticker", "interval", "first", "last", "rows", "fetched_at"]].to_csv(man_path, index=False)
    pd.DataFrame(list(manifest.values()))[["ticker", "interval", "first", "last", "rows", "fetched_at"]].to_csv(man_path, index=False)
    print(f"DONE tickers={len(tickers)} files={len(manifest)} failed={len(failed)}")
    for t, iv in failed:
        print(f"FAILED {t} {iv}")


if __name__ == "__main__":
    main()
