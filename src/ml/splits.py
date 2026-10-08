"""Phase B walk-forward validation framework (folds only: no model fitting, no thresholds, no feature or label changes).

Frozen design
  * rows = the labeled dataset (src/ml/labels.py); model fitting uses is_training_label rows only (WIN = 1, LOSS = 0);
    AMBIGUOUS / CENSORED / OPEN / NOFILL rows are never fit on (they stay in test windows for later evaluation).
  * expanding walk-forward, test windows 2023H1 ... 2025H2 (half-years by entry_time, [start, end));
  * inner validation = the last 6 calendar months of the training window;
  * embargo = the 5 trading days (NIFTY trading calendar) before a boundary: resolved rows entered in that span are dropped;
  * purge = resolved rows entered before the embargo whose outcome (exit_time) reaches the boundary or later are dropped;
  * 2026-01-01 onward is the untouched holdout: no row with entry_time >= holdout_start is a fit, validation or test row of any
    fold, and no test window extends past it;
  * siblings: rows of one HTF zone (ticker + htf_key) belong to the side of the group's earliest entry; a later member that
    would land on the other side of a boundary is removed from that side (test: `sibling_removed`; validation: `val_sibling`).
Two boundaries per fold, same rules at both:
  test boundary       B = test start:        training pool (= fit + validation) vs test
  validation boundary V = B - 6 months:      fit vs validation
Training pool = what the final model of the fold is refit on after hyperparameters were chosen on validation.
No random split anywhere. Everything is a pure function of the dataframe, the config and the trading calendar.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml import registry as R

DEV_START = pd.Timestamp("2021-01-01")
HOLDOUT_START = pd.Timestamp("2026-01-01")
WINDOWS = (("2023H1", "2023-01-01", "2023-07-01"), ("2023H2", "2023-07-01", "2024-01-01"),
           ("2024H1", "2024-01-01", "2024-07-01"), ("2024H2", "2024-07-01", "2025-01-01"),
           ("2025H1", "2025-01-01", "2025-07-01"), ("2025H2", "2025-07-01", "2026-01-01"))


@dataclass(frozen=True)
class WFConfig:
    windows: tuple = WINDOWS
    dev_start: pd.Timestamp = DEV_START
    holdout_start: pd.Timestamp = HOLDOUT_START
    val_months: int = 6
    embargo_days: int = 5
    n_features: int = len(R.MODEL_COLUMNS)
    min_train_resolved: int = 300
    min_wins_per_feature: int = 10
    min_test_resolved: int = 100


CFG = WFConfig()


def embargo_start(trading_days, boundary, n=5):
    """Midnight of the n-th trading day before `boundary` (trading days strictly earlier than the boundary date)."""
    d = np.asarray(trading_days, dtype="datetime64[ns]")
    k = int(np.searchsorted(d, np.datetime64(pd.Timestamp(boundary).normalize()), side="left"))
    if k < n:
        raise ValueError(f"fewer than {n} trading days before {boundary}")
    return pd.Timestamp(d[k - n])


def default_trading_days():
    from ml import features as F
    return F.load_nifty()["timestamp"].dt.normalize().to_numpy(dtype="datetime64[ns]")


def prepare(df):
    """Sorted copy with the helper columns the fold builder needs. Input needs: row_id, ticker, htf_key, entry_time, exit_time,
    label_status, is_training_label, label."""
    d = df.copy()
    d["entry_time"] = pd.to_datetime(d["entry_time"])
    d["exit_time"] = pd.to_datetime(d["exit_time"])
    d = d.sort_values(["entry_time", "ticker", "row_id"], kind="mergesort").reset_index(drop=True)
    d["is_training_label"] = d["is_training_label"].astype(bool)
    bad = d[d["is_training_label"] & d["exit_time"].isna()]
    if len(bad):
        raise ValueError(f"{len(bad)} resolved rows without exit_time (cannot purge)")
    d["_gfirst"] = d.groupby(["ticker", "htf_key"])["entry_time"].transform("min")
    return d


@dataclass
class Fold:
    name: str
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    val_start: pd.Timestamp
    test_embargo_start: pd.Timestamp
    val_embargo_start: pd.Timestamp
    idx: dict = field(default_factory=dict)  # role -> integer positions into the prepared dataframe


ROLES = ("fit", "validation", "test", "embargo", "purged", "val_embargo", "val_purged", "sibling_removed", "val_sibling",
         "unresolved_excluded")


def build_folds(df, cfg=CFG, trading_days=None):
    """Deterministic folds. `df` as produced by prepare(); returns (list of Fold, prepared df)."""
    d = df if "_gfirst" in df.columns else prepare(df)
    td = default_trading_days() if trading_days is None else trading_days
    e, x, gf = d["entry_time"], d["exit_time"], d["_gfirst"]
    resolved = d["is_training_label"].to_numpy()
    folds = []
    for name, s, t in cfg.windows:
        ts, te = pd.Timestamp(s), pd.Timestamp(t)
        if te > cfg.holdout_start:
            raise ValueError(f"{name}: test window ends after the holdout start")
        vs = ts - pd.DateOffset(months=cfg.val_months)
        t_emb, v_emb = embargo_start(td, ts, cfg.embargo_days), embargo_start(td, vs, cfg.embargo_days)
        in_test = ((e >= ts) & (e < te)).to_numpy()
        sib = in_test & (gf < ts).to_numpy()
        test = in_test & ~sib
        cand = resolved & (e < ts).to_numpy() & (e >= cfg.dev_start).to_numpy()
        emb = cand & (e >= t_emb).to_numpy()
        purged = cand & ~emb & (x >= ts).to_numpy()
        pool = cand & ~emb & ~purged
        val_all = pool & (e >= vs).to_numpy()
        val_sib = val_all & (gf < vs).to_numpy()
        val = val_all & ~val_sib
        fit_c = pool & (e < vs).to_numpy()
        v_emb_m = fit_c & (e >= v_emb).to_numpy()
        v_pur = fit_c & ~v_emb_m & (x >= vs).to_numpy()
        fit = fit_c & ~v_emb_m & ~v_pur
        unres = (~resolved) & (e < ts).to_numpy() & (e >= cfg.dev_start).to_numpy()
        f = Fold(name, ts, te, vs, t_emb, v_emb)
        f.idx["pool"] = np.flatnonzero(pool)  # refit pool = every row eligible for the final fold model (not an assignment role)
        for role, m in (("fit", fit), ("validation", val), ("test", test), ("embargo", emb), ("purged", purged),
                        ("val_embargo", v_emb_m), ("val_purged", v_pur), ("sibling_removed", sib), ("val_sibling", val_sib),
                        ("unresolved_excluded", unres)):
            f.idx[role] = np.flatnonzero(m)
        folds.append(f)
    return folds, d


def _wl(d, pos):
    s = d.iloc[pos]
    return int((s["label_status"] == "WIN").sum()), int((s["label_status"] == "LOSS").sum())


def fold_table(folds, d, cfg=CFG):
    """One row per fold: periods, counts, purge / embargo and the minimum-sample verdicts."""
    rows = []
    for f in folds:
        fit, val, test = f.idx["fit"], f.idx["validation"], f.idx["test"]
        pool = f.idx["pool"]
        fw, fl = _wl(d, fit)
        vw, vl = _wl(d, val)
        pw, pl = _wl(d, pool)
        te = d.iloc[test]
        tw, tl = _wl(d, test[d.iloc[test]["is_training_label"].to_numpy()]) if len(test) else (0, 0)
        need_w = cfg.min_wins_per_feature * cfg.n_features
        rows.append(dict(
            fold=f.name,
            fit_period=f"{cfg.dev_start.date()} .. {f.val_start.date()}", validation_period=f"{f.val_start.date()} .. {f.test_start.date()}",
            test_period=f"{f.test_start.date()} .. {f.test_end.date()}",
            val_embargo_start=f.val_embargo_start.date(), test_embargo_start=f.test_embargo_start.date(),
            fit_n=len(fit), fit_wins=fw, fit_losses=fl, val_n=len(val), val_wins=vw, val_losses=vl,
            pool_n=len(pool), pool_wins=pw, pool_losses=pl,
            test_rows=len(test), test_resolved=tw + tl, test_wins=tw, test_losses=tl,
            test_ambiguous=int((te["label_status"] == "AMBIGUOUS").sum()), test_censored=int((te["label_status"] == "CENSORED").sum()),
            test_open_nofill=int(te["label_status"].isin(["OPEN", "NOFILL"]).sum()),
            embargo_n=len(f.idx["embargo"]), purged_n=len(f.idx["purged"]), val_embargo_n=len(f.idx["val_embargo"]),
            val_purged_n=len(f.idx["val_purged"]), sibling_removed_n=len(f.idx["sibling_removed"]),
            val_sibling_n=len(f.idx["val_sibling"]), unresolved_excluded_n=len(f.idx["unresolved_excluded"]),
            test_rows_exiting_in_holdout=int((te["exit_time"] >= cfg.holdout_start).sum()),
            pool_ok_resolved=(pw + pl) >= cfg.min_train_resolved, pool_ok_wins=pw >= need_w,
            fit_ok_resolved=(fw + fl) >= cfg.min_train_resolved, fit_ok_wins=fw >= need_w,
            test_ok_resolved=(tw + tl) >= cfg.min_test_resolved,
        ))
    return pd.DataFrame(rows)


def assignments(folds, d):
    """Long table fold / row_id / role for every row that plays a role in a fold (holdout rows never appear)."""
    out = []
    for f in folds:
        for role in ROLES:
            pos = f.idx[role]
            if len(pos):
                out.append(pd.DataFrame(dict(fold=f.name, row_id=d["row_id"].to_numpy()[pos], role=role,
                                             entry_time=d["entry_time"].to_numpy()[pos])))
    return pd.concat(out, ignore_index=True)


def check_folds(folds, d, cfg=CFG, trading_days=None):
    """Explicit leakage checks. Returns {check name: (passed, detail)}; callers assert all passed."""
    td = default_trading_days() if trading_days is None else trading_days
    e, x = d["entry_time"], d["exit_time"]
    res = {}

    def ok(name, cond, detail=""):
        res[name] = (bool(cond), detail)

    def pos(f, *roles):
        return np.concatenate([f.idx[r] for r in roles]) if roles else np.array([], dtype=int)

    ok("folds_are_chronological", all(a.test_end <= b.test_start for a, b in zip(folds, folds[1:])))
    ok("windows_end_before_holdout", all(f.test_end <= cfg.holdout_start for f in folds))
    holdout_rows = set(np.flatnonzero((e >= cfg.holdout_start).to_numpy()))
    all_used = set()
    for f in folds:
        all_used |= set(pos(f, "fit", "validation", "test"))
    ok("holdout_rows_never_in_any_fit_validation_or_test", not (holdout_rows & all_used), f"holdout rows {len(holdout_rows)}")
    ok("no_row_entered_on_or_after_holdout_start_in_any_role",
       all(not (set(f.idx[r]) & holdout_rows) for f in folds for r in ROLES))
    for f in folds:
        fit, val, test = f.idx["fit"], f.idx["validation"], f.idx["test"]
        tr = f.idx["pool"]
        n = f.name
        ok(f"{n}: roles_disjoint", len(set(fit) & set(val)) == 0 and len(set(tr) & set(test)) == 0)
        ok(f"{n}: fit_and_validation_inside_pool", set(fit) <= set(tr) and set(val) <= set(tr))
        fitted = np.union1d(np.union1d(tr, fit), val)  # every row a model could be fitted or validated on
        ok(f"{n}: only_resolved_rows_are_fitted", bool(d["is_training_label"].to_numpy()[fitted].all())
           and set(d["label_status"].to_numpy()[fitted]) <= {"WIN", "LOSS"})
        ok(f"{n}: no_test_information_in_training_entries", len(tr) == 0 or e.iloc[tr].max() < f.test_embargo_start,
           f"max train entry {e.iloc[tr].max()} < embargo start {f.test_embargo_start}")
        ok(f"{n}: purge_respected_outcomes_end_before_test_start", len(tr) == 0 or x.iloc[tr].max() < f.test_start,
           f"max train exit {x.iloc[tr].max()} < test start {f.test_start}")
        ok(f"{n}: embargo_respected", not ((e.iloc[tr] >= f.test_embargo_start) & (e.iloc[tr] < f.test_start)).any())
        emb_days = int(((np.asarray(td, dtype="datetime64[ns]") >= np.datetime64(f.test_embargo_start))
                        & (np.asarray(td, dtype="datetime64[ns]") < np.datetime64(f.test_start))).sum())
        ok(f"{n}: embargo_spans_exactly_{cfg.embargo_days}_trading_days", emb_days == cfg.embargo_days, f"{emb_days} trading days")
        ok(f"{n}: purged_rows_cross_test_start", len(f.idx["purged"]) == 0 or
           ((x.iloc[f.idx["purged"]] >= f.test_start).all() and (e.iloc[f.idx["purged"]] < f.test_embargo_start).all()))
        ok(f"{n}: embargoed_rows_lie_in_embargo_span", len(f.idx["embargo"]) == 0 or
           ((e.iloc[f.idx["embargo"]] >= f.test_embargo_start) & (e.iloc[f.idx["embargo"]] < f.test_start)).all())
        ok(f"{n}: test_rows_inside_window", len(test) == 0 or
           ((e.iloc[test] >= f.test_start) & (e.iloc[test] < f.test_end)).all())
        ok(f"{n}: validation_is_last_{cfg.val_months}_months_of_training",
           len(val) == 0 or ((e.iloc[val] >= f.val_start) & (e.iloc[val] < f.test_start)).all())
        ok(f"{n}: fit_ends_before_validation_with_embargo_and_purge",
           len(fit) == 0 or (e.iloc[fit].max() < f.val_embargo_start and x.iloc[fit].max() < f.val_start))
        gtr = set(zip(d["ticker"].to_numpy()[tr], d["htf_key"].to_numpy()[tr]))
        gte = set(zip(d["ticker"].to_numpy()[test], d["htf_key"].to_numpy()[test]))
        ok(f"{n}: no_htf_zone_group_on_both_sides", not (gtr & gte), f"{len(gtr & gte)} shared")
        ok(f"{n}: expanding_window_starts_at_dev_start", len(tr) == 0 or e.iloc[tr].min() >= cfg.dev_start)
    # expanding: each later pool reaches at least as far back and as far forward as the previous one
    for a, b in zip(folds, folds[1:]):
        ok(f"{b.name}: pool_is_expanding_vs_{a.name}", len(set(a.idx["pool"]) - set(b.idx["pool"]) - set(b.idx["purged"])
                                                         - set(b.idx["embargo"])) == 0)
    return res
