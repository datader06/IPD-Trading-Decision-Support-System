"""Winner/loser patterns across the cap-5 lists (DIT15 + WIT + MIT). No network. Univariate splits within each combo, permutation p-values (outcomes shuffled within combo)."""
import sys
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
rng = np.random.default_rng(7)
FILES = {"dit15": "results/9739e07/trades_dit15_kite_2024_v2_cap5_final.csv",
         "wit": "results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv",
         "mit": "results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv"}
CNT = {c: f"results/e7842da/trades_{c}_kite_2024_newbase_final.csv" for c in FILES}
frames = []
for c, p in FILES.items():
    d = pd.read_csv(p, parse_dates=["entry_time", "htf_formed_at"]).drop_duplicates(["ticker", "entry_time"])
    real = d.exit_outcome.isin(["win", "loss"])
    d["win"] = (np.where(real, d.exit_outcome, d.heuristic_outcome) == "win").astype(int)
    d["R"] = np.where(real, d.exit_r, d.heuristic_r)
    d["combo"] = c
    cn = pd.read_csv(CNT[c], parse_dates=["entry_time", "htf_formed_at"])[["ticker", "entry_time", "htf_formed_at", "ltf_base_count", "htf_base_count"]].drop_duplicates(["ticker", "entry_time", "htf_formed_at"])
    d = d.merge(cn, on=["ticker", "entry_time", "htf_formed_at"], how="left")
    d["hour"] = d.entry_time.dt.hour
    d["demand"] = (d.type == "demand").astype(int)
    d["year"] = d.entry_time.dt.year
    for b in ("htf_strong_legout", "ltf_strong_legout"):
        d[b] = d[b].astype(str).str.lower().eq("true").astype(int)
    d["gap"] = d.gap_fill.astype(str).str.lower().eq("true").astype(int)
    frames.append(d)
D = pd.concat(frames, ignore_index=True)
print(f"pooled {len(D)} trades: " + ", ".join(f"{c} {int((D.combo == c).sum())}" for c in FILES) + f"; overall win rate {100 * D.win.mean():.1f}%; per combo " + ", ".join(f"{c} {100 * D[D.combo == c].win.mean():.1f}%" for c in FILES))

def split_feature(name, col, how):
    """Returns Series 'hi' (1) / 'lo' (0) / NaN, split WITHIN each combo (median) or by a boolean."""
    out = pd.Series(np.nan, index=D.index)
    for c in FILES:
        m = D.combo == c; x = D.loc[m, col]
        if how == "bool": out[m] = x
        elif how == "median": out[m] = np.where(x.isna(), np.nan, (x > x.median()).astype(float))
        elif how == "le3": out[m] = np.where(x.isna(), np.nan, (x <= 3).astype(float))
        elif how == "morning": out[m] = np.where(x.isna(), np.nan, (x <= 10).astype(float))
    return out

tests = [("demand (vs supply)", "demand", "bool"), ("LTF stop % of price above median", "ltf_risk_pct", "median"), ("HTF zone height % above median", "htf_risk_pct", "median"),
         ("LTF/HTF overlap above median", "overlap_frac", "median"), ("trend strength above median", "trend_strength_atr", "median"),
         ("HTF strong legout", "htf_strong_legout", "bool"), ("LTF strong legout", "ltf_strong_legout", "bool"),
         ("gap fill", "gap", "bool"), ("LTF base count <= 3 (2024+ only)", "ltf_base_count", "le3"), ("HTF base count <= 3 (2024+ only)", "htf_base_count", "le3"),
         ("entry at/before 10:xx (intraday combos)", "hour", "morning"), ("risk (Rs per share) above median", "risk", "median")]
rows = []
for name, col, how in tests:
    g = split_feature(name, col, how); ok = g.notna()
    if col == "hour": ok &= D.combo.isin(["dit15", "wit"])
    if ok.sum() < 40: continue
    dd = D[ok].copy(); dd["g"] = g[ok]
    n1, n0 = int((dd.g == 1).sum()), int((dd.g == 0).sum())
    if min(n1, n0) < 10: continue
    w1, w0 = dd[dd.g == 1].win.mean(), dd[dd.g == 0].win.mean()
    obs = w1 - w0
    cnt = 0
    for _ in range(3000):
        sh = dd.groupby("combo").win.transform(lambda s: rng.permutation(s.values))
        cnt += abs(sh[dd.g == 1].mean() - sh[dd.g == 0].mean()) >= abs(obs)
    p = (cnt + 1) / 3001
    per = []
    for c in FILES:
        s = dd[dd.combo == c]
        if (s.g == 1).sum() >= 5 and (s.g == 0).sum() >= 5: per.append(np.sign((s[s.g == 1].win.mean() - s[s.g == 0].win.mean())))
    cons = f"{int((np.array(per) == np.sign(obs)).sum())}/{len(per)} combos same direction"
    r1 = dd[dd.g == 1].R.mean(); r0 = dd[dd.g == 0].R.mean()
    rows.append((name, n1, n0, 100 * w1, 100 * w0, 100 * obs, r1, r0, p, cons))
res = pd.DataFrame(rows, columns=["feature", "n_yes", "n_no", "win%_yes", "win%_no", "diff_pts", "avgR_yes", "avgR_no", "perm_p", "consistency"]).sort_values("perm_p")
pd.set_option("display.width", 250)
print(f"\n{len(res)} features tested (Bonferroni threshold for 5% overall: p < {0.05 / len(res):.4f})")
print(res.round(3).to_string(index=False))
print("\nWin rate by entry year (pooled, with per-combo n):")
print(D.groupby("year").win.agg(["count", "mean"]).assign(mean=lambda x: (100 * x["mean"]).round(1)).T.to_string())
print("\nWin rate by LTF base count (2024+ trades with counts):")
x = D.dropna(subset=["ltf_base_count"]); print(x.groupby("ltf_base_count").win.agg(["count", "mean"]).assign(mean=lambda t: (100 * t["mean"]).round(1)).T.to_string())
print("\nWin rate by HTF base count:"); print(x.groupby("htf_base_count").win.agg(["count", "mean"]).assign(mean=lambda t: (100 * t["mean"]).round(1)).T.to_string())
print("\nLTF stop % of price: quartiles within combo -> win rate"); 
D["q"] = D.groupby("combo").ltf_risk_pct.transform(lambda s: pd.qcut(s, 4, labels=False, duplicates="drop"))
print(D.groupby("q").win.agg(["count", "mean"]).assign(mean=lambda t: (100 * t["mean"]).round(1)).T.to_string())
print("\nBy combo and type:"); print(D.groupby(["combo", "type"]).win.agg(["count", "mean"]).assign(mean=lambda t: (100 * t["mean"]).round(1)).to_string())

print("\n=== 2025 effect and date clustering ===")
D["is2025"] = (D.year == 2025).astype(int)
obs = D[D.is2025 == 1].win.mean() - D[D.is2025 == 0].win.mean(); cnt = 0
for _ in range(3000):
    sh = D.groupby("combo").win.transform(lambda s: rng.permutation(s.values)); cnt += abs(sh[D.is2025 == 1].mean() - sh[D.is2025 == 0].mean()) >= abs(obs)
print(f"2025 vs all other years (shuffled within combo): {100 * D[D.is2025 == 1].win.mean():.1f}% (n={int((D.is2025 == 1).sum())}) vs {100 * D[D.is2025 == 0].win.mean():.1f}% (n={int((D.is2025 == 0).sum())}), diff {100 * obs:+.1f} pts, permutation p = {(cnt + 1) / 3001:.4f}")
print("by combo, 2025 vs rest: " + "; ".join(f"{c} {100 * D[(D.combo == c) & (D.year == 2025)].win.mean():.0f}% vs {100 * D[(D.combo == c) & (D.year != 2025)].win.mean():.0f}%" for c in FILES))
D["ym"] = D.entry_time.dt.to_period("M").astype(str)
m = D.groupby("ym").win.agg(["count", "sum"]).assign(rate=lambda t: (100 * t["sum"] / t["count"]).round(0)); m = m[m["count"] >= 8]
print("months with >= 8 trades (n, wins, win%):"); print(m.to_string())
D["date"] = D.entry_time.dt.normalize()
g = D.groupby("date").win.agg(["count", "mean"]); big = g[g["count"] >= 4]
print(f"\ndates with 4+ trades entering on the same day: {len(big)}; trades on those dates {int(big['count'].sum())}, win rate {100 * (big['count'] * big['mean']).sum() / big['count'].sum():.1f}% vs {100 * D[~D.date.isin(big.index)].win.mean():.1f}% on other days")
print(big.assign(mean=lambda t: (100 * t["mean"]).round(0)).sort_values("count", ascending=False).head(10).to_string())
