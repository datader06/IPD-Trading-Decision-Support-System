"""Strategy & Architecture page (project overview for the presentation).

Strategy descriptions follow docs/RULES.md and the Phase A code docstrings; frozen trade counts are parsed from docs/PHASE_A_FREEZE.md;
file paths in the architecture diagram are checked for existence when the page loads. Nothing is computed, fetched or re-run here.
"""
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import registry as R  # noqa: E402

FREEZE = ROOT / "docs" / "PHASE_A_FREEZE.md"
FEED_META = ROOT / "results" / "scanner_demo_smoke" / "scanner_feed_meta.json"
EXP_MAN = ROOT / "results" / "nogit-145d6302" / "phase_b" / "experiment_1" / "manifest.json"
FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"

st.set_page_config(page_title="Strategy & Architecture", page_icon="🧭", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
.banner {border-radius: 10px; padding: .7rem 1rem; margin-bottom: .6rem; font-weight: 600;}
.banner.info {background: #0f1f33; border: 1px solid #3b82f6; color: #bcd6ff;}
.banner.warn {background: linear-gradient(90deg, #3b2a05, #1f1a0b); border: 1px solid #f5a524; color: #ffd48a;}
.banner small {display: block; font-weight: 400; margin-top: .15rem; opacity: .9;}
.card {background: #121923; border: 1px solid #1f2a37; border-radius: 12px; padding: 1rem 1.1rem; height: 100%;}
.card h4 {margin: 0 0 .15rem 0; font-size: 1.2rem;}
.card .sub {color: #8b97a7; font-size: .8rem; margin-bottom: .6rem;}
.card .tf {display: grid; grid-template-columns: 1fr 1fr 1fr; gap: .4rem; margin-bottom: .7rem;}
.card .tf div {background: #0b0f14; border: 1px solid #1f2a37; border-radius: 8px; padding: .4rem .5rem; text-align: center;}
.card .tf b {display: block; font-size: 1rem;}
.card .tf span {color: #8b97a7; font-size: .66rem; text-transform: uppercase; letter-spacing: .5px;}
.card .stat {color: #8b97a7; font-size: .8rem;}
.card .stat b {color: #e6edf3;}
[data-testid="stTable"] table {width: 100%; table-layout: fixed;}
[data-testid="stTable"] th:first-child, [data-testid="stTable"] td:first-child {width: 20%; font-weight: 600;}
[data-testid="stTable"] th:nth-child(2), [data-testid="stTable"] td:nth-child(2) {width: 9%;}
[data-testid="stTable"] td {white-space: normal; word-wrap: break-word; vertical-align: top; font-size: .88rem;}
@media (max-width: 900px) {[data-testid="stTable"] th:first-child, [data-testid="stTable"] td:first-child {width: 28%;}
                           [data-testid="stTable"] th:nth-child(2), [data-testid="stTable"] td:nth-child(2) {width: 14%;} [data-testid="stTable"] td {font-size: .8rem;}}
.flow {display: flex; flex-wrap: wrap; gap: 1.1rem; align-items: stretch; margin: .4rem 0 1rem 0;}
.step {flex: 1 1 190px; background: #121923; border: 1px solid #1f2a37; border-radius: 12px; padding: .8rem .9rem; position: relative;}
.step .no {display: inline-block; background: #3b82f6; color: #0b0f14; font-weight: 800; border-radius: 999px; width: 1.5rem; height: 1.5rem;
           text-align: center; line-height: 1.5rem; margin-right: .4rem;}
.step h5 {display: inline; font-size: 1rem;}
.step p {color: #c4cdd8; font-size: .82rem; margin: .5rem 0 .4rem 0;}
.step code {font-size: .7rem; color: #8bb4ff; background: #0b0f14; display: block; padding: .15rem .35rem; border-radius: 5px; margin-top: .2rem;
            word-break: break-all;}
.step code.missing {color: #ef5350;}
.step:not(:last-child)::after {content: "➜"; position: absolute; right: -1.05rem; top: 45%; color: #3b82f6; font-size: 1.1rem;}
.step.ml {border-color: #f5a524;}
.pill {display: inline-block; padding: .08rem .55rem; border-radius: 999px; font-size: .72rem; font-weight: 700; color: #0b0f14; background: #f5a524;}
.lim {background: #121923; border: 1px solid #1f2a37; border-left: 4px solid #ef5350; border-radius: 8px; padding: .65rem .9rem; margin-bottom: .55rem;}
.lim b {display: block; margin-bottom: .1rem;}
.lim span {color: #c4cdd8; font-size: .86rem;}
@media (max-width: 900px) {.step:not(:last-child)::after {display: none;} .card .tf {grid-template-columns: 1fr;}}
</style>
""", unsafe_allow_html=True)


def frozen_rows():
    """Frozen baseline rows of docs/PHASE_A_FREEZE.md (trades, W/L/ambiguous, win rate, expectancy, PF)."""
    rows = {}
    for line in FREEZE.read_text(encoding="utf-8").splitlines():
        for s in ("DIT15", "WIT", "MIT"):
            if line.startswith(f"| **{s}**"):
                f = [x.strip() for x in line.split("|")]
                w, l, a = (int(x) for x in f[5].replace(" ", "").split("/"))
                rows[s] = dict(trades=int(f[4]), W=w, L=l, A=a, win=f[6], exp=f[7], pf=f[8])
    return rows


@st.cache_data(show_spinner=False)
def facts():
    out = dict(rows=frozen_rows(), meta=None, man=None)
    if FEED_META.exists():
        out["meta"] = json.loads(FEED_META.read_text(encoding="utf-8"))
    if EXP_MAN.exists():
        out["man"] = json.loads(EXP_MAN.read_text(encoding="utf-8"))
    out["universe"] = len(list(FRAMES.glob("*__1d.csv"))) if FRAMES.exists() else 503
    return out


F = facts()
rows, meta, man = F["rows"], F["meta"], F["man"]
as_of = meta["as_of_dates"][-1] if meta else "2026-10-01"
as_of_txt = f"{int(as_of[8:])} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(as_of[5:7]) - 1]} {as_of[:4]}"
sampled = meta["tickers"] if meta else 100

st.title("Strategy & Architecture")
st.markdown('<div class="banner info">Project overview for the presentation<small>How the three multi-timeframe supply/demand strategies work, how '
            'the system is built, and what the evidence does and does not show. All descriptions follow the project documentation and code.'
            '</small></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------------------ 1. strategies
st.header("1. The strategies")
st.markdown("""
All three strategies trade **supply and demand zones**. A zone is a small **base** (a short consolidation of small candles) followed by an
explosive **legout** candle (or two). A **demand** zone is a base before a strong rise (buy zone); a **supply** zone is a base before a strong fall
(sell zone). Each zone has a **proximal** line (the edge nearest price) and a **distal** line (the far edge, where the stop sits).
The idea is multi-timeframe: a **higher timeframe (HTF)** zone gives the bias, a **lower timeframe (LTF)** zone inside it gives the entry, and an
**intermediate timeframe** is used only to read the trend.
""")
cols = st.columns(3)
SPEC = {"DIT15": ("Daily", "2-hour", "15-minute", "Daily HTF zone, 2h trend, 15-minute entry"),
        "WIT": ("Weekly", "Daily", "2-hour", "Weekly HTF zone, daily trend, 2-hour entry"),
        "MIT": ("Monthly", "Weekly", "Daily", "Monthly HTF zone, weekly trend, daily entry")}
for col, s in zip(cols, SPEC):
    htf, tr, ltf, sub = SPEC[s]
    r = rows.get(s)
    stat = (f'<div class="stat">Frozen strict list: <b>{r["trades"]} trades</b> ({r["W"]} wins / {r["L"]} losses / {r["A"]} ambiguous), '
            f'win rate <b>{r["win"]}</b>, gross expectancy <b>{r["exp"]} R</b>, profit factor <b>{r["pf"]}</b>.</div>') if r else ""
    col.markdown(f'<div class="card"><h4>{s}</h4><div class="sub">{sub}</div><div class="tf"><div><b>{htf}</b><span>HTF zone (bias)</span></div>'
                 f'<div><b>{tr}</b><span>Trend</span></div><div><b>{ltf}</b><span>LTF zone (entry)</span></div></div>{stat}</div>',
                 unsafe_allow_html=True)
st.caption("Counts are the frozen Phase A rule-only results from docs/PHASE_A_FREEZE.md (entries 2021-01-01 to 2026-10-01, gross R). "
           "The weekly and monthly HTF bars are built from daily data.")

st.subheader("The shared trade rules")
rules = [
    ("Zone construction", "R01–R06", "Base candles are counted back from the legout and a base longer than 5 candles is rejected; the legout is a candle with body at least about 1.3 × ATR "
     "closing in the outer 25% of its range (one to three candles); proximal at the base's body edge, distal at its far wick plus a 0.1 × ATR buffer."),
    ("HTF–LTF pairing", "R09", "The LTF zone must form inside the HTF zone's own formation window, still be untouched when the HTF zone confirms, and have at least 30% of "
     "its height inside the HTF zone."),
    ("Trend filter", "R11", "Read from zone breaks on the intermediate timeframe (two supply breaks = up, two demand breaks = down, otherwise sideways; an "
     "all-time high counts as up). Demand is blocked only in a downtrend, supply only in an uptrend. Checked at HTF formation and again at entry."),
    ("HTF freshness", "R10", "If price already reached the HTF base's wick extreme before the entry date, the zone is used up and the trade is skipped."),
    ("Entry", "R08", "The first touch of the LTF zone's proximal line after the HTF zone is confirmed. The replay fills at that line, or at the open if price gaps through it."),
    ("Stop and target", "R09", "Stop at the LTF zone's distal line; target at entry ± 2 × risk (fixed 2:1 reward to risk)."),
    ("Sizing", "R13", "Maximum loss Rs 1,000 per trade, capital Rs 1,00,000 with no leverage: shares = min(1000 / risk, 100000 / entry)."),
    ("Outcome", "R12", "Price must enter the zone first; then the stop or target decides. Replayed on 15-minute bars, then 1-minute bars when a bar is ambiguous. "
     "Outcomes: WIN, LOSS, AMBIGUOUS, OPEN, CENSORED, NOFILL."),
]
import pandas as pd  # noqa: E402

st.table(pd.DataFrame([{"Rule": a, "Ref": b, "What it does": c} for a, b, c in rules]).set_index("Rule"))  # st.table wraps long text (desktop and phone)
st.caption("Ref = rule IDs in docs/RULES.md. Phase A hardening made every decision point-in-time: bars are used only after they close, and each trade has an explicit decision time "
           "(start of the entry bar for DIT15 and WIT, entry day 09:15 for MIT).")

# ------------------------------------------------------------------------------------------------------------ 2. architecture
st.header("2. System architecture")
steps = [
    ("Cached market data", "Kite historical bars (daily, 60-minute, 15-minute, cached 1-minute files for ambiguous cases). Read-only; nothing is fetched at run time.",
     ["data/cache/kite_frames_dit15_long", "src/kite_client.py"], False),
    ("Supply/demand zones", "Impulsive legouts, base walk-back, zone lines, freshness; HTF, LTF and trend zones for each strategy.",
     ["legacy/handoff/handoff/code/sd_zones.py", "src/base_candles.py"], False),
    ("Candidate generation", "HTF–LTF matching, trend and wick-freshness filters; one candidate per trade with entry, stop, target.",
     ["src/candidates.py", "src/candidates_mtf.py"], False),
    ("Labeling & backtesting", "Deterministic replay gives WIN/LOSS/AMBIGUOUS; portfolio metrics and cost scenarios; WIN = 1, LOSS = 0 labels.",
     ["src/replay.py", "src/portfolio.py", "src/ml/labels.py"], False),
    ("Walk-forward ML evaluation", "Experimental filter: 18 frozen features, four models, chronological folds, 2026 holdout untouched.",
     ["src/ml/splits.py", "src/ml/models.py", "src/ml/experiment.py"], True),
    ("Scanner dashboard", "Streamlit demo of current setup status from cached data, plus these results pages.",
     ["src/scanner/feed.py", "app.py"], False),
]
n_paths = n_found = 0
html = ['<div class="flow">']
for i, (title, text, paths, ml) in enumerate(steps, 1):
    chips = []
    for p in paths:
        ok = (ROOT / p).exists()
        n_paths += 1
        n_found += ok
        chips.append(f'<code class="{"" if ok else "missing"}">{p}{"" if ok else " (missing)"}</code>')
    html.append(f'<div class="step{" ml" if ml else ""}"><span class="no">{i}</span><h5>{title}</h5><p>{text}</p>{"".join(chips)}</div>')
html.append("</div>")
st.markdown("".join(html), unsafe_allow_html=True)
st.caption(f"{n_found} of {n_paths} referenced files found in the project. Step 5 is highlighted because it is experimental (next section).")

# ------------------------------------------------------------------------------------------------------------ 3. ML
st.header("3. The role of machine learning")
n_feat = len(R.MODEL_COLUMNS)
champ = "no champion was selected" if (man and man["champion"]["primary"] is None) else "see the results page"
st.markdown(f'<div class="banner warn">ML is an experimental trade filter — not a proven source of predictive edge<small>In Experiment 1 no model '
            f'demonstrated a reliable edge and {champ}. The rule-based strategies remain the system; ML only tested whether it could improve them.</small></div>',
            unsafe_allow_html=True)
a, b = st.columns(2)
a.markdown(f"""
**What it does**
- Takes or skips candidates the rules already produced. It never changes an entry, stop, target, zone or trend rule.
- Uses {n_feat} frozen features known at the decision time (zone shape, volatility, trend, relative strength, session timing).
  The entry bar itself is never read.
- Trains only on resolved trades (WIN = 1, LOSS = 0). Ambiguous and unresolved trades are scored but never used as labels.
- Compares four models: logistic regression, random forest, gradient boosting and XGBoost.
""")
b.markdown(f"""
**How it was tested**
- Walk-forward by half-year, 2023H1–2025H2, with an embargo and a purge at every boundary and validation-only tuning.
- The 2026 holdout ({man['scope']['holdout_rows_excluded'] if man else 781} candidates) was never used and was not scored.
- Decisions were preregistered before training; a shuffled-label control and a repeat run both passed.
- Result: ROC-AUC about 0.5 for every model, and too few trades to select a champion. Details are on the Backtest & ML Results page.
""")

# ------------------------------------------------------------------------------------------------------------ 4. limitations
st.header("4. Limitations")
dit = rows.get("DIT15")
amb_share = f' ({100 * dit["A"] / dit["trades"]:.0f}% of the DIT15 strict list)' if dit else ""
lims = [
    ("Cached data only", f"All results and the scanner use cached market data through {as_of_txt}. Nothing is fetched live, so the scanner reflects that "
     "date, not today's market."),
    ("Sampled scanner universe", f"The demo scanner covers {sampled} of {F['universe']} tickers, to keep the build time short. Strategy results use the full "
     f"{F['universe']}-ticker universe."),
    ("Transaction costs", "Broker costs and slippage are not fixed. Results are shown gross and at 0.10%, 0.20% and 0.30% round trip; the DIT15 gross edge "
     "does not survive any of them."),
    ("Ambiguous outcomes", f"Some trades cannot be settled even at 1-minute resolution (a target inside the entry bar, stop and target in the same bar, a gap "
     f"through the stop). They are counted as AMBIGUOUS, never converted into wins or losses{amb_share}."),
    ("Small samples and survivorship", f"WIT and MIT have only {rows['WIT']['W'] + rows['WIT']['L']} and {rows['MIT']['W'] + rows['MIT']['L']} resolved trades, too few for conclusions. The universe is today's listing "
     "(survivorship), moves under 35% are not treated as corporate actions, and 2026 is partly contaminated by chart reviews."),
    ("No live execution", "The system is a research and decision-support prototype. It places no orders and uses the broker API for historical data only. "
     "The scanner output is a demo, not trading advice."),
]
for t, d in lims:
    st.markdown(f'<div class="lim"><b>{t}</b><span>{d}</span></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------------------ 5. demo guide
st.header("5. Reading the app")
c1, c2, c3 = st.columns(3)
c1.markdown("**Scanner (main page)**  \nCurrent setup status per ticker and strategy from cached data: APPROACHING, IN ZONE, CONFIRMED or NO SETUP, "
            "with entry, stop, target and a chart.")
c2.markdown("**Backtest & ML Results**  \nThe frozen DIT15 baseline, the cost sensitivity, the Experiment 1 comparison and how it was validated.")
c3.markdown("**Strategy & Architecture** (this page)  \nWhat the strategies are, how the pieces fit, and what the evidence does and does not show.")
st.caption("Sources: docs/RULES.md, docs/PHASE_A_FREEZE.md, docs/PHASE_A_MTF_RESULTS.md, docs/EXPERIMENT_1_PREREGISTRATION.md, the Phase A and Phase B code. "
           "Past results do not predict future results. Not trading advice.")
