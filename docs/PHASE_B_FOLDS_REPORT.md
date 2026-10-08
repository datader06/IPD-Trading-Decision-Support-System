# PHASE_B_FOLDS_REPORT.md: walk-forward validation framework (7 Oct 2026)

Step 3 of Phase B. Folds and leakage checks only: no model fitting, no thresholds, no change to features or labels.
Code: `src/ml/splits.py`, `scripts/run_phase_b_folds.py`, `tests/test_phase_b_folds.py`.
Outputs: `results/nogit-145d6302/phase_b/folds/` (`folds.csv`, `fold_assignments.csv`, `manifest.json`, `report.txt`).
Rebuild: `python scripts/run_phase_b_folds.py` (exits with an error if any leakage check fails).

## Rules as implemented
- Rows come from `labeled.csv` (4,552). Model fitting and validation use WIN/LOSS rows only. AMBIGUOUS / CENSORED / OPEN / NOFILL are
  never fitted; they stay in test windows so the later evaluation can count them.
- Expanding walk-forward from 2021-01-01. Test windows are half-years by `entry_time`, `[start, end)`.
- Inner validation is the last 6 calendar months of the training window. Fit data ends at the validation boundary.
- **Embargo:** at each boundary (test start, and validation start) the 5 trading days before it (NIFTY trading calendar) are dropped
  from the earlier side.
- **Purge:** among rows entered before the embargo, any whose outcome (`exit_time`) is at or after the boundary is dropped.
- **Siblings:** rows of one HTF zone (ticker + `htf_key`) go to the side of the group's earliest entry; a later member that would land
  on the other side of the boundary is removed from that side.
- **Training pool** = what the final fold model is refit on after hyperparameters are chosen on validation = fit + validation +
  rows dropped only to keep the validation set clean (their outcomes still end before the test start).
- **Holdout:** rows with `entry_time` on or after 2026-01-01 (781 rows) are never a fit, validation or test row of any fold. A window
  that reaches into 2026 is rejected. The holdout is only counted, never inspected.

## Fold definitions

| Fold | Fit | Validation | Test | Test embargo starts |
|---|---|---|---|---|
| 2023H1 | 2021-01-01 .. 2022-07-01 | 2022-07-01 .. 2023-01-01 | 2023-01-01 .. 2023-07-01 | 2022-12-26 |
| 2023H2 | .. 2023-01-01 | 2023-01-01 .. 2023-07-01 | 2023-07-01 .. 2024-01-01 | 2023-06-23 |
| 2024H1 | .. 2023-07-01 | 2023-07-01 .. 2024-01-01 | 2024-01-01 .. 2024-07-01 | 2023-12-22 |
| 2024H2 | .. 2024-01-01 | 2024-01-01 .. 2024-07-01 | 2024-07-01 .. 2025-01-01 | 2024-06-24 |
| 2025H1 | .. 2024-07-01 | 2024-07-01 .. 2025-01-01 | 2025-01-01 .. 2025-07-01 | 2024-12-24 |
| 2025H2 | .. 2025-01-01 | 2025-01-01 .. 2025-07-01 | 2025-07-01 .. 2026-01-01 | 2025-06-24 |

Each fold's validation window is the previous fold's test window. That is normal for an expanding walk-forward, but it means
hyperparameters for fold k are chosen on data that was a test window for fold k-1.

## Row counts (resolved = WIN + LOSS)

| Fold | Fit (W/L) | Validation (W/L) | Pool (W/L) | Test rows | Test resolved (W/L) | Test AMB / CENS |
|---|---|---|---|---|---|---|
| 2023H1 | 808 (261/547) | 308 (84/224) | 1,123 (346/777) | 334 | 300 (100/200) | 34 / 0 |
| 2023H2 | 1,123 (346/777) | 275 (89/186) | 1,410 (439/971) | 466 | 392 (131/261) | 74 / 0 |
| 2024H1 | 1,410 (439/971) | 346 (117/229) | 1,781 (567/1,214) | 456 | 378 (121/257) | 78 / 0 |
| 2024H2 | 1,781 (567/1,214) | 372 (119/253) | 2,199 (700/1,499) | 371 | 318 (103/215) | 53 / 0 |
| 2025H1 | 2,199 (700/1,499) | 303 (95/208) | 2,508 (797/1,711) | 456 | 363 (108/255) | 93 / 0 |
| 2025H2 | 2,508 (797/1,711) | 361 (108/253) | 2,884 (913/1,971) | 426 | 371 (123/248) | 55 / 0 |

Test windows total 2,122 resolved trades (686 wins).

## Purge, embargo and sibling counts (resolved rows removed)

| Fold | Test embargo | Test purge | Test sibling | Validation embargo | Validation purge | Validation sibling | Unresolved rows excluded from fitting |
|---|---|---|---|---|---|---|---|
| 2023H1 | 12 | 0 | 0 | 7 | 0 | 0 | 127 |
| 2023H2 | 25 | 0 | 0 | 12 | 0 | 0 | 161 |
| 2024H1 | 46 | 0 | 0 | 25 | 0 | 0 | 235 |
| 2024H2 | 6 | 0 | 0 | 46 | 0 | 0 | 313 |
| 2025H1 | 15 | 0 | 0 | 6 | 0 | 0 | 366 |
| 2025H2 | 2 | 0 | 0 | 15 | 0 | 0 | 459 |

Purge and sibling removal never fire on the real data: almost every candidate exits within days (so the 5-day embargo already
covers any outcome that could reach a boundary) and only 6 candidate pairs share an HTF zone. Both rules are exercised by the
synthetic tests. No test row exits on or after 2026-01-01.

## Minimum sample rules (train >= 300 resolved, wins >= 180 = 10 x 18 features, test >= 100 resolved)
Every fold passes every rule, on both the fit set and the pool. Smallest values: fit 808 resolved / 261 wins; pool 1,123 / 346;
test 300 resolved. No fold fails.

## Leakage checks: 93 run, 0 failed; deterministic rebuild: yes
Per fold: roles are disjoint; only WIN/LOSS rows are ever fitted or validated; the latest training entry is before the embargo
start; the latest training outcome is before the test start (purge); the embargo spans exactly 5 trading days; purged rows really
cross the boundary; test rows lie inside the window; validation is the last 6 months; fit ends before the validation boundary with
embargo and purge; no HTF-zone group sits on both sides; pools expand. Across folds: windows are chronological and end by the
holdout start, and no holdout row appears in any role. The checks are tested to fail on deliberately corrupted folds (a test row in
training, an embargoed row, a purged row, a holdout row, an unresolved row).

## Tests: `tests/test_phase_b_folds.py`, 18 tests, all pass
Embargo counts trading days (including a holiday case) · exactly the 5 trading days before the test are dropped · purge at the
test boundary and at the validation boundary · chronological, disjoint roles · unresolved rows never fitted but kept in test windows ·
holdout never used and a window into 2026 rejected · a dev trade exiting in 2026 is reported · siblings stay on one side · minimum
rules flag small folds and equal the thresholds exactly · deterministic and independent of row order · five corruption tests · real
dataset timestamps obey every rule · fold files match a fresh construction. Full suite: 73 passed (the long
`tests/test_base_candles.py` golden run was not repeated this time).

## Notes and one decision for you
- A dev-window test row whose outcome ends in 2026 would count as a test row (holdout membership is by entry time). None exist
  today, and the count is reported per fold (`test_rows_exiting_in_holdout`), so a rebuild would show it.
- Nothing has been fitted. Fold files are fixed by the labeled dataset hash in the manifest; any change to labels or features
  means rebuilding them.
