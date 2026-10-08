"""Frozen Phase B Tier-1 feature registry (docs/PHASE_B_PLAN.md section 12, definitions confirmed by the project owner).

17 named features -> 18 model columns (`trend_entry` becomes trend_up / trend_down, reference level sideways).
Nothing here may be added to, dropped from or redefined without a new registry version (and a fresh holdout decision).

Decision-time symbols: T_d = entry_time (start of the entry 15m bar); D-1 = last daily bar dated before the entry date;
T_L / T_H = close of the LTF / HTF leg-end bar. The entry bar's own open/high/low/close is never read by any feature.
"""

REGISTRY_VERSION = "tier1-v1"
SOURCE_CODE_HASH = "cd73bf8d"  # code_hash recorded in pit_refetch/run_info.txt

# name, group, definition, source, known_at
FEATURES = [
    dict(name="ltf_base_count", group="LTF zone", known_at="T_L", columns=["ltf_base_count"],
         definition="contiguous base candles before the LTF legout (strict V2 definition)",
         source="Phase A candidates.csv ltf_base_count"),
    dict(name="htf_base_count", group="HTF zone", known_at="T_H", columns=["htf_base_count"],
         definition="contiguous base candles before the HTF legout, counted with the strict HTF config",
         source="Phase A candidates.csv htf_base_count"),
    dict(name="htf_strong_legout", group="HTF zone", known_at="T_H", columns=["htf_strong_legout"],
         definition="1 if the HTF leg gapped open beyond 0.5 ATR or absorbed a 2nd impulsive candle, else 0",
         source="Phase A candidates.csv htf_strong_legout (Zone.has_strong_legout)"),
    dict(name="ltf_leg_body_atr", group="LTF zone", known_at="T_L", columns=["ltf_leg_body_atr"],
         definition="sum(abs(close-open)) over the LTF leg candles / ATR15 at the leg-end bar",
         source="15m frame via ltf_key leg_start..leg_end; sd_zones.wilder_atr"),
    dict(name="htf_zone_width_atr", group="HTF zone", known_at="T_H", columns=["htf_zone_width_atr"],
         definition="abs(htf_proximal - htf_distal) / daily ATR at the HTF leg-end bar",
         source="candidates.csv levels; daily frame via htf_key leg_end; sd_zones.wilder_atr"),
    dict(name="overlap_frac", group="Multi-timeframe", known_at="T_H", columns=["overlap_frac"],
         definition="share of the LTF zone's height inside the HTF zone", source="Phase A candidates.csv overlap_frac"),
    dict(name="ltf_pos_in_htf", group="Multi-timeframe", known_at="T_H", columns=["ltf_pos_in_htf"],
         definition="(entry_price - htf_distal) / (htf_proximal - htf_distal); 0 = HTF distal, 1 = HTF proximal; may leave [0, 1]",
         source="candidates.csv entry_price, htf_proximal, htf_distal"),
    dict(name="wick_fresh_fail", group="Multi-timeframe", known_at="D-1", columns=["wick_fresh_fail"],
         definition="1 if an earlier daily bar (date < entry date) reached the HTF base wick extreme (rule R10 as a flag)",
         source="Phase A candidates.csv wick_fresh_fail (TickerContext.wick_fail)"),
    dict(name="log(ltf_age_bars)", group="Multi-timeframe", known_at="T_d", columns=["log_ltf_age_bars"],
         definition="natural log of (entry_idx - ltf leg-end idx), in rows of the 15m frame",
         source="15m frame; entry_idx = position of entry_time; ltf_key leg_end"),
    dict(name="trend_entry", group="Trend", known_at="T_d", columns=["trend_up", "trend_down"],
         definition="point-in-time trend state at T_d as two dummies (up, down); sideways is the reference",
         source="Phase A candidates.csv trend_entry (trend_pit.TrendContext.classify)"),
    dict(name="risk_atr_d", group="Volatility", known_at="D-1", columns=["risk_atr_d"],
         definition="risk (entry - stop, price units) / daily ATR at D-1", source="candidates.csv risk; daily frame; sd_zones.wilder_atr"),
    dict(name="approach_speed_atr", group="Price action", known_at="T_d", columns=["approach_speed_atr"],
         definition=("signed move over the previous 8 completed 15m close-to-close intervals "
                     "(close[entry_idx-1] - close[entry_idx-9]) / ATR15 at entry_idx-1; overnight gaps included; "
                     "sign convention: positive = price moving toward the zone (demand: falling, supply: rising)"),
         source="15m frame bars strictly before entry_idx; sd_zones.wilder_atr"),
    dict(name="cost_in_r_rt0.20", group="Trade geometry", known_at="T_d", columns=["cost_in_r_rt0.20"],
         definition="costs.round_trip('rt0.20', 0.20).cost_r(entry_price, entry_price, risk) = 0.002*entry_price/risk",
         source="src/costs.py; candidates.csv entry_price, risk"),
    dict(name="type_demand", group="Trade geometry", known_at="T_H", columns=["type_demand"],
         definition="1 for demand, 0 for supply", source="Phase A candidates.csv type"),
    dict(name="nifty_above_200dma", group="Regime", known_at="D-1", columns=["nifty_above_200dma"],
         definition="1 if NIFTY 50 close at D-1 > mean of its last 200 daily closes ending at D-1",
         source="data/cache/kite/NIFTY50/day; asof.daily_index_asof"),
    dict(name="stock_rs63", group="Regime", known_at="D-1", columns=["stock_rs63"],
         definition=("(stock close[D-1]/stock close[D-1 minus 63 own bars] - 1) - (NIFTY close[D-1]/NIFTY close[D-1 minus 63 own bars] - 1); "
                     "each series uses its own 63 prior daily bars"),
         source="daily frame; NIFTY daily; asof.daily_index_asof"),
    dict(name="is_0915_bar", group="Time/session", known_at="T_d", columns=["is_0915_bar"],
         definition="1 if the entry bar starts at 09:15", source="candidates.csv entry_time"),
]

MODEL_COLUMNS = [c for f in FEATURES for c in f["columns"]]

# Identifier / bookkeeping / outcome columns kept in the dataset file for later labelling and evaluation. NEVER model inputs.
META_COLUMNS = [
    "row_id", "ticker", "type", "htf_key", "ltf_key", "entry_time", "T_L", "T_H", "htf_formed_at", "ltf_formed_at",
    "trend_entry_state", "is_b0", "relaxed_selected",
    "trend_htf_fail", "trend_entry_fail", "htf_strict_fail", "htf_cap_fail", "ltf_cap_fail",
    "entry_price", "stop", "target", "risk", "shares",
    "outcome", "exit_reason", "decided_interval", "fill_time", "fill_price", "exit_time", "exit_price", "r_gross", "mtm_r",
]

# Columns that must never reach a model matrix (outcomes, replay output, raw levels, identifiers, bookkeeping).
FORBIDDEN = set(META_COLUMNS) | {
    "outcome", "exit_reason", "decided_interval", "fill_time", "fill_price", "gap_fill", "exit_time", "exit_price", "r", "mtm_r",
    "minute_used", "r_gross", "ca_excluded", "relaxed_selected", "is_b0", "htf_in_b0_set", "mode", "shares", "target", "stop",
    "entry_price", "htf_proximal", "htf_distal", "ticker", "htf_key", "ltf_key", "combo", "year",
    # label dataset columns (src/ml/labels.py): the target and its bookkeeping are never model inputs
    "label", "label_status", "is_training_label", "phase_a_src_row", "replay_check",
}


def assert_no_forbidden(columns):
    bad = sorted(set(columns) & FORBIDDEN)
    if bad:
        raise ValueError(f"forbidden columns in model matrix: {bad}")
    return list(columns)
