"""
mtf_backtest.py

Backtests the DIT/WIT/MIT setups produced by mtf_zones.py under a fixed
position-sizing rule (user spec, 2026-09-22):
    - capital = Rs 1,00,000, run SEPARATELY per combo (each gets its own pool)
    - max loss per trade = Rs 1,000 -- position sized in whole shares so a
      full stop-out never loses more than this (shares = floor(1000/risk);
      0 shares -> trade skipped entirely, can't be sized under the cap).
    - reward:risk = 2:1 (target = entry +/- 2x risk)
    - multiple concurrent trades allowed; capped so total capital deployed
      across all currently-open positions never exceeds Rs 1,00,000. A
      trade whose own cost alone exceeds Rs 1,00,000 is skipped outright.

Entry/exit mechanics:
    - Entry triggers at the LTF zone's first-ever touch AFTER the HTF zone
      confirmed -- this is exactly Zone.tested_at_index/timestamp from
      apply_freshness, which match_zones() already guarantees falls after
      the HTF confirmation for any candidate it returns.
    - Exit: walk forward candle-by-candle on the LTF frame from the entry
      candle. Whichever of stop/target is touched first closes the trade.
      Same-candle ambiguity is resolved conservatively -- stop wins.
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "webapp"))

import mtf_zones as mtz
from universe import NIFTY50, EXTENDED, NIFTY500

CAPITAL = 100_000.0
MAX_LOSS_PER_TRADE = 1_000.0
REWARD_RISK = 2.0

LOOKBACK_DAYS = {"dit": None, "wit": 730, "mit": 730}

# Phase 1 (user directive, 2026-09-27): entries before this date are the
# TRAIN set -- the only data any tuning (manual or automated Phase 3 sweep)
# is allowed to look at. Entries on/after this date are HOLDOUT -- never
# touched while choosing a config, used only afterward to confirm a change
# actually generalizes instead of just fitting noise in the data already
# eyeballed. This lives in this ISOLATED ml_pipeline copy, not the
# production mtf_backtest.py -- see ml_pipeline/README_ML.md.
SPLIT_DATE = pd.Timestamp("2026-01-01")


def r_multiple(t: dict) -> Optional[float]:
    """P&L expressed in multiples of initial risk (R). +2.0 for a win, -1.0
    for a loss, given the fixed 2:1 reward:risk -- computed from the actual
    recorded pnl/shares/risk rather than hardcoded, so it stays correct if
    a trade was ever sized to 0 shares or partially filled."""
    if t["outcome"] is None or not t["shares"] or not t["risk"]:
        return None
    return t["pnl"] / (t["shares"] * t["risk"])


def split_train_holdout(trades: List[dict], split_date: pd.Timestamp = SPLIT_DATE):
    train = [t for t in trades if pd.Timestamp(t["entry_time"]) < split_date]
    holdout = [t for t in trades if pd.Timestamp(t["entry_time"]) >= split_date]
    return train, holdout


def _split_metrics(trades: List[dict]) -> dict:
    closed = [t for t in trades if t["outcome"] is not None]
    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    total_pnl = sum(t["pnl"] for t in closed) if closed else 0.0
    win_rate = (len(wins) / len(closed) * 100) if closed else None
    r_values = [r for r in (r_multiple(t) for t in closed) if r is not None]
    avg_r = (sum(r_values) / len(r_values)) if r_values else None
    return dict(n_taken=len(trades), n_closed=len(closed), n_wins=len(wins),
                n_losses=len(losses), win_rate=win_rate, total_pnl=total_pnl, avg_r=avg_r)


def summarize_train_holdout(taken: List[dict], combo: str, split_date: pd.Timestamp = SPLIT_DATE,
                             print_report: bool = True) -> dict:
    """Train/holdout metrics for one combo's capital-constrained trade list
    (Phase 1). The SAME chronological capital-constrained schedule is used
    for both halves -- trades aren't re-scheduled with a separate capital
    pool per split, this only partitions the resulting trade list by entry
    date for reporting, so the numbers reflect 'how did the one strategy
    that was actually running the whole time do in each period.'"""
    train, holdout = split_train_holdout(taken, split_date)
    train_m, holdout_m = _split_metrics(train), _split_metrics(holdout)

    if print_report:
        print(f"\n=== {combo.upper()} train/holdout split (cutoff {split_date.date()}) ===")
        for label, m in [("TRAIN", train_m), ("HOLDOUT", holdout_m)]:
            if m["n_closed"] == 0:
                print(f"  {label:8s} n_closed=0 (no data in range)")
                continue
            print(f"  {label:8s} n_closed={m['n_closed']:4d}  win_rate={m['win_rate']:5.1f}%  "
                  f"total_pnl=Rs {m['total_pnl']:>9,.0f}  avg_R={m['avg_r']:+.2f}")

    return dict(combo=combo, train=train_m, holdout=holdout_m)


def simulate_exit(ltf_df: pd.DataFrame, entry_idx: int, zone_type: str,
                   stop: float, target: float):
    for i in range(entry_idx, len(ltf_df)):
        row = ltf_df.iloc[i]
        if zone_type == "demand":
            hit_stop = row["low"] <= stop
            hit_target = row["high"] >= target
        else:
            hit_stop = row["high"] >= stop
            hit_target = row["low"] <= target
        # Price must enter the zone FIRST; target and stop only exist after
        # that (user rule, 2026-10-01). On the entry candle the stop is always
        # after entry (price crosses the entry level before a stop beyond it),
        # but the target can be touched BEFORE entry (e.g. a gap/open past the
        # target, then a move back into the zone) -- that is NOT a win. With
        # only OHLC, the target counts on the entry candle only if the
        # candle's path puts the entry first: demand = bullish candle (low
        # first, then high); supply = bearish candle (high first, then low).
        if i == entry_idx and hit_target:
            if zone_type == "demand":
                hit_target = row["close"] > row["open"]
            else:
                hit_target = row["close"] < row["open"]
        if hit_stop:
            return row["timestamp"], "loss"
        if hit_target:
            return row["timestamp"], "win"
    return None, None


def build_trades_for_ticker(ticker: str, combo: str, apply_trend_filter: bool = True) -> List[dict]:
    spec = mtz.COMBOS[combo]
    htf_df = mtz._build_frame(ticker, spec.htf_source, spec.htf_interval,
                               spec.ltf_fetch_period, spec.htf_resample, spec.htf_window)
    ltf_df = mtz._build_frame(ticker, spec.ltf_source, spec.ltf_interval,
                               spec.ltf_fetch_period, spec.ltf_resample, spec.ltf_window)
    if len(htf_df) < 20 or len(ltf_df) < 20:
        return []

    # allow_wick_to_wick=False: HTF/trend are bias/context, never the
    # execution timeframe -- see sd_zones.detect_zones' docstring (user
    # directive, 2026-09-27).
    htf_zones = mtz.detect_zones(htf_df, config=spec.htf_config, allow_wick_to_wick=False)
    trend_df, trend_events = None, None
    if apply_trend_filter:
        trend_df = mtz._build_frame(ticker, spec.trend_source, spec.trend_interval,
                                     spec.trend_fetch_period, spec.trend_resample, spec.trend_window)
        if len(trend_df) >= 20:
            trend_zones = mtz.detect_zones(trend_df, config=spec.trend_config, allow_wick_to_wick=False)
            trend_events = mtz._compute_trend_events(trend_df, trend_zones)
            htf_zones = mtz.filter_zones_by_trend_3tf(htf_zones, htf_df, trend_df, trend_zones)
        else:
            htf_zones = []
    ltf_zones = mtz.detect_zones(ltf_df, config=spec.ltf_config)
    ltf_atr = mtz.wilder_atr(ltf_df)
    htf_atr = mtz.wilder_atr(htf_df)
    ltf_states = {id(z): mtz.classify_zone_state(ltf_df, z, atr=ltf_atr) for z in ltf_zones}

    # trend_df/trend_events (2026-09-28, ACE fix): re-checks trend at the
    # LTF entry's actual trigger moment, not just at HTF formation -- see
    # match_zones' docstring point 5.
    matches = mtz.match_zones(htf_zones, htf_df, ltf_zones, ltf_df, ltf_states,
                               trend_df=trend_df, trend_events=trend_events)
    htf_ts_to_idx = {ts: i for i, ts in enumerate(htf_df["timestamp"])}

    trades = []
    for m in matches:
        entry_idx = m.get("ltf_tested_at_index")
        if entry_idx is None:
            continue

        entry_price = m["ltf_proximal"]
        stop = m["ltf_distal"]
        risk = abs(entry_price - stop)
        if risk <= 0:
            continue
        shares_by_loss = int(MAX_LOSS_PER_TRADE // risk)
        shares_by_capital = int(CAPITAL // entry_price)
        shares = min(shares_by_loss, shares_by_capital)
        if shares <= 0:
            continue

        zone_type = m["type"]
        target = entry_price + REWARD_RISK * risk if zone_type == "demand" else entry_price - REWARD_RISK * risk

        entry_time = ltf_df.iloc[entry_idx]["timestamp"]
        exit_time, outcome = simulate_exit(ltf_df, entry_idx, zone_type, stop, target)
        cost = shares * entry_price
        pnl = None
        if outcome == "win":
            pnl = shares * risk * REWARD_RISK
        elif outcome == "loss":
            pnl = -shares * risk

        # Diagnostics for the "why do winners win" breakdown -- not used in
        # P&L/sizing at all, just recorded for post-hoc analysis.
        ltf_risk_pct = risk / entry_price * 100 if entry_price else None
        htf_risk_pct = abs(m["htf_proximal"] - m["htf_distal"]) / max(m["htf_proximal"], m["htf_distal"]) * 100
        htf_idx = htf_ts_to_idx.get(pd.Timestamp(m["htf_formed_at"]))
        trend_strength_atr = None
        if htf_idx is not None:
            atr_ref = htf_atr.iloc[htf_idx]
            if pd.notna(atr_ref) and atr_ref > 0:
                ma = htf_df["close"].iloc[max(0, htf_idx - 49): htf_idx + 1].mean()
                trend_strength_atr = (htf_df.iloc[htf_idx]["close"] - ma) / atr_ref
                if zone_type == "supply":
                    trend_strength_atr = -trend_strength_atr  # flip so "+" always means "aligned, strongly"
        holding_bars = None
        if exit_time is not None:
            exit_positions = ltf_df.index[ltf_df["timestamp"] == exit_time]
            if len(exit_positions) > 0:
                holding_bars = exit_positions[0] - entry_idx

        trades.append({
            "ticker": ticker, "combo": combo, "type": zone_type,
            "htf_proximal": m["htf_proximal"], "htf_distal": m["htf_distal"],
            "ltf_formed_at": m["ltf_formed_at"],
            "entry_time": entry_time, "entry_price": entry_price,
            "stop": stop, "target": target, "risk": risk, "shares": shares,
            "cost": cost, "exit_time": exit_time, "outcome": outcome, "pnl": pnl,
            "htf_formed_at": m["htf_formed_at"],
            "overlap_frac": m["overlap_frac_of_ltf"],
            "ltf_risk_pct": ltf_risk_pct, "htf_risk_pct": htf_risk_pct,
            "trend_strength_atr": trend_strength_atr, "holding_bars": holding_bars,
            "htf_strong_legout": m["htf_strong_legout"], "ltf_strong_legout": m["ltf_strong_legout"],
        })
    return trades


def run_capital_constrained(trades: List[dict], capital: float = CAPITAL):
    trades_sorted = sorted(trades, key=lambda t: t["entry_time"])
    open_positions = []
    deployed = 0.0
    taken, skipped_capital, skipped_too_big = [], 0, 0

    for t in trades_sorted:
        still_open = []
        for exit_time, cost in open_positions:
            if exit_time <= t["entry_time"]:
                deployed -= cost
            else:
                still_open.append((exit_time, cost))
        open_positions = still_open

        if t["cost"] > capital:
            skipped_too_big += 1
            continue
        if deployed + t["cost"] <= capital + 1e-6:
            effective_exit = t["exit_time"] if t["exit_time"] is not None else pd.Timestamp.max
            open_positions.append((effective_exit, t["cost"]))
            deployed += t["cost"]
            taken.append(t)
        else:
            skipped_capital += 1

    return taken, skipped_capital, skipped_too_big


def summarize(taken: List[dict], combo: str) -> dict:
    closed = [t for t in taken if t["outcome"] is not None]
    still_open = [t for t in taken if t["outcome"] is None]
    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    total_pnl = sum(t["pnl"] for t in closed)
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0

    print(f"\n=== {combo.upper()} backtest (trend filter applied) ===")
    print(f"Trades taken: {len(taken)}   (closed: {len(closed)}, still open at data end: {len(still_open)})")
    print(f"Wins: {len(wins)}   Losses: {len(losses)}   Win rate: {win_rate:.1f}%")
    print(f"Total P&L (closed trades): Rs {total_pnl:,.0f}")
    print(f"Ending capital (started Rs {CAPITAL:,.0f}): Rs {CAPITAL + total_pnl:,.0f}")
    if wins:
        print(f"Avg win: Rs {sum(t['pnl'] for t in wins) / len(wins):,.0f}")
    if losses:
        print(f"Avg loss: Rs {sum(t['pnl'] for t in losses) / len(losses):,.0f}")

    return dict(combo=combo, taken=len(taken), closed=len(closed), wins=len(wins),
                losses=len(losses), win_rate=win_rate, total_pnl=total_pnl,
                still_open=len(still_open))


def bucket_report(closed_trades: List[dict], key: str, buckets: List[tuple], label: str):
    print(f"\n--- Win rate by {label} ---")
    for lo, hi, name in buckets:
        sub = [t for t in closed_trades if t.get(key) is not None and lo <= t[key] < hi]
        if not sub:
            continue
        wins = sum(1 for t in sub if t["outcome"] == "win")
        print(f"  {name:14s}  n={len(sub):4d}  win_rate={wins/len(sub)*100:5.1f}%  "
              f"total_pnl=Rs {sum(t['pnl'] for t in sub):,.0f}")


if __name__ == "__main__":
    APPLY_TREND_FILTER = "--no-trend-filter" not in sys.argv
    print(f"\n### Trend filter: {'ON' if APPLY_TREND_FILTER else 'OFF'} ###")

    # --combos=wit,mit (user directive, 2026-09-28): run only a subset of
    # combos, to get a bigger sample for WIT/MIT on the full universe
    # without re-running DIT (already has plenty of trades). Defaults to
    # all three -- existing behavior unchanged when the flag is omitted.
    combos_arg = next((a for a in sys.argv if a.startswith("--combos=")), None)
    COMBOS_TO_RUN = combos_arg.split("=", 1)[1].split(",") if combos_arg else ["dit", "wit", "mit"]
    print(f"### Combos: {', '.join(c.upper() for c in COMBOS_TO_RUN)} ###")

    reference_tickers = ["BHARTIARTL.NS", "MASTEK.NS", "MANAPPURAM.NS", "KEI.NS", "MAXHEALTH.NS", "CAMS.NS"]
    if "--nifty50" in sys.argv:
        universe = sorted(set(NIFTY50))
        universe_tag = "nifty50"
    elif "--medium" in sys.argv:
        # ~80 known-good tickers, no dead/delisted symbols -- for fast
        # iteration while still tuning logic. Nifty500 (default) is
        # impractically slow right now: 3 fetches/ticker (HTF+LTF+TREND)
        # and yfinance retries hard on each of Nifty500's several dozen
        # dead/delisted symbols before giving up.
        universe = sorted(set(NIFTY50 + EXTENDED + reference_tickers))
        universe_tag = "medium"
    else:
        # Widened to the full Nifty500 list per user request ("run a full
        # scan on a lot of stocks") -- not every symbol resolves on
        # yfinance, those just error out per-ticker below and get skipped.
        universe = sorted(set(NIFTY500 + NIFTY50 + EXTENDED + reference_tickers))
        universe_tag = "full"

    now = pd.Timestamp.now()
    all_summaries = []
    all_train_holdout = []
    all_closed_everywhere: List[dict] = []

    for combo in COMBOS_TO_RUN:
        print(f"\nBuilding trades for {combo.upper()} across {len(universe)} tickers...")
        all_trades: List[dict] = []
        # REVERTED (2026-09-24): tried a ThreadPoolExecutor here for speed,
        # but yfinance's shared session/crumb auth is NOT thread-safe --
        # concurrent requests corrupted it, causing most tickers (including
        # obviously-still-listed ones like RELIANCE/TCS/HDFCBANK) to fail
        # with false "possibly delisted" / "Invalid Crumb" errors. A run
        # that "completed" under threading silently used a fraction of the
        # universe and is not trustworthy. Back to sequential -- correct
        # and slow beats fast and wrong. A real speedup would need
        # yfinance's own batch multi-ticker download() (which manages its
        # session safely for many tickers in one call) instead of manual
        # per-ticker threading; not implemented yet.
        for i, ticker in enumerate(universe):
            try:
                all_trades.extend(build_trades_for_ticker(ticker, combo, apply_trend_filter=APPLY_TREND_FILTER))
            except Exception as e:
                print(f"  [{combo}] {ticker}: ERROR {e}")
            if (i + 1) % 25 == 0:
                print(f"  [{combo.upper()}] progress: {i + 1}/{len(universe)} tickers "
                      f"({len(all_trades)} signals so far)", flush=True)

        lookback = LOOKBACK_DAYS[combo]
        if lookback:
            cutoff = now - pd.Timedelta(days=lookback)
            all_trades = [t for t in all_trades if pd.Timestamp(t["entry_time"]) >= cutoff]

        if not all_trades:
            print("  no triggered signals in range")
            continue

        span_start = min(t["entry_time"] for t in all_trades)
        span_end = max(t["entry_time"] for t in all_trades)
        print(f"  {len(all_trades)} triggered signals, entries spanning {span_start} to {span_end}")

        taken, skipped_capital, skipped_too_big = run_capital_constrained(all_trades)
        print(f"  Took {len(taken)} trades, skipped {skipped_capital} (capital full at the time), "
              f"{skipped_too_big} (single trade cost > capital)")
        all_summaries.append(summarize(taken, combo))
        all_train_holdout.append(summarize_train_holdout(taken, combo))
        all_closed_everywhere.extend([t for t in all_trades if t["outcome"] is not None])

    print("\n\n=== Overall summary ===")
    for s in all_summaries:
        print(f"{s['combo'].upper():4s}  trades={s['taken']:4d}  closed={s['closed']:4d}  "
              f"win_rate={s['win_rate']:5.1f}%  pnl=Rs {s['total_pnl']:,.0f}  "
              f"still_open={s['still_open']}")

    print(f"\n\n=== Train/holdout summary (cutoff {SPLIT_DATE.date()}) ===")
    print(f"{'combo':6s} {'train_n':>8s} {'train_wr':>9s} {'train_pnl':>11s} {'train_R':>8s}  |  "
          f"{'hold_n':>7s} {'hold_wr':>8s} {'hold_pnl':>10s} {'hold_R':>7s}")
    for s in all_train_holdout:
        tm, hm = s["train"], s["holdout"]
        tr_wr = f"{tm['win_rate']:.1f}%" if tm["win_rate"] is not None else "n/a"
        tr_r = f"{tm['avg_r']:+.2f}" if tm["avg_r"] is not None else "n/a"
        ho_wr = f"{hm['win_rate']:.1f}%" if hm["win_rate"] is not None else "n/a"
        ho_r = f"{hm['avg_r']:+.2f}" if hm["avg_r"] is not None else "n/a"
        print(f"{s['combo'].upper():6s} {tm['n_closed']:8d} {tr_wr:>9s} "
              f"{tm['total_pnl']:>11,.0f} {tr_r:>8s}  |  "
              f"{hm['n_closed']:7d} {ho_wr:>8s} {hm['total_pnl']:>10,.0f} {ho_r:>7s}")

    # --- Why do winners win? Breakdown across ALL triggered+closed trades
    # (not just the capital-constrained subset -- capital scheduling is
    # about scheduling, not signal quality). Per user request 2026-09-23.
    print("\n\n=== WHY: breakdown of all closed trades across DIT/WIT/MIT ===")
    print(f"Total closed trades analyzed: {len(all_closed_everywhere)}")

    print("\n--- Win rate by combo ---")
    for combo in ["dit", "wit", "mit"]:
        sub = [t for t in all_closed_everywhere if t["combo"] == combo]
        if not sub:
            continue
        wins = sum(1 for t in sub if t["outcome"] == "win")
        print(f"  {combo.upper():4s}  n={len(sub):4d}  win_rate={wins/len(sub)*100:5.1f}%  "
              f"total_pnl=Rs {sum(t['pnl'] for t in sub):,.0f}")

    print("\n--- Win rate by zone type ---")
    for zt in ["demand", "supply"]:
        sub = [t for t in all_closed_everywhere if t["type"] == zt]
        if not sub:
            continue
        wins = sum(1 for t in sub if t["outcome"] == "win")
        print(f"  {zt:8s}  n={len(sub):4d}  win_rate={wins/len(sub)*100:5.1f}%  "
              f"total_pnl=Rs {sum(t['pnl'] for t in sub):,.0f}")

    bucket_report(all_closed_everywhere, "overlap_frac",
                  [(0.5, 0.7, "50-70%"), (0.7, 0.9, "70-90%"), (0.9, 1.01, "90-100%")],
                  "LTF-in-HTF overlap fraction")

    bucket_report(all_closed_everywhere, "ltf_risk_pct",
                  [(0, 1, "<1% risk"), (1, 3, "1-3% risk"), (3, 6, "3-6% risk"), (6, 1000, ">6% risk")],
                  "LTF risk as % of entry price")

    bucket_report(all_closed_everywhere, "htf_risk_pct",
                  [(0, 3, "<3% risk"), (3, 8, "3-8% risk"), (8, 15, "8-15% risk"), (15, 1000, ">15% risk")],
                  "HTF zone width as % of price")

    bucket_report(all_closed_everywhere, "trend_strength_atr",
                  [(-100, 0, "against/no trend"), (0, 1, "weak (0-1x ATR)"),
                   (1, 3, "moderate (1-3x ATR)"), (3, 1000, "strong (>3x ATR)")],
                  "trend strength at HTF formation (ATR multiples beyond MA, sign-flipped for supply)")

    bucket_report(all_closed_everywhere, "holding_bars",
                  [(0, 3, "0-2 bars"), (3, 10, "3-9 bars"), (10, 30, "10-29 bars"), (30, 100000, "30+ bars")],
                  "holding period (in LTF bars)")

    print("\n--- Win rate by strong-legout quality signal (gap or 2nd strong candle -- NOT a filter) ---")
    for label, pred in [
        ("neither HTF nor LTF", lambda t: not t["htf_strong_legout"] and not t["ltf_strong_legout"]),
        ("HTF only", lambda t: t["htf_strong_legout"] and not t["ltf_strong_legout"]),
        ("LTF only", lambda t: not t["htf_strong_legout"] and t["ltf_strong_legout"]),
        ("both HTF and LTF", lambda t: t["htf_strong_legout"] and t["ltf_strong_legout"]),
    ]:
        sub = [t for t in all_closed_everywhere if pred(t)]
        if not sub:
            continue
        wins = sum(1 for t in sub if t["outcome"] == "win")
        print(f"  {label:20s}  n={len(sub):4d}  win_rate={wins/len(sub)*100:5.1f}%  "
              f"total_pnl=Rs {sum(t['pnl'] for t in sub):,.0f}")

    # Export full diagnostic CSV for manual digging / Phase 2's ML diagnosis.
    # "split" column (train/holdout, per SPLIT_DATE) lets Phase 2 partition
    # directly instead of re-deriving it from entry_time.
    out_df = pd.DataFrame(all_closed_everywhere)
    if not out_df.empty:
        out_df["split"] = out_df["entry_time"].apply(
            lambda t: "train" if pd.Timestamp(t) < SPLIT_DATE else "holdout")
    suffix = "with_trend" if APPLY_TREND_FILTER else "no_trend"
    # Distinct filename whenever this isn't the standard all-combos/medium-
    # universe run, so a partial-combo or full-universe pass never
    # overwrites the existing medium-universe export (user directive,
    # 2026-09-28: "a clearly separate filename so it doesn't overwrite the
    # existing one with the smaller-universe data").
    is_standard_run = (COMBOS_TO_RUN == ["dit", "wit", "mit"]) and universe_tag == "medium"
    if is_standard_run:
        out_path = os.path.join(_HERE, f"mtf_trade_diagnostics_{suffix}.csv")
    else:
        combos_tag = "_".join(COMBOS_TO_RUN)
        out_path = os.path.join(_HERE, f"mtf_trade_diagnostics_{combos_tag}_{universe_tag}_{suffix}.csv")
    out_df.to_csv(out_path, index=False)
    print(f"\nFull diagnostic CSV saved: {out_path}")
