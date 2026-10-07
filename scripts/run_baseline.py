"""Phase 1: run the unmodified legacy build_trades_for_ticker (WIT, MIT) on the frozen Yahoo snapshot only.

Reads data/cache/yahoo via legacy offline_loader. Keeps entries >= 2025-01-01. Saves results/<git short hash>/trades_{combo}_heuristic.csv.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
sys.path.insert(0, str(LEGACY / "code"))
import offline_loader  # noqa: E402  (legacy, unmodified)

FROZEN = ROOT / "data" / "cache" / "yahoo"
START = pd.Timestamp("2025-01-01")
SPLIT = pd.Timestamp("2026-01-01")
COMBOS = [a.split("=")[1] for a in sys.argv if a.startswith("--combos=")][0].split(",") if any(a.startswith("--combos=") for a in sys.argv) else ["wit", "mit"]


def git_hash():
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()


def summarize(df, label):
    d = df[df["outcome"].isin(["win", "loss"])]
    n, w = len(d), int((d["outcome"] == "win").sum())
    r = np.where(d["outcome"] == "win", 2.0, -1.0)
    return (f"{label}: n={len(df)} resolved={n} wins={w} losses={n - w} win%={100 * w / n if n else float('nan'):.1f} "
            f"avgR={r.mean() if n else float('nan'):+.3f} totalRs={d['pnl'].sum():+,.0f}")


def main():
    offline_loader.install(data_dir=str(FROZEN))
    import mtf_backtest as bt  # noqa: E402

    tickers = json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"]
    out = ROOT / "results" / git_hash()
    out.mkdir(parents=True, exist_ok=True)
    print(f"run hash {out.name}; universe size {len(tickers)}")
    for combo, needs in (("wit", ["1d", "60m"]), ("mit", ["1d"])):
        if combo not in COMBOS:
            continue
        print(f"{combo} starting", flush=True)
        have = [t for t in tickers if all((FROZEN / f"{t}__{iv}.csv").exists() for iv in needs)]
        trades, errors = [], []
        for n_done, t in enumerate(have, 1):
            if n_done % 50 == 0:
                print(f"  {combo} {n_done}/{len(have)} tickers, {len(trades)} raw signals", flush=True)
            try:
                trades += bt.build_trades_for_ticker(t, combo)
            except Exception as e:  # report, do not hide
                errors.append((t, repr(e)[:80]))
        df = pd.DataFrame(trades)
        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df = df[df["entry_time"] >= START].sort_values(["entry_time", "ticker"]).reset_index(drop=True)
        df["split"] = np.where(df["entry_time"] < SPLIT, "train", "holdout")
        df.to_csv(out / f"trades_{combo}_heuristic.csv", index=False)
        print(f"\n{combo.upper()}: universe {len(tickers)}, tickers with frozen data {len(have)}, errors {len(errors)} {errors[:3]}")
        print(summarize(df, f"{combo.upper()} all   "))
        print(summarize(df[df.split == 'train'], f"{combo.upper()} train "))
        print(summarize(df[df.split == 'holdout'], f"{combo.upper()} hold  "))
        print(f"{combo.upper()} trades with no resolved outcome: {int((~df['outcome'].isin(['win','loss'])).sum())}")
        leg = pd.read_csv(LEGACY / "results" / f"mtf_trade_diagnostics_{combo}_FIXEDEXIT.csv")
        leg["entry_time"] = pd.to_datetime(leg["entry_time"])
        key = lambda x: set(zip(x["ticker"], x["entry_time"]))  # noqa: E731
        new_k, leg_all, leg_25 = key(df), key(leg), key(leg[leg["entry_time"] >= START])
        print(f"{combo.upper()} vs legacy FIXEDEXIT (entries >= 2025-01-01: legacy {len(leg_25)}, now {len(new_k)}): "
              f"in both {len(new_k & leg_25)}, new {len(new_k - leg_25)}, missing {len(leg_25 - new_k)}")
        print(f"{combo.upper()} (legacy file total {len(leg_all)} incl. before 2025: in both with all legacy {len(new_k & leg_all)})")
        for lab, ks in (("new", sorted(new_k - leg_25)), ("missing", sorted(leg_25 - new_k))):
            print(f"{combo.upper()} {lab}: " + "; ".join(f"{t} {e:%Y-%m-%d %H:%M}" for t, e in ks))


if __name__ == "__main__":
    main()
