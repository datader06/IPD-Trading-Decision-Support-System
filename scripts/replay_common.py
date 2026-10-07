"""Shared exit scoring for all trade lists: calls src/exits.replay_trade (15minute, then 1minute for AMBIGUOUS).

Standing rule (CLAUDE.md): automatic; stop only if one run needs > 1,500 Kite requests. Heuristic exit = labelled comparison only.
"""
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from exits import replay_trade  # noqa: E402
from kite_client import KiteReadOnly, CACHE_DIR, cache_path  # noqa: E402

MAX_REQUESTS = 1500
HORIZON_DAYS = 90
HORIZON_BY_COMBO = {"qit": 365}  # weekly-execution trades take months to resolve
SPLIT = pd.Timestamp("2026-01-01")
SESSION = pd.Timedelta(hours=9, minutes=15)


def scan_start(combo, entry_time):
    """dit15: the 15m entry bar start. MIT: entry day 09:15. WIT/DIT: first 60m bar start (09:15 + k h) at or after the entry label."""
    day = entry_time.normalize()
    if combo == "dit15":  # entry label is already a 15-minute bar start
        return entry_time
    if combo == "qit":  # weekly bar labelled by its Sunday: scan from that week's Monday 09:15
        return entry_time.normalize() - pd.Timedelta(days=6) + SESSION
    if combo == "mit":
        return day + SESSION
    for k in range(7):
        s = day + SESSION + pd.Timedelta(hours=k)
        if s >= entry_time:
            return s
    return day + pd.Timedelta(days=1) + SESSION


def boot_ci(wins, n, reps=5000):
    if n == 0:
        return "n/a"
    x = np.random.default_rng(12345).binomial(n, wins / n, reps) / n
    lo, hi = np.percentile(x, [2.5, 97.5])
    return f"[{100 * lo:.0f}-{100 * hi:.0f}]"


def cache_count():
    return sum(1 for _ in CACHE_DIR.glob("*/*/*.csv")) if CACHE_DIR.exists() else 0


def planned_requests(df, combo):
    """Uncached 15minute windows + worst case two 1minute chunks for each trade that may need a drill-down."""
    from datetime import timedelta
    h = timedelta(days=HORIZON_BY_COMBO.get(combo, HORIZON_DAYS))
    p15 = 0
    for t, s in zip(df["ticker"], df["scan_start"]):
        d0 = s.normalize().to_pydatetime()
        p15 += 0 if cache_path(t.replace(".NS", ""), "15minute", d0, d0 + h).exists() else 1
    known = df["exit_prev_ambiguous"].sum() if "exit_prev_ambiguous" in df else len(df)
    return p15, p15 + 2 * int(known)


def score(df, combo, k, tokmap):
    rows = []
    for tr in df.itertuples():
        sym = tr.ticker.replace(".NS", "")
        if sym not in tokmap:
            r = dict(outcome="AMBIGUOUS", decided_interval=None, reason="NO_MINUTE_DATA (no Kite symbol)", r15_outcome="",
                     no_minute_data=True, r=None, fill_time=None, fill_price=None, gap_fill=False, exit_time=None,
                     exit_price=None, detail="")
        else:
            r = replay_trade(k, sym, int(tokmap[sym]), tr.type, tr.entry_price, tr.stop, tr.target, tr.scan_start,
                             horizon_days=HORIZON_BY_COMBO.get(combo, HORIZON_DAYS))
        rows.append(dict(exit_outcome=r["outcome"], exit_interval=r["decided_interval"], exit_reason=r["reason"],
                         exit_r15=r["r15_outcome"], exit_no_minute_data=r["no_minute_data"],
                         exit_r=np.nan if r["r"] is None else r["r"], fill_time=r["fill_time"],
                         fill_price=np.nan if r["fill_price"] is None else r["fill_price"], gap_fill=r["gap_fill"],
                         exit_time_new=r["exit_time"], exit_detail=r["detail"]))
    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out["heuristic_outcome"] = out["outcome"].where(out["outcome"].isin(["win", "loss"]), "OPEN")
    out["heuristic_r"] = np.where(out["outcome"] == "win", 2.0, np.where(out["outcome"] == "loss", -1.0, np.nan))
    out["heuristic_pnl"] = np.where(out["outcome"] == "win", out["shares"] * out["risk"] * 2,
                                    np.where(out["outcome"] == "loss", -out["shares"] * out["risk"], 0.0))
    out["exit_pnl"] = out["exit_r"] * out["shares"] * out["risk"]
    return out


def block(label, d):
    c = Counter(d["exit_outcome"])
    w, l, amb = c["win"], c["loss"], c["AMBIGUOUS"]
    nmd = int(((d["exit_outcome"] == "AMBIGUOUS") & d["exit_no_minute_data"]).sum())
    res = d[d["exit_outcome"].isin(["win", "loss"])]
    r, pnl = res["exit_r"].to_numpy(dtype=float), res["exit_pnl"].to_numpy(dtype=float)
    a = d[d["exit_outcome"] == "AMBIGUOUS"]
    unit = (a["shares"] * a["risk"]).to_numpy(dtype=float)
    n = len(d)
    s = (f"{label}: n={n} wins={w} losses={l} AMBIGUOUS={amb} (of which NO_MINUTE_DATA {nmd}) OPEN={c['OPEN']} NOFILL={c['NOFILL']} "
         f"sum={w + l + amb + c['OPEN'] + c['NOFILL']} win%={100 * w / (w + l) if w + l else float('nan'):.1f} "
         f"boot95={boot_ci(w, w + l)} avgR={r.mean() if len(r) else float('nan'):+.3f} totalRs={pnl.sum():+,.0f}"
         + ("  SAMPLE<30" if n < 30 else ""))
    if amb:
        for nm, rv in (("best (all AMBIGUOUS win)", 2.0), ("worst (all AMBIGUOUS lose)", -1.0)):
            ww = w + (amb if rv > 0 else 0)
            tot = len(r) + amb
            s += (f"\n      {nm}: win%={100 * ww / (w + l + amb):.1f} avgR={(r.sum() + rv * amb) / tot:+.3f} "
                  f"totalRs={pnl.sum() + (rv * unit).sum():+,.0f}")
    return s


def report(out, combo, title):
    print(f"\n{title}")
    slices = [("ALL", out), ("2024", out[out.entry_time.dt.year == 2024]), ("2025", out[out.entry_time.dt.year == 2025]),
              ("2026", out[out.entry_time.dt.year == 2026]), ("TRAIN (<2026-01-01)", out[out.entry_time < SPLIT]),
              ("HOLDOUT (2026)", out[out.entry_time >= SPLIT])]
    for lab, sub in slices:
        print(block(f"{lab:19}", sub))
    print("per-year n add up:", sum(len(s) for _, s in slices[1:4]), "of", len(out))
    print("\nheuristic exit (labelled comparison only): "
          f"wins={int((out.heuristic_outcome == 'win').sum())} losses={int((out.heuristic_outcome == 'loss').sum())} "
          f"totalRs={out.heuristic_pnl.sum():+,.0f}")
    diff = out[out["heuristic_outcome"] != out["exit_outcome"]]
    print(f"trades whose final outcome differs from the heuristic: {len(diff)} of {len(out)}")
    for t in diff.itertuples():
        print(f"  {t.ticker} {t.entry_time:%Y-%m-%d %H:%M} heuristic={t.heuristic_outcome} final={t.exit_outcome} "
              f"decided_by={t.exit_interval} {t.exit_reason}")


def run(combo, src, out_path, title):
    """Score every trade in `src` (a *_heuristic.csv) with replay_trade, save to out_path, print the report."""
    df = pd.read_csv(src, parse_dates=["entry_time"])
    df["scan_start"] = [scan_start(combo, t) for t in df["entry_time"]]
    pmin, pmax = planned_requests(df, combo)
    print(f"{title}: {len(df)} trades; planned Kite requests: min {pmin} (uncached 15minute), max {pmax} (plus 1minute drill-downs)")
    if pmax > MAX_REQUESTS:
        print(f"STOP: {pmax} > {MAX_REQUESTS} (standing rule)")
        return None
    k = KiteReadOnly()
    inst = k.instruments("NSE")
    eq = inst[(inst["instrument_type"] == "EQ") & (inst["segment"] == "NSE")]
    tokmap = dict(zip(eq["tradingsymbol"], eq["instrument_token"]))
    before = cache_count()
    out = score(df, combo, k, tokmap)
    print(f"new cache files written (= Kite requests made) this run: {cache_count() - before}")
    out.to_csv(out_path, index=False)
    amb15 = out[out["exit_r15"] == "AMBIGUOUS"]
    print(f"\n15minute-AMBIGUOUS trades re-run at 1minute: {len(amb15)} of {len(out)}")
    for t in amb15.itertuples():
        r1 = ("NO_MINUTE_DATA" if t.exit_no_minute_data else
              f"{t.exit_outcome}" + (f" ({t.exit_reason})" if t.exit_outcome == "AMBIGUOUS" else ""))
        print(f"  {t.ticker} {t.entry_time:%Y-%m-%d %H:%M} 15m=AMBIGUOUS 1m={r1} | {t.exit_detail}")
    report(out, combo, f"{title}: FINAL (15minute, 1minute drill-down for AMBIGUOUS)")
    print(f"saved {out_path}")
    return out
