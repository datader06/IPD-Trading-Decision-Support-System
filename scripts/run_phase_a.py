"""Phase A runner: DIT15 candidates (strict B0 + relaxed pool) with offline deterministic replay, then reports.

  python scripts/run_phase_a.py generate --label=pit [--mode=pit|legacy] [--no-pit-trend] [--no-session-2h] [--no-ath-full]
                                         [--no-ca-reset] [--sample=N | --tickers=A.NS,B.NS] [--workers=K] [--from=2021-01-01]
  python scripts/run_phase_a.py report  --label=pit [--before=results/4d02f6d/trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv]
                                         [--slippage=0.0]
  python scripts/run_phase_a.py compare --a=LABEL --b=LABEL          (B0 trade-level differences between two runs)

Outputs: results/<run id>/phase_a/<label>/candidates.csv, report.txt (run id = git hash or nogit-<code hash>, src/runinfo.py).
Checkpoints: data/cache/checkpoints/phase_a/<label>-<code hash>/<ticker>.pkl (a rerun with the same code skips finished tickers;
different code -> different folder). Offline only (frozen Kite frames + cached minute files); Kite is never called.
Workers default to half the cores, at below-normal priority (user rule).
"""
import json
import multiprocessing as mp
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import runinfo  # noqa: E402

LEGACY = ROOT / "legacy" / "handoff" / "handoff"
FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
SKIP = {"HFCL.NS"}
SPLIT = pd.Timestamp("2026-01-01")
YEARS = range(2021, 2027)
ORDER_KEY = ["ticker", "type", "entry_time", "entry_price", "stop"]


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def universe():
    t = [x for x in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if x not in SKIP]
    return sorted(x for x in t if all((FRAMES / f"{x}__{iv}.csv").exists() for iv in ("1d", "60m", "15m")))


def pick(tickers):
    if arg("tickers"):
        return arg("tickers").split(",")
    n = arg("sample")
    if n:
        n = int(n)
        return [tickers[round(i * (len(tickers) - 1) / max(n - 1, 1))] for i in range(n)]
    return tickers


def mode_from_args():
    import candidates as CD
    base = CD.LEGACY if arg("mode", "pit") == "legacy" else CD.PIT
    kw = dict(pit_trend=base.pit_trend, session_2h=base.session_2h, ath_full=base.ath_full, ca_reset=base.ca_reset,
              formation_at_close=False)
    for flag, k in (("--no-pit-trend", "pit_trend"), ("--no-session-2h", "session_2h"), ("--no-ath-full", "ath_full"),
                    ("--no-ca-reset", "ca_reset")):
        if flag in sys.argv:
            kw[k] = False
    if "--formation-at-close" in sys.argv:
        kw["formation_at_close"] = True
    return CD.Mode(name=arg("label", base.name), **kw)


def outdir(label):
    """results/<run>/phase_a/<label>; --run=<id> reads/writes an earlier run's folder (reports on runs made by older code)."""
    d = ROOT / "results" / (arg("run") or runinfo.run_id()) / "phase_a" / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def _low_priority():
    """Below-normal priority (user rule). The pseudo-handle must be typed as a pointer: with ctypes' default 32-bit int return
    type it is truncated on 64-bit Python and SetPriorityClass fails with ERROR_INVALID_HANDLE (the older runners' version)."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


_MODE = None


def _init(mode):
    global _MODE
    _low_priority()
    sys.dont_write_bytecode = True
    _MODE = mode
    import candidates
    candidates.engine()


def _work(t):
    import candidates as CD
    try:
        return t, CD.build(t, mode=_MODE, do_replay="--no-replay" not in sys.argv), None
    except Exception as e:  # recorded and reported, never silently dropped
        return t, [], repr(e)[:200]


def generate():
    mode = mode_from_args()
    label = arg("label", mode.name)
    tickers = pick(universe())
    workers = int(arg("workers", max(1, mp.cpu_count() // 2)))
    ck = ROOT / "data" / "cache" / "checkpoints" / "phase_a" / f"{label}-{runinfo.code_hash()}"
    ck.mkdir(parents=True, exist_ok=True)
    safe = lambda t: t.replace("&", "_AMP_")  # noqa: E731
    done, rows, errors = set(), [], []
    for t in tickers:
        f = ck / f"{safe(t)}.pkl"
        if f.exists():
            rows += pickle.load(open(f, "rb"))
            done.add(t)
    todo = [t for t in tickers if t not in done]
    _low_priority()
    print(f"label {label} mode {mode}; tickers {len(tickers)} (checkpointed {len(done)}, to run {len(todo)}); workers {workers}",
          flush=True)
    with mp.Pool(workers, initializer=_init, initargs=(mode,)) as pool:
        for i, (t, r, err) in enumerate(pool.imap_unordered(_work, todo, chunksize=1), 1):
            if err:
                errors.append((t, err))
            else:
                pickle.dump(r, open(ck / f"{safe(t)}.pkl", "wb"))
                rows += r
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} tickers, {len(rows)} rows, errors {len(errors)}", flush=True)
    df = pd.DataFrame(rows)
    if len(df):
        for c in ("htf_key", "ltf_key"):
            df[c] = df[c].astype(str)
        df = df.sort_values(["entry_time", "ticker", "htf_formed_at", "type"], kind="mergesort").reset_index(drop=True)
    od = outdir(label)
    df.to_csv(od / "candidates.csv", index=False)
    (od / "run_info.txt").write_text(f"mode={mode}\ntickers={len(tickers)}\nerrors={errors}\ncode_hash={runinfo.code_hash()}\n")
    print(f"saved {od / 'candidates.csv'} rows {len(df)}; errors {len(errors)} {errors[:3]}")


# ------------------------------------------------------------------------------------------------- reporting
def load(label):
    p = outdir(label) / "candidates.csv"
    df = pd.read_csv(p, parse_dates=["entry_time", "htf_formed_at", "ltf_formed_at", "T_H", "T_L", "fill_time", "exit_time",
                                     "htf_base_start"])
    return df


def add_costs(df, slippage):
    import costs
    for cm in costs.scenarios(slippage):
        col = f"r_{cm.name}"
        v = np.full(len(df), np.nan)
        res = df["outcome"].isin(["WIN", "LOSS"]).to_numpy()
        for i in np.nonzero(res)[0]:
            v[i] = cm.net_r(df["r_gross"].iat[i], df["fill_price"].iat[i], df["exit_price"].iat[i], df["risk"].iat[i])
        df[col] = v
    return df


def report():
    import portfolio as P
    import costs
    label = arg("label", "pit")
    entry_from = pd.Timestamp(arg("from", "2021-01-01"))
    slippage = float(arg("slippage", "0"))
    df = load(label)
    df = df[df["entry_time"] >= entry_from].reset_index(drop=True)
    df = add_costs(df, slippage)
    lines = []
    p = lines.append
    p(f"PHASE A REPORT  label={label}  run={arg('run') or runinfo.run_id()}  entries >= {entry_from.date()}  "
      f"slippage/side={slippage}%")
    p("Outcome classes: WIN/LOSS resolved; AMBIGUOUS never converted (bounds shown); OPEN = no exit within 90 days; "
      "CENSORED = data ends first; NOFILL = entry never traded. Metrics on WIN+LOSS. R = gross unless the column says rt*.")
    b0_all = df[df["is_b0"]]
    ca = b0_all[b0_all["ca_excluded"]]
    b0 = b0_all[~b0_all["ca_excluded"]].copy()
    p(f"\n=== B0 (strict, corrected): {len(b0_all)} trades, of which corporate-action excluded {len(ca)} -> {len(b0)} used ===")
    for t in ca.itertuples():
        p(f"  CA-excluded: {t.ticker} {t.entry_time:%Y-%m-%d %H:%M} {t.type} outcome={t.outcome}")
    dup = b0.duplicated(ORDER_KEY).sum()
    p(f"duplicate orders (same ticker/type/entry time/entry/stop from two HTF zones): {dup}")
    _block(p, b0, "B0", P)
    for cm in costs.scenarios(slippage)[1:]:
        p(f"\n-- B0 net of costs, scenario {cm.name} (round trip {2 * cm.lump_pct_per_side:.2f}% + slippage {slippage}%/side)")
        for lab, sub in (("ALL", b0), ("TRAIN (<2026)", b0[b0.entry_time < SPLIT]), ("HOLDOUT (2026)", b0[b0.entry_time >= SPLIT])):
            p(P.fmt(lab, P.summary(sub, f"r_{cm.name}")))
    taken = P.capital_constrained(b0)
    p(f"\n-- B0 capital-constrained (Rs 1L, no leverage): taken {int(taken.sum())} of {len(b0)}")
    p(P.fmt("CAPPED gross", P.summary(b0[taken])))
    p(P.fmt("CAPPED rt0.20", P.summary(b0[taken], "r_rt0.20")))
    n, dep = P.concurrency(b0)
    p(f"all-signals concurrency: max open positions {n}, peak deployed Rs {dep:,.0f}")
    res = b0[b0.outcome.isin(["WIN", "LOSS"])]
    rs = (res["r_gross"] * res["shares"] * res["risk"])
    p(f"rupees (all signals, gross): total Rs {rs.sum():+,.0f}; max drawdown Rs {P.max_drawdown(P.order(res).eval('r_gross*shares*risk')):,.0f}")
    p("\nAMBIGUOUS reasons (B0): " + str(b0[b0.outcome == "AMBIGUOUS"]["exit_reason"].str.replace(r" \(.*", "", regex=True).value_counts().to_dict()))
    p("decided at 1minute (B0): " + str(int((b0.decided_interval == "1minute").sum())))

    before = arg("before")
    if before:
        _before(p, b0, before, P)

    _relaxed(p, df, b0_all, P)
    od = outdir(label)
    (od / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nsaved {od / 'report.txt'}")


def _block(p, d, name, P):
    p(P.fmt(f"{name} ALL", P.summary(d)))
    for y in YEARS:
        p(P.fmt(f"{name} {y}", P.summary(d[d.entry_time.dt.year == y])))
    p(P.fmt(f"{name} TRAIN (<2026)", P.summary(d[d.entry_time < SPLIT])))
    p(P.fmt(f"{name} HOLDOUT (2026)", P.summary(d[d.entry_time >= SPLIT])))
    p(f"per-year n add up: {sum((d.entry_time.dt.year == y).sum() for y in YEARS)} of {len(d)}; "
      f"trades/year: {', '.join(f'{y}: {(d.entry_time.dt.year == y).sum()}' for y in YEARS)}")


def _before(p, b0, path, P):
    old = pd.read_csv(ROOT / path, parse_dates=["entry_time", "exit_time", "fill_time"])
    old = old.assign(outcome=old["exit_outcome"].str.upper().replace({"NOFILL": "NOFILL"}), r_gross=old["exit_r"],
                     exit_time=pd.to_datetime(old["exit_time_new"]))
    p(f"\n=== BEFORE: {path} ({len(old)} trades; legacy pipeline, Kite replay; old outcome labels) ===")
    p(P.fmt("BEFORE replay-only", P.summary(old)))
    pub = old.copy()
    real = pub.outcome.isin(["WIN", "LOSS"])
    pub.loc[~real, "outcome"] = pub.loc[~real, "heuristic_outcome"].str.upper()
    pub.loc[~real, "r_gross"] = pub.loc[~real, "heuristic_r"]
    p(P.fmt("BEFORE as published", P.summary(pub)) + "   (heuristic fills AMBIGUOUS)")
    k = lambda d: set(zip(d.ticker, d.entry_time.dt.strftime("%Y-%m-%d %H:%M"), d.type, d.entry_price.round(4), d.stop.round(4)))  # noqa: E731
    a, b = k(old), k(b0)
    p(f"trade overlap: in both {len(a & b)}, only before {len(a - b)}, only after {len(b - a)}")
    m = old.assign(_k=list(zip(old.ticker, old.entry_time.dt.strftime("%Y-%m-%d %H:%M"), old.type, old.entry_price.round(4), old.stop.round(4)))) \
        .merge(b0.assign(_k=list(zip(b0.ticker, b0.entry_time.dt.strftime("%Y-%m-%d %H:%M"), b0.type, b0.entry_price.round(4), b0.stop.round(4)))),
               on="_k", suffixes=("_old", "_new"))
    ch = m[m.outcome_old != m.outcome_new]
    p(f"same trade, different outcome class: {len(ch)} " + str(ch.groupby(["outcome_old", "outcome_new"]).size().to_dict()))


def _relaxed(p, df, b0_all, P):
    pool = df[df["relaxed_selected"] | df["is_b0"]]
    dedup = pool.drop_duplicates(ORDER_KEY)
    p(f"\n=== RELAXED POOL (A11/A12) ===")
    p(f"rows {len(pool)} (relaxed-selected {int(pool.relaxed_selected.sum())}, B0 {int(pool.is_b0.sum())}, "
      f"B0 not chosen by relaxed matching = displaced {int((pool.is_b0 & ~pool.relaxed_selected).sum())}); "
      f"after removing duplicate orders {len(dedup)}; corporate-action excluded {int(dedup.ca_excluded.sum())}")
    use = dedup[~dedup.ca_excluded]
    b0u = b0_all[~b0_all.ca_excluded]
    p(f"{'year':<8}{'strict':>8}{'relaxed':>9}{'x':>7}{'WIN':>6}{'LOSS':>6}{'AMB':>6}{'OPEN':>6}{'CENS':>6}{'NOFILL':>7}")
    for y in list(YEARS) + ["TOTAL"]:
        s = b0u if y == "TOTAL" else b0u[b0u.entry_time.dt.year == y]
        r = use if y == "TOTAL" else use[use.entry_time.dt.year == y]
        c = r.outcome.value_counts()
        p(f"{str(y):<8}{len(s):>8}{len(r):>9}{(len(r) / len(s) if len(s) else float('nan')):>7.2f}{c.get('WIN', 0):>6}"
          f"{c.get('LOSS', 0):>6}{c.get('AMBIGUOUS', 0):>6}{c.get('OPEN', 0):>6}{c.get('CENSORED', 0):>6}{c.get('NOFILL', 0):>7}")
    p(P.fmt("RELAXED ALL (gross)", P.summary(use)))
    fl = ["trend_htf_fail", "trend_entry_fail", "wick_fresh_fail", "htf_strict_fail", "htf_cap_fail", "ltf_cap_fail"]
    p("flag counts (True = strict pipeline would reject): " + ", ".join(f"{f} {int(use[f].sum())}" for f in fl))
    nf = use[fl].sum(axis=1)
    p("candidates by number of failed former filters: " + str(nf.value_counts().sort_index().to_dict()))
    per = use.groupby("ticker").size()
    p(f"tickers with >= 1 candidate: {len(per)}; per-ticker count: median {per.median():.0f}, mean {per.mean():.1f}, "
      f"max {per.max()} ({per.idxmax()}); top 10 {per.sort_values(ascending=False).head(10).to_dict()}")
    p("outcome mix by flag (resolved win%):")
    for f in fl:
        for v in (False, True):
            s = P.summary(use[use[f] == v])
            p(f"   {f}={v!s:<5} n={s['n']:5d} win%={s['win_rate']:5.1f} expR={s['expectancy_r']:+.3f}")


def compare():
    a, b = load(arg("a")), load(arg("b"))
    a, b = a[a.is_b0], b[b.is_b0]
    k = lambda d: d.assign(_k=list(zip(d.ticker, d.entry_time.dt.strftime("%Y-%m-%d %H:%M"), d.type, d.entry_price.round(4), d.stop.round(4))))  # noqa: E731
    a, b = k(a), k(b)
    sa, sb = set(a._k), set(b._k)
    print(f"B0 {arg('a')}: {len(a)}  {arg('b')}: {len(b)}  both {len(sa & sb)}  only {arg('a')} {len(sa - sb)}  only {arg('b')} {len(sb - sa)}")
    for name, d, keys in ((f"only {arg('a')}", a, sa - sb), (f"only {arg('b')}", b, sb - sa)):
        x = d[d._k.isin(keys)]
        cols = [c for c in ("ticker", "type", "entry_time", "trend_htf", "trend_entry", "outcome") if c in x]
        print(f"\n{name}:\n{x[cols].to_string(index=False) if len(x) else '  none'}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "generate"
    {"generate": generate, "report": report, "compare": compare}[step]()
