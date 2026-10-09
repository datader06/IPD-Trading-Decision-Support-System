"""Demo scanner feed: current setup status per ticker and strategy (DIT15 / WIT / MIT) from the CACHED frames.

DEMO OUTPUT. It is not a backtest result and not one of the frozen Phase A baselines. It reuses, unchanged, the strict (B0) zone,
matching, trend and replay logic of src/candidates.py (DIT15) and src/candidates_mtf.py (WIT / MIT) but, unlike the historical
builders, keeps zones that have not triggered yet. Data are the latest bars in the cached frames; nothing is fetched.

Status of the best live setup of a ticker and strategy (priority CONFIRMED > IN ZONE > APPROACHING; ties: nearest to the entry):
  CONFIRMED    the entry level was touched before the latest cached trading day and the replayed trade is still live (neither the
               stop nor the target reached), triggered within CONFIRMED_MAX_AGE_DAYS calendar days
  IN ZONE      the entry level was touched on the latest cached trading day and the trade is still live
  APPROACHING  the LTF zone is untouched and the last close is on the entry side of the proximal line within APPROACH_MAX_ATR
               ATRs (the sd_zones.classify_zone_state cap) or within APPROACH_MAX_PCT percent of the entry
  NO SETUP     no live strict setup
A setup needs: an HTF zone not invalidated, a strict (B0) matched LTF zone, trend at the HTF formation not blocking, trend at the
(actual or current) entry time not blocking, HTF wick-freshness (rule R10) not failed, positive risk and share size.
Entry = LTF proximal, stop = LTF distal, target = entry +/- 2 x risk (risk/reward 2.0), as in Phase A.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT / "src"), str(ROOT / "legacy" / "handoff" / "handoff" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import candidates as CD  # noqa: E402
import candidates_mtf as CM  # noqa: E402
import replay_context as RC  # noqa: E402
from trend_pit import blocks  # noqa: E402

STRATEGIES = ("DIT15", "WIT", "MIT")
STATUSES = ("CONFIRMED", "IN ZONE", "APPROACHING", "NO SETUP")
APPROACH_MAX_ATR = 3.0
APPROACH_MAX_PCT = 10.0  # demo: also accept an untouched zone whose entry is within this % of the last close (weekly / monthly
#                         setups are far from price in short-timeframe ATRs)
CONFIRMED_MAX_AGE_DAYS = 14
LIVE_OUTCOMES = ("CENSORED", "OPEN")  # replay: entry filled, neither stop nor target reached
PRIORITY = {"CONFIRMED": 3, "IN ZONE": 2, "APPROACHING": 1}
COLUMNS = ["ticker", "strategy", "as_of", "price_time", "current_price", "status", "zone_type", "entry", "stop", "target", "risk",
           "risk_reward", "distance_to_entry", "distance_pct", "distance_atr", "trend", "htf_proximal", "htf_distal", "ltf_proximal",
           "ltf_distal", "htf_formed_at", "ltf_formed_at", "triggered_at", "open_r", "n_live_setups", "data_note"]
DATA_NOTE = "DEMO scanner on cached data; not a backtest result"


def _adapter(ticker, strategy, frames):
    """Uniform view of the DIT15 / WIT / MIT contexts built by the existing Phase A classes."""
    if strategy == "DIT15":
        ctx = CD.TickerContext(ticker, frames, CD.PIT)
        if not (ctx.ok and ctx.trend_ok):
            return None
        return dict(ctx=ctx, E=ctx.E, hzs=ctx.htf_b0, idx=ctx.idx_b0, h_ts=ctx.d1_ts, l_ts=ctx.ts15, l_day=ctx.day15,
                    ltf=ctx.m15.reset_index(drop=True), htf=ctx.d1.reset_index(drop=True),
                    form_label=lambda hz: ctx.t_formation(hz), dec=lambda lab: pd.Timestamp(lab),
                    scan=lambda lab: pd.Timestamp(lab))
    ctx = CM.MtfContext(ticker, frames, strategy.lower(), CM.PIT)
    if not (ctx.ok and ctx.trend_ok):
        return None
    return dict(ctx=ctx, E=ctx.E, hzs=ctx.htf_zones, idx=ctx.idx, h_ts=ctx.h_ts, l_ts=ctx.l_ts, l_day=ctx.l_day, ltf=ctx.ltf,
                htf=ctx.htf, form_label=lambda hz: ctx.h_ts[hz.leg_end_index], dec=ctx.decision_time, scan=ctx.scan_start)


def _setups(ticker, strategy, frames, rctx):
    """All live strict setups of one ticker and strategy (list of dicts) plus the latest bar facts."""
    a = _adapter(ticker, strategy, frames)
    if a is None:
        return [], None
    ctx, E, ltf, htf = a["ctx"], a["E"], a["ltf"], a["htf"]
    sz = E.sz
    last = len(ltf) - 1
    last_ts, price = pd.Timestamp(ltf["timestamp"].iloc[last]), float(ltf["close"].iloc[last])
    atr = float(sz.wilder_atr(ltf).iloc[last])
    as_of = pd.Timestamp(frames["1d"]["timestamp"].iloc[-1]).normalize()
    facts = dict(price=price, price_time=last_ts, as_of=as_of, trend=ctx.trend_at(last_ts))
    out = []
    for hz in a["hzs"]:
        if sz.is_zone_invalidated(htf, hz):
            continue
        tr = ctx.trend_at(a["form_label"](hz))  # trend at HTF formation (strict B0 rule, decision D1)
        if tr is None or blocks(hz.type, tr):
            continue
        m = CD._best_ltf(E, hz, a["h_ts"], a["idx"][hz.type], a["l_ts"], a["l_day"])
        if m is None:
            continue
        lz, frac = m
        entry, stop = lz.proximal_line, lz.distal_line
        risk = abs(entry - stop)
        if risk <= 0 or min(int(1000.0 // risk), int(100000.0 // entry)) <= 0:
            continue
        demand = hz.type == "demand"
        target = entry + 2.0 * risk if demand else entry - 2.0 * risk
        ti = lz.tested_at_index
        row = dict(ticker=ticker, strategy=strategy, zone_type=hz.type, entry=entry, stop=stop, target=target, risk=risk,
                   risk_reward=abs(target - entry) / risk, htf_proximal=hz.proximal_line, htf_distal=hz.distal_line,
                   ltf_proximal=entry, ltf_distal=stop, htf_formed_at=pd.Timestamp(a["h_ts"][hz.leg_end_index]),
                   ltf_formed_at=pd.Timestamp(a["l_ts"][lz.leg_end_index]), triggered_at=None, open_r=np.nan)
        if ti is None:  # untouched LTF zone
            if ctx.wick_fail(hz, last_ts):
                continue
            te = ctx.trend_at(a["dec"](last_ts))
            if te is not None and blocks(hz.type, te):
                continue
            gap = (price - entry) if demand else (entry - price)  # > 0: price still on the entry side of the zone
            if gap <= 0 or not np.isfinite(atr) or atr <= 0:
                continue
            if gap / atr > APPROACH_MAX_ATR and 100.0 * gap / entry > APPROACH_MAX_PCT:
                continue
            row["status"] = "APPROACHING"
        else:  # the entry level was touched: is the trade still live?
            e_label = pd.Timestamp(a["l_ts"][ti])
            if ctx.wick_fail(hz, e_label):
                continue
            te = ctx.trend_at(a["dec"](e_label))
            if te is not None and blocks(hz.type, te):
                continue
            res = RC.replay_row(dict(type=hz.type, entry_price=entry, stop=stop, target=target, risk=risk,
                                     entry_time=a["scan"](e_label)), rctx)
            if res["outcome"] not in LIVE_OUTCOMES:
                continue
            trig = pd.Timestamp(res["fill_time"]) if res["fill_time"] is not None else e_label
            if trig.normalize() == as_of:
                row["status"] = "IN ZONE"
            elif (as_of - trig.normalize()).days <= CONFIRMED_MAX_AGE_DAYS:
                row["status"] = "CONFIRMED"
            else:
                continue  # an old open trade is not a current opportunity
            row["triggered_at"] = trig
            row["open_r"] = res["mtm_r"] if res["mtm_r"] is not None else np.nan
        row["distance_to_entry"] = price - entry
        row["distance_pct"] = 100.0 * (price - entry) / entry
        row["distance_atr"] = (price - entry) / atr if np.isfinite(atr) and atr > 0 else np.nan
        row["_rank"] = (-PRIORITY[row["status"]], abs(row["distance_pct"]))
        out.append(row)
    return out, facts


def scan_ticker(args):
    """(ticker, strategies) -> list of feed rows, one per strategy (NO SETUP rows included). Never raises: errors become rows."""
    ticker, strategies = args
    rows = []
    try:
        frames = CM.load_frames(ticker)
        if frames["1d"].empty or frames["15m"].empty:
            return [dict(ticker=ticker, strategy=s, status="NO SETUP", data_note="no cached frames") for s in strategies]
        rctx = RC.ReplayContext(ticker, frames["1d"], frames["15m"])
    except Exception as e:  # noqa: BLE001
        return [dict(ticker=ticker, strategy=s, status="NO SETUP", data_note=f"error: {type(e).__name__}: {e}") for s in strategies]
    for s in strategies:
        try:
            live, facts = _setups(ticker, s, frames, rctx)
        except Exception as e:  # noqa: BLE001
            rows.append(dict(ticker=ticker, strategy=s, status="NO SETUP", data_note=f"error: {type(e).__name__}: {e}"))
            continue
        if facts is None:
            rows.append(dict(ticker=ticker, strategy=s, status="NO SETUP", data_note="insufficient data for this strategy"))
        elif not live:
            rows.append(dict(ticker=ticker, strategy=s, status="NO SETUP", as_of=facts["as_of"].date().isoformat(),
                             price_time=facts["price_time"], current_price=facts["price"], trend=facts["trend"], n_live_setups=0,
                             data_note=DATA_NOTE))
        else:
            best = sorted(live, key=lambda r: r["_rank"])[0]
            best.pop("_rank")
            for r in live:
                r.pop("_rank", None)
            best.update(as_of=facts["as_of"].date().isoformat(), price_time=facts["price_time"], current_price=facts["price"],
                        trend=facts["trend"], n_live_setups=len(live), data_note=DATA_NOTE)
            rows.append(best)
    return rows


def to_frame(rows):
    df = pd.DataFrame(rows)
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    return df[COLUMNS].sort_values(["strategy", "status", "ticker"], key=lambda s: s.map({k: i for i, k in enumerate(STATUSES + STRATEGIES)})
                                   if s.name in ("status", "strategy") else s, kind="mergesort").reset_index(drop=True)
