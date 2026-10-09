# EXPERIMENT_4_PREREGISTRATION.md: eight-model comparison on the final algorithm (baselines v5), written before the run

Status: final for this run. Variant 4 of the ML study (Experiments 1, 2, 3 already found no improvement). Written before any Experiment 4 model was fit.
Same data, features, folds, embargo/purge, selection convention, random-selection control and holdout rule as `docs/EXPERIMENT_3_PREREGISTRATION.md`; only the model list changes.
Code: `src/ml_core/model_registry.py` (every model and its fixed hyperparameters live there), run with `python scripts/run_ml_baseline_v5.py --models=all --tag=exp4_zoo`.

## Models (eight, fixed hyperparameters, seed 42, no tuning)
logreg (standardised, L2, C = 0.3); random_forest (300 trees, depth 3, min leaf 10); hist_gb (depth 2, 60 iterations, lr 0.05, l2 1.0); xgboost (hist, depth 2, 120 rounds, lr 0.05);
extra_trees (300 trees, depth 3, min leaf 10); adaboost (100 depth-1 stumps, lr 0.5); knn (standardised, k = 25, distance weights); naive_bayes (Gaussian, standardised).

## Success criteria
Unchanged from Experiment 3 except for the multiple-testing correction: with eight models the random-selection p-value must be at most 0.05 / 8 = 0.00625.
A model shows a win-rate improvement only if, pooled over 2023-2025, (a) its top-50% win rate is at least 5 points above the base win rate, (b) p <= 0.00625, (c) ROC AUC > 0.55.
Anything else is "no win-rate improvement established". Per-strategy results are descriptive. The first four models are the Experiment 3 models and must reproduce its numbers exactly.
This is the fourth variant tried on this research question; any result is reported with that count. The 2026 holdout remains unscored.

## Appendix A: algorithm-version comparison (registered before it was run)
Purpose: show that the ML layer can compare deterministic-layer versions on one protocol. Version A = Phase A strict B0 trades of the previous algorithm
(`results/ml_core/exp2_6c6e182c/dataset.csv`, rows with `is_b0`, resolved WIN/LOSS only, entries before 2026-01-01, feature set tier2-agnostic-v1 minus the unavailable strat dummies kept as is).
Version B = final algorithm export (Experiment 3). Same protocol: yearly walk-forward 2023-2025, the four default models, top-k by rank, random-selection control, same criteria with alpha 0.05 / 4.
The comparison is descriptive: the two versions differ in trades, rules and sample, so win-rate lifts are compared side by side, never subtracted into a claim about the algorithms.
Code: `scripts/run_ml_phase_a_b0.py`.
