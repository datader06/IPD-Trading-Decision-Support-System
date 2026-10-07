"""Measure the HTF (daily) legout strength of existing DIT15 trades so the strict-HTF thresholds can be set to remove a target share of trades. No network."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "legacy/handoff/handoff/code")); sys.path.insert(0, str(ROOT / "src"))
import offline_loader; offline_loader.install(data_dir=str(ROOT / "data/cache/kite_frames"))
import mtf_zones as mtz, sd_zones as sz, base_candles as bc
bc.install(sz, mtz)

d = pd.read_csv(ROOT / "results/9739e07/trades_dit15_kite_2024_v2_cap5_final.csv", parse_dates=["entry_time", "htf_formed_at"])
real = d.exit_outcome.isin(["win", "loss"]); d["win"] = (np.where(real, d.exit_outcome, d.heuristic_outcome) == "win").astype(int)
cfg = bc.new_base_config(mtz.COMBOS["dit"].htf_config, "htf") if False else bc.new_base_config(mtz.WEEKLY_CONFIG, "htf")
rows = []
for t, g in d.groupby("ticker"):
    df = mtz._build_frame(t, "daily", "1d", "max", None, 750); atr = sz.wilder_atr(df)
    zs = sz.detect_zones(df, config=cfg, allow_wick_to_wick=False)
    for r in g.itertuples():
        z = [z for z in zs if z.type == r.type and df.iloc[z.leg_end_index]["timestamp"] == r.htf_formed_at]
        if not z: continue
        z = z[0]; ls, le = z.leg_start_index, z.leg_end_index
        body = max(abs(df.iloc[k]["close"] - df.iloc[k]["open"]) / atr.iloc[k] for k in range(ls, le + 1))
        e = df.iloc[le]; rng = e.high - e.low
        cp = (e.close - e.low) / rng if r.type == "demand" else (e.high - e.close) / rng
        ratio = sz._base_range(df, z.base_start_index, z.base_end_index) / sz._leg_range(df, ls, le, r.type)
        rows.append(dict(ticker=t, entry=r.entry_time, win=r.win, body=body, closepos=cp, ratio=ratio))
x = pd.DataFrame(rows)
print(f"{len(x)} of {len(d)} trades matched to their HTF zone; win rate {100 * x.win.mean():.1f}%")
for col in ("body", "closepos", "ratio"):
    print(f"{col}: percentiles 10/20/30/50/70/90 =", np.round(np.percentile(x[col], [10, 20, 30, 50, 70, 90]), 2))
def cut(b, c, r):
    keep = (x.body >= b) & (x.closepos >= c) & (x.ratio <= r)
    return 100 * (1 - keep.mean()), 100 * x[keep].win.mean(), int(keep.sum())
print("\nprofile (body >= , close pos >= , base/legout <=): % of trades removed | win rate of the remaining | n kept")
for prof in ((1.3, 0.75, 1.25), (1.5, 0.75, 1.25), (1.5, 0.80, 1.0), (1.6, 0.80, 1.0), (1.6, 0.85, 1.0), (1.7, 0.80, 0.9), (1.8, 0.85, 0.75), (2.0, 0.85, 0.75)):
    rem, wr, n = cut(*prof); print(f"  {prof}: removed {rem:4.1f}% | win {wr:4.1f}% | kept {n}")
x.to_csv(ROOT / "results/htf_legout_stats_dit15_2024.csv", index=False)
