"""DIT15 candidate generator (Phase A, A1-A4, A6, A11): one code path for the strict baseline (B0) and the relaxed pool.

Zone detection, zone construction and HTF/LTF matching are the legacy code, imported unchanged (sd_zones + mtf_zones, with the
V2 base logic of src/base_candles.py). This module only re-orchestrates legacy mtf_backtest.build_trades_for_ticker so that:
  1. every decision is taken at an explicit time (T_H = HTF leg-end close, T_d = start of the 15m entry bar) using only bars
     closed by then (switches in Mode; Mode LEGACY reproduces the old pipeline exactly, which tests/test_phase_a.py checks
     against the 4d02f6d checkpoints);
  2. one pass yields both the strict B0 trades (every legacy filter applied) and the relaxed pool (former filters recorded as
     flags instead of rejecting).

DIT15 rule set = the 4d02f6d run (docs/STATUS.md sec. 9): HTF daily (WEEKLY_CONFIG + V2, cap 5, legout over base wick,
strict HTF legout 1.35 ATR / outer 22 %), trend 2h from 60m (TREND_ZONE_CONFIG, legacy), LTF 15m (LTF_ENTRY_CONFIG + V2, cap 5).

Relaxed pool (A11): hard rules kept = zone detection/construction (incl. Rule 1 legout beyond legin, HTF legout over base wick,
min width, clean departure, base/leg ratios) and matching (formation window, untested at HTF confirm, 30 % overlap, most recent
candidate). Recorded as flags instead of rejecting: trend at HTF formation, trend at entry, HTF wick-freshness, strict-HTF
legout, HTF base cap 5, LTF base cap 5.
"""
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LEGACY_CODE = ROOT / "legacy" / "handoff" / "handoff" / "code"
FRAMES = ROOT / "data" / "cache" / "kite_frames_dit15_long"
NOCAP = 10 ** 6
for _p in (str(ROOT), str(ROOT / "src"), str(LEGACY_CODE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bars as B  # noqa: E402
import corp_actions as CA  # noqa: E402
import replay as RP  # noqa: E402
from trend_pit import TrendContext, blocks  # noqa: E402


@dataclass(frozen=True)
class Mode:
    pit_trend: bool = True    # A1: trend events at bar close, queries use closed bars only
    session_2h: bool = True   # A2: 2h bars anchored at 09:15
    ath_full: bool = True     # A3: ATH against all closes known at T (daily history too)
    ca_reset: bool = True     # A6: trend/ATH ignore prices before a flagged corporate-action day
    name: str = "pit"
    # Trend check "at HTF formation": legacy queried at the HTF bar's LABEL (midnight of the leg-end day), i.e. with information
    # up to the previous day's close: stale by one day but NOT a leak. Querying at T_H (15:30 of the leg-end day) adds the
    # legout day's own 2h bars and changes which trades pass (sample of 40 tickers: +9 of 27 B0 trades). That is a strategy
    # change, not a leakage fix, so the default keeps the legacy timing; --formation-at-close runs the T_H variant (user decision).
    formation_at_close: bool = False


LEGACY = Mode(False, False, False, False, "legacy")
PIT = Mode()

_E = None


class _Engine:
    pass


def engine():
    """Import the legacy engine once per process and build the configs (same objects the 4d02f6d run used)."""
    global _E
    if _E is not None:
        return _E
    for k in ("DZ_LTF_CAP", "DZ_HTF_CAP"):
        os.environ.pop(k, None)
    os.environ["DZ_BASE_LOGIC_V2"] = "1"
    os.environ["DZ_HTF_LEGOUT_WICK"] = "1"
    import offline_loader  # legacy; only used to stub yfinance so mtf_zones imports offline
    offline_loader.install(data_dir=str(FRAMES))
    import mtf_zones as mtz
    import sd_zones as sz
    import base_candles as bc
    import config as C
    bc.install(sz, mtz, combos=())
    E = _Engine()
    E.mtz, E.sz, E.bc, E.C = mtz, sz, bc, C
    os.environ["DZ_STRICT_HTF"] = "1"
    E.htf_strict = bc.new_base_config(mtz.WEEKLY_CONFIG, "htf")
    os.environ["DZ_STRICT_HTF"] = "0"
    E.htf_loose = bc.new_base_config(mtz.WEEKLY_CONFIG, "htf")
    E.ltf = bc.new_base_config(mtz.LTF_ENTRY_CONFIG, "ltf")
    E.htf_strict_nocap = _with_cap(E.htf_strict, NOCAP)
    E.htf_loose_nocap = _with_cap(E.htf_loose, NOCAP)
    E.ltf_nocap = _with_cap(E.ltf, NOCAP)
    E.trend = mtz.TREND_ZONE_CONFIG
    E.ltf_cap = E.ltf.max_base_candles
    E.htf_cap = E.htf_strict.max_base_candles
    _E = E
    return E


def _with_cap(cfg, cap):
    out = replace(cfg, max_base_candles=cap)
    for a in ("new_base", "legout_beyond_base_wick", "line_candles"):
        setattr(out, a, getattr(cfg, a))
    return out


def load_frames(ticker, frames_dir=FRAMES):
    return {iv: B.load_frame(frames_dir, ticker, iv) for iv in ("1d", "60m", "15m")}


def detect_raw(E, df, atr, cfg, wtw):
    """sd_zones.detect_zones without the V2 de-duplication, with a precomputed ATR (same result, ATR computed once)."""
    z = (E.sz._detect_zones_one_direction(df, atr, "demand", cfg, wtw)
         + E.sz._detect_zones_one_direction(df, atr, "supply", cfg, wtw))
    z.sort(key=lambda q: q.leg_start_index)
    return z


def dedupe_earliest(zones):
    """Same rule as base_candles._dedupe: identical (type, lines) from adjacent legouts -> keep the earliest."""
    seen, out = set(), []
    for z in sorted(zones, key=lambda q: q.leg_start_index):
        k = (z.type, round(z.proximal_line, 6), round(z.distal_line, 6))
        if k not in seen:
            seen.add(k)
            out.append(z)
    return out


def zkey(z):
    return (z.type, z.base_start_index, z.base_end_index, z.leg_start_index, z.leg_end_index)


class _LtfIndex:
    """LTF zones of one type in legacy order, with formation dates for window lookups."""

    def __init__(self, zones, ts15):
        self.zones = zones
        self.fd = np.array([ts15[z.leg_end_index] for z in zones], dtype="datetime64[ns]").astype("datetime64[D]")


def _best_ltf(E, hz, d1_ts, idx, ts15, day15):
    """legacy mtf_zones.match_zones candidate selection for one HTF zone (conditions 1-4); returns (zone, overlap) or None."""
    h_lo, h_hi = min(hz.proximal_line, hz.distal_line), max(hz.proximal_line, hz.distal_line)
    ws = d1_ts[hz.base_start_index].astype("datetime64[D]")
    we = d1_ts[hz.leg_end_index].astype("datetime64[D]")
    j = int(np.searchsorted(day15, we, side="right")) - 1
    cutoff = ts15[j] if j >= 0 else we.astype("datetime64[ns]")
    i0, i1 = int(np.searchsorted(idx.fd, ws, side="left")), int(np.searchsorted(idx.fd, we, side="right"))
    cands = []
    for z in idx.zones[i0:i1]:
        lo, hi = min(z.proximal_line, z.distal_line), max(z.proximal_line, z.distal_line)
        hgt = hi - lo
        if hgt <= 0:
            continue
        if z.tested_at_timestamp is not None and np.datetime64(pd.Timestamp(z.tested_at_timestamp)) <= cutoff:
            continue
        frac = (min(h_hi, hi) - max(h_lo, lo)) / hgt
        if frac < E.mtz.MIN_LTF_OVERLAP_FRAC:
            continue
        cands.append((frac, ts15[z.leg_end_index], z))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[1], c[0]), reverse=True)
    return cands[0][2], cands[0][0]


class TickerContext:
    """Everything the decisions of one ticker need, built from frames (so tests can pass truncated/perturbed frames)."""

    def __init__(self, ticker, frames, mode=PIT):
        E = engine()
        self.E, self.ticker, self.mode = E, ticker, mode
        d1, h60, m15 = frames["1d"], frames["60m"], frames["15m"]
        self.d1, self.h60, self.m15 = d1, h60, m15
        self.ok = len(d1) >= 20 and len(m15) >= 20
        if not self.ok:
            return
        sz = E.sz
        self.ca = CA.flag_days(d1)
        # --- trend frame and classifier
        ohlc = ["timestamp", "open", "high", "low", "close"]
        if mode.session_2h:
            tdf = B.resample_2h_session(h60)
        else:
            tdf = B.resample_2h_legacy(h60)
        self.tdf = tdf
        self.trend_ok = len(tdf) >= 20
        if self.trend_ok:
            if mode.pit_trend:
                tz = detect_raw(E, tdf, sz.wilder_atr(tdf), E.trend, False)
                self.tctx = TrendContext(tdf, tz, daily=d1, ca_flags=self.ca, ath_full=mode.ath_full, ca_reset=mode.ca_reset)
                self.classify = self.tctx.classify
            else:
                t_l = tdf[ohlc].reset_index(drop=True)
                tz = E.mtz.detect_zones(t_l, config=E.trend, allow_wick_to_wick=False)
                ev = E.mtz._compute_trend_events(t_l, tz)
                self.classify = lambda t, _df=t_l, _ev=ev: E.mtz._classify_trend_from_events(_df, _ev, t)
        # --- HTF zone sets (daily)
        atr_d = sz.wilder_atr(d1)
        self.atr_d = atr_d
        self.htf_b0 = dedupe_earliest(detect_raw(E, d1, atr_d, E.htf_strict, False))
        self.htf_rel = dedupe_earliest(detect_raw(E, d1, atr_d, E.htf_loose_nocap, False))
        self.htf_strict_keys = {zkey(z) for z in detect_raw(E, d1, atr_d, E.htf_strict_nocap, False)}
        self.htf_b0_keys = {zkey(z) for z in self.htf_b0}
        # --- LTF zone sets (15m): one detection without the cap; the capped set is the same zones with count <= cap
        atr15 = sz.wilder_atr(m15)
        raw = detect_raw(E, m15, atr15, E.ltf_nocap, True)
        self.ltf_count = {id(z): len(E.bc.base_run(m15, atr15, z.leg_start_index, E.ltf, sz)) for z in raw}
        self.ltf_b0 = dedupe_earliest([z for z in raw if self.ltf_count[id(z)] <= E.ltf_cap])
        self.ltf_rel = dedupe_earliest(raw)
        self.d1_ts = d1["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.d1_ct = d1["close_time"].to_numpy(dtype="datetime64[ns]")
        self.ts15 = m15["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.ct15 = m15["close_time"].to_numpy(dtype="datetime64[ns]")
        self.day15 = self.ts15.astype("datetime64[D]")
        self.idx_b0 = {t: _LtfIndex([z for z in self.ltf_b0 if z.type == t], self.ts15) for t in ("demand", "supply")}
        self.idx_rel = {t: _LtfIndex([z for z in self.ltf_rel if z.type == t], self.ts15) for t in ("demand", "supply")}

    # decisions -----------------------------------------------------------------------------------------------
    def t_formation(self, hz):
        """Query time of the trend check at HTF formation: the HTF bar label (midnight: information through the previous day's
        close; with pit_trend only closed bars are used) unless mode.formation_at_close, then T_H (15:30 of the leg-end day)."""
        if self.mode.pit_trend and self.mode.formation_at_close:
            return self.d1_ct[hz.leg_end_index]
        return self.d1_ts[hz.leg_end_index]

    def trend_at(self, t):
        return self.classify(pd.Timestamp(t)) if self.trend_ok else None

    def wick_fail(self, hz, entry_ts):
        """Legacy rule R10 (mtf_zones._htf_wick_tested_at): an earlier daily bar (date < entry date) reached the base wick."""
        wt = self.E.mtz._htf_wick_tested_at(self.d1, hz)
        return bool(wt is not None and pd.Timestamp(wt).normalize() < pd.Timestamp(entry_ts).normalize())

    def htf_count(self, hz):
        """Base-run length under the strict B0 HTF config (the definition the cap-5 rule uses)."""
        return len(self.E.bc.base_run(self.d1, self.atr_d, hz.leg_start_index, self.E.htf_strict, self.E.sz))


def _trade_row(ctx, hz, lz, frac):
    E = ctx.E
    entry_idx = lz.tested_at_index
    entry_price, stop = lz.proximal_line, lz.distal_line
    risk = abs(entry_price - stop)
    if risk <= 0:
        return None
    shares = min(int(1000.0 // risk), int(100000.0 // entry_price))
    if shares <= 0:
        return None
    target = entry_price + 2.0 * risk if hz.type == "demand" else entry_price - 2.0 * risk
    entry_ts = pd.Timestamp(ctx.ts15[entry_idx])
    return dict(
        ticker=ctx.ticker, combo="dit15", type=hz.type,
        htf_proximal=hz.proximal_line, htf_distal=hz.distal_line,
        htf_base_start=pd.Timestamp(ctx.d1_ts[hz.base_start_index]),
        htf_formed_at=pd.Timestamp(ctx.d1_ts[hz.leg_end_index]), T_H=pd.Timestamp(ctx.d1_ct[hz.leg_end_index]),
        htf_key=zkey(hz)[1:], ltf_key=zkey(lz)[1:],
        ltf_formed_at=pd.Timestamp(ctx.ts15[lz.leg_end_index]), T_L=pd.Timestamp(ctx.ct15[lz.leg_end_index]),
        entry_time=entry_ts, entry_price=entry_price, stop=stop, target=target, risk=risk, shares=shares,
        overlap_frac=frac, ltf_risk_pct=risk / entry_price * 100,
        htf_risk_pct=abs(hz.proximal_line - hz.distal_line) / max(hz.proximal_line, hz.distal_line) * 100,
        htf_strong_legout=hz.has_strong_legout, ltf_strong_legout=lz.has_strong_legout,
        ltf_base_count=ctx.ltf_count.get(id(lz)), htf_base_count=ctx.htf_count(hz),
    )


def b0_trades(ctx):
    """Strict B0: legacy build_trades_for_ticker logic (all filters reject), at the times defined by ctx.mode."""
    if not ctx.ok or not ctx.trend_ok:
        return []
    out = []
    for hz in ctx.htf_b0:
        tr = ctx.trend_at(ctx.t_formation(hz))
        if tr is None or blocks(hz.type, tr):
            continue
        m = _best_ltf(ctx.E, hz, ctx.d1_ts, ctx.idx_b0[hz.type], ctx.ts15, ctx.day15)
        if m is None or m[0].tested_at_index is None:
            continue
        lz, frac = m
        entry_ts = ctx.ts15[lz.tested_at_index]
        if ctx.wick_fail(hz, entry_ts):
            continue
        te = ctx.trend_at(entry_ts)
        if te is not None and blocks(hz.type, te):
            continue
        row = _trade_row(ctx, hz, lz, frac)
        if row:
            row.update(trend_htf=tr, trend_entry=te, trend_htf_time=pd.Timestamp(ctx.t_formation(hz)))
            out.append(row)
    return out


def relaxed_candidates(ctx):
    """Relaxed pool: same structure, former filters recorded as flags (A11)."""
    if not ctx.ok:
        return []
    out = []
    for hz in ctx.htf_rel:
        m = _best_ltf(ctx.E, hz, ctx.d1_ts, ctx.idx_rel[hz.type], ctx.ts15, ctx.day15)
        if m is None or m[0].tested_at_index is None:
            continue
        lz, frac = m
        row = _trade_row(ctx, hz, lz, frac)
        if not row:
            continue
        entry_ts = ctx.ts15[lz.tested_at_index]
        tr = ctx.trend_at(ctx.t_formation(hz))
        te = ctx.trend_at(entry_ts)
        row.update(trend_htf=tr, trend_entry=te, trend_htf_time=pd.Timestamp(ctx.t_formation(hz)))
        out.append(row)
    return out


def flags(ctx, row):
    """Former filters as flags (True = the strict pipeline would reject on this rule)."""
    E = ctx.E
    hk = ("demand" if row["type"] == "demand" else "supply",) + tuple(row["htf_key"])
    tr, te = row["trend_htf"], row["trend_entry"]
    return dict(
        trend_htf_fail=bool(tr is None or blocks(row["type"], tr)),
        trend_entry_fail=bool(te is not None and blocks(row["type"], te)),
        wick_fresh_fail=row["_wick_fail"],
        htf_strict_fail=hk not in ctx.htf_strict_keys,
        htf_cap_fail=bool(row["htf_base_count"] > E.htf_cap),
        ltf_cap_fail=bool(row["ltf_base_count"] is not None and row["ltf_base_count"] > E.ltf_cap),
        htf_in_b0_set=hk in ctx.htf_b0_keys,
    )


def build(ticker, frames=None, mode=PIT, entry_from=None, do_replay=True):
    """All candidate rows for one ticker: relaxed pool union B0, flags, outcome. One row per (HTF zone, LTF zone)."""
    frames = frames if frames is not None else load_frames(ticker)
    ctx = TickerContext(ticker, frames, mode)
    if not ctx.ok:
        return []
    rows = {}
    for r in relaxed_candidates(ctx):
        r["relaxed_selected"], r["is_b0"] = True, False
        rows[(r["type"], r["htf_key"], r["ltf_key"])] = r
    for r in b0_trades(ctx):
        k = (r["type"], r["htf_key"], r["ltf_key"])
        if k in rows:
            rows[k]["is_b0"] = True
        else:
            r["relaxed_selected"], r["is_b0"] = False, True
            rows[k] = r
    out = sorted(rows.values(), key=lambda r: (r["entry_time"], r["htf_formed_at"], r["type"]))
    hz_by_key = {}
    for z in ctx.htf_rel + ctx.htf_b0:
        hz_by_key.setdefault(zkey(z), z)
    for r in out:
        hz = hz_by_key[(r["type"],) + tuple(r["htf_key"])]
        r["_wick_fail"] = ctx.wick_fail(hz, r["entry_time"])
        r.update(flags(ctx, r))
        del r["_wick_fail"]
        r["mode"] = mode.name
    if entry_from is not None:
        out = [r for r in out if r["entry_time"] >= pd.Timestamp(entry_from)]
    if do_replay:
        _replay_all(ctx, out)
    return out


def _replay_all(ctx, rows):
    if not rows:
        return
    arr = RP.arrays(ctx.m15)
    inc = B.intraday_incomplete_days(ctx.m15, ctx.d1)
    dhl = {pd.Timestamp(t).normalize(): (h, l) for t, h, l in zip(ctx.d1["timestamp"], ctx.d1["high"], ctx.d1["low"])}
    data_end = ctx.ct15[-1]
    minute = None
    for r in rows:
        tr = dict(type=r["type"], entry_price=r["entry_price"], stop=r["stop"], target=r["target"], risk=r["risk"],
                  scan_start=r["entry_time"])
        res = RP.replay(arr, tr, minute=None, incomplete_days=inc, daily_hl=dhl, data_end=data_end)
        if res["outcome"] == RP.AMBIGUOUS and res["reason"].startswith("MINUTE_NOT_CACHED"):
            if minute is None:
                minute = RP.MinuteCache(ctx.ticker)
            res = RP.replay(arr, tr, minute=minute, incomplete_days=inc, daily_hl=dhl, data_end=data_end)
        r.update({f"exit_{k}" if k in ("reason",) else k: v for k, v in res.items()})
        r["r_gross"] = res["r"]
        end = res["exit_time"] if res["exit_time"] is not None else \
            pd.Timestamp(r["entry_time"]).normalize() + pd.Timedelta(days=RP.HORIZON_DAYS)
        r["ca_excluded"] = CA.window_has_flag(ctx.ca, r["htf_base_start"] - pd.Timedelta(days=CA.CA_PAD_DAYS), end)
