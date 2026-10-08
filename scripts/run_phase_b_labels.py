"""Phase B step 2: outcome labels for the Tier-1 dataset (no model, no validation).

  python scripts/run_phase_b_labels.py [--features=results/nogit-145d6302/phase_b/tier1/features.csv]
        [--src=results/nogit-145d6302/phase_a/pit_refetch/candidates.csv] [--out=DIR] [--workers=K] [--no-replay-check]

Reads the Tier-1 feature dataset, keeps EVERY row, and adds: label (1 = WIN, 0 = LOSS, empty otherwise), label_status (WIN / LOSS /
AMBIGUOUS / CENSORED / OPEN / NOFILL), is_training_label, phase_a_src_row (row index in the Phase A candidates file) and
replay_check (fresh replay with the unchanged src/replay.py equals the stored Phase A fields). Writes labeled.csv, manifest.json
and report.txt to <run folder>/phase_b/labels/. Offline only (frozen frames + cached minute files). Workers default to half the
cores at below-normal priority.
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
import bars as B  # noqa: E402
from ml import features as F  # noqa: E402
from ml import labels as L  # noqa: E402
from ml import registry as R  # noqa: E402

DEF_FEATURES = "results/nogit-145d6302/phase_b/tier1/features.csv"
DEF_SRC = "results/nogit-145d6302/phase_a/pit_refetch/candidates.csv"
TIME_COLS = ["entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at", "fill_time", "exit_time"]


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def _low_priority():
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _init():
    _low_priority()
    sys.dont_write_bytecode = True


def _work(args):
    ticker, rows, src_rows, check = args
    d1 = B.load_frame(F.FRAMES, ticker, "1d")
    m15 = B.load_frame(F.FRAMES, ticker, "15m")
    ctx = L.ReplayContext(ticker, d1, m15)
    return L.label_rows(rows, ctx, src_row_of=lambda r: src_rows[r["row_id"]], check=check)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trace_index(src):
    """row_id -> index of the Phase A source row (row_id + htf_key + ltf_key must identify it uniquely)."""
    ids = [F.row_id(r) for r in src.to_dict("records")]
    key = pd.Series(list(zip(ids, src["htf_key"], src["ltf_key"])))
    assert not key.duplicated().any(), "source rows not uniquely identified by (row_id, htf_key, ltf_key)"
    return ids, {k: i for i, k in enumerate(key)}


def main():
    feat_path = ROOT / arg("features", DEF_FEATURES)
    src_path = ROOT / arg("src", DEF_SRC)
    out = Path(arg("out") or feat_path.parent.parent / "labels")
    out.mkdir(parents=True, exist_ok=True)
    check = "--no-replay-check" not in sys.argv
    feats = pd.read_csv(feat_path, parse_dates=TIME_COLS, float_precision="round_trip")  # exact floats: model columns stay bit-identical
    src = pd.read_csv(src_path, parse_dates=TIME_COLS, float_precision="round_trip")
    ids, idx = trace_index(src)
    src_rows = {}
    for r in feats.to_dict("records"):
        k = (r["row_id"], r["htf_key"], r["ltf_key"])
        assert k in idx, f"row {r['row_id']} not traceable to the Phase A source"
        src_rows[r["row_id"]] = idx[k]
    groups = [(t, g.to_dict("records"), {x: src_rows[x] for x in g["row_id"]}, check) for t, g in feats.groupby("ticker", sort=True)]
    workers = int(arg("workers", max(1, mp.cpu_count() // 2)))
    print(f"features {len(feats)} rows, {len(groups)} tickers; replay check {check}; workers {workers}", flush=True)
    rows = []
    with mp.Pool(workers, initializer=_init) as p:
        for i, r in enumerate(p.imap_unordered(_work, groups, chunksize=1), 1):
            rows += r
            if i % 100 == 0:
                print(f"  {i}/{len(groups)} tickers", flush=True)
    ds = pd.DataFrame(rows)
    ds = ds.sort_values(["entry_time", "ticker", "htf_formed_at", "type"], kind="mergesort").reset_index(drop=True)
    ds = ds[list(feats.columns) + L.LABEL_COLUMNS]
    ds["label"] = ds["label"].astype("Int64")
    R.assert_no_forbidden(R.MODEL_COLUMNS)
    assert ds["row_id"].tolist() == feats["row_id"].tolist() or set(ds["row_id"]) == set(feats["row_id"])
    ds.to_csv(out / "labeled.csv", index=False)

    # ---------------- verification against Phase A
    s = src.iloc[ds["phase_a_src_row"]].reset_index(drop=True)
    same_outcome = (s["outcome"].to_numpy() == ds["outcome"].to_numpy())
    cnt = ds["label_status"].value_counts().reindex(L.STATUSES, fill_value=0)
    excluded_ids = set(F.row_id(r) for r in src.to_dict("records")) - set(ds["row_id"])
    pool, _ = F.select_pool(src)
    pool_cnt = pool["outcome"].value_counts().reindex(L.STATUSES, fill_value=0)
    ex_feat = pool[~pool.apply(F.row_id, axis=1).isin(set(ds["row_id"]))]
    ex_cnt = ex_feat["outcome"].value_counts().reindex(L.STATUSES, fill_value=0)
    res = ds[ds["is_training_label"]]
    rc = ds["replay_check"].value_counts().to_dict()
    manifest = dict(
        features_file=str(feat_path.relative_to(ROOT)), features_sha256=sha256(feat_path), source_file=str(src_path.relative_to(ROOT)),
        source_sha256=sha256(src_path), registry_version=R.REGISTRY_VERSION, source_code_hash=R.SOURCE_CODE_HASH,
        rows=len(ds), status_counts={k: int(v) for k, v in cnt.items()}, replay_check=rc,
        outcome_equals_phase_a_row=int(same_outcome.sum()), label_ones=int((res["label"] == 1).sum()),
        label_zeros=int((res["label"] == 0).sum()), labeled_sha256=sha256(out / "labeled.csv"),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    lines = []
    p_ = lines.append
    p_(f"PHASE B LABEL REPORT  features {feat_path.relative_to(ROOT)}  source {src_path.relative_to(ROOT)}  code_hash {R.SOURCE_CODE_HASH}")
    p_(f"rows {len(ds)} (every Tier-1 row kept); tickers {ds['ticker'].nunique()}; model columns unchanged: "
       f"{bool((ds[R.MODEL_COLUMNS].to_numpy() == feats[R.MODEL_COLUMNS].to_numpy()).all())}")
    p_("\nSTATUS COUNTS (label_status)")
    for k in L.STATUSES:
        p_(f"  {k:<10}{int(cnt[k]):>6}   label = {'1' if k == 'WIN' else '0' if k == 'LOSS' else '(none)'}")
    p_(f"  total {int(cnt.sum())}; training labels {len(res)} (WIN {int((res['label'] == 1).sum())}, LOSS {int((res['label'] == 0).sum())})")
    p_(f"\nLABEL BALANCE (resolved): win rate {100 * (res['label'] == 1).mean():.2f}%")
    for y, g in res.groupby(res["entry_time"].dt.year):
        p_(f"  {y}: resolved {len(g):>4} wins {int((g['label'] == 1).sum()):>4} win% {100 * (g['label'] == 1).mean():5.1f}")
    p_(f"  B0 rows: {int(ds['is_b0'].sum())} (resolved {int(res['is_b0'].sum())}); relaxed-pool rows: {len(ds)}")
    p_("\nAMBIGUOUS reasons: " + str(ds[ds['label_status'] == 'AMBIGUOUS']['exit_reason'].str.replace(r' \(.*', '', regex=True).value_counts().to_dict()))
    p_("\nCOMPARISON WITH PHASE A (pit_refetch)")
    p_(f"  {'status':<10}{'Phase A pool':>13}{'excluded at features':>22}{'dataset':>9}{'pool - excluded':>17}")
    for k in L.STATUSES:
        p_(f"  {k:<10}{int(pool_cnt[k]):>13}{int(ex_cnt[k]):>22}{int(cnt[k]):>9}{int(pool_cnt[k] - ex_cnt[k]):>17}"
           + ("" if pool_cnt[k] - ex_cnt[k] == cnt[k] else "   <-- MISMATCH"))
    p_(f"  outcome equals the traced Phase A row: {int(same_outcome.sum())} of {len(ds)}")
    p_(f"  fresh replay (unchanged src/replay.py, same call path) vs stored Phase A fields: {rc}")
    if check and rc != {"match": len(ds)}:
        bad = ds[ds["replay_check"] != "match"]
        p_("  DISCREPANCIES:")
        for r in bad.head(20).itertuples():
            p_(f"    {r.row_id}  {r.replay_check}  stored={r.outcome}")
    (out / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
