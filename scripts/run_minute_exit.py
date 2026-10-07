"""Exit scoring for the run_baseline.py trade lists (any combo) via replay_trade. Standing rule in CLAUDE.md.

Usage: python scripts/run_minute_exit.py wit|mit   (reads results/<hash>/trades_<combo>_heuristic.csv)
"""
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import replay_common as rc  # noqa: E402


def main():
    combo = sys.argv[1] if len(sys.argv) > 1 else "wit"
    h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    src = ROOT / "results" / h / f"trades_{combo}_heuristic.csv"
    out = ROOT / "results" / h / f"trades_{combo}_final.csv"
    rc.run(combo, src, out, f"{combo.upper()} baseline")


if __name__ == "__main__":
    main()
