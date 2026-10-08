"""Phase B step 1: Tier-1 feature extraction from a Phase A candidates file (no labels, models or validation).

  python scripts/run_phase_b_features.py [--src=results/nogit-145d6302/phase_a/pit_refetch/candidates.csv] [--out=DIR] [--workers=K]

Writes to <run folder>/phase_b/tier1/ (next to the source's run folder; no git call):
  features.csv     one row per unique candidate order: identifiers + outcome fields (meta, never model inputs) + the 18 model columns
  exclusions.csv   every excluded row with the exact reason and stage (pool | features)
  manifest.json    source file hash, source code_hash (from run_info.txt), registry version, row counts, column lists
  report.txt       row counts, exclusions, missing values, feature ranges
Offline only: reads frozen frames and the NIFTY daily file. Workers default to half the cores at below-normal priority.
"""
import hashlib
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ml import features as F  # noqa: E402
from ml import registry as R  # noqa: E402

DEFAULT_SRC = "results/nogit-145d6302/phase_a/pit_refetch/candidates.csv"
TIME_COLS = ["entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at", "fill_time", "exit_time"]


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def _low_priority():
    """Below-normal priority. The pseudo-handle must be a pointer type or SetPriorityClass fails on 64-bit Python."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


_NIFTY = None


def _init():
    global _NIFTY
    _low_priority()
    sys.dont_write_bytecode = True
    _NIFTY = F.load_nifty()


def _work(args):
    ticker, rows = args
    td = F.TickerData.from_ticker(ticker, _NIFTY)
    return F.build_ticker(ticker, rows, td)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    src = ROOT / arg("src", DEFAULT_SRC)
    out = Path(arg("out") or src.parent.parent.parent / "phase_b" / "tier1")
    out.mkdir(parents=True, exist_ok=True)
    info = {}
    ri = src.parent / "run_info.txt"
    if ri.exists():
        for line in ri.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()
    code_hash = info.get("code_hash")
    if code_hash != R.SOURCE_CODE_HASH:
        print(f"WARNING: source code_hash {code_hash!r} != expected {R.SOURCE_CODE_HASH!r}")
    df = pd.read_csv(src, parse_dates=TIME_COLS)
    pool, pool_log = F.select_pool(df)
    workers = int(arg("workers", max(1, mp.cpu_count() // 2)))
    groups = [(t, g) for t, g in pool.groupby("ticker", sort=True)]
    print(f"source {src.name} rows {len(df)}; pool {len(pool)} rows, {len(groups)} tickers; workers {workers}", flush=True)
    rows, ex = [], []
    with mp.Pool(workers, initializer=_init) as p:
        for i, (r, e) in enumerate(p.imap_unordered(_work, groups, chunksize=1), 1):
            rows += r
            ex += e
            if i % 100 == 0:
                print(f"  {i}/{len(groups)} tickers", flush=True)
    ds = pd.DataFrame(rows)
    ds = ds.sort_values(["entry_time", "ticker", "htf_formed_at", "type"], kind="mergesort").reset_index(drop=True)
    ds = ds[R.META_COLUMNS + R.MODEL_COLUMNS]
    R.assert_no_forbidden(R.MODEL_COLUMNS)
    excl = pd.concat([pool_log, pd.DataFrame(ex)], ignore_index=True)
    excl.to_csv(out / "exclusions.csv", index=False)
    ds.to_csv(out / "features.csv", index=False)

    X = ds[R.MODEL_COLUMNS]
    nan = int(X.isna().sum().sum())
    inf = int(np.isinf(X.to_numpy(dtype=float)).sum())
    dup = int(ds["row_id"].duplicated().sum())
    manifest = dict(
        registry_version=R.REGISTRY_VERSION, source_file=str(src.relative_to(ROOT)), source_sha256=sha256(src),
        source_code_hash=code_hash, source_run_info=info, rows_source=len(df), rows_pool=len(pool), rows_dataset=len(ds),
        exclusions=excl["reason"].value_counts().to_dict(), model_columns=R.MODEL_COLUMNS, meta_columns=R.META_COLUMNS,
        nan_cells=nan, inf_cells=inf, duplicate_row_ids=dup, features_sha256=sha256(out / "features.csv"),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    L = []
    p_ = L.append
    p_(f"PHASE B TIER-1 FEATURE REPORT  registry {R.REGISTRY_VERSION}  source {src.relative_to(ROOT)}  code_hash {code_hash}")
    p_(f"source rows {len(df)} -> pool {len(pool)} -> dataset {len(ds)} rows ({ds['ticker'].nunique()} tickers); "
       f"B0 rows in dataset {int(ds['is_b0'].sum())}; duplicate row_ids {dup}")
    p_("\nEXCLUSIONS (stage, reason, count)")
    for (stage, reason), n in excl.groupby(["stage", "reason"]).size().items():
        p_(f"  {stage:<9}{reason:<46}{n:>6}")
    p_(f"  total excluded {len(excl)}; pool + dataset check: {len(pool)} - {int((excl['stage'] == 'features').sum())} = {len(ds)}")
    p_("\nOUTCOMES in dataset (not labels; carried for later): " + str(ds["outcome"].value_counts().to_dict()))
    p_(f"entries by year: {ds.groupby(ds['entry_time'].dt.year).size().to_dict()}")
    p_(f"\nMISSING VALUES in the 18 model columns: NaN cells {nan}, inf cells {inf}")
    p_("\nFEATURE RANGES (raw, unclipped)")
    p_(f"  {'column':<22}{'min':>10}{'p1':>10}{'median':>10}{'mean':>10}{'p99':>10}{'max':>12}{'n_unique':>9}")
    for c in R.MODEL_COLUMNS:
        v = X[c].to_numpy(dtype=float)
        p_(f"  {c:<22}{v.min():>10.3f}{np.percentile(v, 1):>10.3f}{np.median(v):>10.3f}{v.mean():>10.3f}"
           f"{np.percentile(v, 99):>10.3f}{v.max():>12.3f}{len(np.unique(v)):>9}")
    (out / "report.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
