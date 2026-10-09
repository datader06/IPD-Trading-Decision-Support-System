"""Backtest & ML Results page (frozen DIT15 Phase A baseline and Experiment 1).

Every number shown is read from the existing report / result files (results/nogit-145d6302/...) and cross-checked against the other
artifacts and the documentation; the checks are listed at the bottom of the page. Nothing is re-run, fetched or modified. The scanner
rows of the main page are demo output and are not used here.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import costs  # noqa: E402
import portfolio as P  # noqa: E402

RUN = ROOT / "results" / "nogit-145d6302"
PA = RUN / "phase_a" / "pit"
PB = RUN / "phase_b"
EXP = PB / "experiment_1"
DOC = ROOT / "docs" / "PHASE_A_FREEZE.md"
FAMILIES = ["logreg", "random_forest", "hist_gb", "xgboost"]
NAMES = {"logreg": "Logistic Regression", "random_forest": "Random Forest", "hist_gb": "HistGradientBoosting", "xgboost": "XGBoost"}
SCEN = ["gross", "rt0.10", "rt0.20", "rt0.30"]
SCEN_TEXT = {"gross": "Gross (no costs)", "rt0.10": "0.10% round trip", "rt0.20": "0.20% round trip", "rt0.30": "0.30% round trip"}
C = dict(good="#34d399", bad="#ef5350", blue="#3b82f6", amber="#f5a524", grey="#6b7788", red="#ef4444")

st.set_page_config(page_title="Backtest & ML Results", page_icon="📊", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
.banner {border-radius: 10px; padding: .7rem 1rem; margin-bottom: .6rem; font-weight: 600;}
.banner.info {background: #0f1f33; border: 1px solid #3b82f6; color: #bcd6ff;}
.banner.warn {background: linear-gradient(90deg, #3b2a05, #1f1a0b); border: 1px solid #f5a524; color: #ffd48a;}
.banner small {display: block; font-weight: 400; margin-top: .15rem; opacity: .9;}
.kpi {background: #121923; border: 1px solid #1f2a37; border-radius: 12px; padding: .8rem 1rem; height: 100%;}
.kpi .k {color: #8b97a7; font-size: .7rem; text-transform: uppercase; letter-spacing: .5px;}
.kpi .v {font-size: 1.6rem; font-weight: 700; line-height: 1.2;}
.kpi .s {color: #8b97a7; font-size: .76rem;}
.verdict {background: #121923; border-left: 5px solid #f5a524; border-radius: 8px; padding: .8rem 1rem; margin: .4rem 0 1rem 0;}
.note {color: #8b97a7; font-size: .84rem;}
@media (max-width: 600px) {[data-testid="stTable"] td, [data-testid="stTable"] th {padding: .3rem .2rem; font-size: .68rem; word-break: normal !important; overflow-wrap: normal !important;}
                           [data-testid="stTable"] p {word-break: normal !important; overflow-wrap: normal !important; hyphens: none !important;}
                           [data-testid="stTable"] td:not(:first-child), [data-testid="stTable"] th:not(:first-child) {white-space: nowrap;}}
</style>
""", unsafe_allow_html=True)

LINE = re.compile(r"n=\s*(\d+)\s+W=\s*(\d+)\s+L=\s*(\d+)\s+AMB=\s*(\d+).*?win%=\s*([\d.]+)\s+\[(\d+)-(\d+)\]\s+expR=([+-]?[\d.]+)\s+"
                  r"PF=([\d.]+)\s+totR=\s*([+-]?[\d.]+)\s+maxDD_R=\s*([\d.]+)")


def _parse(line):
    m = LINE.search(line)
    if not m:
        return None
    n, w, l, a, wr, lo, hi, e, pf, tr, dd = m.groups()
    return dict(n=int(n), W=int(w), L=int(l), AMB=int(a), win=float(wr), ci_lo=int(lo), ci_hi=int(hi), exp=float(e), pf=float(pf),
                tot=float(tr), dd=float(dd))


@st.cache_data(show_spinner=False)
def load_phase_a():
    lines = (PA / "report.txt").read_text(encoding="utf-8").splitlines()
    out = dict(all=None, years={}, train=None, holdout=None, costs={})
    for l in lines:
        if l.startswith("B0 ALL"):
            out["all"] = _parse(l)
        elif re.match(r"B0 (20\d\d) ", l):
            out["years"][int(l.split()[1])] = _parse(l)
        elif l.startswith("B0 TRAIN"):
            out["train"] = _parse(l)
        elif l.startswith("B0 HOLDOUT"):
            out["holdout"] = _parse(l)
    for s in SCEN[1:]:
        i = next(i for i, l in enumerate(lines) if l.startswith(f"-- B0 net of costs, scenario {s} "))
        out["costs"][s] = _parse(next(l for l in lines[i + 1:] if l.startswith("ALL")))
    out["costs"]["gross"] = out["all"]
    # documentation (PHASE_A_FREEZE.md): the frozen DIT15 row and the cost row
    doc = DOC.read_text(encoding="utf-8").splitlines()
    row = next(l for l in doc if l.startswith("| **DIT15** strict B0")).split("|")
    wla = [int(x) for x in row[5].replace(" ", "").split("/")]
    out["doc"] = dict(n=int(row[4]), W=wla[0], L=wla[1], AMB=wla[2], win=float(row[6].strip().rstrip("%")), exp=float(row[7]),
                      pf=float(row[8]), tot=float(row[9]), dd=float(row[10]))
    crow = next(l for l in doc if l.startswith("| DIT15 B0 |")).split("|")
    out["doc_costs"] = dict(zip(SCEN[1:], [float(x) for x in crow[2:5]]))
    return out


@st.cache_data(show_spinner=False)
def recompute_phase_a():
    """Independent recomputation of the B0 baseline from the stored candidates file (Phase A portfolio / cost code)."""
    c = pd.read_csv(PA / "candidates.csv", parse_dates=["entry_time", "fill_time", "exit_time"])
    b0 = c[c["is_b0"].astype(bool) & ~c["ca_excluded"].astype(bool) & (c["entry_time"] >= "2021-01-01")].copy()
    res = {}
    for cm in costs.scenarios(0.0):
        col = f"r_{cm.name}"
        v = np.full(len(b0), np.nan)
        for i in np.flatnonzero(b0["outcome"].isin(["WIN", "LOSS"]).to_numpy()):
            v[i] = cm.net_r(b0["r_gross"].iat[i], b0["fill_price"].iat[i], b0["exit_price"].iat[i], b0["risk"].iat[i])
        b0[col] = v
        s = P.summary(b0, col)
        res[cm.name] = dict(n=s["n"], W=s["WIN"], L=s["LOSS"], AMB=s["AMBIGUOUS"], exp=s["expectancy_r"], pf=s["profit_factor"],
                            tot=s["total_r"], dd=s["max_dd_r"], win=s["win_rate"])
    return res


@st.cache_data(show_spinner=False)
def load_exp1():
    d = {}
    d["res"] = json.loads((EXP / "primary" / "results.json").read_text(encoding="utf-8"))
    d["man"] = json.loads((EXP / "manifest.json").read_text(encoding="utf-8"))
    d["pooled"] = pd.read_csv(EXP / "primary" / "pooled_metrics.csv")
    d["rep_pooled"] = pd.read_csv(EXP / "report" / "primary_pooled.csv")
    d["sel"] = pd.read_csv(EXP / "primary" / "fold_selections.csv")
    d["boot"] = pd.read_csv(EXP / "report" / "primary_boot.csv")
    d["strict"] = json.loads((EXP / "strict_htf" / "results.json").read_text(encoding="utf-8"))
    d["folds"] = pd.read_csv(PB / "tier1" / "folds" / "folds.csv")
    d["oof_cost"] = pd.read_csv(EXP / "primary" / "oof_predictions.csv", usecols=["cost_in_r_rt0.20"])["cost_in_r_rt0.20"]
    return d


pa, rc, ex = load_phase_a(), recompute_phase_a(), load_exp1()
res, man, pooled = ex["res"], ex["man"], ex["pooled"]
A = pa["all"]


def fnum(v, nd=3, sign=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def kpi(col, k, v, s=""):
    col.markdown(f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>', unsafe_allow_html=True)


def pm(fam, arm, scen):
    r = pooled[(pooled["family"] == fam) & (pooled["arm"] == arm) & (pooled["scenario"] == scen)]
    return r.iloc[0]


def base(arm, scen):
    r = pooled[(pooled["family"] == "-") & (pooled["arm"] == arm) & (pooled["scenario"] == scen)]
    return r.iloc[0]


# ------------------------------------------------------------------------------------------------------------ verification
checks = []


def chk(label, ok):
    checks.append((label, bool(ok)))


def same(a, b, nd):
    return abs(round(a, nd) - round(b, nd)) < 10 ** (-nd) / 2 + 1e-12


d = pa["doc"]
chk("Phase A report.txt B0 row = PHASE_A_FREEZE.md DIT15 row (trades, W/L/ambiguous, win rate, expectancy, PF, total R, max DD)",
    all([A["n"] == d["n"], (A["W"], A["L"], A["AMB"]) == (d["W"], d["L"], d["AMB"]), A["win"] == d["win"], A["exp"] == d["exp"],
         A["pf"] == d["pf"], A["tot"] == d["tot"], A["dd"] == d["dd"]]))
chk("Independent recomputation from candidates.csv = report.txt for gross and the 3 cost scenarios (n, W/L/ambiguous, expectancy, PF, total R, max DD)",
    all(rc[s]["n"] == pa["costs"][s]["n"] and (rc[s]["W"], rc[s]["L"], rc[s]["AMB"]) == (pa["costs"][s]["W"], pa["costs"][s]["L"], pa["costs"][s]["AMB"])
        and same(rc[s]["exp"], pa["costs"][s]["exp"], 3) and same(rc[s]["pf"], pa["costs"][s]["pf"], 2)
        and same(rc[s]["tot"], pa["costs"][s]["tot"], 1) and same(rc[s]["dd"], pa["costs"][s]["dd"], 1) for s in SCEN))
chk("Cost-sensitivity expectancies (0.10/0.20/0.30%) in report.txt = PHASE_A_FREEZE.md cost table",
    all(pa["costs"][s]["exp"] == pa["doc_costs"][s] for s in SCEN[1:]))
chk("Per-year B0 trades, wins, losses and ambiguous add up to the totals (318; 91/167/60)",
    sum(y["n"] for y in pa["years"].values()) == A["n"] and sum(y["W"] for y in pa["years"].values()) == A["W"]
    and sum(y["L"] for y in pa["years"].values()) == A["L"] and sum(y["AMB"] for y in pa["years"].values()) == A["AMB"])
ok_tbl = True
for fam in FAMILIES:
    m = res["pooled"]["models"][fam]["arms"]["ML"]
    for s in ("gross", "rt0.20"):
        a, b, c = m[s], pm(fam, "ML", s), ex["rep_pooled"][(ex["rep_pooled"]["arm"] == f"ML:{fam}") & (ex["rep_pooled"]["scenario"] == s)].iloc[0]
        for k, kb in (("n_taken", "n_taken"), ("n_resolved_taken", "n_resolved_taken"), ("expectancy", "expectancy"), ("total_r", "total_r")):
            va, vb = a[k], b[kb]
            vc = c[{"n_resolved_taken": "n_resolved"}.get(k, k)]
            ok_tbl &= all(((x is None or (isinstance(x, float) and np.isnan(x))) and (isinstance(y, float) and np.isnan(y))) or
                          (x is not None and not (isinstance(x, float) and np.isnan(x)) and abs(float(x) - float(y)) < 1e-9)
                          for x, y in ((va, vb), (va, vc)))
chk("Experiment 1 pooled ML results agree across results.json, pooled_metrics.csv and the report tables (takes, expectancy, total R; gross and 0.20%)", ok_tbl)
sel = ex["sel"]
chk("Per-fold T1 take counts add up to the pooled take counts for every model",
    all(int(sel[sel["family"] == f]["n_take_t1"].sum()) == int(pm(f, "ML", "rt0.20")["n_taken"]) for f in FAMILIES))
chk("No model reaches the 100 resolved takes required; champion is None in results.json and manifest.json",
    all(int(pm(f, "ML", "rt0.20")["n_resolved_taken"]) < 100 for f in FAMILIES) and res["champion"]["champion"] is None
    and man["champion"]["primary"] is None)
fo = ex["folds"]
chk("Six folds; test windows end by 2026-01-01; test rows sum to the 2,509-row out-of-fold stream; 781 holdout rows excluded",
    len(fo) == 6 and all(p.split(" .. ")[1] <= "2026-01-01" for p in fo["test_period"]) and int(fo["test_rows"].sum()) == man["scope"]["primary_oof_rows"] == 2509
    and man["scope"]["holdout_rows_excluded"] == 781 and fo["test_rows_exiting_in_holdout"].sum() == 0)
chk("Shuffled-label check passed for all four models and the repeat run was identical",
    all(v["passed"] for v in man["shuffled_label_check"].values()) and all(man["determinism"].values()))
chk("Strict-HTF sensitivity: 240 flagged rows (196 in development data), none left in its out-of-fold stream",
    man["strict_subset_checks"]["flagged_total"] == 240 and man["strict_subset_checks"]["flagged_in_development_data"] == 196
    and man["strict_subset_checks"]["none_left_in_strict_oof"])
base_rate = res["pooled"]["models"]["logreg"]["ml"]["base_rate_observed"]
L_mean = float(np.mean([fr["L_pool"] for fr in res["folds"]]))
c_mean = float(ex["oof_cost"].mean())
p_need = (L_mean + c_mean) / (2.0 + L_mean)  # break-even win probability of the preregistered rule: p*2 - (1-p)*L - c > 0
brier_base = base_rate * (1 - base_rate)
ll_base = -(base_rate * np.log(base_rate) + (1 - base_rate) * np.log(1 - base_rate))
briers = [res["pooled"]["models"][f]["ml"]["brier"] for f in FAMILIES]
lls = [res["pooled"]["models"][f]["ml"]["log_loss"] for f in FAMILIES]
chk("Brier score and log-loss of every model are at or above the constant base-rate predictor (no probabilistic skill)",
    all(b >= brier_base - 1e-3 for b in briers) and all(v >= ll_base - 1e-3 for v in lls))
n_ok = sum(ok for _, ok in checks)

# ------------------------------------------------------------------------------------------------------------ header
st.title("Backtest & ML Results")
st.markdown(f'<div class="banner info">Frozen results — not the demo scanner<small>Phase A DIT15 baseline and Experiment 1 (ML meta-labeling), read '
            f'from the stored report files and cross-checked ({n_ok} of {len(checks)} checks passed; details at the bottom). '
            f'Nothing on this page was re-run, and these are not live trading advice.</small></div>', unsafe_allow_html=True)
if n_ok != len(checks):
    st.error("Some cross-checks failed. See the verification list at the bottom before using these numbers.")

best_auc = max(res["pooled"]["models"][f]["ml"]["roc_auc"] for f in FAMILIES)
worst_auc = min(res["pooled"]["models"][f]["ml"]["roc_auc"] for f in FAMILIES)
st.markdown(f'<div class="verdict"><b>Headline.</b> The DIT15 rules earned {fnum(A["exp"], 3, True)}R per trade before costs '
            f'({A["n"]} trades, 2021–2026) and lose money at every cost level tested. In Experiment 1 no ML model demonstrated a reliable '
            f'predictive edge: pooled out-of-fold ROC-AUC was {worst_auc:.3f}–{best_auc:.3f} (0.5 = no skill), and <b>no champion was '
            f'selected</b> because no model reached the preregistered minimum of 100 resolved trades.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------------------ A. baseline
st.header("1. DIT15 rule baseline (frozen Phase A)")
st.caption("Strict rule-only list (B0), entries 2021-01-01 to 2026-10-01, 503-ticker universe, cached Kite data. Gross R unless stated; "
           f"{A['AMB']} ambiguous trades are never converted into wins or losses. Source: results/nogit-145d6302/phase_a/pit/report.txt.")
k = st.columns(6)
kpi(k[0], "Trades", f'{A["n"]}', f'{A["W"]} W / {A["L"]} L / {A["AMB"]} ambiguous')
kpi(k[1], "Win rate", f'{A["win"]:.1f}%', f'95% interval {A["ci_lo"]}–{A["ci_hi"]}%')
kpi(k[2], "Expectancy (gross)", f'{A["exp"]:+.3f} R', "mean R per resolved trade")
kpi(k[3], "Profit factor", f'{A["pf"]:.2f}', "gross")
kpi(k[4], "Total R", f'{A["tot"]:+.1f}', "gross, resolved trades")
kpi(k[5], "Max drawdown", f'{A["dd"]:.1f} R', "cumulative R, by exit time")
st.write("")
yrs = pd.DataFrame([dict(year=str(y), trades=v["n"], resolved=v["W"] + v["L"], exp=v["exp"], pf=v["pf"], win=v["win"], tot=v["tot"], dd=v["dd"])
                    for y, v in sorted(pa["years"].items())])
yrs.loc[yrs.year == "2026", "year"] = "2026*"
c1, c2 = st.columns([1, 1.3])
fig = go.Figure(go.Bar(x=yrs["year"], y=yrs["exp"], marker_color=[C["good"] if v > 0 else C["bad"] for v in yrs["exp"]],
                       text=[f"n={n}" for n in yrs["trades"]], textposition="outside", name="Expectancy"))
fig.add_hline(y=0, line_color="#9aa7b8", line_width=1)
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=340, margin=dict(l=10, r=10, t=40, b=10),
                  title="Gross expectancy per year (R), n = trades", yaxis_title="R", showlegend=False)
c1.plotly_chart(fig, width="stretch")
yr_show = pd.DataFrame({"Year": yrs["year"], "Trades": yrs["trades"].astype(str), "Exp R": [f"{v:+.3f}" for v in yrs["exp"]],
                        "PF": [f"{v:.2f}" for v in yrs["pf"]], "Win %": [f"{v:.1f}" for v in yrs["win"]],
                        "Total R": [f"{v:+.1f}" for v in yrs["tot"]], "Max DD": [f"{v:.1f}" for v in yrs["dd"]]}).set_index("Year")
c2.table(yr_show)  # st.table fits the container at any width (the values shown are the report.txt figures, formatted)
c2.caption("*2026 is partly contaminated by chart reviews (see the Phase A freeze notes) and is not a clean test.")
st.markdown(f"""
**What it means.** Across 2021–2026 the strategy is only barely positive before costs ({A['exp']:+.3f}R, profit factor {A['pf']:.2f}), and the
win-rate interval ({A['ci_lo']}–{A['ci_hi']}%) is wide. Results swing by year ({yrs['exp'].min():+.3f}R to {yrs['exp'].max():+.3f}R), and
no year has more than {int(yrs['trades'].max())} trades. These numbers are the benchmark every ML filter was measured against.
""")

# ------------------------------------------------------------------------------------------------------------ B. costs
st.header("2. Cost sensitivity")
st.caption("The same 318 trades re-scored with round-trip costs of 0.10%, 0.20% and 0.30% of traded value (no slippage). The broker's real "
           "cost schedule is not fixed, so all three are reported and none is chosen to flatter a result.")
crow = []
for s in SCEN:
    v = pa["costs"][s]
    crow.append({"Scenario": SCEN_TEXT[s], "Expectancy (R)": v["exp"], "Profit factor": v["pf"], "Total R": v["tot"], "Max drawdown (R)": v["dd"]})
ct = pd.DataFrame(crow)
c1, c2 = st.columns([1, 1])
fig = go.Figure(go.Bar(x=[SCEN_TEXT[s] for s in SCEN], y=ct["Expectancy (R)"], marker_color=[C["good"] if v > 0 else C["bad"] for v in ct["Expectancy (R)"]],
                       text=[f"{v:+.3f}" for v in ct["Expectancy (R)"]], textposition="outside"))
fig.add_hline(y=0, line_color="#9aa7b8", line_width=1)
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=340, margin=dict(l=10, r=10, t=40, b=10),
                  title="Expectancy per trade by cost scenario (R)", yaxis_title="R", showlegend=False)
c1.plotly_chart(fig, width="stretch")
ct_show = pd.DataFrame({"Scenario": ct["Scenario"], "Exp (R)": [f"{v:+.3f}" for v in ct["Expectancy (R)"]],
                        "PF": [f"{v:.2f}" for v in ct["Profit factor"]], "Total R": [f"{v:+.1f}" for v in ct["Total R"]],
                        "Max DD (R)": [f"{v:.1f}" for v in ct["Max drawdown (R)"]]}).set_index("Scenario")
c2.table(ct_show)
c2.caption(f"Win rate is {pa['costs']['gross']['win']:.1f}% in every scenario (costs change the R of each trade, not whether it wins).")
st.markdown(f"""
**What it means.** The thin gross edge ({pa['costs']['gross']['exp']:+.3f}R) does not survive costs: at 0.10% the expectancy is
{pa['costs']['rt0.10']['exp']:+.3f}R (profit factor {pa['costs']['rt0.10']['pf']:.2f}), at 0.20% {pa['costs']['rt0.20']['exp']:+.3f}R and at 0.30%
{pa['costs']['rt0.30']['exp']:+.3f}R. Drawdown grows from {pa['costs']['gross']['dd']:.1f}R to {pa['costs']['rt0.30']['dd']:.1f}R. The rule set alone is
not a tradable edge at any of these cost levels.
""")

# ------------------------------------------------------------------------------------------------------------ C. experiment 1
st.header("3. Experiment 1: can ML filter the DIT15 candidates?")
st.markdown(f'<div class="banner warn">No model demonstrated a reliable predictive edge. No champion was selected.'
            f'<small>The ML layer may only take or skip existing DIT15 candidates; it never changes entries, stops or targets. Four models '
            f'(logistic regression, random forest, gradient boosting, XGBoost) were trained walk-forward on 2021–2025 and tested out-of-sample on '
            f'{man["scope"]["primary_oof_rows"]:,} candidates from 2023–2025. All decisions were preregistered before training.</small></div>',
            unsafe_allow_html=True)
rows = []
for f in FAMILIES:
    ml = res["pooled"]["models"][f]["ml"]
    n02, g = pm(f, "ML", "rt0.20"), pm(f, "ML", "gross")
    bt = ex["boot"][(ex["boot"]["family"] == f) & (ex["boot"]["versus"] == "B0") & (ex["boot"]["scenario"] == "rt0.20") & (ex["boot"]["metric"] == "expectancy")].iloc[0]
    rows.append({"Model": NAMES[f], "ROC-AUC": ml["roc_auc"], "PR-AUC": ml["pr_auc"], "Brier": ml["brier"], "Log-loss": ml["log_loss"],
                 "Trades taken": int(n02["n_taken"]), "Resolved taken": int(n02["n_resolved_taken"]),
                 "Gross exp (R)": g["expectancy"], "Net exp 0.20% (R)": n02["expectancy"],
                 "vs B0 (0.20%)": "n/a (no trades)" if pd.isna(bt["diff"]) else f'{bt["diff"]:+.3f}  [{bt["ci_lo"]:+.2f}, {bt["ci_hi"]:+.2f}]'})
b0, b1 = base("B0", "rt0.20"), base("B1", "rt0.20")
b0g, b1g = base("B0", "gross"), base("B1", "gross")
rows += [{"Model": "B0 rules only (reference)", "ROC-AUC": np.nan, "PR-AUC": np.nan, "Brier": np.nan, "Log-loss": np.nan, "Trades taken": int(b0["n_taken"]),
          "Resolved taken": int(b0["n_resolved_taken"]), "Gross exp (R)": b0g["expectancy"], "Net exp 0.20% (R)": b0["expectancy"], "vs B0 (0.20%)": "—"},
         {"Model": "B1 whole pool (reference)", "ROC-AUC": np.nan, "PR-AUC": np.nan, "Brier": np.nan, "Log-loss": np.nan, "Trades taken": int(b1["n_taken"]),
          "Resolved taken": int(b1["n_resolved_taken"]), "Gross exp (R)": b1g["expectancy"], "Net exp 0.20% (R)": b1["expectancy"], "vs B0 (0.20%)": "—"}]
t = pd.DataFrame(rows)
_fmt = {"ROC-AUC": "{:.3f}", "PR-AUC": "{:.3f}", "Brier": "{:.3f}", "Log-loss": "{:.3f}", "Gross exp (R)": "{:+.3f}", "Net exp 0.20% (R)": "{:+.3f}"}
t_show = t.copy()
for _c, _f in _fmt.items():  # display strings: an undefined metric is a blank cell (never 0 or "None"); the values in `t` are unchanged
    t_show[_c] = [("" if pd.isna(v) else _f.format(v)) for v in t[_c]]
t_show = t_show.rename(columns={"Trades taken": "Taken", "Resolved taken": "Resolved", "Gross exp (R)": "Gross exp R", "Net exp 0.20% (R)": "Net exp R*",
                                "vs B0 (0.20%)": "Net exp vs B0*"})
TC = st.column_config.TextColumn
st.dataframe(t_show, hide_index=True, width="stretch",
             column_config={**{c: TC(c, width="small") for c in ("ROC-AUC", "PR-AUC", "Brier", "Log-loss", "Gross exp R", "Net exp R*")},
                            "Model": TC("Model", width="medium"), "Net exp vs B0*": TC("Net exp vs B0*", width="medium")})
st.caption("\* Net of 0.20% round-trip costs. 'Net exp vs B0' is the paired month-block bootstrap difference with its 95% interval. "
           "Blank cells are undefined (no trades, or a reference row with no classifier).")
base_rate = res["pooled"]["models"]["logreg"]["ml"]["base_rate_observed"]
st.caption(f"Pooled 2023–2025 out-of-fold stream. Observed win rate among resolved test trades: {100 * base_rate:.1f}% (the PR-AUC reference). "
           "B0/B1 rows are the rule-only "
           "baselines on the same test rows (they differ from the 318-trade full-history baseline above).")

band = list(man["shuffled_label_check"]["logreg"]["band"])
c1, c2 = st.columns(2)
auc = [res["pooled"]["models"][f]["ml"]["roc_auc"] for f in FAMILIES]
fig = go.Figure()
fig.add_hrect(y0=band[0], y1=band[1], fillcolor="rgba(107,119,136,.25)", line_width=0)
fig.add_trace(go.Bar(x=[NAMES[f] for f in FAMILIES], y=auc, marker_color=C["blue"], text=[f"{a:.3f}" for a in auc], textposition="outside"))
fig.add_hline(y=0.5, line_color="#9aa7b8", line_dash="dash", annotation_text="0.5 = no skill", annotation_position="top left")
fig.update_yaxes(range=[0.42, 0.60])
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=360, margin=dict(l=10, r=10, t=40, b=10),
                  title="Pooled out-of-fold ROC-AUC (grey band = shuffled-label 95% range)", showlegend=False)
c1.plotly_chart(fig, width="stretch")
fl = sel.copy()
fl["Model"] = fl["family"].map(NAMES)
fig = px.line(fl, x="fold", y="auc", color="Model", markers=True, color_discrete_sequence=[C["blue"], C["amber"], C["good"], "#c084fc"])
fig.add_hline(y=0.5, line_color="#9aa7b8", line_dash="dash")
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=360, margin=dict(l=10, r=10, t=40, b=10),
                  title="ROC-AUC by test fold (half-year)", yaxis_title="ROC-AUC", xaxis_title="", legend=dict(orientation="h", y=-0.15))
c2.plotly_chart(fig, width="stretch")
c1, c2 = st.columns(2)
rt = [int(pm(f, "ML", "rt0.20")["n_resolved_taken"]) for f in FAMILIES]
fig = go.Figure(go.Bar(x=[NAMES[f] for f in FAMILIES], y=rt, marker_color=C["amber"], text=rt, textposition="outside"))
fig.add_hline(y=100, line_color=C["red"], line_dash="dash", annotation_text="100 resolved trades required for a champion", annotation_position="top left")
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=340, margin=dict(l=10, r=10, t=40, b=10),
                  title=f"Resolved trades each model chose to take (of {int(b1['n_resolved_taken']):,} test trades)", showlegend=False)
c1.plotly_chart(fig, width="stretch")
ne = [pm(f, "ML", "rt0.20")["expectancy"] for f in FAMILIES]
labels = [NAMES[f] for f in FAMILIES] + ["Rules only (B0)", "Whole pool (B1)"]
vals = ne + [b0["expectancy"], b1["expectancy"]]
fig = go.Figure(go.Bar(x=labels, y=[0 if pd.isna(v) else v for v in vals],
                       marker_color=[C["grey"] if pd.isna(v) else (C["good"] if v > 0 else C["bad"]) for v in vals],
                       text=["no trades" if pd.isna(v) else f"{v:+.3f}" for v in vals], textposition="outside"))
fig.add_hline(y=0, line_color="#9aa7b8", line_width=1)
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=340, margin=dict(l=10, r=10, t=40, b=10),
                  title="Net expectancy at 0.20% costs on the test stream (R)", showlegend=False)
c2.plotly_chart(fig, width="stretch")

tk = {f: int(pm(f, "ML", "rt0.20")["n_taken"]) for f in FAMILIES}

n_all = int(b1["n_taken"])
sres = ex["strict"]
sh = sres["pooled"]["models"]["hist_gb"]["arms"]["ML"]["rt0.20"]
st.markdown(f"""
**Interpretation**
- **No skill.** Every model's ROC-AUC ({worst_auc:.3f}–{best_auc:.3f}) is essentially 0.5, and the shuffled-label control (labels scrambled, then
  tested) lands in the same range ({man['shuffled_label_check']['logreg']['roc_auc']:.3f}–{max(v['roc_auc'] for v in man['shuffled_label_check'].values()):.3f}).
  Brier scores ({min(briers):.3f}–{max(briers):.3f}) and log-losses ({min(lls):.3f}–{max(lls):.3f}) sit at the level of a constant
  base-rate predictor ({brier_base:.3f} and {ll_base:.3f}).
- **Almost nothing passes the profit rule.** The preregistered rule takes a trade only if its expected net R is positive. That needs a win
  probability of about {100 * p_need:.0f}% (average loss {L_mean:.2f}R, average cost {c_mean:.2f}R) against a {100 * base_rate:.0f}% base rate, so the models took just {min(tk.values())}–{max(tk.values())} of {n_all:,}
  test candidates ({100 * min(tk.values()) / n_all:.1f}%–{100 * max(tk.values()) / n_all:.1f}%). With so few trades, none of the expectancy
  differences is distinguishable from zero (every bootstrap interval for the expectancy difference includes 0; random forest took no trades).
- **No champion.** The champion rule requires at least 100 resolved trades; the largest model took {max(rt)}. The strict-HTF sensitivity run
  (240 rows removed) picks HistGradientBoosting only because it took {int(sh['n_resolved_taken'])} trades, and its expectancy is
  {sh['expectancy']:+.3f}R, not an improvement.
- **Conclusion.** With these 18 frozen features and this rule set, ML meta-labeling did not improve the DIT15 candidates. The result is
  reported as it is; no model, feature, threshold or cost was tuned after seeing it.
""")

# ------------------------------------------------------------------------------------------------------------ D. validation design
st.header("4. How the results were validated")
st.caption("Chronological walk-forward validation. The 2026 holdout was never used and was not scored in Experiment 1.")
as_of_end = pd.Timestamp(man.get("holdout_end", "2026-10-01"))
segs = []
for r in fo.itertuples():
    fit0, val0 = (pd.Timestamp(x) for x in r.fit_period.split(" .. "))
    v0, t0 = (pd.Timestamp(x) for x in r.validation_period.split(" .. "))
    ts, te = (pd.Timestamp(x) for x in r.test_period.split(" .. "))
    ve, tem = pd.Timestamp(r.val_embargo_start), pd.Timestamp(r.test_embargo_start)
    for role, a, b in (("Training", fit0, ve), ("Embargo / purge", ve, v0), ("Validation (last 6 months)", v0, tem),
                       ("Embargo / purge", tem, t0), ("Test (out-of-sample)", ts, te)):
        segs.append(dict(Fold=r.fold, Role=role, Start=a, End=b))
segs.append(dict(Fold="2026 holdout", Role="Holdout (never used)", Start=pd.Timestamp("2026-01-01"), End=as_of_end))
tl = pd.DataFrame(segs)
fig = px.timeline(tl, x_start="Start", x_end="End", y="Fold", color="Role",
                  color_discrete_map={"Training": C["blue"], "Embargo / purge": C["grey"], "Validation (last 6 months)": C["amber"],
                                      "Test (out-of-sample)": C["good"], "Holdout (never used)": C["red"]},
                  category_orders={"Fold": [r.fold for r in fo.itertuples()] + ["2026 holdout"]})
fig.update_yaxes(autorange="reversed", title="")
fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=380, margin=dict(l=10, r=10, t=30, b=10),
                  legend=dict(orientation="h", y=-0.12, title=""), xaxis_title="")
st.plotly_chart(fig, width="stretch")
ft = fo[["fold", "fit_n", "val_n", "test_rows", "test_resolved", "test_ambiguous"]].rename(
    columns={"fold": "Fold", "fit_n": "Training rows", "val_n": "Validation rows", "test_rows": "Test rows", "test_resolved": "Test resolved",
             "test_ambiguous": "Test ambiguous"})
c1, c2 = st.columns([1.3, 1])
c1.dataframe(ft, hide_index=True, width="stretch")
c1.caption("Training and validation counts are resolved trades (wins and losses); test rows include every candidate, resolved or not.")
c2.markdown(f"""
- **Expanding window.** Each fold trains on everything before its test half-year, starting 2021-01-01.
- **Validation.** The last 6 months of training choose each model's settings. Test labels are never used for any choice.
- **Embargo and purge.** Trades within 5 trading days before a boundary, and trades whose outcome would reach into the next period, are removed.
- **Sibling zones.** Trades from the same higher-timeframe zone stay on one side of every split.
- **2026 holdout.** {man['scope']['holdout_rows_excluded']} candidates entered in 2026 were excluded from fitting, tuning, thresholds, model
  selection and scoring. {man['scope']['primary_rows_used']:,} development rows were used.
""")

# ------------------------------------------------------------------------------------------------------------ verification
st.header("Verification against the report files")
st.markdown(f"**{n_ok} of {len(checks)} cross-checks passed.** Numbers are read from the files below; where a figure appears in more than one "
            "artifact, the page compares them.")
for label, ok in checks:
    st.markdown(f"{'✅' if ok else '❌'} {label}")
with st.expander("Source files"):
    st.markdown("""
- `results/nogit-145d6302/phase_a/pit/report.txt` and `candidates.csv`: DIT15 baseline, per-year and cost tables
- `docs/PHASE_A_FREEZE.md`: documented baseline row and cost table
- `results/nogit-145d6302/phase_b/experiment_1/primary/{results.json, pooled_metrics.csv, fold_selections.csv}`, `strict_htf/results.json`, `manifest.json`
- `results/nogit-145d6302/phase_b/experiment_1/report/{primary_pooled.csv, primary_boot.csv}`: month-block bootstrap
- `results/nogit-145d6302/phase_b/tier1/folds/folds.csv`: fold windows and counts
""")
st.caption("Frozen backtest and experiment results on cached historical data. Past results do not predict future results. Not trading advice.")
