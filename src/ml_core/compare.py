"""Reporting helpers for pooled multi-strategy runs: per-strategy tables, per-strategy AUC and a paired month-block bootstrap."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml import evaluate as E  # noqa: E402

SCENARIOS = ("gross", "rt0.10", "rt0.20", "rt0.30")
KEEP = ("n_rows", "n_taken", "n_resolved_taken", "take_rate", "WIN", "LOSS", "AMBIGUOUS", "win_rate", "expectancy", "profit_factor",
        "total_r", "max_dd", "total_r_amb_worst", "total_r_amb_best")


def arms_of(oof, families):
    """{arm name: boolean take mask over oof rows}: B0, B1 and, per family, the T1 and T2 ML takes."""
    arms = {"B0": oof["is_b0"].to_numpy(dtype=bool), "B1": np.ones(len(oof), dtype=bool)}
    for f in families:
        arms[f"ML:{f}"] = oof[f"take_{f}"].to_numpy(dtype=bool)
        arms[f"ML_T2:{f}"] = oof[f"take_t2_{f}"].to_numpy(dtype=bool)
    return arms


def per_strategy_table(oof, families):
    """Long table: strategy (ALL + each), arm, scenario, metrics. Scenario names follow ml.evaluate (gross, rt0.10, ...)."""
    rows = []
    for strat in ["ALL"] + sorted(oof["strategy"].unique()):
        sub = oof if strat == "ALL" else oof[oof["strategy"] == strat]
        mask = np.ones(len(oof), dtype=bool) if strat == "ALL" else (oof["strategy"] == strat).to_numpy()
        pr = E.Prepared(sub.reset_index(drop=True))
        for arm, take in arms_of(oof, families).items():
            res = E.evaluate(pr, take[mask])
            for sc, m in res.items():
                rows.append(dict(strategy=strat, arm=arm, scenario=sc, **{k: m[k] for k in KEEP}))
    return pd.DataFrame(rows)


def per_strategy_auc(oof, families):
    from sklearn.metrics import roc_auc_score
    rows = []
    res = oof[oof["outcome"].isin(E.RESOLVED)]
    for strat in ["ALL"] + sorted(oof["strategy"].unique()):
        sub = res if strat == "ALL" else res[res["strategy"] == strat]
        y = (sub["outcome"] == "WIN").to_numpy().astype(int)
        for f in families:
            ok = len(set(y)) == 2
            rows.append(dict(strategy=strat, family=f, n_resolved=len(sub), roc_auc=float(roc_auc_score(y, sub[f"p_{f}"])) if ok else np.nan))
    return pd.DataFrame(rows)


def month_block_bootstrap(oof, families, versus=("B0", "B1"), scenario="rt0.20", n_boot=2000, seed=42):
    """Paired month-block bootstrap of expectancy (ML minus baseline) on the pooled stream; months are resampled with replacement."""
    pr = E.Prepared(oof.reset_index(drop=True))
    net = np.full(len(oof), np.nan)
    net[pr.pos] = pr.net[scenario]
    resolved = ~np.isnan(net)
    month = oof["entry_time"].dt.to_period("M").astype(str).to_numpy()
    months = sorted(set(month))
    mi = np.array([months.index(m) for m in month])
    arms = arms_of(oof, families)

    def month_stats(take):
        s = np.zeros(len(months))
        n = np.zeros(len(months))
        sel = take & resolved
        np.add.at(s, mi[sel], net[sel])
        np.add.at(n, mi[sel], 1)
        return s, n

    stats = {a: month_stats(t) for a, t in arms.items()}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(months), size=(n_boot, len(months)))

    def expect(a):
        s, n = stats[a]
        ss, nn = s[draws].sum(1), n[draws].sum(1)
        return np.where(nn > 0, ss / np.maximum(nn, 1), np.nan)

    out = []
    for fam in families:
        for kind in ("ML", "ML_T2"):
            a = f"{kind}:{fam}"
            e_ml = expect(a)
            for v in versus:
                diff = e_ml - expect(v)
                ok = diff[np.isfinite(diff)]
                s, n = stats[a]
                sv, nv = stats[v]
                point_ml = s.sum() / n.sum() if n.sum() else np.nan
                point_b = sv.sum() / nv.sum() if nv.sum() else np.nan
                out.append(dict(arm=a, versus=v, scenario=scenario, ml=point_ml, baseline=point_b, diff=point_ml - point_b,
                                ci_lo=float(np.percentile(ok, 2.5)) if len(ok) else np.nan,
                                ci_hi=float(np.percentile(ok, 97.5)) if len(ok) else np.nan,
                                share_positive=float((ok > 0).mean()) if len(ok) else np.nan, n_valid=len(ok), n_boot=n_boot,
                                n_months=len(months)))
    return pd.DataFrame(out)
