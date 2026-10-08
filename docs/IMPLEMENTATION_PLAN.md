# IPD Trading Decision Support System: implementation plan

Audience: the whole team (engineers who own components, whoever runs validation, and anyone approving gates).
Status: planning document only. It describes work; it changes no code.

Conventions:
- **[E]** exists today, **[P]** planned.
- Facts about current status come from `docs/PHASE_A_RESULTS.md`, `docs/PHASE_B_PLAN.md` and the modules in `src/`.
- Decisions D1-D7 are fixed: bar-label formation timing (D1), session-aligned 2h with the 15:15 stub (D2), minute-data fetch (D3), gap-fill-beyond-stop stays AMBIGUOUS (D4), STATUS.md correction (D5), 0.10/0.20/0.30% cost scenarios (D6), DIT15 first (D7).
- The Tier-1 feature registry (Section 12 of `PHASE_B_PLAN.md`) is frozen: 17 named features, 18 model columns (`trend_entry` becomes two dummies).
- Two registry definitions are still open and must be answered in writing before Phase 4 code: `approach_speed_atr` (signed or absolute, which endpoints) and `ltf_leg_body_atr` (read as the sum of `|close - open|` over the leg candles).

---

## PHASE 0: Project architecture

**1. Objective:** one agreed component map so research results are reproducible and production can later reuse the same code.

**2. Current status:**
- [E] Research pipeline for DIT15 only: `bars`, `asof`, `trend_pit`, `corp_actions`, `candidates`, `replay`, `costs`, `portfolio`, `scripts/run_phase_a.py`.
- [E] Legacy zone engine (`legacy/.../sd_zones.py`, `mtf_zones.py`, `mtf_backtest.py`) imported unchanged, with `src/base_candles.py` monkey-patched in at run time.
- `src/{zones,matching,data,backtest}.py` are still empty stubs.

**3. Tasks:**
- Write `docs/ARCHITECTURE.md` with the component table and interface contracts below.
- Decide whether to port the legacy engine into `src/` (recommended, behind golden tests) or keep importing it (acceptable for now).
- Add `requirements.txt` with pinned versions (scikit-learn 1.4.0 is installed; shap is not).

| Component | Does | Does not |
|---|---|---|
| Data layer | loads frames, adds `close_time`, as-of joins, corporate-action flags | decide trades |
| Zone / MTF / trend engine | zones, matching, trend states | know outcomes |
| Candidate generator | rows with flags and decision times | train or filter |
| Replay / backtester | outcomes (WIN / LOSS / AMBIGUOUS / OPEN / CENSORED / NOFILL), R | change entries |
| Feature builder [P] | the Tier-1 columns only | label rows |
| ML filter [P] | take/skip probability | move entry, stop or target |
| Risk module | sizing, caps, exposure | read model internals |
| Evaluation | metrics, bootstrap, comparisons | tune anything |
| Reporting / explain | tables, importance, trade explanations | |
| Serving [P, later] | scheduled run of the same code | |

Interfaces:
- Data layer to candidate generator: dict of frames per interval.
- Generator to feature builder: candidate rows (CSV or parquet) plus zone objects via `TickerContext` and `zkey`.
- Feature builder to model: a matrix plus a manifest.
- Model to evaluation: probabilities per row id.
- Evaluation takes only rows and outcomes, never frames.

**4. Dependencies:** none.
**5. Inputs:** existing modules and docs.
**6. Artifacts:** `ARCHITECTURE.md`, `requirements.txt`, one-page interface contract.
**7. Validation:** a reviewer can find every module from the doc; imports follow the diagram (the generator never imports feature code).
**8. Leakage / overfitting risks:**
- Leakage: a component that holds both decision data and outcome data. Prevent by contract: only replay and evaluation read outcome columns.
- Overfitting: none yet.
**9. Exit criteria:** architecture approved; research and production explicitly separated (research never imports serving code).

---

## PHASE 1: Data foundation

**1. Objective:** every dataset can be rebuilt bit for bit, and every price used has a known "known-at" time.

**2. Current status:**
- [E] Frozen Kite frames (daily 2012+, 60m and 15m from 2020-11), 503 tickers.
- [E] Raw cache with volume; NIFTY 50 daily.
- [E] `bars.add_close_time`, `asof` joins, `corp_actions` (>35% flag, 30-day pad), `runinfo.code_hash`.
- Prices are split-adjusted (checked on three tickers).
- The 15:15 bar is missing since 2026-08-03.
- The universe is the current 503 names (survivorship bias).
- Minute-data fetch pending (1,407 requests).

**3. Tasks:**
- Complete the minute fetch under the read-only rules (needs the user's Kite login).
- Write a data manifest (file hashes, row counts, date ranges per ticker) and a data-quality report (gaps, duplicates, daily vs 15m disagreement, adjustment checks).
- Decide the point-in-time universe policy: keep the current list and document the bias, or source historical index membership.
- Extend the corporate-action check below 35% only if evidence appears; do not guess.
- Freeze the minute cache.

**4. Dependencies:** Kite login (user); Phase 0 manifest format.
**5. Inputs:** frames, raw cache, universe JSON.
**6. Artifacts:** `data_manifest.json`, `data_quality_report.md`, updated minute cache, written universe policy.
**7. Validation:**
- manifest hash matches on rebuild;
- every frame has monotone timestamps and no duplicates;
- every `close_time` is at or after its bar start;
- corporate-action exclusions are listed.
- Existing tests [E]: close-time, as-of and 2h alignment in `tests/test_phase_a.py`; [P] manifest-hash test.
**8. Leakage / overfitting risks:**
- Leakage: using a bar's label as its known time; as-of joins that use the same-day daily bar. Prevention: `close_time` everywhere and `asof.daily_index_asof` for intraday decisions.
- Overfitting: universe choices must not be made by looking at which tickers perform.
**9. Exit criteria:** minute data fetched and frozen; manifest and quality report approved; universe policy written down.

---

## PHASE 2: Deterministic trading engine

**1. Objective:** the rule engine produces identical candidates for identical data, with every former discretionary filter recorded as a flag.

**2. Current status:**
- [E] DIT15 strict (B0) and relaxed pool through `candidates.build` (pre-fetch: 318 strict trades, 4,575 relaxed candidates).
- [E] Legacy-mode reproduction of the old results is tested.
- [E] Trend: point-in-time zone-break classifier with session-aligned 2h bars.
- WIT, MIT and QIT are not hardened (D7).

**3. Tasks:**
- Write golden tests for the current DIT15 output so a later port cannot drift.
- Re-run Phase A (`generate --label=pit_final`) after the minute fetch; this is the frozen dataset source.
- [P] Port `sd_zones` / `mtf_zones` into `src/` only after the golden tests exist.
- [P, later] Harden WIT and MIT with the same architecture.

**4. Dependencies:** Phase 1 minute data.
**5. Inputs:** frames, config, `docs/RULES.md`.
**6. Artifacts:** `pit_final` candidates file, golden test set, engine version tag.
**7. Validation:** legacy-mode reproduction (503 tickers); append-stability; determinism; forming-bar test.
**8. Leakage / overfitting risks:**
- Leakage: forming bars, entry-bar data, end-anchored windows. Prevention [E]: `close_time` queries, fixed-start frames.
- Overfitting: rule thresholds must not be changed to improve results. Any rule change is a new baseline and invalidates the ML comparison.
**9. Exit criteria:** `pit_final` generated, verified and frozen with its code hash.

---

## PHASE 3: Backtesting engine

**1. Objective:** a realistic, deterministic outcome for every candidate and honest portfolio-level numbers.

**2. Current status:**
- [E] Offline replay with six outcome classes, 15m then cached 1-minute drill-down, gap handling, explicit 90-day horizon, missing-bar check.
- [E] Cost scenarios (0.10 / 0.20 / 0.30%) and a slippage input.
- [E] Sequencing, drawdown, capital cap, concurrency.
- Pre-fetch B0: 318 trades, 79 W / 145 L / 94 AMBIGUOUS, gross expectancy +0.04R, negative net of every cost scenario.

**3. Tasks:**
- Report B0 on `pit_final`, with AMBIGUOUS reasons grouped.
- Add per-year and per-ticker slices to the standard report.
- Document pending-order behaviour (the limit rests until touched; no expiry) and its age distribution (median 17 days, p99 824 days pre-fetch).
- Report slippage as a parameter only (no figure agreed; D6).

**4. Dependencies:** Phase 2.
**5. Inputs:** `pit_final`.
**6. Artifacts:** the B0 baseline report on `pit_final` (the number every later comparison uses).
**7. Validation:** synthetic replay cases [E]; counts add up per year; results identical on rerun.
**8. Leakage / overfitting risks:**
- Leakage: replay output (`fill_price`, `exit_*`, `gap_fill`) used as features. Prevent with the forbidden-column list (Phase 4).
- Overfitting: cost scenarios must not be picked to flatter a result.
**9. Exit criteria:** B0 baseline accepted by the user and frozen.

---

## PHASE 4: Feature engineering (frozen Tier-1 only)

**1. Objective:** the 18 pre-registered columns for every pool row, computed with no future information.

**2. Current status:**
- [P] Nothing exists under `src/ml/`.
- 8 features are in the candidate CSV or derivable from it: `ltf_base_count`, `htf_base_count`, `htf_strong_legout`, `overlap_frac`, `wick_fresh_fail`, `type_demand`, `ltf_pos_in_htf`, `is_0915_bar`.
- `trend_entry` and `cost_in_r_rt0.20` need small wrappers.
- 6 need new computation: `ltf_leg_body_atr`, `htf_zone_width_atr`, `log(ltf_age_bars)`, `risk_atr_d`, `approach_speed_atr`, plus the regime pair `nifty_above_200dma` and `stock_rs63`.
- Two definition questions are open (see the top).

**3. Tasks:**
- Confirm the open definitions in writing.
- Build the registry (name, group, known-at, source), the per-ticker feature builder, and the dataset assembler with a manifest (source run id, code hash, row counts, exclusion counts).
- Parse the stored `htf_key` / `ltf_key` strings; recover `entry_idx` from `entry_time`.
- Implement the leakage tests.
- Not allowed: any structure, volume or Tier-2 feature, or any extra indicator.

**4. Dependencies:** Phase 3 (frozen rows); the two definition answers.
**5. Inputs:** `pit_final` candidates, frames, NIFTY 50 daily.
**6. Artifacts:** versioned feature dataset, feature manifest, leakage test report.
**7. Validation:**
- truncation test (recompute on data cut at the decision time and compare);
- future-perturbation test;
- forbidden-column test;
- missingness report;
- distribution sanity against the pre-fetch rows.
**8. Leakage / overfitting risks:**
- Leakage: ATR index must be D-1 or `entry_idx - 1`; NIFTY only through as-of joins; the 63-day look-back may cross a corporate-action day outside the exclusion window.
- Overfitting: no feature may be added, dropped or redefined after seeing model results; changes mean a new registry version and a fresh holdout decision.
**9. Exit criteria:** all leakage tests pass; feature manifest signed off; dataset version frozen.

---

## PHASE 5: ML meta-labeling

**1. Objective:** a calibrated probability that a candidate wins (+2R before -1R), used only to take or skip.

**2. Current status:** [P] design done in `PHASE_B_PLAN.md`; no code. scikit-learn 1.4.0 is installed.

**3. Tasks:**
- Label from outcome (WIN = 1, LOSS = 0); other classes excluded from training only.
- Models: L2 logistic regression (standardised on the training fold only) and `HistGradientBoostingClassifier` (depth 3, at most 4 logged configurations).
- Calibration only if the reliability check on validation shows it helps (isotonic at 1,000+ rows, otherwise Platt).
- Decision rule fixed in advance: take if `p*2 - (1-p)*L - cost_in_R > 0`, with L the training mean loss.

**4. Dependencies:** Phase 4.
**5. Inputs:** the frozen feature dataset.
**6. Artifacts:** trained models per fold with their configuration, probabilities per row, calibration report.
**7. Validation:** shuffled-label test; reliability curves; model beats a base-rate predictor on Brier before any trading comparison.
**8. Leakage / overfitting risks:**
- Leakage: scalers or calibrators fitted on test rows; sibling rows split across folds. Prevent by fitting only inside the training window plus purge and embargo (Phase 6).
- Overfitting: tune only C and the fixed tree grid; log every configuration tried.
**9. Exit criteria:** both models trained for every fold; no leakage failures; ready for evaluation.

---

## PHASE 6: Validation and anti-overfitting

**1. Objective:** a protocol that stops us from fooling ourselves.

**2. Current status:** [P] designed (windows, purge, embargo); no code.

**3. Tasks (the protocol):**
- Expanding walk-forward: train from 2021-01-01; test half-years 2023H1 to 2025H2; inner validation = last 6 months of each training window.
- Purge: drop training rows whose `exit_time` is at or after the test start. Embargo: 5 trading days before the test start.
- Rows sharing an HTF zone stay on one side of each split.
- Frozen final test: 2026-01-01 onward, run once. It is partly contaminated by the 2026 chart reviews, so the clean evidence is forward data after the freeze date.
- Unseen stocks: 5 hashed ticker groups; train on the others, test on the held-out group.
- Shuffled-label sanity test; feature-rank and coefficient stability across folds; confidence intervals by month blocks and ticker clusters.
- Pre-registration: the Phase 7 criteria are written and signed before the first training run; an experiment log records every model and configuration tried.

**What can be tuned, and on what data:** only the logistic C and the boosting grid, only on inner validation. Everything else (features, threshold rule, cost scenario, folds) is fixed. Test windows and the final holdout are never used for choices.
**Robustness tests:** per-year, per-ticker-group and per-cost-scenario results; the filter must beat the random filter.

**4. Dependencies:** Phase 5.
**5. Inputs:** feature dataset, probabilities.
**6. Artifacts:** fold definitions, experiment log, validation report.
**7. Validation:** unit tests for fold boundaries (no overlap, purge works); shuffled-label AUC inside its 95% band around 0.5.
**8. Leakage / overfitting risks:** repeated test-set tuning; folds that overlap. Prevent with a single-command final run that writes a locked result file and refuses a second run.
**9. Exit criteria:** protocol approved; fold code reviewed by someone other than its author.

---

## PHASE 7: Strategy evaluation

**1. Objective:** decide whether the filter improves the trading strategy, not the classifier.

**2. Current status:** [P]. Reuse `portfolio.summary`, `capital_constrained`, `concurrency` and the cost scenarios [E].

**3. Tasks:** compare, each gross and at 0.10 / 0.20 / 0.30%:

| Name | What it is |
|---|---|
| B0 | existing rules only |
| B1 | whole relaxed pool, taken |
| ML | pool rows the filter takes |
| ML-on-B0 | B0 rows the filter takes |
| B2 | random filter at the same take-rate (1,000 draws) |
| B3 | best single old filter, chosen on training data |

Report for each:
- trade count, take-rate, trades per year;
- the six outcome counts, with AMBIGUOUS best/worst bounds and by predicted decile;
- win rate with interval, expectancy, profit factor, total R, maximum drawdown in R;
- capital-capped versions;
- per-year and per-ticker-group stability.

Success needs all pre-registered criteria (a)-(g) of `PHASE_B_PLAN.md` Section 13 on the 2023-2025 stream at 0.20%, then agreement on the 2026 test. Classification accuracy or AUC alone counts for nothing.

**4. Dependencies:** Phases 3 and 6.
**5. Inputs:** probabilities, outcomes.
**6. Artifacts:** evaluation report with paired block-bootstrap differences.
**7. Validation:** counts add up; metrics reproduce on rerun.
**8. Leakage / overfitting risks:** reading the final test more than once; picking the cost scenario or threshold after seeing results.
**9. Exit criteria:** report published, whatever the outcome. A null or negative result is a valid exit.

---

## PHASE 8: Risk management

**1. Objective:** define the limits the system always obeys and what ML may touch.

**2. Current status:**
- [E] Rs 1,000 risk per trade, Rs 1L notional cap with no leverage, 2:1 target, deterministic capital cap, concurrency and drawdown reporting.
- No exposure limits, drawdown controls or correlation handling beyond the capital cap.

**3. Tasks:**
- Document today's risk rules as the baseline.
- Add reporting-only measures first: peak exposure, concurrent positions, correlated-position counts (sector grouping only if a map is sourced).
- Define drawdown controls (a pause rule) only as a simulation to evaluate, not a default.

**ML is allowed to:** take or skip a candidate.
**ML is not allowed to:** move entry, stop or target; change zone or matching rules; raise risk above the cap; override the capital cap or any drawdown rule; select the universe.
**Probability-based sizing:** out of scope for the first experiment. It may be evaluated later as a separately pre-registered experiment, capped by the existing Rs 1,000 and Rs 1L limits.

**4. Dependencies:** Phases 3 and 7.
**5. Inputs:** B0 and ML trade lists.
**6. Artifacts:** risk specification, exposure report.
**7. Validation:** limits enforced in tests (a trade exceeding a cap is rejected); simulation shows the capital cap is never exceeded.
**8. Leakage / overfitting risks:** drawdown rules chosen after seeing the equity curve. Fix rules before simulation and test on the walk-forward stream only.
**9. Exit criteria:** specification approved; baseline numbers unchanged.

---

## PHASE 9: Explainability and monitoring

**1. Objective:** understand why trades are accepted or rejected, and notice when the model or data degrade.

**2. Current status:** [P]. Nothing exists.

**3. Tasks:**
- Logistic regression: standardised coefficients with bootstrap intervals, per fold.
- Permutation importance on out-of-sample folds, per feature and per feature group; SHAP for both models (shap must be added); ALE plots for the top features.
- Trade-level explanation file for accepted and rejected trades; importance stability across folds.
- Monitoring [P, after validation]: input drift per feature against training, performance drift against the pre-registered range, data-quality checks (missing bars, adjustment gaps), model confidence (probability histogram).
- Retraining policy: fixed schedule (for example half-yearly), always through the same walk-forward protocol; no retraining on a drift alert alone; the old model stays until the new one passes the same criteria.

**4. Dependencies:** Phase 5 (models), Phase 7 (comparison).
**5. Inputs:** models, out-of-sample rows.
**6. Artifacts:** explain outputs, monitoring spec, retraining policy.
**7. Validation:** SHAP additivity check; drift metrics are zero on training data.
**8. Leakage / overfitting risks:** explanations on training rows read as evidence; importance used to prune features after the fact. Compute explanations on out-of-sample data and never feed them back into feature selection.
**9. Exit criteria:** explanation outputs reviewed; monitoring thresholds written down.

---

## PHASE 10: Production architecture (only after Phase 11 passes)

**1. Objective:** a decision-support service that runs the validated pipeline daily.

**2. Current status:** [P], deliberately not started. Kite use stays read-only (instruments and historical data); no order placement.

**3. Tasks:**
- Start file-based: versioned parquet or CSV, model files, run manifests, a scheduled job, a small read-only API and dashboard.
- Add a database only when concurrent users or query volume require it; PostgreSQL is the default choice then. Supabase and Docker are optional conveniences, not requirements.
- Scheduled ingestion, the same feature pipeline, model serving that loads a versioned model, a decision engine that writes a candidate list with probabilities and explanations, logging, alerts on data-quality failures.

**4. Dependencies:** Phase 11 evidence; Phase 9 monitoring.
**5. Inputs:** frozen code, model, manifests.
**6. Artifacts:** service, API specification, dashboard, runbook.
**7. Validation:** a replay test feeds historical days through the live path and must reproduce the research outputs exactly.
**8. Leakage / overfitting risks:** live data timing differs from the frozen frames (late bars, missing 15:15 bar). Prevent with the same `close_time` rules and the replay test.
**9. Exit criteria:** replay equivalence passes; paper-run period completed.

---

## PHASE 11: Final system validation

**1. Objective:** state exactly what evidence permits the claim "ML improves the trading strategy".

**2. Current status:** [P].

**3-7. Evidence required (all of it):**
1. All Phase 4 leakage tests and the shuffled-label test pass on the frozen dataset.
2. On the 2023-2025 walk-forward stream at 0.20% cost, criteria (a)-(g) hold:
   - net expectancy above both B0 and B1, with a bootstrap interval for the difference excluding 0;
   - net expectancy above 0 and profit factor above 1.1;
   - above the 95th percentile of the random filter;
   - maximum drawdown no worse than B0;
   - at least 100 trades and at least 30 per year;
   - better than B0 in at least 2 of 3 years and at least 4 of 5 ticker groups;
   - Brier score better than the base rate.
3. The result agrees in direction across all three cost scenarios.
4. The frozen 2026 test, run once, agrees in direction.
5. A forward paper period after the freeze date agrees in direction; this is the only clean out-of-sample evidence.
6. The experiment log shows no repeated test-set tuning.
7. Preferably the same architecture reproduces the direction on WIT or MIT once hardened.

**8. Leakage / overfitting risks:** claiming success from one metric, one period or one cost scenario.
**9. Exit criteria:** a written conclusion stating the result, including a clean "no improvement" outcome.

---

## A. Dependency / order diagram

```
P0 Architecture --> P1 Data (minute fetch <- user login) --> P2 Engine (pit_final frozen)
                                                                  |
                                      P3 Backtest / B0 baseline <-+
                                              |
              (open definitions) --> P4 Features --> P5 ML models
                                              |            |
                                              +--> P6 Validation protocol --> P7 Evaluation
                                                                                  |
                              P8 Risk spec (can start after P3) -----------------+
                              P9 Explain / monitor (after P5, P7) ---------------+
                                                                                  v
                                                        P11 Final validation --> P10 Production
```

## B. What can be developed in parallel

- **Now, no dependencies:** `requirements.txt`, the architecture doc, data manifest and data-quality tooling, fold and purge code with its tests, evaluation and bootstrap tooling, the leakage test harness, the risk specification.
- **After `pit_final` is frozen:** the feature builder and dataset assembler (can be developed earlier against the pre-fetch candidates, for development only).
- **After features exist:** models, explainability code, the monitoring specification.
- **Blocked on the user:** Kite login for the minute fetch; D6 broker costs.

## C. Recommended team task split (adapt to team size)

| Role | Owns |
|---|---|
| Data engineer | Phase 1: fetch, manifest, data-quality, universe policy, `requirements.txt` |
| Engine / backtest engineer | Phases 2-3: golden tests, `pit_final`, B0 report, later WIT/MIT hardening |
| ML engineer | Phases 4-5 and 9: features, dataset, models, explanations |
| Validation / QA lead | Phases 6-7 and 11: fold code, leakage tests, evaluation, experiment log. Must not write the features or models they validate |
| Platform engineer (later) | Phase 10 |
| Project owner | decisions: feature definitions, costs, universe, gate sign-offs |

## D. Technology and components

- Python 3.11, pandas 2.2, numpy 1.26, pytest [E]; scikit-learn 1.4.0 (installed, to be pinned); shap [P] (Phase 9).
- Files: CSV or parquet plus JSON manifests; code hash as run id (git hash once on a branch).
- No ML library beyond scikit-learn in the first experiment (no LightGBM, deep learning or Random Forest).
- Kite read-only client [E]; `kiteconnect` installed for 3.11.
- Production [P]: an OS-level scheduler, a small web API, a dashboard; a database only if justified in Phase 10.

## E. What should NOT be built yet

- Any structure, volume, Tier-2 or extra-indicator features.
- Probability-based position sizing.
- A database, Docker, Supabase, or any API/UI before Phase 11 passes.
- WIT/MIT/QIT hardening (D7) and any ML on them.
- Live trading or order placement of any kind.
- Random Forest, LightGBM, deep learning, or any model beyond the two chosen.
- A port of the legacy engine without golden tests.

## F. Milestones

| # | Milestone | Gate |
|---|---|---|
| M0 | Architecture doc, `requirements.txt`, open feature definitions answered | team sign-off |
| M1 | Minute fetch done, data manifest and quality report | manifest hash stable |
| M2 | `pit_final` generated and frozen; B0 baseline on it | user accepts baseline |
| M3 | Tier-1 features and dataset, all leakage tests green | QA lead signs |
| M4 | Fold/purge/embargo code and experiment log, pre-registration signed | second-person review |
| M5 | Models trained per fold, shuffled-label test passed | |
| M6 | Walk-forward evaluation vs B0, B1, random filter | report published |
| M7 | Frozen 2026 test run once | locked result |
| M8 | Explainability and monitoring spec | |
| M9 | Forward paper period | agreement in direction |
| M10 | Production decision (go or no-go) | Phase 11 evidence |

## G. Final acceptance checklist

- [ ] Minute data fetched, cache frozen, manifest hash matches.
- [ ] `pit_final` regenerates identically from the recorded code hash.
- [ ] Legacy-mode reproduction and golden tests pass.
- [ ] B0 baseline report on `pit_final`, accepted.
- [ ] 18-column registry implemented exactly as written; both open definitions recorded.
- [ ] Truncation, future-perturbation, forbidden-column and shuffled-label tests pass.
- [ ] Fold code reviewed; no overlap; purge and embargo verified.
- [ ] Experiment log complete; hyperparameters chosen on inner validation only.
- [ ] Criteria (a)-(g) evaluated and reported, including failures.
- [ ] Cost scenarios 0.10 / 0.20 / 0.30% reported; none picked after the fact.
- [ ] Final 2026 test run once.
- [ ] Forward paper evidence collected.
- [ ] Explanations and monitoring spec delivered.
- [ ] Risk limits tested; ML scope limited to take/skip.
- [ ] Production phase started only after all of the above.

## H. Biggest technical risks and mitigations

| Risk | Mitigation |
|---|---|
| Too few labelled rows if the minute fetch is incomplete (36% of the pool unlabelled pre-fetch) | finish the fetch; report AMBIGUOUS by predicted decile; flag folds above 25% ambiguity |
| No real edge in the rules, so ML has nothing to filter (B0 is negative after every cost scenario) | accept a null result; do not tune to find one |
| Hidden look-ahead in a feature | truncation and future-perturbation tests run in CI; known traps listed per feature |
| Correlated rows (97% of tickers have multiple candidates) inflating confidence | month-block and ticker-cluster bootstrap; sibling rows on one side of a split |
| 2026 holdout partly contaminated by chart reviews | treat it as confirmation only; forward data is the clean test |
| Survivorship bias | document it; compare models on the same universe; seek historical membership if affordable |
| Code drift invalidating results | freeze rule; run id plus code hash recorded in every artifact |
| Costs not yet known | keep the three scenarios; never pick one to flatter a result |
| Legacy monkey-patching fragility | golden tests before any port; port only in a dedicated phase |
| Pending orders can sit for years (p99 824 days) | report the age distribution; any expiry rule is a strategy change needing a decision |
| Over-reading explainability | explanations only on out-of-sample data; never used to select features |
