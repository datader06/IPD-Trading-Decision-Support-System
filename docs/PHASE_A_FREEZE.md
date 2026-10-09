# PHASE_A_FREEZE.md: frozen Phase A baselines (DIT15, WIT, MIT)

Frozen 8 Oct 2026. These are the rule-only baselines every later comparison (including the Phase B ML filter) is measured against.
Strategy rules, zone logic, matching, sizing (Rs 1,000 risk, Rs 1,00,000 notional cap, no leverage), the 2:1 target and the
90-day replay horizon are unchanged from the pre-hardening engine. Do not change `src/candidates.py`, `src/candidates_mtf.py`,
`src/trend_pit.py`, `src/bars.py`, `src/htf_bars.py`, `src/replay.py` or `legacy/handoff/handoff/code/` without declaring a new baseline.

All numbers: entries from 2021-01-01 to 2026-10-01, 503-ticker universe (`universe_live.json` minus HFCL.NS), Kite data (split / bonus
adjusted), gross R unless stated. Resolved = WIN + LOSS; AMBIGUOUS trades are never converted into wins or losses.

## Frozen baselines

| Combo | Result folder (relative to repo root) | Code hash | Trades | W / L / Ambig. | Win rate | Expectancy R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|
| **DIT15** strict B0 | `results/nogit-145d6302/phase_a/pit_refetch/` (`candidates.csv`, `report.txt`, `run_info.txt`) | `cd73bf8d` | 318 | 91 / 167 / 60 | 35.3% | +0.046 | 1.07 | +11.9 | 34.3 |
| **WIT** strict B0 | `results/nogit-7a8ea6d9/phase_a_mtf/wit/pit/` (run id `nogit-7a8ea6d9`) | `943d8a47` | 111 | 40 / 65 / 6 | 38.1% | +0.144 | 1.23 | +15.2 | 9.0 |
| **MIT** strict B0 | `results/nogit-8b4a8735/phase_a_mtf/mit/pit/` (run id `nogit-8b4a8735`) | `ce036150` | 36 | 18 / 16 / 2 | 52.9% | +0.545 | 2.05 | +18.5 | 5.2 |

Also frozen: the DIT15 relaxed candidate pool in the same `pit_refetch/candidates.csv` (4,575 pool rows, 14.4x the strict list;
rows with `relaxed_selected` or `is_b0`). WIT and MIT have no relaxed pool.

**WIT freeze reference (corrected 9 Oct 2026).** The frozen WIT primary dataset is
`results/nogit-7a8ea6d9/phase_a_mtf/wit/pit/` (`candidates.csv`, `run_info.txt`), run id `nogit-7a8ea6d9`, `code_hash=943d8a47`.
It was regenerated with the corrected generator (`src/candidates_mtf.py` using `src/replay_context.py`) from the cached frames and
the existing minute cache; no new data was fetched during the regeneration. The trades, counts, metrics, ambiguity policy and
conclusions in this document are unchanged. Verification of the regenerated run:
- all 111 trade keys match the prior WIT `pit` dataset (`results/nogit-ff52bbc2/phase_a_mtf/wit/pit/`, `code_hash=ce036150`, pre-minute-fetch); every non-outcome field is identical;
- the 95 previously resolved outcomes (outcome, `r_gross`, fill and exit) are unchanged;
- 10 of the 16 previously ambiguous rows resolved (5 WIN, 5 LOSS) from the cached minute data fetched earlier for the 13 `MINUTE_NOT_CACHED` cases (D3); the other 6 stay AMBIGUOUS;
- 6 genuine intrabar ambiguities remain (5 target in fill bar, 1 stop+target in fill bar), all examined at 1-minute resolution and never converted to a win or a loss.
The older reference `results/nogit-8b4a8735/` with `code_hash=ce036150` is superseded by this verified run. That code hash no longer
matches the current tree (its hashed file set differed), so the WIT folder name is `nogit-7a8ea6d9`. The MIT row above is unchanged
and was not regenerated.

None of the three is statistically distinguishable from zero edge or from its pre-hardening version: DIT15 B0 gross expectancy
+0.046 R has a bootstrap 95% interval of [-0.126, +0.226]; the DIT15 old-to-new change interval is [-0.18, +0.32] R; WIT [-0.45, +0.40] R;
MIT [-0.69, +0.79] R. WIT has 105 resolved trades and MIT 34.

## Cost scenarios (round trip, no slippage; D6)

| Expectancy R | 0.10% | 0.20% | 0.30% |
|---|---|---|---|
| DIT15 B0 | -0.120 | -0.287 | -0.454 |
| WIT | +0.069 | -0.007 | -0.083 |
| MIT | +0.514 | +0.483 | +0.452 |

DIT15 is negative at every cost level. Broker-specific costs and slippage are not yet agreed; no scenario was chosen to flatter a result.

## What is frozen per combo (hardening applied)
- Point-in-time trend: zone-break events stamped at the breaking bar's close; queries use only bars closed by the decision time.
- Explicit bar close times (`src/bars.py`, `src/htf_bars.py` for weekly / monthly bars); an unfinished final period is never closed.
- Session-aligned 2h bars anchored at 09:15 (09:15, 11:15, 13:15, 15:15 stub) for DIT15's trend frame and WIT's LTF.
- All-time-high from every close known at the decision time; no end-anchored windows (fixed start).
- Corporate-action handling: a daily close move above 35% is flagged; trades whose window touches one are excluded (listed in the reports); trend and ATH ignore prices before it.
- Deterministic offline replay (`src/replay.py`): 15m, then cached 1-minute drill-down; outcome classes WIN / LOSS / AMBIGUOUS / OPEN / CENSORED / NOFILL; 90-day horizon.
- Decision times: DIT15 = start of the entry 15m bar; WIT = start of the entry 2h bar; MIT = entry day 09:15.

## Decisions D1-D7
- **D1** Keep the existing HTF formation timing (trend at formation queried at the HTF bar label). Moving it to the HTF close (`T_H`) is a strategy change and is not in the baseline (`--formation-at-close` stays off).
- **D2** Keep the TradingView-style session-aligned 2h convention with the 15:15 stub bar (not folded into the 13:15 bar).
- **D3** Resolve missing minute-data ambiguity with read-only Kite minute fetches: done for DIT15 (1,407 requests) and for the 13 WIT cases.
- **D4** "Gap-fill opens beyond the stop" stays AMBIGUOUS; no immediate-stop rule.
- **D5** Correct `docs/STATUS.md`: Kite data is split / bonus adjusted (done; see STATUS.md section 0). Historical results are not altered.
- **D6** Keep reporting 0.10 / 0.20 / 0.30% round-trip scenarios until broker-specific assumptions are supplied; costs are never tuned.
- **D7** DIT15 first; WIT and MIT were hardened afterwards with the same architecture (done: `docs/PHASE_A_MTF_RESULTS.md`).

## Ambiguity left in the frozen baselines
- DIT15 B0 (60 AMBIGUOUS) and the relaxed pool (671): target in fill bar, stop+target in fill bar, gap-fill beyond the stop (by rule), 1 intraday data gap.
- WIT (6): 5 target in fill bar, 1 stop+target in fill bar (true 1-minute ties). The 13 earlier `MINUTE_NOT_CACHED` cases were fetched: 10 resolved, 3 genuine ties.
- MIT (2): both gap-fill beyond the stop.
- No OPEN, CENSORED (except one DIT15 relaxed-pool row) or NOFILL trades.

## Reproducing the frozen numbers
1. Legacy mode reproduces the stored pre-hardening results exactly: DIT15 268 / 268 trades (`results/4d02f6d`), WIT 98 / 98 (`results/50f701a`), MIT 35 / 35 (`results/132d5d8`). Checks: `python scripts/run_phase_a_mtf.py verify --combo=wit|mit`; DIT15 via `tests/test_phase_a.py`.
2. Rebuild commands are in `README.md`. Result-folder names are code hashes (`nogit-<8 hex>`, or the git short hash inside a repository). **The frozen folder names cannot be regenerated by name from today's tree**: new files were added under `src/` after the DIT15 run, so a rebuild creates a differently named folder with the same trades. To read a frozen folder pass `--run=nogit-145d6302` (DIT15) or `--run=nogit-7a8ea6d9` (WIT, verified run, `code_hash=943d8a47`).
3. Reports: `docs/PHASE_A_RESULTS.md` (DIT15), `docs/PHASE_A_MTF_RESULTS.md` (WIT / MIT), `results/nogit-145d6302/comparison_2021/` (DIT15 old vs new and per-combo comparison).

## Phase B inputs derived from the DIT15 baseline (not part of this freeze, listed for orientation)
`results/nogit-145d6302/phase_b/tier1/features.csv` (4,552 rows, 18 model columns), `labels/labeled.csv` (3,882 training labels: 1,229 WIN / 2,653 LOSS),
`folds/` (six walk-forward folds 2023H1-2025H2, 2026 holdout untouched). See `docs/PHASE_B_FEATURES_REPORT.md`,
`docs/PHASE_B_LABELS_REPORT.md`, `docs/PHASE_B_FOLDS_REPORT.md`.

## Known limitations
Survivorship (current 503-ticker universe); corporate-action moves under 35% undetected; the 15:15 bar is missing from the Kite data since 2026-08-03;
the frames used by Phase A carry no volume (volume exists only in the raw cache and its split adjustment has not been checked); 2026 is partly contaminated by chart reviews; small WIT / MIT samples.
