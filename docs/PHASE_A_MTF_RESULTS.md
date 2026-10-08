# PHASE_A_MTF_RESULTS.md: WIT and MIT hardening (8 Oct 2026)

Same methodology as DIT15 (docs/PHASE_A_PLAN.md, PHASE_A_RESULTS.md), strict B0 lists only (no relaxed pool for WIT / MIT).
DIT15 baseline files, `src/candidates.py`, `trend_pit.py`, `bars.py`, `replay.py` and all legacy code are unchanged.
Full tables: `results/nogit-8b4a8735/phase_a_mtf/hardening_report.md`. Rebuild per combo and mode:
`python scripts/run_phase_a_mtf.py generate --combo=wit|mit --mode=legacy|pit_trend|pit_2h|pit`, then `report`.
Run id = hash of the Phase A code plus the runner (no git call).

## What was wrong (WIT / MIT versus the DIT15 standard) and what changed

| Issue | WIT | MIT | Fix |
|---|---|---|---|
| Trend look-ahead: events stamped with the bar label, `timestamp <= query` | **yes**: daily trend bar and its zone breaks of the entry day visible at the entry | no: weekly labels are Sundays, so only closed weeks were seen (the break stamps are still labels) | closed-bar trend (`trend_pit`): events at the bar close, queries use bars closed by the decision time |
| Weekly / monthly HTF close time unknown (label = Sunday / month-end midnight, a month-end label is earlier than that day's 15:30 close) | yes | yes | `src/htf_bars.py`: legacy grouping kept, explicit `close_time` = last trading day 15:30, unfinished final period never closed |
| 2h LTF on clock-hour bins (08:00 / 10:00 ... , first bin one hour) | **yes** | n/a (daily LTF) | session-aligned 09:15 bins with 15:15 stub (D2) |
| All-time-high from a trimmed frame | yes (daily trend) | yes (weekly trend, last 400 bars) | all closes known at the decision time |
| End-anchored windows (WIT weekly HTF last 400 bars; MIT weekly trend last 400 bars) | yes | yes | fixed start (full history), append-stable (tested) |
| No corporate-action handling | yes | yes | flag + exclusion + trend/ATH reset (same rule as DIT15) |
| Replay start and decision time not defined | yes | yes | decision time T_d = start of the entry 2h bar (WIT) / entry day 09:15 (MIT); replay from there with the unchanged `src/replay.py`, 90-day horizon, six outcome classes |
| Run metadata via `git rev-parse` | yes | yes | code-hash run id |

Unchanged on purpose (strategy rules): trend check at HTF formation queried at the HTF bar label (D1), V2 base logic cap 5, legout-over-wick, wick-freshness, matching, 2:1 target, sizing.
New code: `src/htf_bars.py`, `src/candidates_mtf.py`, `scripts/run_phase_a_mtf.py`, `tests/test_phase_a_mtf.py`.

## Verification
Legacy mode reproduces the stored 2021+ results exactly across the full universe: **WIT 98 of 98 trades identical, MIT 35 of 35**
(trade keys). Tests: 14 new (period-bar close times and incomplete periods, daily and weekly trend without forming bars,
decision and replay-start rules, 2h conventions, legacy reproduction, determinism, append-stability, trend states unchanged when
later data is removed). All pass; Phase A and Phase B suites still pass (87 in the last full run before the final test fix).

## Results (entries from 2021-01-01, gross; resolved = WIN + LOSS)

| | Trades | W / L / Ambig. | Win rate | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| WIT before (stored, replay-only) | 98 | 34 / 54 / 10 | 38.6% | +0.181 | 1.30 | +15.9 | 11.0 |
| WIT legacy re-scored | 98 | 34 / 55 / 9 | 38.2% | +0.166 | 1.27 | +14.8 | 11.0 |
| **WIT hardened (after the 13-request minute fetch)** | 111 | 40 / 65 / 6 | 38.1% | +0.144 | 1.23 | +15.2 | 9.0 |
| MIT before (stored, replay-only) | 35 | 17 / 16 / 2 | 51.5% | +0.501 | 1.94 | +16.5 | 5.2 |
| MIT legacy re-scored | 35 | 17 / 16 / 2 | 51.5% | +0.501 | 1.94 | +16.5 | 5.2 |
| **MIT hardened** | 36 | 18 / 16 / 2 | 52.9% | +0.545 | 2.05 | +18.5 | 5.2 |

Both changes are inside the bootstrap noise (expectancy change WIT [-0.45, +0.40] R, MIT [-0.69, +0.79] R).

WIT attribution: the trend leak fix alone **added** 16 trades (the leak only blocked trades) and lowered expectancy by 0.10 R;
session-aligned 2h bars replace every LTF zone line (0 of 114 trades stay identical) and move expectancy by +0.08 R; ATH, corporate
actions and fixed start change nothing. The headline WIT change (legacy to hardened: -0.1 points win rate, -0.022 R) is therefore a
change of which trades are selected, not an improvement or a deterioration. MIT attribution: the leak fix changes nothing (weekly labels were already safe); ATH / full
history adds one winning trade.

Cost scenarios (expectancy R, hardened; round trip 0.10 / 0.20 / 0.30%): WIT +0.069 / -0.007 / -0.083, MIT +0.514 / +0.483 / +0.452.
WIT is about break-even at 0.20% and negative at 0.30%; MIT stays positive (n = 34).

## Ambiguity
- WIT hardened: 6 AMBIGUOUS: target in fill bar 5, stop+target in fill bar 1. A fetch of the 13 `MINUTE_NOT_CACHED` cases (13 read-only requests, 8 Oct 2026) resolved 10 of them (5 WIN, 5 LOSS) and left 3 as genuine ties at 1-minute resolution (target in the fill minute). No previously resolved trade changed. The pre-fetch WIT results are kept in `phase_a_mtf/wit_prefetch/`.
- MIT hardened: 2 AMBIGUOUS, both "gap-fill opens beyond the stop" (kept ambiguous by D4); 0 minute requests needed.
- No OPEN, CENSORED or NOFILL trades in either.
- Corporate-action exclusions: 0 trades in both.

## Remaining limitations
- Samples are small (95 resolved WIT, 34 MIT): no statistical conclusion; ML on them alone is not viable.
- Survivorship (current universe), corporate-action moves under 35% undetected, 15:15 bar missing since 2026-08-03 (affects WIT's last 2h bin), 2026 partly contaminated by chart reviews.
- No relaxed pool exists for WIT / MIT.
- HTF formation trend query still uses the bar label (stale, not leaking; D1).
- Because new files live in `src/`, the code hash changed: future reruns of DIT15 get a new run-id folder; the frozen DIT15 baseline files are untouched.

## Freeze readiness
MIT: ready to freeze (exact legacy reproduction, no leak found beyond label stamps, no outstanding data). WIT: ready to freeze (minute fetch done; 6 residual ambiguous trades are by rule or true 1-minute ties).
