"""Small-sample yearly walk-forward with win-rate-focused evaluation (gross R, no costs). Works on any ml_core standard frame.

Protocol (docs/EXPERIMENT_3_PREREGISTRATION.md): expanding training window by calendar year, purge on exit_time, 7-day embargo,
fixed hyperparameters, top-k% selection by rank within each test year, random-selection control.
"""
import numpy as np
import pandas as pd

FAMILIES = ("logreg", "random_forest", "hist_gb", "xgboost")
SEED = 42
TOPK = (0.25, 0.50, 0.75)
EMBARGO_DAYS = 7


def make_model(family):
    from ml_core import model_registry as MR
    return MR.build(family)


def train_mask(d, test_start):
    """Rows usable for training before `test_start`: entered earlier, outcome known before the boundary (purge), outside the embargo."""
    e, x = d["entry_time"], d["exit_time"]
    return ((e < test_start - pd.Timedelta(days=EMBARGO_DAYS)) & (x < test_start)).to_numpy()


def walk_forward(d, features, test_years, families=FAMILIES):
    """d: development frame (holdout already removed). Returns the out-of-fold frame with p_<family> columns."""
    parts = []
    for y in test_years:
        ts, te = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        tr = train_mask(d, ts)
        te_m = ((d["entry_time"] >= ts) & (d["entry_time"] < te)).to_numpy()
        if tr.sum() < 40 or te_m.sum() == 0 or d.loc[tr, "label"].nunique() < 2:
            raise ValueError(f"{y}: not enough training rows ({int(tr.sum())})")
        part = d.loc[te_m].copy()
        part["test_year"], part["n_train"] = y, int(tr.sum())
        Xtr, ytr, Xte = d.loc[tr, features].to_numpy(float), d.loc[tr, "label"].to_numpy(int), d.loc[te_m, features].to_numpy(float)
        for fam in families:
            m = make_model(fam)
            m.fit(Xtr, ytr)
            part[f"p_{fam}"] = m.predict_proba(Xte)[:, 1]
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def wilson(w, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def select_topk(oof, col, k):
    """Boolean mask: within each test year, the top ceil(k*n) rows by predicted probability (ties broken by row order)."""
    take = np.zeros(len(oof), dtype=bool)
    for _, idx in oof.groupby("test_year").indices.items():
        n = int(np.ceil(k * len(idx)))
        order = idx[np.argsort(-oof[col].to_numpy()[idx], kind="mergesort")]
        take[order[:n]] = True
    return take


def random_pvalue(oof, take, n_draws=10000, seed=SEED):
    """P(win rate of a random same-size-per-year selection >= observed). Random draws are within each test year."""
    rng = np.random.default_rng(seed)
    y = oof["label"].to_numpy(int)
    groups = [(idx, int(take[idx].sum())) for _, idx in oof.groupby("test_year").indices.items()]
    obs = y[take].mean()
    hits = 0
    total_n = sum(k for _, k in groups)
    for _ in range(n_draws):
        w = sum(int(y[rng.choice(idx, size=k, replace=False)].sum()) for idx, k in groups)
        hits += (w / total_n) >= obs - 1e-12
    return (hits + 1) / (n_draws + 1)


def summarise(oof, families=FAMILIES, topk=TOPK, n_draws=10000):
    from sklearn.metrics import roc_auc_score
    rows = []
    scopes = [("ALL", np.ones(len(oof), dtype=bool))] + [(s, (oof["strategy"] == s).to_numpy()) for s in sorted(oof["strategy"].unique())]
    for fam in families:
        col = f"p_{fam}"
        for scope, m in scopes:
            sub = oof[m]
            y = sub["label"].to_numpy(int)
            auc = float(roc_auc_score(y, sub[col])) if len(set(y)) == 2 else float("nan")
            for k in topk:
                take = select_topk(oof, col, k)[m] if scope == "ALL" else select_topk(oof[m].reset_index(drop=True), col, k)
                ts = take
                n, w = int(ts.sum()), int(y[ts].sum())
                lo, hi = wilson(w, n)
                pval = random_pvalue(oof, select_topk(oof, col, k), n_draws) if scope == "ALL" else float("nan")
                rows.append(dict(family=fam, scope=scope, top_pct=int(k * 100), n_test=len(sub), base_win_rate=float(y.mean()),
                                 n_taken=n, win_rate=w / n if n else float("nan"), ci_lo=lo, ci_hi=hi,
                                 lift_pts=(w / n - y.mean()) * 100 if n else float("nan"),
                                 avg_r_taken=float(sub["r_gross"].to_numpy()[ts].mean()) if n else float("nan"),
                                 avg_r_all=float(sub["r_gross"].mean()), auc=auc, p_random=pval))
    return pd.DataFrame(rows)


def edge_verdict(summary, families=FAMILIES, min_lift=5.0, alpha=0.05, min_auc=0.55):
    out = []
    bonf = alpha / len(families)
    for fam in families:
        r = summary[(summary.family == fam) & (summary.scope == "ALL") & (summary.top_pct == 50)].iloc[0]
        a, b, c = r.lift_pts >= min_lift, r.p_random <= bonf, r.auc > min_auc
        out.append(dict(family=fam, top50_win_rate=r.win_rate, base_win_rate=r.base_win_rate, lift_pts=r.lift_pts, p_random=r.p_random,
                        auc=r.auc, lift_ge_5pts=bool(a), p_le_bonferroni=bool(b), auc_gt_055=bool(c), win_rate_improvement_established=bool(a and b and c)))
    return pd.DataFrame(out)


def power_table(base_win_rate, n_selected_now, lifts=(0.03, 0.05, 0.10, 0.15), alpha=0.0125, power=0.80):
    """Normal-approximation power for 'selected trades win more often than base': selected trades needed per lift, and the smallest
    lift detectable with n_selected_now trades. One-sided test at `alpha` (Bonferroni over four models), selection of fixed size."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(power)
    v = base_win_rate * (1 - base_win_rate)
    rows = [dict(lift_pts=l * 100, selected_trades_needed=int(np.ceil(z * z * v / (l * l)))) for l in lifts]
    return dict(rows=rows, min_detectable_lift_pts=float(z * np.sqrt(v / n_selected_now) * 100), n_selected_now=n_selected_now,
                alpha=alpha, power=power, base_win_rate=base_win_rate)
