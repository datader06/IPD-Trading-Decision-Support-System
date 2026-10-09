"""Frozen Experiment 1 threshold rules (strategy-agnostic). Decides take / skip from probabilities; never fits a model, builds
folds, evaluates trading performance or chooses a champion model.

T1 (primary, no tuned parameter):  take  <=>  p*W - (1-p)*L - c > 0
  p  native probability of class 1
  W  2.0, fixed and preregistered (never the observed mean WIN R)
  L  mean absolute r_gross of the LOSS rows of the current TRAINING stage (compute_l_from_training)
  c  per-row cost in R at 0.20% round trip (the caller supplies it)
The strict inequality on the expected value is authoritative (apply_t1). The break-even probability is the same inequality solved
for p and is for reporting and for T2's candidate list; do not decide takes by comparing p with it (floating-point rounding).

T2 (secondary, reported only; it never selects the champion): a validation-only search over a fixed threshold list.
"""
import math
from dataclasses import dataclass, field

import numpy as np

W_FIXED = 2.0
T2_GRID = tuple(round(0.15 + 0.01 * i, 2) for i in range(46))  # 0.15 .. 0.60 inclusive
T2_MIN_TAKES_FLOOR = 30
T2_MIN_TAKES_SHARE_DENOM = 10  # at least 1/10 of the resolved validation rows


def _finite_1d(a, name):
    a = np.asarray(a, dtype=float)
    if a.ndim != 1:
        raise ValueError(f"{name} must be 1-dimensional")
    if not np.isfinite(a).all():
        raise ValueError(f"{name} contains NaN or infinite values")
    return a


def compute_l_from_training(outcome, r_gross, loss_label="LOSS"):
    """L = mean |r_gross| over the LOSS rows of the supplied TRAINING rows. Rejects empty / non-finite input and no-loss input."""
    outcome = np.asarray(outcome)
    r = np.asarray(r_gross, dtype=float)
    if outcome.ndim != 1 or r.ndim != 1 or len(outcome) != len(r):
        raise ValueError("outcome and r_gross must be 1-dimensional and of equal length")
    loss = outcome == loss_label
    if not loss.any():
        raise ValueError(f"no {loss_label} rows in the training input: L is undefined")
    lr = r[loss]
    if not np.isfinite(lr).all():
        raise ValueError(f"{loss_label} rows contain NaN or infinite r_gross")
    L = float(np.abs(lr).mean())
    if not L > 0:
        raise ValueError("mean absolute loss is not positive")
    return L


def _check_l(L):
    if not (np.isfinite(L) and L > 0):
        raise ValueError("L must be finite and positive")


def t1_breakeven(L, c, W=W_FIXED):
    """Probability at which the T1 expected value is zero: p*W - (1-p)*L - c = 0  =>  p* = (L + c) / (W + L), for scalar c.
    A take needs p strictly above it. Not clipped: a value above 1 means no probability can qualify."""
    _check_l(L)
    if not (np.isfinite(W) and W > 0):
        raise ValueError("W must be finite and positive")
    if not (np.isfinite(c) and c >= 0):
        raise ValueError("c must be finite and non-negative")
    return float((L + c) / (W + L))


def t1_expected_value(p, c, L):
    """Per-row expected net R of taking the trade: p*W - (1-p)*L - c, with W fixed at 2.0."""
    p = _finite_1d(p, "p")
    c = _finite_1d(c, "c")
    if len(p) != len(c):
        raise ValueError("p and c must have the same length")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("probabilities must lie in [0, 1]")
    if (c < 0).any():
        raise ValueError("costs must be non-negative")
    _check_l(L)
    return p * W_FIXED - (1.0 - p) * L - c


def apply_t1(p, c, L):
    """Boolean take mask: expected value strictly greater than 0. Probabilities are used exactly as given (no rounding)."""
    return t1_expected_value(p, c, L) > 0


@dataclass
class T2Result:
    threshold: float      # None when no candidate reaches the minimum number of takes
    expectancy: float
    n_taken: int          # resolved validation rows taken at the chosen threshold
    min_takes: int
    candidates: list = field(default_factory=list)  # (threshold, n_taken, expectancy or None, eligible) in evaluation order


def t2_candidate_thresholds(t1_breakeven_value=None):
    """Fixed grid 0.15 .. 0.60 (step 0.01) plus the supplied T1 break-even, de-duplicated, ascending."""
    cands = set(T2_GRID)
    if t1_breakeven_value is not None:
        if not np.isfinite(t1_breakeven_value):
            raise ValueError("t1_breakeven_value must be finite")
        cands.add(float(t1_breakeven_value))
    return sorted(cands)


def t2_min_takes(n_resolved):
    """max(30, 10% of the resolved validation rows), rounded up (integer arithmetic)."""
    return max(T2_MIN_TAKES_FLOOR, -(-int(n_resolved) // T2_MIN_TAKES_SHARE_DENOM))


def select_t2(p_val, net_r_val, resolved_val, t1_breakeven_value=None):
    """Secondary threshold search on VALIDATION rows only.

    p_val          validation probabilities (all validation rows)
    net_r_val      validation net R at 0.20% round trip (any value where the row is unresolved; only resolved rows are read)
    resolved_val   boolean mask of resolved (WIN / LOSS) validation rows
    t1_breakeven_value  T1 break-even probability to add to the candidates (the caller decides which scalar cost produced it)

    A row is taken at threshold t when p > t. Candidates are scored on resolved rows only: expectancy = mean net R of the taken
    rows. A candidate is eligible when it takes at least t2_min_takes(n_resolved) resolved rows. Choice: higher expectancy, then
    more takes, then lower threshold (exact comparison; equal values arise from identical take sets). The result is reported only
    and must never be used to select the champion model.
    """
    p = _finite_1d(p_val, "p_val")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("probabilities must lie in [0, 1]")
    res = np.asarray(resolved_val)
    if res.dtype != bool or res.ndim != 1:
        raise ValueError("resolved_val must be a 1-dimensional boolean mask")
    r = np.asarray(net_r_val, dtype=float)
    if r.ndim != 1 or not (len(p) == len(res) == len(r)):
        raise ValueError("p_val, net_r_val and resolved_val must be 1-dimensional and of equal length")
    if not np.isfinite(r[res]).all():
        raise ValueError("net_r_val must be finite for every resolved row")
    n_res = int(res.sum())
    if n_res == 0:
        raise ValueError("no resolved validation rows")
    need = t2_min_takes(n_res)
    pr, rr = p[res], r[res]
    rows, best_key, best = [], None, None
    for t in t2_candidate_thresholds(t1_breakeven_value):
        taken = pr > t
        n = int(taken.sum())
        eligible = n >= need
        exp = float(rr[taken].mean()) if n else None
        rows.append((t, n, exp, eligible))
        if eligible:
            key = (-exp, -n, t)
            if best_key is None or key < best_key:
                best_key, best = key, (t, exp, n)
    if best is None:
        return T2Result(None, float("nan"), 0, need, rows)
    return T2Result(best[0], best[1], best[2], need, rows)
