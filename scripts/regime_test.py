"""Does the broad market (NIFTY 50) explain winners/losers? Read-only Kite: instruments() + historical_data() (3 day-bar requests, cached)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from kite_client import KiteReadOnly  # noqa: E402

k = KiteReadOnly(); inst = k.instruments("NSE")
row = inst[(inst.tradingsymbol == "NIFTY 50")]
print("index rows found:", len(row), row[["tradingsymbol", "segment", "instrument_type"]].head(2).to_dict("records"))
tok = int(row.instrument_token.iloc[0])
nf = k.historical_data(tok, datetime(2012, 1, 1), datetime(2026, 10, 3), "day", symbol="NIFTY50")
nf["timestamp"] = pd.to_datetime(nf["timestamp"]); nf = nf.set_index("timestamp")["close"]
print(f"NIFTY bars {len(nf)} from {nf.index.min():%Y-%m-%d} to {nf.index.max():%Y-%m-%d}")
dma200 = nf.rolling(200).mean(); dma50 = nf.rolling(50).mean(); ret63 = nf.pct_change(63); ret21 = nf.pct_change(21)
hi252 = nf.rolling(252).max(); dd = nf / hi252 - 1
reg = pd.DataFrame({"above200": nf > dma200, "above50": nf > dma50, "ret63": ret63, "ret21": ret21, "dd": dd})

rng = np.random.default_rng(11)
FILES = {"dit15": "results/9739e07/trades_dit15_kite_2024_v2_cap5_final.csv", "wit": "results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv", "mit": "results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv"}
fr = []
for c, p in FILES.items():
    d = pd.read_csv(p, parse_dates=["entry_time"]).drop_duplicates(["ticker", "entry_time"]); real = d.exit_outcome.isin(["win", "loss"])
    d["win"] = (np.where(real, d.exit_outcome, d.heuristic_outcome) == "win").astype(int); d["R"] = np.where(real, d.exit_r, d.heuristic_r); d["combo"] = c; fr.append(d)
D = pd.concat(fr, ignore_index=True)
day = D.entry_time.dt.normalize()
idx = reg.index.searchsorted(day, side="left") - 1           # Phase A (A5): last index bar strictly BEFORE the entry day; entries are intraday, the entry day's close is not known yet (was side="right": used day D's close)
idx = np.clip(idx, 0, len(reg) - 1)
for col in reg.columns: D[col] = reg[col].to_numpy()[idx]
D = D.dropna(subset=["above200", "ret63"])
D["demand"] = D.type == "demand"
print(f"\ntrades with a market reading: {len(D)} of 317")

def table(title, mask_a, la, lb):
    a, b = D[mask_a], D[~mask_a]
    obs = a.win.mean() - b.win.mean(); cnt = 0
    for _ in range(3000):
        sh = D.groupby("combo").win.transform(lambda s: rng.permutation(s.values)); cnt += abs(sh[mask_a].mean() - sh[~mask_a].mean()) >= abs(obs)
    per = "; ".join(f"{c} {100 * a[a.combo == c].win.mean():.0f}%/{100 * b[b.combo == c].win.mean():.0f}%" for c in FILES if (a.combo == c).sum() >= 5 and (b.combo == c).sum() >= 5)
    print(f"{title}\n   {la}: n={len(a)} win {100 * a.win.mean():.1f}% avgR {a.R.mean():+.3f} | {lb}: n={len(b)} win {100 * b.win.mean():.1f}% avgR {b.R.mean():+.3f} | diff {100 * obs:+.1f} pts, perm p {(cnt + 1) / 3001:.4f} | per combo ({la}/{lb}): {per}")

table("NIFTY above its 200-day average on the entry day", D.above200, "above", "below")
table("NIFTY above its 50-day average", D.above50, "above", "below")
table("NIFTY 3-month return positive", D.ret63 > 0, "up", "down")
table("NIFTY within 5% of its 52-week high", D.dd > -0.05, "near high", "5%+ below high")
dem = D[D.demand]; sup = D[~D.demand]
print("\nDEMAND trades only:"); 
for lab, m in (("NIFTY above 200-day", dem.above200), ("NIFTY 3-month up", dem.ret63 > 0)):
    a, b = dem[m], dem[~m]; print(f"   {lab}: yes n={len(a)} win {100 * a.win.mean():.1f}% | no n={len(b)} win {100 * b.win.mean():.1f}%")
print("SUPPLY trades only:")
for lab, m in (("NIFTY above 200-day", sup.above200), ("NIFTY 3-month up", sup.ret63 > 0)):
    a, b = sup[m], sup[~m]; print(f"   {lab}: yes n={len(a)} win {100 * a.win.mean():.1f}% | no n={len(b)} win {100 * b.win.mean():.1f}%")
print("\nBy year: share of trades entered with NIFTY below its 200-day average, and win rate in each state")
for y, g in D.groupby(D.entry_time.dt.year):
    print(f"   {y}: n={len(g)}, below 200-day {100 * (~g.above200).mean():.0f}% of trades; win above {100 * g[g.above200].win.mean():.0f}% (n={int(g.above200.sum())}) below {100 * g[~g.above200].win.mean() if (~g.above200).sum() else float('nan'):.0f}% (n={int((~g.above200).sum())})")
