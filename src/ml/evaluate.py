"""Evaluation of an already-created take set (strategy-agnostic). No threshold logic, model fitting, folds, calibration, champion
selection, file writing or orchestration.

Semantics are the Phase A ones (src/portfolio.py, src/costs.py):
  * R series = resolved rows (WIN / LOSS) only, ordered by exit_time, fill_time, ticker, entry_price (portfolio.order);
    max drawdown = portfolio.max_drawdown of that series; PF = positive R / |negative R|, NaN when there is no negative R.
  * net R = costs.CostModel.net_r(r_gross, fill_price, exit_price, risk) for the scenarios of costs.scenarios(); the actual r_gross
    of each trade is used (a WIN is never replaced by +2R, a LOSS never by -1R). The same take set is scored under every scenario.
  * AMBIGUOUS / CENSORED / OPEN / NOFILL rows stay in the counts and never enter R, expectancy, PF or drawdown. AMBIGUOUS bounds
    keep the Phase A convention (+2R gross if every ambiguous trade won, -1R gross if every one lost, win-rate bounds over
    WIN + LOSS + AMBIGUOUS). For a net scenario the same bounds also subtract that scenario's cost, estimated with the fill price
    on both legs because the exit price of an ambiguous trade is unknown; for the gross scenario they equal Phase A exactly.
Results are plain numbers (win rates are fractions in [0, 1], undefined values are NaN). Rows are addressed by position, so
pooled frames with repeated or arbitrary indices are fine.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import costs  # noqa: E402
import portfolio as P  # noqa: E402

OUTCOMES = ("WIN", "LOSS", "AMBIGUOUS", "CENSORED", "OPEN", "NOFILL")
RESOLVED = ("WIN", "LOSS")
REQUIRED_COLUMNS = ("outcome", "r_gross", "fill_price", "exit_price", "risk", "fill_time", "exit_time", "ticker", "entry_price")
AMBIGUOUS_BEST_R, AMBIGUOUS_WORST_R = 2.0, -1.0  # Phase A bound convention (gross R)
_COUNT_KEYS = OUTCOMES


class Prepared:
    """Row data prepared once for a frame: ordered resolved rows, net R per scenario, ambiguity-bound costs."""

    def __init__(self, df, slippage=0.0):
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        d = df.reset_index(drop=True)
        self.n = len(d)
        self.outcome = d["outcome"].to_numpy(dtype=object)
        unknown = sorted(set(self.outcome) - set(OUTCOMES))
        if unknown:
            raise ValueError(f"unknown outcome classes: {unknown}")
        res = np.isin(self.outcome, RESOLVED)
        work = d[res].copy()
        for c in ("fill_time", "exit_time"):
            work[c] = pd.to_datetime(work[c])
        for c in ("r_gross", "fill_price", "exit_price", "risk"):
            work[c] = work[c].astype(float)
        bad = ~np.isfinite(work[["r_gross", "fill_price", "exit_price", "risk"]].to_numpy()).all(axis=1)
        bad |= work["fill_time"].isna().to_numpy() | work["exit_time"].isna().to_numpy() | ~(work["risk"].to_numpy() > 0)
        if bad.any():
            raise ValueError(f"{int(bad.sum())} resolved rows lack finite r_gross / prices / risk / times")
        ordered = P.order(work)  # exit_time, fill_time, ticker, entry_price (stable)
        self.pos = ordered.index.to_numpy()          # positions (in the reset frame) of resolved rows, in R-series order
        self.scenarios = [cm.name for cm in costs.scenarios(slippage)]
        self.net = {}
        for cm in costs.scenarios(slippage):
            self.net[cm.name] = np.array([cm.net_r(g, f, e, k) for g, f, e, k in
                                          zip(ordered["r_gross"], ordered["fill_price"], ordered["exit_price"], ordered["risk"])])
        self.amb_pos = np.flatnonzero(self.outcome == "AMBIGUOUS")
        self.amb_cost = {}
        if len(self.amb_pos):
            a = d.iloc[self.amb_pos]
            fp, rk = a["fill_price"].to_numpy(dtype=float), a["risk"].to_numpy(dtype=float)
            if not (np.isfinite(fp).all() and np.isfinite(rk).all() and (rk > 0).all()):
                raise ValueError("AMBIGUOUS rows need finite fill_price and positive risk")
            for cm in costs.scenarios(slippage):
                self.amb_cost[cm.name] = np.array([cm.cost_r(f, f, k) for f, k in zip(fp, rk)])
        else:
            for cm in costs.scenarios(slippage):
                self.amb_cost[cm.name] = np.array([])


def _as_prepared(x, slippage):
    return x if isinstance(x, Prepared) else Prepared(x, slippage)


def _take(take, n):
    t = np.asarray(take)
    if t.dtype != bool or t.ndim != 1 or len(t) != n:
        raise ValueError("take must be a 1-dimensional boolean array with one value per row")
    return t


def evaluate(prepared, take):
    """Metrics of one take set under every cost scenario: {scenario name: {metric: number}}."""
    pr = prepared
    t = _take(take, pr.n)
    counts = {k: int((t & (pr.outcome == k)).sum()) for k in _COUNT_KEYS}
    n_taken = int(t.sum())
    w, l, amb = counts["WIN"], counts["LOSS"], counts["AMBIGUOUS"]
    tk = t[pr.pos]
    out = {}
    for name in pr.scenarios:
        r = pr.net[name][tk]
        pos, neg = r[r > 0].sum(), -r[r < 0].sum()
        total = float(r.sum())
        m = dict(n_rows=pr.n, n_taken=n_taken, n_resolved_taken=w + l, take_rate=n_taken / pr.n if pr.n else float("nan"), **counts,
                 win_rate=w / (w + l) if w + l else float("nan"),
                 expectancy=float(r.mean()) if len(r) else float("nan"),
                 profit_factor=float(pos / neg) if neg > 0 else float("nan"),
                 total_r=total, max_dd=P.max_drawdown(r))
        ta = t[pr.amb_pos]
        c = pr.amb_cost[name][ta]
        m.update(win_rate_amb_best=(w + amb) / (w + l + amb) if w + l + amb else float("nan"),
                 win_rate_amb_worst=w / (w + l + amb) if w + l + amb else float("nan"),
                 total_r_amb_best=total + float((AMBIGUOUS_BEST_R - c).sum()),
                 total_r_amb_worst=total + float((AMBIGUOUS_WORST_R - c).sum()))
        out[name] = m
    return out


def evaluate_take_set(df, take, slippage=0.0):
    """Convenience: prepare df (any index) and evaluate one take set under gross / 0.10% / 0.20% / 0.30% round trip."""
    return evaluate(Prepared(df, slippage), take)


def ml_metrics(outcome, p, take, base_rate=None):
    """Classifier metrics on the resolved rows (WIN = 1, LOSS = 0) of one frame, for probabilities p over ALL rows.
    precision / recall refer to the supplied take mask; undefined values are NaN. base_rate (from training data, optional) adds
    the Brier score of the constant base-rate predictor."""
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
    outcome = np.asarray(outcome, dtype=object)
    p = np.asarray(p, dtype=float)
    t = _take(take, len(outcome))
    if p.ndim != 1 or len(p) != len(outcome) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("p must be 1-dimensional, finite and within [0, 1], one value per row")
    res = np.isin(outcome, RESOLVED)
    y, pr, tr = (outcome[res] == "WIN").astype(int), p[res], t[res]
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    both = n_pos > 0 and n_neg > 0
    tp = int((tr & (y == 1)).sum())
    out = dict(n_rows=len(outcome), n_resolved=len(y), n_pos=n_pos, n_neg=n_neg,
               roc_auc=float(roc_auc_score(y, pr)) if both else float("nan"),
               pr_auc=float(average_precision_score(y, pr)) if n_pos else float("nan"),
               predicted_positive=int(t.sum()), predicted_positive_resolved=int(tr.sum()),
               precision=tp / int(tr.sum()) if tr.sum() else float("nan"),
               recall=tp / n_pos if n_pos else float("nan"),
               brier=float(brier_score_loss(y, pr)) if len(y) else float("nan"),
               log_loss=float(log_loss(y, pr, labels=[0, 1])) if len(y) else float("nan"),
               base_rate_observed=n_pos / len(y) if len(y) else float("nan"))
    if base_rate is not None:
        if not (np.isfinite(base_rate) and 0 <= base_rate <= 1):
            raise ValueError("base_rate must lie in [0, 1]")
        out["brier_base_rate"] = float(brier_score_loss(y, np.full(len(y), float(base_rate)))) if len(y) else float("nan")
    return out


def random_filter_take(n_rows, n_take, seed, groups=None):
    """Deterministic B2 control mask. Without groups, n_take rows are drawn uniformly without replacement. With groups (one label
    per row), n_take is a mapping {group: count} and each group is sampled separately, in sorted group order, from one generator."""
    rng = np.random.default_rng(seed)
    mask = np.zeros(n_rows, dtype=bool)
    if groups is None:
        if not 0 <= int(n_take) <= n_rows:
            raise ValueError("n_take must lie in [0, n_rows]")
        mask[rng.choice(n_rows, size=int(n_take), replace=False)] = True
        return mask
    g = np.asarray(groups)
    if len(g) != n_rows:
        raise ValueError("groups needs one label per row")
    for key in sorted(set(g.tolist())):
        idx = np.flatnonzero(g == key)
        k = int(n_take.get(key, 0))
        if not 0 <= k <= len(idx):
            raise ValueError(f"n_take for group {key!r} must lie in [0, {len(idx)}]")
        mask[rng.choice(idx, size=k, replace=False)] = True
    return mask


def evaluate_random_filter(df, n_take, seed, groups=None, slippage=0.0):
    """B2 control for one seed: a random take set of the supplied size scored exactly like any other take set."""
    pr = _as_prepared(df, slippage)
    return evaluate(pr, random_filter_take(pr.n, n_take, seed, groups))


def random_filter_distribution(df, n_take, n_draws, seed, groups=None, slippage=0.0):
    """Metrics over n_draws random filters (draw k uses seed [seed, k], so any draw is reproducible alone):
    {scenario: {metric: array of length n_draws}} for the numeric metrics of evaluate()."""
    pr = _as_prepared(df, slippage)
    keys = None
    cols = {}
    for k in range(int(n_draws)):
        res = evaluate(pr, random_filter_take(pr.n, n_take, [int(seed), k], groups))
        if keys is None:
            keys = list(next(iter(res.values())).keys())
            cols = {s: {m: np.empty(int(n_draws)) for m in keys} for s in res}
        for s, m in res.items():
            for key in keys:
                cols[s][key][k] = m[key]
    return cols
