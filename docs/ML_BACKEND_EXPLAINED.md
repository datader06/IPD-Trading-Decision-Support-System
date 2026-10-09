# The ML backend and the planned comparative study: a technical walkthrough

Written for a team discussion or viva. Source of truth: the files in this repository (`src/ml/`, `scripts/run_phase_b_*.py`,
`tests/test_phase_b_*.py`, `docs/PHASE_A_FREEZE.md`, `docs/PHASE_B_PLAN.md`, `docs/IMPLEMENTATION_PLAN.md`, the three Phase B reports).

**Legend.** [IMPL] implemented in code. [TEST] covered by passing tests. [FROZEN] fixed, not to be changed without a new version.
[PLAN] documented but not implemented. [DEFER] explicitly left out of the first experiment. Anything not marked is an explanation,
not a repository fact. Where a hypothesis is given for why a feature might help, it is a hypothesis: no valid evidence of any feature's
predictive value exists yet (the older feature-effect numbers in `docs/DECISIONS.md` were measured under a known exit bug and are invalid).

**What does not exist yet:** no model code. `src/ml/` contains `registry.py`, `features.py`, `labels.py`, `splits.py` only. There is no
`models.py`, `train`, `evaluate` or `explain` module, and no `scripts/run_phase_b_*` for training. Everything about model fitting,
thresholds and evaluation below is **[PLAN]**.

---

## 1. Big-picture ML architecture

```
Phase A rule engine [IMPL][FROZEN]    zones, HTF/LTF matching, trend, entry/stop/target, sizing
        |
        v
Candidate trades [IMPL][FROZEN]       one row per unique order; former discretionary filters recorded as flags
        |                             (DIT15 relaxed pool: 4,575 rows; strict B0: 318)
        v
Feature extraction [IMPL][TEST]       18 model columns, computed only from information known at the decision time T_d
        |
        v
Labels [IMPL][TEST]                   WIN = 1, LOSS = 0 from the stored replay; AMBIGUOUS / CENSORED / OPEN / NOFILL: no label
        |
        v
Chronological walk-forward folds [IMPL][TEST]    6 expanding folds 2023H1..2025H2, 6-month inner validation, 5-day embargo,
        |                                         purge, 2026 holdout untouched
        v
Model training [PLAN]                 L2 logistic regression first; HistGradientBoosting as the comparison; fit on training data only
        |
        v
Validation: hyperparameters / calibration (and threshold, see section 6) [PLAN]
        |
        v
Frozen test prediction [PLAN]         probabilities for each test window, model and rule fixed before looking at the test rows
        |
        v
ML filtering [PLAN]                   take / skip each candidate; the candidate's own stored outcome is used, nothing is re-simulated
        |
        v
Trading evaluation [PLAN, building blocks IMPL]   src/portfolio.py (metrics, drawdown), src/costs.py (0.10 / 0.20 / 0.30%)
```

**Why a meta-labeling / filtering layer, not a replacement for the rule engine**
- The rule engine already defines everything that carries risk: entry (LTF proximal), stop (LTF distal), target (2R), size
  (Rs 1,000 risk, Rs 1,00,000 notional cap). ML is only asked one question per candidate: *how likely is this already-defined trade
  to reach +2R before -1R?* It never moves a level, changes a size, or creates a trade.
- The data are small: 4,552 candidate rows, 3,882 with a WIN / LOSS label (1,229 / 2,653). That is far too little to learn a
  trading policy from prices; it is enough to ask a narrow, structured question about trades the rules already produced.
- The comparison is clean: *rules only* versus *rules + filter* differ only in which of the same trades are taken (section 10).
- Risk rules stay deterministic and auditable. ML cannot raise risk, override a cap, or select the universe (`docs/IMPLEMENTATION_PLAN.md`, Phase 8).
- The frozen rule-only baselines are weak: DIT15 B0 is +0.046 R gross (95% interval -0.126 to +0.226) and negative after costs at every scenario.
  So the open question is whether *selection among* these trades adds anything, not whether ML can "find alpha" on its own.

---

## 2. The current Phase B data pipeline

All outputs live under `results/nogit-145d6302/phase_b/` (source: the frozen DIT15 `pit_refetch` run, code hash `cd73bf8d`).

### `src/ml/registry.py` [IMPL][FROZEN]
- **Responsibility:** the single definition of what a model may see. `FEATURES` (17 named features, with group, definition, source, known-at time),
  `MODEL_COLUMNS` (the 18 columns, in order), `META_COLUMNS` (identifiers and outcome fields carried for later use), `FORBIDDEN`
  (columns that must never reach a model), `assert_no_forbidden()`, `REGISTRY_VERSION = "tier1-v1"`, `SOURCE_CODE_HASH = "cd73bf8d"`.
- **Leakage protection:** `FORBIDDEN` contains every outcome / replay field (`outcome`, `exit_*`, `fill_*`, `r_gross`, ...), raw price levels
  (`entry_price`, `stop`, `target`, ...), identifiers, bookkeeping flags, and the label columns (`label`, `label_status`,
  `is_training_label`, `phase_a_src_row`, `replay_check`). `assert_no_forbidden(MODEL_COLUMNS)` runs in the feature runner and in tests.
- **Connects to:** imported by `features.py`, `labels.py`, `splits.py` and the three runners. The registry is the contract the (future) model code must use.

### `src/ml/features.py` and `scripts/run_phase_b_features.py` [IMPL][TEST]
- **Inputs:** `results/nogit-145d6302/phase_a/pit_refetch/candidates.csv` (all 4,661 Phase A rows), the frozen frames
  `data/cache/kite_frames_dit15_long/{1d,15m}`, and the NIFTY 50 daily file.
- **Row selection (`select_pool`, fixed order):** keep rows that are `relaxed_selected` or `is_b0`; drop entries before 2021-01-01 (79); drop
  Phase A corporate-action exclusions (5); drop duplicate orders, keeping the earliest HTF formation (2). Pool: **4,575** rows.
- **Per-row features (`compute_features`):** returns the 18 values or an exclusion reason; it never imputes. Excluded at this stage: 20 rows with fewer
  than 63 prior stock bars (warm-up) and 3 rows whose 63-day look-back crosses a flagged corporate action. Result: **4,552 rows, 489 tickers, no NaN or inf**.
- **Important logic:** `entry_idx = searchsorted(15m timestamps, entry_time)`. The entry bar is used *only to locate its position*; every price or ATR
  value comes from positions `< entry_idx`. Daily data use only bars dated before the entry date (`asof.daily_index_asof`). Zone positions from `ltf_key` / `htf_key`
  are checked against the stored `T_L` / `T_H` close times. ATR is the legacy causal Wilder ATR, so truncating later data cannot change it.
- **Outputs:** `tier1/features.csv` (meta columns first, then the 18 model columns), `exclusions.csv` (109 rows with exact reasons), `manifest.json`
  (source hash, code hash, counts), `report.txt`. A second full run is byte-identical.
- **Tests (15, `tests/test_phase_b_features.py`):** registry frozen; every formula with controlled ATR for demand and supply; the entry bar and the entry-day
  daily bar are never read (absurd values do not change anything); scrambling everything after the decision time leaves all features unchanged (with a
  sensitivity check that scrambling the last completed bar *does* change `approach_speed_atr`); truncation equivalence on synthetic and real tickers; all
  exclusion reasons; deterministic build; dataset integrity against the manifest.
- **Connects to:** `labels.py` reads `features.csv`.

### `src/ml/labels.py` and `scripts/run_phase_b_labels.py` [IMPL][TEST]
- **Inputs:** `tier1/features.csv` and the Phase A candidates (for tracing).
- **Logic:** `label_from_outcome`: WIN to 1, LOSS to 0, AMBIGUOUS / CENSORED / OPEN / NOFILL to no label. Every row is kept with an explicit `label_status`.
  As an independent check each row is replayed again with the unchanged `src/replay.py` through the Phase A call path and compared with the stored Phase A fields
  (`replay_check`). `phase_a_src_row` traces each row to its Phase A source row.
- **Outputs:** `labels/labeled.csv` (4,552 rows: the features plus 5 label columns), `manifest.json`, `report.txt`. Result: 1,229 WIN, 2,653 LOSS, 669 AMBIGUOUS,
  1 CENSORED, 0 OPEN, 0 NOFILL; 4,552 of 4,552 rows replay identically. Byte-identical on rerun.
- **Leakage protection:** the five label columns are in `FORBIDDEN`; the model columns in the labeled file are bit-identical to the feature file (tested).
- **Tests (15, `tests/test_phase_b_labels.py`):** target-before-stop, stop-before-target, gap through the stop, same-bar ambiguity with and without minute data,
  target-in-fill-bar, censored / open / no-fill, determinism, row retention, traceability, count reconciliation with Phase A.
- **Connects to:** `splits.py` reads `labeled.csv`.

### `src/ml/splits.py` and `scripts/run_phase_b_folds.py` [IMPL][TEST]
- **Inputs:** `labeled.csv`, the NIFTY trading calendar.
- **Logic:** `WFConfig` (frozen design), `embargo_start`, `build_folds`, `fold_table`, `assignments`, `check_folds`. Builds the six folds and runs 93 explicit
  leakage checks; the runner exits with an error if any fails.
- **Outputs:** `folds/folds.csv` (one row per fold: periods, row counts, W/L, purge / embargo counts, minimum-sample verdicts), `fold_assignments.csv`
  (fold, row_id, role), `manifest.json`, `report.txt`.
- **Tests (18, `tests/test_phase_b_folds.py`):** embargo counts trading days (incl. a holiday), purge at the test and at the validation boundary, chronology,
  unresolved rows never fitted, holdout never used, sibling handling, minimum-sample flags, determinism and row-order independence, and five tests that
  *corrupt a fold on purpose* and require the checks to fail.
- **Connects to:** the future model code will take `fold.idx["fit" | "validation" | "pool" | "test"]` positions and the matching rows of `labeled.csv`.

### Phase A and documentation [FROZEN]
`docs/PHASE_A_FREEZE.md` fixes the rule-only baselines (DIT15 318 / WIT 111 / MIT 36 strict trades), decisions D1-D7 (formation timing, session-aligned 2h bars,
minute-data resolution, gap-fill beyond the stop stays AMBIGUOUS, Kite data split-adjusted, cost scenarios, DIT15 first), and the rule that any change to the
Phase A modules invalidates the comparison. `docs/PHASE_B_PLAN.md` is the design; `PHASE_B_FEATURES_REPORT.md`, `PHASE_B_LABELS_REPORT.md`, `PHASE_B_FOLDS_REPORT.md`
report what was built and verified; `docs/IMPLEMENTATION_PLAN.md` is the whole-system plan.

---

## 3. The 18 model columns

**Glossary**
- **LTF / HTF:** lower (execution) timeframe and higher (bias) timeframe. DIT15: HTF = daily, LTF = 15-minute, trend = 2-hour. The HTF zone gives the bias; an LTF
  zone formed inside it gives entry (proximal edge), stop (distal edge) and a 2R target.
- **T_d:** the decision time = the start of the 15-minute bar in which price first trades into the LTF zone (`entry_time`). The model is imagined to score the
  candidate at that moment.
- **D-1:** the last daily bar dated strictly before the entry date. For an intraday decision on day D the daily bar of day D is not final, so daily information
  comes from D-1.
- **T_L / T_H:** the close of the LTF / HTF leg-end bar (when the zone was complete).
- **ATR:** Wilder-smoothed average true range, 14 periods, causal (the value at bar i uses bars up to i only). Used to express sizes in "volatility units" so
  features compare across stocks and price levels.
- **trend_entry:** the point-in-time trend state at T_d from the Phase A trend classifier (zone breaks on the 2-hour frame; an all-time high forces "up"; only bars closed by T_d).
  Three states, encoded as two dummies `trend_up`, `trend_down`; "sideways" is the reference (both 0).
- **Why scaling must be inside each training fold:** standardising uses the mean and standard deviation of the data. If those are computed on all rows, the test
  period's distribution leaks into the training transform (and the test period would be scaled by statistics from its own future). Each fold therefore fits the
  scaler on that fold's training rows only and applies the fitted transform to validation and test. The features are stored raw and unclipped on purpose; several are
  heavy-tailed (`ltf_base_count` up to 40, `htf_base_count` up to 51, `log_ltf_age_bars`, `cost_in_r`, `risk_atr_d`), so scaling and any clipping belong to the
  walk-forward pipeline, fitted per fold.

| # | Column | Calculation concept | Why it might help (hypothesis) | Known at | Why it does not leak |
|---|---|---|---|---|---|
| 1 | `ltf_base_count` | length of the contiguous run of small-body ("base") candles before the LTF legout (strict V2 definition, cap 5 for B0, uncapped in the pool) | a long consolidation may mean absorbed orders (stronger) or a messy zone (weaker); the old rule capped it at 3-5 | T_L | computed from bars up to the leg start; stored by Phase A at zone formation |
| 2 | `htf_base_count` | same on the daily HTF zone, counted with the strict HTF config | same idea on the bias zone | T_H | bars up to the HTF leg end |
| 3 | `htf_strong_legout` | 1 if the HTF legout gapped open beyond 0.5 ATR or absorbed a second impulsive candle | a forceful departure may indicate real imbalance | T_H | determined by the legout candles, all closed by T_H |
| 4 | `ltf_leg_body_atr` | sum of `|close-open|` over the LTF leg candles divided by ATR15 at the leg-end bar | size of the explosive move relative to normal volatility | T_L | leg candles and the ATR at the leg end are all closed by T_L |
| 5 | `htf_zone_width_atr` | `|htf_proximal - htf_distal|` divided by daily ATR at the HTF leg-end bar | a wide HTF zone leaves more room for the LTF entry to sit anywhere in it | T_H | zone lines and the ATR at the leg end |
| 6 | `overlap_frac` | share of the LTF zone's height that lies inside the HTF zone (at least 0.30 by rule) | confluence between timeframes | T_H | both zones are complete by T_H |
| 7 | `ltf_pos_in_htf` | `(entry_price - htf_distal)/(htf_proximal - htf_distal)`: 0 = HTF distal, 1 = HTF proximal; can leave [0, 1] | where in the bias zone the entry sits | T_H | only zone levels |
| 8 | `wick_fresh_fail` | 1 if an earlier daily bar (date before the entry date) already reached the HTF base's wick extreme (the old R10 rule, now a flag) | an HTF level already tested may be used up | D-1 | strict date comparison; today's bar is excluded |
| 9 | `log_ltf_age_bars` | natural log of the number of 15m bars between the LTF leg end and the entry bar | fresher zones may react more strongly; log tames a range of 2 to 31,812 bars | T_d | counts positions; the entry bar's prices are not read |
| 10-11 | `trend_up`, `trend_down` | dummies for `trend_entry` | alignment with the prevailing trend (the old filter blocked counter-trend trades) | T_d | classifier uses only bars closed by T_d (bar-close event stamps; verified in Phase A) |
| 12 | `risk_atr_d` | risk (entry minus stop, price units) divided by daily ATR at D-1 | very tight stops relative to daily volatility are easily stopped by noise | D-1 | ATR taken at D-1, not the entry day |
| 13 | `approach_speed_atr` | `(close[entry_idx-1] - close[entry_idx-9]) / ATR15[entry_idx-1]`, 8 completed 15m close-to-close intervals, overnight gaps included, signed so that **positive = price moving toward the zone** (demand: falling, supply: rising) | fast arrival (momentum into the zone) vs slow drift | T_d | only bars strictly before the entry bar |
| 14 | `cost_in_r_rt0.20` | `0.002 * entry_price / risk`: the round-trip cost at 0.20% expressed in R (exit price unknown at T_d, so the entry price is used for both legs; median 0.32 R) | small-risk trades are dominated by cost; it is also an input of the take rule (section 6) | T_d | uses only entry price and risk, never the realised exit |
| 15 | `type_demand` | 1 for demand (long), 0 for supply (short) | long / short asymmetry in the sample | T_H | zone type |
| 16 | `nifty_above_200dma` | 1 if the NIFTY 50 close at D-1 is above the mean of its last 200 closes ending at D-1 | broad-market regime | D-1 | as-of join to the previous day (a same-day join was a Phase A bug, fixed) |
| 17 | `stock_rs63` | stock's 63-bar return at D-1 minus NIFTY's 63-bar return at D-1; each series uses its own 63 prior daily bars; fewer than 63 stock bars = warm-up exclusion | relative strength: leaders versus laggards | D-1 | only daily bars before the entry date |
| 18 | `is_0915_bar` | 1 if the entry bar starts at 09:15 (33% of entries) | the opening bar carries gaps and unusual volatility | T_d | derived from the timestamp |

Why they are not leaking in general: every value is a function of data that were final before T_d (or before the entry date for daily data). This is enforced by
construction (position and date rules in `features.py`) and tested (truncation and future-scrambling tests, section B at the end).

---

## 4. Labeling

**Definition (frozen).** Decision time = start of the entry 15m bar. For each candidate the outcome comes from the Phase A replay (`src/replay.py`), which walks the
15-minute bars forward from the entry bar:
- **Fill:** the first bar that trades through the entry level; at the open if it gaps through. Stop and target exist only after the fill.
- **WIN (label 1):** the **+2R target** (entry + 2 x risk for demand, mirrored for supply) is reached before the stop.
- **LOSS (label 0):** the **-1R stop** (the LTF distal) is reached first. A gap through the stop books at the open, so R can be below -1.
- **AMBIGUOUS:** the order of events inside one bar cannot be settled even after the cached 1-minute drill-down: the target in the fill bar (it may have been touched before
  the fill), stop and target in the same bar, a gap-fill that opens beyond the stop (kept ambiguous by decision D4), or a day with missing intraday bars.
- **CENSORED:** the position is filled but the data end before the 90-day horizon, so the outcome is not yet knowable (1 row in the dataset).
- **OPEN:** filled, nothing happened within the full 90-day horizon (none in this dataset). **NOFILL:** the entry level is never traded (none; it would signal a bar-mapping bug).

**Why AMBIGUOUS is excluded from model fitting.** The true outcome is unknown. Assigning one (for example by the old heuristic, as the pre-hardening numbers did) would
train the model on invented labels. The rule is never to convert an AMBIGUOUS row into a win or loss. It is also a bias risk: the ambiguous rows (669, 14.7%) are
concentrated in gap and wide-bar entries, so the evaluation reports the ambiguous rate and best / worst bounds for every strategy, and by predicted-probability decile.
AMBIGUOUS rows stay in the test windows so they are counted in the trading evaluation.

**Why CENSORED (and OPEN, NOFILL) are excluded.** There is no valid label: the outcome is not knowable or not a trade. Using the position's mark-to-market would create
a label with a different meaning.

**Why labels depend on information after the decision point.** A label is by definition the future. The replay uses bars from the entry bar onward; features use only bars before it.
That is exactly the separation that makes this supervised learning rather than hindsight.

**Why labels must never enter the feature set.** The target would then be predicting itself. The protections: the label and all outcome / replay columns are in
`FORBIDDEN`, `assert_no_forbidden` runs before any model matrix is built, and a shuffled-label sanity test is planned (out-of-sample AUC with shuffled labels must be near 0.5;
if it is not, something leaks). Label counts: 1,229 WIN / 2,653 LOSS / 669 AMBIGUOUS / 1 CENSORED; resolved win rate 31.66% (3,882 rows), against a break-even of
33.3% for a 2:1 trade before costs.

---

## 5. Walk-forward validation

**Why not a random train / test split.** Rows are neither independent nor exchangeable. 97% of tickers have several candidates; candidates cluster in time (a market regime
produces many similar trades); the label of a trade is determined by the following days of prices. A random split would put near-neighbours of every test trade in training
(including the same stock a day earlier and trades whose outcome windows overlap the test row) and would train on the future of the test period. The honest question is
"given only the past, how do we do on the future", which requires a chronological split.

**Folds [IMPL][TEST][FROZEN]** (from `folds/folds.csv`; resolved trades only for fit, validation and pool, W/L in brackets):

| Fold | Fit | Validation (last 6 months before test) | Test window | Pool (fit + validation) | Test resolved |
|---|---|---|---|---|---|
| 2023H1 | 2021-01-01 .. 2022-07-01: 808 (261/547) | 2022-07 .. 2023-01: 308 | 2023-01-01 .. 2023-07-01 | 1,123 (346/777) | 300 (100/200) |
| 2023H2 | .. 2023-01-01: 1,123 | 2023-01 .. 2023-07: 275 | 2023-07-01 .. 2024-01-01 | 1,410 (439/971) | 392 (131/261) |
| 2024H1 | .. 2023-07-01: 1,410 | 2023-07 .. 2024-01: 346 | 2024-01-01 .. 2024-07-01 | 1,781 (567/1,214) | 378 (121/257) |
| 2024H2 | .. 2024-01-01: 1,781 | 2024-01 .. 2024-07: 372 | 2024-07-01 .. 2025-01-01 | 2,199 (700/1,499) | 318 (103/215) |
| 2025H1 | .. 2024-07-01: 2,199 | 2024-07 .. 2025-01: 303 | 2025-01-01 .. 2025-07-01 | 2,508 (797/1,711) | 363 (108/255) |
| 2025H2 | .. 2025-01-01: 2,508 | 2025-01 .. 2025-07: 361 | 2025-07-01 .. 2026-01-01 | 2,884 (913/1,971) | 371 (123/248) |

Chronology for one fold (here 2024H1), left to right in time:

```
2021-01-01 ----- FIT ----------------- 2023-07-01 -- VALIDATION -- 2023-12-22 | embargo | 2024-01-01 -- TEST -- 2024-07-01        2026-01-01 -> HOLDOUT
                 (rows entered, with outcome       (last 6 months of             5 NIFTY       (all statuses kept for           (never used)
                  finished, before validation)      the training window)         trading days   evaluation; only WIN/LOSS
                                                                                                 count in resolved metrics)
Pool for the final fold model = FIT + VALIDATION (+ rows dropped only to keep the validation set clean).
```

- **Expanding training window:** every fold trains on everything from 2021-01-01 up to its boundary, so later folds see more data (the largest pool, for 2025H2, reaches back about 4.5 years).
- **Validation role:** the last 6 months of the training window. It is where hyperparameters (the logistic C and the small gradient-boosting grid), early stopping and a calibration
  check are chosen. It is *not* the test. Each fold's validation window equals the previous fold's test window; this is normal for an expanding walk-forward, but it means
  hyperparameters for fold k are chosen on data that served as a test window for fold k-1.
- **Test role:** the out-of-sample evaluation window. The model, hyperparameters and decision rule are frozen before test rows are scored. The six test windows concatenated give one
  out-of-sample stream of 2,122 resolved trades (686 wins), 2023-2025.
- **5 trading-day NIFTY embargo:** at each boundary (test start and validation start), resolved rows entered in the 5 trading days before it (counted on the NIFTY calendar, so holidays
  are skipped) are dropped from the earlier side. Reason: trades entered just before the boundary are still open when the boundary arrives and are correlated with what follows.
  Counts at the test boundary: 12, 25, 46, 6, 15, 2.
- **Purge:** among rows entered before the embargo, any whose outcome time (`exit_time`) is at or after the boundary is dropped, so no training label depends on prices inside the test window.
  On the real data the purge never fires (0 rows in all folds): almost all trades exit within days, and the embargo already covers any that could reach the boundary. It is exercised by synthetic tests.
- **Sibling protection:** rows of one HTF zone (same ticker and `htf_key`) belong to the side of the group's earliest entry; a later member that would land on the other side of a boundary
  is removed from that side. Also 0 on the real data (only 6 candidate pairs share an HTF zone).
- **2026 as an untouched final holdout:** the 781 rows with `entry_time` on or after 2026-01-01 are never a fit, validation or test row of any fold, and a window that reaches into 2026 is
  rejected. It is reserved for one final run after the design is frozen. Caveat stated in the docs: 2026 is only partly clean because chart reviews of 2026 setups influenced earlier rule choices;
  data after the freeze date (paper trading) is the only fully clean test.
- **Checks:** 93 explicit checks, all passing (roles disjoint; only WIN / LOSS rows fitted; latest training entry before the embargo start; latest training outcome before the test start;
  embargo spans exactly 5 trading days; no HTF-zone group on both sides; pools expand; no holdout row in any role). The checks are themselves tested to fail on corrupted folds.
- **Minimum sample rules** (all folds pass): at least 300 resolved training rows, at least 180 wins (10 per feature x 18), at least 100 resolved test rows.

---

## 6. First model: logistic regression [PLAN]

**What the repository documents** (`docs/PHASE_B_PLAN.md` sections 8, 10, 12): L2-regularised logistic regression (scikit-learn, lbfgs), inputs standardised with the *training fold only*,
the regularisation strength C chosen from {0.01, 0.1, 1.0} by log-loss on the inner validation window, no class weights (calibrated probabilities are needed),
WIN / LOSS rows only, and a take / skip rule fixed in advance:

> take the trade if expected net R is positive: `2*p - (1-p)*L - c > 0`, i.e. `p > (L + c) / (2 + L)`

where `p` is the model's win probability, `L` is the mean loss size in R on the training rows (about 1, larger because gap stops can exceed -1R) and `c` is the
round-trip cost in R for the scenario (`cost_in_r_rt0.20` for the primary one). For example, with `L = 1` and `c = 0` the cut-off is `p > 1/3` (the 2:1 break-even); with `c = 0.32` it rises
to about 0.44. The rule is fixed and never tuned on test data.

**Open point to resolve before coding.** Your description says the *validation* window chooses the probability threshold. The repository documents a *fixed expected-value cut-off*
and uses validation for C, early stopping and a calibration check; it does not document a threshold fitted on validation. Both are leakage-safe if the procedure is fixed in
advance and uses validation only, but they are different experiments; the choice has to be written down (and, if validation chooses the threshold, the exact objective, such as
net expectancy with a minimum trade count) before the first run. Nothing in the repository has implemented either yet.

**What it is, mathematically.** For a feature vector `x` (the 18 standardised columns), the model computes a linear score and squashes it to a probability:

```
z = w . x + b                  p(WIN | x) = sigma(z) = 1 / (1 + e^(-z))
```

`w` (one weight per feature) and `b` are found by minimising the L2-regularised log-loss over the training rows:

```
minimise   -sum_i [ y_i log p_i + (1 - y_i) log(1 - p_i) ]  +  (1 / (2C)) * ||w||^2
```

(scikit-learn's `C` is the inverse of the penalty strength: smaller C = stronger shrinkage.) The loss is convex, so lbfgs finds the single optimum and the result is
deterministic for a given dataset. Each weight is the change in log-odds per one standard deviation of that feature, holding the others fixed.

**Why it is a good first model here.**
- Few parameters (19) for 1,100 to 2,900 training rows per fold: low variance, low overfitting risk.
- Calibrated by construction (the loss is a proper scoring rule), which the expected-value cut-off needs.
- Interpretable: standardised coefficients with bootstrap intervals say which features move the probability and in which direction.
- Fast and deterministic, so the whole walk-forward can be repeated exactly.
- It sets a floor: if a more flexible model cannot beat it, the extra complexity is not justified.
- Its limit is the assumption of a linear effect in log-odds and no interactions; that limit is exactly what the comparison model probes.

**Process.** Per fold: fit the scaler and the model on the fold's training rows only; choose C on the inner validation window; (re)fit on the pool; score the test rows; apply the frozen rule.
Deterministic: fixed solver, fixed seeds wherever randomness exists, fixed fold definitions (the folds file is hash-stamped).

---

## 7. The model comparative study [PLAN]

**What the repository decides** (`docs/PHASE_B_PLAN.md` sections 10-11 and `docs/IMPLEMENTATION_PLAN.md` Phase 5):

| Model | Status |
|---|---|
| L2 logistic regression | **planned, first baseline** |
| `HistGradientBoostingClassifier` (scikit-learn) | **planned, the comparison model** |
| Random Forest | **explicitly deferred** ("not in the first experiment: calibration needs data we do not have") |
| LightGBM | **explicitly excluded from the first experiment** (HGB covers the need with one dependency) |
| XGBoost | **not mentioned in any repository document** (only the earlier design conversation named "XGBoost or LightGBM" as options); not planned |
| Deep learning | **explicitly excluded** from the first experiment (`IMPLEMENTATION_PLAN.md`: "no model beyond the two chosen"; the rationale given in the design discussion was tabular data and a small sample) |

Non-model comparators are also defined (section 10): the whole pool, the strict B0 list, a random filter, and the best single old filter chosen on training data.

### Model 1: L2 logistic regression
- **How it works / what it captures:** section 6. Captures monotone, additive effects of standardised features on the log-odds.
- **Strengths:** low variance, calibrated probabilities, interpretable, deterministic, fast.
- **Weaknesses:** cannot represent interactions (for example "tight stop *and* 09:15 entry") or non-monotone effects (a feature that helps in the middle of its range) unless they are hand-engineered, which the frozen registry forbids.
- **Overfitting risk:** low (19 parameters). Sensitive to heavy-tailed raw features, hence per-fold standardisation; collinearity (for example `risk_atr_d` and `cost_in_r_rt0.20`) can make individual coefficients unstable.
- **Interpretability:** high.
- **Suitability for the sample size:** good. The largest training pool is 2,884 resolved trades (3,882 resolved in total), with 913 wins in the largest pool. The events-per-variable rule (10 wins per feature) is met in every fold.
- **Expected behaviour on tabular trading features:** a modest signal at best; financial features are weakly predictive and noisy, so a good result is probabilities only slightly better than the base rate.
- **Role in the study:** the reference every other model must beat.

### Model 2: `HistGradientBoostingClassifier`
- **How it works:** it builds many small decision trees one after another. Each new tree is fit to the errors (the gradient of the log-loss) of the current ensemble, and the trees' outputs are
  added, scaled by a learning rate. "Histogram" means feature values are first grouped into at most 255 bins, which makes the splits fast. The documented configuration is deliberately
  small: depth 3, at most 7 leaves, at least 50 rows per leaf, learning rate 0.05, L2 regularisation 1.0, at most 4 configurations tried and all logged, probabilities calibrated on validation
  (isotonic if at least 1,000 rows, otherwise Platt). It needs no feature scaling, but it uses the same frozen 18 columns.
- **What patterns it can capture:** threshold effects ("the effect appears only above x"), interactions between features, and non-monotone relationships, without those being specified in advance.
- **Strengths:** typically the strongest model class on tabular data; handles different feature scales and outliers.
- **Weaknesses:** needs more data to find real interactions; its raw probabilities are usually miscalibrated (hence the calibration step); less interpretable.
- **Overfitting risk:** higher than logistic regression, and real at 1,100 to 2,900 rows with a ~32% base rate and weak signal. The plan's mitigations are shallow trees, a minimum leaf size, a small fixed grid, tuning only on the inner validation window, and logging every configuration tried.
- **Interpretability:** lower. Planned tools (later, after the first evaluation): permutation importance on out-of-sample folds, SHAP (the `shap` package is not installed yet) and ALE plots.
- **Suitability for the sample size:** marginal by design; that is part of what the study measures. It is useful to know whether flexibility helps at this size or only adds variance.
- **Expected behaviour:** if the real relationships are approximately additive, it will match logistic regression or do slightly worse; if there are real interactions, it can do better.
- **Why it is the right comparison:** it is the smallest step up in flexibility with the same inputs, labels and folds, so any difference is attributable to model form rather than to data.
- **Implementation point to settle (not yet decided in the repo).** The plan says "early stopping on inner validation". scikit-learn's `HistGradientBoostingClassifier` cannot take an explicit validation set; its built-in
  early stopping carves a *random* fraction out of the training rows, which would be a random split inside training. To stay chronological, the number of iterations should be chosen as a hyperparameter on the inner validation window
  (a fixed `max_iter` grid) with the built-in early stopping off. This has to be written down before coding.

---

## 8. Fair comparison

Every model faces exactly the same conditions; only the model form differs.

- **Same frozen 18 features** (`tier1-v1`); no feature added, removed or transformed for one model (scaling is a pipeline step fitted per fold; trees do not need it but receive the same columns).
- **Same labels:** `labeled.csv`, WIN / LOSS only for fitting, same ambiguous / censored handling in evaluation.
- **Same folds and chronology:** the six frozen folds, same fit / validation / pool / test row sets, same embargo and purge, same 2026 holdout.
- **Same decision-rule procedure:** the same fixed expected-value cut-off (or, if adopted, the same validation-only threshold procedure) for both models; the same cost scenario.
- **No test-set tuning:** hyperparameters, calibration and thresholds are chosen on validation only; the test rows are scored once with everything frozen. The final 2026 holdout is run once, through one command that refuses a second run.
- **Pre-registered grids and logged configurations:** the logistic C grid and at most 4 boosting configurations are fixed in advance; every configuration tried is recorded in an experiment log (a multiple-testing record).
- **Deterministic seeds:** fixed random seeds wherever a model or bootstrap uses randomness (the existing bootstrap code uses seed 12345); fold files are hash-stamped; a model run is reproduced by rerunning with the same inputs.
- **Same evaluation metrics and the same baselines** (section 9-10), reported identically for each model, including the same cost scenarios.
- **Leakage and sanity checks run for each model:** forbidden-column check, shuffled-label test, calibration reliability per fold.

---

## 9. Metrics

### ML metrics (about the probabilities) [PLAN]
- **ROC-AUC:** probability that a randomly chosen WIN gets a higher score than a randomly chosen LOSS (0.5 = no information). It measures ranking, ignores the threshold and the payoff.
- **PR-AUC:** area under the precision-recall curve; informative when the positive class is rare (wins are about 32%). The baseline value is the base rate, not 0.5.
- **Precision (at the chosen threshold):** among the trades the model accepts, the share that are WIN. This is the model's realised win rate on taken trades.
- **Recall (at the chosen threshold):** among all WINs, the share the model accepts. High precision with very low recall means the filter is accepting too few trades to matter.
- **Predicted-positive count:** how many trades the model takes (take-rate). It determines whether the filter just reduces the number of trades and whether the sample is large enough (the success criteria need at least 100 taken trades).
- **Brier score:** mean squared error of the probability; it is judged against a base-rate predictor. Log-loss and a reliability curve / expected calibration error are also planned.

### Trading metrics (about money) [PLAN; building blocks IMPL in `src/portfolio.py` and `src/costs.py`]
- **Trade count** (and trades per year, take-rate).
- **Win rate:** WIN / (WIN + LOSS), with a bootstrap 95% interval; AMBIGUOUS bounds (all lost .. all won) are shown.
- **Expectancy:** mean R per resolved trade. Gross uses the replay R; net subtracts the cost in R.
- **Profit factor:** gross profit / gross loss in R.
- **Total R:** sum of R over resolved trades.
- **Maximum drawdown:** the largest peak-to-trough fall of the cumulative R curve, trades ordered by exit time.
- **Costs at 0%, 0.10%, 0.20%, 0.30% round trip:** `net R = gross R - cost_R`, `cost_R = (pct_per_side/100) * (fill + exit price) / risk`. No broker figure is agreed, so all scenarios are reported and none is chosen to flatter a result.
  Capital-constrained versions (Rs 1,00,000, no leverage) and per-year / per-ticker-group stability are also reported.

**Why accuracy alone is not the primary metric.** (1) The classes are imbalanced: a model that always says "LOSS" is right about 68% of the time and earns nothing. (2) It ignores payoff: a win is worth +2R, a loss -1R, plus costs
that vary by trade (0.03 to 1.65 R), so a model can raise accuracy while lowering expectancy. (3) It depends on one threshold. (4) It is blind to how many trades are taken. A better classifier is only useful if the *resulting trading
strategy* improves out of sample after costs, which is the project's stated success test.

---

## 10. Rule-only vs ML-filtered vs random filter

- **A. All resolved rule-engine trades.** The reference: take everything the rules produce (the strict B0 list, and the whole relaxed pool "B1"). It answers what the unfiltered strategy earns.
- **B. ML-filtered trades.** The same candidates, keeping only those the model scores above the frozen rule. Each kept trade carries its own stored outcome and R; nothing is re-simulated.
- **C. Random filter with the same take-rate.** From the same candidates, keep a random subset of the same size as the ML-kept set (1,000 draws, fixed seed) and compute the same metrics for each draw, giving a distribution.

**Why the random control is essential.** Any filter that takes fewer trades changes the numbers: fewer trades, a different mix by year, a smaller drawdown, a higher or lower average by luck. In a small, noisy sample, random subsets
of a break-even strategy swing widely. If ML-filtered expectancy lies inside the range of random subsets of the same size, the model has shown *nothing beyond taking fewer trades*. If it sits above the 95th percentile of the random
draws, the model's selection carries information that chance does not explain. It therefore separates "ML selected better trades" from "ML selected fewer trades", which accuracy or AUC cannot do.

A fourth comparator is also defined: the best single old filter (for example "only trend-aligned") chosen on training data, to check that the model beats a simple rule and not just the unfiltered set.

---

## 11. End-to-end example (conceptual; every number is invented for illustration)

1. **Candidate generation.** A hypothetical demand setup in `EXAMPLE.NS`: a daily demand zone (HTF) formed on 2025-01-22 and a 15-minute demand zone inside it, matched by the Phase A rules. The LTF zone stays untouched until price first trades
   into its proximal edge in the 15-minute bar starting **2025-03-04 09:15**. That is the decision time T_d. Entry = LTF proximal, stop = LTF distal, target = entry + 2 x risk, shares per the sizing rule.
2. **18 features** (made-up values, all known at T_d or earlier): `ltf_base_count` 3, `htf_base_count` 4, `htf_strong_legout` 1, `ltf_leg_body_atr` 3.1, `htf_zone_width_atr` 0.9, `overlap_frac` 1.0, `ltf_pos_in_htf` 0.82,
   `wick_fresh_fail` 0, `log_ltf_age_bars` 5.6, `trend_up` 1, `trend_down` 0, `risk_atr_d` 0.19, `approach_speed_atr` 1.9, `cost_in_r_rt0.20` 0.32, `type_demand` 1, `nifty_above_200dma` 1, `stock_rs63` 0.03, `is_0915_bar` 1.
3. **Label (computed later, never an input).** The replay walks the 15m bars from 09:15; suppose the stop is not touched and the target is reached on 2025-03-05. Outcome WIN, label 1, R = +2.0. (Had the target and stop both
   been touched inside one minute, it would be AMBIGUOUS with no label.)
4. **Fold assignment.** Entry 2025-03-04 lies in the **2025H1 test window** (2025-01-01 .. 2025-07-01). The 2025H1 model was trained on the pool of 2,508 resolved rows (entries before the embargo start 2024-12-24, outcomes finished by
   2025-01-01), with 2024-07 .. 2025-01 as the inner validation window. This candidate was not in training.
5. **Scaler.** The `StandardScaler` was fit on the 2025H1 training rows only (mean and standard deviation per column) and is now applied to this candidate's 18 values.
6. **Model probability.** The frozen logistic regression (C chosen on validation) maps the scaled vector to `p = sigma(w . x + b)`; suppose **p = 0.47**.
7. **Threshold.** The frozen rule uses the fold's training mean loss `L` (say 1.05) and this candidate's cost `c = 0.32`: take if `p > (L + c) / (2 + L) = 1.37 / 3.05 = 0.449`. (If the project instead adopts a threshold chosen on the validation window,
   that frozen number would be used here.)
8. **Test decision.** 0.47 > 0.449, so the candidate is **accepted**. A candidate with p = 0.40 would be rejected and simply not counted.
9. **Accepted / rejected trade.** The accepted trade keeps its stored outcome: +2R gross, minus its cost (0.32 R at the 0.20% scenario), so +1.68 R net. A rejected WIN would be a missed gain; a rejected LOSS an avoided -1R.
10. **Trading metrics.** All accepted trades of the 2025H1 window (and of the other five windows, concatenated into one out-of-sample stream) are combined: count, win rate, expectancy, profit factor, total R, maximum drawdown, at 0 / 0.10 / 0.20 / 0.30%.
    They are compared with the unfiltered trades (A) and with the 1,000 random subsets of the same size (C).

---

## 12. Current status

| Component | Status | Evidence / file | Next step |
|---|---|---|---|
| Phase A rule engine, DIT15 / WIT / MIT baselines | implemented, tested, **frozen** | `src/candidates.py`, `src/candidates_mtf.py`, `docs/PHASE_A_FREEZE.md`; tests in `test_phase_a.py`, `test_phase_a_mtf.py` | none (do not change without a new baseline) |
| Candidate dataset (DIT15 relaxed pool) | implemented, **frozen** | `results/nogit-145d6302/phase_a/pit_refetch/candidates.csv` | none |
| Feature registry, 18 columns | implemented, tested, **frozen** | `src/ml/registry.py` (`tier1-v1`) | none |
| Feature extraction | implemented, tested | `src/ml/features.py`, `scripts/run_phase_b_features.py`, `test_phase_b_features.py` (15) | none; confirm `approach_speed_atr` sign convention was accepted |
| Labels | implemented, tested | `src/ml/labels.py`, `scripts/run_phase_b_labels.py`, `test_phase_b_labels.py` (15) | none |
| Walk-forward folds + 93 leakage checks | implemented, tested, **frozen** | `src/ml/splits.py`, `scripts/run_phase_b_folds.py`, `test_phase_b_folds.py` (18) | none |
| Leakage tests on features / folds | implemented | truncation, future-scrambling, forbidden-column, corrupted-fold tests | add model-level tests |
| Model training (LR, then HGB) | **planned** | `docs/PHASE_B_PLAN.md` sections 10-11; no `src/ml/models.py` | write the pipelines; settle the threshold procedure and HGB iteration selection (sections 6-7) |
| Hyperparameter / calibration selection on validation | planned | `PHASE_B_PLAN.md` section 9-11 | implement with an experiment log |
| Take / skip rule and threshold | planned (rule documented; validation-chosen variant undecided) | `PHASE_B_PLAN.md` section 8 | decide and write down before coding |
| Shuffled-label sanity test | planned | `PHASE_B_PLAN.md` section 6 | implement with the model code |
| Evaluation vs B0 / B1 / random filter / best single filter | planned; building blocks implemented | `src/portfolio.py`, `src/costs.py`, `scripts/compare_phase_a_2021.py` | write `evaluate` code, the 1,000-draw random control, paired block bootstrap |
| Explainability (coefficients, permutation importance, SHAP, ALE) | planned, after the first evaluation | `PHASE_B_PLAN.md` section 15; `shap` not installed | after results exist |
| Random Forest | **explicitly deferred** | `PHASE_B_PLAN.md` section 11 | revisit only if the first study justifies it |
| LightGBM, deep learning | **explicitly excluded** from the first experiment | `PHASE_B_PLAN.md`, `IMPLEMENTATION_PLAN.md` | none |
| XGBoost | not in any repository document | n/a | none |
| WIT / MIT ML | not started (small samples: 105 and 34 resolved; no relaxed pool) | `docs/PHASE_A_MTF_RESULTS.md` | after the DIT15 study, if at all |
| Final 2026 holdout run | planned, **untouched** | folds manifest: 781 rows unused | run once after the design is frozen |
| Production / API / UI | not started, intentionally | `docs/IMPLEMENTATION_PLAN.md` Phase 10 | only after the final validation |

---

## A. What happens inside the ML backend

Phase A produces candidate trades; `features.py` turns each into 18 numbers using only information available at the start of its entry bar; `labels.py` attaches the realised outcome
(WIN = 1 / LOSS = 0, else no label) from the deterministic replay; `splits.py` arranges the labelled rows into six chronological folds with an embargo and purge. For each fold a
scaler and a model are fit on the training rows only, hyperparameters are chosen on the 6-month validation window, the frozen model scores the test window, a frozen rule turns each probability into take / skip,
and the taken trades (each with its own stored outcome) are evaluated with trading metrics and costs and compared with all trades and with random subsets of the same size. The first four stages are built and tested; the model and evaluation stages are planned.

## B. How we know the experiment is leakage-safe

- **By construction:** feature values come from bars before the entry bar and from daily bars before the entry date; the entry bar's prices are never read; ATR is causal; the trend uses closed bars only; the regime uses the previous day.
- **By tests that can fail:** the scrambling test (everything after the decision time randomised, features unchanged, plus a sensitivity check that the test would detect a leak), truncation tests on real tickers, and the corrupted-fold tests (each deliberately injected leak must be caught).
- **By contract:** `FORBIDDEN` + `assert_no_forbidden` keep outcomes, raw levels, identifiers and labels out of the model matrix; labels are replayed independently and match Phase A on 4,552 of 4,552 rows.
- **By split design:** chronological folds, 5-trading-day embargo, purge by outcome time, sibling protection, 93 passing checks, a 2026 holdout that appears in no role.
- **By process:** every artifact is hash-stamped and rebuilds byte-identically; the Phase A modules are frozen; the feature set is pre-registered.
- **Not yet in place (planned):** the shuffled-label test and model-level checks, which can only run once models exist. Residual risks acknowledged in the docs: survivorship in the universe, corporate-action moves under 35% undetected, the missing 15:15 bar since August 2026,
  partial contamination of 2026 by chart reviews, and validation windows that were earlier test windows.

## C. What question the ML experiment is actually trying to answer

*Given a trade the frozen rule engine has just triggered, and using only the 18 pre-registered pieces of information known at that moment, can we predict its probability of reaching +2R before -1R well enough that skipping the low-probability trades raises
out-of-sample, after-cost expectancy (without a worse drawdown or an unusably small trade count) compared with taking every trade and compared with skipping the same number of trades at random?* It is explicitly not asking whether ML can trade on its own, whether accuracy goes up, or whether a flexible model beats a simple one in-sample.

## D. What would count as a successful model

From the pre-registered criteria (`docs/PHASE_B_PLAN.md` section 13), all measured on the 2023-2025 walk-forward stream at the 0.20% cost scenario, then confirmed in direction on the single 2026 holdout run:
(a) net expectancy above both the unfiltered strict list and the unfiltered pool, with a block-bootstrap 95% interval for the difference excluding 0; (b) net expectancy above 0 and profit factor above 1.1; (c) above the 95th percentile of the random-filter distribution;
(d) maximum drawdown no worse than the unfiltered strict list; (e) at least 100 taken trades overall and at least 30 per year; (f) better than the unfiltered strict list in at least 2 of 3 years and in at least 4 of 5 ticker groups (unseen-stock check);
(g) out-of-sample Brier score better than the base-rate predictor. Higher AUC alone counts for nothing; expectancy up with total R down is reported as "mixed". Because the baselines are weak (DIT15 B0 is negative after costs), meeting (b) after costs is a demanding bar.

## E. What would count as evidence that ML should NOT be used

- The ML-filtered expectancy lies inside the random-filter distribution (the model only reduced the trade count).
- The improvement over the unfiltered set has a bootstrap interval that includes 0, or appears in only one year or one ticker group.
- Net expectancy stays at or below 0 after the 0.20% cost, or the profit factor is below 1.1.
- Maximum drawdown is worse than the rule-only list, or fewer than 100 trades are taken.
- Out-of-sample probabilities are worse than the base rate (Brier), badly miscalibrated, or the shuffled-label test shows an AUC away from 0.5 (a sign of leakage, which invalidates the run rather than supporting ML).
- The flexible model does not beat logistic regression, or beats it only in-sample (then the extra complexity is unjustified).
- The result does not hold on the untouched 2026 holdout.
A null result is a valid result of the study: the repository's design explicitly allows concluding that the rule-based strategy should not be filtered by ML.
