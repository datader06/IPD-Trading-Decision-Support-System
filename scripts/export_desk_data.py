"""Bundle research + ML results into one JSON for the frontend-desk UI (read-only on results).

  python scripts/export_desk_data.py --out=../dz-desk/frontend/public/data/desk.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ML = ROOT / "results" / "ml_core"


def wilson(w, n, z=1.96):
    if n == 0:
        return [None, None]
    p, d = w / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h)), round(100 * (c + h))]


def stats(g, rs_col):
    n, w = len(g), int(g["win"].sum())
    return dict(n=n, wins=w, win_rate=round(100 * w / n, 1) if n else None, ci=wilson(w, n), avg_r=round(float(g["r"].mean()), 3) if n else None,
                pnl=round(float(g[rs_col].sum())) if n else 0)


def baselines():
    v5 = pd.read_csv(ROOT / "data" / "algo_v5" / "ml_dataset_baseline_v5.csv", parse_dates=["entry_time"])
    v5 = v5.rename(columns={"combo": "strategy", "label_win": "win", "label_R": "r", "label_rs": "rs"})
    v6 = v5[(v5.strategy != "DIT15") | (v5.legout_strength_score == 2)]
    out = {}
    for key, title, window, df in [("v6", "Final v6", "2021–2026 · rules chosen on these trades", v6), ("v6_train", "v6 train", "2021–2025", v6[v6.split == "train"]),
                                    ("v6_holdout", "v6 holdout", "2026 only", v6[v6.split == "holdout"]),
                                    ("v5", "v5", "2021–2026, before strength filter", v5)]:
        rows = [dict(combo=s, **stats(df[df.strategy == s], "rs")) for s in ("DIT15", "WIT", "MIT")]
        out[key] = dict(title=title, window=window, rows=rows, all=stats(df, "rs"))
    return out


def experiments():
    exps = []
    spec = [("Exp 3", "Win-rate filter, 4 models", "exp3_v5_f381ac0a", "v5, 172 test trades"),
            ("Exp 4", "Win-rate filter, 8 models", "exp4_zoo_f381ac0a", "v5, 172 test trades"),
            ("Exp 5", "Win-rate filter on final v6", "exp5_v6_f381ac0a", "v6, 117 test trades")]
    for name, what, run, data in spec:
        v = pd.read_csv(ML / run / "verdict.csv")
        b = v.loc[v.lift_pts.idxmax()]
        exps.append(dict(name=name, what=what, data=data, best=b.family, metric=f"{b.lift_pts:+.1f} pts win rate", auc=round(float(v.auc.max()), 3),
                         p=round(float(b.p_random), 3), passed=bool(v.win_rate_improvement_established.any())))
    for name, run, data in [("Exp 6", "exp6_pnl_f381ac0a", "v6, 117 test trades")]:
        v = pd.read_csv(ML / run / "verdict.csv")
        for arm, label, unit in [("A", "Expected-R filter", "R/trade"), ("B", "ML position sizing", "per unit risk")]:
            g = v[v.arm == arm]
            b = g.loc[g.effect.idxmax()]
            m = f"{b.effect:+.2f} {unit}" if arm == "A" else f"{100 * b.effect:+.0f}% {unit}"
            exps.append(dict(name=name, what=label, data=data, best=b.model, metric=m, auc=None, p=round(float(b.p_random), 3), passed=bool(g.improved.any())))
    return exps


def setups():
    f = pd.read_csv(ROOT / "results" / "scanner_demo_smoke" / "scanner_feed_asof_2026-10-01.csv")
    ins = json.loads((ML / "scanner_insights" / "insights.json").read_text(encoding="utf-8"))
    live = f[f.entry.notna()]
    rows = []
    for r in live.to_dict("records"):
        key = f"{r['ticker']}|{r['strategy']}|{r['zone_type']}|{r['entry']:.4f}"
        rows.append(dict(ticker=r["ticker"].replace(".NS", ""), strategy=r["strategy"], status=r["status"], type=r["zone_type"], entry=r["entry"], stop=r["stop"],
                         target=r["target"], price=r["current_price"], htf_proximal=r["htf_proximal"], htf_distal=r["htf_distal"], ltf_proximal=r["ltf_proximal"],
                         ltf_distal=r["ltf_distal"], htf_formed_at=str(r["htf_formed_at"]), ltf_formed_at=str(r["ltf_formed_at"]), dist_pct=r["distance_pct"], as_of=r["as_of"], insight=ins["setups"].get(key)))
    return rows, ins["meta"]


def main():
    out = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), "desk.json"))
    s, meta = setups()
    e5 = json.loads((ML / "exp5_v6_f381ac0a" / "summary.json").read_text(encoding="utf-8"))
    doc = dict(baselines=baselines(), experiments=experiments(), setups=s, ml_meta=meta,
               power=dict(test_trades=e5["n_oof"], base=round(100 * e5["base_win_rate"], 1), min_detectable=round(e5["power"]["min_detectable_lift_pts"], 1)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB): {len(s)} live setups, {len(doc['experiments'])} experiment rows")


if __name__ == "__main__":
    main()
