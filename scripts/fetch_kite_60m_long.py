"""Fetch Kite 60minute bars 2020-11-01 .. 2023-01-02 and write MERGED frames (old + new) to data/cache/kite_frames_wit_long/.

Also copies the daily frames there. data/cache/kite_frames (used by every earlier run) is NOT modified.
Read-only Kite: instruments() and historical_data() only. Stops before fetching if planned requests > 1500 (override --go).
"""
import json
import shutil
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

SRC = ROOT / "data" / "cache" / "kite_frames"
OUT = ROOT / "data" / "cache" / "kite_frames_wit_long"
FROM, TO = datetime(2020, 11, 1), datetime(2023, 1, 2)
MAX_REQUESTS = 1500


def main():
    tickers = [t for t in json.load(open(UNIVERSE))["tickers"] if t not in SKIP]
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    mapped = [t for t in tickers if t.replace(".NS", "") in tokmap]
    nch = len(chunks(FROM, TO, timedelta(days=MAX_DAYS_PER_REQUEST["60minute"])))
    todo = [t for t in mapped if not cache_path(t.replace(".NS", ""), "60minute", FROM, TO).exists()]
    print(f"mapped {len(mapped)}; chunks per ticker {nch}; uncached {len(todo)}; planned requests {nch * len(todo)}", flush=True)
    if nch * len(todo) > MAX_REQUESTS and "--go" not in sys.argv:
        print("STOP: over 1500")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(mapped, 1):
        sym = t.replace(".NS", "")
        new = k.historical_data(int(tokmap[sym]), FROM, TO, "60minute", symbol=sym)
        old = pd.read_csv(SRC / f"{t}__60m.csv", parse_dates=["timestamp"])
        if len(new):
            new["timestamp"] = pd.to_datetime(new["timestamp"])
            old = pd.concat([new[["timestamp", "open", "high", "low", "close"]], old]).drop_duplicates("timestamp").sort_values("timestamp")
        old.to_csv(OUT / f"{t}__60m.csv", index=False)
        shutil.copy(SRC / f"{t}__1d.csv", OUT / f"{t}__1d.csv")
        if i % 50 == 0:
            print(f"{i}/{len(mapped)} done", flush=True)
    firsts = [pd.read_csv(OUT / f"{t}__60m.csv", nrows=1).timestamp.iloc[0] for t in mapped[:50]]
    print(f"DONE {len(mapped)} merged frames in {OUT.relative_to(ROOT)}; earliest 60m bar in the first 50: {min(firsts)}")


if __name__ == "__main__":
    main()
