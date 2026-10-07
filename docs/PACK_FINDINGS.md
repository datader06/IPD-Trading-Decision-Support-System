# PACK_FINDINGS.md — findings from the user's review of the handoff pack (2 Oct 2026)

a) Baselines (DIT 207 / 31.4% / -Rs 12,221; WIT 25 / 24.0% / -Rs 7,313; MIT 22 / 40.9% / +Rs 4,908) recompute exactly from results/*_FIXEDEXIT.csv. Same-candle = holding_bars == 0 (DIT 117 trades, 28 wins; other 90 won 37).

b) Baseline P&L is GROSS: no brokerage, tax or slippage. The column "cost" is shares x entry price (capital deployed), not a trading cost.

c) Baselines are NOT capital-capped: DIT has up to 4 concurrent trades, peak about Rs 3.5L deployed. The "Rs 1L cap came from the old run" statement is wrong.

d) Bootstrap 95% win-rate intervals: DIT 25-38% (contains the 33.3% break-even), WIT 8-44%, MIT 23-59%.

e) golden_exit_cases.csv: the "expected" column is the heuristic's own output. Grade new code against "independent_truth": E09 (SUNTV) must be win; E04 is unverified and reported, not graded.

f) The pack holds 5-minute truth for only 9 cases (E05-E13, heuristic gets 8 of 9). The "15 of 16" cannot be re-verified from the pack.

g) NEW ISSUE: 2h bars come from pandas resample('2h') on clock hours, so the first bar of each day (08:00 bin) holds only the 09:15 hourly candle. 9 of 25 WIT entries sit on such a one-hour bar; the DIT 2h trend frame has the same problem. Stage 3 must build bars from explicit start and end times.

h) NEW ISSUE: entry is always booked at the proximal edge and a stop hit on a gap is booked as exactly -1R. Gaps through the entry or the stop are not modelled. Stage 4 must fill at the open when gapping.

i) Stage 2 can prove identical zones only where sample bars exist: DIT 13 of 207 trades, WIT 8 of 25, MIT 22 of 22. For the rest, the full Yahoo bars must be cached once on this machine.

j) Pack contradictions: base cap truncates in code but "reject" is the wanted rule (R20); pen-circled screenshots exist for only 3 of the 6 base-candle cases; wick-freshness removed WIT trades are 18 in DECISIONS #24 vs 16 in the re-score (unreconciled); RULES X05 says "not recorded" but Record B holds the table (subset of n=131, which subset is unknown).

k) STATUS.md open-issue list is missing: DIT wick-freshness breakdown, ANURAS check, EMA-in-zone concentration check. Added to docs/STATUS.md open issues (items 13-15).
