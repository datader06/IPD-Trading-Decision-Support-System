"""Phase B trade-outcome labels (frozen definition). No features, models or validation code here.

Decision time = start of the 15m entry bar. For every candidate row:
  label 1  = +2R target reached before the -1R stop      (Phase A outcome WIN)
  label 0  = -1R stop reached before the +2R target      (Phase A outcome LOSS)
  no label = AMBIGUOUS / OPEN / CENSORED / NOFILL         (kept in the file with an explicit status; never a training label)
The label is the Phase A replay outcome, not a new rule: `outcome` / `exit_reason` / `r_gross` of the Tier-1 dataset are
preserved unchanged. As an independent check every row is replayed again with the unchanged src/replay.py through the same
call path as candidates._replay_all (15m replay, then the cached 1-minute drill-down for MINUTE_NOT_CACHED bars), and the
result must equal the stored Phase A fields (`replay_check` column).
Nothing here feeds back into features: labels use data after the decision time by construction, features never do.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# The replay helpers live in the common module src/replay_context.py (Phase A must not depend on this package). They are
# re-exported here so existing callers (`labels.ReplayContext`, `labels.replay_row`, `labels.check_row`) keep working unchanged.
from replay_context import ReplayContext, check_row, replay_row  # noqa: E402,F401

STATUSES = ("WIN", "LOSS", "AMBIGUOUS", "CENSORED", "OPEN", "NOFILL")
LABEL_COLUMNS = ["label", "label_status", "is_training_label", "phase_a_src_row", "replay_check"]


def label_from_outcome(outcome):
    """(label, status, is_training_label). label is None for anything that is not a resolved WIN or LOSS."""
    if outcome == "WIN":
        return 1, "WIN", True
    if outcome == "LOSS":
        return 0, "LOSS", True
    if outcome in STATUSES:
        return None, outcome, False
    raise ValueError(f"unknown outcome class {outcome!r}")


def label_rows(rows, ctx, src_row_of=None, check=True):
    """rows: iterable of dicts (Tier-1 dataset rows). Returns a list of dicts with the four label columns added."""
    out = []
    for r in rows:
        lab, status, is_train = label_from_outcome(r["outcome"])
        rec = dict(r)
        rec["label"] = lab
        rec["label_status"] = status
        rec["is_training_label"] = is_train
        rec["phase_a_src_row"] = src_row_of(r) if src_row_of else -1
        rec["replay_check"] = check_row(r, replay_row(r, ctx)) if check else "not_checked"
        out.append(rec)
    return out
