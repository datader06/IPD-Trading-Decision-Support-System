"""
sd_zones.py

Supply & Demand zone detection on OHLC candlestick data, following an
institutional "impulsive leg -> base -> zone" methodology.

Modular by design:
    - wilder_atr            : ATR (Wilder smoothing)
    - find_impulsive_legs    : locate impulsive (explosive) legs, up or down
    - walk_back_base         : walk backward from a leg to find its base
    - construct_zone         : build proximal/distal lines from a base
    - validity filters        : base_range check + clean-departure check
    - apply_freshness         : forward-scan to mark fresh/tested
    - detect_zones             : orchestrates all of the above -> list[Zone]

All thresholds live on a `ZoneConfig` dataclass so they can be tuned
independently, and per-timeframe (daily/weekly/monthly all behave
differently relative to their own ATR) without touching function internals.
`DEFAULT_CONFIG` mirrors the original single-profile thresholds;
`MONTHLY_CONFIG` is a looser profile for monthly candles (see its docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Literal

import pandas as pd
import numpy as np


ZoneType = Literal["demand", "supply"]


@dataclass
class ZoneConfig:
    atr_period: int = 14
    impulse_body_atr_mult: float = 1.3       # body_size >= this * ATR to count as impulsive
    impulse_close_range_pct: float = 0.75     # close must be in top/bottom 25% of its range
    max_leg_candles: int = 3                  # allow 1-3 consecutive impulsive candles per leg
    base_body_atr_mult: float = 0.5           # base candle body_size <= this * ATR
    max_base_candles: int = 3
    max_base_range_to_leg_range: float = 0.5  # base_range <= this * leg_range
    min_zone_width_atr_mult: float = 0.5      # proximal-distal width >= this * ATR (reject noise-tight zones)
    departure_tolerance_atr_mult: float = 0.0  # leg candles may dip this many ATRs past distal before "clean departure" fails
    base_extension_atr_mult: float = float("inf")  # cap on how much each new base candle may grow the base's own range -- see walk_back_base
    # User directive (2026-09-26): "keep some gap between the wick and the
    # SL... a lot of times the zone just gets swept and then the rally
    # comes." Small buffer pushing distal a bit further past the base's raw
    # wick, applied uniformly (not tuned per-config -- "no rule as such,
    # just a little"). See construct_zone.
    distal_buffer_atr_mult: float = 0.1
    # Gap threshold for Zone.has_strong_legout's gap-open check (see
    # _has_strong_legout). User directive (2026-09-26): backtest showed
    # HTF-side strong legout correlates with much better P&L (+Rs 277/trade
    # vs -Rs 82/trade), but only ~22% of zones qualified under the strict
    # 1.0x ATR gap bar -- "implement this but not too restrictive, increase
    # the boundary of htf legout but not too much." Halved (not zeroed) for
    # WEEKLY_CONFIG/MONTHLY_CONFIG (the configs used in the HTF role across
    # all combos) so more zones qualify without flagging every candle as
    # "strong". DEFAULT_CONFIG (and LTF_ENTRY_CONFIG, which derives from it)
    # stays at the original 1.0 -- the LTF-side signal didn't show the same
    # correlation, so it's left untouched.
    legout_gap_atr_mult: float = 1.0
    # Cap on a SINGLE base candle's own high-low range (not just its body),
    # relative to ATR. User directive (2026-09-28, from AUBANK/BEL/CCL/
    # BOSCHLTD MIT feedback -- "sl should've been tighter cuz of the base
    # candle", "base candle wick is too damn huge"): walk_back_base already
    # capped how much EACH ADDITIONAL candle could grow the base's range
    # (base_extension_atr_mult), but that check only ever applied once a
    # second candle joined -- the very first (nearest) candle's own range
    # was never checked at all, only its body. A small-bodied candle with
    # huge wicks both ways (real cases: AUBANK May-2025 body=0.14x ATR but
    # range=0.63x ATR; CCL Oct-2024 body=0.33x but range=1.11x ATR) sailed
    # through as a single-candle "base" and dragged the distal (SL) line
    # out to that candle's raw wick. +inf here is a no-op (matches prior
    # behavior); set explicitly on WEEKLY_CONFIG/MONTHLY_CONFIG below.
    base_candle_max_range_atr_mult: float = float("inf")
    # EXPERIMENTAL, default OFF (2026-10-01, WIT review screenshots): when
    # True, a zone is REJECTED if the consolidation before its leg is longer
    # than max_base_candles -- counted by base_run_count (flexible: small
    # candles plus "exciting" candles that close inside the small-candle
    # band), not by the strict walk_back_base test, which truncates.
    reject_long_base: bool = False
    base_body_range_frac: float = 0.5   # "small" candle: body <= this * its own high-low range
    # User directive (2026-09-29, from GTF reference notes; MADE PERMANENT
    # 2026-09-29 after isolated backtesting on DIT/WIT/MIT full-universe
    # data). "Legout candle should be closed above legin" (p.24) -- the
    # candle that closes the impulsive leg must CLOSE beyond the legin
    # candle's own range (not just clear the body/ATR impulsive bar), or the
    # zone is invalid. "Legin" = the single candle immediately preceding the
    # base (base_start_index - 1) -- the leg-IN, as distinct from the leg
    # OUT this codebase already calls "leg". See _detect_zones_one_direction.
    # Default stays False here (DEFAULT_CONFIG/HTF/trend configs are
    # unaffected -- this was only ever meant for the LTF/execution role,
    # see LTF_ENTRY_CONFIG in mtf_zones.py, which sets this True).
    # Isolated test results (full 504-ticker universe, vs the pre-rule
    # baseline): DIT n=308->281 (45.8%->45.6% win, Rs88,225->Rs78,096),
    # WIT n=41->44 (51.2%->52.3% win, Rs20,581->Rs22,696), MIT n=27->26
    # (44.4%->46.2% win, Rs8,946->Rs9,938) -- net positive/neutral on all
    # three, unlike the companion rule below which was tested and rejected.
    # CONFIRMED PERMANENT (2026-09-30) via the real production code path on
    # a fresh full-universe run: DIT n=297/45.8%/Rs84,563, WIT n=45/51.1%/
    # Rs21,697, MIT n=27/44.4%/Rs8,946 -- see mtf_zones.LTF_ENTRY_CONFIG's
    # comment for why these differ slightly from the isolated numbers above
    # (day-to-day data drift + transient fetch dropouts, not a bug -- both
    # verified by direct inspection). These confirmed numbers are the
    # standing baseline going forward.
    require_legout_beyond_legin: bool = False
    # REJECTED (2026-09-29): a companion rule was tested alongside the one
    # above -- "if the legin candle's own wick is more extreme than the
    # base's wick, use the legin's wick for the distal line instead"
    # (GTF notes p.18-21, "exceptional marking"). Isolated full-universe
    # backtesting showed it net HURT DIT (Rs88,225->Rs73,313) and WIT
    # (Rs20,581->Rs11,982), only helping MIT -- rejected as a net negative
    # across combos. Deliberately removed rather than left as a disabled
    # flag, so it can't be silently re-enabled later. If revisiting this
    # idea, re-derive it from scratch rather than re-adding this exact
    # flag/logic -- see git history / conversation log for the original
    # implementation in _detect_zones_one_direction if needed for reference.


# Default profile -- tuned and validated against daily NSE/Nifty50 charts.
# impulse_body_atr_mult lowered 1.5 -> 1.3 (2026-09-19): four tickers turned
# up genuine-looking breakout candles rejected by a hair under 1.5x --
# SBICARD (1.42x, 1.39x), ICICIBANK (1.44x), GRASIM weekly (1.49x),
# BAJAJFINSV weekly (1.45x, 1.33x) -- all with close_pos well above 0.75.
# User confirmed via the same reasoning already applied to MONTHLY_CONFIG
# (which needed 1.0x for the same smoothing-driven near-miss pattern).
# Re-verify previously-confirmed zones after this change; if any regress,
# this needs to be revisited rather than silently kept.
DEFAULT_CONFIG = ZoneConfig()

# Monthly candles smooth out ~20 trading days of intra-month volatility, so a
# real breakout month's body/ATR ratio runs systematically lower than a daily
# breakout candle's ratio. Confirmed genuine HTF leg-outs landing in the
# 1.0-1.15x band: Eicher Motors Jul-2026 (1.05x), Bharti Airtl Mar-2025
# (1.14x), ONGC Jan-2026 (1.01x) -- all clean breakout months with close in
# the outer 25% of range, all missed at 1.5x and even at 1.2x. Leave the
# close_pos>=0.75 bar untouched as the quality filter; loosen only the body
# bar for monthly.
#
# User directive (2026-09-19, after reviewing ~40 hand-marked HTF charts,
# many sector indices): on weekly/monthly it's fine for the base/zone to be
# wide -- these are used for HTF context, with the actual tight entry taken
# on daily. So max_base_candles and max_base_range_to_leg_range are loosened
# for monthly/weekly relative to daily's validated tight-base thresholds.
# Daily DEFAULT_CONFIG is untouched -- it's the one used for actual entries
# and stays strict.
# min_zone_width_atr_mult loosened 0.5 -> 0.4 on both HTF configs: confirmed
# case is POWERGRID weekly, week of 2026-02-08 (body=3.16x ATR, close_pos
# 0.98 -- an obvious breakout, clean 3-week base Jan18-Feb1 beforehand).
# zone_width/ATR came out to 0.45 -- correctly constructed (proximal uses
# base body edges, not wicks) but rejected by a ~10% margin under the
# daily-calibrated 0.5x floor. User confirmed this zone by eye as clearly
# real and better than what the old floor was returning instead.
# departure_tolerance_atr_mult=0.25 on both HTF configs: same POWERGRID
# weekly case -- the Feb-2026 breakout candle's own low wicks 0.156 ATR
# under distal before closing at 98% of its range. That's a liquidity-sweep
# wick on the breakout candle itself, not the "choppy base, never really
# left" pattern the zero-tolerance rule exists to catch. 0.25x ATR covers
# this with margin while still rejecting real chop.
# max_base_candles=8 tried reverting to 3 on 2026-09-19 (theory: BAJAJFINSV
# weekly's 5-candle base looked padded with stale weeks) but that broke the
# already-confirmed TECHM monthly zone -- its correct distal (1304.10) comes
# from the 4th (oldest) base candle, which a max of 3 cuts off, distal
# recomputing to a worse 1327.30. The BAJAJFINSV issue needs a different
# explanation; capping candle count isn't it. Reverted back to 8.
#
# max_base_candles=8 -> 5 (2026-09-27, user directive from a large batch of
# annotated-chart corrections): repeated, independent complaints that the
# HTF base was reaching back too far and dragging the distal (SL) line with
# it -- HEROMOTOCO ("so many base candles... htf sl too big"), HUDCO (same
# pattern), NTPC ("too many base candles, put a restriction... maybe 5"),
# GRASIM ("keep a limit of 5 base candles in htf"). 5 sits above the earlier
# TECHM regression point (needs 4) so that confirmed case still holds, while
# actually capping the runaway 6-8 candle bases the complaints point at.
#
# base_extension_atr_mult=0.15 (2026-09-23): this IS the "different
# explanation" the note above was looking for. User flagged NTPC/TCS/UPL/
# HINDALCO monthly zones as reaching too far back for their proximal line
# (e.g. NTPC: algorithm walked base back to Jun-2025, proximal 340.45;
# user's chart says the real zone is just Dec-2025, proximal ~330). The
# problem isn't candle COUNT -- it's that walk_back_base only checked each
# candle's body in isolation, with no limit on how far the base's own
# high-low range could keep growing as more individually-small candles get
# absorbed. Diagnosed by computing, for each base candle added, how much it
# grows the base's accumulated range (in ATR terms): NTPC's 2nd candle
# (Nov-2025) grows the range by 0.21x ATR, TCS's 3rd candle by 0.35x ATR,
# UPL's 2nd candle by 0.27x ATR -- all clearly "reaching for a new area",
# not tightening. Verified this does NOT regress the confirmed cases:
# TECHM's needed 4-candle base only ever grows the range by up to 0.115x
# ATR per step (comfortably under 0.15), and POWERGRID's confirmed 3-week
# base is fully nested inside its own nearest candle's range (zero growth
# at every step) -- so a 0.15x ATR cap cuts off NTPC/TCS/UPL/HINDALCO
# without touching TECHM or POWERGRID at all. See walk_back_base().
MONTHLY_CONFIG = ZoneConfig(
    impulse_body_atr_mult=1.0,
    max_base_candles=5,
    max_base_range_to_leg_range=1.5,
    min_zone_width_atr_mult=0.4,
    departure_tolerance_atr_mult=0.25,
    base_extension_atr_mult=0.15,
    legout_gap_atr_mult=0.5,
)

# Weekly: base-width, min-width, and departure-tolerance allowances loosened,
# same reasoning as MONTHLY_CONFIG. max_base_candles=5, same reasoning above
# (reverting to 3 broke a confirmed case elsewhere on the same setting; 5 is
# the 2026-09-27 revision -- see MONTHLY_CONFIG's comment).
# base_extension_atr_mult=0.15: same fix as MONTHLY_CONFIG, same reasoning.
WEEKLY_CONFIG = ZoneConfig(
    max_base_candles=5,
    max_base_range_to_leg_range=1.5,
    min_zone_width_atr_mult=0.4,
    departure_tolerance_atr_mult=0.25,
    base_extension_atr_mult=0.15,
    legout_gap_atr_mult=0.5,
)


# --------------------------------------------------------------------------
# Backwards-compatible module-level constants (mirror DEFAULT_CONFIG)
# --------------------------------------------------------------------------
ATR_PERIOD = DEFAULT_CONFIG.atr_period
IMPULSE_BODY_ATR_MULT = DEFAULT_CONFIG.impulse_body_atr_mult
IMPULSE_CLOSE_RANGE_PCT = DEFAULT_CONFIG.impulse_close_range_pct
MAX_LEG_CANDLES = DEFAULT_CONFIG.max_leg_candles
BASE_BODY_ATR_MULT = DEFAULT_CONFIG.base_body_atr_mult
MAX_BASE_CANDLES = DEFAULT_CONFIG.max_base_candles
MAX_BASE_RANGE_TO_LEG_RANGE = DEFAULT_CONFIG.max_base_range_to_leg_range
MIN_ZONE_WIDTH_ATR_MULT = DEFAULT_CONFIG.min_zone_width_atr_mult


@dataclass
class Zone:
    type: ZoneType
    proximal_line: float
    distal_line: float
    base_start_index: int
    base_end_index: int
    leg_start_index: int
    leg_end_index: int
    fresh: bool = True
    tested_at_index: Optional[int] = None
    tested_at_timestamp: Optional[object] = None
    # Quality signal, NOT a filter (user directive, 2026-09-24, from
    # annotated chart examples repeatedly calling out "gap+decent legout" /
    # "2 legouts strong explosive" / "nice strong legout" on winning
    # setups): True if the leg either gapped open beyond ATR on its anchor
    # candle, or absorbed a second independently-impulsive candle (i.e. the
    # leg is 2+ candles long -- find_impulsive_legs' forward-absorption
    # already captures this). "It's okay if it isn't there" -- a zone
    # without this is still perfectly valid, this is purely a plus-point
    # flag for downstream scoring/ranking, never used to reject a zone.
    has_strong_legout: bool = False

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "proximal_line": self.proximal_line,
            "distal_line": self.distal_line,
            "base_start_index": self.base_start_index,
            "base_end_index": self.base_end_index,
            "leg_start_index": self.leg_start_index,
            "leg_end_index": self.leg_end_index,
            "fresh": self.fresh,
            "tested_at_index": self.tested_at_index,
            "tested_at_timestamp": self.tested_at_timestamp,
            "has_strong_legout": self.has_strong_legout,
        }


# --------------------------------------------------------------------------
# Step 0 — ATR
# --------------------------------------------------------------------------

def wilder_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Wilder-smoothed Average True Range.

    Returns a Series aligned to df.index. The first `period` values will be
    NaN (not enough data to seed the smoothing) -- callers should treat rows
    with NaN ATR as un-usable for zone detection.
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing == an EMA with alpha = 1/period, seeded by the
    # simple mean of the first `period` true-range values.
    atr = tr.copy()
    atr.iloc[:] = np.nan

    if len(tr) < period:
        return atr

    seed = tr.iloc[1:period + 1].mean()  # TR at index 0 is NaN (no prev close)
    atr.iloc[period] = seed
    for i in range(period + 1, len(tr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period

    return atr


# --------------------------------------------------------------------------
# Step 1 — impulsive legs
# --------------------------------------------------------------------------

def _is_impulsive_candle(row, atr_value: float, direction: ZoneType, config: ZoneConfig) -> bool:
    if atr_value is None or pd.isna(atr_value):
        return False

    body_size = abs(row["close"] - row["open"])
    candle_range = row["high"] - row["low"]
    if candle_range <= 0:
        return False

    if body_size < config.impulse_body_atr_mult * atr_value:
        return False

    if direction == "demand":
        if not (row["close"] > row["open"]):
            return False
        close_pos = (row["close"] - row["low"]) / candle_range
        return close_pos >= config.impulse_close_range_pct
    else:  # supply
        if not (row["close"] < row["open"]):
            return False
        close_pos = (row["high"] - row["close"]) / candle_range
        return close_pos >= config.impulse_close_range_pct


def _is_same_direction(row, direction: ZoneType) -> bool:
    if direction == "demand":
        return row["close"] > row["open"]
    else:
        return row["close"] < row["open"]


def _is_base_candidate(row, atr_value: float, config: ZoneConfig) -> bool:
    """True if this candle is small-bodied enough to be a base candle."""
    if atr_value is None or pd.isna(atr_value):
        return False
    body_size = abs(row["close"] - row["open"])
    return body_size <= config.base_body_atr_mult * atr_value


def find_impulsive_legs(df: pd.DataFrame, atr: pd.Series, direction: ZoneType,
                         config: ZoneConfig = DEFAULT_CONFIG) -> List[tuple]:
    """Scan the dataframe and return a list of (leg_start_idx, leg_end_idx)
    tuples describing impulsive legs (1-3 consecutive candles in the same
    direction).

    A leg is anchored on a candle that passes the strict single-candle
    impulsive test (body >= impulse_body_atr_mult*ATR, close in outer 25% of
    range), then greedily extended:
      - forward, absorbing subsequent candles that are themselves impulsive
      - backward, absorbing preceding same-direction candles whose body is
        too large to count as a "base" candle (> base_body_atr_mult*ATR) --
        these are candles that are clearly part of the same directional push
        but don't individually clear the impulsive bar. Without this, a real
        leg-out that starts with one merely-strong candle and finishes with
        one explosive candle gets orphaned: the strong candle is too big to
        be a base and too small to be "impulsive", so the backward
        base-walk stops on it and the whole zone is lost.
    Both directions are capped so a leg never exceeds config.max_leg_candles.
    """
    n = len(df)
    is_impulsive = np.zeros(n, dtype=bool)
    for i in range(n):
        is_impulsive[i] = _is_impulsive_candle(df.iloc[i], atr.iloc[i], direction, config)

    legs = []
    i = 0
    while i < n:
        if not is_impulsive[i]:
            i += 1
            continue
        start = i
        end = i
        while end + 1 < n and is_impulsive[end + 1] and (end - start + 1) < config.max_leg_candles:
            end += 1

        j = start - 1
        while j >= 0 and (end - j + 1) <= config.max_leg_candles:
            row_j = df.iloc[j]
            atr_j = atr.iloc[j]
            if atr_j is None or pd.isna(atr_j):
                break
            if _is_same_direction(row_j, direction) and not _is_base_candidate(row_j, atr_j, config):
                start = j
                j -= 1
            else:
                break

        legs.append((start, end))
        i = end + 1

    return legs


# --------------------------------------------------------------------------
# Step 2 — walk backward to find the base
# --------------------------------------------------------------------------

def base_run_count(df: pd.DataFrame, atr: pd.Series, leg_start_idx: int,
                   config: ZoneConfig, max_scan: int = 80) -> int:
    """Length of the consolidation right before the leg. A small candle
    (body <= base_body_range_frac of its range) always counts and widens the
    band; an exciting candle counts only if it closes inside the band of the
    small candles counted so far. Stops at the first candle that does
    neither. Used only by reject_long_base."""
    lo = hi = None
    n = 0
    j = leg_start_idx - 1
    while j >= 0 and n < max_scan:
        r = df.iloc[j]
        rng = r["high"] - r["low"]
        small = rng > 0 and abs(r["close"] - r["open"]) <= config.base_body_range_frac * rng
        if small:
            lo = r["low"] if lo is None else min(lo, r["low"])
            hi = r["high"] if hi is None else max(hi, r["high"])
        elif lo is None or not (lo <= r["close"] <= hi):
            break
        n += 1
        j -= 1
    return n


def walk_back_base(df: pd.DataFrame, atr: pd.Series, leg_start_idx: int,
                    config: ZoneConfig = DEFAULT_CONFIG) -> Optional[tuple]:
    """Starting at candle (leg_start_idx - 1), walk backward collecting up
    to config.max_base_candles small-bodied candles.

    A candle also has to pass a range-growth test: including it must not
    grow the base's own accumulated high-low range by more than
    config.base_extension_atr_mult * ATR beyond what's already there. A
    small body alone isn't enough -- a candle sitting well outside the
    range the nearer candles already established is reaching into a
    different area of price, not tightening the same coil (see
    MONTHLY_CONFIG/WEEKLY_CONFIG's base_extension_atr_mult comment for the
    evidence). The reference ATR is taken at leg_start_idx (the base's own
    period), and the check is skipped (falls back to prior behavior) if
    that ATR isn't available yet. DEFAULT_CONFIG's base_extension_atr_mult
    is +inf, so this is a no-op there -- daily entry-grade zones are
    unaffected.

    Returns (base_start_idx, base_end_idx) or None if there is no room
    before the leg (leg starts at index 0) or the immediately preceding
    candle already fails the small-body test.
    """
    if leg_start_idx == 0:
        return None

    ref_atr = atr.iloc[leg_start_idx]
    extension_cap =None if (ref_atr is None or pd.isna(ref_atr)) else config.base_extension_atr_mult * ref_atr
    single_candle_cap = (None if (ref_atr is None or pd.isna(ref_atr))
                          else config.base_candle_max_range_atr_mult * ref_atr)

    base_indices = []
    running_low = None
    running_high = None
    j = leg_start_idx - 1
    while j >= 0 and len(base_indices) < config.max_base_candles:
        atr_value = atr.iloc[j]
        if atr_value is None or pd.isna(atr_value):
            break
        row = df.iloc[j]
        body_size = abs(row["close"] - row["open"])
        if body_size > config.base_body_atr_mult * atr_value:
            break
        # A candle's own wick range can disqualify it as a base candle even
        # with a small body -- checked before it's ever added, so a single
        # wide-wicked candle can't become the whole base (see
        # base_candle_max_range_atr_mult).
        if single_candle_cap is not None and (row["high"] - row["low"]) > single_candle_cap:
            break

        new_low = row["low"] if running_low is None else min(running_low, row["low"])
        new_high = row["high"] if running_high is None else max(running_high, row["high"])
        if extension_cap is not None and running_low is not None:
            growth = (new_high - new_low) - (running_high - running_low)
            if growth > extension_cap:
                break

        running_low, running_high = new_low, new_high
        base_indices.append(j)
        j -= 1

    if not base_indices:
        return None

    base_indices.sort()
    return base_indices[0], base_indices[-1]


# --------------------------------------------------------------------------
# Step 3 — construct the zone
# --------------------------------------------------------------------------

def construct_zone(df: pd.DataFrame, base_start_idx: int, base_end_idx: int,
                    direction: ZoneType, use_wick_to_wick: bool = False,
                    distal_buffer: float = 0.0) -> tuple:
    """Return (proximal_line, distal_line) for the base candles
    [base_start_idx, base_end_idx] inclusive.

    use_wick_to_wick (user directive, 2026-09-26): normally proximal is
    body-to-wick (max/min of open/close -- the real body edge) while distal
    is already wick-based (low/high). For a zone with a confirmed strong
    legout (gap-open or a 2nd independently-impulsive candle -- see
    Zone.has_strong_legout), mark it wick-to-wick instead: proximal also
    uses the base's wick extreme, not just the body. Widens the zone:
    proximal moves away from distal, only ever increasing zone_width, so
    this can't cause a previously-valid zone to fail the min-width check.

    distal_buffer (user directive, 2026-09-26): "keep some gap between the
    wick and the SL -- don't stick the distal right to the base's wick,
    leave a little space, because a lot of times the zone just gets swept
    and then the rally comes." Small ATR-relative amount subtracted (demand)
    or added (supply) beyond the raw wick extreme, pushing the stop a
    little further out. Also only ever widens the zone (same reasoning:
    can't newly fail the min-width check)."""
    base = df.iloc[base_start_idx:base_end_idx + 1]

    if direction == "demand":
        if use_wick_to_wick:
            proximal_line = base["high"].max()
        else:
            proximal_line = max(base["open"].max(), base["close"].max())
        distal_line = base["low"].min() - distal_buffer
    else:  # supply
        if use_wick_to_wick:
            proximal_line = base["low"].min()
        else:
            proximal_line = min(base["open"].min(), base["close"].min())
        distal_line = base["high"].max() + distal_buffer

    return proximal_line, distal_line


# --------------------------------------------------------------------------
# Step 4 — validity filters
# --------------------------------------------------------------------------

def _leg_range(df: pd.DataFrame, leg_start_idx: int, leg_end_idx: int, direction: ZoneType) -> float:
    if direction == "demand":
        return df.iloc[leg_end_idx]["high"] - df.iloc[leg_start_idx]["low"]
    else:
        return df.iloc[leg_start_idx]["high"] - df.iloc[leg_end_idx]["low"]


def _has_strong_legout(df: pd.DataFrame, atr: pd.Series, leg_start_idx: int, leg_end_idx: int,
                        gap_atr_mult: float = 1.0) -> bool:
    """Quality signal (not a filter -- see Zone.has_strong_legout): True if
    the leg's anchor candle gapped open beyond gap_atr_mult*ATR versus the
    prior close, OR the leg absorbed a second candle (find_impulsive_legs'
    forward absorption already means leg_end_idx > leg_start_idx only when
    a second independently-impulsive candle followed). gap_atr_mult is
    ZoneConfig.legout_gap_atr_mult -- see there for why it's looser for
    HTF-role configs."""
    if leg_end_idx > leg_start_idx:
        return True
    if leg_start_idx == 0:
        return False
    atr_val = atr.iloc[leg_start_idx]
    if atr_val is None or pd.isna(atr_val):
        return False
    prev_close = df.iloc[leg_start_idx - 1]["close"]
    open_ = df.iloc[leg_start_idx]["open"]
    return abs(open_ - prev_close) > gap_atr_mult * atr_val


def _base_range(df: pd.DataFrame, base_start_idx: int, base_end_idx: int) -> float:
    base = df.iloc[base_start_idx:base_end_idx + 1]
    return base["high"].max() - base["low"].min()


def _is_clean_departure(df: pd.DataFrame, leg_start_idx: int, leg_end_idx: int,
                         distal_line: float, proximal_line: float, direction: ZoneType,
                         tolerance: float = 0.0) -> bool:
    """No leg candle should wick back into the base zone before/while
    departing. For demand: leg candle lows shouldn't dip under
    (distal_line - tolerance). For supply: leg candle highs shouldn't poke
    above (distal_line + tolerance). `tolerance` is an absolute price
    amount (caller converts from ATR multiples)."""
    leg = df.iloc[leg_start_idx:leg_end_idx + 1]
    if direction == "demand":
        return bool((leg["low"] >= distal_line - tolerance).all())
    else:
        return bool((leg["high"] <= distal_line + tolerance).all())


def _is_valid_zone(df: pd.DataFrame, atr: pd.Series, base_start_idx: int, base_end_idx: int,
                    leg_start_idx: int, leg_end_idx: int,
                    proximal_line: float, distal_line: float, direction: ZoneType,
                    config: ZoneConfig = DEFAULT_CONFIG) -> bool:
    leg_rng = _leg_range(df, leg_start_idx, leg_end_idx, direction)
    if leg_rng <= 0:
        return False

    base_rng = _base_range(df, base_start_idx, base_end_idx)
    if base_rng > config.max_base_range_to_leg_range * leg_rng:
        return False

    atr_ref = atr.iloc[leg_end_idx]
    departure_tolerance = 0.0 if pd.isna(atr_ref) else config.departure_tolerance_atr_mult * atr_ref
    if not _is_clean_departure(df, leg_start_idx, leg_end_idx, distal_line, proximal_line, direction,
                                tolerance=departure_tolerance):
        return False

    zone_width = abs(proximal_line - distal_line)
    if pd.isna(atr_ref) or zone_width < config.min_zone_width_atr_mult * atr_ref:
        return False

    return True


# --------------------------------------------------------------------------
# Step 5 — freshness tracking
# --------------------------------------------------------------------------

def apply_freshness(df: pd.DataFrame, zone: Zone) -> None:
    """Scan forward from the candle after the leg ends and mark the zone
    tested the first time price trades back into it. Mutates `zone` in
    place."""
    start_scan = zone.leg_end_index + 1
    for i in range(start_scan, len(df)):
        row = df.iloc[i]
        if zone.type == "demand":
            touched = row["low"] <= zone.proximal_line
        else:
            touched = row["high"] >= zone.proximal_line

        if touched:
            zone.fresh = False
            zone.tested_at_index = i
            if "timestamp" in df.columns:
                zone.tested_at_timestamp = df.iloc[i]["timestamp"]
            return


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _detect_zones_one_direction(df: pd.DataFrame, atr: pd.Series, direction: ZoneType,
                                 config: ZoneConfig, allow_wick_to_wick: bool = True) -> List[Zone]:
    zones: List[Zone] = []
    legs = find_impulsive_legs(df, atr, direction, config)

    for leg_start_idx, leg_end_idx in legs:
        base_range_idx = walk_back_base(df, atr, leg_start_idx, config)
        if base_range_idx is None:
            continue
        base_start_idx, base_end_idx = base_range_idx
        if config.reject_long_base and base_run_count(df, atr, leg_start_idx, config) > config.max_base_candles:
            continue

        strong_legout = _has_strong_legout(df, atr, leg_start_idx, leg_end_idx,
                                            gap_atr_mult=config.legout_gap_atr_mult)
        atr_ref = atr.iloc[leg_start_idx]
        distal_buffer = 0.0 if pd.isna(atr_ref) else config.distal_buffer_atr_mult * atr_ref
        proximal_line, distal_line = construct_zone(df, base_start_idx, base_end_idx, direction,
                                                     use_wick_to_wick=strong_legout and allow_wick_to_wick,
                                                     distal_buffer=distal_buffer)

        if config.require_legout_beyond_legin:
            legin_idx = base_start_idx - 1
            if legin_idx >= 0:
                legin_row = df.iloc[legin_idx]
                legout_close = df.iloc[leg_end_idx]["close"]
                if direction == "demand":
                    if legout_close <= legin_row["high"]:
                        continue
                else:
                    if legout_close >= legin_row["low"]:
                        continue

        if not _is_valid_zone(df, atr, base_start_idx, base_end_idx, leg_start_idx, leg_end_idx,
                               proximal_line, distal_line, direction, config):
            continue

        zone = Zone(
            type=direction,
            proximal_line=proximal_line,
            distal_line=distal_line,
            base_start_index=base_start_idx,
            base_end_index=base_end_idx,
            leg_start_index=leg_start_idx,
            leg_end_index=leg_end_idx,
            has_strong_legout=strong_legout,
        )
        apply_freshness(df, zone)
        zones.append(zone)

    return zones


def detect_zones(df: pd.DataFrame, atr_period: int = ATR_PERIOD,
                  config: ZoneConfig = DEFAULT_CONFIG,
                  allow_wick_to_wick: bool = True) -> List[Zone]:
    """Main entry point. Detects both demand and supply zones on `df`.

    df must have columns: timestamp, open, high, low, close.
    `config` selects the threshold profile -- use DEFAULT_CONFIG for
    daily/weekly, MONTHLY_CONFIG for monthly (see MONTHLY_CONFIG's comment).

    allow_wick_to_wick (user directive, 2026-09-27): "you're not supposed to
    keep HTF wick to wick ever, only execution timeframe gets wick to wick."
    Wick-to-wick construction (see construct_zone) is a property of the
    zone's ROLE (is this the timeframe being traded off of, or just context/
    bias?), not of which ZoneConfig profile detected it -- WEEKLY_CONFIG/
    MONTHLY_CONFIG are reused both as the HTF-context profile inside
    mtf_zones.py's DIT/WIT/MIT pairing AND as the execution-timeframe
    profile for the webapp's standalone weekly/monthly/quarterly/yearly
    scanner (see webapp/app.py's TIMEFRAMES dict), so the flag can't live on
    the config itself. Callers acting in an HTF or trend (non-execution)
    role must pass allow_wick_to_wick=False explicitly (see mtf_zones.py's
    find_mtf_setups / mtf_backtest.py's build_trades_for_ticker). Defaults
    to True so every other caller (standalone scans, LTF/execution zones)
    is unaffected.
    Returns a list of Zone objects (sorted by leg_start_index).
    """
    required_cols = {"open", "high", "low", "close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"df is missing required columns: {missing}")

    df = df.reset_index(drop=True)
    atr = wilder_atr(df, period=atr_period)

    demand_zones = _detect_zones_one_direction(df, atr, "demand", config, allow_wick_to_wick)
    supply_zones = _detect_zones_one_direction(df, atr, "supply", config, allow_wick_to_wick)

    all_zones = demand_zones + supply_zones
    all_zones.sort(key=lambda z: z.leg_start_index)
    return all_zones


APPROACH_MAX_ATR_MULT = 3.0  # "approaching" caps out at this many ATRs away from the zone


def is_zone_invalidated(df: pd.DataFrame, zone: Zone) -> bool:
    """True if price has ever CLOSED beyond the distal line after the zone
    formed -- i.e. the zone has been broken through, not merely touched.

    This is deliberately different from Zone.fresh/tested_at_index (from
    apply_freshness), which flips False on the very first touch of the
    proximal edge -- that's the right definition for the original
    methodology's backtest-style "is this zone still untouched" tracking,
    but too strict for a live scanner: a real zone can be tested multiple
    times and still be perfectly valid to react to, as long as price never
    closes through the distal (stop) line. Confirmed against user-supplied
    ground truth (e.g. POWERGRID monthly, KOTAKBANK yearly showing
    'reacting' despite prior touches) that repeated-test zones should still
    count.
    """
    start = zone.leg_end_index + 1
    if start >= len(df):
        return False
    after_close = df.iloc[start:]["close"]
    if zone.type == "demand":
        return bool((after_close < zone.distal_line).any())
    else:
        return bool((after_close > zone.distal_line).any())


def is_zone_used_up(df: pd.DataFrame, zone: Zone) -> bool:
    """True if, after the zone's first-ever touch, price fully closed back
    beyond the proximal line at some point strictly before the current
    (last) candle -- i.e. a complete touch-and-leave cycle already
    happened. A zone only gets one shot: once price has reacted and then
    genuinely left, a later return doesn't count as "reacting" or
    "approaching" again.

    Distinguishes a real repeat visit from ongoing presence in the zone:
    confirmed cases --
      - POWERGRID monthly: touched Aug-2026, closed inside the zone both
        Aug and Sep (never exited) -- one continuous visit, NOT used up,
        correctly still 'reacting'.
      - SBIN monthly: touched Mar-2026 (close 979.4, inside), then closed
        at 1068.45 in Apr-2026 -- clean exit above proximal -- then dipped
        back into the zone in Sep-2026. That's a genuine second visit and
        should NOT show as 'reacting' again. User: "once its tapped once
        then 2nd tap 3rd tap we dont consider."
    """
    if zone.tested_at_index is None:
        return False
    last_idx = len(df) - 1
    start = zone.tested_at_index + 1
    end = last_idx  # exclusive of the current/last candle
    if start >= end:
        return False
    between_close = df.iloc[start:end]["close"]
    if zone.type == "demand":
        return bool((between_close > zone.proximal_line).any())
    else:
        return bool((between_close < zone.proximal_line).any())


def classify_zone_state(df: pd.DataFrame, zone: Zone, atr: Optional[pd.Series] = None,
                         max_approach_atr_mult: float = APPROACH_MAX_ATR_MULT) -> Optional[str]:
    """Classify a zone's relationship to the most recent candle, for a
    scanner UI. A zone that's been invalidated (price closed through
    distal) or used up (see is_zone_used_up) never returns a state:

      - 'reacting': the latest candle's range overlaps the zone (low <=
        proximal and high >= distal for demand) -- price traded into the
        zone at some point during this candle. Uses the full range, not
        just the close, because the latest candle on a weekly/monthly/
        yearly chart is often still in progress: price can dip into the
        zone and rally back above it within the same still-forming candle
        (confirmed case: KOTAKBANK yearly -- 2026 candle's low dipped to
        345.5 into a zone at 308.77-381.80, then recovered to close at
        412.5; still a live "reacting" setup, not "approaching"). Ongoing/
        continuous presence since the first touch counts too (see
        is_zone_used_up) -- just not a touch-leave-return cycle.
      - 'approaching': the latest candle's low never reached the zone
        (stayed fully above proximal for demand), latest close is within
        `max_approach_atr_mult` ATRs of the proximal line. Without the
        distance cap, "approaching" would include zones from decades ago
        that price is now 10x away from. `atr` (pass wilder_atr(df)) is
        optional for backwards compatibility, but the cap is skipped
        (never filters) if it's not supplied.
      - None: invalidated, used up, or price is nowhere near the zone.
    """
    if len(df) == 0:
        return None
    if is_zone_invalidated(df, zone):
        return None
    if is_zone_used_up(df, zone):
        return None

    last_idx = len(df) - 1
    last_low = df.iloc[last_idx]["low"]
    last_high = df.iloc[last_idx]["high"]
    last_close = df.iloc[last_idx]["close"]

    # The candle that closes the impulsive leg IS the candle that forms the
    # zone -- it can't simultaneously be "reacting into" a zone its own
    # departure just created. Its low commonly sits near/under proximal
    # (the base is right there) without that being a real test; what
    # matters is where it closed. Confirmed bug case: BHARTIARTL daily,
    # leg closed today, low=1835.30 dipped under proximal=1844.00 but
    # closed at 1893.30 -- was wrongly showing 'reacting' on day one.
    on_formation_candle = last_idx == zone.leg_end_index

    def _within_approach_band(distance: float) -> bool:
        if atr is None:
            return True
        atr_ref = atr.iloc[last_idx]
        if atr_ref is None or pd.isna(atr_ref):
            return True
        return distance <= max_approach_atr_mult * atr_ref

    if zone.type == "demand":
        if not on_formation_candle and last_low <= zone.proximal_line and last_high >= zone.distal_line:
            return "reacting"
        still_outside = (last_close > zone.proximal_line) if on_formation_candle else (last_low > zone.proximal_line)
        if still_outside:
            if _within_approach_band(last_close - zone.proximal_line):
                return "approaching"
    else:  # supply
        if not on_formation_candle and last_high >= zone.proximal_line and last_low <= zone.distal_line:
            return "reacting"
        still_outside = (last_close < zone.proximal_line) if on_formation_candle else (last_high < zone.proximal_line)
        if still_outside:
            if _within_approach_band(zone.proximal_line - last_close):
                return "approaching"

    return None


def is_new_zone(df: pd.DataFrame, zone: Zone, recent_candles: int = 3) -> bool:
    """True if the zone's leg closed within the last `recent_candles` bars."""
    if len(df) == 0:
        return False
    last_idx = len(df) - 1
    return (last_idx - zone.leg_end_index) <= recent_candles


def zones_to_dicts(zones: List[Zone]) -> List[dict]:
    return [z.as_dict() for z in zones]


def zones_to_dataframe(df: pd.DataFrame, zones: List[Zone]) -> pd.DataFrame:
    """Flatten zones into a table with human-readable timestamps, suitable
    for exporting to Excel/CSV.

    'formed_at' = timestamp of the candle that closes the impulsive leg --
    i.e. the moment the zone becomes confirmed/tradeable (leg_end_index).
    """
    has_ts = "timestamp" in df.columns

    def ts(idx: int):
        return df.iloc[idx]["timestamp"] if has_ts else idx

    rows = []
    for z in zones:
        rows.append({
            "type": z.type,
            "entry_proximal": z.proximal_line,
            "stop_distal": z.distal_line,
            "risk": abs(z.proximal_line - z.distal_line),
            "formed_at": ts(z.leg_end_index),
            "base_start_time": ts(z.base_start_index),
            "base_end_time": ts(z.base_end_index),
            "leg_start_time": ts(z.leg_start_index),
            "leg_end_time": ts(z.leg_end_index),
            "fresh": z.fresh,
            "tested_at_time": ts(z.tested_at_index) if z.tested_at_index is not None else None,
            "base_start_index": z.base_start_index,
            "base_end_index": z.base_end_index,
            "leg_start_index": z.leg_start_index,
            "leg_end_index": z.leg_end_index,
            "tested_at_index": z.tested_at_index,
            "has_strong_legout": z.has_strong_legout,
        })

    return pd.DataFrame(rows)
