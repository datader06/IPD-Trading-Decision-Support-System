"""P&L-oriented ML arms on a ml_core standard frame (docs/EXPERIMENT_6_PREREGISTRATION.md): expected-R filter and ML risk sizing.

All P&L is gross (costs excluded by decision). `rs` = gross rupees of the trade at its baseline risk, `r_gross` = gross R.
"""
import numpy as np
import pandas as pd

from ml_core import walkforward as W

SEED = 42
REGRESSORS = ("ridge", "hist_gb_reg")
CLASSIFIERS = ("logreg", "hist_gb")


def make_regressor(name):
    if name == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if name == "hist_gb_reg":
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(max_depth=2, max_iter=60, learning_rate=0.05, l2_regularization=1.0, early_stopping=False,
                                             random_state=SEED)
    raise ValueError(name)


def walk_forward_pnl(d, features, test_years):
    """Out-of-fold frame with pred_<regressor> (expected R) and p_<classifier> (win probability) plus base_win (training win rate)."""
    parts = []
    for y in test_years:
        ts, te = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        tr = W.train_mask(d, ts)
        te_m = ((d["entry_time"] >= ts) & (d["entry_time"] < te)).to_numpy()
        if tr.sum() < 40 or te_m.sum() == 0:
            raise ValueError(f"{y}: not enough training rows")
        part = d.loc[te_m].copy()
        part["test_year"], part["n_train"], part["base_win"] = y, int(tr.sum()), float(d.loc[tr, "label"].mean())
        Xtr, Xte = d.loc[tr, features].to_numpy(float), d.loc[te_m, features].to_numpy(float)
        for name in REGRESSORS:
            m = make_regressor(name).fit(Xtr, d.loc[tr, "r_gross"].to_numpy(float))
            part[f"pred_{name}"] = m.predict(Xte)
        for name in CLASSIFIERS:
            m = W.make_model(name).fit(Xtr, d.loc[tr, "label"].to_numpy(int))
            part[f"p_{name}"] = m.predict_proba(Xte)[:, 1]
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def multipliers(oof, clf):
    return np.clip(oof[f"p_{clf}"].to_numpy() / oof["base_win"].to_numpy(), 0.5, 1.5)


def _year_rows(oof):
    return [(y, idx) for y, idx in oof.groupby("test_year").indices.items()]


def summarise(oof, n_draws=10000, seed=SEED):
    rs, r = oof["rs"].to_numpy(float), oof["r_gross"].to_numpy(float)
    rng = np.random.default_rng(seed)
    base = dict(arm="take all (v6)", scope="pooled", n=len(oof), pnl_rs=rs.sum(), pnl_r=r.sum(), mean_r=r.mean(), per_unit_risk_r=r.mean(), p_random=np.nan, effect=np.nan)
    rows = [base]
    for y, idx in _year_rows(oof):
        rows.append(dict(arm="take all (v6)", scope=str(y), n=len(idx), pnl_rs=rs[idx].sum(), pnl_r=r[idx].sum(), mean_r=r[idx].mean(),
                         per_unit_risk_r=r[idx].mean(), p_random=np.nan, effect=np.nan))
    verdict = []
    # A: expected-R filter
    for name in REGRESSORS:
        take = oof[f"pred_{name}"].to_numpy() > 0
        sel_mean = r[take].mean() if take.any() else np.nan
        effect = sel_mean - r.mean()
        groups = [(idx, int(take[idx].sum())) for _, idx in _year_rows(oof)]
        hits = 0
        for _ in range(n_draws):
            tot = sum(r[rng.choice(idx, size=k, replace=False)].sum() for idx, k in groups if k)
            hits += (tot / max(take.sum(), 1)) >= sel_mean - 1e-12
        p = (hits + 1) / (n_draws + 1)
        yrs_ok = 0
        for y, idx in _year_rows(oof):
            t = take[idx]
            yrs_ok += int(t.any() and r[idx][t].mean() > r[idx].mean())
        rows.append(dict(arm=f"A expected-R filter: {name}", scope="pooled", n=int(take.sum()), pnl_rs=rs[take].sum(), pnl_r=r[take].sum(), mean_r=sel_mean,
                         per_unit_risk_r=sel_mean, p_random=p, effect=effect))
        for y, idx in _year_rows(oof):
            t = take[idx]
            rows.append(dict(arm=f"A expected-R filter: {name}", scope=str(y), n=int(t.sum()), pnl_rs=rs[idx][t].sum(), pnl_r=r[idx][t].sum(),
                             mean_r=r[idx][t].mean() if t.any() else np.nan, per_unit_risk_r=r[idx][t].mean() if t.any() else np.nan, p_random=np.nan, effect=np.nan))
        verdict.append(dict(arm="A", model=name, effect=effect, effect_target=0.15, p_random=p, years_right_sign=yrs_ok,
                            improved=bool(effect >= 0.15 and p <= 0.025 and yrs_ok >= 2)))
    # B: ML sizing
    for name in CLASSIFIERS:
        m = multipliers(oof, name)
        unit = (m * r).sum() / m.sum()
        effect = unit / r.mean() - 1 if r.mean() > 0 else np.nan
        hits = 0
        for _ in range(n_draws):
            mm = m.copy()
            for _, idx in _year_rows(oof):
                mm[idx] = rng.permutation(m[idx])
            hits += ((mm * r).sum() / mm.sum()) >= unit - 1e-12
        p = (hits + 1) / (n_draws + 1)
        yrs_ok = 0
        for y, idx in _year_rows(oof):
            yrs_ok += int(((m[idx] * r[idx]).sum() / m[idx].sum()) > r[idx].mean())
        rows.append(dict(arm=f"B ML sizing: {name}", scope="pooled", n=len(oof), pnl_rs=(m * rs).sum(), pnl_r=(m * r).sum(), mean_r=(m * r).sum() / len(oof),
                         per_unit_risk_r=unit, p_random=p, effect=effect))
        for y, idx in _year_rows(oof):
            rows.append(dict(arm=f"B ML sizing: {name}", scope=str(y), n=len(idx), pnl_rs=(m[idx] * rs[idx]).sum(), pnl_r=(m[idx] * r[idx]).sum(),
                             mean_r=(m[idx] * r[idx]).sum() / len(idx), per_unit_risk_r=(m[idx] * r[idx]).sum() / m[idx].sum(), p_random=np.nan, effect=np.nan))
        verdict.append(dict(arm="B", model=name, effect=effect, effect_target=0.10, p_random=p, years_right_sign=yrs_ok,
                            improved=bool(np.isfinite(effect) and effect >= 0.10 and p <= 0.025 and yrs_ok >= 2), avg_multiplier=float(m.mean())))
    return pd.DataFrame(rows), pd.DataFrame(verdict)
