# PHASE_B_LABELS_REPORT.md: trade outcome labels (7 Oct 2026)

Step 2 of Phase B. No model, walk-forward validation or feature change.

## Definition (frozen)
Decision time = start of the 15m entry bar. Label **1** = +2R target reached before the -1R stop (Phase A outcome WIN). Label **0** =
-1R stop reached before the +2R target (LOSS). AMBIGUOUS, OPEN, CENSORED and NOFILL have **no label** and are never training labels;
they stay in the file with an explicit `label_status`. The label is the Phase A replay outcome carried over, not a new rule:
`outcome`, `exit_reason`, `r_gross`, `fill_*` and `exit_*` are preserved unchanged. As an independent check, every row was
replayed again with the unchanged `src/replay.py`, through the same call path as Phase A (15m replay, then the cached 1-minute
drill-down for MINUTE_NOT_CACHED bars), and compared with the stored Phase A fields.
Labels use data after the decision time by construction; features never do (checked in the feature tests).

## Outputs
Folder `results/nogit-145d6302/phase_b/labels/`: `labeled.csv`, `manifest.json`, `report.txt`.
Rebuild: `python scripts/run_phase_b_labels.py` (offline). A second run gave a byte-identical `labeled.csv`.

`labeled.csv` = all 4,552 Tier-1 rows, same order, same 18 model columns (bit-identical to `features.csv`), plus:

| Column | Meaning |
|---|---|
| `label` | 1 (WIN), 0 (LOSS), empty otherwise |
| `label_status` | WIN / LOSS / AMBIGUOUS / CENSORED / OPEN / NOFILL |
| `is_training_label` | true only for WIN or LOSS |
| `phase_a_src_row` | row index of this candidate in `pit_refetch/candidates.csv` |
| `replay_check` | `match` if the fresh replay equals the stored Phase A fields |

These five columns are added to `registry.FORBIDDEN`, so none of them can enter a model matrix. This is the only change to
`registry.py`; the feature definitions are untouched. Traceability: `row_id` + `htf_key` + `ltf_key` identify the Phase A row
uniquely (checked).

## Counts

| Status | Rows | Label |
|---|---|---|
| WIN | 1,229 | 1 |
| LOSS | 2,653 | 0 |
| AMBIGUOUS | 669 | none |
| CENSORED | 1 | none |
| OPEN | 0 | none |
| NOFILL | 0 | none |
| **Total** | **4,552** | 3,882 training labels |

Label balance among resolved trades: **31.66% wins**.

| Year | Resolved | Wins | Win % |
|---|---|---|---|
| 2021 | 493 | 163 | 33.1 |
| 2022 | 642 | 187 | 29.1 |
| 2023 | 692 | 231 | 33.4 |
| 2024 | 696 | 224 | 32.2 |
| 2025 | 734 | 231 | 31.5 |
| 2026 | 625 | 193 | 30.9 |

B0 rows: 316 (256 resolved). Remaining AMBIGUOUS (669): target in fill bar 300, stop+target in fill bar 177, gap-fill opens beyond
the stop 172 (kept AMBIGUOUS by decision D4), intraday data gap 15, MINUTE_NOT_CACHED 4, stop+target in the same bar 1.
The single CENSORED row is a filled trade whose 90-day horizon extends past the end of the data.

## Comparison with Phase A (`pit_refetch`)

| Status | Phase A pool | Excluded at features | Dataset | Pool - excluded |
|---|---|---|---|---|
| WIN | 1,237 | 8 | 1,229 | 1,229 |
| LOSS | 2,666 | 13 | 2,653 | 2,653 |
| AMBIGUOUS | 671 | 2 | 669 | 669 |
| CENSORED | 1 | 0 | 1 | 1 |
| OPEN | 0 | 0 | 0 | 0 |
| NOFILL | 0 | 0 | 0 | 0 |

- Outcome equals the traced Phase A row: 4,552 of 4,552.
- Fresh replay vs stored Phase A fields: 4,552 of 4,552 match (outcome, reason, interval, fill and exit times and prices, R).
- The 23 rows excluded at the feature stage (20 warm-up, 3 corporate-action look-back) account for every difference between the
  Phase A pool counts and the dataset counts.

## Tests
`tests/test_phase_b_labels.py`, 15 tests, all pass. They cover:
- the outcome-to-label mapping and unknown outcomes rejected;
- label columns never model inputs;
- target before stop (demand and supply, label 1, R = +2);
- stop before target (demand and supply, label 0, R = -1);
- a gap through the stop (label 0, R = -2);
- same-bar stop+target ambiguity: no label without minute data, label 1 when 1-minute data shows the target first, and a true
  1-minute tie stays AMBIGUOUS;
- target in the fill bar and gap-fill beyond the stop: AMBIGUOUS, no label;
- CENSORED, OPEN, NOFILL (and an unfilled order with an incomplete horizon): no label;
- replay determinism;
- every row kept, Phase A fields preserved, `replay_check` detecting a changed outcome or R;
- the real dataset: all rows kept, features identical to `features.csv`, labels only for WIN/LOSS, traceability, count
  reconciliation, all `replay_check` = match;
- labels reproduce from the features file for sample tickers.

Full suite run: 55 passed (Phase A 25, features 15, labels 15).

## Notes
- No discrepancy and no blocker.
- OPEN and NOFILL are empty in this dataset; the code and tests handle them, so a future run that produces them will not mislabel.
- Labels are for the model target only. The AMBIGUOUS rows remain in the file and are reported by the evaluation step later.
