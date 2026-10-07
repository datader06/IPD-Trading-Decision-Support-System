"""Probe: Kite minute bars vs Yahoo samples, and minute-level replay of the golden exit cases. Read-only."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from kite_client import KiteReadOnly  # noqa: E402
from exits import replay_trade  # noqa: E402

PACK = ROOT / "legacy" / "handoff" / "handoff"
SESSION_OPEN = pd.Timedelta(hours=9, minutes=15)
OHLC = ["open", "high", "low", "close"]


def load_cases():
    g = pd.read_csv(PACK / "golden" / "golden_exit_cases.csv")
    cases = [
        dict(case=r.case_id, ticker=r.ticker, type=r.type, entry_time=pd.Timestamp(r.entry_time),
             entry=r.entry_price, stop=r.stop, target=r.target,
             heur=r.expected_outcome_fixed_rule, truth=r.independent_truth, truth_note="")
        for r in g.itertuples()
    ]
    d = pd.read_csv(PACK / "results" / "mtf_trade_diagnostics_dit_FIXEDEXIT.csv")
    r = d[d.ticker == "DIVISLAB.NS"].iloc[0]
    cases.append(dict(case="DIVISLAB", ticker=r.ticker, type=r.type, entry_time=pd.Timestamp(r.entry_time),
                      entry=r.entry_price, stop=r.stop, target=r.target, heur=r.outcome,
                      truth="loss", truth_note=" (user verdict, unconfirmed)"))
    return cases


def build_bars(m, minutes):
    """Aggregate minute bars into `minutes`-wide bars aligned to 09:15."""
    m = m.copy()
    off = (m["timestamp"] - m["timestamp"].dt.normalize() - SESSION_OPEN) // pd.Timedelta(minutes=minutes)
    m["bar"] = m["timestamp"].dt.normalize() + SESSION_OPEN + off * pd.Timedelta(minutes=minutes)
    g = m.groupby("bar")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                        "low": g["low"].min(), "close": g["close"].last()})
    return out


def compare(built, sample_path, lo, hi):
    if not sample_path.exists():
        return "no sample"
    y = pd.read_csv(sample_path, parse_dates=["timestamp"]).set_index("timestamp")
    y = y[(y.index >= lo) & (y.index <= hi)]
    common = built.index.intersection(y.index)
    if len(common) == 0:
        return f"match 0/{len(y)} yahoo"
    diff = (built.loc[common, OHLC] - y.loc[common, OHLC]).abs().max().max()
    return f"match {len(common)}/{len(y)} yahoo, built {len(built)}, maxdiff {diff:.4f}"


def replay(k, tok, sym, c, bars60):
    """Scan start = first 60m bar start at/after entry_time; scored by src/exits.replay_trade (15minute, then 1minute)."""
    starts = bars60.index[bars60.index >= c["entry_time"]]
    if len(starts) == 0:
        return "NODATA", "no 60m bar at/after entry"
    r = replay_trade(k, sym, tok, c["type"], c["entry"], c["stop"], c["target"], starts[0])
    info = ""
    if r["fill_time"] is not None:
        info = f"fill {pd.Timestamp(r['fill_time']):%m-%d %H:%M} @ {r['fill_price']:g}{' GAP' if r['gap_fill'] else ''}; "
    ex = f" at {pd.Timestamp(r['exit_time']):%m-%d %H:%M}" if r["exit_time"] is not None else ""
    why = f"; still AMBIGUOUS: {r['reason']}" if r["outcome"] == "AMBIGUOUS" else ""
    return r["outcome"], f"[{r['decided_interval']}; 15m={r['r15_outcome']}] {info}{r['detail']}{ex}{why}"


def main():
    cases = load_cases()
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    unmapped = sorted({c["ticker"] for c in cases if c["ticker"].replace(".NS", "") not in tokmap})
    print(f"MAPPING: {len(cases)} cases, unmapped: {unmapped if unmapped else 'none'}")

    rows, results = [], []
    for c in cases:
        sym = c["ticker"].replace(".NS", "")
        if sym not in tokmap:
            continue
        d0 = c["entry_time"].normalize()
        lo, hi = d0 - timedelta(days=2), d0 + timedelta(days=10, hours=23, minutes=59)
        m = k.historical_data(int(tokmap[sym]), lo.to_pydatetime(), hi.to_pydatetime(), "minute", symbol=sym)
        if m.empty:
            print(f"{c['case']} {c['ticker']}: NO MINUTE DATA"); continue
        m["timestamp"] = pd.to_datetime(m["timestamp"])
        # (a)
        per_day = m.groupby(m["timestamp"].dt.date).size()
        flagged = {str(d): int(n) for d, n in per_day.items() if not 370 <= n <= 380}
        # (b)
        b60 = build_bars(m, 60)
        y60 = compare(b60, PACK / "data" / "bars" / f"{c['ticker']}__60m.csv", m["timestamp"].min(), m["timestamp"].max())
        # (c)
        y5 = "-"
        if c["case"].startswith("E") and 5 <= int(c["case"][1:]) <= 13:
            b5 = build_bars(m, 5)
            y5 = compare(b5, PACK / "data" / "bars5m" / f"{c['ticker']}__5m.csv", m["timestamp"].min(), m["timestamp"].max())
        # (d)
        label, detail = replay(k, int(tokmap[sym]), sym, c, b60)
        truth = c["truth"]
        if label == "AMBIGUOUS":
            verdict = "AMBIGUOUS"
        elif truth == "unconfirmed":
            verdict = "ungraded"
        elif label == truth:
            verdict = "AGREE"
        else:
            verdict = "DISAGREE"
        results.append(verdict)
        print(f"\n{c['case']} {c['ticker']} {c['type']} entry {c['entry_time']:%Y-%m-%d %H:%M} @ {c['entry']} stop {c['stop']:.2f} tgt {c['target']:.2f}")
        print(f"  a) minute bars {len(m)}, first {m['timestamp'].min():%Y-%m-%d %H:%M}, days {len(per_day)}, per-day min/max {per_day.min()}/{per_day.max()}, flagged(outside 370-380): {flagged or 'none'}")
        print(f"  b) 60m from minutes vs yahoo: {y60}")
        print(f"  c) 5m from minutes vs yahoo: {y5}")
        print(f"  d) replay={label} | heuristic={c['heur']} | truth={truth}{c['truth_note']} -> {verdict} | {detail}")
        rows.append((c["case"], c["ticker"], label, c["heur"], truth + c["truth_note"], verdict))

    print("\nSUMMARY")
    print(f"{'case':9}{'ticker':15}{'replay':11}{'heuristic':10}{'truth':38}{'verdict'}")
    for r in rows:
        print(f"{r[0]:9}{r[1]:15}{r[2]:11}{r[3]:10}{r[4]:38}{r[5]}")
    from collections import Counter
    print("\nCOUNTS", dict(Counter(results)), "of", len(results))
    e2 = next((r for r in rows if r[0] == "E02"), None)
    print("E02 present:", bool(e2))


if __name__ == "__main__":
    main()
