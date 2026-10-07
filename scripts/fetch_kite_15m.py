"""Fetch Kite 15minute bars (2023-01-01 .. tomorrow 00:00) for the legacy universe; write legacy-format frames.

Read-only: instruments() and historical_data() only. Frames -> data/cache/kite_frames/{ticker}__15m.csv.
Stops before fetching if planned requests > 4000 (override --go).
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from kite_client import KiteReadOnly, MAX_DAYS_PER_REQUEST, cache_path  # noqa: E402
from fetch_kite_daily import chunks, SKIP, UNIVERSE  # noqa: E402

OUT = ROOT / "data" / "cache" / "kite_frames"
FROM = datetime(2023, 1, 1)
MAX_REQUESTS = 4000


def main():
    to = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())
    tickers = [t for t in json.load(open(UNIVERSE))["tickers"] if t not in SKIP]
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    mapped = [t for t in tickers if t.replace(".NS", "") in tokmap]
    nch = len(chunks(FROM, to, timedelta(days=MAX_DAYS_PER_REQUEST["15minute"])))
    todo = [t for t in mapped if not cache_path(t.replace(".NS", ""), "15minute", FROM, to).exists()]
    print(f"mapped {len(mapped)} (HFCL.NS skipped); chunks per ticker {nch}; uncached {len(todo)}; planned requests {nch * len(todo)}; "
          f"daily and 60m frames reused from cache (0 requests)", flush=True)
    if nch * len(todo) > MAX_REQUESTS and "--go" not in sys.argv:
        print(f"STOP: over {MAX_REQUESTS} (ask user)")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(mapped, 1):
        sym = t.replace(".NS", "")
        df = k.historical_data(int(tokmap[sym]), FROM, to, "15minute", symbol=sym)
        if len(df):
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df[["timestamp", "open", "high", "low", "close"]].to_csv(OUT / f"{t}__15m.csv", index=False)
        if i % 25 == 0:
            print(f"{i}/{len(mapped)} done", flush=True)
    print(f"DONE 60m frames {len(list(OUT.glob('*__15m.csv')))} of {len(mapped)} mapped")


if __name__ == "__main__":
    main()
