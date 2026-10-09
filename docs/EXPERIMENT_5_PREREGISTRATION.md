# EXPERIMENT_5_PREREGISTRATION.md: ML filter on the FINAL baseline v6, and rule-vs-model reference (written before the run)

Status: final for this run. Variant 5 of the ML study; Experiments 1-4 found no improvement. Written before any Experiment 5 model was fit on v6 data.

## Final baseline
`STATUS.md` section 19 (copy: `data/algo_v6/STATUS_final.md`): FINAL baseline v6 = v5 plus zone strength 2 on DIT15 only (WIT and MIT unchanged): 205 trades (DIT15 100 / WIT 70 / MIT 35), win rate 44.4%.
Verified: applying that rule (`legout_strength_score == 2` for DIT15) to `data/algo_v5/ml_dataset_baseline_v5.csv` reproduces the 205 trades of `data/algo_v6/v6_trades_min_strength_2_only_DIT15.csv` exactly.
The rule was chosen in-sample after about 90 filter/scope combinations (STATUS 18-19), so v6 win rates are optimistic.

## A. ML on the v6 pool
Same features, models, fixed hyperparameters, walk-forward by test year (2023, 2024, 2025), purge/embargo, top-k selection, random-selection control and criteria as `docs/EXPERIMENT_3_PREREGISTRATION.md`
(four default models, alpha 0.05 / 4 = 0.0125, lift >= 5 points, AUC > 0.55). Pool = development rows (entries before 2026) of the 205 v6 trades = 168 rows; test years have 38 / 45 / 34 rows.
`python scripts/run_ml_baseline_v5.py --pool=v6 --tag=exp5_v6`. With about 59 selected test trades the smallest detectable lift is near 20 points (power table in the output); the run is reported with that caveat.
The 2026 holdout (37 v6 trades) is not used.

## B. Rule versus model on the v5 pool (descriptive, no new model fitting)
Using the existing Experiment 3 out-of-fold predictions (v5 pool, test years 2023-2025): for DIT15 test trades report the win rate of (i) all, (ii) the hand-made strength-2 rule, (iii) each model's top-50% selection (ranked across all strategies).
This only compares the human rule with the models on the same rows. The rule was fitted on the same years, so it is NOT an out-of-sample result and must be labelled in-sample wherever shown.
Code: `scripts/rule_vs_model.py`.
