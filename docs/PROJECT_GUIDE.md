# IPD Trading Decision Support System: project guide

One file to read before touching the project. Everything here comes from the repository's code, tests and docs; where a number is quoted, its source file is named.
If this guide and a source file disagree, the source file wins; please fix the guide.

**Status tags used throughout**
- **IMPLEMENTED**: exists in code and runs.
- **FROZEN**: fixed contract; do not change without declaring a new baseline or registry version and discussing it first.
- **PLANNED**: documented, not implemented.
- **DEFERRED**: explicitly left out of the first experiment (or until later).
- **KNOWN LIMITATION**: a documented weakness that is accepted for now.

---

# 1. Project overview

**Purpose.** A decision-support system for NSE cash equities that finds supply / demand trade setups across several timeframes, backtests them realistically, and (being added) uses
machine learning to rank the setups the rules produce. It is a research system: it does **not** place orders.

**Trading problem.** Supply and demand zones are price areas where a strong move started after a short consolidation (a "base"). The idea is that unfilled orders remain there, so price returning to
the zone tends to react. A discretionary trader marks these by eye; the code reproduces that marking (see `docs/RULES.md`, which records the trader's corrections rule by rule) so it can be
tested over hundreds of stocks and years.

**Rule-based supply / demand strategy (in one paragraph).**
A *higher-timeframe (HTF)* zone gives the directional bias. A *lower-timeframe (LTF)* zone formed inside the same move, still untouched when the HTF bar closed, supplies the actual trade: entry at the LTF zone's near edge (proximal),
stop just beyond its far edge (distal, plus a 0.1 ATR buffer), target at 2x the risk (2R). Position size is set so a full stop-out costs at most Rs 1,000 (and the position never exceeds Rs 1,00,000 notional). A third, intermediate
timeframe classifies trend, and a trade against a confirmed trend is rejected.

**Why multi-timeframe.** The HTF decides *whether and which way* (bias and where the big players acted); the LTF decides *where exactly* (a tight entry and stop inside the HTF zone, so risk per share is small). The trend timeframe
sits between them. The combos differ only in the timeframes: DIT15 (daily / 2h trend / 15m), WIT (weekly / daily trend / 2h), MIT (monthly / weekly trend / daily).

**Role of ML.** The rule engine generates candidate trades. ML never invents trades and never changes entry, stop, target or size. It estimates, for each rule-generated candidate, the probability that it reaches +2R before -1R, and a fixed rule
turns that probability into take / skip. Whether this selection helps is what the Phase B experiment tests.

**What the system does NOT currently do**
- It does not trade or place orders (Kite is used read-only for historical data only).
- No ML model has been trained yet (**PLANNED**): features, labels and validation folds exist; models, thresholds and the ML evaluation do not.
- There is no market-structure engine (no BOS / CHoCH / swing logic). "Trend" is inferred from supply / demand zone breaks on the intermediate timeframe.
- No relaxed candidate pool for WIT or MIT; ML on WIT / MIT is not started (**DEFERRED**).
- No API, database, dashboard or live data feed (production is intentionally not started: `docs/IMPLEMENTATION_PLAN.md`, Phase 10).
- No broker-specific costs (cost scenarios only) and no portfolio-level risk controls beyond the Rs 1,00,000 capital cap.
- No evidence yet of a statistically demonstrated trading edge: see section 5.

---

# 2. Architecture

```
Market / Data                      Kite historical bars (daily 2012+, 60m and 15m from 2020-11), minute bars for ambiguous trades, NIFTY 50 daily
   |                               data/cache/ (NOT in git)                                                                      [data layer IMPLEMENTED]
   v
Data preparation                   src/bars.py, src/htf_bars.py, src/asof.py, src/corp_actions.py   explicit bar close times, session-aligned 2h bars,
   |                               weekly / monthly bars, as-of joins, corporate-action flags                                      [IMPLEMENTED, FROZEN]
   v
Phase A rule engine                legacy/handoff/handoff/code/{sd_zones,mtf_zones}.py + src/base_candles.py + src/trend_pit.py
   |                               zones, HTF/LTF matching, trend filter                                                          [IMPLEMENTED, FROZEN]
   v
Candidate trades                   src/candidates.py (DIT15), src/candidates_mtf.py (WIT/MIT); one row per order, former filters kept as flags;
   |                               outcome from src/replay.py                                                                   [IMPLEMENTED, FROZEN]
   v
Phase B feature extraction         src/ml/features.py, registry.py   18 columns known at the decision time                      [IMPLEMENTED, FROZEN registry]
   v
Labels                             src/ml/labels.py   WIN = 1 / LOSS = 0, everything else unlabeled                              [IMPLEMENTED]
   v
Walk-forward splits                src/ml/splits.py   6 expanding folds, 6-month validation, embargo, purge, 2026 holdout        [IMPLEMENTED]
   v
ML model                           logistic regression first, HistGradientBoosting as comparison                               [PLANNED]
   v
Probability / threshold            P(win) -> take or skip with a fixed expected-value rule                                     [PLANNED]
   v
ML-filtered trades                 the same candidates, minus the skipped ones; each keeps its own stored outcome              [PLANNED]
   v
Backtest comparison                rule-only vs ML-filtered vs random filter of the same size                                  [PLANNED; metrics code IMPLEMENTED]
   v
Risk / performance analysis        src/portfolio.py (R metrics, drawdown, capital cap), src/costs.py (0.10 / 0.20 / 0.30%)     [IMPLEMENTED building blocks]
```

**Each stage**
1. *Market / data.* Prices come from Kite's historical API (read-only) and are stored as CSV frames. Daily, 60-minute and 15-minute bars for 503 tickers; 1-minute bars only where an ambiguous trade needed them.
2. *Data preparation.* Every bar gets an explicit `close_time` (the moment its OHLC is final). The label of a bar is its start, never the time it became known. Weekly and monthly bars are built from daily bars with the legacy grouping but a real close time; 2-hour bars are anchored at 09:15.
3. *Rule engine.* Detects zones on each timeframe, pairs an HTF zone with an LTF zone, applies the trend filter, and defines entry / stop / target.
4. *Candidate trades.* One row per order. For DIT15 the "relaxed pool" keeps rows that the strict pipeline would have rejected for discretionary reasons, recording each reason as a flag, so ML has enough rows.
5. *Features.* 18 numbers computed from information available at the start of the entry bar.
6. *Labels.* What happened afterwards, from the deterministic replay.
7. *Walk-forward splits.* Chronological train / validation / test windows with an embargo.
8. *Model, probability, threshold.* Planned; see sections 12-13.
9. *ML-filtered trades, backtest comparison, risk analysis.* The same candidates with their own outcomes, evaluated with trading metrics and costs, against the unfiltered set and a random filter.

---

# 3. Repository structure

| Path | Purpose |
|---|---|
| `src/` | The engine. `bars.py` (bar close times, session 2h), `htf_bars.py` (weekly / monthly bars with close times), `asof.py` (as-of joins), `corp_actions.py` (>35% move flags), `trend_pit.py` (point-in-time trend, ATH), `base_candles.py` (V2 base-candle logic, patched into the legacy engine), `candidates.py` (DIT15 candidate builder), `candidates_mtf.py` (WIT / MIT builder), `replay.py` (offline deterministic outcome replay), `exits.py` and `kite_client.py` (read-only Kite access and the original online replay), `costs.py`, `portfolio.py`, `runinfo.py` (run ids). `backtest.py`, `data.py`, `matching.py`, `zones.py` are one-line stubs. |
| `src/ml/` | Phase B. `registry.py` (frozen feature registry), `features.py`, `labels.py`, `splits.py`. No model code yet. |
| `legacy/handoff/handoff/code/` | The original zone engine, imported unchanged: `sd_zones.py` (zone detection), `mtf_zones.py` (combos, trend, matching), `mtf_backtest.py`, `offline_loader.py`, `webapp/universe_live.json` (the ticker universe). Required by everything. |
| `scripts/` | Runners and tools. Phase A: `run_phase_a.py` (DIT15), `run_phase_a_mtf.py` (WIT / MIT), `fetch_minute_for_ambiguous.py`, `compare_phase_a_2021.py`, `compare_by_combo.py`, `fetch_kite_*.py`, plus older runners (`run_*_kite.py`, `replay_common.py`, ...). Phase B: `run_phase_b_features.py`, `run_phase_b_labels.py`, `run_phase_b_folds.py`. |
| `tests/` | pytest suites (section 18) and `tests/golden/` (hand-checked cases). |
| `docs/` | Rules, decisions, status, plans, reports. Start with `PHASE_A_FREEZE.md`. |
| `results/` | Stored runs, named by run id (a code hash, e.g. `nogit-145d6302`). Frozen: `nogit-145d6302` (DIT15 + Phase B datasets), `nogit-8b4a8735` (WIT / MIT). Older commit-hash folders are history. |
| `data/cache/` | Market data cache. Large; **not** in git (section 19). |
| `config.py` | Strategy constants (impulse and base thresholds, caps, 2:1 reward, Rs 1,000 risk, Rs 1,00,000 capital, 0.30 overlap, split date). |
| `requirements.txt` | Pinned dependencies (Python 3.11). |
| `pytest.ini` | `testpaths = tests` and the `slow` marker. |
| `README.md` | Short entry point: setup, data, tests, run commands. |
| `.gitignore` | Excludes secrets, caches, generated and personal files (section 19). |
| `CLAUDE.md` | Standing project rules (baseline discipline, read-only Kite, no `.env` access). |
| `kite_login.py` | Interactive Kite login that writes the daily access token to `.env`. |
| `test_kite.py` | Scratch connectivity script (not a test; `pytest.ini` keeps it out of collection). |

Key docs: `RULES.md` (every rule with the trader's wording), `DECISIONS.md` (experiment history; older numbers carry a known exit bug), `STATUS.md` (section 0 is current), `PHASE_A_*.md`, `PHASE_B_*.md`, `IMPLEMENTATION_PLAN.md`, `ML_BACKEND_EXPLAINED.md`.

---

# 4. Phase A: rule-based backtesting

**The three combos (HTF / trend / LTF)**

| Combo | HTF (bias) | Trend timeframe | LTF (execution) | Decision time T_d |
|---|---|---|---|---|
| **DIT15** | daily | 2h (from 60m) | 15m | start of the entry 15m bar |
| **WIT** | weekly | daily | 2h (from 60m) | start of the entry 2h bar |
| **MIT** | monthly | weekly | daily | entry day 09:15 |

QIT (quarterly / monthly / weekly) exists as an old script and is not part of the frozen baselines.

**Candidate generation**
1. *Zones.* An **impulsive leg** ("legout") is a candle with body at least 1.3 ATR (14-period Wilder) closing in the outer 25% of its range (LTF legs at most 2 candles). The **base** is the contiguous run of small candles
   just before it (V2 definition: not impulsive, and either total wick above 50% of the body or body at most 0.5 ATR; each at most 2.5 ATR tall). A base longer than 5 candles is rejected (not truncated). Zone lines: demand proximal =
   highest body edge of the base, distal = lowest wick minus 0.1 ATR (supply mirrored); the LTF zone may be drawn wick-to-wick when the legout is strong. Extra validity rules: base height relative to the leg, clean departure,
   minimum width (0.5 ATR), LTF legout must close beyond the legin, HTF legout must close beyond the base wick. (Full rules: `docs/RULES.md`, `config.py`.)
2. *HTF-LTF pairing.* One result per HTF zone: an LTF zone of the same type that formed during the HTF zone's own formation window, was still untested when the HTF bar closed, and overlaps the HTF zone by at least 30% of its own height. The
   most recently formed candidate wins.
3. *Trend filter.* Trend is read on the intermediate timeframe from zone breaks (two breaks of the same kind confirm a trend; one break against a trend drops it to sideways; a close at an all-time high forces "up"). The filter is asymmetric:
   demand is blocked only in a confirmed downtrend, supply only in a confirmed uptrend. It is checked at HTF formation and again at the entry.
4. *HTF wick-freshness.* If price already reached the HTF base's true wick extreme earlier (a separate visit), the HTF zone is used up and the trade is rejected.

**Entry, stop, target, size**
- **Zone entry:** a pending limit order at the LTF proximal edge, triggered when price first trades into it after the HTF bar has closed. There is no expiry. For the DIT15 pool, the time from HTF confirmation to entry had a median of about 17 days and a 99th percentile of 824 days (measured on the pre-fetch pool; `docs/PHASE_B_PLAN.md`, feature `htf_age_days`).
- **Stop:** the LTF distal edge (including the 0.1 ATR buffer). **Target:** entry plus 2 x risk (demand; mirrored for supply), the "2R target".
- **Sizing:** `shares = min(floor(1000 / risk), floor(100000 / entry))`. DIT15 stops are tight (in the earlier 268-trade list the median stop was 0.62% of price and 78% of trades were limited by the notional cap rather than the Rs 1,000 risk), so real risk per trade is then below Rs 1,000. No leverage.

**Replay (outcome simulation, `src/replay.py`)**
- Walks the 15-minute bars from the decision time. The fill is the first bar that trades through the entry level (at the open if it gaps through). The stop and target exist only after the fill. A gap through the stop books at the open (R can be below -1).
- If one bar contains both the stop and the target (or the target in the fill bar, where it may precede the fill), the **minute-level ambiguity resolution** replaces that bar by its cached 1-minute bars. If that is still a tie, or a gap-fill opens beyond the stop (rule D4), or the day has missing intraday bars, the trade is **AMBIGUOUS** and is never converted into a win or loss.
- Horizon 90 days; no time exit. Outcome classes: WIN, LOSS, AMBIGUOUS, OPEN (filled, nothing within 90 days), CENSORED (data end before the horizon), NOFILL (entry never traded).

**Point-in-time (PIT) logic.** Every decision uses only bars closed by the decision time. Zone-break events are stamped at the breaking bar's close; trend queries use closed bars only; the all-time-high uses every close known at the time;
daily data for an intraday decision come from the previous day (D-1); there are no end-anchored windows; 2h bars are session-aligned. A "legacy" mode of each builder reproduces the pre-hardening results exactly, so the hardening effect can be measured.

**Costs.** `src/costs.py`: a configurable round-trip percentage per side plus slippage; net R = gross R minus `cost_R`, where `cost_R = (pct per side / 100) * (fill + exit price) / risk`. Scenarios reported: 0.10%, 0.20%, 0.30% round trip, no slippage. No broker-specific schedule is agreed.

**Portfolio constraints.** The frozen baselines are "all signals" (every triggered trade counts, no capital limit; peak DIT15 concurrency 3 positions and Rs 2.91 lakh deployed). A deterministic capital-constrained variant (Rs 1,00,000, positions free capital at their exit) and R-curve drawdown
exist in `src/portfolio.py` and are reported alongside.

---

# 5. Phase A frozen baselines (`docs/PHASE_A_FREEZE.md`, frozen 8 Oct 2026)

Entries from 2021-01-01 to 2026-10-01, 503-ticker universe, Kite data (split / bonus adjusted), gross R unless stated. Resolved = WIN + LOSS.

| Combo | Result folder | Code hash | Trades | W / L / Ambiguous | Win rate | Expectancy R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|
| **DIT15** strict B0 | `results/nogit-145d6302/phase_a/pit_refetch/` | `cd73bf8d` | 318 | 91 / 167 / 60 | 35.3% | +0.046 | 1.07 | +11.9 | 34.3 |
| **WIT** strict B0 | `results/nogit-8b4a8735/phase_a_mtf/wit/pit/` | `ce036150` | 111 | 40 / 65 / 6 | 38.1% | +0.144 | 1.23 | +15.2 | 9.0 |
| **MIT** strict B0 | `results/nogit-8b4a8735/phase_a_mtf/mit/pit/` | `ce036150` | 36 | 18 / 16 / 2 | 52.9% | +0.545 | 2.05 | +18.5 | 5.2 |

Also frozen: the DIT15 relaxed candidate pool in the same `candidates.csv` (4,575 pool rows, 14.4x the strict list). WIT and MIT have no relaxed pool.

**Cost scenarios, expectancy R (round trip, no slippage)**

| | 0.10% | 0.20% | 0.30% |
|---|---|---|---|
| DIT15 B0 | -0.120 | -0.287 | -0.454 |
| WIT | +0.069 | -0.007 | -0.083 |
| MIT | +0.514 | +0.483 | +0.452 |

**Important caveats (from the freeze document)**
- None of the three is statistically distinguishable from zero edge: DIT15 B0 gross expectancy +0.046 R has a bootstrap 95% interval of [-0.126, +0.226]. The old-to-new (pre-hardening to hardened) changes are also inside the noise: DIT15 [-0.18, +0.32] R, WIT [-0.45, +0.40] R, MIT [-0.69, +0.79] R.
- DIT15 is negative at every cost level. WIT is about break-even at 0.20%. MIT stays positive but has only 34 resolved trades. WIT has 105 resolved trades.
- The hardening mostly changes *which* trades are selected, not how they exit: for DIT15 the 201 trades common to old and new have identical outcomes.
- Ambiguity left in the baselines: DIT15 B0 60 (relaxed pool 671); WIT 6 (5 target in fill bar, 1 stop+target in fill bar); MIT 2 (gap-fill beyond the stop).
- Break-even for a 2:1 trade before costs is a 33.3% win rate. The DIT15 relaxed pool, resolved, wins 31.7% (3,903 trades) with expectancy -0.049 R gross (`results/nogit-145d6302/comparison_2021/comparison_report.md`).

---

# 6. Phase A data and known limitations (all **KNOWN LIMITATION** unless noted)

- **Universe.** 503 tickers: `universe_live.json` (504 validated NSE names, built 28 Sep 2026 from Nifty 500 and related lists) minus HFCL.NS (Kite lists only HFCL-BE).
- **Survivorship bias.** The universe is today's list applied to 2021-2026 history; delisted stocks are absent. This inflates absolute results and affects the baseline and any ML filter equally.
- **Corporate actions.** Kite prices are split / bonus adjusted (verified on NESTLEIND 2024-01, TATASTEEL 2022-07, IRCTC 2021-10). A daily close move above 35% is flagged; trades whose window touches one are excluded (3 DIT15 B0 trades) and trend / ATH ignore prices before it.
  28 abnormal moves in 24 tickers exist in the frames. Adjustment differences smaller than 35% (e.g. a demerger such as TMPV) are **not** detected.
- **Missing 15:15 bars.** From 2026-08-03 the 15:15 bar is absent from the Kite 15-minute and 60-minute data (documented in `docs/PHASE_A_RESULTS.md`, observed on the checked tickers and in the raw cache); handled by an INTRADAY_DATA_GAP rule that marks affected trades AMBIGUOUS.
- **Volume.** The frames used in Phase A contain no volume. Volume exists only in the raw cache, and its split adjustment has not been checked. No volume feature is in the frozen registry.
- **2026 contamination.** The 2026 period is partly contaminated: chart reviews of 2026 setups influenced earlier rule choices. The only fully clean test is data after the freeze date.
- **Small samples.** WIT 105 and MIT 34 resolved trades: no statistical conclusion about either; ML on them alone is not viable (**DEFERRED**).
- **Other documented ambiguities.** AMBIGUOUS trades by rule (gap-fill beyond the stop, ties inside one minute); the trend history for DIT15 starts in 2020-11 (60m data); the HTF formation trend check still uses the HTF bar label (stale by about a day, not a leak; decision D1);
  pending orders have no expiry; the older `docs/DECISIONS.md` numbers were measured under a known exit bug and are invalid for comparison.

---

# 7. Phase B objective

**Why ML exists.** The frozen rule-only baselines are weak: DIT15 is negative after costs, WIT is break-even, MIT is promising but tiny. Many rule-generated candidates lose. The question is whether the information visible when a candidate triggers can separate the better ones.

**The principle.** The rule engine generates candidates. ML does not invent trades. ML estimates which rule-generated candidates are more likely to reach the desired outcome (+2R before -1R).

**Meta-labeling in simple language.** The rules say "here is a trade". A second model, trained on past rule-generated trades and their results, answers "of the trades the rules offer, which look like the ones that worked?" It does not predict the market;
it grades the rules' own output. Because entry, stop, target and size are already fixed by the rules, grading can only change *which* trades are taken, so the comparison with taking everything is clean.

**Scope.** DIT15 only for the first study (4,552 candidate rows). WIT / MIT are **DEFERRED**.

---

# 8. Phase B feature pipeline (**IMPLEMENTED**, registry **FROZEN** as `tier1-v1`)

**Files.** `src/ml/registry.py` (the contract), `src/ml/features.py`, `scripts/run_phase_b_features.py`. Output: `results/nogit-145d6302/phase_b/tier1/{features.csv, exclusions.csv, manifest.json, report.txt}`.

**Decision-time constraint.** Each candidate is scored at **T_d**, the start of its 15-minute entry bar. A feature may use only data final before T_d: 15-minute bars strictly before the entry bar; daily data dated before the entry date (**D-1**);
zone data up to the zone's completion (T_L for the LTF zone, T_H for the HTF zone). The entry bar's own prices are never read.

**The 18 model columns** (17 named features; `trend_entry` becomes two dummies)

| # | Column | Meaning | Known at |
|---|---|---|---|
| 1 | `ltf_base_count` | candles in the LTF base | T_L |
| 2 | `htf_base_count` | candles in the HTF base (strict config) | T_H |
| 3 | `htf_strong_legout` | 1 if the HTF leg gapped open beyond 0.5 ATR or had two impulsive candles | T_H |
| 4 | `ltf_leg_body_atr` | sum of `abs(close-open)` over the LTF leg candles / ATR15 at the leg end | T_L |
| 5 | `htf_zone_width_atr` | `abs(htf_proximal - htf_distal)` / daily ATR at the HTF leg end | T_H |
| 6 | `overlap_frac` | share of the LTF zone inside the HTF zone | T_H |
| 7 | `ltf_pos_in_htf` | `(entry - htf_distal)/(htf_proximal - htf_distal)`; 0 = HTF distal, 1 = HTF proximal | T_H |
| 8 | `wick_fresh_fail` | 1 if an earlier daily bar already reached the HTF base wick (old rule R10 as a flag) | D-1 |
| 9 | `log_ltf_age_bars` | ln(15m bars between LTF leg end and entry bar) | T_d |
| 10 | `trend_up` | trend state at T_d is "up" | T_d |
| 11 | `trend_down` | trend state at T_d is "down" (sideways = both 0) | T_d |
| 12 | `risk_atr_d` | risk (entry - stop) / daily ATR at D-1 | D-1 |
| 13 | `approach_speed_atr` | `(close[entry_idx-1] - close[entry_idx-9]) / ATR15[entry_idx-1]`, signed so positive = moving toward the zone; overnight gaps included | T_d |
| 14 | `cost_in_r_rt0.20` | `0.002 * entry_price / risk` (round-trip 0.20% in R) | T_d |
| 15 | `type_demand` | 1 demand, 0 supply | T_H |
| 16 | `nifty_above_200dma` | NIFTY close at D-1 above its 200-day mean | D-1 |
| 17 | `stock_rs63` | stock 63-bar return minus NIFTY 63-bar return at D-1 (each uses its own 63 bars) | D-1 |
| 18 | `is_0915_bar` | entry bar starts at 09:15 (33% of entries) | T_d |

**Extraction rules.** Pool selection (4,575 rows: relaxed or strict, from 2021-01-01, not corporate-action-excluded, duplicates removed). Rows that cannot be computed are *excluded with a reason*, never imputed: 20 rows with fewer than 63 prior stock bars, 3 rows whose 63-day look-back crosses a flagged
corporate action. Result: **4,552 rows, 489 tickers, no missing values.** Features are stored raw and unclipped.

**Scaling.** Not done in the dataset. Standardisation must be fit inside each walk-forward training fold only, then applied to that fold's validation and test rows (otherwise test-period statistics leak into the transform). Several features are heavy-tailed (e.g. `ltf_base_count` up to 40, `log_ltf_age_bars`, `cost_in_r`).

**Deterministic behaviour.** The runner produces a byte-identical `features.csv` on a second run; the manifest records the source file hash, code hash `cd73bf8d` and counts.

**Leakage tests** (`tests/test_phase_b_features.py`): the entry bar and entry-day daily bar can hold absurd values without changing any feature; scrambling every bar after the decision time leaves all features unchanged (with a sensitivity check proving the test would detect a leak); features recomputed on data cut at the decision
time equal the full-data values (synthetic and real tickers); a forbidden-column guard (`assert_no_forbidden`) keeps outcomes, raw price levels, identifiers and labels out of any model matrix.

---

# 9. Phase B labels (**IMPLEMENTED**)

Files: `src/ml/labels.py`, `scripts/run_phase_b_labels.py`. Output: `results/nogit-145d6302/phase_b/labels/labeled.csv` (all 4,552 rows kept, plus `label`, `label_status`, `is_training_label`, `phase_a_src_row`, `replay_check`).

| Status | Meaning | Rows | Label | Enters training? |
|---|---|---|---|---|
| **WIN** | +2R target reached before the stop | 1,229 | 1 | yes |
| **LOSS** | -1R stop reached before the target (gap stops can be worse) | 2,653 | 0 | yes |
| **AMBIGUOUS** | order of stop / target inside one bar cannot be settled, even at 1 minute (or a rule-based case) | 669 | none | **no** |
| **CENSORED** | filled, but data end before the 90-day horizon | 1 | none | **no** |
| **OPEN** | filled, nothing within 90 days | 0 | none | no |
| **NOFILL** | entry never traded | 0 | none | no |

Total 4,552; **training labels 3,882**; resolved win rate **31.66%**. By year (resolved / wins): 2021 493 / 163, 2022 642 / 187, 2023 692 / 231, 2024 696 / 224, 2025 734 / 231, 2026 625 / 193. B0 rows: 316 (256 resolved).

**Why only WIN / LOSS train the model.** Those are the only rows with a known outcome. AMBIGUOUS rows have an unknown outcome and must not be given an invented one; they are also not random (they concentrate in gap and wide-bar entries), so the evaluation reports them separately with best / worst bounds.
CENSORED, OPEN and NOFILL have no valid label. All of them stay in the file and are counted in the trading evaluation.

**Consistency check.** Every row is replayed again with the unchanged `src/replay.py` and compared with the stored Phase A fields: 4,552 of 4,552 match; the counts reconcile exactly with Phase A (the 23 rows excluded at the feature stage explain the difference). Output is byte-identical on rerun.
Labels use data after the decision time by construction; they are in `FORBIDDEN` and can never be a feature.

---

# 10. Walk-forward validation (**IMPLEMENTED**, **FROZEN**)

Files: `src/ml/splits.py`, `scripts/run_phase_b_folds.py`; output `results/nogit-145d6302/phase_b/folds/`. Expanding windows from 2021-01-01; test windows are half-years by entry time; the validation window is the last 6 calendar months of the training window; a 5-trading-day embargo (NIFTY calendar) precedes each boundary.
"Pool" = fit + validation = what the final fold model is refit on after hyperparameters are chosen. Counts are resolved trades (W / L).

| Fold | Fit period concept | Validation | Test | Fit n | Validation n | Pool n (W / L) | Test resolved (W / L) | Test embargo starts |
|---|---|---|---|---|---|---|---|---|
| 2023H1 | 2021-01-01 to 2022-07-01 | 2022-07-01 to 2023-01-01 | 2023-01-01 to 2023-07-01 | 808 | 308 | 1,123 (346 / 777) | 300 (100 / 200) | 2022-12-26 (12 rows dropped) |
| 2023H2 | to 2023-01-01 | 2023-01-01 to 2023-07-01 | 2023-07-01 to 2024-01-01 | 1,123 | 275 | 1,410 (439 / 971) | 392 (131 / 261) | 2023-06-23 (25) |
| 2024H1 | to 2023-07-01 | 2023-07-01 to 2024-01-01 | 2024-01-01 to 2024-07-01 | 1,410 | 346 | 1,781 (567 / 1,214) | 378 (121 / 257) | 2023-12-22 (46) |
| 2024H2 | to 2024-01-01 | 2024-01-01 to 2024-07-01 | 2024-07-01 to 2025-01-01 | 1,781 | 372 | 2,199 (700 / 1,499) | 318 (103 / 215) | 2024-06-24 (6) |
| 2025H1 | to 2024-07-01 | 2024-07-01 to 2025-01-01 | 2025-01-01 to 2025-07-01 | 2,199 | 303 | 2,508 (797 / 1,711) | 363 (108 / 255) | 2024-12-24 (15) |
| 2025H2 | to 2025-01-01 | 2025-01-01 to 2025-07-01 | 2025-07-01 to 2026-01-01 | 2,508 | 361 | 2,884 (913 / 1,971) | 371 (123 / 248) | 2025-06-24 (2) |

Test windows total 2,122 resolved trades (686 wins). Test windows also contain AMBIGUOUS rows (34, 74, 78, 53, 93, 55) that are never fitted but counted in the evaluation. The **purpose** of each fold is the same: train on the past only, choose settings on the most recent six months, and measure on the next six months, so the
six test windows chain into one out-of-sample stream for 2023-2025. Purge and sibling removal remove 0 rows on the real data (almost every trade exits within days and the embargo already covers it); both are exercised by synthetic tests. The 2026 holdout (781 rows) appears in no role.

**Why chronological validation is mandatory.** Candidates are not independent: 97% of tickers have several, they cluster in market regimes, and each label depends on the prices that follow. A random split would train on near-neighbours and on the future of the test trades and would overstate performance. The question
the project must answer is "given only the past, how does the filter do on the future".

**Minimum sample rules** (all folds pass): at least 300 resolved training rows, at least 180 wins (10 per feature x 18), at least 100 resolved test rows. **93 leakage checks** run on every build and all pass.

**Caveat.** Each fold's validation window equals the previous fold's test window, so hyperparameters for fold k are chosen on data that was a test window for fold k-1. This is normal for an expanding walk-forward but is a limitation to keep in mind.

---

# 11. Leakage prevention

| Protection | How it is done | Status |
|---|---|---|
| No future features | features read only bars before the entry bar and daily bars before the entry date; ATR is causal; trend uses closed bars; regime uses the previous day | IMPLEMENTED, tested (truncation and scrambling tests) |
| No future labels in training | training rows are WIN / LOSS whose outcome ended before the test boundary (purge); label columns are forbidden as inputs | IMPLEMENTED, tested |
| Train-only scaler | standardisation is fit on each fold's training rows only | PLANNED (model pipeline not written) |
| Validation threshold selection | settings (and, if adopted, the threshold) are chosen on the validation window only | PLANNED; see section 13 for the open point |
| Frozen test threshold | the model, hyperparameters and take / skip rule are fixed before test rows are scored | PLANNED |
| No test tuning | a single test pass per window; the 2026 holdout through one command that refuses a second run; every configuration tried is logged | PLANNED |
| Embargo | 5 NIFTY trading days dropped before each boundary | IMPLEMENTED, tested |
| Purge | training trades whose outcome time reaches the boundary are dropped | IMPLEMENTED, tested (synthetic; 0 occurrences on real data) |
| Sibling protection | rows of one HTF zone stay on one side of a boundary | IMPLEMENTED, tested (0 occurrences on real data) |
| Untouched 2026 holdout | 781 rows with entry on or after 2026-01-01 are in no fit, validation or test set; windows reaching 2026 are rejected | IMPLEMENTED, tested |
| Forbidden-column guard | `assert_no_forbidden` on every model matrix | IMPLEMENTED, tested |
| Shuffled-label sanity test | fit on shuffled labels; out-of-sample AUC must be near 0.5 | PLANNED |
| Corrupted-fold tests | deliberately injected leaks must make the checks fail | IMPLEMENTED, tested |

---

# 12. ML model study

Source: `docs/PHASE_B_PLAN.md` (sections 10-11), `docs/IMPLEMENTATION_PLAN.md` (Phase 5). **No model is implemented yet.**

| Model | Status |
|---|---|
| L2 logistic regression | **PLANNED**, the first baseline |
| `HistGradientBoostingClassifier` (scikit-learn) | **PLANNED**, the comparison model |
| Random Forest | **DEFERRED** ("not in the first experiment: calibration needs data we do not have") |
| LightGBM | **DEFERRED / excluded from the first experiment** (HistGradientBoosting covers the need with one dependency) |
| XGBoost | not mentioned in any repository document; not planned |
| Deep learning | **excluded** from the first experiment ("no model beyond the two chosen") |

## 12.1 Logistic regression (planned first model)
- **Purpose:** the simple, interpretable reference every other model must beat.
- **Mechanism:** it computes `z = w . x + b` from the 18 standardised features and converts it to a probability `p = 1 / (1 + e^(-z))`. The weights minimise the log-loss on the training rows plus an L2 penalty `(1/(2C)) * sum(w^2)` (scikit-learn's `C` is the inverse strength; plan: C in {0.01, 0.1, 1.0} chosen on validation log-loss, no class weights, lbfgs solver).
  Each weight is the change in log-odds per one standard deviation of that feature.
- **Strengths:** 19 parameters for 1,100 to 2,900 training rows (low variance); probabilities are well calibrated, which the take / skip rule needs; deterministic; coefficients can be read directly.
- **Weaknesses:** assumes a linear, additive effect on log-odds; cannot represent interactions or non-monotone effects unless features are hand-built (the registry is frozen); sensitive to heavy tails and to collinear features.
- **Overfitting:** low. **Interpretability:** high (standardised coefficients with bootstrap intervals).
- **Why included:** it sets the floor; if a flexible model cannot beat it, the extra complexity is not justified.

## 12.2 HistGradientBoostingClassifier (planned comparison)
- **Purpose:** the smallest step up in flexibility on the same inputs, to see whether nonlinear effects or interactions between the 18 features carry usable signal.
- **Mechanism:** it builds many small decision trees in sequence; each new tree is fit to the errors (the log-loss gradient) of the ensemble so far, and the trees' outputs are added, scaled by a learning rate. Feature values are grouped into bins first, which makes it fast. Planned settings: depth 3, at most 7 leaves, at least 50 rows per leaf,
  learning rate 0.05, L2 regularisation 1.0, at most 4 configurations (all logged), probabilities calibrated on validation (isotonic with at least 1,000 rows, otherwise Platt).
- **Strengths:** captures thresholds, interactions and non-monotone effects; no feature scaling needed.
- **Weaknesses:** needs more data to find real interactions; raw probabilities are usually miscalibrated (hence calibration); harder to interpret.
- **Overfitting:** higher than logistic regression and a real concern at this size; mitigated by shallow trees, a minimum leaf size, a small fixed grid, tuning only on validation, and logging every configuration.
- **Interpretability:** lower; planned tools after the first evaluation are permutation importance, SHAP (`shap` is not installed yet) and ALE plots.
- **Why included:** the pre-agreed comparison to logistic regression on identical data and folds.
- **Open implementation point:** the plan says "early stopping on inner validation", but scikit-learn's histogram boosting cannot take an explicit validation set (its built-in early stopping would hold out a random part of the training rows). The iteration count should instead be chosen on the chronological validation window. To be decided before coding.

Non-model comparators are also defined (section 15): the whole pool, the strict list, a random filter, and the best single old filter chosen on training data.

---

# 13. Experimental protocol (**PLANNED**)

For each model and each of the six folds, in this order:
1. **Train.** Fit the scaler (logistic regression) and the model on the fold's fit rows (WIN / LOSS only).
2. **Validate.** Score the validation window; choose the hyperparameters (logistic C or the boosting grid), and run the calibration check.
3. **Select the threshold.** Decide the probability cut-off.
4. **Freeze.** Refit on the pool if planned, then freeze the model, hyperparameters and cut-off. Log every configuration tried.
5. **Predict the test window** once. Probabilities for every test row, including ambiguous ones.
6. **Compare trading results.** Take / skip each test candidate with the frozen cut-off, evaluate the taken trades with their stored outcomes and the cost scenarios, and compare with the rule-only and random-filter results. Concatenate the six windows into one out-of-sample stream; run the 2026 holdout once at the end.

**Open point on step 3.** The repository documents the cut-off as a *fixed expected-value rule* (`docs/PHASE_B_PLAN.md`, section 8): take the trade if `2p - (1-p)L - c > 0`, i.e. `p > (L + c)/(2 + L)`, where `p` is the model probability, `L` the training mean loss in R (about 1) and `c` the round-trip cost in R. With `L = 1` and `c = 0` this is `p > 1/3`, the 2:1 break-even.
A version in which the validation window itself chooses the cut-off is *not* documented. Either is leakage-safe if fixed in advance and fitted on validation only, but they are different experiments, so the choice must be written down before the first run.

**Why the test set cannot be used for tuning.** Every setting chosen while looking at test results has been fit to those results; the test would then no longer estimate performance on unseen data, it would measure how well we searched. With about 2,100 noisy trades and many possible settings, a good-looking result is easy to find by chance. Choices are therefore made on validation, the test
is scored once, and the holdout once.

---

# 14. Metrics (**PLANNED** for the models; trading building blocks IMPLEMENTED)

**ML metrics (about the probabilities)**
- **ROC-AUC:** the chance a random WIN is scored above a random LOSS (0.5 = no information). Ranking only; ignores the cut-off and the payoff.
- **PR-AUC:** area under the precision-recall curve; its no-skill value is the base rate (about 32%), not 0.5.
- **Precision:** of the trades the model takes, the share that are WIN (the realised win rate on taken trades).
- **Recall:** of all WINs, the share the model takes.
- **Predicted-positive count:** how many trades are taken; shows whether the filter merely reduces trade count and whether the sample is large enough (the success criteria need at least 100 taken trades).
- **Brier score:** mean squared error of the probability; judged against a predictor that always says the base rate. (Log-loss and a reliability curve are also planned.)

**Trading metrics (about money; `src/portfolio.py`, `src/costs.py`)**
- **Trade count** (and take-rate, trades per year), **win rate** (with a bootstrap interval and AMBIGUOUS bounds), **expectancy** (mean R per resolved trade), **profit factor** (gross profit / gross loss in R), **total R**, **maximum drawdown** (largest peak-to-trough fall of the cumulative R curve ordered by exit time).
- **Transaction-cost scenarios:** gross, 0.10%, 0.20% and 0.30% round trip (no slippage unless set): `net R = gross R - cost_R`.

**Why accuracy alone is not the primary metric.** The classes are imbalanced (always predicting LOSS is right about 68% of the time and earns nothing); a win pays +2R and a loss -1R, with costs of 0.03 to 1.65 R per trade, so a more accurate model can still have lower expectancy; accuracy depends on one cut-off; and it ignores how many trades are taken. A better classifier only matters
if the resulting *trading strategy* improves out of sample after costs.

---

# 15. Baselines

- **Rule-only baseline.** Take every resolved candidate the rules produce: the strict list (DIT15 B0: 318 trades, 258 resolved) and the whole relaxed pool (4,575 candidates). This is the frozen Phase A result.
- **ML-filtered strategy.** The same candidates, keeping only those the frozen model and rule select. Entry, stop, target and size are unchanged; each kept trade uses its own stored outcome.
- **Random-filter control.** From the same candidates, keep a random subset of the *same size* as the ML-kept set, many times (1,000 draws, fixed seed), and compute the same metrics for each draw.

**Why the random control is necessary.** Taking fewer trades changes every number by itself: fewer trades, a different mix by year, a smaller drawdown, an average that moves up or down by luck, and in a small noisy sample random subsets of a break-even strategy vary a lot. If the ML-filtered expectancy sits inside the random subsets' range, the model has shown nothing beyond taking fewer
trades. If it sits above the 95th percentile of the random draws, the model's selection carries information that chance does not explain. A fourth comparator, the best single former filter (for example "only trend-aligned") chosen on training data, checks that the model beats a simple rule.

---

# 16. Current results vs planned results

## Completed (present in the repository)
- Phase A frozen baselines for DIT15, WIT and MIT, with cost scenarios and ambiguity counts (section 5; `docs/PHASE_A_FREEZE.md`, `PHASE_A_RESULTS.md`, `PHASE_A_MTF_RESULTS.md`).
- Old-versus-hardened comparisons: DIT15 `results/nogit-145d6302/comparison_2021/comparison_report.md` (hardening effect within bootstrap noise; the leak fix only ever blocked trades; minute data resolved ambiguity without changing win rates on the strict list) and `by_combo.md`.
- WIT and MIT hardening with exact legacy reproduction (98 of 98 and 35 of 35 trade keys) and the 13-request WIT minute fetch (10 resolved, 3 ties).
- Phase B datasets for DIT15: `tier1/features.csv` (4,552 rows x 18 columns), `labels/labeled.csv` (1,229 WIN / 2,653 LOSS / 669 AMBIGUOUS / 1 CENSORED), `folds/` (six folds, 93 leakage checks passing, all minimum sample rules passing).
- Tests (section 18).

## Not yet run
- Any model: logistic regression, HistGradientBoosting (no `models` code exists).
- Hyperparameter and calibration selection; threshold decision; shuffled-label test.
- Out-of-sample probabilities, ML metrics (AUC, PR-AUC, Brier, precision, recall) and ML-filtered trading metrics.
- The random-filter control, the best-single-filter comparison, the paired bootstrap of ML versus baseline.
- Explainability (coefficients, permutation importance, SHAP, ALE).
- The 2026 holdout run.
- Any ML on WIT or MIT.
**There is no model performance to report; any number claiming one would be fabricated.**

---

# 17. How to run the project

Only commands that exist in the repository (details in `README.md`).

```
# environment (Python 3.11)
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
copy .env.example .env                 # only for the Kite fetch scripts; never commit .env

# tests
python -m pytest                       # everything (real-data tests skip if data/cache or results are missing)
python -m pytest -m "not slow"         # fast synthetic tests only

# Phase A DIT15
python scripts/run_phase_a.py generate --label=pit
python scripts/run_phase_a.py report   --label=pit --before=results/4d02f6d/trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv

# Phase A WIT / MIT (modes: legacy | pit_trend | pit_2h (WIT) | pit)
python scripts/run_phase_a_mtf.py generate --combo=wit --mode=pit
python scripts/run_phase_a_mtf.py generate --combo=mit --mode=pit
python scripts/run_phase_a_mtf.py verify   --combo=wit        # legacy mode vs the stored pre-hardening results
python scripts/run_phase_a_mtf.py report

# comparison reports
python scripts/compare_phase_a_2021.py
python scripts/compare_by_combo.py

# minute data for ambiguous trades (read-only Kite; needs python kite_login.py first; prints the request count, stop above 1,500)
python scripts/fetch_minute_for_ambiguous.py --run=<run id> --label=<label> --dry-run

# Phase B (DIT15)
python scripts/run_phase_b_features.py     # -> results/nogit-145d6302/phase_b/tier1/
python scripts/run_phase_b_labels.py       # -> .../phase_b/labels/
python scripts/run_phase_b_folds.py        # -> .../phase_b/folds/ (exits with an error if any leakage check fails)
```
Run folders are named by a code hash, so a rebuild creates a new folder; add `--run=nogit-145d6302` or `--run=nogit-8b4a8735` to read the frozen ones. All of this needs `data/cache` (section 19). **There is no ML-experiment command yet.**

---

# 18. Testing

Organised by area (`pytest.ini`: `testpaths = tests`, marker `slow`). Real-data tests need `data/cache` and the frozen `results/` folders and skip otherwise; the `slow` ones take minutes.

| File | Tests | What it verifies |
|---|---|---|
| `tests/test_phase_a.py` | 25 | DIT15: bar close times, session-aligned 2h bars, trend without forming bars, all-time-high from known data, corporate-action reset, as-of joins, replay (win / loss / gap / ambiguity / minute drill-down / censored / open / no-fill), costs, drawdown, capital cap, replay determinism; legacy mode reproduces the stored 268-trade result, append-stability, entry-time truncation |
| `tests/test_phase_a_mtf.py` | 14 | WIT / MIT: weekly and monthly close times, unfinished final period, daily and weekly trend without forming bars, decision and replay start rules, legacy reproduction, determinism, append-stability, trend unchanged when later data is removed |
| `tests/test_phase_b_features.py` | 15 | frozen registry (18 columns), every formula, entry bar never read, no future information (scrambling and truncation), exclusions, deterministic build, dataset integrity |
| `tests/test_phase_b_labels.py` | 15 | target-before-stop, stop-before-target, gap through the stop, same-bar ambiguity, minute resolution, censored / open / no-fill, row retention, traceability, replay-check consistency, count reconciliation with Phase A |
| `tests/test_phase_b_folds.py` | 18 | embargo counts trading days, purge at both boundaries, chronology, unresolved rows never fitted, holdout never used, siblings, minimum-sample flags, row-order independence, five corrupted-fold tests that must fail, real timestamps obey every rule |
| `tests/test_base_candles.py` | 1 (30 hand-checked zone cases) | the V2 base-candle logic against the trader's annotated charts |

**Latest verified status:** full run of `python -m pytest` on 8 Oct 2026 with the data and frozen results present: **88 passed in about 3.3 minutes** (25 + 14 + 15 + 15 + 18 + 1), 0 failed, 0 skipped. Without `data/cache` the real-data tests are written to skip; that path was not exercised in this run.

---

# 19. Data, results and Git hygiene

**Never commit**
- Secrets: `.env` (API key, secret, daily access token), anything with "token" in its name. `.env.example` (empty placeholders) is the only env file that belongs in the repo. Never print, log or paste credentials.
- `data/cache/` (market data, several GB, rebuilt by the fetch scripts or shared as an archive).
- Generated or bulky artifacts covered by `.gitignore`: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.pkl`, `results/**/_ckpt/`, `results/**/rescored_*.csv`, `results/tmp/`, `*.zip`.
- Personal or third-party material covered by `.gitignore`: `*.pdf`, `*.docx`, `photos*/`, and the private or bulky parts of `legacy/handoff/handoff/` (`data/`, `old_invalid/`, `corrections/`, `golden/annotated_charts/`).

**May be committed (decided by the project owner):** code, tests, docs, and a curated set of small result files (the frozen baselines and the Phase B datasets are CSV / markdown files of a few MB each).

**Rules of the road.** The engine in `legacy/handoff/handoff/code/` is required and imported unchanged. Result folders are named by code hash and are immutable history: do not edit or overwrite them; add a new label or run instead. Kite is used only through `src/kite_client.py` (read-only): `instruments()` and `historical_data()`; never orders, positions or holdings (`CLAUDE.md`).

---

# 20. Team workflow

- **Branches.** `main` is the shared Phase A baseline branch; the ML work (Phase B) is organised on the `ml` branch, which tracks `origin/ml`. Keep ML experiments on `ml`; changes to the frozen Phase A baselines are not ML work and need a separate discussion first.
  Commits are authored by the person making them, and no tool or assistant attribution is added. This guide deliberately gives no commit or push commands: how and when to commit is the project owner's decision.
- **How the ML work is organised.** Code in `src/ml/` (registry, features, labels, splits; models and evaluation to be added there), runners `scripts/run_phase_b_*.py`, tests `tests/test_phase_b_*.py`, outputs under `results/nogit-145d6302/phase_b/`, reports in `docs/PHASE_B_*.md`.
- **Frozen contracts (do not change without a team discussion and a new baseline / version):** `src/candidates.py`, `src/candidates_mtf.py`, `src/trend_pit.py`, `src/bars.py`, `src/htf_bars.py`, `src/replay.py`, `legacy/handoff/handoff/code/`; the frozen results listed in `docs/PHASE_A_FREEZE.md`; the feature registry `tier1-v1` (`src/ml/registry.py`); the labeled dataset and fold files for the DIT15 study; the decisions D1-D7.
- **Before changing frozen Phase A logic:** write down what changes and why (correctness / leakage / reproducibility fix, or a strategy change), expect every baseline and the ML dataset to need regenerating, agree it with the project owner, and declare a new baseline. A strategy change is never justified by "it improves returns".
- **Documenting experiments.** Pre-register the plan (features, grids, decision rule, success criteria) before the first run; keep an experiment log of every configuration tried; report gross and net results, ambiguous bounds and bootstrap intervals; name the baseline compared against; record dataset and code hashes (the manifests do this); a null result is a valid, reportable result. Follow `CLAUDE.md` (raw numbers, counts that add up, train versus holdout, samples under 30 flagged).

---

# 21. Glossary

- **HTF / LTF.** Higher timeframe (bias) / lower timeframe (execution). Also a third **trend timeframe**.
- **DIT15 / WIT / MIT.** Daily-HTF / weekly-HTF / monthly-HTF combos with 15m-LTF (DIT15), 2h-LTF (WIT) and daily-LTF (MIT). "15" marks the 15-minute LTF used in the DIT variant.
- **R.** The initial risk of a trade: entry minus stop. A +2R win earns twice the risk; -1R loses it.
- **ATR.** Average true range: the typical bar range, Wilder-smoothed over 14 periods; used to measure sizes in volatility units.
- **PIT (point-in-time).** Using only information that was final at the decision time.
- **T_d, D-1, T_L, T_H.** Decision time (start of the entry bar); the last daily bar before the entry date; completion of the LTF / HTF zone.
- **BOS / CHoCH.** Break of structure / change of character (market-structure terms). **Not implemented** in this system; trend here is inferred from supply / demand zone breaks.
- **Meta-labeling.** A second model that grades the trades a primary rule-based model produces, deciding which to take, without changing the trades.
- **Walk-forward validation.** Repeatedly training on the past and testing on the next period, moving forward in time.
- **Embargo.** A gap (here 5 trading days) removed before a boundary so trades still open at the boundary do not link training and test.
- **Purge.** Removing training trades whose outcome extends to or past the boundary.
- **OOF (out-of-fold).** A prediction made by a model that did not train on that row. In this project the equivalent term is the *out-of-sample stream*: the six test windows' predictions concatenated.
- **Holdout.** Data (here from 2026-01-01) reserved for one final test and never used to make choices.
- **ROC-AUC / PR-AUC.** Area under the ROC / precision-recall curve (ranking quality).
- **Brier score.** Mean squared error of predicted probabilities against 0/1 outcomes.
- **Expectancy.** Mean R per trade.
- **Profit factor.** Total R won divided by total R lost.
- **Max drawdown.** The largest fall from a peak of the cumulative R curve.
- **AMBIGUOUS / AMBIG.** A trade whose stop / target order cannot be determined; the repository writes AMBIGUOUS.
- **B0 / B1.** The strict rule-only list / the whole relaxed pool taken without filtering.

---

# 22. Current project status

| Area | Status | Current evidence | Next planned action |
|---|---|---|---|
| Phase A (all combos) | IMPLEMENTED, FROZEN | `docs/PHASE_A_FREEZE.md` | none; discuss before any change |
| DIT15 | FROZEN | `results/nogit-145d6302/phase_a/pit_refetch/` (318 strict, 258 resolved, +0.046 R gross) | none |
| WIT | FROZEN | `results/nogit-8b4a8735/phase_a_mtf/wit/pit/` (111 trades, 105 resolved, +0.144 R) | none (ML DEFERRED) |
| MIT | FROZEN | `results/nogit-8b4a8735/phase_a_mtf/mit/pit/` (36 trades, 34 resolved, +0.545 R) | none (ML DEFERRED) |
| Feature pipeline | IMPLEMENTED, tested, registry FROZEN | `src/ml/features.py`, `tier1/features.csv` (4,552 x 18), 15 tests | none |
| Labels | IMPLEMENTED, tested | `labels/labeled.csv` (3,882 training labels), 15 tests | none |
| Walk-forward folds | IMPLEMENTED, tested, FROZEN | `folds/` (6 folds, 93 checks), 18 tests | none |
| Logistic Regression | PLANNED, not implemented | `docs/PHASE_B_PLAN.md` sections 10-12 | write the pipeline; settle the threshold procedure |
| Other model comparison | PLANNED (HistGradientBoosting); DEFERRED (Random Forest, LightGBM); deep learning excluded | `docs/PHASE_B_PLAN.md` section 11 | after logistic regression; settle the boosting iteration selection |
| Evaluation vs baselines and random filter | PLANNED; metric code IMPLEMENTED | `src/portfolio.py`, `src/costs.py` | write the evaluation and random-filter code |
| 2026 holdout | untouched (781 rows unused) | folds manifest | run once, after the design is frozen |
| Documentation | IMPLEMENTED | `README.md`, `docs/PHASE_A_FREEZE.md`, `docs/PHASE_B_*.md`, `IMPLEMENTATION_PLAN.md`, `ML_BACKEND_EXPLAINED.md`, this guide | update this guide when models and results exist |

---

# 23. If you are new to this project

1. `README.md`: setup, data, tests, commands.
2. `docs/PHASE_A_FREEZE.md`: what is frozen and the decisions D1-D7; then `docs/PHASE_A_RESULTS.md` and `docs/PHASE_A_MTF_RESULTS.md`.
3. Phase A source, in this order: `config.py`, `docs/RULES.md` (the strategy in the trader's words), `legacy/handoff/handoff/code/sd_zones.py` (zones), `mtf_zones.py` (matching and trend), then `src/bars.py`, `src/trend_pit.py`, `src/candidates.py`, `src/replay.py`.
4. `src/ml/registry.py`: the feature contract.
5. `src/ml/features.py`.
6. `src/ml/labels.py`.
7. `src/ml/splits.py`.
8. The tests, starting with `tests/test_phase_b_folds.py` (the corrupted-fold tests show what each protection is for) and `tests/test_phase_b_features.py`.
9. ML experiment documentation: `docs/ML_BACKEND_EXPLAINED.md` (long explanation), `docs/PHASE_B_PLAN.md` (the design), `docs/IMPLEMENTATION_PLAN.md` (the whole roadmap), then the three `docs/PHASE_B_*_REPORT.md`.

---

# 24. One-page mental model

```
RULE ENGINE  = generates candidate trades (entry, stop, 2R target, size are already decided here)
FEATURES     = describe each candidate using only what was known at its decision time (18 numbers)
LABEL        = tells what actually happened afterwards (WIN / LOSS; everything unclear is left out of training)
WALK-FORWARD = simulates realistic future prediction: train on the past, tune on the latest months, test on the next window
MODEL        = estimates candidate quality (probability of reaching +2R before -1R)
THRESHOLD    = decides which candidates to keep
BACKTEST     = checks whether filtering improves trading performance after costs, against taking everything and against a random filter
HOLDOUT      = final untouched reality check (2026), used once
```
Remember: ML only chooses among the rules' trades, nothing else; and a null result ("the filter adds nothing") is a perfectly valid outcome.
