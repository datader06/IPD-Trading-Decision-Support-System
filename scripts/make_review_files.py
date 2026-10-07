"""Build review_dit15.csv, review_wit.csv, review_mit.csv (sorted by entry_time) in results/<HEAD hash>/.

Sources: newest trades_dit15_kite_2024_final.csv, trades_wit_kite_2024_final.csv, trades_mit_kite_2024_final.csv.
Columns end with an empty my_verdict for the user's manual review. No network.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
COLS = ["ticker", "type", "htf_formed_at", "htf_proximal", "htf_distal", "ltf_formed_at", "entry_price", "stop", "target",
        "entry_time", "exit_time", "outcome", "deciding_interval", "my_verdict"]
INTERVAL = {"15minute": "15m", "1minute": "1m"}


def newest(name):
    hits = sorted((ROOT / "results").glob(f"*/{name}"), key=lambda p: p.stat().st_mtime)
    return hits[-1]


def build(src):
    d = pd.read_csv(src, parse_dates=["entry_time"])
    out = pd.DataFrame({c: d[c] for c in ["ticker", "type", "htf_formed_at", "htf_proximal", "htf_distal", "ltf_formed_at",
                                         "entry_price", "stop", "target", "entry_time"]})
    out["exit_time"] = d["exit_time_new"].where(d["exit_time_new"].notna(), d["exit_time"])
    out["outcome"] = d["exit_outcome"]
    out["deciding_interval"] = [INTERVAL.get(i, "heuristic (no minute data; outcome stays AMBIGUOUS)") for i in d["exit_interval"]]
    out["my_verdict"] = ""
    return out[COLS].sort_values("entry_time").reset_index(drop=True)


def main():
    h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    res = ROOT / "results" / h
    res.mkdir(parents=True, exist_ok=True)
    for key, name in (("dit15", "trades_dit15_kite_2024_final.csv"), ("wit", "trades_wit_kite_2024_final.csv"),
                      ("mit", "trades_mit_kite_2024_final.csv")):
        src = newest(name)
        out = build(src)
        out.to_csv(res / f"review_{key}.csv", index=False)
        print(f"results/{h}/review_{key}.csv: {len(out)} rows (from {src.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
