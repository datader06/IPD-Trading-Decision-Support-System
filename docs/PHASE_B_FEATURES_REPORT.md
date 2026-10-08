# PHASE_B_FEATURES_REPORT.md: Tier-1 feature generation (7 Oct 2026)

Step 1 of Phase B only. No labels, walk-forward validation or models exist yet.
Registry: `src/ml/registry.py` (version `tier1-v1`, 17 named features, 18 model columns, frozen).

## Source and outputs

| Item | Value |
|---|---|
| Source | `results/nogit-145d6302/phase_a/pit_refetch/candidates.csv` (4,661 rows, sha256 `162f57c4...`) |
| Source code hash | `cd73bf8d` (from `pit_refetch/run_info.txt`; recorded in the manifest and checked by a test) |
| Output folder | `results/nogit-145d6302/phase_b/tier1/` |
| Dataset | `features.csv`: **4,552 rows**, 489 tickers, one row per unique candidate order |
| Other files | `exclusions.csv` (109 rows), `manifest.json`, `report.txt` |
| Rebuild command | `python scripts/run_phase_b_features.py` (offline; frozen frames and NIFTY daily only) |
| Determinism | a second full run produced a byte-identical `features.csv` (same SHA-256) |

Columns: identifiers and outcome fields (`row_id`, keys, times, flags, entry/stop/target/risk/shares, `outcome`, `exit_reason`,
`fill_*`, `exit_*`, `r_gross`, `mtm_r`) come first. They are carried for later labelling and evaluation and are **forbidden as
model inputs** (`registry.FORBIDDEN`). The 18 model columns come last:

```
ltf_base_count, htf_base_count, htf_strong_legout, ltf_leg_body_atr, htf_zone_width_atr, overlap_frac, ltf_pos_in_htf,
wick_fresh_fail, log_ltf_age_bars, trend_up, trend_down, risk_atr_d, approach_speed_atr, cost_in_r_rt0.20, type_demand,
nifty_above_200dma, stock_rs63, is_0915_bar
```

## Frozen definitions as implemented
- `approach_speed_atr`: `(close[entry_idx-1] - close[entry_idx-9]) / ATR15[entry_idx-1]` (8 completed close-to-close intervals,
  overnight gaps included), **signed so that positive means price moving toward the zone** (demand: falling, supply: rising).
  The sign convention is my reading of "signed": flipping it is a one-line change but would change the frozen feature, so
  please confirm it.
- `ltf_leg_body_atr`: `sum(abs(close-open))` over the LTF leg candles / ATR15 at the leg-end bar.
- `stock_rs63`: stock and NIFTY each use their own 63 prior daily bars at D-1; fewer than 63 stock bars is a warm-up exclusion.
- No clipping or scaling; raw values are stored.

## Row counts and exclusions

| Stage | Reason | Rows |
|---|---|---|
| pool | `entry_before_2021-01-01` | 79 |
| pool | `phase_a_corporate_action_excluded` | 5 |
| pool | `duplicate_order` (earliest `htf_formed_at` kept) | 2 |
| features | `warmup_stock_lt_63_prior_daily_bars` | 20 |
| features | `corporate_action_in_63d_lookback` | 3 |
| | **Pool 4,575 - 23 feature exclusions = 4,552** | |

The 4,575 pool rows match the Phase A relaxed pool. No other exclusion reason occurred (the checks for entry bar missing, key
mismatch, ATR unavailable, HTF leg after D-1 and missing trend state all returned zero).

## Missing values
NaN cells: **0**. Infinite cells: **0**. Duplicate `row_id`: 0.

## Outcomes carried (not labels yet)

| | Count |
|---|---|
| WIN | 1,229 |
| LOSS | 2,653 |
| AMBIGUOUS | 669 |
| CENSORED | 1 |
| B0 rows | 316 (256 resolved) |

| Year | Rows | Resolved | Wins | Win % (resolved) |
|---|---|---|---|---|
| 2021 | 546 | 493 | 163 | 33.1 |
| 2022 | 716 | 642 | 187 | 29.1 |
| 2023 | 800 | 692 | 231 | 33.4 |
| 2024 | 827 | 696 | 224 | 32.2 |
| 2025 | 882 | 734 | 231 | 31.5 |
| 2026 | 781 | 625 | 193 | 30.9 |

Sample-size check for the first walk-forward fold (training 2021-2022): 1,135 resolved rows and 350 wins against the 180 wins
needed for 18 columns (10 per column). No ticker exceeds 0.5% of the rows (max 22).

## Feature ranges (raw, unclipped)

| Column | min | median | mean | p99 | max |
|---|---|---|---|---|---|
| ltf_base_count | 1 | 4 | 5.41 | 24 | 40 |
| htf_base_count | 1 | 4 | 5.48 | 22 | 51 |
| htf_strong_legout | 0 | 0 | 0.22 | 1 | 1 |
| ltf_leg_body_atr | 1.30 | 3.16 | 3.35 | 7.00 | 8.74 |
| htf_zone_width_atr | 0.40 | 0.85 | 0.92 | 2.00 | 2.81 |
| overlap_frac | 0.31 | 1.00 | 0.90 | 1.00 | 1.00 |
| ltf_pos_in_htf | 0.04 | 0.82 | 0.80 | 1.34 | 1.87 |
| wick_fresh_fail | 0 | 1 | 0.54 | 1 | 1 |
| log_ltf_age_bars | 0.69 | 5.71 | 5.87 | 9.55 | 10.37 |
| trend_up / trend_down | 0 | 0 | 0.35 / 0.35 | 1 | 1 |
| risk_atr_d | 0.036 | 0.19 | 0.21 | 0.56 | 1.39 |
| approach_speed_atr | -5.66 | 1.88 | 2.03 | 7.16 | 10.96 |
| cost_in_r_rt0.20 | 0.030 | 0.32 | 0.36 | 1.04 | 1.65 |
| type_demand | 0 | 1 | 0.64 | 1 | 1 |
| nifty_above_200dma | 0 | 1 | 0.73 | 1 | 1 |
| stock_rs63 | -0.54 | 0.009 | 0.037 | 0.75 | 1.60 |
| is_0915_bar | 0 | 0 | 0.33 | 1 | 1 |

Full per-column table including p1 and unique counts: `results/nogit-145d6302/phase_b/tier1/report.txt`.

## Point-in-time rules enforced (`src/ml/features.py`)
- The entry bar's prices are never read: only the entry bar's timestamp is used to locate `entry_idx`; every price or ATR
  value comes from positions before it (`entry_idx-1` and earlier).
- LTF zone values use bars up to the LTF leg-end (checked to be before `entry_idx`); HTF zone values use daily bars up to the HTF
  leg-end (checked to be on or before D-1).
- Daily ATR, `stock_rs63` and the NIFTY features use only daily bars dated before the entry date (`asof.daily_index_asof`).
- ATR is the legacy causal Wilder ATR, so later data cannot change earlier values.
- Zone key positions are verified against the stored `T_L` and `T_H` close times for every row.

## Tests (`tests/test_phase_b_features.py`, 15 tests, all pass)
Registry frozen (17 / 18 columns, no forbidden column) · every formula with controlled ATR for demand and supply · trend dummies
and the 09:15 flag · NIFTY 200-day average uses D-1 only · `stock_rs63` uses each series' own bars · scrambling the entry bar and
all later data leaves every feature unchanged (with a sensitivity check that scrambling the last completed bar does change
`approach_speed_atr`) · the entry bar and entry-day daily bar are never read · truncation equivalence (synthetic and real
ADANIPORTS / RVNL rows) · all exclusion reasons · pool selection order and log · deterministic `build_ticker` · dataset
integrity against the manifest and exclusions file · the saved dataset reproduces from the source. The Phase A tests still
pass (20 synthetic).

## Limitations and notes
- `approach_speed_atr` sign convention needs your confirmation (above).
- Heavy-tailed raw features (`ltf_base_count`, `htf_base_count`, `log_ltf_age_bars`, `cost_in_r_rt0.20`, `risk_atr_d`) are
  stored unscaled by design; scaling belongs to the walk-forward model pipeline.
- Survivorship, the sub-35% corporate-action blind spot and the missing 15:15 bar since 2026-08-03 carry over from Phase A.
