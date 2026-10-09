"""Experiment 1 final report (reporting layer only): month-block bootstrap, capital-constrained and concurrency views, per-year results.

  python scripts/run_phase_b_report.py

Reads only the existing Experiment 1 outputs (results/nogit-145d6302/phase_b/experiment_1/{primary,strict_htf}/oof_predictions.csv
after verifying their SHA-256 against experiment_1/manifest.json) and writes experiment_1/report/ (report.md, CSV tables, manifest).
It trains nothing, changes no take set and never touches the 2026 holdout (the out-of-fold files contain 2023-2025 test rows only).
Methodology: PHASE_B_PLAN.md section 13 / EXPERIMENT_1_PREREGISTRATION.md: paired month-block bootstrap of ML minus B0 and ML minus
B1, pooled 2023-2025 out-of-fold stream, T1 take sets, gross and 0.10 / 0.20 / 0.30% round-trip costs, portfolio.capital_constrained
and portfolio.concurrency from Phase A.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import portfolio as P  # noqa: E402
from ml import evaluate as E  # noqa: E402
from ml import models as M  # noqa: E402

EXP = ROOT / "results" / "nogit-145d6302" / "phase_b" / "experiment_1"
OUT = EXP / "report"
DATASETS = ("primary", "strict_htf")
SCENARIOS = ("gross", "rt0.10", "rt0.20", "rt0.30")
PRIMARY = "rt0.20"
METRICS = ("expectancy", "win_rate", "profit_factor", "total_r", "max_dd")
N_BOOT = 2000
SEED = M.SEED
TIME_COLS = ["entry_time", "exit_time", "fill_time", "htf_formed_at"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")


def f3(v, nd=3):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def md_table(df, floats=3):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append(f3(float(v), floats) if isinstance(v, (float, np.floating)) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load(ds):
    p = EXP / ds / "oof_predictions.csv"
    return pd.read_csv(p, parse_dates=TIME_COLS, float_precision="round_trip")


def arms_of(oof):
    arms = {"B0": oof["is_b0"].to_numpy(dtype=bool), "B1": np.ones(len(oof), dtype=bool)}
    for fam in M.FAMILIES:
        arms[f"ML:{fam}"] = oof[f"take_{fam}"].to_numpy(dtype=bool)
    return arms


# ---------------------------------------------------------------------------------------------------------------------------
def seq_metrics(r, is_win):
    n = len(r)
    if n == 0:
        return dict(expectancy=np.nan, win_rate=np.nan, profit_factor=np.nan, total_r=0.0, max_dd=0.0)
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return dict(expectancy=float(r.mean()), win_rate=float(is_win.mean()), profit_factor=float(pos / neg) if neg > 0 else np.nan,
                total_r=float(r.sum()), max_dd=float(P.max_drawdown(r)))


def month_block_bootstrap(oof, arms, n_boot=N_BOOT, seed=SEED):
    """Paired month-block bootstrap: months (by entry month) are resampled with replacement; each draw concatenates the drawn
    months' resolved trades (each month in portfolio order) and scores every arm on the SAME draw. Returns a long table of
    ML-minus-B0 and ML-minus-B1 differences with percentile 95% intervals."""
    pr = E.Prepared(oof)
    ent = oof["entry_time"].dt.to_period("M")
    codes = pd.factorize(ent, sort=True)[0]
    mo = codes[pr.pos]                                  # month of each resolved row, in portfolio order
    n_m = int(codes.max()) + 1
    by_month = [np.flatnonzero(mo == m) for m in range(n_m)]
    win = (pr.outcome[pr.pos] == "WIN")
    take = {a: t[pr.pos] for a, t in arms.items()}
    full = np.arange(len(pr.pos))
    point = {(a, s): seq_metrics(pr.net[s][full][take[a]], win[take[a]]) for a in arms for s in SCENARIOS}
    draws = {(a, s, m): np.empty(n_boot) for a in arms for s in SCENARIOS for m in METRICS}
    for k in range(n_boot):
        rng = np.random.default_rng([seed, k])
        seq = np.concatenate([by_month[m] for m in rng.integers(0, n_m, n_m)])
        for a in arms:
            sel = seq[take[a][seq]]
            for s in SCENARIOS:
                for m, v in seq_metrics(pr.net[s][sel], win[sel]).items():
                    draws[(a, s, m)][k] = v
    rows = []
    for fam in M.FAMILIES:
        ml = f"ML:{fam}"
        for base in ("B0", "B1"):
            for s in SCENARIOS:
                for m in METRICS:
                    d = draws[(ml, s, m)] - draws[(base, s, m)]
                    ok = d[np.isfinite(d)]
                    pt = point[(ml, s)][m] - point[(base, s)][m]
                    rows.append(dict(family=fam, versus=base, scenario=s, metric=m, ml=point[(ml, s)][m], baseline=point[(base, s)][m],
                                     diff=pt, ci_lo=float(np.percentile(ok, 2.5)) if len(ok) >= 20 else np.nan,
                                     ci_hi=float(np.percentile(ok, 97.5)) if len(ok) >= 20 else np.nan,
                                     share_positive=float((ok > 0).mean()) if len(ok) else np.nan, n_valid=len(ok), n_boot=n_boot,
                                     n_months=n_m))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------------------
def capital_and_concurrency(oof, arms):
    pr = E.Prepared(oof)
    rows = []
    for a, t in arms.items():
        idx = np.flatnonzero(t)
        sub = oof.iloc[idx].reset_index(drop=True)
        n_open, dep = P.concurrency(sub) if len(sub) else (0, 0.0)
        capped = np.zeros(len(oof), dtype=bool)
        if len(sub):
            capped[idx[P.capital_constrained(sub).to_numpy(dtype=bool)]] = True
        csub = oof[capped].reset_index(drop=True)
        c_open, c_dep = P.concurrency(csub) if len(csub) else (0, 0.0)
        for s, m in E.evaluate(pr, capped).items():
            rows.append(dict(arm=a, scenario=s, n_taken_uncapped=int(t.sum()), n_taken_capped=int(capped.sum()),
                             uncapped_peak_open=n_open, uncapped_peak_deployed=dep, capped_peak_open=c_open, capped_peak_deployed=c_dep,
                             n_resolved=m["n_resolved_taken"], win_rate=m["win_rate"], expectancy=m["expectancy"],
                             profit_factor=m["profit_factor"], total_r=m["total_r"], max_dd=m["max_dd"]))
    return pd.DataFrame(rows)


def per_year(oof, arms):
    rows = []
    years = oof["entry_time"].dt.year.to_numpy()
    for y in sorted(set(years)):
        m = years == y
        sub = oof[m].reset_index(drop=True)
        pr = E.Prepared(sub)
        for a, t in arms.items():
            for s, r in E.evaluate(pr, t[m]).items():
                rows.append(dict(year=int(y), arm=a, scenario=s, n_rows=r["n_rows"], n_taken=r["n_taken"], n_resolved=r["n_resolved_taken"],
                                 take_rate=r["take_rate"], win_rate=r["win_rate"], expectancy=r["expectancy"],
                                 profit_factor=r["profit_factor"], total_r=r["total_r"], max_dd=r["max_dd"], ambiguous=r["AMBIGUOUS"]))
    return pd.DataFrame(rows)


def pooled(oof, arms):
    pr = E.Prepared(oof)
    rows = []
    for a, t in arms.items():
        for s, r in E.evaluate(pr, t).items():
            rows.append(dict(arm=a, scenario=s, n_taken=r["n_taken"], n_resolved=r["n_resolved_taken"], take_rate=r["take_rate"],
                             win_rate=r["win_rate"], expectancy=r["expectancy"], profit_factor=r["profit_factor"],
                             total_r=r["total_r"], max_dd=r["max_dd"], ambiguous=r["AMBIGUOUS"],
                             total_r_amb_worst=r["total_r_amb_worst"], total_r_amb_best=r["total_r_amb_best"]))
    return pd.DataFrame(rows)


def check_against_experiment(ds, pool_tbl):
    """The report's pooled numbers must equal the Experiment 1 pooled metrics (same take sets, same evaluator)."""
    ref = pd.read_csv(EXP / ds / "pooled_metrics.csv")
    for _, r in ref[ref["arm"].isin(["B0", "B1", "ML"])].iterrows():
        a = r["arm"] if r["family"] == "-" else f"ML:{r['family']}"
        mine = pool_tbl[(pool_tbl["arm"] == a) & (pool_tbl["scenario"] == r["scenario"])].iloc[0]
        for k, kr in (("n_taken", "n_taken"), ("expectancy", "expectancy"), ("total_r", "total_r"), ("max_dd", "max_dd")):
            same = (np.isnan(mine[k]) and np.isnan(r[kr])) or np.isclose(mine[k], r[kr], rtol=0, atol=1e-9)
            if not same:
                raise AssertionError(f"{ds}: report differs from experiment output for {a}/{r['scenario']}/{k}: {mine[k]} vs {r[kr]}")


# ---------------------------------------------------------------------------------------------------------------------------
def build_report(res, man, inputs):
    L = []
    w = L.append
    prim = res["primary"]
    w("# Experiment 1 final report (DIT15 meta-labeling, v1)\n")
    w("Descriptive reporting of the frozen Experiment 1 outputs. Nothing was retrained, retuned or re-selected; the 2026 holdout "
      "was excluded from every step and is not scored here. Costs are round-trip percentages of traded value (gross, 0.10, 0.20, 0.30); "
      "the single T1 take set (made at 0.20%) is evaluated at every cost level.\n")
    w("## Scope and provenance\n")
    sc = man["scope"]
    w(f"- Dataset: {sc['labeled_rows']} labeled rows, {sc['holdout_rows_excluded']} holdout rows excluded, {sc['primary_rows_used']} development rows; "
      f"pooled out-of-fold test stream (2023H1-2025H2): primary {sc['primary_oof_rows']} rows, strict-HTF sensitivity {sc['strict_oof_rows']} rows "
      f"(the {man['strict_subset_checks']['flagged_in_development_data']} flagged development rows removed).")
    w(f"- Phase A measured code hash `{man['phase_a_measured_code_hash']}` (registry constant `{man['registry_source_code_hash']}`, documented, unchanged). "
      f"Seed {man['seed']}; scikit-learn {man['versions']['scikit_learn']}, xgboost {man['versions']['xgboost']}.")
    w(f"- Determinism (second identical run): {man['determinism']}. Shuffled-label check: "
      + ", ".join(f"{f} AUC {s['roc_auc']:.3f} (band {s['band'][0]:.3f}-{s['band'][1]:.3f})" for f, s in man["shuffled_label_check"].items()) + ".")
    w(f"- Champion (preregistered rule: at least 100 resolved takes at 0.20%, then expectancy, total R, drawdown, PF): "
      f"primary **{man['champion']['primary']}**, strict sensitivity **{man['champion']['strict']}**.")
    w("- Inputs (SHA-256 verified against `experiment_1/manifest.json`): " + "; ".join(f"`{k}` {v[:12]}" for k, v in inputs.items()) + "\n")

    for ds, title in (("primary", "Primary dataset"), ("strict_htf", "Strict HTF-PIT sensitivity (240 flagged rows removed)")):
        r = res[ds]
        w(f"\n# {title}\n")
        w("## Pooled 2023-2025 out-of-fold results\n")
        t = r["pooled"]
        for s in (PRIMARY, "gross"):
            w(f"**{s}**\n")
            w(md_table(t[t.scenario == s][["arm", "n_taken", "n_resolved", "take_rate", "win_rate", "expectancy", "profit_factor", "total_r",
                                              "max_dd", "ambiguous"]]) + "\n")
        w("Ambiguity bounds on total R at 0.20% (all taken AMBIGUOUS trades lost / won, net of cost): "
          + "; ".join(f"{a} {f3(x.total_r_amb_worst, 1)} .. {f3(x.total_r_amb_best, 1)}" for a, x in
                      t[t.scenario == PRIMARY].set_index("arm").iterrows()) + "\n")
        w("## Month-block bootstrap (paired; ML minus baseline, 0.20% round trip)\n")
        b = r["boot"]
        w(f"{b['n_boot'].iloc[0]} draws of {b['n_months'].iloc[0]} entry-month blocks with replacement, seed {SEED}; intervals are percentile 2.5-97.5; "
          "`share+` is the share of draws with a positive difference; `valid` is the number of draws where both sides are defined "
          "(fewer than 20 valid draws gives no interval).\n")
        sub = b[(b.scenario == PRIMARY) & b.metric.isin(["expectancy", "total_r", "profit_factor", "max_dd", "win_rate"])].copy()
        sub["interval"] = [("n/a" if not np.isfinite(lo) else f"[{lo:+.3f}, {hi:+.3f}]") for lo, hi in zip(sub.ci_lo, sub.ci_hi)]
        sub = sub.rename(columns={"diff": "difference", "share_positive": "share+", "n_valid": "valid"})
        for base in ("B0", "B1"):
            w(f"*ML minus {base}*\n")
            w(md_table(sub[sub.versus == base][["family", "metric", "ml", "baseline", "difference", "interval", "share+", "valid"]]) + "\n")
        w("## Capital-constrained view (Rs 1,00,000, no leverage; Phase A `capital_constrained`) and concurrency\n")
        c = r["cap"]
        w("Peak open positions / peak deployed notional are for all taken signals with no capital limit (uncapped) and after the capital rule (capped).\n")
        ct = c[c.scenario == PRIMARY][["arm", "n_taken_uncapped", "n_taken_capped", "uncapped_peak_open", "uncapped_peak_deployed",
                                       "capped_peak_open", "capped_peak_deployed", "n_resolved", "expectancy", "profit_factor",
                                       "total_r", "max_dd"]].copy()
        for col in ("uncapped_peak_deployed", "capped_peak_deployed"):
            ct[col] = ct[col].map(lambda v: f"{v:,.0f}")
        w(md_table(ct) + "\n")
        w("## Per-year results (0.20% round trip)\n")
        y = r["year"]
        w(md_table(y[y.scenario == PRIMARY][["year", "arm", "n_taken", "n_resolved", "take_rate", "win_rate", "expectancy", "profit_factor",
                                             "total_r", "max_dd"]]) + "\n")
        wins = []
        for fam in M.FAMILIES:
            yy = y[y.scenario == PRIMARY].pivot(index="year", columns="arm", values="expectancy")
            better = int((yy[f"ML:{fam}"] > yy["B0"]).sum())
            wins.append(f"{fam} {better}/{len(yy)}")
        w("Years in which ML net expectancy exceeds B0 (undefined counts as not better): " + ", ".join(wins) + ".")
        enough = []
        for fam in M.FAMILIES:
            n_ok = int((y[(y.scenario == PRIMARY) & (y.arm == f"ML:{fam}")]["n_resolved"] >= 30).sum())
            enough.append(f"{fam} {n_ok}/{y['year'].nunique()}")
        w("Years in which the model has at least 30 resolved takes (a year with fewer is not a meaningful comparison): "
          + ", ".join(enough) + ".\n")
    w("\n## Reading the results\n")
    cm = prim["pooled"]
    ml = cm[(cm.scenario == PRIMARY) & cm.arm.str.startswith("ML:")].set_index("arm")
    w(f"- No model reaches the preregistered minimum of 100 resolved takes (resolved takes: "
      + ", ".join(f"{a[3:]} {int(x.n_resolved)}" for a, x in ml.iterrows())
      + "), so no champion exists in the primary run. The T1 rule needs roughly p > 0.45 at the average cost; the models' probabilities "
        "rarely reach that level.")
    w("- The rule-only baselines are negative after costs on this 2023-2025 stream (B0 and B1 above); ML-minus-baseline intervals that "
      "include zero, or have few valid draws, carry no evidence of improvement.")
    b2 = json.loads((EXP / "primary" / "results.json").read_text(encoding="utf-8"))["b2"]
    w("- Total R and drawdown differences against B0 / B1 mostly reflect how few trades the models take (0-4% of rows), not selection skill: "
      "skipping most of a negative-expectancy pool raises total R mechanically. The like-for-like control is the random filter with the same take "
      "counts (B2, 1,000 draws): ML expectancy sits at the "
      + ", ".join(f"{f3(v['ml_expectancy_percentile'] * 100, 0)}th percentile ({f})" for f, v in b2.items() if v["ml_expectancy_percentile"] is not None)
      + f" of random filters (random-filter mean expectancy about {f3(float(np.mean([v['expectancy_mean'] for v in b2.values() if v['expectancy_mean'] is not None])), 2)}).")
    w("- Samples of a few dozen trades give wide intervals; differences are descriptive and are not used to alter any frozen decision.")
    return "\n".join(L)


def main():
    if OUT.exists() and any(OUT.iterdir()):
        print(f"{rel(OUT)} is not empty: refusing to overwrite.")
        return 1
    man = json.loads((EXP / "manifest.json").read_text(encoding="utf-8"))
    inputs = {}
    for ds in DATASETS:
        p = EXP / ds / "oof_predictions.csv"
        got, want = sha256(p), man["output_sha256"][rel(p)]
        if got != want:
            print(f"SHA-256 mismatch for {rel(p)}: {got[:12]} != {want[:12]}")
            return 1
        inputs[rel(p)] = got
    t0 = time.time()
    res = {}
    for ds in DATASETS:
        oof = load(ds)
        if (oof["entry_time"] >= "2026-01-01").any():
            raise AssertionError("holdout rows present in the out-of-fold stream")
        arms = arms_of(oof)
        tbl = pooled(oof, arms)
        check_against_experiment(ds, tbl)
        print(f"[{time.time() - t0:6.1f}s] {ds}: pooled table agrees with the Experiment 1 outputs; bootstrap ...", flush=True)
        res[ds] = dict(pooled=tbl, boot=month_block_bootstrap(oof, arms), cap=capital_and_concurrency(oof, arms), year=per_year(oof, arms))
        print(f"[{time.time() - t0:6.1f}s] {ds}: done", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for ds in DATASETS:
        for k, df in res[ds].items():
            df.to_csv(OUT / f"{ds}_{k}.csv", index=False)
    (OUT / "report.md").write_text(build_report(res, man, inputs), encoding="utf-8")
    outputs = {rel(p): sha256(p) for p in sorted(OUT.iterdir()) if p.is_file()}
    (OUT / "report_manifest.json").write_text(json.dumps(dict(inputs=inputs, outputs=outputs, n_boot=N_BOOT, seed=SEED), indent=1), encoding="utf-8")
    print(f"written {rel(OUT)} ({len(outputs) + 1} files, {time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
