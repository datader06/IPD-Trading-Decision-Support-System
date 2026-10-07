"""Fetch Kite 15minute bars 2020-11-01 .. 2023-01-02 and write MERGED frames to data/cache/kite_frames_dit15_long/ (15m merged, plus 1d and the merged 60m copied).

Read-only Kite: instruments() and historical_data() only. data/cache/kite_frames and kite_frames_wit_long are not modified.
Request count is printed first (about 4 chunks of 200 days per ticker); approved by the user for this experiment.
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
SRC60 = ROOT / "data" / "cache" / "kite_frames_wit_long"
OUT = ROOT / "data" / "cache" / "kite_frames_dit15_long"
FROM, TO = datetime(2020, 11, 1), datetime(2023, 1, 2)


def main():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass
    tickers = [t for t in json.load(open(UNIVERSE))["tickers"] if t not in SKIP]
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    mapped = [t for t in tickers if t.replace(".NS", "") in tokmap]
    nch = len(chunks(FROM, TO, timedelta(days=MAX_DAYS_PER_REQUEST["15minute"])))
    todo = [t for t in mapped if not cache_path(t.replace(".NS", ""), "15minute", FROM, TO).exists()]
    print(f"mapped {len(mapped)}; chunks per ticker {nch}; uncached {len(todo)}; planned requests {nch * len(todo)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(mapped, 1):
        sym = t.replace(".NS", "")
        new = k.historical_data(int(tokmap[sym]), FROM, TO, "15minute", symbol=sym)
        old = pd.read_csv(SRC / f"{t}__15m.csv", parse_dates=["timestamp"])
        if len(new):
            new["timestamp"] = pd.to_datetime(new["timestamp"])
            old = pd.concat([new[["timestamp", "open", "high", "low", "close"]], old]).drop_duplicates("timestamp").sort_values("timestamp")
        old.to_csv(OUT / f"{t}__15m.csv", index=False)
        shutil.copy(SRC60 / f"{t}__60m.csv", OUT / f"{t}__60m.csv")
        shutil.copy(SRC60 / f"{t}__1d.csv", OUT / f"{t}__1d.csv")
        if i % 50 == 0:
            print(f"{i}/{len(mapped)} done", flush=True)
    firsts = [pd.read_csv(OUT / f"{t}__15m.csv", nrows=1).timestamp.iloc[0] for t in mapped[:50]]
    print(f"DONE {len(mapped)} merged frames in {OUT.relative_to(ROOT)}; earliest 15m bar in the first 50: {min(firsts)}")


if __name__ == "__main__":
    main()
