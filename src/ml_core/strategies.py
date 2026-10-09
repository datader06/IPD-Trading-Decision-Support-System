"""Candidate sources per strategy. Edit an entry (or pass overrides to build_dataset) to point the ML layer at a new deterministic-layer run."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SOURCES = {
    "DIT15": ROOT / "results" / "nogit-145d6302" / "phase_a" / "pit" / "candidates.csv",
    "WIT": ROOT / "results" / "nogit-7a8ea6d9" / "phase_a_mtf" / "wit" / "pit" / "candidates.csv",
    "MIT": ROOT / "results" / "nogit-ff52bbc2" / "phase_a_mtf" / "mit" / "pit" / "candidates.csv",
}
STRATEGY_ORDER = ("DIT15", "WIT", "MIT")  # DIT15 is the reference level of the strategy indicators
