"""Build the demo scanner feed (DIT15 / WIT / MIT setup status per ticker) from the cached frames. Offline, deterministic.

  python scripts/run_scanner_feed.py [--tickers=A.NS,B.NS | --sample=N] [--strategies=DIT15,WIT,MIT] [--workers=K] [--out=DIR]

Writes results/scanner_demo/scanner_feed_asof_<date>.csv and scanner_feed_meta.json (default folder). DEMO output on cached data:
not a backtest result and not one of the frozen Phase A baselines. No data are fetched.
"""
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from scanner import feed as F  # noqa: E402

FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
DEF_OUT = ROOT / "results" / "scanner_demo"


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def universe():
    return sorted(p.name.split("__")[0] for p in FRAMES.glob("*__1d.csv"))


def main():
    tickers = arg("tickers").split(",") if arg("tickers") else universe()
    if arg("sample"):
        step = max(1, len(tickers) // int(arg("sample")))
        tickers = tickers[::step][:int(arg("sample"))]
    strategies = tuple(arg("strategies", ",".join(F.STRATEGIES)).split(","))
    bad = [s for s in strategies if s not in F.STRATEGIES]
    if bad:
        print(f"unknown strategies {bad}")
        return 1
    workers = int(arg("workers", "1"))
    out = Path(arg("out", DEF_OUT))
    out = out if out.is_absolute() else ROOT / out
    t0 = time.time()
    jobs = [(t, strategies) for t in tickers]
    rows = []
    if workers > 1:
        with mp.Pool(workers) as pool:
            for i, r in enumerate(pool.imap(F.scan_ticker, jobs, chunksize=2), 1):
                rows.extend(r)
                if i % 25 == 0:
                    print(f"  {i}/{len(jobs)}", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            rows.extend(F.scan_ticker(j))
            if i % 5 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)
    df = F.to_frame(rows)
    as_of = sorted(set(df["as_of"].dropna()))
    errors = df[df["data_note"].fillna("").str.startswith(("error", "no cached", "insufficient"))]
    out.mkdir(parents=True, exist_ok=True)
    stamp = as_of[-1] if as_of else "unknown"
    path = out / f"scanner_feed_asof_{stamp}.csv"
    df.to_csv(path, index=False)
    meta = dict(label=f"As of {stamp}", as_of_dates=as_of, note=F.DATA_NOTE + "; cached Kite frames, nothing fetched; not a frozen Phase A baseline",
                tickers=len(tickers), strategies=list(strategies), rows=len(df),
                rows_by_strategy=df["strategy"].value_counts().to_dict(),
                status_by_strategy={s: g["status"].value_counts().to_dict() for s, g in df.groupby("strategy")},
                status_total=df["status"].value_counts().to_dict(), problems=len(errors),
                definitions=dict(approach_max_atr=F.APPROACH_MAX_ATR, approach_max_pct=F.APPROACH_MAX_PCT, confirmed_max_age_days=F.CONFIRMED_MAX_AGE_DAYS),
                seconds=round(time.time() - t0, 1), file=str(path.relative_to(ROOT)).replace("\\", "/"))
    (out / "scanner_feed_meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(json.dumps(meta, indent=1, default=str))
    if len(errors):
        print("\nproblem rows:\n", errors[["ticker", "strategy", "data_note"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
