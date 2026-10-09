# EXPERIMENT_6_PREREGISTRATION.md: ML for P&L per year on the final baseline v6 (written before the run)

Status: final for this run. Variant 6 of the ML study. Written before any Experiment 6 model was fit. Experiments 1-5 asked "does ML raise the win rate?"; this one asks "does ML raise gross P&L per year?"
Data: the 205 trades of baseline v6 (`data/algo_v6/`; reproduced from `data/algo_v5/ml_dataset_baseline_v5.csv` by the strength-2 rule on DIT15). P&L = `label_rs` (gross rupees at about Rs 1,000 risk per trade) and `label_R` (gross R). Costs are excluded by decision.
Protocol: development rows only (entries before 2026), yearly expanding walk-forward, test years 2023, 2024, 2025 (117 trades), purge/embargo, features and seed as Experiment 3. The 2026 holdout is not used.
Code: `src/ml_core/pnl.py`, `scripts/run_ml_pnl.py`.

## Arms (all compared with "take every v6 trade")
A. **Expected-R filter.** Two regressors predict R: ridge (standardised, alpha 10) and hist_gb regressor (depth 2, 60 iterations, lr 0.05). Take a trade if predicted R > 0.
B. **ML sizing.** Two classifiers (logreg C = 0.3, hist_gb as before) give p. Risk multiplier m = clip(p / base, 0.5, 1.5), where base = the training-set win rate; every trade is still taken. P&L of a trade = m x its baseline P&L.
No other variant (thresholds, features, hyperparameters) is tried in this run.

## Metrics
Per test year and pooled: trades taken, total P&L (Rs and R), P&L per trade, and for sizing P&L per unit of risk (total P&L / sum of multipliers), so that "more risk" cannot masquerade as skill.
Controls (10,000 draws, seed 42, within each test year): for A, random selections of the same size; for B, the multipliers randomly permuted across that year's trades.

## What counts as improvement (decided now)
A model arm counts only if ALL hold: (1) A: mean R per taken trade at least 0.15 above the take-all mean, B: P&L per unit of risk at least 10% above take-all; (2) random-control p <= 0.025 (0.05 / 2 models per arm); (3) the pooled effect has the right sign in at least 2 of the 3 test years.
Anything else = "no P&L improvement established", including positive but non-significant results. With 117 test trades only large effects are detectable; this is stated with the results. The 2026 holdout stays unscored.
After the extended data (2015+) arrives, the same arms are re-run unchanged and reported as a separate, larger test.
