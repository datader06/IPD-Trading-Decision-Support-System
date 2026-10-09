"""ML decision-support for scanner setups (no trade filter, no edge claimed):
  1. similar past trades: 10 nearest v6 trades of the same strategy (standardised feature space), with outcomes;
  2. setup explanation: per-feature percentile vs that strategy's history + logistic-regression contributions (coef x z);
  3. unusual-setup flag: distance to the 5th neighbour vs the leave-one-out distribution of history (> 95th percentile = unusual).

History = the 205 baseline-v6 trades 2021-2026 (data/algo_v5 export with the DIT15 strength-2 rule).
Features use only data known at the decision date (daily bars before it). Output: results/ml_core/scanner_insights/insights.json

  python scripts/build_scanner_insights.py [--feed=results/scanner_demo_smoke/scanner_feed_asof_2026-10-01.csv]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import features as F  # noqa: E402
from ml_core import adapters as A  # noqa: E402
from ml_core import dataset as D  # noqa: E402

FEATS = ["risk_pct", "htf_width_pct", "entry_to_htf_pct", "risk_atr_d", "stock_rs63", "nifty_above_200dma", "log_htf_age_days", "type_demand"]
LABEL = {"risk_pct": "Stop distance (% of price)", "htf_width_pct": "HTF zone width (% of price)", "entry_to_htf_pct": "Entry depth inside HTF zone (%)",
         "risk_atr_d": "Stop distance in daily ATRs", "stock_rs63": "Stock vs NIFTY, last 63 days", "nifty_above_200dma": "NIFTY above 200-day average",
         "log_htf_age_days": "Age of HTF zone (log days)", "type_demand": "Demand zone (1) / supply (0)"}
K, K_ANOM = 10, 5


def feats(entry, risk, prox, dist, typ, formed, when, td):
    day, why = A._daily_features({"entry_time": when, "risk": risk}, td) if td else (None, "no_frames")
    if why:
        return None
    return dict(risk_pct=100 * risk / entry, htf_width_pct=100 * abs(prox - dist) / entry, entry_to_htf_pct=100 * abs(entry - prox) / entry,
                risk_atr_d=day[0], stock_rs63=day[1], nifty_above_200dma=day[2], type_demand=float(typ == "demand"),
                log_htf_age_days=math.log1p(max((pd.Timestamp(when) - pd.Timestamp(formed)) / pd.Timedelta(days=1), 0.0)))


def history(nifty, tds):
    """Baseline v6 trades 2021-2026: the final export with the DIT15 strength-2 rule applied (STATUS section 19)."""
    h = pd.read_csv(A.DEFAULT_PATH, parse_dates=["entry_time", "after_entry_exit_time"])
    h = h[(h["combo"] != "DIT15") | (h["legout_strength_score"] == 2)]
    rows = []
    for r in h.to_dict("records"):
        tk = r["ticker"]
        if tk not in tds:
            tds[tk] = D._td(tk, nifty)
        f = feats(r["entry_price"], r["risk"], r["htf_proximal"], r["htf_distal"], r["type"], r["htf_formed_at"], r["entry_time"], tds[tk])
        if f:
            rows.append(dict(strategy=r["combo"], ticker=tk, type=r["type"], entry_time=str(r["entry_time"])[:16], win=int(r["label_win"]),
                             exit_time=r["after_entry_exit_time"], r=round(float(r["label_R"]), 3), era=r["split"], **f))
    return pd.DataFrame(rows)


def main():
    feed_path = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--feed=")),
                          ROOT / "results" / "scanner_demo_smoke" / "scanner_feed_asof_2026-10-01.csv"))
    nifty, tds = F.load_nifty(), {}
    H = history(nifty, tds)
    feed = pd.read_csv(feed_path)
    asof = pd.to_datetime(feed["as_of"]).min()
    H = H[pd.to_datetime(H["exit_time"]) < asof].reset_index(drop=True)  # only trades already closed on the scanner date
    from sklearn.linear_model import LogisticRegression
    out, stats = {}, {}
    for s, g in H.groupby("strategy"):
        X = g[FEATS].to_numpy(float)
        mu, sd = X.mean(0), X.std(0)
        sd[sd == 0] = 1.0
        Z = (X - mu) / sd
        lr = LogisticRegression(C=0.3, max_iter=2000).fit(Z, g["win"].to_numpy())
        dmat = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(dmat, np.inf)
        loo = np.sort(dmat, 1)[:, K_ANOM - 1]
        stats[s] = dict(n=len(g), win_rate=float(g["win"].mean()), avg_r=float(g["r"].mean()), unusual_cut=float(np.percentile(loo, 95)))
        for r in feed[feed["strategy"] == s].to_dict("records"):
            tk = r["ticker"]
            if tk not in tds:
                tds[tk] = D._td(tk, nifty)
            key = f"{tk}|{s}|{r['zone_type']}|{r['entry']:.4f}" if pd.notna(r["entry"]) else f"{tk}|{s}"
            if pd.isna(r["as_of"]) or pd.isna(r["entry"]) or pd.isna(r["risk"]):
                out[key] = dict(available=False, reason="no live setup on this ticker")
                continue
            when = pd.Timestamp(r["as_of"]) + pd.Timedelta(days=1)
            f = feats(r["entry"], r["risk"], r["htf_proximal"], r["htf_distal"], r["zone_type"], r["htf_formed_at"], when, tds[tk])
            if not f:
                out[key] = dict(available=False, reason="not enough daily history for the features")
                continue
            x = np.array([f[c] for c in FEATS], float)
            z = (x - mu) / sd
            d = np.sqrt(((Z - z) ** 2).sum(1))
            nn = np.argsort(d)[:K]
            sim = g.iloc[nn]
            k5 = float(np.sort(d)[K_ANOM - 1])
            contrib = lr.coef_[0] * z
            out[key] = dict(
                available=True,
                similar=[dict(ticker=a.ticker, entry_time=a.entry_time, type=a.type, win=a.win, r=a.r, era=a.era, distance=round(float(b), 2))
                         for a, b in zip(sim.itertuples(), d[nn])],
                similar_win_rate=float(sim["win"].mean()), similar_avg_r=float(sim["r"].mean()),
                unusual=bool(k5 > stats[s]["unusual_cut"]), novelty_pct=float((loo < k5).mean() * 100),
                features=[dict(name=c, label=LABEL[c], value=round(float(f[c]), 3), pct=round(float((g[c] < f[c]).mean() * 100), 0),
                               contribution=round(float(cb), 3)) for c, cb in zip(FEATS, contrib)])
    o = ROOT / "results" / "ml_core" / "scanner_insights"
    o.mkdir(parents=True, exist_ok=True)
    meta = dict(feed=feed_path.name, history_rows=len(H), history_by_strategy=stats, k=K, k_anomaly=K_ANOM, features=FEATS,
                note="Decision support only. Walk-forward tests (Experiments 3-6) found no reliable win-rate or P&L edge from ML; contributions describe the model, they do not predict outcomes.")
    (o / "insights.json").write_text(json.dumps(dict(meta=meta, setups=out), indent=0), encoding="utf-8")
    ok = sum(v["available"] for v in out.values())
    print(f"history {len(H)} trades {H.strategy.value_counts().to_dict()}; setups {len(out)} ({ok} with insights, {sum(v.get('unusual', False) for v in out.values())} unusual) -> {o}")


if __name__ == "__main__":
    main()
