# Experiment 1 final report (DIT15 meta-labeling, v1)

Descriptive reporting of the frozen Experiment 1 outputs. Nothing was retrained, retuned or re-selected; the 2026 holdout was excluded from every step and is not scored here. Costs are round-trip percentages of traded value (gross, 0.10, 0.20, 0.30); the single T1 take set (made at 0.20%) is evaluated at every cost level.

## Scope and provenance

- Dataset: 4552 labeled rows, 781 holdout rows excluded, 3771 development rows; pooled out-of-fold test stream (2023H1-2025H2): primary 2509 rows, strict-HTF sensitivity 2386 rows (the 196 flagged development rows removed).
- Phase A measured code hash `e5e09db7` (registry constant `cd73bf8d`, documented, unchanged). Seed 42; scikit-learn 1.4.0, xgboost 2.0.3.
- Determinism (second identical run): {'oof_predictions_and_takes': True, 'metrics_selections_champion': True, 'b2_draws': True}. Shuffled-label check: logreg AUC 0.475 (band 0.474-0.526), random_forest AUC 0.490 (band 0.474-0.526), hist_gb AUC 0.495 (band 0.474-0.526), xgboost AUC 0.499 (band 0.474-0.526).
- Champion (preregistered rule: at least 100 resolved takes at 0.20%, then expectancy, total R, drawdown, PF): primary **None**, strict sensitivity **hist_gb**.
- Inputs (SHA-256 verified against `experiment_1/manifest.json`): `results/nogit-145d6302/phase_b/experiment_1/primary/oof_predictions.csv` 27f39136339f; `results/nogit-145d6302/phase_b/experiment_1/strict_htf/oof_predictions.csv` 7a9f2e9f7339


# Primary dataset

## Pooled 2023-2025 out-of-fold results

**rt0.20**

| arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd | ambiguous |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 163 | 128 | 0.065 | 0.320 | -0.392 | 0.579 | -50.196 | 54.825 | 35 |
| B1 | 2509 | 2122 | 1.000 | 0.323 | -0.392 | 0.578 | -831.835 | 834.505 | 387 |
| ML:logreg | 23 | 20 | 0.009 | 0.350 | -0.112 | 0.851 | -2.239 | 10.361 | 3 |
| ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 | 0 |
| ML:hist_gb | 108 | 92 | 0.043 | 0.250 | -0.479 | 0.476 | -44.042 | 49.862 | 16 |
| ML:xgboost | 10 | 10 | 0.004 | 0.300 | -0.295 | 0.650 | -2.955 | 7.242 | 0 |

**gross**

| arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd | ambiguous |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 163 | 128 | 0.065 | 0.320 | -0.065 | 0.908 | -8.304 | 30.304 | 35 |
| B1 | 2509 | 2122 | 1.000 | 0.323 | -0.029 | 0.957 | -61.533 | 112.183 | 387 |
| ML:logreg | 23 | 20 | 0.009 | 0.350 | 0.050 | 1.077 | 1.000 | 9.000 | 3 |
| ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 | 0 |
| ML:hist_gb | 108 | 92 | 0.043 | 0.250 | -0.239 | 0.676 | -22.021 | 32.471 | 16 |
| ML:xgboost | 10 | 10 | 0.004 | 0.300 | -0.107 | 0.849 | -1.065 | 6.065 | 0 |

Ambiguity bounds on total R at 0.20% (all taken AMBIGUOUS trades lost / won, net of cost): B0 -100.4 .. 4.6; B1 -1387.7 .. -226.7; ML:logreg -5.8 .. 3.2; ML:random_forest 0.0 .. 0.0; ML:hist_gb -64.9 .. -16.9; ML:xgboost -3.0 .. -3.0

## Month-block bootstrap (paired; ML minus baseline, 0.20% round trip)

2000 draws of 36 entry-month blocks with replacement, seed 42; intervals are percentile 2.5-97.5; `share+` is the share of draws with a positive difference; `valid` is the number of draws where both sides are defined (fewer than 20 valid draws gives no interval).

*ML minus B0*

| family | metric | ml | baseline | difference | interval | share+ | valid |
|---|---|---|---|---|---|---|---|
| logreg | expectancy | -0.112 | -0.392 | 0.280 | [-0.468, +0.913] | 0.806 | 1999 |
| logreg | win_rate | 0.350 | 0.320 | 0.030 | [-0.225, +0.240] | 0.625 | 1999 |
| logreg | profit_factor | 0.851 | 0.579 | 0.272 | [-0.430, +1.360] | 0.778 | 1999 |
| logreg | total_r | -2.239 | -50.196 | 47.957 | [+14.290, +85.121] | 0.997 | 2000 |
| logreg | max_dd | 10.361 | 54.825 | -44.464 | [-80.679, -17.046] | 0.001 | 2000 |
| random_forest | expectancy | n/a | -0.392 | n/a | n/a | n/a | 0 |
| random_forest | win_rate | n/a | 0.320 | n/a | n/a | n/a | 0 |
| random_forest | profit_factor | n/a | 0.579 | n/a | n/a | n/a | 0 |
| random_forest | total_r | 0.000 | -50.196 | 50.196 | [+16.511, +86.274] | 1.000 | 2000 |
| random_forest | max_dd | 0.000 | 54.825 | -54.825 | [-89.164, -24.154] | 0.000 | 2000 |
| hist_gb | expectancy | -0.479 | -0.392 | -0.087 | [-0.410, +0.272] | 0.317 | 2000 |
| hist_gb | win_rate | 0.250 | 0.320 | -0.070 | [-0.176, +0.048] | 0.117 | 2000 |
| hist_gb | profit_factor | 0.476 | 0.579 | -0.103 | [-0.386, +0.216] | 0.255 | 2000 |
| hist_gb | total_r | -44.042 | -50.196 | 6.154 | [-29.495, +43.695] | 0.617 | 2000 |
| hist_gb | max_dd | 49.862 | 54.825 | -4.963 | [-41.715, +25.756] | 0.361 | 2000 |
| xgboost | expectancy | -0.295 | -0.392 | 0.097 | [-0.707, +2.024] | 0.627 | 1968 |
| xgboost | win_rate | 0.300 | 0.320 | -0.020 | [-0.282, +0.620] | 0.467 | 1968 |
| xgboost | profit_factor | 0.650 | 0.579 | 0.071 | [-0.509, +2.418] | 0.587 | 1907 |
| xgboost | total_r | -2.955 | -50.196 | 47.241 | [+17.164, +79.466] | 1.000 | 2000 |
| xgboost | max_dd | 7.242 | 54.825 | -47.582 | [-80.949, -20.742] | 0.000 | 2000 |

*ML minus B1*

| family | metric | ml | baseline | difference | interval | share+ | valid |
|---|---|---|---|---|---|---|---|
| logreg | expectancy | -0.112 | -0.392 | 0.280 | [-0.408, +0.895] | 0.817 | 1999 |
| logreg | win_rate | 0.350 | 0.323 | 0.027 | [-0.207, +0.231] | 0.615 | 1999 |
| logreg | profit_factor | 0.851 | 0.578 | 0.274 | [-0.366, +1.380] | 0.790 | 1999 |
| logreg | total_r | -2.239 | -831.835 | 829.596 | [+634.349, +1044.572] | 1.000 | 2000 |
| logreg | max_dd | 10.361 | 834.505 | -824.144 | [-1041.585, -633.410] | 0.000 | 2000 |
| random_forest | expectancy | n/a | -0.392 | n/a | n/a | n/a | 0 |
| random_forest | win_rate | n/a | 0.323 | n/a | n/a | n/a | 0 |
| random_forest | profit_factor | n/a | 0.578 | n/a | n/a | n/a | 0 |
| random_forest | total_r | 0.000 | -831.835 | 831.835 | [+638.405, +1046.346] | 1.000 | 2000 |
| random_forest | max_dd | 0.000 | 834.505 | -834.505 | [-1049.519, -641.628] | 0.000 | 2000 |
| hist_gb | expectancy | -0.479 | -0.392 | -0.087 | [-0.340, +0.215] | 0.277 | 2000 |
| hist_gb | win_rate | 0.250 | 0.323 | -0.073 | [-0.163, +0.031] | 0.083 | 2000 |
| hist_gb | profit_factor | 0.476 | 0.578 | -0.102 | [-0.301, +0.202] | 0.220 | 2000 |
| hist_gb | total_r | -44.042 | -831.835 | 787.792 | [+607.341, +987.702] | 1.000 | 2000 |
| hist_gb | max_dd | 49.862 | 834.505 | -784.643 | [-986.924, -605.333] | 0.000 | 2000 |
| xgboost | expectancy | -0.295 | -0.392 | 0.097 | [-0.805, +2.175] | 0.591 | 1968 |
| xgboost | win_rate | 0.300 | 0.323 | -0.023 | [-0.314, +0.663] | 0.452 | 1968 |
| xgboost | profit_factor | 0.650 | 0.578 | 0.072 | [-0.555, +2.483] | 0.565 | 1907 |
| xgboost | total_r | -2.955 | -831.835 | 828.880 | [+636.507, +1039.571] | 1.000 | 2000 |
| xgboost | max_dd | 7.242 | 834.505 | -827.262 | [-1040.318, -637.852] | 0.000 | 2000 |

## Capital-constrained view (Rs 1,00,000, no leverage; Phase A `capital_constrained`) and concurrency

Peak open positions / peak deployed notional are for all taken signals with no capital limit (uncapped) and after the capital rule (capped).

| arm | n_taken_uncapped | n_taken_capped | uncapped_peak_open | uncapped_peak_deployed | capped_peak_open | capped_peak_deployed | n_resolved | expectancy | profit_factor | total_r | max_dd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 163 | 155 | 3 | 290,768 | 1 | 99,995 | 123 | -0.380 | 0.591 | -46.731 | 50.724 |
| B1 | 2509 | 1384 | 7 | 662,877 | 2 | 100,000 | 1146 | -0.376 | 0.592 | -431.280 | 436.538 |
| ML:logreg | 23 | 22 | 2 | 173,138 | 1 | 99,784 | 19 | -0.214 | 0.730 | -4.075 | 10.361 |
| ML:random_forest | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | 0.000 | 0.000 |
| ML:hist_gb | 108 | 103 | 2 | 194,680 | 1 | 99,990 | 88 | -0.446 | 0.505 | -39.257 | 45.077 |
| ML:xgboost | 10 | 9 | 2 | 197,171 | 1 | 99,502 | 9 | -0.190 | 0.763 | -1.709 | 5.997 |

## Per-year results (0.20% round trip)

| year | arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd |
|---|---|---|---|---|---|---|---|---|---|
| 2023 | B0 | 48 | 37 | 0.060 | 0.459 | 0.016 | 1.021 | 0.580 | 5.705 |
| 2023 | B1 | 800 | 692 | 1.000 | 0.334 | -0.368 | 0.599 | -254.757 | 257.774 |
| 2023 | ML:logreg | 1 | 1 | 0.001 | 1.000 | 1.825 | n/a | 1.825 | 0.000 |
| 2023 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2023 | ML:hist_gb | 24 | 23 | 0.030 | 0.348 | -0.263 | 0.692 | -6.046 | 8.181 |
| 2023 | ML:xgboost | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2024 | B0 | 68 | 53 | 0.082 | 0.283 | -0.495 | 0.499 | -26.224 | 30.759 |
| 2024 | B1 | 827 | 696 | 1.000 | 0.322 | -0.377 | 0.588 | -262.422 | 281.108 |
| 2024 | ML:logreg | 20 | 17 | 0.024 | 0.294 | -0.282 | 0.656 | -4.799 | 9.224 |
| 2024 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2024 | ML:hist_gb | 50 | 43 | 0.060 | 0.209 | -0.594 | 0.380 | -25.552 | 25.914 |
| 2024 | ML:xgboost | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2025 | B0 | 47 | 38 | 0.053 | 0.237 | -0.646 | 0.380 | -24.552 | 24.552 |
| 2025 | B1 | 882 | 734 | 1.000 | 0.315 | -0.429 | 0.549 | -314.656 | 316.311 |
| 2025 | ML:logreg | 2 | 2 | 0.002 | 0.500 | 0.367 | 1.646 | 0.735 | 1.137 |
| 2025 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2025 | ML:hist_gb | 34 | 26 | 0.039 | 0.231 | -0.479 | 0.464 | -12.445 | 18.264 |
| 2025 | ML:xgboost | 10 | 10 | 0.011 | 0.300 | -0.295 | 0.650 | -2.955 | 7.242 |

Years in which ML net expectancy exceeds B0 (undefined counts as not better): logreg 3/3, random_forest 0/3, hist_gb 1/3, xgboost 1/3.
Years in which the model has at least 30 resolved takes (a year with fewer is not a meaningful comparison): logreg 0/3, random_forest 0/3, hist_gb 1/3, xgboost 0/3.


# Strict HTF-PIT sensitivity (240 flagged rows removed)

## Pooled 2023-2025 out-of-fold results

**rt0.20**

| arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd | ambiguous |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 135 | 105 | 0.057 | 0.324 | -0.370 | 0.598 | -38.877 | 48.698 | 30 |
| B1 | 2386 | 2019 | 1.000 | 0.321 | -0.401 | 0.571 | -808.738 | 811.407 | 367 |
| ML:logreg | 23 | 19 | 0.010 | 0.316 | -0.218 | 0.726 | -4.142 | 11.499 | 4 |
| ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 | 0 |
| ML:hist_gb | 117 | 101 | 0.049 | 0.287 | -0.375 | 0.572 | -37.895 | 42.283 | 16 |
| ML:xgboost | 7 | 7 | 0.003 | 0.286 | -0.343 | 0.604 | -2.402 | 4.869 | 0 |

**gross**

| arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd | ambiguous |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 135 | 105 | 0.057 | 0.324 | -0.044 | 0.937 | -4.580 | 26.580 | 30 |
| B1 | 2386 | 2019 | 1.000 | 0.321 | -0.035 | 0.948 | -70.809 | 116.933 | 367 |
| ML:logreg | 23 | 19 | 0.010 | 0.316 | -0.053 | 0.923 | -1.000 | 10.000 | 4 |
| ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 | 0 |
| ML:hist_gb | 117 | 101 | 0.049 | 0.287 | -0.129 | 0.817 | -13.021 | 26.471 | 16 |
| ML:xgboost | 7 | 7 | 0.003 | 0.286 | -0.152 | 0.790 | -1.065 | 4.065 | 0 |

Ambiguity bounds on total R at 0.20% (all taken AMBIGUOUS trades lost / won, net of cost): B0 -81.2 .. 8.8; B1 -1336.2 .. -235.2; ML:logreg -8.9 .. 3.1; ML:random_forest 0.0 .. 0.0; ML:hist_gb -58.5 .. -10.5; ML:xgboost -2.4 .. -2.4

## Month-block bootstrap (paired; ML minus baseline, 0.20% round trip)

2000 draws of 36 entry-month blocks with replacement, seed 42; intervals are percentile 2.5-97.5; `share+` is the share of draws with a positive difference; `valid` is the number of draws where both sides are defined (fewer than 20 valid draws gives no interval).

*ML minus B0*

| family | metric | ml | baseline | difference | interval | share+ | valid |
|---|---|---|---|---|---|---|---|
| logreg | expectancy | -0.218 | -0.370 | 0.152 | [-0.457, +0.835] | 0.704 | 1999 |
| logreg | win_rate | 0.316 | 0.324 | -0.008 | [-0.215, +0.217] | 0.475 | 1999 |
| logreg | profit_factor | 0.726 | 0.598 | 0.128 | [-0.451, +1.188] | 0.663 | 1999 |
| logreg | total_r | -4.142 | -38.877 | 34.735 | [+4.238, +67.371] | 0.987 | 2000 |
| logreg | max_dd | 11.499 | 48.698 | -37.199 | [-65.400, -10.350] | 0.001 | 2000 |
| random_forest | expectancy | n/a | -0.370 | n/a | n/a | n/a | 0 |
| random_forest | win_rate | n/a | 0.324 | n/a | n/a | n/a | 0 |
| random_forest | profit_factor | n/a | 0.598 | n/a | n/a | n/a | 0 |
| random_forest | total_r | 0.000 | -38.877 | 38.877 | [+9.104, +71.855] | 0.998 | 2000 |
| random_forest | max_dd | 0.000 | 48.698 | -48.698 | [-74.861, -18.002] | 0.000 | 2000 |
| hist_gb | expectancy | -0.375 | -0.370 | -0.005 | [-0.324, +0.347] | 0.489 | 2000 |
| hist_gb | win_rate | 0.287 | 0.324 | -0.037 | [-0.141, +0.078] | 0.253 | 2000 |
| hist_gb | profit_factor | 0.572 | 0.598 | -0.027 | [-0.330, +0.289] | 0.422 | 2000 |
| hist_gb | total_r | -37.895 | -38.877 | 0.982 | [-30.026, +34.984] | 0.511 | 2000 |
| hist_gb | max_dd | 42.283 | 48.698 | -6.414 | [-32.920, +25.029] | 0.457 | 2000 |
| xgboost | expectancy | -0.343 | -0.370 | 0.027 | [-0.919, +0.712] | 0.576 | 1907 |
| xgboost | win_rate | 0.286 | 0.324 | -0.038 | [-0.347, +0.181] | 0.408 | 1907 |
| xgboost | profit_factor | 0.604 | 0.598 | 0.006 | [-0.665, +0.940] | 0.551 | 1907 |
| xgboost | total_r | -2.402 | -38.877 | 36.475 | [+8.221, +66.806] | 0.998 | 2000 |
| xgboost | max_dd | 4.869 | 48.698 | -43.828 | [-68.379, -15.512] | 0.000 | 2000 |

*ML minus B1*

| family | metric | ml | baseline | difference | interval | share+ | valid |
|---|---|---|---|---|---|---|---|
| logreg | expectancy | -0.218 | -0.401 | 0.183 | [-0.366, +0.818] | 0.741 | 1999 |
| logreg | win_rate | 0.316 | 0.321 | -0.005 | [-0.193, +0.213] | 0.471 | 1999 |
| logreg | profit_factor | 0.726 | 0.571 | 0.155 | [-0.335, +1.249] | 0.694 | 1999 |
| logreg | total_r | -4.142 | -808.738 | 804.596 | [+617.689, +1010.574] | 1.000 | 2000 |
| logreg | max_dd | 11.499 | 811.407 | -799.908 | [-1010.816, -619.740] | 0.000 | 2000 |
| random_forest | expectancy | n/a | -0.401 | n/a | n/a | n/a | 0 |
| random_forest | win_rate | n/a | 0.321 | n/a | n/a | n/a | 0 |
| random_forest | profit_factor | n/a | 0.571 | n/a | n/a | n/a | 0 |
| random_forest | total_r | 0.000 | -808.738 | 808.738 | [+620.821, +1016.425] | 1.000 | 2000 |
| random_forest | max_dd | 0.000 | 811.407 | -811.407 | [-1020.419, -626.229] | 0.000 | 2000 |
| hist_gb | expectancy | -0.375 | -0.401 | 0.025 | [-0.176, +0.269] | 0.569 | 2000 |
| hist_gb | win_rate | 0.287 | 0.321 | -0.034 | [-0.107, +0.049] | 0.208 | 2000 |
| hist_gb | profit_factor | 0.572 | 0.571 | 0.001 | [-0.175, +0.255] | 0.488 | 2000 |
| hist_gb | total_r | -37.895 | -808.738 | 770.842 | [+596.539, +960.783] | 1.000 | 2000 |
| hist_gb | max_dd | 42.283 | 811.407 | -769.124 | [-960.374, -596.203] | 0.000 | 2000 |
| xgboost | expectancy | -0.343 | -0.401 | 0.057 | [-0.820, +0.720] | 0.590 | 1907 |
| xgboost | win_rate | 0.286 | 0.321 | -0.035 | [-0.325, +0.178] | 0.428 | 1907 |
| xgboost | profit_factor | 0.604 | 0.571 | 0.034 | [-0.576, +0.959] | 0.568 | 1907 |
| xgboost | total_r | -2.402 | -808.738 | 806.336 | [+621.458, +1009.445] | 1.000 | 2000 |
| xgboost | max_dd | 4.869 | 811.407 | -806.538 | [-1011.095, -623.411] | 0.000 | 2000 |

## Capital-constrained view (Rs 1,00,000, no leverage; Phase A `capital_constrained`) and concurrency

Peak open positions / peak deployed notional are for all taken signals with no capital limit (uncapped) and after the capital rule (capped).

| arm | n_taken_uncapped | n_taken_capped | uncapped_peak_open | uncapped_peak_deployed | capped_peak_open | capped_peak_deployed | n_resolved | expectancy | profit_factor | total_r | max_dd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | 135 | 130 | 3 | 290,768 | 1 | 99,995 | 102 | -0.371 | 0.598 | -37.853 | 48.019 |
| B1 | 2386 | 1334 | 7 | 662,877 | 2 | 100,000 | 1100 | -0.386 | 0.584 | -424.758 | 430.016 |
| ML:logreg | 23 | 22 | 2 | 173,138 | 1 | 99,784 | 18 | -0.332 | 0.604 | -5.977 | 11.499 |
| ML:random_forest | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | 0.000 | 0.000 |
| ML:hist_gb | 117 | 112 | 2 | 197,171 | 1 | 99,990 | 97 | -0.371 | 0.577 | -35.956 | 39.575 |
| ML:xgboost | 7 | 6 | 2 | 197,171 | 1 | 99,502 | 6 | -0.193 | 0.760 | -1.157 | 3.624 |

## Per-year results (0.20% round trip)

| year | arm | n_taken | n_resolved | take_rate | win_rate | expectancy | profit_factor | total_r | max_dd |
|---|---|---|---|---|---|---|---|---|---|
| 2023 | B0 | 37 | 28 | 0.049 | 0.500 | 0.164 | 1.240 | 4.581 | 5.195 |
| 2023 | B1 | 754 | 651 | 1.000 | 0.332 | -0.374 | 0.594 | -243.656 | 246.674 |
| 2023 | ML:logreg | 2 | 1 | 0.003 | 1.000 | 1.825 | n/a | 1.825 | 0.000 |
| 2023 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2023 | ML:hist_gb | 33 | 28 | 0.044 | 0.393 | -0.131 | 0.837 | -3.669 | 6.236 |
| 2023 | ML:xgboost | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2024 | B0 | 57 | 44 | 0.072 | 0.295 | -0.439 | 0.540 | -19.316 | 26.315 |
| 2024 | B1 | 788 | 667 | 1.000 | 0.319 | -0.385 | 0.581 | -256.703 | 276.653 |
| 2024 | ML:logreg | 19 | 16 | 0.024 | 0.250 | -0.419 | 0.520 | -6.701 | 10.362 |
| 2024 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2024 | ML:hist_gb | 46 | 43 | 0.058 | 0.233 | -0.518 | 0.440 | -22.268 | 24.004 |
| 2024 | ML:xgboost | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2025 | B0 | 41 | 33 | 0.049 | 0.212 | -0.732 | 0.325 | -24.142 | 24.142 |
| 2025 | B1 | 844 | 701 | 1.000 | 0.312 | -0.440 | 0.540 | -308.378 | 310.034 |
| 2025 | ML:logreg | 2 | 2 | 0.002 | 0.500 | 0.367 | 1.646 | 0.735 | 1.137 |
| 2025 | ML:random_forest | 0 | 0 | 0.000 | n/a | n/a | n/a | 0.000 | 0.000 |
| 2025 | ML:hist_gb | 38 | 30 | 0.045 | 0.267 | -0.399 | 0.544 | -11.959 | 13.779 |
| 2025 | ML:xgboost | 7 | 7 | 0.008 | 0.286 | -0.343 | 0.604 | -2.402 | 4.869 |

Years in which ML net expectancy exceeds B0 (undefined counts as not better): logreg 3/3, random_forest 0/3, hist_gb 1/3, xgboost 1/3.
Years in which the model has at least 30 resolved takes (a year with fewer is not a meaningful comparison): logreg 0/3, random_forest 0/3, hist_gb 2/3, xgboost 0/3.


## Reading the results

- No model reaches the preregistered minimum of 100 resolved takes (resolved takes: logreg 20, random_forest 0, hist_gb 92, xgboost 10), so no champion exists in the primary run. The T1 rule needs roughly p > 0.45 at the average cost; the models' probabilities rarely reach that level.
- The rule-only baselines are negative after costs on this 2023-2025 stream (B0 and B1 above); ML-minus-baseline intervals that include zero, or have few valid draws, carry no evidence of improvement.
- Total R and drawdown differences against B0 / B1 mostly reflect how few trades the models take (0-4% of rows), not selection skill: skipping most of a negative-expectancy pool raises total R mechanically. The like-for-like control is the random filter with the same take counts (B2, 1,000 draws): ML expectancy sits at the 79th percentile (logreg), 30th percentile (hist_gb), 64th percentile (xgboost) of random filters (random-filter mean expectancy about -0.41).
- Samples of a few dozen trades give wide intervals; differences are descriptive and are not used to alter any frozen decision.