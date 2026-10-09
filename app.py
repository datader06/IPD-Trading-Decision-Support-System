"""IPD Trading Decision Support System: scanner demo dashboard.

  python -m streamlit run app.py

Reads the pre-built scanner feed (results/scanner_demo_smoke/, built by scripts/run_scanner_feed.py from the cached frames) and the
cached OHLC frames for charts. Fetches nothing, trains nothing. DEMO DATA: not live trading advice and not a backtest result.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
FEED = ROOT / "results" / "scanner_demo_smoke" / "scanner_feed_asof_2026-10-01.csv"
META = FEED.with_name("scanner_feed_meta.json")
FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
STRATEGIES = ("DIT15", "WIT", "MIT")
STATUSES = ("APPROACHING", "IN ZONE", "CONFIRMED", "NO SETUP")
COLORS = {"APPROACHING": "#f5a524", "IN ZONE": "#22d3ee", "CONFIRMED": "#34d399", "NO SETUP": "#6b7788"}
STRAT_TEXT = {"DIT15": "Daily HTF, 15m entry", "WIT": "Weekly HTF, 2h entry", "MIT": "Monthly HTF, daily entry"}
LEVEL_COLORS = dict(entry="#3b82f6", stop="#ef4444", target="#22c55e")

st.set_page_config(page_title="IPD Trading Decision Support System", page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
h1, h2, h3 {letter-spacing: .2px;}
.banner {background: linear-gradient(90deg, #3b2a05, #1f1a0b); border: 1px solid #f5a524; color: #ffd48a; border-radius: 10px;
         padding: .7rem 1rem; font-weight: 700; letter-spacing: .4px; margin-bottom: .4rem;}
.banner small {display: block; font-weight: 400; color: #e8c88f; margin-top: .15rem;}
.card {background: #121923; border: 1px solid #1f2a37; border-radius: 12px; padding: 1rem 1.1rem; height: 100%;}
.card h4 {margin: 0 0 .1rem 0; font-size: 1.15rem;}
.card .sub {color: #8b97a7; font-size: .8rem; margin-bottom: .7rem;}
.card .grid {display: grid; grid-template-columns: repeat(5, 1fr); gap: .4rem; text-align: center;}
.card .n {font-size: 1.5rem; font-weight: 700; line-height: 1.1;}
.card .l {color: #8b97a7; font-size: .68rem; text-transform: uppercase; letter-spacing: .5px;}
.pill {display: inline-block; padding: .12rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 700; color: #0b0f14;}
.kv {background: #121923; border: 1px solid #1f2a37; border-radius: 10px; padding: .55rem .8rem; margin-bottom: .5rem;}
.kv .k {color: #8b97a7; font-size: .7rem; text-transform: uppercase; letter-spacing: .5px;}
.kv .v {font-size: 1.12rem; font-weight: 650;}
.note {color: #8b97a7; font-size: .82rem;}
@media (max-width: 900px) {.card .grid {grid-template-columns: repeat(3, 1fr);}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_feed():
    df = pd.read_csv(FEED, parse_dates=["price_time", "htf_formed_at", "ltf_formed_at", "triggered_at"])
    meta = json.loads(META.read_text(encoding="utf-8"))
    return df, meta


@st.cache_data(show_spinner=False)
def load_ohlc(ticker, interval):
    p = FRAMES / f"{ticker}__{interval}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["timestamp"])
    return d[["timestamp", "open", "high", "low", "close"]].dropna()


def universe_size():
    n = len(list(FRAMES.glob("*__1d.csv"))) if FRAMES.exists() else 0
    return n or 503


def fmt_date(s):
    d = pd.Timestamp(s)
    return f"{d.day} {d:%b %Y}"


def num(v, nd=2):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:,.{nd}f}"


def pill(status):
    return f'<span class="pill" style="background:{COLORS[status]}">{status}</span>'


def valid(v):
    return v is not None and pd.notna(v) and np.isfinite(float(v)) and float(v) > 0


# ---------------------------------------------------------------------------------------------------------------- data
if not FEED.exists() or not META.exists():
    st.error(f"Scanner feed not found: {FEED.relative_to(ROOT)}. Build it with scripts/run_scanner_feed.py.")
    st.stop()
feed, meta = load_feed()
as_of = fmt_date(meta["as_of_dates"][-1])
n_sampled, n_universe = meta["tickers"], universe_size()

st.title("IPD Trading Decision Support System")
st.markdown(f'<div class="banner">DEMO DATA — As of {as_of} — {n_sampled} of {n_universe} tickers sampled'
            f'<small>Scanner demo built from cached market data. Not live trading advice and not a backtest result.</small></div>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------------------------- cards
cols = st.columns(3)
for col, s in zip(cols, STRATEGIES):
    g = feed[feed["strategy"] == s]
    cnt = g["status"].value_counts()
    cells = "".join(f'<div><div class="n" style="color:{COLORS[k]}">{int(cnt.get(k, 0))}</div><div class="l">{k}</div></div>'
                    for k in STATUSES)
    col.markdown(f'<div class="card"><h4>{s}</h4><div class="sub">{STRAT_TEXT[s]}</div><div class="grid">'
                 f'<div><div class="n">{g["ticker"].nunique()}</div><div class="l">Tickers</div></div>{cells}</div></div>',
                 unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filters")
    f_strat = st.multiselect("Strategy", STRATEGIES, default=list(STRATEGIES))
    f_status = st.multiselect("Status", STATUSES, default=["APPROACHING", "IN ZONE", "CONFIRMED"])
    f_ticker = st.multiselect("Ticker", sorted(feed["ticker"].unique()), placeholder="All tickers")
    st.caption("Add NO SETUP to the status filter to list tickers without a live setup.")
    st.divider()
    st.markdown(f'<div class="note">Feed: <b>{meta["label"]}</b><br>{meta["note"]}</div>', unsafe_allow_html=True)

view = feed[feed["strategy"].isin(f_strat) & feed["status"].isin(f_status)]
if f_ticker:
    view = view[view["ticker"].isin(f_ticker)]
order = {k: i for i, k in enumerate(STATUSES)}
view = view.assign(_o=view["status"].map(order), _d=view["distance_pct"].abs().fillna(1e9)).sort_values(
    ["_o", "_d", "strategy", "ticker"]).drop(columns=["_o", "_d"]).reset_index(drop=True)

st.subheader("Opportunities")
if view.empty:
    st.info("No rows match the current filters. Adjust the strategy, status or ticker filters.")
    st.stop()

SHOW = ["ticker", "strategy", "status", "current_price", "entry", "stop", "target", "risk_reward", "trend", "zone_type",
        "distance_to_entry", "distance_pct"]
table = view[SHOW].rename(columns={"current_price": "price", "risk_reward": "R:R", "zone_type": "zone",
                                   "distance_to_entry": "dist to entry", "distance_pct": "dist %"})


def row_style(r):
    if r["status"] == "APPROACHING":
        return ["background-color: rgba(245,165,36,.16); font-weight: 600"] * len(r)
    if r["status"] == "IN ZONE":
        return ["background-color: rgba(34,211,238,.13)"] * len(r)
    if r["status"] == "CONFIRMED":
        return ["background-color: rgba(52,211,153,.13)"] * len(r)
    return [""] * len(r)


styled = table.style.apply(row_style, axis=1)  # row highlight only; number display comes from column_config (values stay numeric, sorting works)
num2 = st.column_config.NumberColumn  # printf-style display format; the underlying numbers are untouched
col_cfg = {c: num2(format="%.2f") for c in ("price", "entry", "stop", "target", "dist to entry")}
col_cfg["R:R"] = num2(format="%.1f")
col_cfg["dist %"] = num2(format="%+.1f%%")
event = st.dataframe(styled, width="stretch", hide_index=True, height=min(60 + 35 * len(table), 420), column_config=col_cfg,
                     on_select="rerun", selection_mode="single-row", key="opp_table")
st.caption(f"{len(view)} rows. Click a row (or use the selector below) for the setup detail. Columns sort by clicking the header. "
           "Distance = last close minus entry: negative for a supply zone above price, positive for a demand zone below price.")

# ---------------------------------------------------------------------------------------------------------------- detail
labels = [f"{r.ticker} · {r.strategy} · {r.status}" for r in view.itertuples()]
sel = event.selection.rows if event and event.selection else []
if sel and sel[0] < len(labels) and st.session_state.get("_last_row") != (sel[0], labels[sel[0]]):
    st.session_state["_last_row"] = (sel[0], labels[sel[0]])
    st.session_state["inspect"] = labels[sel[0]]
if st.session_state.get("inspect") not in labels:
    st.session_state["inspect"] = labels[0]
st.subheader("Setup detail")
choice = st.selectbox("Inspect setup", labels, key="inspect")
row = view.iloc[labels.index(choice)]
status = row["status"]

head, _ = st.columns([3, 1])
head.markdown(f'### {row["ticker"]} &nbsp; <span class="note">{row["strategy"]} · {STRAT_TEXT[row["strategy"]]}</span> &nbsp; {pill(status)}',
              unsafe_allow_html=True)


def kv(col, k, v):
    col.markdown(f'<div class="kv"><div class="k">{k}</div><div class="v">{v}</div></div>', unsafe_allow_html=True)


left, right = st.columns([1, 2.2], gap="large")
with left:
    if status == "NO SETUP":
        st.info(row["data_note"] if isinstance(row["data_note"], str) else "No live setup.")
        kv(st, "Last close", num(row["current_price"]))
        kv(st, "Trend", row["trend"] if isinstance(row["trend"], str) else "n/a")
    else:
        direction = "SHORT" if row["zone_type"] == "supply" else "LONG"
        a, b = st.columns(2)
        kv(a, "Current price", num(row["current_price"]))
        kv(b, "Direction / zone", f'{direction} · {row["zone_type"]}')
        kv(a, "Entry", num(row["entry"]))
        kv(b, "Stop", num(row["stop"]))
        kv(a, "Target (2R)", num(row["target"]))
        kv(b, "Risk / reward", f'1 : {row["risk_reward"]:.1f}')
        kv(a, "Risk per share", f'{num(row["risk"])} ({100 * row["risk"] / row["entry"]:.2f}%)')
        kv(b, "Distance to entry", f'{num(row["distance_to_entry"])} ({row["distance_pct"]:+.1f}%)')
        kv(a, "Distance (ATR)", f'{row["distance_atr"]:+.1f}' if pd.notna(row["distance_atr"]) else "n/a")
        kv(b, "Trend", row["trend"] if isinstance(row["trend"], str) else "n/a")
        kv(a, "HTF zone", f'{num(row["htf_proximal"])} – {num(row["htf_distal"])}')
        kv(b, "LTF zone", f'{num(row["ltf_proximal"])} – {num(row["ltf_distal"])}')
        kv(a, "HTF formed", fmt_date(row["htf_formed_at"]) if pd.notna(row["htf_formed_at"]) else "n/a")
        kv(b, "LTF formed", fmt_date(row["ltf_formed_at"]) if pd.notna(row["ltf_formed_at"]) else "n/a")
        if pd.notna(row["triggered_at"]):
            kv(a, "Triggered", str(row["triggered_at"])[:16])
            kv(b, "Open R", num(row["open_r"]) if pd.notna(row["open_r"]) else "n/a")
        st.caption(f'Live strict setups for this ticker and strategy: {int(row["n_live_setups"])} (the nearest is shown). '
                   "Entry is the LTF zone proximal line, stop its distal line, target entry ± 2 × risk.")

with right:
    c1, c2 = st.columns([1, 1])
    tf = c1.radio("Chart timeframe", ["Daily", "15-minute"], horizontal=True, key="tf")
    bars = c2.slider("Bars shown", 40, 400, 150, step=10, key="bars") if tf == "Daily" else c2.slider("Sessions shown", 2, 20, 8, key="sess")
    ohlc = load_ohlc(row["ticker"], "1d" if tf == "Daily" else "15m")
    if ohlc is None or ohlc.empty:
        st.warning("No cached OHLC data for this ticker, so no chart is shown.")
    else:
        if tf == "Daily":
            d = ohlc.tail(bars)
        else:
            days = ohlc["timestamp"].dt.normalize().drop_duplicates().tail(bars)
            d = ohlc[ohlc["timestamp"].dt.normalize().isin(days)]
        fig = go.Figure(go.Candlestick(x=d["timestamp"], open=d["open"], high=d["high"], low=d["low"], close=d["close"], name="Price",
                                       increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))
        x0, x1 = d["timestamp"].iloc[0], d["timestamp"].iloc[-1]
        drawn, skipped = [], []
        if status != "NO SETUP":
            e, s_, t_ = row["entry"], row["stop"], row["target"]
            ok = all(valid(v) for v in (e, s_, t_)) and ((s_ < e < t_) if row["zone_type"] == "demand" else (t_ < e < s_))
            if ok:
                for nm, v in (("Entry", e), ("Stop", s_), ("Target", t_)):
                    fig.add_trace(go.Scatter(x=[x0, x1], y=[v, v], mode="lines", name=f"{nm} {v:,.2f}",
                                             line=dict(color=LEVEL_COLORS[nm.lower()], width=1.6, dash="dash")))
                fig.add_hrect(y0=min(e, s_), y1=max(e, s_), fillcolor="#3b82f6", opacity=0.18, line_width=0)
                drawn += ["entry", "stop", "target", "LTF zone"]
            else:
                skipped.append("entry/stop/target (invalid or inconsistent values)")
            hp, hd = row["htf_proximal"], row["htf_distal"]
            if valid(hp) and valid(hd) and hp != hd:
                fig.add_trace(go.Scatter(x=[x0, x1, x1, x0, x0], y=[hp, hp, hd, hd, hp], mode="lines", name="HTF zone",
                                         fill="toself", fillcolor="rgba(245,165,36,.12)", line=dict(color="#f5a524", width=1, dash="dot")))
                drawn.append("HTF zone")
            else:
                skipped.append("HTF zone")
        last = ohlc.iloc[-1]
        fig.add_hline(y=float(last["close"]), line_color="#9aa7b8", line_width=1, line_dash="dot",
                      annotation_text=f"last close {last['close']:,.2f}", annotation_position="right")
        rb = [dict(bounds=["sat", "mon"])]
        if tf != "Daily":
            rb.append(dict(bounds=[15.5, 9.25], pattern="hour"))
        fig.update_xaxes(rangebreaks=rb, rangeslider_visible=False, gridcolor="#1a2330")
        fig.update_yaxes(gridcolor="#1a2330", tickformat=",.2f")
        fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=520,
                          margin=dict(l=10, r=10, t=95, b=10),
                          legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=11)),
                          title=dict(text=f'{row["ticker"]} · {tf.lower()} · cached bars to {pd.Timestamp(last["timestamp"]):%d %b %Y}',
                                     font=dict(size=14), x=0, y=0.97, xanchor="left", yanchor="top"))
        st.plotly_chart(fig, width="stretch")
        note = "Drawn: " + (", ".join(drawn) if drawn else "price only")
        if skipped:
            note += " · not drawn: " + ", ".join(skipped)
        st.caption(note + ". Candles are the cached bars; levels come from the scanner feed.")

# ---------------------------------------------------------------------------------------------------------------- footer
with st.expander("Status definitions and limitations"):
    d = meta["definitions"]
    st.markdown(f"""
- **APPROACHING**: the lower-timeframe zone is untouched and the last close is on the entry side of its proximal line, within
  {d['approach_max_atr']:.0f} ATRs or within {d['approach_max_pct']:.0f}% of the entry (the 10% rule is a demo choice).
- **IN ZONE**: the entry level was touched on the latest cached day and the replayed trade is still live (neither stop nor target hit).
- **CONFIRMED**: the entry was touched earlier (within {d['confirmed_max_age_days']} days) and the trade is still live.
- **NO SETUP**: no live strict setup for that ticker and strategy.
- Setups use the frozen strict (B0) zone, matching, trend and wick-freshness rules; the scanner keeps untouched and live zones, which the
  historical builders drop. It is a demonstration on a **{n_sampled}-ticker sample** of cached data as of {as_of}, with no live fetch.
- No edge is claimed: the frozen rule sets are about break-even after costs, and the Experiment 1 ML filter showed no improvement.
  This is not trading advice.
""")
