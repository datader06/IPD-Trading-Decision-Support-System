"""Constants only. Defaults taken from legacy/handoff/handoff/RULES.md; verified against legacy code."""

# Rule flags
RULE_TREND_RECHECK_AT_ENTRY = True
RULE1_LEGOUT_BEYOND_LEGIN_LTF = True
RULE_WICK_FRESHNESS_HTF = True

# Base logic V2 (src/base_candles.py) is the default since 2 Oct 2026 (user decision on chart judgement).
# BASE_LOGIC_V2 = False reproduces Baseline v1 exactly (legacy base logic, LTF cap 3 truncating); runners: --legacy-base.
BASE_LOGIC_V2 = True

# Base caps (V2 rejects a zone whose base run is longer than the cap; legacy truncated)
LTF_BASE_CAP = 5          # V2 default. Legacy code used 3 (truncating). Override per run with --ltf-cap=N (V2 first tested at 8)
HTF_BASE_CAP = 5
BASE_CAP_MODE = "reject"  # V2 behaviour; legacy was "truncate"

# Impulse / leg
IMPULSE_BODY_ATR_MULT = 1.3
IMPULSE_CLOSE_RANGE_PCT = 0.75
LTF_MAX_LEG_CANDLES = 2

# Base / zone geometry
BASE_BODY_ATR_MULT = 0.5
MIN_ZONE_WIDTH_ATR_MULT = 0.5
DISTAL_BUFFER_ATR_MULT = 0.1

# Matching
MIN_LTF_OVERLAP_FRAC = 0.30

# Sizing
REWARD_RISK = 2.0
MAX_LOSS_PER_TRADE = 1000
CAPITAL = 100000

# Train / holdout
SPLIT_DATE = "2026-01-01"

# Base logic V2 details (src/base_candles.py), user corrections 2 Oct 2026.
# Base candle = not impulsive AND (total wick > BASE_WICK_TO_BODY * body  OR  body <= BASE_BODY_ATR_MULT * ATR).
BASE_WICK_TO_BODY = 0.5
BASE_CANDLE_MAX_RANGE_ATR = 2.5      # a base candle's own high-low range cap, in ATR (MRPL 4.5 bad, CGPOWER 2.7 bad, best good 2.3)
HTF_MAX_BASE_TO_LEG_RANGE = 1.25     # legacy HTF value was 1.5 (MRPL 1.31 and IRCTC 1.34 bad; measured good examples below 1.25)
BASE_EXTENSION_ATR = 0.4             # HTF zone lines: each added base candle may grow the base range by <= this many ATR (legacy 0.15; the run COUNT ignores it)
LTF_LINE_CANDLES = 3                 # LTF zone lines come from the nearest N base candles (= the legacy LTF cap; matches ACC/RVNL/CONCORDBIO lines)
LTF_MAX_BASE_TO_LEG_RANGE = 0.6         # legacy LTF value 0.5; CONCORDBIO daily (user: genuinely very good) is 0.57 once its wicky 3rd candle counts as base
HTF_LEGOUT_CLOSE_BEYOND_BASE_WICK = True  # user rule 2 Oct 2026: on the HTF the legout must CLOSE beyond the base's wick (demand: above the base high, supply: below the base low). Runner: --no-legout-wick turns it off

# Strict HTF profile (opt-in with the runner flag --strict-htf; default OFF), set 2 Oct 2026 so that it removes about 20% of trades:
# measured on the 184 DIT15 cap-5 trades (scripts/htf_legout_calibration.py): this profile removes 21.2% of them.
# Legacy/V2 daily HTF: legout body >= 1.3 x ATR, close in the outer 25% of its range, base range <= 1.25 x legout range.
STRICT_HTF_IMPULSE_BODY_ATR = 1.35    # legout candle body at least 1.35 x ATR (was 1.3)
STRICT_HTF_IMPULSE_CLOSE_POS = 0.78   # legout closes in the outer 22% of its own range (was 25%)
STRICT_HTF_MAX_BASE_TO_LEG_RANGE = 1.25  # unchanged from V2
