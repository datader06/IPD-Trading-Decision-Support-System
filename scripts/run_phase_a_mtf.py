"""Phase A hardening for WIT and MIT (strict B0 lists; DIT15 baseline untouched).

  python scripts/run_phase_a_mtf.py generate --combo=wit|mit --mode=legacy|pit_trend|pit [--workers=K] [--sample=N] [--no-replay]
  python scripts/run_phase_a_mtf.py report   [--run=ID]
  python scripts/run_phase_a_mtf.py verify   --combo=wit|mit [--run=ID]       (legacy mode vs the stored 2021+ results, trade lists)

Modes: legacy = pre-hardening pipeline reproduced exactly; pit_trend = only the trend look-ahead fix; pit = full hardening
(see src/candidates_mtf.py). Run id = nogit-<hash of the Phase A code + this runner> (no git call). Output:
results/<run id>/phase_a_mtf/<combo>/<mode>/candidates.csv (+ run_info.txt). Offline: frozen frames and the cached minute files only.
Workers default to half the cores at below-normal priority.
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
import candidates_mtf as M  # noqa: E402
import costs  # noqa: E402
import portfolio as P  # noqa: E402
import runinfo  # noqa: E402

LEGACY_DIR = ROOT / "legacy" / "handoff" / "handoff"
OLD = {"wit": "results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv",
       "mit": "results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv"}
MODES = {"legacy": M.LEGACY, "pit_trend": M.Mode(True, False, False, False, False, "pit_trend"),
         "pit_2h": M.Mode(True, True, False, False, False, "pit_2h"), "pit": M.PIT}
STAGES = {"wit": ("legacy", "pit_trend", "pit_2h", "pit"), "mit": ("legacy", "pit_trend", "pit")}
STAGE_TEXT = {"pit_trend": "+ trend look-ahead fix", "pit_2h": "+ session-aligned 2h LTF bars",
              "pit": "+ all-time ATH, corporate-action reset, no windows (= hardened)"}
START = pd.Timestamp("2021-01-01")
TIME_COLS = ["htf_base_start", "htf_formed_at", "T_H", "ltf_formed_at", "T_L", "entry_bar", "entry_time", "scan_start", "fill_time",
             "exit_time"]


def arg(name, default=None):
    v = [a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")]
    return v[0] if v else default


def run_id():
    h = hashlib.sha1((runinfo.code_hash() + hashlib.sha1(Path(__file__).read_bytes()).hexdigest()).encode()).hexdigest()[:8]
    return arg("run") or f"nogit-{h}"


def outdir(combo, mode):
    d = ROOT / "results" / run_id() / "phase_a_mtf" / combo / mode
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    M.CD.engine()


def _work(a):
    t, combo, mode, replay = a
    try:
        return t, M.build(t, combo, mode=MODES[mode], do_replay=replay), None
    except Exception as e:
        return t, [], repr(e)[:200]


def universe():
    t = [x for x in json.load(open(LEGACY_DIR / "code" / "webapp" / "universe_live.json"))["tickers"] if x != "HFCL.NS"]
    return sorted(x for x in t if all((M.FRAMES / f"{x}__{iv}.csv").exists() for iv in ("1d", "60m", "15m")))


def generate():
    combo, mode = arg("combo"), arg("mode", "pit")
    tickers = universe()
    if arg("sample"):
        n = int(arg("sample"))
        tickers = [tickers[round(i * (len(tickers) - 1) / max(n - 1, 1))] for i in range(n)]
    workers = int(arg("workers", max(1, mp.cpu_count() // 2)))
    replay = "--no-replay" not in sys.argv
    _low_priority()
    print(f"{combo} {mode}: {len(tickers)} tickers, workers {workers}, replay {replay}", flush=True)
    rows, errors = [], []
    with mp.Pool(workers, initializer=_init) as p:
        for i, (t, r, e) in enumerate(p.imap_unordered(_work, [(t, combo, mode, replay) for t in tickers], chunksize=1), 1):
            rows += r
            if e:
                errors.append((t, e))
            if i % 100 == 0:
                print(f"  {i}/{len(tickers)}", flush=True)
    df = pd.DataFrame(rows)
    for c in ("htf_key", "ltf_key"):
        df[c] = df[c].astype(str)
    df = df.sort_values(["entry_time", "ticker", "htf_formed_at", "type"], kind="mergesort").reset_index(drop=True)
    od = outdir(combo, mode)
    df.to_csv(od / "candidates.csv", index=False)
    (od / "run_info.txt").write_text(f"mode={MODES[mode]}\ncombo={combo}\ntickers={len(tickers)}\nerrors={errors}\n"
                                     f"code_hash={runinfo.code_hash()}\nrun_id={run_id()}\n")
    print(f"saved {od / 'candidates.csv'} rows {len(df)} errors {len(errors)} {errors[:3]}")


def load(combo, mode):
    d = pd.read_csv(outdir(combo, mode) / "candidates.csv", parse_dates=TIME_COLS, float_precision="round_trip")
    return d[(d["entry_bar"] >= START)].copy()


def load_old(combo, filled=False):
    d = pd.read_csv(ROOT / OLD[combo], parse_dates=["entry_time", "fill_time", "exit_time_new"])
    d = d[d["entry_time"] >= START].drop_duplicates(["ticker", "entry_time", "type", "entry_price", "stop"]).copy()
    d["outcome"] = d["exit_outcome"].str.upper()
    d["r_gross"] = d["exit_r"]
    d["exit_time"] = d["exit_time_new"]
    d["exit_price"] = d["fill_price"]  # old files store no exit price: costs approximate it by the entry fill (marked ~)
    d["ca_excluded"] = False
    if filled:
        m = ~d["outcome"].isin(["WIN", "LOSS"])
        d.loc[m, "outcome"] = d.loc[m, "heuristic_outcome"].str.upper()
        d.loc[m, "r_gross"] = d.loc[m, "heuristic_r"]
    return d


def usable(d):
    return d[~d["ca_excluded"]].drop_duplicates(["ticker", "type", "entry_time", "entry_price", "stop"])


def key(d):
    return pd.Series(list(zip(d["ticker"], d["type"], d["entry_price"].round(4), d["stop"].round(4),
                              pd.to_datetime(d["entry_bar"] if "entry_bar" in d else d["entry_time"]).dt.normalize().astype(str))),
                     index=d.index)


def costed(d):
    d = d.copy()
    res = d["outcome"].isin(["WIN", "LOSS"]).to_numpy()
    for cm in costs.scenarios(0.0)[1:]:
        v = np.full(len(d), np.nan)
        for i in np.nonzero(res)[0]:
            v[i] = cm.net_r(d["r_gross"].iat[i], d["fill_price"].iat[i], d["exit_price"].iat[i], d["risk"].iat[i])
        d[f"r_{cm.name}"] = v
    return d


HDR = ("| Set | Trades | W | L | Ambig. | Open/Cens. | Resolved | Win rate (95% CI) | Exp. R | PF | Total R | Max DD (R) |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")


def line(label, s):
    return (f"| {label} | {s['n']} | {s['WIN']} | {s['LOSS']} | {s['AMBIGUOUS']} | {s['OPEN'] + s['CENSORED']} | {s['WIN'] + s['LOSS']} | "
            f"{s['win_rate']:.1f}% {s['boot95']} | {s['expectancy_r']:+.3f} | {s['profit_factor']:.2f} | {s['total_r']:+.1f} | {s['max_dd_r']:.1f} |")


def verify():
    combo = arg("combo")
    o = load_old(combo)
    L = usable(load(combo, "legacy"))
    ko, kl = set(zip(o.ticker, o.type, o.entry_price.round(4), o.stop.round(4), o.entry_time.astype(str))), \
        set(zip(L.ticker, L.type, L.entry_price.round(4), L.stop.round(4), L.entry_time.astype(str)))
    print(f"{combo}: legacy-mode trades {len(L)} vs stored {len(o)}; identical {len(ko & kl)}; only stored {len(ko - kl)}; only legacy-mode {len(kl - ko)}")


def report():
    out = ROOT / "results" / run_id() / "phase_a_mtf"
    md = []
    w = md.append
    w("# WIT and MIT hardening: before vs hardened (strict lists, entries from 2021-01-01, gross unless stated)\n")
    w("Before = stored 2021+ results of the pre-hardening engine (Kite replay). Legacy mode = the same pipeline re-run through the new "
      "orchestrator (must reproduce the stored trade list) and re-scored with the unchanged replay and today's minute cache. "
      "Hardened = point-in-time mode. Resolved = WIN + LOSS; AMBIGUOUS never converted; max drawdown on the cumulative R curve by exit time.\n")
    summary = {}
    for combo in ("wit", "mit"):
        name = combo.upper()
        o, op = load_old(combo), load_old(combo, True)
        stages = {m: usable(load(combo, m)) for m in STAGES[combo]}
        ca = {m: int(load(combo, m)["ca_excluded"].sum()) for m in stages}
        ko = set(zip(o.ticker, o.type, o.entry_price.round(4), o.stop.round(4), o.entry_time.astype(str)))
        L = stages["legacy"]
        kl = set(zip(L.ticker, L.type, L.entry_price.round(4), L.stop.round(4), L.entry_time.astype(str)))
        w(f"## {name}\n")
        w(HDR)
        w(line(f"{name} before, replay-only (stored)", P.summary(o)))
        w(line(f"{name} before, as published (heuristic-filled)", P.summary(op)))
        w(line("legacy mode, re-scored (reproduction)", P.summary(L)))
        for m in STAGES[combo][1:-1]:
            w(line(f"cumulative: {STAGE_TEXT[m]}", P.summary(stages[m])))
        w(line("**hardened (full point-in-time)**", P.summary(stages["pit"])))
        w(f"\nReproduction check: legacy mode gives {len(L)} trades vs {len(o)} stored; identical trade keys {len(ko & kl)}, "
          f"only stored {len(ko - kl)}, only legacy mode {len(kl - ko)}. Corporate-action-excluded trades: "
          + ", ".join(f"{m} {c}" for m, c in ca.items()) + ".\n")
        b, h = P.summary(L), P.summary(stages["pit"])
        w("Attribution, one step at a time (each step adds one fix to the previous row; same replay and minute cache):\n")
        w("| Step | Trades | in both / removed / added | Win rate | Exp. R | PF | Total R | Max DD (R) | Resolved |\n|---|---|---|---|---|---|---|---|---|")
        prev = None
        for m in STAGES[combo]:
            cur = stages[m]
            sc = P.summary(cur)
            if prev is None:
                w(f"| legacy (reproduction) | {len(cur)} | - | {sc['win_rate']:.1f}% | {sc['expectancy_r']:+.3f} | {sc['profit_factor']:.2f} | "
                  f"{sc['total_r']:+.1f} | {sc['max_dd_r']:.1f} | {sc['WIN'] + sc['LOSS']} |")
            else:
                kp, kc = set(key(prev)), set(key(cur))
                sp = P.summary(prev)
                w(f"| {STAGE_TEXT[m]} | {len(cur)} | {len(kp & kc)} / {len(kp - kc)} / {len(kc - kp)} | {sc['win_rate']:.1f}% "
                  f"({sc['win_rate'] - sp['win_rate']:+.1f}) | {sc['expectancy_r']:+.3f} ({sc['expectancy_r'] - sp['expectancy_r']:+.3f}) | "
                  f"{sc['profit_factor']:.2f} | {sc['total_r']:+.1f} ({sc['total_r'] - sp['total_r']:+.1f}) | {sc['max_dd_r']:.1f} | "
                  f"{sc['WIN'] + sc['LOSS']} ({sc['WIN'] + sc['LOSS'] - sp['WIN'] - sp['LOSS']:+d}) |")
            prev = cur
        w("\nChange, legacy to hardened:\n")
        w("| Win rate | Expectancy R | Profit factor | Total R | Max DD (R) | Resolved |\n|---|---|---|---|---|---|")
        w(f"| {h['win_rate'] - b['win_rate']:+.1f} pts | {h['expectancy_r'] - b['expectancy_r']:+.3f} | {h['profit_factor'] - b['profit_factor']:+.2f} | "
          f"{h['total_r'] - b['total_r']:+.1f} | {h['max_dd_r'] - b['max_dd_r']:+.1f} | {h['WIN'] + h['LOSS'] - b['WIN'] - b['LOSS']:+d} |\n")
        H = stages["pit"]
        kh = key(H)
        kb = key(L)
        both = set(kb) & set(kh)
        rng = np.random.default_rng(12345)
        rb = L[L.outcome.isin(["WIN", "LOSS"])]["r_gross"].to_numpy(float)
        rh = H[H.outcome.isin(["WIN", "LOSS"])]["r_gross"].to_numpy(float)
        ci = np.percentile([rng.choice(rh, len(rh)).mean() - rng.choice(rb, len(rb)).mean() for _ in range(5000)], [2.5, 97.5])
        w(f"Bootstrap 95% interval of the expectancy change: [{ci[0]:+.3f}, {ci[1]:+.3f}] R "
          f"({'includes 0: not distinguishable from noise' if ci[0] < 0 < ci[1] else 'excludes 0'}).\n")
        kept, rem, add = H[kh.isin(both)], L[~kb.isin(both)], H[~kh.isin(both)]
        w(f"Trade-set change: {len(both)} orders in both, {len(rem)} removed by the hardening, {len(add)} added.\n")
        w(HDR)
        w(line("kept in both (hardened outcomes)", P.summary(kept)))
        w(line("removed", P.summary(rem)))
        w(line("added", P.summary(add)))
        amb = H[H.outcome == "AMBIGUOUS"]["exit_reason"].fillna("").str.replace(r" \(.*", "", regex=True).value_counts().to_dict()
        need = amb.get("MINUTE_NOT_CACHED", 0)
        reqs = H[(H.outcome == "AMBIGUOUS") & H["exit_reason"].fillna("").str.startswith("MINUTE_NOT_CACHED")]
        nreq = len(set(zip(reqs.ticker, pd.to_datetime(reqs.exit_time).dt.normalize())))
        w(f"\nHardened ambiguity: {amb}. Kite minute requests that would resolve the MINUTE_NOT_CACHED trades: {nreq} (one per symbol-day); "
          "not fetched (no authorisation in this task).\n")
        outc = H["outcome"].value_counts().to_dict()
        w(f"Hardened outcome classes: {outc}.\n")
        w("Cost scenarios (round trip, no slippage; the stored 'before' rows approximate the exit price by the entry fill, marked ~):\n")
        w("| Cost | Set | Resolved | Win rate | Exp. R | PF | Total R | Max DD (R) |\n|---|---|---|---|---|---|---|---|")
        sets = [("before ~", costed(o)), ("legacy re-scored", costed(L)), ("hardened", costed(H))]
        for cname, rc in (("gross", "r_gross"), ("0.10%", "r_rt0.10"), ("0.20%", "r_rt0.20"), ("0.30%", "r_rt0.30")):
            for lab, d in sets:
                s = P.summary(d, rc)
                w(f"| {cname} | {lab} | {s['WIN'] + s['LOSS']} | {s['win_rate']:.1f}% | {s['expectancy_r']:+.3f} | {s['profit_factor']:.2f} | "
                  f"{s['total_r']:+.1f} | {s['max_dd_r']:.1f} |")
        w("\nBy year (resolved / win % / expectancy R): " + "; ".join(
            f"{y}: " + " vs ".join(
                (lambda s: f"{s['WIN'] + s['LOSS']}/{s['win_rate']:.0f}%/{s['expectancy_r']:+.2f}" if s['WIN'] + s['LOSS'] else "0")(
                    P.summary(d[pd.to_datetime(d.entry_time).dt.year == y])) for d in (L, H)) for y in range(2021, 2027))
          + " (legacy vs hardened)\n")
        summary[combo] = dict(legacy=b, hard=h)
    text = "\n".join(md)
    (out / "hardening_report.md").write_text(text, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(dict(run_id=run_id(), code_hash=runinfo.code_hash(), old=OLD,
                                                       modes={k: str(v) for k, v in MODES.items()}), indent=2), encoding="utf-8")
    print(text)
    print(f"\nsaved {out / 'hardening_report.md'}")


if __name__ == "__main__":
    {"generate": generate, "report": report, "verify": verify}[sys.argv[1]]()
