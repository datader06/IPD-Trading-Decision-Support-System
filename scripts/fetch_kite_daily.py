"""Fetch Kite day bars (2012-01-01 .. tomorrow 00:00) for the legacy universe and write legacy-format frames.

Read-only: instruments() and historical_data() only. Cached + rate limited by src/kite_client.py.
Frames -> data/cache/kite_frames/{ticker}__1d.csv with columns timestamp,open,high,low,close.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from kite_client import KiteReadOnly, MAX_DAYS_PER_REQUEST, cache_path  # noqa: E402

UNIVERSE = ROOT / "legacy" / "handoff" / "handoff" / "code" / "webapp" / "universe_live.json"
OUT = ROOT / "data" / "cache" / "kite_frames"
FROM = datetime(2012, 1, 1)
SKIP = {"HFCL.NS"}  # Kite lists it only as HFCL-BE (different series); reported as unmapped
MAX_REQUESTS = 1500


def chunks(frm, to, step):
    out, s = [], frm
    while s < to:
        e = min(s + step, to)
        out.append((s, e))
        s = e + timedelta(seconds=1)
    return out


def main():
    to = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())
    tickers = json.load(open(UNIVERSE))["tickers"]
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    unmapped = [t for t in tickers if t in SKIP or t.replace(".NS", "") not in tokmap]
    mapped = [t for t in tickers if t not in unmapped]
    print(f"universe {len(tickers)}, mapped {len(mapped)}, unmapped {len(unmapped)}: {unmapped}")
    # historical_data() caches the whole requested window under one name; planned requests = chunks per uncached ticker
    nch = len(chunks(FROM, to, timedelta(days=MAX_DAYS_PER_REQUEST["day"])))
    todo = [t for t in mapped if not cache_path(t.replace(".NS", ""), "day", FROM, to).exists()]
    print(f"to date {to:%Y-%m-%d}; chunks per ticker {nch}; uncached tickers {len(todo)}; planned requests {nch * len(todo)}", flush=True)
    if nch * len(todo) > MAX_REQUESTS:
        print("STOP: over 1500 (approved cap was 1509 for this run; rerun with --go)")
        if "--go" not in sys.argv:
            return
    OUT.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(mapped, 1):
        sym = t.replace(".NS", "")
        df = k.historical_data(int(tokmap[sym]), FROM, to, "day", symbol=sym)
        if len(df):
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df[["timestamp", "open", "high", "low", "close"]].to_csv(OUT / f"{t}__1d.csv", index=False)
        if i % 25 == 0:
            print(f"{i}/{len(mapped)} done", flush=True)
    print(f"DONE frames {len(list(OUT.glob('*__1d.csv')))} of {len(mapped)} mapped")


if __name__ == "__main__":
    main()
