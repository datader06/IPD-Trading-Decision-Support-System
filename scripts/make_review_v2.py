"""Review files for the cap-5 (V2) lists. Usage: python scripts/make_review_v2.py [wit mit dit15] [--workers=N]. No Kite calls, no network.

Writes results/<HEAD hash>/review/: review_{wit,mit}_cap5.csv and review_{wit,mit}_removed.csv
(removed = in Baseline v1 but gone under cap 5; their base counts are measured with the V2 definition by add_base_counts).
"""
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import add_base_counts as abc  # noqa: E402

CAP5 = {c: ROOT / f"results/c0b74c8/trades_{c}_kite_2024_newbase_cap5_final.csv" for c in ("wit", "mit")}
CAP5["dit15"] = ROOT / "results/9739e07/trades_dit15_kite_2024_v2_cap5_final.csv"
CAP8 = {c: ROOT / f"results/e7842da/trades_{c}_kite_2024_newbase_final.csv" for c in ("wit", "mit", "dit15")}  # carry the base counts
V1 = {c: ROOT / f"results/53aecde/baseline_v1_{c}.csv" for c in ("wit", "mit", "dit15")}
WORKERS = 5
SRC = {"15minute": "15m", "1minute": "1m"}
COLS = ["ticker", "type", "htf_formed_at", "htf_proximal", "htf_distal", "ltf_formed_at", "ltf_proximal", "stop", "target",
        "entry_time", "exit_time", "outcome_final", "outcome_source", "ltf_base_count", "htf_base_count", "in_baseline_v1", "my_verdict"]


def git_hash():
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()


def counts_for(combo, df):
    jobs = [(combo, t, [(i, r.type, pd.Timestamp(r.htf_formed_at), pd.Timestamp(r.ltf_formed_at)) for i, r in g.iterrows()])
            for t, g in df.groupby("ticker")]
    res = {}
    with mp.Pool(WORKERS, initializer=abc._init) as pool:
        for part in pool.imap_unordered(abc._work, jobs, chunksize=1):
            for idx, lc, hc in part:
                res[idx] = (lc, hc)
    return [res[i][0] for i in df.index], [res[i][1] for i in df.index]


def build_cap5(combo):
    d = pd.read_csv(CAP5[combo], parse_dates=["entry_time", "htf_formed_at", "ltf_formed_at", "exit_time", "exit_time_new"])
    real = d.exit_outcome.isin(["win", "loss"])
    d["outcome_final"] = np.where(real, d.exit_outcome, d.heuristic_outcome)
    d["outcome_source"] = np.where(real, d.exit_interval.map(SRC), "heuristic")
    d["exit_time"] = np.where(real & d.exit_time_new.notna(), d.exit_time_new, d.exit_time)
    # a duplicate trade (same ticker + entry) is the same zone matched through two adjacent legouts: keep the earliest HTF zone
    d = d.sort_values(["entry_time", "ticker", "htf_formed_at"]).drop_duplicates(["ticker", "entry_time"], keep="first")
    c8 = pd.read_csv(CAP8[combo], parse_dates=["entry_time", "htf_formed_at"])[["ticker", "entry_time", "htf_formed_at", "ltf_base_count", "htf_base_count"]]
    d = d.merge(c8, on=["ticker", "entry_time", "htf_formed_at"], how="left")
    assert d["ltf_base_count"].notna().all(), f"{combo}: base counts missing for {int(d['ltf_base_count'].isna().sum())} trades"
    v1 = pd.read_csv(V1[combo], parse_dates=["entry_time"])
    k1 = set(zip(v1.ticker, v1.entry_time))
    d["in_baseline_v1"] = ["yes" if k in k1 else "no" for k in zip(d.ticker, d.entry_time)]
    d["ltf_proximal"] = d["entry_price"]
    d["my_verdict"] = ""
    return d.sort_values("entry_time").reset_index(drop=True)


def build_removed(combo, kept):
    v1 = pd.read_csv(V1[combo], parse_dates=["entry_time", "htf_formed_at", "ltf_formed_at", "exit_time", "exit_time_new"])
    keep = set(zip(kept.ticker, kept.entry_time))
    r = v1[[k not in keep for k in zip(v1.ticker, v1.entry_time)]].copy().reset_index(drop=True)
    r["exit_time"] = np.where(r.outcome_source.isin(["15m", "1m"]) & r.exit_time_new.notna(), r.exit_time_new, r.exit_time)
    r["ltf_base_count"], r["htf_base_count"] = counts_for(combo, r)
    r["in_baseline_v1"] = "yes"
    r["ltf_proximal"] = r["entry_price"]
    r["my_verdict"] = ""
    return r.sort_values("entry_time").reset_index(drop=True)


def main():
    global WORKERS
    arg = [a.split("=")[1] for a in sys.argv if a.startswith("--workers=")]
    WORKERS = int(arg[0]) if arg else WORKERS
    combos = [a for a in sys.argv[1:] if not a.startswith("--")] or ["wit", "mit"]
    out = ROOT / "results" / git_hash() / "review"
    out.mkdir(parents=True, exist_ok=True)
    for combo in combos:
        d = build_cap5(combo)
        d[COLS].to_csv(out / f"review_{combo}_cap5.csv", index=False)
        w = int((d.outcome_final == "win").sum())
        print(f"review_{combo}_cap5.csv: {len(d)} rows, {w} wins, {len(d) - w} losses; in_baseline_v1 yes {int((d.in_baseline_v1 == 'yes').sum())} / no {int((d.in_baseline_v1 == 'no').sum())}; "
              f"ltf_base_count max {int(d.ltf_base_count.max())}, htf max {int(d.htf_base_count.max())}")
        r = build_removed(combo, d)
        r[COLS].to_csv(out / f"review_{combo}_removed.csv", index=False)
        rw = int((r.outcome_final == "win").sum())
        print(f"review_{combo}_removed.csv: {len(r)} rows, {rw} wins, {len(r) - rw} losses; ltf_base_count>5: {int((r.ltf_base_count > 5).sum())}, "
              f"ltf <=5: {int((r.ltf_base_count <= 5).sum())}, unmatched: {int(r.ltf_base_count.isna().sum())}")
        v1n = len(pd.read_csv(V1[combo]))
        print(f"  check {combo}: kept-in-both {int((d.in_baseline_v1 == 'yes').sum())} + removed {len(r)} = {int((d.in_baseline_v1 == 'yes').sum()) + len(r)} (Baseline v1 has {v1n})")
    print(f"folder: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
