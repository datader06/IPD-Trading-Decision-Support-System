# EXPERIMENT_3_PREREGISTRATION.md: ML filter on the final algorithm, baselines v5 (written before any model was fit on this data)

Status: final for this run. Written before any Experiment 3 model was fit or any Experiment 3 result was seen.
Input: `data/algo_v5/ml_dataset_baseline_v5.csv` (copied unchanged from `dz_ml_package.zip`; rules in `data/algo_v5/STATUS_algo_v5.md`, sections 13-17).
Code: `src/ml_core/adapters.py`, `src/ml_core/walkforward.py`, `scripts/run_ml_baseline_v5.py`.
Costs are deliberately out of scope here (user decision): every figure is gross R and win rate. This experiment asks one thing: does an ML filter raise the win rate?

## 1. Data
300 resolved trades of the final algorithm (no AMBIGUOUS left): DIT15 195 (2R), WIT 70 (2R), MIT 35 (3R target). Base win rates 37.4% / 45.7% / 45.7%.
`split = holdout` (56 trades, entries from 2026-01-07) is never used for fitting, selection or scoring in this experiment. Development set = `split = train` (244 trades, 2021-2025).
Known caveats, stated before the run: the sample is small; several rules and cutoffs of the algorithm (HTF base 0.6x legout, DIT15 stop buffer 0.2 ATR, MIT 3R) were chosen after looking at the same trades
(STATUS sections 13, 15, 17), so the base win rates are optimistic and any ML result inherits that bias; WIT and MIT have 70 and 35 trades in total.

## 2. Features (final, 21 columns)
From the file: ltf_risk_pct, htf_risk_pct, overlap_frac, trend_strength_atr, htf_strong_legout, ltf_strong_legout, legout_exciting_candles, legout_gap, legout_strength_score,
ltf_base_count, htf_base_count, time_at_base_score, ema_all, ema_count (sum of the eleven ema_* flags). Derived: type_demand, strat_wit, strat_mit.
From daily bars dated before the entry date and NIFTY daily: risk_atr_d (risk / daily ATR at D-1), stock_rs63, nifty_above_200dma, log_htf_age_days (entry minus htf_formed_at, in days).
One missing ltf_base_count and one missing htf_base_count are filled with 0 (documented constant, no data-dependent imputation). No outcome, exit or label column is a feature.

## 3. Models (fixed hyperparameters, no tuning: the sample is too small to tune honestly)
logistic regression (standardised, L2, C = 0.3), random forest (300 trees, max depth 3, min leaf 10), histogram gradient boosting (max depth 2, 60 iterations, learning rate 0.05, l2 1.0),
XGBoost (hist, depth 2, 120 rounds, learning rate 0.05). Seed 42. Native probabilities, no calibration.

## 4. Validation
Expanding walk-forward by calendar year: test years 2023, 2024, 2025 (172 trades). Training rows = development rows entered before the test year, minus rows whose exit_time reaches the test-year start (purge)
and rows entered in the 7 days before it (embargo). One pooled model across the three strategies. No random split anywhere.

## 5. What is reported
Pooled and per strategy (per strategy is descriptive only): base win rate of the test rows; ROC AUC; for the top 25%, 50% and 75% of trades ranked by predicted probability within each test year:
win rate with a Wilson 95% interval, average gross R and trade count. Control: 10,000 random selections of the same size per test year; p = share of draws with a win rate at least as high as the model's.

## 6. What counts as an edge (decided now)
A model shows a win-rate improvement only if, on the pooled 2023-2025 stream, ALL hold: (a) its top-50% win rate is at least 5 percentage points above the base win rate of the same rows;
(b) the random-selection p-value for the top-50% win rate is at most 0.0125 (0.05 divided by the four models, Bonferroni); (c) ROC AUC is above 0.55.
Anything less is reported as "no win-rate improvement established", including positive but non-significant lifts. Per-strategy results never establish an edge.
Four models are compared in this run; any later variant is a new registered experiment and must report how many variants were tried. The 2026 holdout stays unscored until a separate, explicit decision.
