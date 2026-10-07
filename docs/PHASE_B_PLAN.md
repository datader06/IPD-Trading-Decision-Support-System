# PHASE_B_PLAN.md: ML meta-labelling filter for DIT15, implementation design (7 Oct 2026)

Design only. Nothing in this document is implemented. No model, no ML dependency, no Kite fetch, no change to trading logic,
the backtester or any Phase A file.
Inputs referenced here exist in the repository today: `src/candidates.py`, `src/trend_pit.py`, `src/bars.py`, `src/asof.py`,
`src/replay.py`, `src/costs.py`, `src/portfolio.py`, `src/corp_actions.py`, `scripts/run_phase_a.py`, the Phase A output
`results/nogit-145d6302/phase_a/pit/candidates.csv`, the frozen frames `data/cache/kite_frames_dit15_long/`, the raw Kite cache
`data/cache/kite/<SYM>/{day,60minute,15minute,minute}/` (with volume) and `data/cache/kite/NIFTY50/day/`.
Numbers quoted below come from the pre-fetch Phase A run (nogit-145d6302) and will change after the minute-data fetch.

The ML model is a **filter on rule-generated candidates**. It never creates trades, never moves entry/stop/target, and never
replaces a rule. It answers: "given this candidate at its decision time, P(+2R before -1R)?"

---

## 0. Prerequisites (must be done before any Phase B code runs)

1. Minute-data fetch (decision D3, waiting for Kite login): `python scripts/fetch_minute_for_ambiguous.py --run=nogit-145d6302 --label=pit`
   (1,407 read-only requests, entries >= 2021-01-01), plus at most one small second round for trades that hit another
   15m-ambiguous bar later.
2. Re-score with a NEW label so no stale checkpoint is reused: `python scripts/run_phase_a.py generate --label=pit_final`, then
   `report --label=pit_final`. Decisions D1 (bar-label formation timing), D2 (09:15-anchored 2h with 15:15 stub), D4 (gap-fill
   beyond stop stays AMBIGUOUS) are already the defaults of that command. The run id (code hash) of that run is the **frozen
   source** of the ML dataset; record it in the dataset manifest.
3. Updated Phase A report accepted by the user.
4. Freeze: from this point any change to `src/candidates.py`, `src/replay.py`, `src/trend_pit.py`, `src/bars.py` or the legacy
   engine invalidates the ML comparison and requires a new dataset.

---

## 1. Source dataset

`results/<pit_final run>/phase_a/pit_final/candidates.csv`, produced by `scripts/run_phase_a.py generate` (PIT mode, default
switches). It already contains both populations in one file:

| Population | Selection | Pre-fetch size (2021+) |
|---|---|---|
| **Relaxed pool** (ML universe) | `relaxed_selected | is_b0`, entry_time >= 2021-01-01, not `ca_excluded`, duplicate orders removed | 4,575 |
| **B0** (strict rule baseline) | `is_b0`, entry_time >= 2021-01-01, not `ca_excluded` | 318 |

B0 is a subset of the pool (every `is_b0` row is in the pool by construction of `candidates.build`). The model is trained on
the pool. B0 is never used to train; it is the comparison baseline.

## 2. Row definition

One row = one **unique order** of the relaxed pool:
key `(ticker, type, entry_time, entry_price, stop)` (the `ORDER_KEY` of `scripts/run_phase_a.py`). Where two HTF zones produce
the same order (2 cases pre-fetch), keep the first by `htf_formed_at`, and add `n_htf_for_order`.

What a row means: for one HTF zone (`htf_key`), the LTF zone chosen by the legacy matching rules (`ltf_key`) has been formed and
matched, and price **trades into its proximal during the 15m bar starting at `entry_time`**. A B0 row that relaxed matching would
not pick ("displaced", 6 rows) is kept as its own row, sharing `htf_key` with a sibling. Both rows go to the same split side
(sec. 9).

Identifiers kept in the file but never used as features: `ticker`, `htf_key`, `ltf_key`, `combo`, `mode`.

### Decision timestamps (all already in candidates.csv)

| Symbol | Column | Meaning |
|---|---|---|
| T_H | `T_H` | close of the HTF (daily) leg-end bar, 15:30 of `htf_formed_at` |
| T_trend_H | `trend_htf_time` | time of the trend-at-formation check = HTF bar label (midnight), i.e. information through the previous day's close (D1) |
| T_L | `T_L` | close of the LTF (15m) leg-end bar |
| **T_d** | `entry_time` | **decision time = start of the 15m bar in which the entry is touched** |
| D-1 | (derived) | last daily bar with date < date(T_d) (`asof.daily_index_asof`, intraday mode) |

Why the decision is at T_d: the limit order rests at the proximal from HTF confirmation until it fills. A live filter re-scores
at the start of every 15m bar while the order is pending; the score that matters for the outcome is the one at the start of the
bar that fills, i.e. at T_d. Conditioning rows on "the touch happened in this bar" is therefore legitimate, **provided no
feature uses anything from the entry bar after its open**.

**Two information tiers:**
- Tier 1 (default): bars with `close_time <= T_d` only.
- Tier 2 (optional, OFF in the first experiment): also the entry bar's OPEN price (known at the bar's first trade, before the
  touch).

---

## 3. Label

| Name | Definition | Use |
|---|---|---|
| `y` | 1 if `outcome == "WIN"` (+2R target reached after the fill, before the stop), 0 if `outcome == "LOSS"` | training target |
| `r_gross` | realised R from `src/replay.py` (gap fills: > 2 or < -1 possible) | evaluation |
| `r_rt0.10/0.20/0.30` | `r_gross - costs.CostModel.cost_r(fill_price, exit_price, risk)` per `costs.scenarios()` (computed by `run_phase_a.add_costs`) | evaluation |

The label uses exactly the strategy's own exit rules (src/replay.py, 90-day horizon). No new exit, no time exit.

### Outcome classes

| Class | Training | Evaluation (trading metrics) | Reason |
|---|---|---|---|
| WIN / LOSS | y = 1 / 0 | realised R | resolved |
| AMBIGUOUS | **excluded** | counted; best (+2R) / worst (-1R) bounds reported for every strategy | order inside one bar unknown; never relabelled (D4); heuristic labels never used |
| OPEN | excluded | counted; mtm_r reported separately | strategy has no time exit; none observed pre-fetch |
| CENSORED | excluded | counted | outcome not yet knowable; 1 pre-fetch |
| NOFILL | excluded | counted (expected 0; nonzero = bar-mapping bug, stop and investigate) | 0 pre-fetch |

Bias control for the AMBIGUOUS exclusion: remaining AMBIGUOUS rows (mainly "gap-fill opens beyond the stop", 172 pre-fetch;
"target in fill bar") are concentrated in gap and wide-bar entries. For every model, report the AMBIGUOUS rate and the AMBIGUOUS
bounds **by predicted-probability decile**. If the filter accepts AMBIGUOUS rows at a very different rate than resolved ones,
the comparison is reported as uncertain.

---

## 4. Exclusions

| Rule | Why |
|---|---|
| entry_time < 2021-01-01 | trend history starts 2020-11; Phase A reporting window |
| `ca_excluded == True` | corporate-action window (5 pool rows pre-fetch) |
| duplicate orders (keep first) | the same order cannot be taken twice |
| training only: outcome not WIN/LOSS | sec. 3 |
| training only: purge/embargo (sec. 9) | temporal leakage |
| rows whose required features are NaN because of warm-up (e.g. 200-day NIFTY average, ATR(100)) | report count; never impute with future data. Expected only in early 2021 |
| entry_time > data end - 90 days AND unresolved | censored, not knowable |

Not excluded: 15:15 entries (none after 2026-08-03 because the bar is missing; documented, not removed); rows failing former
filters (that is the point of the pool).

---

## 5. Features

Conventions:
- **Exists** = column already in candidates.csv.
- **Derivable** = arithmetic on existing columns only.
- **New** = new code needed (in `src/ml/`, never in Phase A modules).
- ATR: `sd_zones.wilder_atr` (causal; value at index i includes bar i).
- Frames: `candidates.load_frames` / `bars.load_frame` (fixed start, with `close_time`).
- Zone objects: rebuilt per ticker with `candidates.TickerContext(ticker, frames, candidates.PIT)` and looked up by
  `candidates.zkey` against `ctx.htf_rel + ctx.htf_b0` and `ctx.ltf_rel + ctx.ltf_b0`, as `tests/test_phase_a.py` already does.

Leakage risk: **none** = only data closed before the stated time. **low** = correct if the stated index rule is followed.
**medium/high** = a known trap, with a mandatory test.

### 5.1 Supply/Demand zone: LTF (known at T_L)

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| ltf_base_count | contiguous base candles before the legout | `TickerContext.ltf_count` | T_L | yes | no | none |
| ltf_cap_fail | base count > 5 | `candidates.flags` | T_L | yes | no | none |
| ltf_strong_legout | gap or 2-candle leg | `Zone.has_strong_legout` | T_L | yes | no | none |
| ltf_leg_ncandles | leg_end - leg_start + 1 | `ltf_key` | T_L | derivable | trivial | none |
| ltf_leg_body_atr | sum of leg bodies / ATR15 at leg end | 15m frame + `wilder_atr` | T_L | no | yes | low (ATR index = leg_end) |
| ltf_leg_close_pos | close position of the last leg candle in its range | 15m frame | T_L | no | yes | none |
| ltf_base_to_leg_range | base high-low / leg range | 15m frame, `ltf_key` | T_L | no | yes | none |
| ltf_legin_margin_atr | (legout close - legin high) / ATR (demand; mirrored for supply), legin = base_start - 1 | 15m frame | T_L | no | yes | none |
| ltf_zone_width_atr | (proximal - distal) / ATR15 at leg end (= risk / ATR) | `risk` + ATR | T_L | no | yes | low |
| ltf_wick_to_wick | proximal drawn at the base wick | compare `entry_price` to base high/low | T_L | no | yes | none |

### 5.2 Supply/Demand zone: HTF (known at T_H)

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| htf_base_count | base count under the strict HTF config | `TickerContext.htf_count` | T_H | yes | no | none |
| htf_cap_fail / htf_strict_fail | former filters | `candidates.flags` | T_H | yes | no | none (detection is append-stable, tested) |
| htf_strong_legout | gap or 2-candle leg | `Zone` | T_H | yes | no | none |
| htf_risk_pct | HTF zone width % of price | CSV | T_H | yes | no | none |
| htf_zone_width_atr | HTF width / daily ATR at leg end | daily frame + ATR | T_H | no | yes | low |
| htf_leg_body_atr, htf_leg_close_pos | HTF legout strength | daily frame, `htf_key` | T_H | no | yes | none |
| htf_legout_wick_margin_atr | how far the HTF legout closed beyond the base wick (R31) | daily frame | T_H | no | yes | none |

### 5.3 Multi-timeframe relationship

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| overlap_frac | share of the LTF zone inside the HTF zone | CSV | T_H | yes | no | none |
| ltf_pos_in_htf | LTF proximal position in the HTF zone (0 = HTF distal, 1 = HTF proximal) | `entry_price, htf_proximal, htf_distal` | T_H | derivable | trivial | none |
| ltf_risk_to_htf_width | `risk` / HTF width | CSV | T_H | derivable | trivial | none |
| stop_room_htf_distal_r | (LTF stop - HTF distal) / risk, signed by type | CSV | T_H | derivable | trivial | none |
| formation_lag_hours | T_H - T_L | CSV | T_H | derivable | trivial | none |
| htf_age_days | T_d - T_H (pending-order age; median 17 d, p99 824 d pre-fetch) | CSV | T_d | derivable | trivial | none |
| ltf_age_bars | 15m bars between T_L and T_d | 15m frame | T_d | no | yes | none |
| wick_fresh_fail | earlier HTF visit to the base wick (R10) | `TickerContext.wick_fail` | D-1 | yes | no | low (strict date < entry date; already tested) |
| htf_prior_visits | separate earlier visits to the HTF zone | daily bars with date < date(T_d) | D-1 | no | yes (rewrite; `run_tradescore._visits` is NOT reusable: it lets the entry-day bar end a visit) | **medium**: truncation test mandatory |
| n_ltf_candidates | LTF zones that passed matching conditions 1-4 for this HTF zone | same logic as `candidates._best_ltf` (re-implemented read-only in `src/ml`, `_best_ltf` itself unchanged) | T_H | no | yes | low (uses `tested_at_timestamp` only as "first touch <= cutoff", like the rule) |
| is_b0_eligible_flags | count of failed former filters (0-6) | `candidates.flags` columns | T_d | derivable | trivial | none |

### 5.4 Market structure (nothing exists; new module `src/ml/structure.py`)

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| swing_bias_d | (higher highs + higher lows) - (lower highs + lower lows) over the last 4 confirmed daily pivots | daily frame, k-bar fractal pivots | D-1 | no | yes | **high**: a k-bar pivot is known only k bars after it; pivot i usable only if i + k <= index(D-1) |
| dist_last_swing_high_atr / low | entry distance to the last confirmed daily swing | same | D-1 | no | yes | **high** (same rule) |
| last_bos_dir, days_since_bos | last close beyond a confirmed swing | same | D-1 | no | yes | high (same rule) |
| range_pos_60d | entry price within the high-low of the last 60 daily bars | daily frame | D-1 | no | yes | low (exclude the entry day) |
| room_to_opposing_zone_r | distance from entry to the nearest opposite-type HTF zone that is formed (`close_time` of leg end <= T_d) and untouched at T_d, in R. Is the 2R target blocked? | `ctx.htf_rel + ctx.htf_b0`, `Zone.tested_at_timestamp` | T_d | no | yes | **high**: `Zone.fresh` must never be used (computed on full history); "untouched at T_d" = `tested_at_timestamp is None or close_time(tested bar) > T_d` |

### 5.5 Trend

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| trend_htf | up / sideways / down at `trend_htf_time` | CSV (`TrendContext.classify`) | previous day close (D1) | yes | no | none (PIT, tested) |
| trend_entry | state at T_d | CSV | T_d | yes | no | none (PIT, tested) |
| trend_htf_fail / trend_entry_fail | former filters | CSV | as above | yes | no | none |
| trend_aligned | demand & up, or supply & down | derived | T_d | derivable | trivial | none |
| ath_at_entry | ATH override active at T_d | `TrendContext.ath_at(T_d)` | T_d | function exists | small | none (closed bars + daily D-1) |
| bars_since_trend_event | age of the last zone-break event | `TrendContext.ev_time` (event = break bar close time) | T_d | attribute exists | small | none |
| close_vs_ema50_d, ema50_slope_d, close_vs_ema200_d | classic daily trend | daily frame | D-1 | no | yes | low (exclude the entry day) |

### 5.6 Volatility

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| atr15_pct | ATR15 / close at entry_idx - 1 | 15m frame + `wilder_atr` | T_d | no | yes | **medium**: `atr.iloc[entry_idx]` includes the entry bar; must be `entry_idx - 1` |
| atr_d_pct | daily ATR14 / close at D-1 | daily frame | D-1 | no | yes | medium (same rule, daily) |
| atr_ratio_14_100_d | daily volatility expansion | daily frame | D-1 | no | yes | low |
| rv20_stock | 20-day realised volatility of daily returns | daily frame | D-1 | no | yes | low |
| rv20_nifty | same for NIFTY 50 | `data/cache/kite/NIFTY50/day/*.csv` + `asof.asof_join_daily` | D-1 | no | yes | low |
| risk_atr15, risk_atr_d | stop distance in ATR | `risk` + the ATRs above | T_d | no | yes | as ATR |

### 5.7 Volume (the frames have no volume; the raw cache has it)

New loader `src/ml/volume.py`: reads `data/cache/kite/<SYM>/{15minute,60minute,day}/*.csv` (columns timestamp, OHLC, volume),
merges files, drops duplicate timestamps, and **joins to the frames on timestamp**. Report the join coverage per ticker; a
mismatch is a data-quality failure, not filled.

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| ltf_leg_vol_ratio | legout volume / mean base volume (15m) | raw 15minute | T_L | no | yes | none |
| htf_leg_vol_ratio | same on daily | raw day | T_H | no | yes | none |
| approach_vol_ratio | volume of the last 8 bars before the entry bar / 20-bar mean | raw 15minute, bars < entry_idx | T_d | no | yes | low |
| rel_vol_prev_day | D-1 volume / 20-day mean | raw day | D-1 | no | yes | **high if the entry day is used**: daily volume of the entry day is final only after the close |

Kite volume is not adjusted like prices: use ratios only, never levels.

### 5.8 Price action

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| approach_speed_atr | move over the last 8 15m bars before the entry bar / ATR15 | 15m frame, bars < entry_idx | T_d | no | yes | low |
| approach_counter_candles | candles against the trade among the last 5 bars | 15m frame | T_d | no | yes | low |
| max_excursion_after_ltf_r | furthest move away from the zone between T_L and T_d, in R | 15m frame | T_d | no | yes | low |
| prev_day_close_pos | D-1 close position in its range | daily frame | D-1 | no | yes | none |
| *(Tier 2)* entry_open_gap_atr | entry bar open - previous close, / ATR15 | 15m frame (open of the entry bar) | open of the entry bar | no | yes | **medium**: allowed only in Tier 2; never use the entry bar's high, low or close. Replay's `gap_fill` column must not be used (it is replay output) |
| *(Tier 2)* opens_beyond_entry | entry bar opens through the proximal | same | open of the entry bar | no | yes | medium (Tier 2 only) |

### 5.9 Trade geometry

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| ltf_risk_pct | risk / entry, % | CSV | T_L | yes | no | none |
| cost_in_r_rt0.20 | expected round-trip cost in R = `CostModel.cost_r(entry, entry, risk)` (exit taken as entry: exit price is unknown at T_d) | `src/costs.py` | T_d | function exists | small | none (must not use realised `exit_price`) |
| ticks_in_risk | risk / 0.05 (NSE tick) | CSV | T_L | derivable | trivial | none |
| capital_limited | shares * entry >= 95,000 (sizing capped by notional, not by Rs 1,000 risk) | CSV | T_d | derivable | trivial | none |
| type_demand | 1 = demand, 0 = supply | CSV | T_H | yes | trivial | none |

### 5.10 Market regime

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| nifty_above_200dma, nifty_ret63, nifty_dd252 | broad market state | NIFTY50 daily + `asof.asof_join_daily(..., decision_after_close=False)` | D-1 | as-of join exists | yes (indicators) | none if the as-of join is used (the `regime_test.py` bug, fixed in A5, is the trap) |
| stock_rs63 | 63-day return of the stock - NIFTY | daily frames | D-1 | no | yes | low |
| breadth_above_50dma | share of the 503 tickers above their 50-day average | all daily frames | D-1 | no | yes | survivorship (current universe); **deferred**, not in the first experiment |

### 5.11 Time / session

| Feature | Meaning | Source | Known | Exists | New code | Leakage risk |
|---|---|---|---|---|---|---|
| entry_slot | minutes since 09:15 of the entry bar | `entry_time` | T_d | derivable | trivial | none (a third of pre-fetch entries are the 09:15 bar) |
| is_0915_bar | entry bar is the first bar of the session | `entry_time` | T_d | derivable | trivial | none |
| day_of_week, days_to_month_end | calendar | `entry_time` | T_d | derivable | trivial | none |
| days_to_fo_expiry | F&O expiry distance | expiry calendar (not in repo) | T_d | no | new data | none; deferred (NSE changed the expiry weekday during the period) |

### 5.12 Forbidden columns (enforced by a blacklist in code; tested)

`outcome, exit_reason, decided_interval, fill_time, fill_price, gap_fill, exit_time, exit_price, r, mtm_r, minute_used, r_gross,
r_rt*, ca_excluded` (uses the exit/horizon), `relaxed_selected, is_b0, htf_in_b0_set, mode` (pipeline bookkeeping),
`shares, target, stop, entry_price, htf_proximal, htf_distal` as raw levels (non-stationary; only the normalised versions above),
`ticker, htf_key, ltf_key` (identifiers), `year` or any calendar index, `Zone.fresh`, `Zone.tested_at_*` used as values,
`classify_zone_state` / `ltf_state` (state as of the data end).

---

## 6. Leakage tests (Phase B, mandatory, extend tests/test_phase_a.py's approach)

1. **Truncation test**: for a sample of rows from several tickers, rebuild frames cut at T_d (15m/60m: `close_time <= T_d`;
   daily: date < date(T_d); raw volume likewise) with `bars.truncate_frames`-style cuts, recompute all features, and require
   equality with the full-data values. Tier 2 features are tested with the entry bar's open kept and its H/L/C randomised.
2. **Future-perturbation test**: randomise every bar after T_d; features must not change.
3. **Blacklist test**: no forbidden column reaches the model matrix.
4. **Shuffled-label test**: on a training fold with shuffled y, OOS ROC-AUC must sit inside the 95 % band around 0.5.
5. **Pivot-lag unit test** (sec. 5.4) and **as-of join unit test** (already in Phase A for daily data).

---

## 7. Module layout (new files only)

```
src/ml/
  registry.py     feature metadata (name, group, tier, known_at, source) + forbidden-column list
  volume.py       raw Kite cache loader with volume, join to frames, coverage report
  structure.py    confirmed-pivot swings, BOS, opposing-zone room
  regime.py       NIFTY indicators via asof.asof_join_daily
  features.py     per-ticker feature builder: TickerContext(PIT) + frames + volume -> feature rows for that ticker's candidates
  dataset.py      join candidates.csv + features, exclusions, label, manifest (source run id, code hash, row counts)
  splits.py       walk-forward folds, purge, embargo, ticker groups
  models.py       logistic regression + gradient-boosting pipelines, fixed grids
  evaluate.py     ML metrics + trading metrics via src/portfolio.py and src/costs.py
  explain.py      coefficients, permutation importance, SHAP/ALE (later)
scripts/run_phase_b.py   steps: features | dataset | train | evaluate | explain (checkpoints per ticker like run_phase_a)
tests/test_phase_b.py    sec. 6
```

Feature generation re-runs `TickerContext` per ticker (about 25 s per ticker at normal clock; about 45 min for 503 tickers at
8 workers, as Phase A). Dependencies to add only when Phase B is approved: scikit-learn (LR, HistGradientBoosting,
calibration, permutation importance); shap later (sec. 14). No LightGBM in the first experiment: sklearn's
HistGradientBoostingClassifier covers the comparison model with one dependency.

---

## 8. Insertion into the existing pipeline (the strategy is not replaced)

```
frames -> candidates.build (Phase A, unchanged: zones, matching, flags, replay outcome)
       -> src/ml/features.py (decision-time features)            [new, read-only on Phase A objects]
       -> model.predict_proba at T_d -> ml_p                     [new]
       -> gate: take = ml_p * 2 - (1 - ml_p) * |L| - cost_in_r > 0
       -> the SAME replay outcome / R of that candidate (no re-simulation, no rule change)
       -> src/portfolio.py summary / capital_constrained / concurrency, src/costs.py scenarios
```

The ML gate only selects rows. Entry, stop, target, sizing and exit are the candidate's own (Phase A). In live use the same gate
would run at the start of each 15m bar while an order is pending; in the backtest only the score at T_d matters.

Decision threshold (fixed rule, never tuned on test): take if expected net R > 0:
`p * 2 - (1 - p) * L - c > 0`, where L = mean |R| of LOSS rows in the training fold (gap stops make it > 1), and c =
`cost_in_r` for the scenario (rt0.20 primary; rt0.10 / rt0.30 sensitivity). This requires calibrated probabilities: report
reliability per fold. A fixed take-rate rule (top 50 % by p) is reported as a diagnostic only.

---

## 9. Splits and walk-forward

Chronological by `entry_time`. Pre-fetch resolved pool counts per year: 2021 351, 2022 481, 2023 506, 2024 513, 2025 571,
2026 480.

| Set | Period | Use |
|---|---|---|
| Walk-forward folds | test half-years 2023H1, 2023H2, 2024H1, 2024H2, 2025H1, 2025H2; train = all rows from 2021-01-01 up to the fold start (expanding) | model/feature selection on the concatenated OOS stream |
| Inner validation | last 6 months of each training window | hyperparameter choice, early stopping, calibration check |
| Final test | 2026-01-01 .. data end | used **once**, after the design and features are frozen. Caveat: partly contaminated by 2026 chart reviews (Phase A docs); forward data after the freeze date is the only clean test |

- **Purge**: drop training rows with `exit_time >= fold start`. Pre-fetch, 99 % of candidates exit within 4 days of entry,
  max 25 days. Unresolved rows are already excluded from training.
- **Embargo**: drop training rows with `entry_time` in the 5 trading days before the fold start.
- **Siblings**: rows sharing `htf_key` (displaced pairs) and rows sharing an order are assigned to the side of the earliest
  `entry_time` of the group and purged from the other side.
- **Same ticker**: 97 % of tickers have more than one candidate. Rows are not independent, so all confidence intervals use a
  block bootstrap by calendar month (time) and a ticker-cluster bootstrap (cross-section).
- **Unseen stocks**: ticker groups = 5 groups by a stable hash of the ticker. Variant: train on the other groups up to the fold
  start, test on the held-out group in the fold period.

---

## 10. First baseline model

L2 logistic regression (sklearn `LogisticRegression`, lbfgs).
- Standardise with the training fold only.
- C chosen from {0.01, 0.1, 1.0} by inner-validation log-loss.
- No class weights (the target base rate is needed for calibrated p).
- About 15 Tier-1 features (sec. 12).
- Categorical trend states one-hot (2 dummies each).

## 11. First comparison model

sklearn `HistGradientBoostingClassifier`:
- max_depth 3, max_leaf_nodes 7, min_samples_leaf 50, learning_rate 0.05, l2_regularization 1.0;
- early stopping on inner validation;
- fixed grid of at most 4 configurations, all logged;
- same features;
- probabilities calibrated on inner validation (isotonic if >= 1,000 rows, otherwise Platt).

Random Forest is not in the first experiment (calibration needs data we do not have).

## 12. First experiment feature set (Tier 1, about 15)

`cost_in_r_rt0.20, risk_atr_d, overlap_frac, ltf_pos_in_htf, htf_zone_width_atr, ltf_base_count, htf_base_count,
ltf_leg_body_atr, htf_strong_legout, trend_entry (2 dummies), wick_fresh_fail, log(ltf_age_bars), approach_speed_atr,
nifty_above_200dma, stock_rs63, is_0915_bar, type_demand`.

Pre-registered and frozen before the first training run. Structure, volume and Tier 2 features enter only in a later,
separately logged experiment.

---

## 13. Comparison and trading metrics

| Strategy | Rows |
|---|---|
| **B0**: existing rules only | `is_b0` rows (the hardened strict baseline) |
| **B1**: relaxed pool, take all | all pool rows |
| **ML**: rules + ML filter | pool rows with take = True |
| **ML-on-B0** (secondary) | B0 rows with take = True |
| **B2**: random filter | pool rows sampled at the ML take-rate, 1,000 draws, fixed seed |
| **B3**: best single former-filter rule | chosen on the training fold only (e.g. not `trend_entry_fail`) |

Reported for each, on the walk-forward OOS stream, per year, train vs holdout, and on the final test (via
`portfolio.summary`, `portfolio.capital_constrained`, `portfolio.concurrency`, `costs.scenarios`):
- trades, take-rate, trades per year;
- WIN / LOSS / AMBIGUOUS / OPEN / CENSORED / NOFILL counts;
- win rate with bootstrap 95 % and AMBIGUOUS bounds;
- expectancy (mean R);
- profit factor;
- total R;
- max drawdown in R (sequenced by exit time);
- capital-constrained (Rs 1L) versions;
- rupee P&L and drawdown;
- all of the above gross and at rt0.10 / rt0.20 / rt0.30;
- Sharpe / Sortino of the daily R series, flagged as unreliable at this n.

ML metrics:
- ROC-AUC, PR-AUC (against the fold's base rate), Brier and log-loss (against a base-rate predictor);
- reliability curve, ECE;
- precision / recall at the operating threshold.

Differences: paired block bootstrap (month blocks) of ML minus B0 and ML minus B1 for expectancy, win rate, PF, total R, max DD.
ML versus B2: position of ML's net expectancy within the 1,000-draw distribution.

Success criteria (pre-registered, all on the 2023-2025 OOS stream at rt0.20; then the 2026 test must agree in direction):
- (a) net expectancy above B0 and B1, block-bootstrap 95 % CI of the difference excluding 0;
- (b) net expectancy > 0 and PF > 1.1;
- (c) above the 95th percentile of B2;
- (d) max DD (R) not worse than B0;
- (e) at least 100 taken trades and at least 30 per OOS year;
- (f) improves on B0 in at least 2 of 3 years and at least 4 of 5 ticker groups;
- (g) OOS Brier better than the base rate.

Higher AUC alone counts for nothing. Expectancy up but total R down is reported as "mixed". A null result is a valid result.

---

## 14. Minimum sample size and class balance checks (run before training; failures stop the run)

| Check | Threshold | Action if failed |
|---|---|---|
| resolved rows per training fold | >= 300 | merge test folds to years |
| WIN rows per training fold | >= 10 x number of features (events per variable) | drop to the 8 highest-priority features |
| resolved rows per test fold | >= 100 | merge folds |
| win rate per fold | report; flag if outside [15 %, 50 %] | report only (no resampling, no SMOTE) |
| AMBIGUOUS share per fold and per predicted decile | report | flag the fold if > 25 % after the fetch |
| feature missingness per fold | report; > 5 % missing = feature dropped for that experiment | |
| tickers per fold, rows per ticker | report; flag any ticker > 2 % of a fold | |
| SAMPLE<30 flag | every reported slice | |

Pre-fetch projection: training fold 1 (2021-2022) has about 832 resolved rows, about 236 wins: 15 features pass the events-per-variable
rule (about 16 per feature). Re-check after the fetch.

## 15. XAI outputs (after the first evaluation, not before)

- LR: standardised coefficients with block-bootstrap CIs, per fold.
- Permutation importance on OOS folds: drop in log-loss and drop in net expectancy, per feature and per feature group (sec. 5
  groups). Group level is the primary readout at this n.
- SHAP (LinearExplainer for LR, TreeExplainer for gradient boosting): summary/beeswarm per fold, and per-trade explanations
  saved next to accepted/rejected trades (`results/<run>/phase_b/explain/trades_explained.csv`).
- ALE plots (preferred over PDP because risk, cost and width are correlated) for the top 5 features.
- Stability: rank of each feature across folds. A feature important in only one fold is reported as unstable.
- Former-filter view: how often the model accepts rows that fail each former filter, and their realised R.

## 16. Known limitations carried into Phase B

- Survivorship (current 503-ticker universe).
- Corporate-action moves under 35 % are not detected.
- 15:15 bar missing since 2026-08-03.
- AMBIGUOUS rows by rule (gap-fill beyond stop).
- Trend history from 2020-11.
- 2026 holdout partly contaminated by chart reviews.
- Costs are scenarios, not a broker schedule (D6).
- DIT15 only (D7): WIT/MIT need the same hardening before any ML on them.
