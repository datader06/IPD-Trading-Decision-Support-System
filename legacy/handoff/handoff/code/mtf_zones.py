"""
mtf_zones.py

Multi-timeframe (HTF -> LTF) supply/demand zone pairing.

Three trade types (per user spec, 2026-09-22):
    DIT : HTF = daily,   LTF = 60m  (changed from 15m -- see note below)
    WIT : HTF = weekly,  LTF = 2h   (resampled from 60m -- Yahoo has no
                                     native 2h interval)
    MIT : HTF = monthly, LTF = daily

DIT's LTF was originally 15m. Changed to 60m (2026-09-27, user directive)
after a funnel diagnostic proved DIT's near-zero trade count wasn't a logic
bug: of 1,029 raw daily HTF zones across an 80-ticker universe, only 55
(5%) even had their confirm date fall inside 15m data's ~59-day Yahoo
retention window -- everything downstream (trend filter, LTF pairing, the
HTF-already-tapped rule) only ever had that starved 55-zone pool to work
with. 30m has the SAME ~60-day cap as 15m, so it wouldn't have helped; only
60m+ gets Yahoo's ~730-day intraday retention. Moving LTF to 60m trades a
little execution granularity for a >10x wider window to find concurrent
LTF zones in. The trend (intermediate) timeframe stays 2h, still one step
coarser than the new 60m LTF, so the HTF > TREND > LTF ordering holds.

Golden rule: the HTF zone sets directional bias (context); the LTF zone is
the tighter, tradeable entry/stop. A pairing only counts if the LTF zone is
the SAME type (demand/demand or supply/supply) as the HTF zone, and at
least half of the LTF zone's own price range sits inside the HTF zone's
range -- confirmed against user's reference charts as an acceptable bar
(full containment, like CAMS's 2h-inside-weekly zone, is not required).
See MIN_LTF_OVERLAP_FRAC.

IMPORTANT correction (2026-09-22, user caught this via SBIN DIT supply):
the LTF zone is NOT a later retest/pullback into the HTF zone -- it is the
LTF-resolution view of the SAME price move that built the HTF zone,
happening concurrently. E.g. SBIN's daily (HTF) supply zone formed on
15-Sep; the correct 15m (LTF) zone is also dated 15-Sep (same day) --
zoom into that single HTF candle's own timeframe and its base+leg pattern
is already there. The first version of this module wrongly searched for
LTF zones formed AFTER the HTF zone (a separate later tap-back), which
is a different, wrong thing. The fix: an LTF zone only qualifies if its
own leg closed within the HTF zone's own formation window -- from the
HTF zone's base_start date through its leg_end date -- i.e. during the
HTF zone's formation, not after it.

SECOND correction (2026-09-22, user caught this via LT DIT supply, and the
same pattern in JPPOWER/EICHERMOT/MASTEK MIT): forming inside the window
isn't enough on its own -- an LTF zone that already got tapped (tested)
BEFORE the HTF zone's own leg finished closing is a stale setup by the
time the HTF bias actually exists, and doesn't qualify either. Concretely:
LT's daily supply zone confirmed on 15-Sep, but the LTF candidate the
first version picked had formed back on 9-Sep and had already been tested
(tapped and left) by the time the 15-Sep HTF candle closed -- not a valid
"still live at HTF confirmation" entry. The correct LTF zone is the one
that was STILL FRESH (untested) at the moment the HTF zone's own bar
finished forming -- in LT's case, that's the zone formed same-day, 15-Sep.
The fix: a candidate LTF zone is excluded if its Zone.tested_at_timestamp
(first-ever touch, from apply_freshness, scanned over full LTF history) is
<= the last actual LTF candle at/before the HTF zone's own bar period ends
(see `confirm_cutoff` in match_zones -- deliberately the last real candle
of that day/week/month, not the bar's midnight-normalized label, so a tap
during the HTF bar's own session still correctly excludes it). This
generalizes across all three combos without hardcoding day/week/month
granularity: for DIT it usually resolves to "same trading day as the HTF
close" (confirmed WIT/MIT cases show the valid LTF zone can be days/weeks
earlier than the HTF close, as long as it's still untouched by then --
e.g. ONGC MIT: HTF confirmed 30-Jun, LTF formed 27-May, still fresh
through end of June -- confirmed correct by user ("BLOODY AWESOME")).

HTF config choice: WEEKLY_CONFIG/MONTHLY_CONFIG (the existing "loose HTF
context" profiles) are reused regardless of which *absolute* timeframe is
playing the HTF role here -- e.g. for DIT, daily-as-HTF uses WEEKLY_CONFIG
rather than the strict DEFAULT_CONFIG, since DEFAULT_CONFIG was calibrated
for daily-as-entry-timeframe, not daily-as-context.
LTF config choice: DEFAULT_CONFIG (the validated tight/entry-grade
profile) is reused uniformly across daily/2h/15m LTF, since none of those
have a separately calibrated LTF profile yet.

"Give me trades" mode (this module's __main__): unlike the first logic-demo
pass, results here are filtered to LIVE setups only -- the HTF bias zone
must not be invalidated (price hasn't closed through its distal), and the
LTF zone must currently classify as 'reacting' or 'approaching' (not
invalidated, not used up -- see classify_zone_state in sd_zones.py).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from typing import Optional, List, Literal

import numpy as np
import pandas as pd
import yfinance as yf

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "webapp"))

from sd_zones import (
    detect_zones, wilder_atr, Zone, classify_zone_state, is_zone_invalidated,
    DEFAULT_CONFIG, WEEKLY_CONFIG, MONTHLY_CONFIG,
)
from universe import NIFTY50, EXTENDED

ComboName = Literal["dit", "wit", "mit"]

# User directive (2026-09-23): only take a trade if the LTF leg is a single
# clear explosive candle, or better yet 2 -- never 3. DEFAULT_CONFIG's
# max_leg_candles=3 was calibrated for the general single-timeframe daily
# scanner and is left untouched there; this is a separate, MTF-specific
# entry-grade profile so the webapp's daily/weekly scans aren't affected.
# max_base_candles stays at DEFAULT_CONFIG's 3 for LTF (HTF uses 5). A
# 2026-10-01 test raising LTF to 5 made DIT worse (n=213, 45.1%, Rs58,003
# vs 207/48.3%/Rs67,161) and was reverted. The current cap TRUNCATES the
# base rather than rejecting long ones; ZoneConfig.full_run_base (default
# OFF) is the experimental reject-if-too-long alternative.
# require_legout_beyond_legin=True (made permanent 2026-09-29): GTF-notes
# rule, LTF/execution role only (per user directive -- HTF/trend configs
# are untouched). Isolated full-universe backtesting showed this net
# positive/neutral across all three combos -- see sd_zones.ZoneConfig's
# comment on this field for the exact before/after numbers. The companion
# "legin-wick-as-distal" rule was tested alongside it and rejected (net
# negative on DIT/WIT), and its code has been removed entirely, not just
# left disabled.
#
# STANDING BASELINE, rule-1-only, pre-wick-fix (2026-09-30, confirmed via
# production build_trades_for_ticker on the full 504-ticker universe):
#   DIT: n=297  win_rate=45.8%  total_pnl=Rs 84,563  avg_R=+0.374
#   WIT: n=45   win_rate=51.1%  total_pnl=Rs 21,697  avg_R=+0.533
#   MIT: n=27   win_rate=44.4%  total_pnl=Rs 8,946   avg_R=+0.333
# Note: these differ slightly (a handful of trades each) from the
# isolated rule-1-only test run one day earlier (DIT 281, WIT 44, MIT 26)
# -- diffed and confirmed this is NOT a bug in this rule: it's
# day-to-day drift in walk_back_base's chosen base for a small number of
# zones (live OHLC windows shift between fetches on different days) plus
# ordinary transient "possibly delisted" fetch dropouts, both
# already-documented characteristics of this live-data system, verified
# by direct candle-level inspection (e.g. SCI.NS, GABRIEL.NS) and by the
# dropped ticker appearing in that run's own error log (SYRMA.NS).
#
# STANDING BASELINE, rule-1 + HTF wick-freshness fix -- CURRENT, PERMANENT
# (2026-09-30, confirmed on full 504-ticker universe via production
# build_trades_for_ticker for all three combos). The wick-freshness rule
# (see _htf_wick_tested_at() below): an HTF zone wick touch that
# rallies/drops away and LATER returns to tap it again invalidates the
# zone (freshness lost on the second touch); a wick touch that runs
# straight through into the body without pulling away first still
# counts as one clean touch and the zone stays fresh. Uses the base's
# true wick extreme, not the narrower body-based proximal, per user
# directive after reviewing USHAMART/GODFRYPHLP losses. Saved to
# mtf_trade_diagnostics_{combo}_NEW_BASELINE.csv and rejected_trades_
# {combo}.csv (the latter lists every trade this fix removed vs. the
# rule-1-only baseline above, for manual chart cross-checking):
#   DIT: n=207  win_rate=48.3%  total_pnl=Rs 67,161  avg_R=+0.449
#        (train n=123 wr=48.0% pnl=37,339; holdout n=84 wr=48.8% pnl=29,822)
#   WIT: n=25   win_rate=52.0%  total_pnl=Rs 12,563  avg_R=+0.560
#        (train n=12 wr=58.3% pnl=8,913; holdout n=13 wr=46.2% pnl=3,650)
#   MIT: n=22   win_rate=50.0%  total_pnl=Rs 10,886  avg_R=+0.500
#        (train n=14 wr=50.0% pnl=6,868; holdout n=8 wr=50.0% pnl=4,017)
# Future comparisons should diff against THESE numbers, not the rule-1-
# only ones above.
#
# REJECTED: "strong LTF override" (re-admitting a wick-freshness-
# rejected trade if its LTF leg is a single explosive candle or 2 clean
# absorbed candles, with <=2 base candles) was tested separately
# (2026-09-30) and found to add volume without a real quality edge --
# 11W/13L on the added trades across all three combos combined. This
# was ONLY ever a standalone scratch check (_quality_override_check.py,
# not imported by any production module) and was deliberately never
# wired into match_zones/detect_zones -- do not re-add it here.
LTF_ENTRY_CONFIG = replace(DEFAULT_CONFIG, max_leg_candles=2, require_legout_beyond_legin=True)

# User directive (2026-09-23, from annotated chart examples -- ONGC/
# BAJFINANCE/LAURUSLABS/KEI/ORIENTCEM/MASTEK/MAXHEALTH/MANAPPURAM/IKS/
# GRANULES): zones counted toward the trend break-count on the intermediate
# timeframe don't have to be "perfect" -- "you can consider even bad sz,
# they don't have to be perfect." Real tradeable zones (HTF_CONFIG/
# LTF_ENTRY_CONFIG) stay strict; this is a separate, deliberately loose
# profile used ONLY for counting zone breaks toward trend, via
# classify_trend_3tf/filter_zones_by_trend_3tf below.
TREND_ZONE_CONFIG = replace(
    WEEKLY_CONFIG,
    impulse_body_atr_mult=0.8,
    base_body_atr_mult=0.7,
    max_leg_candles=4,
    max_base_range_to_leg_range=2.5,
    min_zone_width_atr_mult=0.2,
    departure_tolerance_atr_mult=0.4,
    base_extension_atr_mult=float("inf"),
)

# At least this fraction of the LTF zone's own height must overlap the HTF
# zone's range. 1.0 would require full containment. Lowered 0.5 -> 0.3
# (2026-09-23, user directive) after the Nifty500 backtest showed 50-90%
# overlap trades actually outperforming 90-100% overlap trades -- tighter
# containment isn't the quality signal it looked like, so loosening the
# floor further to let more of that better-performing band through.
MIN_LTF_OVERLAP_FRAC = 0.3

_fetch_cache: dict = {}


@dataclass
class ComboSpec:
    htf_interval: str
    htf_resample: Optional[str]
    htf_source: Literal["daily", "intraday"]
    htf_config: object
    htf_window: Optional[int]

    ltf_interval: str
    ltf_resample: Optional[str]
    ltf_source: Literal["daily", "intraday"]
    ltf_config: object
    ltf_window: Optional[int]

    ltf_fetch_period: str

    # Third, intermediate timeframe for trend (user directive, 2026-09-23):
    # sits one step below HTF and feeds classify_trend_3tf/filter_zones_by_
    # trend_3tf instead of the old single-series close-vs-MA placeholder.
    # LTF (execution) is unchanged from the original 2-tier design.
    trend_interval: str = "1d"
    trend_resample: Optional[str] = None
    trend_source: Literal["daily", "intraday"] = "daily"
    trend_config: object = None
    trend_window: Optional[int] = None
    trend_fetch_period: str = "max"


COMBOS: dict[ComboName, ComboSpec] = {
    # DIT: HTF=daily, TREND=2h (intermediate), LTF=60m (execution -- changed
    # from 15m 2026-09-27, see module docstring: 15m/30m are both capped at
    # ~59 days by Yahoo, which was starving DIT down to a handful of trades
    # regardless of universe size; 60m reaches ~729 days instead).
    "dit": ComboSpec(
        htf_interval="1d", htf_resample=None, htf_source="daily",
        htf_config=WEEKLY_CONFIG, htf_window=750,
        ltf_interval="60m", ltf_resample=None, ltf_source="intraday",
        ltf_config=LTF_ENTRY_CONFIG, ltf_window=None,
        ltf_fetch_period="729d",
        trend_interval="60m", trend_resample="2h", trend_source="intraday",
        trend_config=TREND_ZONE_CONFIG, trend_window=None, trend_fetch_period="729d",
    ),
    # WIT: HTF=weekly, TREND=daily (intermediate), LTF=2h (execution, unchanged)
    "wit": ComboSpec(
        htf_interval="1d", htf_resample="W", htf_source="daily",
        htf_config=WEEKLY_CONFIG, htf_window=400,
        ltf_interval="60m", ltf_resample="2h", ltf_source="intraday",
        ltf_config=LTF_ENTRY_CONFIG, ltf_window=None,
        ltf_fetch_period="730d",
        trend_interval="1d", trend_resample=None, trend_source="daily",
        trend_config=TREND_ZONE_CONFIG, trend_window=750, trend_fetch_period="max",
    ),
    # MIT: HTF=monthly, TREND=weekly (intermediate), LTF=daily (execution, unchanged)
    "mit": ComboSpec(
        htf_interval="1d", htf_resample="ME", htf_source="daily",
        htf_config=MONTHLY_CONFIG, htf_window=None,
        ltf_interval="1d", ltf_resample=None, ltf_source="daily",
        ltf_config=LTF_ENTRY_CONFIG, ltf_window=750,
        ltf_fetch_period="max",
        trend_interval="1d", trend_resample="W", trend_source="daily",
        trend_config=TREND_ZONE_CONFIG, trend_window=400, trend_fetch_period="max",
    ),
}


def _fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    key = (ticker, period, interval)
    if key in _fetch_cache:
        return _fetch_cache[key]

    # Explicit start/end instead of period=, for intraday intervals only
    # (2026-09-26 bug fix): yfinance's period="NNNd" for an intraday
    # interval, on a ticker whose own listing date is older than NNN days,
    # can resolve the request's start to the ticker's OWN first trading
    # day rather than "NNN days before today" -- and if THAT date is more
    # than 730 days old, Yahoo's hard intraday-retention limit rejects the
    # whole request outright. Confirmed: failing tickers' error messages
    # gave a startTime that exactly matched their real listing date (e.g.
    # BAJAJHFL listed 2024-09-16, error's startTime decoded to 2024-09-16),
    # even though the requested period ("729d") was itself well under
    # Yahoo's 730-day cap. Anchoring start/end to TODAY explicitly sidesteps
    # this -- Yahoo then just returns whatever's available in that window
    # (naturally clipped to the ticker's real history on the other side).
    # timeout=5 (2026-09-29): yfinance's default 10s timeout means a
    # genuinely bad/delisted ticker costs ~8.3s to fail (confirmed by direct
    # measurement); a real ticker returns in <0.5s regardless of the ceiling.
    # When several bad tickers cluster together in the alphabetically-sorted
    # universe list, that stretch of a run gets disproportionately slow --
    # this was misread as general Yahoo rate-limiting earlier, but a live
    # test of 10 known-good tickers mid-run returned in 0.25-0.7s each,
    # ruling that out. Lowering timeout to 5s cuts failure cost to ~1.1s
    # (measured) with zero effect on successful fetches.
    kwargs = {"interval": interval, "auto_adjust": False, "progress": False, "timeout": 5}
    if interval != "1d" and period.endswith("d") and period[:-1].isdigit():
        # 1-day safety buffer (found 2026-09-26): an EXACT N-day window can
        # land right on Yahoo's rolling cutoff and fail intermittently --
        # each ticker's "now" is computed a fraction of a second later than
        # the last in a sequential loop, so some land just past the edge
        # and some don't (confirmed: HEXT.NS at exactly 60d failed with
        # "must be within the last 60 days", 59d worked reliably). Losing
        # one extra day of history is a trivial cost for not riding the
        # boundary.
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=int(period[:-1]) - 1)
        kwargs["start"] = start
        kwargs["end"] = end
    else:
        kwargs["period"] = period

    raw = yf.download(ticker, **kwargs)
    if raw.empty:
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
        _fetch_cache[key] = df
        return df
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    ts_col = "Date" if "Date" in raw.columns else "Datetime"
    timestamps = raw[ts_col]
    if getattr(timestamps.dt, "tz", None) is not None:
        # Intraday fetches (15m/60m) come back tz-aware (exchange-local);
        # daily/resampled frames are tz-naive. Strip tz (not convert) so
        # formed_at comparisons across HTF/LTF frames work.
        timestamps = timestamps.dt.tz_localize(None)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": raw["Open"].astype(float),
        "high": raw["High"].astype(float),
        "low": raw["Low"].astype(float),
        "close": raw["Close"].astype(float),
    })
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    _fetch_cache[key] = df
    return df


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.set_index("timestamp")
    out = d.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna().reset_index()


def _build_frame(ticker: str, source: str, native_interval: str, period: str,
                  resample_rule: Optional[str], window: Optional[int]) -> pd.DataFrame:
    if source == "daily":
        df = _fetch(ticker, period="max", interval="1d")
    else:
        df = _fetch(ticker, period=period, interval=native_interval)

    if resample_rule:
        df = _resample(df, resample_rule)

    if window and len(df) > window:
        df = df.iloc[-window:].reset_index(drop=True)

    return df


def _zone_range(z: Zone) -> tuple:
    return (min(z.proximal_line, z.distal_line), max(z.proximal_line, z.distal_line))


def _zone_formed_at(df: pd.DataFrame, z: Zone):
    return df.iloc[z.leg_end_index]["timestamp"]


# User directive (2026-09-23): only take a demand-zone trade if price is in
# an uptrend, only a supply-zone trade if price is in a downtrend. Trend
# definition below is a PLACEHOLDER -- user said "for now put any logic
# suitable, I'll give you the full logic later." Using a plain close-vs-
# moving-average check on the HTF timeframe (the "overall bias" timeframe
# per this module's own golden rule), assessed at the HTF zone's own
# formation moment (leg_end_index), since that's when the directional bias
# is set. Swap TREND_MA_PERIOD/classify_trend out once the real rule lands
# -- nothing else in this module depends on how trend is computed.
TREND_MA_PERIOD = 50


def classify_trend(df: pd.DataFrame, idx: int, ma_period: int = TREND_MA_PERIOD) -> Optional[str]:
    if idx < ma_period - 1 or idx >= len(df):
        return None
    ma = df["close"].iloc[idx - ma_period + 1: idx + 1].mean()
    close = df.iloc[idx]["close"]
    if close > ma:
        return "up"
    if close < ma:
        return "down"
    return None


def filter_zones_by_trend(zones: List[Zone], df: pd.DataFrame) -> List[Zone]:
    """Drop any zone that doesn't match the golden rule: demand only in an
    uptrend, supply only in a downtrend (trend assessed at the zone's own
    leg_end_index). A zone is also dropped if there isn't enough history
    yet to classify trend (classify_trend returns None)."""
    kept = []
    for z in zones:
        trend = classify_trend(df, z.leg_end_index)
        if trend is None:
            continue
        if (z.type == "demand" and trend == "up") or (z.type == "supply" and trend == "down"):
            kept.append(z)
    return kept


# =============================================================================
# Trend v2 -- three-timeframe, zone-break-based (user directive, 2026-09-23)
# =============================================================================
# Replaces the close-vs-MA placeholder above. Trend is now read off a THIRD,
# intermediate timeframe (one step below HTF, one step above LTF -- see
# ComboSpec.trend_* fields / COMBOS): DIT trend=2h, WIT trend=daily,
# MIT trend=weekly.
#
# User's rule, as given: "trend is decided if price breaks dz/sz -- if price
# breaks 2 sz then it's in uptrend, if it breaks 2 dz it's in downtrend, 1
# then sideways... if price is at all time high it's obviously uptrend, then
# if it breaks 2 dz in the intermediate timeframe the trend changes."
#
# Interpretation (this is a first pass -- user said they'll give the full
# logic later, this is deliberately simple and documented so it's easy to
# swap out):
#   - Breaking a SUPPLY zone (price closes above its distal, i.e. through
#     the resistance) is a bullish event. Breaking a DEMAND zone (closes
#     below its distal, through support) is bearish. This reuses the exact
#     same "closed beyond distal" definition as is_zone_invalidated in
#     sd_zones.py, just tracking the break's timestamp instead of a bool.
#   - A fresh all-time-high (as of the query moment, on the trend
#     timeframe's own close series) is an unconditional "up" -- matches
#     "if price is at all time high it's obviously uptrend" directly.
#   - Otherwise, walk every zone-break event on the trend timeframe in
#     chronological order up to the query moment, keeping a streak counter:
#     consecutive same-direction breaks accumulate, a break in the other
#     direction resets the streak to 1. Two in a row confirms/flips the
#     state ("if price breaks 2 sz then uptrend... 1 then sideways" -- one
#     break alone isn't enough evidence, it takes two of the same kind).
#   - Before any streak of 2 is ever reached, state is "sideways".


def _find_invalidation_ts(df: pd.DataFrame, zone: Zone):
    """First timestamp (strictly after the zone's own leg) where price
    CLOSED beyond the zone's distal line -- i.e. broke it. Vectorized
    (2026-09-25 perf fix): the original .iloc-in-a-Python-loop version,
    combined with classify_trend_3tf recomputing this for every trend zone
    on EVERY HTF-zone query (see _compute_trend_events below), caused a
    real multi-hour hang on the medium-universe backtest -- TREND_ZONE_
    CONFIG is deliberately loose and finds many zones, so this was O(HTF
    zones x trend zones x bars) repeated from scratch each time."""
    start = zone.leg_end_index + 1
    if start >= len(df):
        return None
    closes = df["close"].to_numpy()[start:]
    hits = np.nonzero(closes < zone.distal_line)[0] if zone.type == "demand" else np.nonzero(closes > zone.distal_line)[0]
    if len(hits) == 0:
        return None
    return df["timestamp"].to_numpy()[start + hits[0]]


def _compute_trend_events(trend_df: pd.DataFrame, trend_zones: List[Zone]):
    """All zone-break events on the trend timeframe, sorted chronologically.
    Computed ONCE per (trend_df, trend_zones) pair -- filter_zones_by_
    trend_3tf reuses this across every HTF zone it queries instead of
    recomputing from scratch each time (see _find_invalidation_ts note)."""
    events = []
    for z in trend_zones:
        inv_ts = _find_invalidation_ts(trend_df, z)
        if inv_ts is not None:
            events.append((pd.Timestamp(inv_ts), "up" if z.type == "supply" else "down"))
    events.sort(key=lambda e: e[0])
    return events


def _classify_trend_from_events(trend_df: pd.DataFrame, events: list, query_ts) -> Optional[str]:
    """Same rule as classify_trend_3tf, but takes precomputed events (see
    _compute_trend_events) instead of recomputing them -- this is the
    actual hot path filter_zones_by_trend_3tf uses."""
    query_ts = pd.Timestamp(query_ts)
    mask = trend_df["timestamp"] <= query_ts
    if not mask.any():
        return None
    sub = trend_df.loc[mask]

    # Fresh all-time-high override.
    if sub["close"].iloc[-1] >= sub["close"].max():
        return "up"

    # Corrected 2026-09-24 (from BAJFINANCE mismatch): a single break AGAINST
    # a CONFIRMED trend immediately downgrades it to sideways -- it doesn't
    # just tally toward a future flip while the old confirmed state lingers.
    # "u check what did it do -- did it come back and run from the most
    # recent dz, if yes uptrend continues, if it broke a dz then sideways."
    # From sideways, it still takes 2 CONSECUTIVE same-direction breaks to
    # (re)confirm a real trend ("if price breaks 2 sz then uptrend").
    state = "sideways"
    pending_dir = None
    pending_count = 0
    for ts, direction in events:
        if ts > query_ts:
            break
        if state == direction:
            # reinforces the already-confirmed trend
            pending_dir, pending_count = None, 0
            continue
        if state == "sideways":
            pending_count = pending_count + 1 if direction == pending_dir else 1
            pending_dir = direction
            if pending_count >= 2:
                state = direction
                pending_dir, pending_count = None, 0
        else:
            # break against a confirmed trend -> immediate downgrade
            state = "sideways"
            pending_dir, pending_count = direction, 1
    return state


def classify_trend_3tf(trend_df: pd.DataFrame, trend_zones: List[Zone], query_ts) -> Optional[str]:
    """Convenience wrapper for one-off queries (e.g. interactive debugging)
    -- recomputes events every call, which is fine for a single query but
    NOT what filter_zones_by_trend_3tf uses internally (it precomputes
    events once via _compute_trend_events and reuses them -- see there)."""
    events = _compute_trend_events(trend_df, trend_zones)
    return _classify_trend_from_events(trend_df, events, query_ts)


def filter_zones_by_trend_3tf(htf_zones: List[Zone], htf_df: pd.DataFrame,
                               trend_df: pd.DataFrame, trend_zones: List[Zone]) -> List[Zone]:
    """ASYMMETRIC rule (revised 2026-09-24 from 9 annotated chart examples --
    ONGC/BAJFINANCE/LAURUSLABS/KEI/ORIENTCEM/MASTEK/MAXHEALTH/MANAPPURAM/
    IKS): every single "good setup" example given was a DEMAND trade taken
    in either SIDEWAYS or UP trend (e.g. BAJFINANCE/MAXHEALTH/IKS all
    demand+sideways, MANAPPURAM demand+up). The only REJECTED example was a
    SUPPLY trade in a confirmed UPtrend (ONGC) -- "technically we shouldn't
    take this trade cuz trend is against". So sideways does NOT block
    either type -- a demand trade is only blocked by a confirmed
    DOWNtrend, a supply trade only by a confirmed UPtrend. This replaces
    the earlier symmetric "exact match only" version, which wrongly
    blocked every sideways-trend demand trade in these examples too.
    (No example of a supply trade in down/sideways was given, so that half
    is the natural symmetric completion, not directly evidenced -- flag if
    it turns out wrong.)
    Trend is assessed at the HTF zone's own formation moment (leg_end
    timestamp) via classify_trend_3tf on the intermediate timeframe."""
    events = _compute_trend_events(trend_df, trend_zones)  # computed ONCE, not per HTF zone
    kept = []
    for z in htf_zones:
        formed_ts = _zone_formed_at(htf_df, z)
        trend = _classify_trend_from_events(trend_df, events, formed_ts)
        if trend is None:
            continue
        if z.type == "demand" and trend != "down":
            kept.append(z)
        elif z.type == "supply" and trend != "up":
            kept.append(z)
    return kept


def _htf_wick_tested_at(htf_df: pd.DataFrame, hz: Zone):
    """First timestamp after the HTF zone's own leg where price reaches the
    base's TRUE WICK extreme -- not just the (possibly tighter) body-based
    proximal line the zone actually trades off of. User directive
    (2026-09-30, USHAMART MIT case): HTF zones are deliberately never built
    wick-to-wick (see detect_zones' allow_wick_to_wick), so proximal can sit
    well inside the base's real wick (confirmed case: USHAMART's Sept-2024
    base candle has body-based proximal=357.50 but its own wick reaches
    371.70 -- Nov-2024 dipped to 363.70, missing the tighter proximal but
    still landing inside the base's real wick range). A touch anywhere in
    that wider wick range still consumes the level's pending orders even
    though it wouldn't count as a proximal touch, so freshness/already-
    tapped checks must use this wider measure, not Zone.tested_at_timestamp
    (which is proximal-based). The CURRENT entry's own triggering touch is
    still allowed if it's the same visit that first reaches this wick
    extreme -- only a genuinely earlier, separate touch invalidates."""
    base = htf_df.iloc[hz.base_start_index:hz.base_end_index + 1]
    wick_extreme = base["high"].max() if hz.type == "demand" else base["low"].min()
    start = hz.leg_end_index + 1
    if start >= len(htf_df):
        return None
    sub = htf_df.iloc[start:]
    if hz.type == "demand":
        hits = sub.index[sub["low"] <= wick_extreme]
    else:
        hits = sub.index[sub["high"] >= wick_extreme]
    if len(hits) == 0:
        return None
    return htf_df.loc[hits[0], "timestamp"]


def match_zones(htf_zones: List[Zone], htf_df: pd.DataFrame,
                 ltf_zones: List[Zone], ltf_df: pd.DataFrame,
                 ltf_states: dict, trend_df: pd.DataFrame = None,
                 trend_events: list = None) -> List[dict]:
    """One result per HTF zone (the best candidate LTF zone, if any) -- not
    one result per (HTF, LTF) pair. An LTF zone only qualifies if:
      1. it's the same zone type as the HTF zone,
      2. its own leg closed DURING the HTF zone's own formation window
         (base_start date through leg_end date) -- it's the LTF-resolution
         view of the same move, not a later retest,
      3. it was STILL FRESH (untested) as of the moment the HTF zone's own
         bar finished forming -- see `confirm_cutoff` below. A zone that
         already got tapped before the HTF confirmed is a stale setup by
         the time the HTF bias exists, even if it formed inside the window.
      4. at least MIN_LTF_OVERLAP_FRAC of its own range overlaps the HTF
         zone's range.
      5. (if trend_df/trend_events given) trend is NOT against the zone's
         direction at the moment the LTF entry actually triggers -- see the
         "trend re-check at entry" block below.
    Among valid candidates, the most recently formed one wins (closest to
    the HTF's own confirmation), with overlap fraction as a tiebreaker."""
    matches = []
    for hz in htf_zones:
        h_lo, h_hi = _zone_range(hz)
        h_base_start = htf_df.iloc[hz.base_start_index]["timestamp"]
        h_leg_end = _zone_formed_at(htf_df, hz)
        window_start = pd.Timestamp(h_base_start).normalize()
        window_end = pd.Timestamp(h_leg_end).normalize()

        # The last actual LTF candle at/before the HTF zone's own bar period
        # ends -- i.e. "by the moment the HTF candle finished forming."
        # Using this (not window_end's midnight label) means a tap that
        # happens during the HTF bar's own session still correctly counts
        # as "tested before confirmation."
        same_period = ltf_df["timestamp"].dt.normalize() <= window_end
        confirm_cutoff = ltf_df.loc[same_period, "timestamp"].max() if same_period.any() else window_end

        candidates = []
        for lz in ltf_zones:
            if lz.type != hz.type:
                continue
            l_lo, l_hi = _zone_range(lz)
            l_height = l_hi - l_lo
            if l_height <= 0:
                continue
            l_formed = _zone_formed_at(ltf_df, lz)
            l_formed_date = pd.Timestamp(l_formed).normalize()
            if not (window_start <= l_formed_date <= window_end):
                continue  # must form during the HTF zone's own formation, not after it

            if lz.tested_at_timestamp is not None and pd.Timestamp(lz.tested_at_timestamp) <= confirm_cutoff:
                continue  # already tapped before HTF confirmed -- stale, not a live concurrent entry

            overlap = min(h_hi, l_hi) - max(h_lo, l_lo)
            overlap_frac = overlap / l_height
            if overlap_frac < MIN_LTF_OVERLAP_FRAC:
                continue

            candidates.append((overlap_frac, l_formed, lz))

        if not candidates:
            continue

        # most recently formed (closest to HTF confirmation) first; ties
        # broken by price-overlap fraction
        candidates.sort(key=lambda c: (c[1], c[0]), reverse=True)
        best_overlap_frac, best_formed, best_lz = candidates[0]

        # New rule (2026-09-27, user directive from BPCL/RAILTEL; WIDENED
        # 2026-09-30 to use the base's true wick extreme, not just the
        # body-based proximal -- see _htf_wick_tested_at): if the HTF zone
        # had ALREADY been tapped on its own timeframe -- once, earlier --
        # before this LTF trade's own entry actually triggers, the HTF bias
        # is stale, not fresh, and the pairing doesn't count even though it
        # happened to still work out ("u got lucky"). This is different from
        # the confirm_cutoff freshness check above (which guards the LTF
        # zone); this guards the HTF zone itself. The concurrent first-ever
        # touch of the HTF zone (which is normally WHAT the LTF entry
        # actually is, since the LTF zone sits inside the HTF zone's own
        # range) is allowed -- only an EARLIER, separate touch invalidates
        # it. Skipped if the LTF trade never actually triggers (tested_at_
        # index is None -- still a pending/live setup, not a backtest-
        # countable trade yet).
        htf_wick_test_ts = _htf_wick_tested_at(htf_df, hz)
        if htf_wick_test_ts is not None and best_lz.tested_at_index is not None:
            htf_test_date = pd.Timestamp(htf_wick_test_ts).normalize()
            entry_date = pd.Timestamp(ltf_df.iloc[best_lz.tested_at_index]["timestamp"]).normalize()
            if htf_test_date < entry_date:
                continue

        # New rule (2026-09-28, user directive from ACE MIT: HTF formed
        # 2024-02-29 but the LTF entry didn't trigger until 2026-01-16 --
        # almost 2 years later, "trend is wayyy down" by the time it
        # actually fired). filter_zones_by_trend_3tf only ever checks trend
        # ONCE, at the HTF zone's own formation moment -- if the LTF entry
        # trigger comes much later, trend can have completely flipped in
        # the gap and the original bias is stale. Re-check trend at the
        # ACTUAL entry moment and drop the trade if it's now against the
        # zone's direction (same asymmetric rule as filter_zones_by_trend_3tf:
        # demand blocked only by a confirmed down, supply only by up).
        # Skipped (no-op) if the caller doesn't pass trend data, or the
        # trade never actually triggers.
        if trend_df is not None and trend_events is not None and best_lz.tested_at_index is not None:
            entry_ts = ltf_df.iloc[best_lz.tested_at_index]["timestamp"]
            trend_at_entry = _classify_trend_from_events(trend_df, trend_events, entry_ts)
            if trend_at_entry is not None:
                if hz.type == "demand" and trend_at_entry == "down":
                    continue
                if hz.type == "supply" and trend_at_entry == "up":
                    continue

        matches.append({
            "type": hz.type,
            "htf_proximal": hz.proximal_line,
            "htf_distal": hz.distal_line,
            "htf_formed_at": h_leg_end,
            "ltf_proximal": best_lz.proximal_line,
            "ltf_distal": best_lz.distal_line,
            "ltf_formed_at": best_formed,
            "ltf_state": ltf_states[id(best_lz)],
            "overlap_frac_of_ltf": best_overlap_frac,
            # index into ltf_df where this zone was first touched (the
            # backtest's entry trigger) -- None if never touched in the
            # available LTF history (signal never actually fires a trade).
            "ltf_tested_at_index": best_lz.tested_at_index,
            # Quality signal, not a filter (see Zone.has_strong_legout) --
            # gap-open or a 2nd strong candle on the leg, HTF and LTF side.
            "htf_strong_legout": hz.has_strong_legout,
            "ltf_strong_legout": best_lz.has_strong_legout,
        })
    return matches


def find_mtf_setups(ticker: str, combo: ComboName, live_only: bool = True) -> List[dict]:
    spec = COMBOS[combo]

    htf_df = _build_frame(ticker, spec.htf_source, spec.htf_interval,
                           spec.ltf_fetch_period, spec.htf_resample, spec.htf_window)
    ltf_df = _build_frame(ticker, spec.ltf_source, spec.ltf_interval,
                           spec.ltf_fetch_period, spec.ltf_resample, spec.ltf_window)

    if len(htf_df) < 20 or len(ltf_df) < 20:
        return []

    # allow_wick_to_wick=False: HTF is bias/context, never the execution
    # timeframe -- see detect_zones' docstring (user directive, 2026-09-27).
    htf_zones = detect_zones(htf_df, config=spec.htf_config, allow_wick_to_wick=False)

    trend_df = _build_frame(ticker, spec.trend_source, spec.trend_interval,
                             spec.trend_fetch_period, spec.trend_resample, spec.trend_window)
    trend_events = None
    if len(trend_df) >= 20:
        trend_zones = detect_zones(trend_df, config=spec.trend_config, allow_wick_to_wick=False)
        trend_events = _compute_trend_events(trend_df, trend_zones)
        htf_zones = filter_zones_by_trend_3tf(htf_zones, htf_df, trend_df, trend_zones)
    else:
        htf_zones = []

    ltf_zones = detect_zones(ltf_df, config=spec.ltf_config)

    ltf_atr = wilder_atr(ltf_df)
    ltf_states = {id(z): classify_zone_state(ltf_df, z, atr=ltf_atr) for z in ltf_zones}

    if live_only:
        htf_zones = [z for z in htf_zones if not is_zone_invalidated(htf_df, z)]
        ltf_zones = [z for z in ltf_zones if ltf_states[id(z)] is not None]

    results = match_zones(htf_zones, htf_df, ltf_zones, ltf_df, ltf_states,
                           trend_df=trend_df, trend_events=trend_events)
    for r in results:
        r["ticker"] = ticker
        r["combo"] = combo
        r["current_price"] = float(ltf_df.iloc[-1]["close"])
    return results


def scan_universe(combo: ComboName, tickers: List[str], limit: int, live_only: bool = False,
                   exclude_tickers: Optional[set] = None) -> List[dict]:
    all_results = []
    for ticker in tickers:
        if exclude_tickers and ticker in exclude_tickers:
            continue
        try:
            all_results.extend(find_mtf_setups(ticker, combo, live_only=live_only))
        except Exception as e:
            print(f"  [{combo}] {ticker}: ERROR {e}")

    # Dedup near-identical HTF zones -- sd_zones.py's leg detection can
    # occasionally produce two overlapping legs that walk back to the same
    # base (same proximal/distal, different leg_end dates), which otherwise
    # shows as the "same" setup twice under different HTF-formed dates
    # (confirmed case: JUBLINGREA WIT showing 605.00/537.30 under both
    # 12-Apr and 26-Apr). Keep the most-recently-confirmed instance.
    all_results.sort(key=lambda r: r["htf_formed_at"], reverse=True)
    seen = set()
    deduped = []
    for r in all_results:
        key = (r["ticker"], r["type"], round(r["htf_proximal"], 2), round(r["htf_distal"], 2))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    all_results = deduped

    # most recently formed HTF zone first; among ties, live LTF zones
    # (reacting/approaching) surface above historical/used-up ones.
    state_rank = {"reacting": 0, "approaching": 1}
    all_results.sort(key=lambda r: (-r["htf_formed_at"].value, state_rank.get(r["ltf_state"], 2)))
    return all_results[:limit]


def _fmt(r: dict) -> str:
    def ts(v):
        return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")

    risk = abs(r["ltf_proximal"] - r["ltf_distal"])
    state = r["ltf_state"] or "historical/used-up"
    return (
        f"{r['ticker'].replace('.NS','')} [{r['combo'].upper()}] {r['type'].upper()} -- {state}\n"
        f"  HTF formed: {ts(r['htf_formed_at'])}\n"
        f"  HTF bias zone : proximal={r['htf_proximal']:.2f}  distal={r['htf_distal']:.2f}\n"
        f"  LTF entry zone: proximal={r['ltf_proximal']:.2f}  distal={r['ltf_distal']:.2f}"
        f"  risk={risk:.2f}  (formed {ts(r['ltf_formed_at'])})\n"
        f"  current price={r['current_price']:.2f}  LTF-in-HTF overlap={r['overlap_frac_of_ltf']*100:.0f}%"
    )


if __name__ == "__main__":
    reference_tickers = ["BHARTIARTL.NS", "MASTEK.NS", "MANAPPURAM.NS", "KEI.NS", "MAXHEALTH.NS", "CAMS.NS"]
    universe = sorted(set(NIFTY50 + EXTENDED + reference_tickers))

    # Already shown to the user in the previous (pre-fix) run -- excluded
    # so this pass surfaces genuinely new tickers, not repeats.
    already_shown = {
        "dit": {"TCS.NS", "GRASIM.NS", "JUBLINGREA.NS", "LT.NS", "MAXHEALTH.NS", "IFCI.NS",
                "PFIZER.NS", "BHARATFORG.NS", "BHARTIARTL.NS", "FEDERALBNK.NS"},
        "wit": {"GRASIM.NS", "JUBLINGREA.NS", "NESTLEIND.NS", "ASIANPAINT.NS"},
        "mit": {"ONGC.NS", "WIPRO.NS", "JPPOWER.NS", "EICHERMOT.NS", "MASTEK.NS"},
    }

    wanted = {"dit": 5, "wit": 5, "mit": 5}

    for combo, limit in wanted.items():
        print(f"\nScanning {len(universe)} tickers for {combo.upper()}...")
        top = scan_universe(combo, universe, limit, exclude_tickers=already_shown[combo])
        print(f"=== Top {len(top)} {combo.upper()} trades ===")
        for r in top:
            print(_fmt(r))
            print()
