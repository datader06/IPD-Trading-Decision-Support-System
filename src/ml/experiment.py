"""Experiment 1 orchestration (strategy-agnostic): per-fold fit / select / refit / predict / evaluate, pooled out-of-fold arms,
random-filter controls and champion selection. Pure functions over in-memory frames: no CLI, no file reading or writing, no
bootstrap, no dataset paths. The caller supplies the labeled frame, the frozen fold assignments and the trading calendar.

Per fold and per model family (frozen grids in ml/models.py):
  1. fit every configuration on the resolved FIT rows (XGBoost stops early on the VALIDATION rows) and score the VALIDATION rows;
  2. keep the configuration with the lowest validation log-loss (ties: first in the frozen order);
  3. T1 (primary): L = mean |r_gross| of LOSS rows of the training stage; the take rule is applied to the test probabilities;
  4. refit the chosen configuration on the resolved POOL rows (XGBoost: the round count found in step 1);
  5. predict ALL test rows (unresolved included) from features only; labels are joined afterwards, in the evaluation;
  6. evaluate the take set under every cost scenario (ml/evaluate.py).
T2 (validation-only search) is computed as a secondary diagnostic arm and never takes part in champion selection. Rows with
entry_time on or after the holdout start are dropped before anything is built or fitted. A strict-subset sensitivity run removes
rows from the (frozen) fold roles instead of rebuilding folds.
"""
import numpy as np
import pandas as pd

from ml import evaluate as E
from ml import models as M
from ml import registry as R
from ml import splits as S
from ml import thresholds as T

import costs  # noqa: E402  (src/ is on sys.path via the ml package modules)

PRIMARY_SCENARIO = "rt0.20"
MIN_RESOLVED_TAKES = 100
N_DRAWS = 1000
ARMS = ("B0", "B1", "ML", "ML_on_B0", "ML_T2")
REQUIRED = ("row_id", "ticker", "htf_key", "entry_time", "exit_time", "label_status", "is_training_label", "label", "outcome",
            "r_gross", "fill_price", "exit_price", "risk", "fill_time", "entry_price")


# ---------------------------------------------------------------------------------------------------------------------------
# pure model step: sees features and the labels of fit / validation / pool rows only, never the test labels
# ---------------------------------------------------------------------------------------------------------------------------
def fit_select_predict(family, X_fit, y_fit, X_val, y_val, X_pool, y_pool, X_test):
    from sklearn.metrics import log_loss
    candidates, best = [], None
    for cfg in M.frozen_configs(family):
        m = M.fit(cfg, X_fit, y_fit, X_val, y_val) if family == "xgboost" else M.fit(cfg, X_fit, y_fit)
        p_val = M.predict_proba(m, X_val)
        ll = float(log_loss(y_val, p_val, labels=[0, 1]))
        candidates.append(dict(config=cfg.name, val_log_loss=ll, best_rounds=m.best_rounds))
        if best is None or ll < best[0]:  # strict: ties keep the first configuration in the frozen order
            best = (ll, cfg, m, p_val)
    ll, cfg, m, p_val = best
    final = M.fit(cfg, X_pool, y_pool, n_rounds=m.best_rounds) if family == "xgboost" else M.fit(cfg, X_pool, y_pool)
    return dict(config=cfg.name, val_log_loss=ll, best_rounds=m.best_rounds, candidates=candidates, p_val=p_val,
                p_test=M.predict_proba(final, X_test))


def _net_r_positional(df, scenario=PRIMARY_SCENARIO):
    """Net R per row (aligned with df rows) for WIN / LOSS rows, NaN elsewhere; same formula as evaluate / Phase A."""
    cm = {c.name: c for c in costs.scenarios(0.0)}[scenario]
    out = np.full(len(df), np.nan)
    for i in np.flatnonzero(df["outcome"].isin(E.RESOLVED).to_numpy()):
        out[i] = cm.net_r(df["r_gross"].iat[i], df["fill_price"].iat[i], df["exit_price"].iat[i], df["risk"].iat[i])
    return out


# ---------------------------------------------------------------------------------------------------------------------------
# fold set-up and checks
# ---------------------------------------------------------------------------------------------------------------------------
def build_checked_folds(df, frozen_assignments, trading_days=None, cfg=S.CFG):
    """Drop holdout rows, rebuild the folds with the splits module, require every leakage check to pass and the rebuilt roles to
    equal the frozen assignments exactly. Returns (folds, prepared frame)."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    work = df[pd.to_datetime(df["entry_time"]) < cfg.holdout_start]
    d = S.prepare(work)
    if d["row_id"].duplicated().any():
        raise ValueError("row_id must be unique")
    folds, d = S.build_folds(d, cfg, trading_days)
    failed = [k for k, (ok, _) in S.check_folds(folds, d, cfg, trading_days).items() if not ok]
    if failed:
        raise ValueError(f"fold leakage checks failed: {failed}")
    key = lambda t: set(map(tuple, t[["fold", "row_id", "role"]].itertuples(index=False, name=None)))  # noqa: E731
    rebuilt, frozen = S.assignments(folds, d), frozen_assignments
    if len(rebuilt) != len(frozen) or key(rebuilt) != key(frozen):
        raise ValueError("rebuilt fold roles do not match the frozen fold assignments")
    if (d["entry_time"] >= cfg.holdout_start).any():
        raise AssertionError("holdout rows remain")
    return folds, d


def _apply_exclusion(folds, d, exclude_row_ids):
    """Strict-subset sensitivity: remove rows from every fold role (fold boundaries are preserved)."""
    ex = d["row_id"].isin(set(exclude_row_ids)).to_numpy()
    if not ex.any():
        return {f.name: {k: v for k, v in f.idx.items()} for f in folds}
    return {f.name: {k: v[~ex[v]] for k, v in f.idx.items()} for f in folds}


def _sample_checks(d, idx, name, cfg):
    y = d["label_status"].to_numpy()
    need_w = cfg.min_wins_per_feature * cfg.n_features
    bad = []
    for role in ("fit", "pool"):
        r = idx[role]
        w, l = int((y[r] == "WIN").sum()), int((y[r] == "LOSS").sum())
        if w + l < cfg.min_train_resolved:
            bad.append(f"{name}: {role} resolved {w + l} < {cfg.min_train_resolved}")
        if w < need_w:
            bad.append(f"{name}: {role} wins {w} < {need_w}")
    t = y[idx["test"]]
    if int(np.isin(t, ["WIN", "LOSS"]).sum()) < cfg.min_test_resolved:
        bad.append(f"{name}: test resolved < {cfg.min_test_resolved}")
    if bad:
        raise ValueError("minimum-sample checks failed: " + "; ".join(bad))


# ---------------------------------------------------------------------------------------------------------------------------
# champion selection
# ---------------------------------------------------------------------------------------------------------------------------
def select_champion(ml_metrics_by_family, min_resolved_takes=MIN_RESOLVED_TAKES):
    """ml_metrics_by_family: {family: evaluate() metrics at the primary scenario for the pooled T1 arm}. Eligible: at least
    min_resolved_takes resolved takes. Order: higher expectancy, higher total R, lower max drawdown, higher profit factor (NaN
    ranks last on that key), then the frozen family order. Returns {"champion", "ranking", "reason"}."""
    order = {f: i for i, f in enumerate(M.FAMILIES)}
    rows = []
    for fam, m in ml_metrics_by_family.items():
        pf = m["profit_factor"]
        eligible = m["n_resolved_taken"] >= min_resolved_takes and np.isfinite(m["expectancy"])
        rows.append(dict(family=fam, eligible=bool(eligible), n_resolved_taken=m["n_resolved_taken"], expectancy=m["expectancy"],
                         total_r=m["total_r"], max_dd=m["max_dd"], profit_factor=pf))
    elig = [r for r in rows if r["eligible"]]
    key = lambda r: (-r["expectancy"], -r["total_r"], r["max_dd"], np.inf if np.isnan(r["profit_factor"]) else -r["profit_factor"],  # noqa: E731
                     order.get(r["family"], len(order)))
    ranking = sorted(elig, key=key) + sorted([r for r in rows if not r["eligible"]], key=lambda r: order.get(r["family"], len(order)))
    if not elig:
        return dict(champion=None, ranking=ranking, reason=f"no model has {min_resolved_takes} resolved takes")
    return dict(champion=ranking[0]["family"], ranking=ranking, reason="ranked by expectancy, total R, max drawdown, profit factor")


# ---------------------------------------------------------------------------------------------------------------------------
# experiment
# ---------------------------------------------------------------------------------------------------------------------------
def run_experiment(df, frozen_assignments, feature_columns=None, cost_column="cost_in_r_rt0.20", baseline_column="is_b0",
                   trading_days=None, families=M.FAMILIES, exclude_row_ids=None, n_draws=N_DRAWS, seed=M.SEED,
                   min_resolved_takes=MIN_RESOLVED_TAKES, cfg=S.CFG):
    """Run the walk-forward experiment on a labeled frame. Returns a structured dict:
    meta, folds (per-fold selections and test metrics), oof (per-row out-of-fold frame), pooled (arms x scenarios per family plus
    the baselines), b2 (random-filter distributions and summaries per family), champion."""
    cols = list(R.MODEL_COLUMNS if feature_columns is None else feature_columns)
    R.assert_no_forbidden(cols)
    if feature_columns is None or cols == list(R.MODEL_COLUMNS):
        cols = list(R.MODEL_COLUMNS)
    for extra in (cost_column, baseline_column):
        if extra not in df.columns:
            raise ValueError(f"missing column {extra!r}")
    n_in = len(df)
    folds, d = build_checked_folds(df, frozen_assignments, trading_days, cfg)
    idx_by_fold = _apply_exclusion(folds, d, exclude_row_ids or ())
    X_all = d[cols].to_numpy(dtype=float)
    y_all = d["label"].to_numpy()
    outcome, r_gross = d["outcome"].to_numpy(dtype=object), d["r_gross"].to_numpy(dtype=float)
    cost, is_base = d[cost_column].to_numpy(dtype=float), d[baseline_column].to_numpy(dtype=bool)

    fold_results, oof_parts = [], []
    for f in folds:
        idx = idx_by_fold[f.name]
        _sample_checks(d, idx, f.name, cfg)
        fit, val, pool, test = idx["fit"], idx["validation"], idx["pool"], idx["test"]
        for nm, r in (("fit", fit), ("validation", val), ("pool", pool)):  # only resolved rows are ever fitted or validated
            if not np.isin(outcome[r], E.RESOLVED).all() or not d["is_training_label"].to_numpy()[r].all():
                raise AssertionError(f"{f.name}: {nm} rows include unresolved rows")
        yfit, yval, ypool = (y_all[r].astype(int) for r in (fit, val, pool))
        L_fit = T.compute_l_from_training(outcome[fit], r_gross[fit])
        L_pool = T.compute_l_from_training(outcome[pool], r_gross[pool])
        be_fit = T.t1_breakeven(L_fit, float(cost[fit].mean()))
        net_val = _net_r_positional(d.iloc[val])
        test_df = d.iloc[test].reset_index(drop=True)
        prep = E.Prepared(test_df)
        tb = is_base[test]
        res = dict(fold=f.name, test_start=f.test_start, test_end=f.test_end, n_fit=len(fit), n_validation=len(val),
                   n_pool=len(pool), n_test=len(test), L_fit=L_fit, L_pool=L_pool,
                   baselines={"B0": E.evaluate(prep, tb), "B1": E.evaluate(prep, np.ones(len(test), dtype=bool))}, models={})
        part = pd.DataFrame(dict(fold=f.name, row_id=d["row_id"].to_numpy()[test], pos=test))
        for fam in families:
            out = fit_select_predict(fam, X_all[fit], yfit, X_all[val], yval, X_all[pool], ypool, X_all[test])
            p_test = out["p_test"]
            take = T.apply_t1(p_test, cost[test], L_pool)                       # primary T1
            t2 = T.select_t2(out["p_val"], net_val, np.ones(len(val), dtype=bool), be_fit)  # secondary diagnostic, validation only
            take2 = p_test > t2.threshold if t2.threshold is not None else np.zeros(len(test), dtype=bool)
            res["models"][fam] = dict(
                config=out["config"], val_log_loss=out["val_log_loss"], best_rounds=out["best_rounds"], candidates=out["candidates"],
                t1_breakeven_fit=be_fit, n_take_t1=int(take.sum()), n_take_t2=int(take2.sum()),
                t2=dict(threshold=t2.threshold, expectancy=t2.expectancy, n_taken=t2.n_taken, min_takes=t2.min_takes),
                arms={"ML": E.evaluate(prep, take), "ML_on_B0": E.evaluate(prep, take & tb), "ML_T2": E.evaluate(prep, take2)},
                ml=E.ml_metrics(test_df["outcome"].to_numpy(dtype=object), p_test, take, base_rate=float(ypool.mean())))
            part[f"p_{fam}"], part[f"take_{fam}"], part[f"take_t2_{fam}"] = p_test, take, take2
        fold_results.append(res)
        oof_parts.append(part)

    oof_idx = pd.concat(oof_parts, ignore_index=True)
    pos = oof_idx["pos"].to_numpy()
    oof = d.iloc[pos].reset_index(drop=True).assign(fold=oof_idx["fold"].to_numpy())
    for c in oof_idx.columns:
        if c.startswith(("p_", "take_")):
            oof[c] = oof_idx[c].to_numpy()
    pre = E.Prepared(oof)
    ob = oof[baseline_column].to_numpy(dtype=bool)
    pooled = {"baselines": {"B0": E.evaluate(pre, ob), "B1": E.evaluate(pre, np.ones(len(oof), dtype=bool))}, "models": {}}
    b2 = {}
    folds_arr = oof["fold"].to_numpy()
    for fam in families:
        t1, t2m = oof[f"take_{fam}"].to_numpy(dtype=bool), oof[f"take_t2_{fam}"].to_numpy(dtype=bool)
        pooled["models"][fam] = dict(arms={"ML": E.evaluate(pre, t1), "ML_on_B0": E.evaluate(pre, t1 & ob), "ML_T2": E.evaluate(pre, t2m)},
                                     ml=E.ml_metrics(oof["outcome"].to_numpy(dtype=object), oof[f"p_{fam}"].to_numpy(), t1))
        counts = {fn: int(t1[folds_arr == fn].sum()) for fn in sorted(set(folds_arr.tolist()))}
        dist = E.random_filter_distribution(pre, counts, n_draws, seed, groups=folds_arr)
        ml_exp = pooled["models"][fam]["arms"]["ML"][PRIMARY_SCENARIO]["expectancy"]
        e = dist[PRIMARY_SCENARIO]["expectancy"]
        e = e[np.isfinite(e)]
        b2[fam] = dict(draws=dist, n_take_by_fold=counts, ml_expectancy_percentile=float((e < ml_exp).mean()) if len(e) and np.isfinite(ml_exp) else float("nan"),
                       expectancy_mean=float(e.mean()) if len(e) else float("nan"),
                       expectancy_p05_p95=(float(np.percentile(e, 5)), float(np.percentile(e, 95))) if len(e) else (float("nan"), float("nan")))
    champion = select_champion({fam: pooled["models"][fam]["arms"]["ML"][PRIMARY_SCENARIO] for fam in families}, min_resolved_takes)
    meta = dict(n_input_rows=n_in, n_rows_used=len(d), holdout_rows_excluded=n_in - len(d), n_excluded_by_request=len(set(exclude_row_ids or ())),
                feature_columns=cols, families=list(families), seed=seed, n_draws=n_draws, primary_scenario=PRIMARY_SCENARIO,
                folds=[f.name for f in folds])
    return dict(meta=meta, folds=fold_results, oof=oof, pooled=pooled, b2=b2, champion=champion)
