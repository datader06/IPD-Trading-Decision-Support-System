# EXPERIMENT_2_PREREGISTRATION.md: pooled DIT15 + WIT + MIT meta-labeling (written before the first run)

Status: final for this run. Written before any Experiment 2 model was trained or any Experiment 2 result was seen.
Code: `src/ml_core/` (new), `scripts/run_ml_core.py`. Frozen code reused unchanged: `src/ml/{splits,models,thresholds,evaluate,experiment,features}.py`.
Experiment 1 (`docs/EXPERIMENT_1_PREREGISTRATION.md`) found no primary champion and no reliable edge; Experiment 2 does not change that result.

## 1. Question
Does one model, trained on the pooled candidates of DIT15, WIT and MIT with a strategy indicator and features that mean the same thing
in every timeframe, beat the rule-only baselines and a matched random filter out-of-fold, after costs?

## 2. Data (frozen, read-only)
| Strategy | Source | Rows used |
|---|---|---|
| DIT15 | `results/nogit-145d6302/phase_a/pit/candidates.csv` (relaxed pool, Experiment 1 pool rules) | 4,552 |
| WIT | `results/nogit-7a8ea6d9/phase_a_mtf/wit/pit/candidates.csv` (strict B0 list only) | 111 |
| MIT | `results/nogit-ff52bbc2/phase_a_mtf/mit/pit/candidates.csv` (strict B0 list only) | 36 |
Pool rules, labels (WIN=1, LOSS=0; others never fitted) and corporate-action exclusions are those of Experiment 1. Source SHA-256 values are
recorded in `dataset_manifest.json`. WIT and MIT have no relaxed pool, so they contribute very few rows (stated limitation).

## 3. Features: `tier2-agnostic-v1` (19 columns)
Only data known at the decision time: the candidates file, daily bars dated before the entry date (D-1) and NIFTY daily. Nothing reads the entry bar.
ltf_base_count, htf_strong_legout, ltf_strong_legout, overlap_frac, ltf_pos_in_htf, htf_zone_width_atr (daily ATR at D-1), risk_atr_d, trend_up, trend_down,
trend_htf_up, trend_htf_down, type_demand, cost_in_r_rt0.20, nifty_above_200dma, stock_rs63, log_ltf_age_days, log_htf_age_days, strat_wit, strat_mit.
Dropped versus Tier-1 because they are 15m-specific or missing for WIT/MIT: ltf_leg_body_atr, htf_base_count, wick_fresh_fail, log_ltf_age_bars,
approach_speed_atr, is_0915_bar. The feature list is final; it cannot change after results are seen.

## 4. Models, threshold, validation (all as Experiment 1)
Four families (logistic regression, random forest, HistGradientBoosting, XGBoost), frozen grids and seed 42 from `src/ml/models.py`; configuration chosen on
validation rows only; refit on the training pool; native probabilities. Threshold T1 (take if p*2 - (1-p)*L - c > 0 at the 0.20% cost). T2 is a secondary diagnostic only.
Expanding walk-forward folds 2023H1-2025H2 with 6-month validation, 5-day embargo, purge and sibling rules (`src/ml/splits.py`). One pooled model per fold.
The 2026 holdout is never fitted, validated, tested or scored.

## 5. Evaluation
Pooled out-of-fold stream, gross and 0.10 / 0.20 / 0.30% round-trip costs. Arms: B0 (strict rule baseline), B1 (take all), ML (T1), ML_T2 (diagnostic).
Reported for ALL rows and separately for DIT15, WIT and MIT. Per-strategy results are descriptive only: WIT and MIT have a few dozen test rows.
Control: random filter with the same take counts per fold (1,000 draws). Month-block bootstrap (2,000 draws, seed 42) of expectancy, ML minus B0 and minus B1.
AUC per strategy is reported as a ranking diagnostic.

## 6. What counts as an edge (decided now)
A model is reported as showing an edge only if ALL hold on the pooled stream at 0.20%: (a) at least 100 resolved takes; (b) net expectancy above zero;
(c) expectancy above the 95th percentile of the matched random filters; (d) the bootstrap 95% interval of ML minus B1 excludes zero.
Anything weaker is reported as "no edge established", including a positive but statistically indistinguishable result. Per-strategy numbers never establish an edge.
At most the four families above are compared in this run; any later variant is a new, separately registered experiment, and results from it must say how many variants were tried.
