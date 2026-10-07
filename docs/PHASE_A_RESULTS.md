# PHASE_A_RESULTS.md: hardened DIT15 baseline (B0) and relaxed candidate pool (7 Oct 2026)

Plan: docs/PHASE_A_PLAN.md. Scope: DIT15 only (HTF daily / trend 2h / LTF 15m, rule set of results/4d02f6d), entries 2021-01-01 to
2026-10-01, 503 tickers, frozen Kite frames (`data/cache/kite_frames_dit15_long`), offline. No ML. No commit.
Result files: `results/nogit-145d6302/phase_a/{pit,legacy,A1}/candidates.csv` + `report.txt` (the run id is a code hash because
the folder is not a git repo; see src/runinfo.py). Reports: `python scripts/run_phase_a.py report --run=nogit-145d6302 --label=pit`.

## 1. What was changed

| Fix | Class | Where | Effect on DIT15 B0 |
|---|---|---|---|
| A1 Trend zone-break events stamped at the breaking bar's **close**; trend queries use only bars **closed** by the query time (legacy: bar label = start, `timestamp <= T`, so a forming 2h bar was used at the entry) | leakage | src/trend_pit.py, src/bars.py | see sec. 3 |
| A1 Trend check at HTF formation keeps the legacy time (HTF bar label = information through the previous day's close); with A1 it now uses closed bars only. The T_H (15:30) variant is a strategy change and is **not** applied (decision D1) | correctness / no silent rule change | src/candidates.py `Mode.formation_at_close` | 0 by construction |
| A2 2h trend bars anchored to the NSE session: 09:15-11:15, 11:15-13:15, 13:15-15:15, 15:15-15:30 stub (TradingView convention), explicit close times (legacy: clock-hour bins 08:00/10:00/12:00/14:00) | correctness | src/bars.py | see sec. 3 |
| A3 ATH override compares with every close known at T (closed trend bars + daily closes since 2012), not the max of the trend frame (which started 2020-11) | correctness | src/trend_pit.py | 0 trades on the 40-ticker sample; included in the full-run difference |
| A4 No end-anchored windows; frames start at their first bar | reproducibility | src/bars.py | 0 for DIT15 (the 4d02f6d run had already lifted its windows); append-stability test added |
| A5 Regime as-of: daily value from D-1 for an intraday decision | leakage | src/asof.py; scripts/regime_test.py (one line, was `side="right"`, used the entry day's close) | analysis script only, not in B0 |
| A6 Abnormal daily moves (> 35 % close to close) flagged; a trade whose [HTF base start - 30 days, exit / horizon end] contains one is excluded and listed; trend and ATH ignore prices before a flag | data quality | src/corp_actions.py | 3 B0 trades excluded (HEGAM x2, POLICYBZR, all Sept 2026) |
| A7 Offline deterministic replay, outcome classes WIN / LOSS / AMBIGUOUS / OPEN / CENSORED / NOFILL, explicit 90-day horizon, 1m drill-down only from cached minute data, missing-intraday-bar days checked against the daily bar | realism / determinism | src/replay.py | the heuristic fallback is gone from the headline; AMBIGUOUS stays AMBIGUOUS |
| A8 Cost model: per-side %, itemised fields, lumped scenarios 0.10 / 0.20 / 0.30 % round trip, slippage per side (0 unless set) | realism | src/costs.py | gross and net R reported |
| A9 Deterministic sequencing (exit time, fill time, ticker), R and rupee drawdown, concurrency, deterministic capital-capped variant | realism | src/portfolio.py | new metrics |
| One orchestrator for strict B0 + relaxed pool, legacy-compatible mode | testability | src/candidates.py, scripts/run_phase_a.py | |
| Run id without git | reproducibility | src/runinfo.py | |
| Below-normal priority actually applied (the old `SetPriorityClass` call always failed: handle truncated to 32 bit) | ops | scripts/run_phase_a.py | the older runners still have the bug |
| Minute fetch script for MINUTE_NOT_CACHED trades (not run: kiteconnect is not installed here) | data | scripts/fetch_minute_for_ambiguous.py | |

Verification of the new orchestrator: **legacy mode reproduces 4d02f6d exactly**: 503 tickers, 268 trades, and the offline replay
gives the same outcome classes as the old Kite replay (W 75 / L 151 / AMBIGUOUS 42; identical on every trade).

## 2. What was deliberately NOT changed
Zone detection and construction (sd_zones, base logic V2, caps, Rule 1, legout-over-wick, strict HTF), matching (formation window,
untested at confirm, 30 % overlap, most recent candidate), wick-freshness (already point-in-time for a daily HTF), the trend state
machine and asymmetric filter, entry at the proximal on first touch, stop at the distal, 2:1 target, sizing (Rs 1,000 risk, Rs 1L
notional cap, no leverage), no time exit. Legacy files, config.py, base_candles.py, exits.py, kite_client.py are untouched.
WIT / MIT / QIT were not re-run.

## 3. Before vs after (DIT15, entries 2021-01-01 .. 2026-10-01, gross, metrics on WIN+LOSS)

"Before" = the 4d02f6d rule set run through the new orchestrator in legacy mode (identical trades and replay classes to the old
files). "After" = B0, point-in-time mode (A1-A4, A6), 3 corporate-action trades excluded.

| | Before (legacy) | After (B0) |
|---|---|---|
| Trades | 268 | 318 (+3 CA-excluded) |
| WIN / LOSS / AMBIGUOUS | 75 / 151 / 42 | 79 / 145 / 94 |
| OPEN / CENSORED / NOFILL | 0 / 0 / 0 | 0 / 0 / 0 |
| Win rate (resolved), bootstrap 95 % | 33.2 % [27-39] | 35.3 % [29-42] |
| Win rate if all AMBIGUOUS lost .. won | 28.0 .. 43.7 % | 24.8 .. 54.4 % |
| Expectancy, gross R/trade | -0.020 | +0.043 |
| Profit factor, gross | 0.97 | 1.06 |
| Total R, gross | -4.5 | +9.6 |
| Max drawdown, R | 31.3 | 27.3 |
| Expectancy net, rt 0.10 / 0.20 / 0.30 % | -0.189 / -0.358 / -0.526 | -0.117 / -0.278 / -0.438 |
| Total R net rt 0.20 % | -80.8 | -62.2 |
| Capital-capped (Rs 1L): taken, expR gross / rt0.20 | 254, +0.024 / -0.316 | 298, +0.045 / -0.274 |
| Rupees gross (all signals), max DD | +Rs 3,623, Rs 19,310 | +Rs 10,804, Rs 17,946 |
| Max concurrent positions / peak notional | 3 / Rs 2.91L | 3 / Rs 2.91L |
| Train (<2026) / holdout win rate | 33.1 % / 33.3 % | 34.6 % / 38.5 % (n = 39 resolved) |

Win-rate difference after - before: +2.1 pts, bootstrap 95 % [-6.8, +10.6]: **no evidence of a change**. Both baselines are at or below
the 33.3 % break-even of a 2:1 trade and **negative after every cost scenario**.

B0 by year (gross; AMBIGUOUS excluded from win%):

| Year | Before n / win% / expR | After n / win% / expR | After AMBIGUOUS |
|---|---|---|---|
| 2021 | 29 / 44.4 / +0.336 | 42 / 44.1 / +0.336 | 8 |
| 2022 | 40 / 34.3 / +0.037 | 50 / 28.9 / -0.129 | 12 |
| 2023 | 52 / 40.5 / +0.214 | 48 / 42.9 / +0.286 | 13 |
| 2024 | 51 / 31.0 / -0.153 | 68 / 31.8 / -0.123 | 24 |
| 2025 | 41 / 17.1 / -0.481 | 47 / 26.5 / -0.202 | 13 |
| 2026 | 55 / 33.3 / -0.013 | 63 / 38.5 / +0.139 | 24 |

Trade-level attribution (full universe, B0 incl. CA-excluded):

| Step | Trades | Kept | Removed | Added | Why |
|---|---|---|---|---|---|
| legacy -> A1 (trend at bar close, closed bars only) | 268 -> 326 | 268 | 0 | 58 | All 58 were blocked by trend-at-entry computed from a 2h bar that was still forming. The leak only ever removed trades: during the pull-back into a zone the forming bar breaks zones against the trade. 41 of the 58 are AMBIGUOUS (no cached minute data) |
| A1 -> B0 (session 2h, full-history ATH, CA reset) | 326 -> 321 | 234 | 92 | 87 | Different 2h bars give different trend zones and breaks. ATH and CA reset changed nothing on the 40-ticker sample, so this churn is the 2h convention |
| legacy -> B0 overall | 268 -> 321 | 201 | 67 (17 W / 43 L / 7 AMB) | 120 (21 W / 37 L / 62 AMB) | On the 201 kept trades the outcome class is identical |

Not applied (decision D1): trend at formation queried at T_H (15:30) instead of the bar label. On the 40-ticker sample it adds 7 B0
trades (35 -> 42: 5 losses, 1 win, 1 ambiguous) and removes none.

Reproducibility: the full run and an independent rerun of 40 tickers with the final code gave identical rows (trades, outcomes,
R, trend states).

## 4. Data limitations
- **Survivorship**: universe = the live Sept-2026 list (503 tickers); delisted names are absent. Biases absolute results up; it
  affects baseline and any later filter equally.
- **Corporate actions**: Kite frames are split/bonus adjusted (checked: NESTLEIND, TATASTEEL, IRCTC splits show no gap; STATUS.md
  sec. 7's "unadjusted" note is wrong). 28 abnormal moves in 24 tickers remain (listing-day artifacts, demergers: ABFRL 2025-05-22,
  HEGAM 2026-09-07, POLICYBZR 2026-09-24, ...). Demerger price adjustments smaller than 35 % (e.g. TMPV, R32) are not detected.
- **Missing intraday data**: from 2026-08-03 every day lacks the 15:15 bar (15m and 60m), also in the raw Kite cache. Handled by the
  INTRADAY_DATA_GAP rule (1 B0 trade, 14 pool candidates); 2h bars of those days end at 15:15.
- **Minute data**: 1-minute bars exist only where earlier runs fetched them (237 tickers, specific windows). Ambiguous 15m bars without
  cached minutes stay AMBIGUOUS (MINUTE_NOT_CACHED): 51 of 318 B0 trades, 1,409 of 4,575 pool candidates.
- **Trend history** starts 2020-11 (60m data); trend states early in 2021 rest on few zone breaks.
- **Gross of costs** in the legacy numbers; net numbers depend on the unconfirmed cost scenario.
- Daily bars and 15m bars disagree slightly on many complete days (daily high above the 15m max on ~20 % of RELIANCE days, likely
  auction prices); only days with missing 15m bars are checked against the daily bar.

## 5. Relaxed candidate pool (A11/A12)
Same zones and matching. Former filters recorded as flags: trend at formation, trend at entry, HTF wick-freshness, strict-HTF
legout, HTF base cap 5, LTF base cap 5. One row per HTF zone (best LTF zone); B0 rows that relaxed matching would not pick (6,
"displaced") are kept too. 2 duplicate orders removed, 5 corporate-action exclusions.

| Year | Strict B0 | Relaxed | x | WIN | LOSS | AMBIGUOUS | resolved |
|---|---|---|---|---|---|---|---|
| 2021 | 42 | 551 | 13.1 | 102 | 249 | 200 | 351 |
| 2022 | 50 | 720 | 14.4 | 134 | 347 | 239 | 481 |
| 2023 | 48 | 804 | 16.8 | 161 | 345 | 298 | 506 |
| 2024 | 68 | 831 | 12.2 | 157 | 356 | 318 | 513 |
| 2025 | 47 | 886 | 18.9 | 165 | 406 | 315 | 571 |
| 2026 | 63 | 783 | 12.4 | 138 | 342 | 302 | 480 (1 CENSORED) |
| **Total** | **318** | **4,575** | **14.4** | 857 | 2,045 | 1,672 | 2,902 |

- Tickers with >= 1 candidate: 490 of 503; median 9 per ticker, max 22 (INDIANB). Demand 2,919 / supply 1,656.
- Former-filter flags (True = strict would reject): trend at formation 1,380, trend at entry 2,005, wick-freshness 2,469, strict-HTF
  834, HTF cap 1,692, LTF cap 1,573. Candidates by number of failed filters: 0: 318, 1: 1,044, 2: 1,463, 3: 1,151, 4: 477, 5: 110, 6: 12.
- Pool, resolved only, gross: win 29.5 % [28-31], expR -0.114, PF 0.84. (Descriptive only: no filter was tuned on this.)
- AMBIGUOUS reasons: MINUTE_NOT_CACHED 1,409, gap-fill opens beyond the stop 172, target in fill bar 45, stop+target in fill bar 32,
  INTRADAY_DATA_GAP 14. Fetching the missing minute data needs **1,450 Kite requests** (one per symbol-day; under the 1,500 limit),
  B0 alone 57: `python scripts/fetch_minute_for_ambiguous.py --run=nogit-145d6302 --label=pit --dry-run`.

Size verdict: the pool is large enough for the planned experiment (about 1,590 resolved candidates in 2023-2025 alone), so this is
not a STOP. But **36 % of candidates are unlabelled**, which is a problem for Phase B (sec. 7).

## 6. Remaining problems
1. **Unlabelled candidates**: 1,409 pool / 51 B0 MINUTE_NOT_CACHED. kiteconnect is not installed on this machine, so no fetch was run.
2. **Unresolvable by rule**: "gap-fill opens beyond the stop" (172 pool / 15 B0) stays AMBIGUOUS under the legacy rule. A realistic
   treatment (the limit order fills at the open below the stop, the stop triggers at once, R about 0 minus costs) would be a rule
   change, so it needs a decision (D4).
3. Decisions D1 (T_H timing), D2 (2h convention) are open; B0 depends on them.
4. WIT / MIT / QIT not hardened: weekly/monthly HTF bars (labels Sunday / month-end), the 2h LTF of WIT, and their 400/750-bar
   end-anchored windows (A4) still apply to their runners.
5. Older runners: `git rev-parse` (fails here), non-working low-priority call. Not edited (frozen).
6. The CA rule misses adjustments under 35 % (e.g. demergers like TMPV); the universe is survivorship-biased.
7. A full DIT15 run takes about 45 minutes (8 workers); much longer when the CPU is throttled (this run saw ~18 % clock).
8. docs/STATUS.md still says Kite prices are unadjusted (wrong for splits/bonuses) and still lists the old baselines; not edited
   pending approval (CLAUDE.md: report only).

## 7. Readiness for Phase B
**Mechanically ready, not label-ready.**

Ready:
- The candidate generator is point-in-time (truncation and forming-bar tests pass).
- It is deterministic and append-stable.
- It reproduces the legacy pipeline exactly in legacy mode.
- It emits one row per candidate with decision times (T_H, T_L, T_d), flags and outcome classes.

Not ready:
- 36 % of the pool is AMBIGUOUS, mostly for lack of minute data. Dropping those rows would bias the dataset: ambiguity comes from
  wide 15m bars and gaps, which correlate with volatility features.
- Recommended before Phase B: run the 1,450-request minute fetch, re-score, and settle D1/D2/D4.

Tests: `python -m pytest tests/test_phase_a.py` (20 synthetic + 5 real-data, all pass);
`python tests/test_base_candles.py` (0 unexpected failures, unchanged).
