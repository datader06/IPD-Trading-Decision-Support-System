# EXPERIMENT_1_PREREGISTRATION.md: DIT15 meta-labeling, Experiment 1 (FINAL, FROZEN)

Status: final. Written before any model is trained. No section is open for approval or later decision.
Scope: the first DIT15 meta-labeling experiment. The ML filter may only take or skip existing Phase A candidates.

## 1. Frozen data

| Item | Value |
|---|---|
| Phase A candidates | `results/nogit-145d6302/phase_a/pit/candidates.csv` (4,661 rows) |
| Phase A measured code hash | `e5e09db7` (`runinfo.code_hash()` of the current tree, equals `run_info.txt`) |
| Phase B folder | `results/nogit-145d6302/phase_b/tier1/` (`features.csv`, `labeled.csv`, `folds/`) |
| Primary dataset | 4,552 rows (`labeled.csv`) |
| Strict HTF sensitivity | the same rows minus exactly 240 (section 7) |
| 2026 holdout | 781 rows (`entry_time >= 2026-01-01`), never used (section 8) |

SHA-256 values are verified against `tier1/manifest.json` and `tier1/folds/manifest.json` before any run (section 12).

**Known hash discrepancy (documented, not changed).** The registry constant `SOURCE_CODE_HASH` is `cd73bf8d`, and the Phase B
manifest echoes that constant. The measured Phase A hash of the data actually in use is `e5e09db7`. The hash fingerprints the whole
file set (`config.py`, `src/*.py`, `scripts/run_phase_a.py`, `legacy/handoff/handoff/code/*.py`), so it changed when that file set
changed. The current candidates reproduce the frozen DIT15 B0 baseline exactly (318 trades; 91 / 167 / 60 W / L / ambiguous;
+0.046 R) and the 4,575-row pool counts. The registry and `SOURCE_CODE_HASH` are not modified.

**Dataset-selection limitation (retained unchanged).** Phase A flags `ca_excluded` in `candidates.py:_replay_all`, using the trade's
`exit_time` (a future event). 5 rows were removed this way, 0.11% of the 4,575-row Phase B pool (2 in 2021-2025, 3 in 2026;
4 AMBIGUOUS and 1 WIN). The rows stay excluded, and `ca_excluded` is not a model feature (it is in `FORBIDDEN`).

## 2. Models

Four models, all with native probabilities, fixed seed `42`, `n_jobs=1`, no class weights, no resampling.

| Model | Preprocessing | Fixed grid |
|---|---|---|
| Logistic Regression (baseline) | `StandardScaler`, fit on training rows only | L2, lbfgs, C in {0.01, 0.1, 1.0} |
| Random Forest | none | 500 trees, min_samples_leaf 30, max_depth in {3, 6} |
| HistGradientBoosting | none | max_depth 3, max_leaf_nodes 7, min_samples_leaf 50, learning_rate 0.05, l2_regularization 1.0, `early_stopping=False`, max_iter in {100, 200} |
| XGBoost | none | `tree_method='hist'`, learning_rate 0.05, subsample 1.0, max_depth in {2, 3}, up to 500 rounds with early stopping (30 rounds) on the validation rows |

- The grids are final. They cannot be expanded or changed after any result is seen.
- Within a fold, the configuration of each model is the one with the lowest log-loss on the validation rows, after fitting on the fit rows only.
- Features: the 18 columns of `R.MODEL_COLUMNS`, unchanged.
- The random filter B2 is a control only. It is never a candidate model.

## 3. Probabilities

Native model probabilities only. No Platt or isotonic calibration in Experiment 1. Calibration is a possible future, separately versioned sensitivity.

## 4. Folds and training protocol

- Reuse `S.prepare`, `S.build_folds` and `S.check_folds` unchanged. Every check must pass.
- The rebuilt fit, validation and test roles must equal the frozen `fold_assignments.csv`. The pool is the `f.idx["pool"]` set from `build_folds`.
- Embargo (5 trading days), purge (exit time), sibling and holdout rules are preserved as implemented.
- Per fold and per model, in this order:
  1. fit on the resolved fit rows, choose the configuration on the resolved validation rows only;
  2. refit the chosen configuration on the resolved pool rows;
  3. predict probabilities for all test rows.
- Hyperparameters use validation rows only. Test labels are never used for any choice.
- Test windows: 2023H1 through 2025H2.

## 5. Threshold

**T1 (primary).** Take a candidate if `p*W - (1-p)*L - c > 0`.
- `W = 2` exactly. The observed mean WIN R is not used.
- `L` is the mean absolute R (`r_gross`) of LOSS rows in the current training stage (fit rows while tuning, pool rows for the final refit).
- `c` is the row's `cost_in_r_rt0.20`.
- T1 has no tuned parameter.

**T2 (secondary only).**
- Candidate thresholds: 0.15 to 0.60 in steps of 0.01, plus the T1 break-even.
- Objective: net expectancy at 0.20% on resolved validation rows taken.
- Constraint: minimum takes = max(30, 10% of the resolved validation rows).
- Tie-breaking, in order: higher expectancy, more trades taken, lower threshold.
- T2 is reported only. It cannot select the primary champion.

## 6. Evaluation

- **Take set:** one take set per model and fold, made with T1 (0.20% costs).
- **Cost scenarios:** the same take set is evaluated gross, and at 0.10%, 0.20% and 0.30% round trip. There is no separate threshold per cost.
- **Test rows:** predict ALL test rows, including AMBIGUOUS and CENSORED. Labels are joined only at evaluation.
- **Arms:** B0 (`is_b0` rows), B1 (relaxed pool, take all), ML (pool rows taken), ML-on-B0, and B2 (random filter: per fold, the same number of rows as ML took, uniform, 1,000 draws, fixed seed).
- **Metrics:** trade count; win rate; expectancy; profit factor; total R; max drawdown (ordered by exit time); the six outcome counts; best and worst bounds for AMBIGUOUS rows. Resolved-only results and the bounds are both reported.
- **ML metrics:** ROC-AUC, PR-AUC, precision, recall, predicted-positive count, Brier score against the base-rate predictor, reliability bins. These are supporting metrics only.
- Per fold and on the pooled 2023-2025 out-of-fold stream.

## 7. Strict HTF sensitivity

- **Primary result = all 4,552 rows.**
- **Sensitivity = the same dataset minus exactly the 240 rows** whose HTF `leg_end` date is the trading day just before the entry date (NIFTY calendar).
- Phase A is not regenerated. The frozen fold boundaries are preserved by removing those rows from the frozen assignments.
- The complete experiment, including tuning, is re-run on the strict subset.
- A fold rebuild on the subset is allowed only as a consistency check.
- The strict result is a sensitivity report and cannot replace the primary result.

## 8. Holdout

The 781 rows with `entry_time >= 2026-01-01` are excluded from training, validation, tuning, threshold selection, model selection, calibration and champion selection. They are not scored in Experiment 1.

## 9. Champion selection

The champion model is selected only on the pooled 2023-2025 out-of-fold stream, using T1 take sets at 0.20%, in this order:
1. highest net expectancy at 0.20%, subject to a minimum of 100 resolved taken trades;
2. higher total R;
3. lower max drawdown;
4. higher profit factor.

AUC, Brier and calibration are supporting metrics and do not select. T2 and the 2026 holdout never select.

## 10. Leakage and determinism requirements

All of the following are required and must pass before results are reported:
1. SHA-256 verification of `labeled.csv`, `features.csv` and the fold files against the manifests.
2. Holdout exclusion: no 2026 row in any fit, validation, pool or test index.
3. Test-label independence: changing test labels leaves hyperparameters, thresholds and probabilities identical.
4. Forbidden-feature guard: `R.assert_no_forbidden`, and the matrix columns equal `R.MODEL_COLUMNS` in order.
5. Fit-only preprocessing: scaler statistics come from training rows only.
6. Deterministic ordering and seeds: rows sorted by `S.prepare`, fixed seed, `n_jobs=1`.
7. Fold validation: `S.check_folds` passes and the roles equal the frozen assignments.
8. Shuffled-label sanity test: with fit labels permuted, out-of-fold AUC lies inside a 95% band around 0.5.
9. Strict-subset verification: exactly 240 rows flagged and removed, none left, and fold boundaries unchanged.
10. Minimum-sample checks from `PHASE_B_PLAN.md` section 14 pass for every fold.
11. Second-run determinism: a second run produces byte-identical outputs.

## 11. Dependencies

```
scikit-learn==1.4.0
xgboost==2.0.3
```

New code lives only in `src/ml/` and `scripts/run_phase_b_*.py`, so the Phase A code hash is unaffected.

## 12. Final status

- Phase A logic cannot be changed for this experiment.
- ML results cannot be used to modify this preregistration.
- Any future change requires a separately versioned experiment.

All Experiment 1 decisions are frozen before the first training run. No post-hoc model, feature, threshold, cost, calibration, or holdout tuning is permitted.
