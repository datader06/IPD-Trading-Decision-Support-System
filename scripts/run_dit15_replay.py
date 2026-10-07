"""dit15 exit scoring via replay_trade (15minute, then 1minute for AMBIGUOUS). Standing rule in CLAUDE.md."""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base_flags  # noqa: E402
TAG = _base_flags.resolve()  # "" = legacy base logic (--legacy-base); "_v2_cap5" = V2 default
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import replay_common as rc  # noqa: E402


def newest(name):
    hits = sorted((ROOT / "results").glob(f"*/{name}"), key=lambda p: p.stat().st_mtime)
    return hits[-1]


def main():
    h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    src = newest(f"trades_dit15_kite_2024{TAG}_heuristic.csv")
    out_path = ROOT / "results" / h / f"trades_dit15_kite_2024{TAG}_final.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"source {src.relative_to(ROOT)}")
    out = rc.run("dit15", src, out_path, "DIT15 on Kite")
    if out is None:
        return
    x = out["ltf_risk_pct"]
    print(f"\nltf_risk_pct (stop as % of price): median {np.median(x):.2f}, 90th percentile {np.percentile(x, 90):.2f}")
    print(f"trades that needed the 1-minute drill-down: {int((out['exit_r15'] == 'AMBIGUOUS').sum())} of {len(out)}")
    print(f"NO_MINUTE_DATA: {int(out['exit_no_minute_data'].sum())}")


if __name__ == "__main__":
    main()
