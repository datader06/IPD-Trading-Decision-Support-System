"""GTF trade-score experiment (throwaway, report only). NEW FILE: nothing existing is edited; every loosened setting is an in-memory override applied at runtime.

Steps (python scripts/run_tradescore.py <step>):  profile | signals | score | report | sanity
  profile  print the effective experiment profile (old -> new values) and every other active rule
  signals  find every MIT/WIT signal with entry >= 2024-01-01 under the loosened profile, compute the trade score, per-ticker checkpoints
  score    exit scoring (15minute, then 1minute for AMBIGUOUS; heuristic where replay stays AMBIGUOUS) via scripts/replay_common.py
  report   score-band tables, overlap with cap-5 candidate and Baseline v1, review sheets
  sanity   run the untouched baseline path (no overrides) for MIT/WIT 2024+ and compare with Baseline v1
"""
import os
import pickle
import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
HASH = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
OUT = ROOT / "results" / HASH / "tradescore"
CKPT = OUT / "_ckpt"
ENTRY_FROM = pd.Timestamp("2024-01-01")
SPLIT = pd.Timestamp("2026-01-01")
SKIP = {"HFCL.NS"}
FRAMES = {"mit": ROOT / "data" / "cache" / "kite_frames", "wit": ROOT / "data" / "cache" / "kite_frames_wit_long"}
NEW_BODY, NEW_CLOSE = 1.15, 0.70   # exciting-candle test: body >= 1.15 ATR (was 1.3), close in the outer 30% (was 25%)
STEP = sys.argv[1] if len(sys.argv) > 1 else "profile"

# --- experiment-only overrides, in memory (read by src/base_candles.py at install time) ---
os.environ["DZ_LTF_CAP"] = "100000"      # LTF base cap removed
os.environ["DZ_HTF_CAP"] = "100000"      # HTF base cap removed
os.environ["DZ_BASE_LOGIC_V2"] = "1"
os.environ["DZ_HTF_LEGOUT_WICK"] = "1"   # HTF legout must close over the base wick: stays ON
os.environ["DZ_STRICT_HTF"] = "0"

sz = mtz = bc = bt = None
OLD = {}


def _low_priority():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _load(combo):
    """Import the legacy modules, capture the old config values, install V2 with no caps, then apply the loosened profile (in memory only)."""
    global sz, mtz, bc, bt
    sys.path.insert(0, str(LEGACY / "code"))
    sys.path.insert(0, str(ROOT / "src"))
    import offline_loader
    offline_loader.install(data_dir=str(FRAMES[combo]))
    import mtf_zones as _m
    import sd_zones as _s
    import base_candles as _b
    import mtf_backtest as _t
    if combo == "wit":   # same overrides as the 2021 runs: trend frame not limited to 750 bars
        _m.COMBOS["wit"] = replace(_m.COMBOS["wit"], trend_window=None)
    if combo == "mit":   # ltf (daily) not limited to 750 bars
        _m.COMBOS["mit"] = replace(_m.COMBOS["mit"], ltf_window=None)
    spec = _m.COMBOS[combo]
    for role in ("htf", "ltf", "trend"):
        c = getattr(spec, f"{role}_config")
        OLD[(combo, role)] = dict(impulse_body_atr_mult=c.impulse_body_atr_mult, impulse_close_range_pct=c.impulse_close_range_pct,
                                  max_base_candles=c.max_base_candles, require_legout_beyond_legin=c.require_legout_beyond_legin)
    _b.install(_s, _m, combos=(combo,))
    for role in ("htf", "ltf"):   # loosen exciting-candle test (never tighten: MIT's HTF is already 1.0 ATR)
        c = getattr(spec, f"{role}_config")
        c.impulse_body_atr_mult = min(c.impulse_body_atr_mult, NEW_BODY)
        c.impulse_close_range_pct = min(c.impulse_close_range_pct, NEW_CLOSE)
    spec.ltf_config.require_legout_beyond_legin = False   # Rule 1 OFF
    sz, mtz, bc, bt = _s, _m, _b, _t
    return spec


def _init(combo):
    _low_priority()
    _load(combo)


# ---------------------------------------------------------------- signal building
def _visits(htf_df, hz, entry_ts):
    """Number of earlier, separate visits to the HTF zone before the visit in which the entry happens.
    Visit = consecutive HTF bars (after the zone's leg-out bar) whose range overlaps the zone; a new visit starts after >= 1 non-overlapping bar."""
    lo, hi = mtz._zone_range(hz)
    start = hz.leg_end_index + 1
    n = len(htf_df)
    if start >= n:
        return None
    ov = ((htf_df["low"].values[start:] <= hi) & (htf_df["high"].values[start:] >= lo))
    ts = htf_df["timestamp"].values
    e = int(np.searchsorted(ts, np.datetime64(pd.Timestamp(entry_ts).normalize()), side="left"))  # HTF bar whose label is >= entry date
    e = min(e, n - 1)
    runs, a = [], None
    for k, f in enumerate(ov):
        pos = start + k
        if f and a is None:
            a = pos
        if (not f) and a is not None:
            runs.append((a, pos - 1))
            a = None
    if a is not None:
        runs.append((a, n - 1))
    return sum(1 for (x, y) in runs if y < e and not (x <= e <= y))


def _strength(df, atr, z, cfg):
    """(score, n_exciting_leg_candles, gap): gap = leg-out first candle opens outside the range of the last base candle, in the trade direction."""
    typ = z.type
    exc = sum(1 for i in range(z.leg_start_index, z.leg_end_index + 1) if sz._is_impulsive_candle(df.iloc[i], atr.iloc[i], typ, cfg))
    bi, ls = df.iloc[z.base_end_index], df.iloc[z.leg_start_index]
    gap = bool(ls["open"] > bi["high"]) if typ == "demand" else bool(ls["open"] < bi["low"])
    score = 2 if (gap or exc >= 2) else (1 if exc == 1 else 0)
    return score, exc, gap


def _base_time_score(n):
    return 2 if n <= 3 else (1 if n <= 5 else 0)


def _old_exciting_ok(df, atr, z, cfg, role, combo):
    o = OLD[(combo, role)]
    old = replace(cfg, impulse_body_atr_mult=o["impulse_body_atr_mult"], impulse_close_range_pct=o["impulse_close_range_pct"])
    return any(sz._is_impulsive_candle(df.iloc[i], atr.iloc[i], z.type, old) for i in range(z.leg_start_index, z.leg_end_index + 1))


def build_signals(args):
    combo, ticker = args
    spec = mtz.COMBOS[combo]
    htf_df = mtz._build_frame(ticker, spec.htf_source, spec.htf_interval, spec.ltf_fetch_period, spec.htf_resample, spec.htf_window)
    ltf_df = mtz._build_frame(ticker, spec.ltf_source, spec.ltf_interval, spec.ltf_fetch_period, spec.ltf_resample, spec.ltf_window)
    if len(htf_df) < 20 or len(ltf_df) < 20:
        return ticker, []
    htf_zones = mtz.detect_zones(htf_df, config=spec.htf_config, allow_wick_to_wick=False)
    trend_df = mtz._build_frame(ticker, spec.trend_source, spec.trend_interval, spec.trend_fetch_period, spec.trend_resample, spec.trend_window)
    if len(trend_df) < 20:
        return ticker, []
    trend_zones = mtz.detect_zones(trend_df, config=spec.trend_config, allow_wick_to_wick=False)
    events = mtz._compute_trend_events(trend_df, trend_zones)
    htf_zones = mtz.filter_zones_by_trend_3tf(htf_zones, htf_df, trend_df, trend_zones)   # trend at HTF formation (legacy rule, ON)
    ltf_zones = mtz.detect_zones(ltf_df, config=spec.ltf_config)
    ltf_atr, htf_atr = mtz.wilder_atr(ltf_df), mtz.wilder_atr(htf_df)
    ema20, ema50 = ltf_df["close"].ewm(span=20, adjust=False).mean(), ltf_df["close"].ewm(span=50, adjust=False).mean()
    rows = []
    for hz in htf_zones:                                   # same selection logic as mtf_zones.match_zones
        h_lo, h_hi = mtz._zone_range(hz)
        h_base_start = htf_df.iloc[hz.base_start_index]["timestamp"]
        h_leg_end = mtz._zone_formed_at(htf_df, hz)
        w0, w1 = pd.Timestamp(h_base_start).normalize(), pd.Timestamp(h_leg_end).normalize()
        same = ltf_df["timestamp"].dt.normalize() <= w1
        cutoff = ltf_df.loc[same, "timestamp"].max() if same.any() else w1
        cands = []
        for lz in ltf_zones:
            if lz.type != hz.type:
                continue
            l_lo, l_hi = mtz._zone_range(lz)
            hgt = l_hi - l_lo
            if hgt <= 0:
                continue
            lf = mtz._zone_formed_at(ltf_df, lz)
            if not (w0 <= pd.Timestamp(lf).normalize() <= w1):
                continue
            if lz.tested_at_timestamp is not None and pd.Timestamp(lz.tested_at_timestamp) <= cutoff:
                continue
            frac = (min(h_hi, l_hi) - max(h_lo, l_lo)) / hgt
            if frac < mtz.MIN_LTF_OVERLAP_FRAC:
                continue
            cands.append((frac, lf, lz))
        if not cands:
            continue
        cands.sort(key=lambda c: (c[1], c[0]), reverse=True)
        frac, lf, lz = cands[0]
        if lz.tested_at_index is None:
            continue
        entry_idx = lz.tested_at_index
        entry_ts = ltf_df.iloc[entry_idx]["timestamp"]
        if entry_ts < ENTRY_FROM:
            continue
        # trend re-check at entry (legacy rule, ON)
        tr = mtz._classify_trend_from_events(trend_df, events, entry_ts)
        if tr is not None and ((hz.type == "demand" and tr == "down") or (hz.type == "supply" and tr == "up")):
            continue
        # legacy HTF wick-freshness: NOT a filter here, only recorded
        wt = mtz._htf_wick_tested_at(htf_df, hz)
        legacy_wick_reject = bool(wt is not None and pd.Timestamp(wt).normalize() < pd.Timestamp(entry_ts).normalize())
        touches = _visits(htf_df, hz, entry_ts)
        if touches is None:
            continue
        fresh = 3.0 if touches == 0 else (1.5 if touches == 1 else 0.0)
        s_score, s_exc, s_gap = _strength(ltf_df, ltf_atr, lz, spec.ltf_config)
        lbc = len(bc.base_run(ltf_df, ltf_atr, lz.leg_start_index, spec.ltf_config, sz))
        hbc = len(bc.base_run(htf_df, htf_atr, hz.leg_start_index, spec.htf_config, sz))
        hs_score, hs_exc, hs_gap = _strength(htf_df, htf_atr, hz, spec.htf_config)
        l_lo, l_hi = mtz._zone_range(lz)
        j = max(entry_idx - 1, 0)   # EMA known before the entry bar
        ema_flag = bool(any(l_lo <= float(e.iloc[j]) <= l_hi for e in (ema20, ema50)))
        # legacy rules that would have rejected it
        legin = lz.base_start_index - 1
        rule1_reject = False
        if legin >= 0:
            lc, lr = ltf_df.iloc[lz.leg_end_index]["close"], ltf_df.iloc[legin]
            rule1_reject = bool(lc <= lr["high"]) if lz.type == "demand" else bool(lc >= lr["low"])
        exc_reject = not (_old_exciting_ok(ltf_df, ltf_atr, lz, spec.ltf_config, "ltf", combo) and _old_exciting_ok(htf_df, htf_atr, hz, spec.htf_config, "htf", combo))
        cap_reject = bool(lbc > 5 or hbc > 5)
        entry_price, stop = lz.proximal_line, lz.distal_line
        risk = abs(entry_price - stop)
        if risk <= 0:
            continue
        shares = min(int(bt.MAX_LOSS_PER_TRADE // risk), int(bt.CAPITAL // entry_price))
        if shares <= 0:
            continue
        target = entry_price + bt.REWARD_RISK * risk if hz.type == "demand" else entry_price - bt.REWARD_RISK * risk
        exit_time, outcome = bt.simulate_exit(ltf_df, entry_idx, hz.type, stop, target)
        pnl = shares * risk * bt.REWARD_RISK if outcome == "win" else (-shares * risk if outcome == "loss" else None)
        rows.append(dict(
            ticker=ticker, combo=combo, type=hz.type, htf_proximal=hz.proximal_line, htf_distal=hz.distal_line, htf_formed_at=h_leg_end,
            ltf_proximal=lz.proximal_line, ltf_distal=lz.distal_line, ltf_formed_at=lf, entry_time=entry_ts, entry_price=entry_price, stop=stop,
            target=target, risk=risk, shares=shares, exit_time=exit_time, outcome=outcome, pnl=pnl,
            htf_touches=touches, freshness=fresh, strength=s_score, ltf_exciting_candles=s_exc, ltf_gap=s_gap,
            ltf_base_count=lbc, base_time=_base_time_score(lbc), total=fresh + s_score + _base_time_score(lbc),
            htf_strength=hs_score, htf_exciting_candles=hs_exc, htf_gap=hs_gap, htf_base_count=hbc, htf_base_time=_base_time_score(hbc), ema_flag=ema_flag,
            legacy_wick_freshness_would_reject=legacy_wick_reject, rule1_would_reject=rule1_reject, old_exciting_would_reject=exc_reject,
            cap5_would_reject=cap_reject, overlap_frac=frac,
        ))
    return ticker, rows


def _tickers(combo):
    import json
    t = [x for x in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if x not in SKIP]
    fr = FRAMES[combo]
    need = ["1d"] + (["60m"] if combo == "wit" else [])
    return [x for x in t if all((fr / f"{x}__{n}.csv").exists() for n in need)]


# ---------------------------------------------------------------- steps
def do_profile():
    if len(sys.argv) < 3:   # one process per combo: the V2 installer patches a process only once
        for combo in ("mit", "wit"):
            subprocess.run([sys.executable, str(Path(__file__)), "profile", combo], check=True)
        print(STATIC_PROFILE)
        return
    for combo in (sys.argv[2],):
        spec = _load(combo)
        print(f"\n=== EXPERIMENT PROFILE: {combo.upper()} ===")
        for role in ("htf", "ltf", "trend"):
            c = getattr(spec, f"{role}_config")
            o = OLD[(combo, role)]
            print(f"{role.upper():5} exciting body >= {c.impulse_body_atr_mult} ATR (old {o['impulse_body_atr_mult']}), close in outer {100 * (1 - c.impulse_close_range_pct):.0f}% (old {100 * (1 - o['impulse_close_range_pct']):.0f}%)"
                  f"{'' if role != 'trend' else '  [trend zones: untouched]'}; max_base_candles {c.max_base_candles} (old {o['max_base_candles']}); "
                  f"legout beyond legin {c.require_legout_beyond_legin} (old {o['require_legout_beyond_legin']})")
        c = spec.htf_config
        print(f"HTF extra: base_to_leg<= {c.max_base_range_to_leg_range}, base extension {c.base_extension_atr_mult} ATR, legout-over-base-wick {getattr(c, 'legout_beyond_base_wick', None)}, "
              f"min zone width {c.min_zone_width_atr_mult} ATR, departure tol {c.departure_tolerance_atr_mult} ATR, distal buffer {c.distal_buffer_atr_mult} ATR")
        c = spec.ltf_config
        print(f"LTF extra: base_to_leg<= {c.max_base_range_to_leg_range}, line candles {getattr(c, 'line_candles', None)}, max leg candles {c.max_leg_candles}, "
              f"min zone width {c.min_zone_width_atr_mult} ATR, departure tol {c.departure_tolerance_atr_mult} ATR, distal buffer {c.distal_buffer_atr_mult} ATR")
        print(f"windows: htf_window {spec.htf_window}, ltf_window {spec.ltf_window}, trend_window {spec.trend_window}; frames {FRAMES[combo].name}")
    return


STATIC_PROFILE = """
WHERE THE VALUES LIVE: exciting-candle thresholds = ZoneConfig.impulse_body_atr_mult / impulse_close_range_pct (legacy sd_zones.py ZoneConfig; per-role copies built in
 mtf_zones.COMBOS; defaults mirrored in config.py IMPULSE_BODY_ATR_MULT 1.3 / IMPULSE_CLOSE_RANGE_PCT 0.75). Here: in-memory edits of the per-run config copies only.
 Applied as min(old, new): MIT's HTF already uses 1.0 ATR (MONTHLY_CONFIG), so it is NOT tightened to 1.15. config.py itself is NOT changed.
 Base caps: DZ_LTF_CAP / DZ_HTF_CAP env = 100000 (config.py LTF_BASE_CAP 5 / HTF_BASE_CAP 5 untouched). Internal scan limit of 80 candles in base_candles.MAX_SCAN stays.
EXPERIMENT SWITCHES: (a) caps removed; (b) exciting 1.3 -> 1.15 ATR and 25% -> 30% (HTF and LTF); (c) HTF wick-freshness is not a filter (feeds the freshness score; flag recorded);
 (d) Rule 1 (LTF legout must close beyond legin) OFF.
STILL ON: trend filter at HTF formation (3-timeframe, blocks only confirmed counter-trend), trend re-check at entry, V2 base logic (base = not impulsive and (wick>50% of body or body<=0.5 ATR),
 range<=2.5 ATR), duplicate-zone drop, HTF legout closes over the base wick, base-to-leg range limits (HTF 1.25, LTF 0.6), HTF base extension 0.4 ATR, LTF lines from the nearest 3 base candles,
 min zone width 0.5 ATR (MIT HTF 0.4), clean-departure test, distal buffer 0.1 ATR, LTF zone must form inside the HTF formation window and be untested at HTF confirmation, LTF/HTF overlap >= 30%,
 max leg candles (HTF 3, LTF 2), one LTF zone per HTF zone (most recent), entry at first touch of the LTF proximal line (entry type 1), stop = LTF distal, target 2R, risk Rs 1,000, capital Rs 1,00,000,
 entries from 2024-01-01 (zones built from full history), Kite data only.
OTHER RULES YOU COULD LOOSEN NEXT: base-to-leg ratios, base-candle wick/body definition and 2.5 ATR range guard, min zone width, departure tolerance, distal buffer, 30% overlap, the
 'untested at HTF confirmation' LTF test, one-LTF-zone-per-HTF-zone, the trend filter at formation / entry, legout-over-wick, max leg candles."""


def do_signals():
    import multiprocessing as mp
    OUT.mkdir(parents=True, exist_ok=True)
    allrows = {}
    for combo in ("mit", "wit"):
        d = CKPT / combo
        d.mkdir(parents=True, exist_ok=True)
        tick = _tickers(combo)
        done = {p.stem for p in d.glob("*.pkl")}
        todo = [t for t in tick if t.replace("&", "_AMP_") not in done]
        print(f"{combo}: {len(tick)} tickers with frames, {len(done)} checkpointed, {len(todo)} to run", flush=True)
        if todo:
            with mp.Pool(3, initializer=_init, initargs=(combo,)) as pool:
                for k, (t, rows) in enumerate(pool.imap_unordered(build_signals, [(combo, t) for t in todo], chunksize=1), 1):
                    pickle.dump(rows, open(d / f"{t.replace('&', '_AMP_')}.pkl", "wb"))
                    if k % 50 == 0:
                        print(f"  {combo} {k}/{len(todo)} tickers", flush=True)
        rows = []
        for t in tick:
            rows += pickle.load(open(d / f"{t.replace('&', '_AMP_')}.pkl", "rb"))
        df = pd.DataFrame(rows).sort_values(["entry_time", "ticker"]).reset_index(drop=True)
        df["split"] = np.where(df["entry_time"] < SPLIT, "train", "holdout")
        df.to_csv(OUT / f"signals_{combo}_heuristic.csv", index=False)
        allrows[combo] = df
        print(f"{combo}: {len(df)} signals, {df.ticker.nunique()} tickers; saved signals_{combo}_heuristic.csv")
        print(f"  freshness (visits) distribution: touches 0 -> 3.0: {(df.freshness == 3).sum()}, 1 -> 1.5: {(df.freshness == 1.5).sum()}, >=2 -> 0: {(df.freshness == 0).sum()}")
        print(f"  strength: 2 -> {(df.strength == 2).sum()}, 1 -> {(df.strength == 1).sum()}, 0 -> {(df.strength == 0).sum()}")
        bc_ = df.ltf_base_count.value_counts().sort_index()
        print("  LTF base count distribution: " + ", ".join(f"{k}:{v}" for k, v in bc_.items()))
        print(f"  share with <= 5 LTF base candles: {100 * (df.ltf_base_count <= 5).mean():.1f}%" + ("   (> 90%: the base walk-back may be stopping early; full_run_base NOT run)" if (df.ltf_base_count <= 5).mean() > 0.9 else ""))
        print("  total score distribution: " + ", ".join(f"{k}:{v}" for k, v in df.total.value_counts().sort_index().items()))
        print(f"  share the old rules would have rejected: wick-freshness {100 * df.legacy_wick_freshness_would_reject.mean():.0f}%, Rule 1 {100 * df.rule1_would_reject.mean():.0f}%, "
              f"old exciting test {100 * df.old_exciting_would_reject.mean():.0f}%, cap-5 {100 * df.cap5_would_reject.mean():.0f}%, ANY of the four "
              f"{100 * (df.legacy_wick_freshness_would_reject | df.rule1_would_reject | df.old_exciting_would_reject | df.cap5_would_reject).mean():.0f}%")


def do_score():
    sys.path.insert(0, str(ROOT / "scripts"))
    import replay_common as rc
    for combo in ("mit", "wit"):
        src = OUT / f"signals_{combo}_heuristic.csv"
        out = OUT / f"signals_{combo}_scored.csv"
        rc.run(combo, src, out, f"TRADESCORE {combo.upper()} 2024+")


def _final(d):
    rep = d["exit_outcome"].isin(["win", "loss"])
    heur = d["outcome"].where(d["outcome"].isin(["win", "loss"]))
    d["outcome_final"] = np.where(rep, d["exit_outcome"], np.where(d["exit_outcome"] == "AMBIGUOUS", heur.fillna("UNRESOLVED"), d["exit_outcome"]))
    d["outcome_source"] = np.where(rep, d["exit_interval"].astype(str), np.where((d["exit_outcome"] == "AMBIGUOUS") & heur.notna(), "heuristic", "unresolved"))
    d["r_final"] = np.where(rep, d["exit_r"], np.where((d["exit_outcome"] == "AMBIGUOUS") & heur.notna(), np.where(heur == "win", 2.0, -1.0), np.nan))
    d["pnl_final"] = d["r_final"] * d["shares"] * d["risk"]
    d["win_final"] = (d["outcome_final"] == "win").astype(int)
    return d


def _ci(x, reps=4000, seed=12345):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return "n/a"
    b = np.random.default_rng(seed).choice(x, (reps, len(x))).mean(1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    return f"{100 * lo:.0f}-{100 * hi:.0f}"


def _row(label, s, base_rate=None):
    n = len(s)
    if n == 0:
        return f"{label:26} n=  0"
    res = s[s.outcome_final.isin(["win", "loss"])]
    w, l = int((res.outcome_final == "win").sum()), int((res.outcome_final == "loss").sum())
    amb = int((s.exit_outcome == "AMBIGUOUS").sum())
    rr = s[s.exit_outcome.isin(["win", "loss"])]
    wr_res = 100 * (rr.exit_outcome == "win").mean() if len(rr) else float("nan")
    aw = int((s.exit_outcome == "win").sum()); den = aw + int((s.exit_outcome == "loss").sum()) + amb
    wr_al = 100 * aw / den if den else float("nan")
    wr = 100 * w / (w + l) if w + l else float("nan")
    return (f"{label:26} n={n:3} W={w:3} L={l:3} amb={amb:2} win%final={wr:5.1f} [{_ci(res.win_final.values) if len(res) else 'n/a'}] resolved-only={wr_res:5.1f} amb-as-loss={wr_al:5.1f} "
            f"avgR={res.r_final.mean() if len(res) else float('nan'):+.3f} Rs={res.pnl_final.sum():+,.0f}" + ("  SAMPLE<30" if n < 30 else ""))


def _tables(name, d, lines):
    lines.append(f"\n##### {name}: {len(d)} signals, {d.ticker.nunique()} tickers #####")
    lines.append(f"legacy rules would have rejected: wick-freshness {int(d.legacy_wick_freshness_would_reject.sum())} ({100 * d.legacy_wick_freshness_would_reject.mean():.0f}%), Rule 1 {int(d.rule1_would_reject.sum())}, "
                 f"old exciting {int(d.old_exciting_would_reject.sum())}, cap-5 {int(d.cap5_would_reject.sum())}, any {int((d.legacy_wick_freshness_would_reject | d.rule1_would_reject | d.old_exciting_would_reject | d.cap5_would_reject).sum())} "
                 f"({100 * (d.legacy_wick_freshness_would_reject | d.rule1_would_reject | d.old_exciting_would_reject | d.cap5_would_reject).mean():.0f}%)")
    unres = int((~d.outcome_final.isin(["win", "loss"])).sum())
    lines.append(f"unresolved (neither replay nor heuristic gives win/loss): {unres}")
    all_wr = d.win_final[d.outcome_final.isin(["win", "loss"])].mean()
    tr, ho = d[d.entry_time < SPLIT], d[d.entry_time >= SPLIT]

    def cons(s):
        rs = {}
        for nm, part, ref in (("train", tr, tr), ("holdout", ho, ho)):
            sub = s[s.entry_time < SPLIT] if nm == "train" else s[s.entry_time >= SPLIT]
            rr, ra = sub[sub.outcome_final.isin(["win", "loss"])], ref[ref.outcome_final.isin(["win", "loss"])]
            rs[nm] = (len(sub), (rr.win_final.mean() if len(rr) else np.nan), (ra.win_final.mean() if len(ra) else np.nan))
        ok = all(rs[k][0] >= 15 for k in rs) and not any(np.isnan(rs[k][1]) for k in rs) and \
            ((rs["train"][1] > rs["train"][2]) == (rs["holdout"][1] > rs["holdout"][2])) and rs["train"][1] != rs["train"][2] and rs["holdout"][1] != rs["holdout"][2]
        return f"  CONSISTENT={'YES' if ok else 'no'} (train n={rs['train'][0]} {100 * rs['train'][1]:.0f}% vs all {100 * rs['train'][2]:.0f}%; holdout n={rs['holdout'][0]} {100 * rs['holdout'][1]:.0f}% vs all {100 * rs['holdout'][2]:.0f}%)"

    lines.append("\n-- BY TOTAL SCORE")
    low = d[d.total < 4]
    lines.append(_row("score < 4", low) + cons(low))
    for v in sorted(d.total[d.total >= 4].unique()):
        s = d[d.total == v]
        lines.append(_row(f"score = {v}", s) + cons(s))
    lines.append("\n-- CUMULATIVE THRESHOLDS")
    prev = None
    for lab, m in (("all signals", d.total >= -1), (">= 4", d.total >= 4), (">= 5", d.total >= 5), (">= 5.5", d.total >= 5.5), (">= 6", d.total >= 6), (">= 6.5", d.total >= 6.5), ("= 7", d.total >= 7)):
        s = d[m]
        extra = "  NO CHANGE: the rule did not fire" if (lab != "all signals" and len(s) == len(d)) else ""
        lines.append(_row(lab, s) + (cons(s) if lab != "all signals" else "") + extra)
    lines.append("\n-- BY COMPONENT")
    for col, vals in (("freshness", (3.0, 1.5, 0.0)), ("strength", (2, 1)), ("base_time", (2, 1, 0))):
        for v in vals:
            s = d[d[col] == v]
            lines.append(_row(f"{col} = {v}", s) + cons(s))
    lines.append("\n-- BY YEAR / TRAIN vs HOLDOUT (all signals, and >= 5)")
    for lab, m in (("all", d.total >= -1), (">= 5", d.total >= 5)):
        s = d[m]
        for y in (2024, 2025, 2026):
            lines.append(_row(f"{lab} year {y}", s[s.entry_time.dt.year == y]))
        lines.append(_row(f"{lab} TRAIN (<2026)", s[s.entry_time < SPLIT]))
        lines.append(_row(f"{lab} HOLDOUT (2026)", s[s.entry_time >= SPLIT]))
    r = d[d.outcome_final.isin(["win", "loss"])].reset_index(drop=True)
    rng = np.random.default_rng(7)
    sel = (r.total >= 5).values
    w = r.win_final.values
    ds = []
    for _ in range(4000):
        ix = rng.integers(0, len(r), len(r))
        ww, ss = w[ix], sel[ix]
        if ss.sum() == 0:
            continue
        ds.append(ww[ss].mean() - ww.mean())
    if ds and sel.sum():
        lines.append(f"win% difference (>= 5 minus all): {100 * (w[sel].mean() - w.mean()):+.1f} pts, bootstrap 95% [{100 * np.percentile(ds, 2.5):+.0f}, {100 * np.percentile(ds, 97.5):+.0f}]")
    # counts must add up
    lines.append(f"counts add up: score rows {len(low) + int((d.total >= 4).sum())} of {len(d)}; years {sum(int((d.entry_time.dt.year == y).sum()) for y in (2024, 2025, 2026))} of {len(d)}; train+holdout {len(tr) + len(ho)} of {len(d)}")


def _overlap(name, d, lines):
    def keys(df):
        return set(zip(df.ticker, pd.to_datetime(df.entry_time).dt.normalize()))
    k = keys(d)
    for lab, f in ((f"cap-5 candidate ({name} 2024+, results/c0b74c8)", ROOT / "results" / "c0b74c8" / f"trades_{name.lower()}_kite_2024_newbase_cap5_final.csv"),
                   (f"Baseline v1 ({name}, results/53aecde)", ROOT / "results" / "53aecde" / f"baseline_v1_{name.lower()}.csv")):
        o = pd.read_csv(f, parse_dates=["entry_time"])
        ko = keys(o)
        lines.append(f"overlap with {lab}: {len(ko)} trades there; in both {len(k & ko)}, only here {len(k - ko)}, only there {len(ko - k)}")


def do_report():
    lines, ds = [], {}
    for combo in ("mit", "wit"):
        d = _final(pd.read_csv(OUT / f"signals_{combo}_scored.csv", parse_dates=["entry_time", "exit_time", "htf_formed_at", "ltf_formed_at"]))
        keep = ["ticker", "type", "htf_proximal", "htf_distal", "ltf_proximal", "ltf_distal", "entry_price", "stop", "target", "entry_time", "exit_time", "freshness", "strength", "base_time", "total",
                "htf_touches", "ltf_base_count", "htf_strength", "htf_base_count", "htf_base_time", "ema_flag", "legacy_wick_freshness_would_reject", "rule1_would_reject", "old_exciting_would_reject",
                "cap5_would_reject", "outcome_final", "outcome_source", "r_final", "pnl_final", "exit_outcome", "exit_interval", "split"]
        d[keep].to_csv(OUT / f"tradescore_{combo}_all_signals.csv", index=False)
        rv = d[keep].copy()
        rv["my_verdict"] = ""
        rv.to_csv(OUT / f"review_tradescore_{combo}.csv", index=False)
        ds[combo] = d
    ds["pooled"] = pd.concat([ds["mit"], ds["wit"]], ignore_index=True)
    lines.append("BASELINES USED FOR OVERLAP: cap-5 candidate = results/c0b74c8 (MIT 18, WIT 58); Baseline v1 = results/53aecde (MIT 24, WIT 63).")
    for name in ("mit", "wit", "pooled"):
        _tables(name.upper(), ds[name], lines)
        if name != "pooled":
            _overlap(name.upper(), ds[name], lines)
    txt = "\n".join(lines)
    (OUT / "report.txt").write_text(txt, encoding="utf-8")
    print(txt)


def do_sanity():
    """Untouched baseline path: legacy modules, no base_candles.install, no overrides. Expected MIT 24 / 41.7%, WIT 63 / 41.3% (2024+)."""
    import multiprocessing as mp
    res = {}
    for combo in ("mit", "wit"):
        tick = _tickers_plain(combo)
        with mp.Pool(3, initializer=_init_plain, initargs=(combo,)) as pool:
            rows = [r for part in pool.imap_unordered(_work_plain, [(combo, t) for t in tick], chunksize=1) for r in part]
        d = pd.DataFrame(rows)
        d["entry_time"] = pd.to_datetime(d["entry_time"])
        d = d[d.entry_time >= ENTRY_FROM]
        b = pd.read_csv(ROOT / "results" / "53aecde" / f"baseline_v1_{combo}.csv", parse_dates=["entry_time"])
        kb = {(t, e.normalize()): o for t, e, o in zip(b.ticker, b.entry_time, b.outcome_final)}
        kd = {(t, e.normalize()) for t, e in zip(d.ticker, d.entry_time)}
        wins = sum(1 for k in kd if kb.get(k) == "win")
        res[combo] = (len(d), len(kd & set(kb)), wins)
        hw = int((d.outcome == "win").sum()); hl = int((d.outcome == "loss").sum())
        print(f"{combo.upper()} untouched baseline path, 2024+: n={len(d)} (Baseline v1 file has {len(b)}); in both {len(kd & set(kb))}; "
              f"win% using Baseline v1 final outcomes on these trades = {100 * wins / len(d):.1f}% ({wins}/{len(d)}); heuristic-only win% {100 * hw / (hw + hl):.1f}%")


def _tickers_plain(combo):
    import json
    t = [x for x in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if x not in SKIP]
    fr = ROOT / "data" / "cache" / "kite_frames"
    need = ["1d"] + (["60m"] if combo == "wit" else [])
    return [x for x in t if all((fr / f"{x}__{n}.csv").exists() for n in need)]


def _init_plain(combo):
    _low_priority()
    global bt
    sys.path.insert(0, str(LEGACY / "code"))
    import offline_loader
    offline_loader.install(data_dir=str(ROOT / "data" / "cache" / "kite_frames"))
    import mtf_backtest as _t
    bt = _t


def _work_plain(a):
    combo, t = a
    try:
        return bt.build_trades_for_ticker(t, combo, apply_trend_filter=True)
    except Exception:
        return []


if __name__ == "__main__":
    {"profile": do_profile, "signals": do_signals, "score": do_score, "report": do_report, "sanity": do_sanity}[STEP]()
