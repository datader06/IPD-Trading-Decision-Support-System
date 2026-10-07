# PHASE_A_PLAN.md: harden and validate the existing rule-based system (written 7 Oct 2026, before any behaviour change)

Scope: correctness, leakage, reproducibility and backtest realism. No ML, no strategy redesign, no threshold tuning.
Primary combo: **DIT15** (HTF daily, trend 2h from 60m, LTF 15m; the 2021+ strict-HTF run in results/4d02f6d is the "before").
WIT / MIT / QIT are not re-run in Phase A (see "Out of scope").

## 1. Current architecture (as found)

| Stage | Where | Notes |
|---|---|---|
| Data | `data/cache/kite_frames_dit15_long/{T}__{1d,60m,15m}.csv` (1d from 2012, 60m/15m from 2020-11, end 2026-10-01) | Frozen frames. No volume. The `kiteconnect` package is **not installed** on this machine, so everything must run offline. |
| Loader | `legacy/.../offline_loader.py` patches `mtf_zones._fetch` | |
| Frames | `mtf_zones._build_frame` (`_resample`, `iloc[-window:]`) | |
| Zones | `sd_zones.detect_zones` + `src/base_candles.install` (V2 base logic, monkey patch) | |
| Trend | `mtf_zones._compute_trend_events`, `_classify_trend_from_events`, `filter_zones_by_trend_3tf` | |
| Matching | `mtf_zones.match_zones` (window, untested-at-confirm, 30 % overlap, wick-freshness, trend at entry) | |
| Trade | `mtf_backtest.build_trades_for_ticker` (entry = LTF proximal at first touch, stop = distal, 2R, shares = min(1000/risk, 1e5/entry)) | |
| Exit | heuristic `mtf_backtest.simulate_exit`; then `src/exits.replay_trade` (Kite 15m, then 1m) via `scripts/replay_common.py` | |
| Runners | DIT15 `scripts/run_dit15_long.py` (2021+) / `run_dit15_kite.py` (2024+) + `run_dit15_replay.py`; WIT `run_wit_kite.py` + `_replay`; MIT `run_mit_kite.py` + `_replay`; QIT `run_qit_kite.py` + `_replay` | Each uses `git rev-parse` to name the results folder, and this folder is **not a git repo**. |
| Reporting | `replay_common.report/block` (years, train/holdout, bootstrap, SAMPLE<30) | |
| Tests | `tests/test_base_candles.py` (30 golden zone cases), `tests/golden/*.csv`, legacy `golden/run_golden_checks.py` | |

## 2. Frozen files (will NOT be edited)
`legacy/**` (sd_zones, mtf_zones, mtf_backtest, offline_loader), `src/base_candles.py`, `config.py` (editing it would also wipe the existing
checkpoint folders, whose signature is md5(config.py + base_candles.py)), `src/exits.py`, `src/kite_client.py`, all existing runners and results.
The zone logic is reused **by import**, unchanged.

## 3. New files (Phase A)

| File | Purpose |
|---|---|
| `src/runinfo.py` | Run id = git short hash if available, else `nogit-<content hash of code>`; results folder |
| `src/bars.py` | Frame loading with a fixed start (no end-anchored windows), explicit `close_time` per bar, session-aligned 2h bars, intraday-completeness check |
| `src/asof.py` | Point-in-time helpers (bars closed by T; daily value as of D-1) |
| `src/trend_pit.py` | Trend events stamped with the break bar's close time; trend query using closed bars only; ATH from all closed history |
| `src/corp_actions.py` | Flag abnormal daily moves (corporate-action windows) |
| `src/replay.py` | Offline deterministic replay: 15m frames, 1m drill-down from the minute cache, outcome classes, 90-day horizon |
| `src/costs.py` | Configurable cost/slippage model, gross and net R |
| `src/portfolio.py` | Deterministic sequencing, drawdown, concurrency, capital-constrained variant |
| `src/candidates.py` | One candidate generator: legacy-compatible mode (reproduces the old pipeline) and point-in-time mode; strict (B0) and relaxed flags |
| `scripts/run_phase_a.py` | Runner: generate / replay / report, per-ticker checkpoints, low priority, workers <= half the cores |
| `tests/test_phase_a_*.py` | Regression tests (section 6) |
| `docs/PHASE_A_RESULTS.md` | Results |

Changed (small, justified): `scripts/regime_test.py`: as-of bug (A5), one line, uses `src/asof.py`.

## 4. Planned fixes

| # | Fix | Why (class) | Expected impact |
|---|---|---|---|
| A1a | Trend events stamped at the **close** of the breaking trend bar (not its label = start) | Leakage: a 2h bar labelled 10:00 (10:15-12:15) is used at a 10:30 entry | Some trades flip between allowed/blocked |
| A1b | Trend query uses only trend bars whose close time <= T. **Revised during A1**: the formation check keeps the legacy query time (bar label = information through the previous day's close; stale, not leaking). Moving it to T_H changed 9 of 27 sample trades, which is a strategy change, so it is a switch (`--formation-at-close`) awaiting the user's decision | Leakage / no silent rule change | None by default |
| A1c | Entry bar: no decision uses the entry bar's H/L/C (audit; the replay fill logic is unaffected) | Leakage audit | Expected none |
| A2 | 2h bars anchored to the NSE session: 09:15-11:15, 11:15-13:15, 13:15-15:15, 15:15-15:30 stub (TradingView convention); explicit start/end; only closed 2h bars used | Correctness: legacy clock-hour bins (08:00 bin = one 09:15 hour; label before the open) | Trend zones on 2h change, so trend states change. **Changes bar boundaries the user sees.** Convention to confirm. |
| A3 | ATH = last closed trend close >= max of all closes closed before T (daily history from 2012 plus closed trend bars), reset after a flagged corporate-action event | Correctness: "all-time" was "since frame start (2020-11)" | ATH override fires less often in 2021-22 |
| A4 | No `iloc[-window:]`: frames start at a fixed date (frame start) | Reproducibility | None for DIT15 2021+ (its windows were already lifted); matters for WIT/MIT |
| A5 | Regime as-of: daily value from D-1 for intraday entries | Leakage (regime_test.py used the entry-day close) | Analysis script only; not in B0 |
| A6 | Flag days with \|close/prev close - 1\| > 35 %; exclude a trade if [HTF base start, exit or horizon end] contains one; trend events/ATH reset after one. Finding: **Kite frames ARE split-adjusted** (NESTLEIND 2024-01, TATASTEEL 2022-07, IRCTC 2021-10 show no gap), contrary to STATUS sec. 7; remaining events are listing artifacts and demergers | Data quality | A few trades excluded, listed in the report |
| A7 | Offline deterministic replay; classes WIN / LOSS / AMBIGUOUS / OPEN / CENSORED / NOFILL; 90-day horizon explicit; AMBIGUOUS never converted; 1m drill-down only from cached minute data (otherwise AMBIGUOUS, MINUTE_NOT_CACHED); days with missing intraday bars (15:15 bar missing since 2026-08-03) checked against the daily bar | Realism / determinism | The heuristic fallback used in old baselines is dropped from headline numbers (shown separately) |
| A8 | Cost model: per-side % (brokerage, exchange, taxes) + slippage; scenarios 0.10 / 0.20 / 0.30 % round trip (0.20 % is the figure in DECISIONS Record B; 0.10/0.30 are the user's sensitivity bracket); gross and net R | Realism | Net R reported next to gross |
| A9 | Deterministic sequencing (ties: exit time, fill time, ticker); R drawdown; concurrency; capital-capped variant (Rs 1L, Rs 1,000 risk, no leverage) | Realism / determinism | New metrics only |
| A10 | Re-baseline B0 (DIT15 2021+, V2 cap 5, legout-wick, strict HTF = the 4d02f6d rule set) | | |
| A11 | Relaxed pool: hard = zone detection/construction (incl. Rule 1, HTF legout-over-wick), matching; flags = trend at formation, trend at entry, HTF wick-freshness, strict-HTF, HTF/LTF base cap 5 | | |
| A12 | Candidate counts by year/ticker, strict vs relaxed | | |

Method per fix: every point-in-time change is a switch in `src/candidates.py`. Mode `legacy` (all switches off) must reproduce the
4d02f6d trades exactly (proves the new orchestrator is faithful). The switches are then turned on one at a time on a sample of tickers,
and every changed trade is counted and attributed before the full run.

## 5. Out of scope / deliberately unchanged
Zone detection rules and thresholds, base-candle logic, matching rules, the 2:1 target, sizing (Rs 1,000 risk / Rs 1L), no time exit
(OPEN stays OPEN), HTF wick-freshness date rule (already point-in-time for a daily HTF). WIT/MIT/QIT re-baselines (their weekly/monthly
HTF timing and 2h LTF need the same treatment; listed in the results).

## 6. Tests
1. Forming-bar leakage (synthetic 2h break inside a forming bar).
2. Entry-bar H/L/C cannot change decisions (truncate data at T_d, recompute).
3. Daily D cannot leak into intraday D (as-of).
4. 2h session alignment: normal day, first/last bar, stub, partial day, entry inside a forming 2h bar.
5. Append-stability: candidates with entry < X identical on data cut at X and on full data.
6. ATH uses no future data.
7. Regime join point-in-time.
8. Replay deterministic (same input, same output; golden synthetic cases).
9. AMBIGUOUS stays AMBIGUOUS.
10. NOFILL counted.
11. Cost deterministic.
12. Candidate generation deterministic, plus legacy-mode reproduction of the 4d02f6d checkpoints.
Existing `tests/test_base_candles.py` must still pass.
