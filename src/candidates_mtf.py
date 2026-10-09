"""WIT / MIT strict (B0) candidate generator: the DIT15 Phase A methodology applied to the weekly and monthly combos.

Zone detection, zone construction and HTF/LTF matching are the legacy code (src/candidates.py helpers, imported unchanged). This
module re-orchestrates legacy mtf_backtest.build_trades_for_ticker with explicit decision times:
  WIT  HTF weekly (resampled from daily), trend daily, LTF 2h (from 60m)      decision time T_d = start of the entry 2h bar
  MIT  HTF monthly (resampled from daily), trend weekly, LTF daily            decision time T_d = entry day 09:15
Hardening switches (Mode flags; LEGACY = all off = the pre-hardening pipeline, validated against the stored 2021+ results):
  pit_trend    trend events stamped at the breaking bar's CLOSE, queries use bars closed by the query time (legacy: bar labels,
               `timestamp <= query`, so WIT's daily trend bar of the entry day and its zone breaks were visible at the entry)
  session_2h   WIT's 2h LTF bars anchored at 09:15 (legacy: clock-hour bins 08:00/10:00/...)
  ath_full     all-time-high override over every close known at T (legacy: the trimmed trend frame)
  ca_reset     trend / ATH ignore prices before a flagged corporate-action day
  fixed_start  no end-anchored windows (legacy: WIT weekly HTF last 400 bars, MIT weekly trend last 400 bars; the 2021 runs already
               lifted WIT's daily-trend and MIT's daily-LTF windows)
Unchanged on purpose (strategy rules): the trend check at HTF formation is queried at the HTF bar LABEL (Sunday / month-end
midnight), exactly as in the legacy code and in DIT15 (decision D1); HTF wick-freshness (date < entry date); entry at the LTF
proximal on first touch; stop at the distal; 2:1 target; sizing; 90-day replay horizon; no time exit.
Only the strict B0 list is produced (no relaxed pool for WIT / MIT).
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import bars as B  # noqa: E402
import candidates as CD  # noqa: E402
import corp_actions as CA  # noqa: E402
import htf_bars as HB  # noqa: E402
import replay_context as RC  # noqa: E402
from trend_pit import TrendContext, blocks  # noqa: E402

FRAMES = CD.FRAMES  # data/cache/kite_frames_dit15_long: 1d, 60m, 15m for the whole universe (identical to the WIT / MIT frames)
OHLC = ["timestamp", "open", "high", "low", "close"]
SESSION_OPEN = pd.Timedelta(hours=9, minutes=15)
SPECS = {
    "wit": dict(htf_rule="W", htf_window=400, trend="D", trend_window=None, ltf="2h", htf_cfg="weekly"),
    "mit": dict(htf_rule="ME", htf_window=None, trend="W", trend_window=400, ltf="D", htf_cfg="monthly"),
}


@dataclass(frozen=True)
class Mode:
    pit_trend: bool = True
    session_2h: bool = True
    ath_full: bool = True
    ca_reset: bool = True
    fixed_start: bool = True
    name: str = "pit"


LEGACY = Mode(False, False, False, False, False, "legacy")
PIT = Mode()


def load_frames(ticker, frames_dir=FRAMES):
    return {iv: B.load_frame(frames_dir, ticker, iv) for iv in ("1d", "60m", "15m")}


def _scan_start_legacy_wit(entry_label):
    """scripts/replay_common.scan_start for WIT: first 60m bar start (09:15 + k h) at or after the legacy 2h label."""
    day = entry_label.normalize()
    for k in range(7):
        s = day + SESSION_OPEN + pd.Timedelta(hours=k)
        if s >= entry_label:
            return s
    return day + pd.Timedelta(days=1) + SESSION_OPEN


class MtfContext:
    def __init__(self, ticker, frames, combo, mode=PIT):
        E = CD.engine()
        self.E, self.ticker, self.combo, self.mode = E, ticker, combo, mode
        sp = SPECS[combo]
        self.sp = sp
        d1, h60, m15 = frames["1d"], frames["60m"], frames["15m"]
        self.d1, self.m15 = d1, m15
        self.ok = len(d1) >= 20
        if not self.ok:
            return
        sz = E.sz
        win = (lambda df, n: df) if mode.fixed_start else HB.trim_last
        self.ca = CA.flag_days(d1)
        # ---- frames
        htf = win(HB.period_frame(d1, sp["htf_rule"]), sp["htf_window"])
        trend = d1 if sp["trend"] == "D" else HB.period_frame(d1, "W")
        trend = win(trend, sp["trend_window"])
        if sp["ltf"] == "2h":
            ltf = B.resample_2h_session(h60) if mode.session_2h else B.resample_2h_legacy(h60)
        else:
            ltf = d1
        self.htf, self.trend_df, self.ltf = htf.reset_index(drop=True), trend.reset_index(drop=True), ltf.reset_index(drop=True)
        self.ok = len(self.htf) >= 20 and len(self.ltf) >= 20
        self.trend_ok = len(self.trend_df) >= 20
        if not self.ok:
            return
        # ---- trend classifier
        if self.trend_ok:
            tdf = self.trend_df
            if mode.pit_trend:
                tz = CD.detect_raw(E, tdf, sz.wilder_atr(tdf), E.trend, False)
                ctx = TrendContext(tdf, tz, daily=d1, ca_flags=self.ca, ath_full=mode.ath_full, ca_reset=mode.ca_reset)
                self.classify = ctx.classify
            else:
                t_l = tdf[OHLC].reset_index(drop=True)
                tz = E.mtz.detect_zones(t_l, config=E.trend, allow_wick_to_wick=False)
                ev = E.mtz._compute_trend_events(t_l, tz)
                self.classify = lambda t, _df=t_l, _ev=ev: E.mtz._classify_trend_from_events(_df, _ev, t)
        # ---- zones
        htf_cfg = E.bc.new_base_config(E.mtz.WEEKLY_CONFIG if sp["htf_cfg"] == "weekly" else E.mtz.MONTHLY_CONFIG, "htf")
        self.htf_zones = CD.dedupe_earliest(CD.detect_raw(E, self.htf, sz.wilder_atr(self.htf), htf_cfg, False))
        atr_l = sz.wilder_atr(self.ltf)
        raw = CD.detect_raw(E, self.ltf, atr_l, E.ltf_nocap, True)
        self.ltf_count = {id(z): len(E.bc.base_run(self.ltf, atr_l, z.leg_start_index, E.ltf, sz)) for z in raw}
        self.ltf_zones = CD.dedupe_earliest([z for z in raw if self.ltf_count[id(z)] <= E.ltf_cap])
        self.h_ts = self.htf["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.h_ct = self.htf["close_time"].to_numpy(dtype="datetime64[ns]")
        self.l_ts = self.ltf["timestamp"].to_numpy(dtype="datetime64[ns]")
        self.l_ct = self.ltf["close_time"].to_numpy(dtype="datetime64[ns]")
        self.l_day = self.l_ts.astype("datetime64[D]")
        self.idx = {t: CD._LtfIndex([z for z in self.ltf_zones if z.type == t], self.l_ts) for t in ("demand", "supply")}

    # ---- times
    def decision_time(self, ltf_label):
        """T_d: WIT = start of the entry 2h bar; MIT = entry day 09:15. Legacy mode keeps the LTF label itself."""
        t = pd.Timestamp(ltf_label)
        if not self.mode.pit_trend:
            return t
        return t if self.combo == "wit" else t.normalize() + SESSION_OPEN

    def trend_at(self, t):
        return self.classify(pd.Timestamp(t)) if self.trend_ok else None

    def wick_fail(self, hz, entry_label):
        wt = self.E.mtz._htf_wick_tested_at(self.htf, hz)
        return bool(wt is not None and pd.Timestamp(wt).normalize() < pd.Timestamp(entry_label).normalize())

    def scan_start(self, ltf_label):
        t = pd.Timestamp(ltf_label)
        if self.combo == "mit":
            return t.normalize() + SESSION_OPEN
        return t if self.mode.session_2h else _scan_start_legacy_wit(t)


def b0_trades(ctx):
    """Strict B0: legacy build_trades_for_ticker logic (every filter rejects), at the decision times of ctx.mode."""
    if not ctx.ok or not ctx.trend_ok:
        return []
    E = ctx.E
    out = []
    for hz in ctx.htf_zones:
        label = ctx.h_ts[hz.leg_end_index]  # HTF label: Sunday / month-end midnight (legacy formation time, decision D1)
        tr = ctx.trend_at(label)
        if tr is None or blocks(hz.type, tr):
            continue
        m = CD._best_ltf(E, hz, ctx.h_ts, ctx.idx[hz.type], ctx.l_ts, ctx.l_day)
        if m is None or m[0].tested_at_index is None:
            continue
        lz, frac = m
        e_label = ctx.l_ts[lz.tested_at_index]
        if ctx.wick_fail(hz, e_label):
            continue
        t_d = ctx.decision_time(e_label)
        te = ctx.trend_at(t_d)
        if te is not None and blocks(hz.type, te):
            continue
        entry, stop = lz.proximal_line, lz.distal_line
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        shares = min(int(1000.0 // risk), int(100000.0 // entry))
        if shares <= 0:
            continue
        target = entry + 2.0 * risk if hz.type == "demand" else entry - 2.0 * risk
        out.append(dict(
            ticker=ctx.ticker, combo=ctx.combo, type=hz.type, htf_proximal=hz.proximal_line, htf_distal=hz.distal_line,
            htf_base_start=pd.Timestamp(ctx.h_ts[hz.base_start_index]), htf_formed_at=pd.Timestamp(label),
            T_H=pd.Timestamp(ctx.h_ct[hz.leg_end_index]), htf_key=CD.zkey(hz)[1:], ltf_key=CD.zkey(lz)[1:],
            ltf_formed_at=pd.Timestamp(ctx.l_ts[lz.leg_end_index]), T_L=pd.Timestamp(ctx.l_ct[lz.leg_end_index]),
            entry_bar=pd.Timestamp(e_label), entry_time=pd.Timestamp(t_d), scan_start=ctx.scan_start(e_label),
            entry_price=entry, stop=stop, target=target, risk=risk, shares=shares, overlap_frac=frac,
            trend_htf=tr, trend_entry=te, htf_strong_legout=hz.has_strong_legout, ltf_strong_legout=lz.has_strong_legout,
            ltf_base_count=ctx.ltf_count.get(id(lz)), is_b0=True, relaxed_selected=False, mode=ctx.mode.name))
    return sorted(out, key=lambda r: (r["entry_time"], r["htf_formed_at"], r["type"]))


def build(ticker, combo, frames=None, mode=PIT, entry_from="2021-01-01", do_replay=True):
    frames = frames if frames is not None else load_frames(ticker)
    ctx = MtfContext(ticker, frames, combo, mode)
    rows = b0_trades(ctx)
    if entry_from is not None:
        rows = [r for r in rows if r["entry_bar"] >= pd.Timestamp(entry_from)]
    if do_replay and rows:
        rctx = RC.ReplayContext(ticker, frames["1d"], frames["15m"])  # the unchanged src/replay.py through the Phase A call path
        for r in rows:
            res = RC.replay_row(dict(r, entry_time=r["scan_start"]), rctx)
            r.update(outcome=res["outcome"], exit_reason=res["reason"], decided_interval=res["decided_interval"],
                     fill_time=res["fill_time"], fill_price=res["fill_price"], gap_fill=res["gap_fill"],
                     exit_time=res["exit_time"], exit_price=res["exit_price"], r_gross=res["r"], mtm_r=res["mtm_r"],
                     minute_used=res["minute_used"])
            end = res["exit_time"] if res["exit_time"] is not None else r["scan_start"].normalize() + pd.Timedelta(days=RP_HORIZON)
            r["ca_excluded"] = CA.window_has_flag(ctx.ca, r["htf_base_start"] - pd.Timedelta(days=CA.CA_PAD_DAYS), end)
    return rows


RP_HORIZON = CD.RP.HORIZON_DAYS
