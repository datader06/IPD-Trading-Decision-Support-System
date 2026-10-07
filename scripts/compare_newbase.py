"""Compare a *_newbase_final.csv run with its Baseline v1 list (baseline-v1 scoring: replay win/loss stands, ambiguous -> heuristic). No network.
Usage: python scripts/compare_newbase.py wit|mit|dit15 <newbase_final.csv> <baseline_v1_csv>"""
import sys
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
combo, new_p, old_p = sys.argv[1:4]
new = pd.read_csv(new_p, parse_dates=["entry_time"]); old = pd.read_csv(old_p, parse_dates=["entry_time"])
real = new.exit_outcome.isin(["win", "loss"])
new["outcome_final"] = np.where(real, new.exit_outcome, new.heuristic_outcome)
new["r_final"] = np.where(real, new.exit_r, new.heuristic_r)
new["pnl_final"] = np.where(real, new.exit_pnl, new.heuristic_pnl)
dups = int(new.duplicated(["ticker", "entry_time"]).sum())
new_u = new.drop_duplicates(["ticker", "entry_time"]).reset_index(drop=True)
rng = np.random.default_rng(12345)
def ci(w, n):
    x = rng.binomial(n, w / n, 5000) / n; return f"{100*np.percentile(x,2.5):.0f}-{100*np.percentile(x,97.5):.0f}"
def line(l, d):
    n = len(d); w = int((d.outcome_final == "win").sum())
    return f"  {l:12} n={n:3d} wins={w:3d} losses={n-w:3d} win%={100*w/n:5.1f} boot95=[{ci(w,n)}] avgR={d.r_final.mean():+.3f} totalRs={d.pnl_final.sum():+9,.0f}" + ("  SAMPLE<30" if n < 30 else "")
def slices(d):
    return [("ALL", d), ("2024", d[d.entry_time.dt.year == 2024]), ("2025", d[d.entry_time.dt.year == 2025]), ("2026", d[d.entry_time.dt.year == 2026]),
            ("TRAIN", d[d.entry_time < "2026-01-01"]), ("HOLDOUT", d[d.entry_time >= "2026-01-01"])]
print(f"=== {combo.upper()} NEW BASE (duplicates removed: {dups}; heuristic-scored {int((~real[~new.duplicated(['ticker','entry_time'])]).sum())} of {len(new_u)}) ===")
for l, s in slices(new_u): print(line(l, s))
print(f"=== {combo.upper()} BASELINE v1 (old base logic) ===")
for l, s in slices(old): print(line(l, s))
ko = set(zip(old.ticker, old.entry_time)); kn = set(zip(new_u.ticker, new_u.entry_time))
o = old.set_index(["ticker", "entry_time"]); n2 = new_u.set_index(["ticker", "entry_time"])
rem, add, both = sorted(ko - kn), sorted(kn - ko), sorted(ko & kn)
print(f"\nin both {len(both)} | removed (only old) {len(rem)} | added (only new) {len(add)}   check: {len(both)}+{len(rem)}={len(old)}, {len(both)}+{len(add)}={len(new_u)}")
print(f"removed: wins {sum(o.loc[k,'outcome_final']=='win' for k in rem)}, losses {sum(o.loc[k,'outcome_final']=='loss' for k in rem)} | added: wins {sum(n2.loc[k,'outcome_final']=='win' for k in add)}, losses {sum(n2.loc[k,'outcome_final']=='loss' for k in add)}")
ch = [(t, str(e.date()), o.loc[(t, e), 'outcome_final'], n2.loc[(t, e), 'outcome_final']) for t, e in both if o.loc[(t, e), 'outcome_final'] != n2.loc[(t, e), 'outcome_final']]
print("kept but outcome changed:", ch if ch else "none")
wn, nn, wo, no = (new_u.outcome_final == "win").sum(), len(new_u), (old.outcome_final == "win").sum(), len(old)
d = rng.binomial(nn, wn/nn, 5000)/nn - rng.binomial(no, wo/no, 5000)/no
print(f"win-rate difference new - old: {100*(wn/nn-wo/no):+.1f} pts, bootstrap 95% [{100*np.percentile(d,2.5):+.0f}, {100*np.percentile(d,97.5):+.0f}] pts")
print("removed:", "; ".join(f"{t.replace('.NS','')} {e:%Y-%m-%d} {o.loc[(t,e),'outcome_final']}" for t, e in rem))
print("added:  ", "; ".join(f"{t.replace('.NS','')} {e:%Y-%m-%d} {n2.loc[(t,e),'outcome_final']}" for t, e in add))
new_u.to_csv(new_p.replace("_final.csv", "_baseline_v1_style.csv"), index=False)
