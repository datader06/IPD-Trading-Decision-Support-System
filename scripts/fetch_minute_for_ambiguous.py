"""Fetch Kite 1-minute bars for candidates that are AMBIGUOUS only because no minute data is cached (Phase A, A7).

Read-only (CLAUDE.md): src/kite_client.KiteReadOnly, instruments() + historical_data() only; credentials from .env via that client.
One request per (symbol, day) of an ambiguous 15m bar; files land in data/cache/kite/<SYM>/minute/ where src/replay.MinuteCache
finds them, so re-running `run_phase_a.py generate` (new label or deleted checkpoints) re-scores those trades.
Standing rule: prints the request count first and stops if it exceeds 1,500 (no override flag on purpose: split the run with
--limit=N instead).

  python scripts/fetch_minute_for_ambiguous.py --label=pit [--run=ID] [--from=2021-01-01] [--b0-only] [--limit=N] [--dry-run]
Needs the kiteconnect package and a valid daily token (python kite_login.py).
"""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
MAX_REQUESTS = 1500


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def main():
    import run_phase_a as R
    df = R.load(arg("label", "pit"))
    m = (df.outcome == "AMBIGUOUS") & df.exit_reason.astype(str).str.startswith("MINUTE_NOT_CACHED")
    m &= df.entry_time >= pd.Timestamp(arg("from", "2021-01-01"))  # only the reported window, no unrelated data
    if "--b0-only" in sys.argv:
        m &= df.is_b0
    need = df[m].assign(sym=lambda d: d.ticker.str.replace(".NS", "", regex=False),
                        day=lambda d: pd.to_datetime(d.exit_time).dt.normalize())[["sym", "day"]].drop_duplicates()
    need = need.sort_values(["day", "sym"])
    if arg("limit"):
        need = need.head(int(arg("limit")))
    print(f"minute requests needed: {len(need)} (one per symbol-day)")
    if len(need) > MAX_REQUESTS:
        print(f"STOP: {len(need)} > {MAX_REQUESTS} (standing rule). Use --limit=N and run in parts, or --b0-only.")
        return
    if "--dry-run" in sys.argv:
        return
    from kite_client import KiteReadOnly
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tok = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    missing = 0
    for t in need.itertuples():
        if t.sym not in tok:
            missing += 1
            continue
        d0 = t.day.to_pydatetime()
        k.historical_data(int(tok[t.sym]), d0, d0 + timedelta(days=1), "minute", symbol=t.sym)
    print(f"done; symbols not found in instruments: {missing}")


if __name__ == "__main__":
    main()
