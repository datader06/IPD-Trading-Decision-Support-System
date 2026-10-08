"""
offline_loader.py -- lets the unmodified pipeline code run with NO internet.

Usage (from the pack root or anywhere):
    import sys; sys.path.insert(0, "code")
    import offline_loader
    mtz = offline_loader.install()          # patches mtf_zones._fetch to read data/bars/*.csv
    import mtf_backtest as bt
    trades = bt.build_trades_for_ticker("ICICIGI.NS", "wit")

What it does: (1) puts a stub `yfinance` in sys.modules if the real one is missing,
(2) replaces mtf_zones._fetch (the ONLY function that touches the network) with a reader
of data/bars/{TICKER}__{interval}.csv (interval = 1d or 60m; the `period` argument is ignored).
Everything else (_build_frame, resampling, windows, zone detection, matching, exits) is the
original code, untouched. Tickers with no sample file return an empty frame, exactly like a
failed download.
"""
import os
import sys
import types

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["timestamp", "open", "high", "low", "close"]


def install(data_dir=None):
    data_dir = data_dir or os.path.join(os.path.dirname(_HERE), "data", "bars")
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    try:
        import yfinance  # noqa: F401
    except Exception:
        stub = types.ModuleType("yfinance")

        def _no_network(*a, **k):
            raise RuntimeError("no network in this sandbox -- data comes from offline_loader")

        stub.download = _no_network
        sys.modules["yfinance"] = stub
    import mtf_zones as mtz

    cache = {}

    def _fetch(ticker, period, interval):
        key = (ticker, interval)
        if key not in cache:
            path = os.path.join(data_dir, f"{ticker}__{interval}.csv")
            if os.path.exists(path):
                cache[key] = pd.read_csv(path, parse_dates=["timestamp"])[COLS]
            else:
                cache[key] = pd.DataFrame(columns=COLS)
        return cache[key].copy()

    mtz._fetch = _fetch
    return mtz
