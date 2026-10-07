# DECISIONS.md — every experiment, its result, and whether the exit bug contaminated it

**The exit bug** (see RULES R12): until 1 Oct 2026 the backtest counted a target touched on the *entry candle* even if price had not yet entered the zone. It was in the code from the start (the earliest data file, 25 Sep, already has 60% of trades exiting on their own entry candle). **Every win rate / P&L / avg R below that is flagged BUGGY-EXIT is inflated** — across the files between a quarter and a third of recorded wins flip to losses (in the three largest files win rate 46–49% → ~31–32%, avg R from +0.4 to about −0.05; per-file figures in `results/history_rescore_table.csv`). Qualitative decisions (a trade's chart looked right/wrong) are not affected.
Flag legend: **BUGGY** = number measured under the bug · **CLEAN** = measured with the corrected exit · **QUAL** = qualitative, user's chart judgment · **n/r** = result not recorded.

The decision column says what was done. "Survives?" is my judgement after the corrected scoring, only where files exist for both sides; otherwise "can't tell".

| # | Date | Experiment | Result | Decision | Flag | Survives corrected scoring? |
|---|---|---|---|---|---|---|
| 1 | 22 Sep | Pair HTF+LTF zones (first scan of 10 DIT / 5 WIT / 5 MIT setups) | User found the LTF zone was taken as a later retest (SBIN); the LTF zone must be the concurrent view of the same move | Pairing rule R09 | QUAL | yes (not P&L based) |
| 2 | 22 Sep | Rounds of per-ticker feedback (TCS, GRASIM, JUBLINGREA, MAXHEALTH, …) | Many zones accepted, several lines corrected | Zone-line fixes, base-candle caps | QUAL | yes |
| 3 | 22 Sep | Integrate the GTF reference bot and backtest it | User reviewed its trades: "absolutely dogshit", no HTF confluence | Discarded (X06); files deleted | QUAL | yes |
| 4 | 22 Sep | LTF must have 1–2 explosive candles; base ≤ 3 | Adopted for LTF | R01, R02 | QUAL | partly open: the base definition (R20) |
| 5 | 22–23 Sep | Trend filter on/off backtest, then a symmetric trend rule | Symmetric rule blocked good sideways demand trades | Replaced by asymmetric 3-timeframe zone-break rule (R11) | n/r | can't tell |
| 6 | 23 Sep | Min LTF overlap lowered to 30% | Adopted | `MIN_LTF_OVERLAP_FRAC = 0.3` | n/r | can't tell |
| 7 | 23 Sep | 26 annotated charts (folder "photos improve"): trend from zone breaks on an intermediate TF; gap / 2nd strong legout is a plus not a rule | Rule R11, R05 | Adopted | QUAL | yes |
| 8 | 23 Sep | `base_extension_atr_mult` = 0.15 for HTF (NTPC/TCS/UPL/HINDALCO HTF proximal too low) | Fixed those four, no regression on TECHM/POWERGRID | Adopted | QUAL | yes — but see OPEN R23 (it may now be cutting bases too short) |
| 9 | 25–26 Sep | Wick-to-wick for strong-legout zones + 0.1×ATR distal buffer | Trade count roughly doubled although the user asked for "no change in trade count"; reported honestly | Adopted; then HTF wick-to-wick removed 26 Sep (R04) | BUGGY | can't tell |
| 10 | 26 Sep | HTF strong-legout vs P&L | HTF strong-legout trades +Rs 277/trade vs −Rs 82; only ~22% qualified | Threshold loosened for HTF (gap 0.5 ATR), kept as a signal not a filter | BUGGY | can't tell |
| 11 | 26 Sep | Daily-only / new-IPO / 15m-with-2h-trend side backtests the user asked for | n/r | Not adopted | n/r | can't tell |
| 12 | 27 Sep | Train/holdout split at 2026-01-01 | Added | R14 | — | — |
| 13 | 27 Sep | Why WIT holdout > train | No regime break at the cutoff (noise + tighter HTF/LTF zones in holdout + 75% of holdout profit in 5 trades; NIFTY +7.4% train vs −10.5% holdout) | Treat holdout as encouraging, not proof | BUGGY | the interpretation of the cause stands; the numbers do not |
| 14 | 27 Sep | Overfit check: rerun excluding the 18 ticker names used to develop rules | Comparison was started; **numbers not recorded** in anything I can retrieve | none | n/r | can't tell |
| 15 | 27–28 Sep | Universe from NSE live data; validate with yfinance | `universe_live.json`, 504 tickers; only DUMMYHEG.NS confirmed dead | Adopted | — | — |
| 16 | 28 Sep | **Trend re-check at the LTF entry moment** ("ACE fix", user: price became downtrend by the time it reached the zone) | MIT 40 → 27 trades (13 removed: 11 losses, 2 wins: GODREJPROP +1,963, TEGA +1,950); WIT removed trades 70/30 toward losses (12 winners lost) | Adopted | BUGGY | **can't tell** (the before-file for the same code does not exist with the needed columns) |
| 17 | 28 Sep | DIT feature analysis (decision tree, bucket filters, cost sensitivity) | Tight HTF zone filter raised win rate 44.8% → 60.4% but total R fell 115 → 58 (more than half the profit); tree beat "always loss" by 0.9 pp; edge survived 0.2R/trade cost | No filter adopted | BUGGY | the "filters cut profit" shape probably holds; levels do not |
| 18 | 28 Sep | Distal-buffer sweep 0.1 → 1.0 (SL widening), 200 tickers | Counts 131/158/180 for 0.1/0.2/0.3; final table **not recorded** | Rejected by the user; 0.1 kept | n/r | can't tell |
| 19 | 28 Sep | Closed-bars-only trend mask (is the trend bar at the entry timestamp still forming?) | **Never run.** I confirmed the mask is `timestamp <= entry_ts`, so a daily trend bar dated the entry day is included even though its close is not known yet; the ATH override is the likeliest place it matters. User thought it would barely matter | Open | — | open |
| 20 | 29 Sep | **Rule 1** (legout closes beyond legin), isolated | DIT 308 → 281 (45.8% → 45.6%, Rs 88,225 → 78,096); WIT 41 → 44 (51.2% → 52.3%, Rs 20,581 → 22,696); MIT 27 → 26 (44.4% → 46.2%, Rs 8,946 → 9,938) | Adopted, LTF only | BUGGY | **can't tell** (rule1-only files lack stop/target columns, cannot be re-scored) |
| 21 | 29 Sep | **Rule 2** (legin wick as distal) | DIT Rs 88,225 → 73,313; WIT Rs 20,581 → 11,982; MIT up | Rejected, code deleted | BUGGY | can't tell (same reason) |
| 22 | 29–30 Sep | Confirmation runs of rule 1 through the production path | DIT 297 / 45.8% / Rs 84,563; WIT 45 / 51.1% / Rs 21,697; MIT 27 / 44.4% / Rs 8,946; small differences from the isolated runs explained by day-to-day `walk_back_base` drift and transient fetch failures | Standing baseline (pre wick-fix) | BUGGY | — |
| 23 | 29 Sep | Slow DIT run | Root cause: Yahoo timeout 10s per failing ticker (8.3 s each); `timeout=5` | Fixed | — | — |
| 24 | 29 Sep | **Wick-freshness** (R10), triggered by the MIT review (USHAMART, GODFRYPHLP, INDIGO, BPCL, RAILTEL) | MIT 27 → 23 trades, better on every metric; WIT 45 → 27, mixed (P&L −37%); 9 of 18 removed WIT trades were wins | Adopted, permanent 30 Sep | BUGGY | **weakened.** Re-scoring the removed lists with the corrected exit: DIT removed 81 trades, +6 R; WIT removed 16, +2 R; MIT removed 4, −1 R — it removes slightly *positive* trades on DIT/WIT. The rule now rests on the user's chart logic, not on P&L |
| 25 | 30 Sep | Final baselines with rule 1 + wick-freshness | DIT 207 / 48.3% / Rs 67,161 / avg R +0.449; WIT 25 / 52.0% / Rs 12,563 / +0.560; MIT 22 / 50.0% / Rs 10,886 / +0.500 | These were the "standing baseline" until 1 Oct | BUGGY | **INVALID** — replaced by row 36 |
| 26 | 30 Sep | Strong-LTF override on the rejected trades | 11 W / 13 L on added trades | Rejected (X03) | BUGGY | can't tell (rejected list not re-scored for it) |
| 27 | 30 Sep | EMA20/50 in zone / direction filters, 5 versions | see RULES X04 | Rejected | BUGGY | likely (they were inversely predictive, a structural effect: entries are pull-backs into a zone, so EMA sits on the far side of price) |
| 28 | 1 Oct | WIT review docx: "code is not capping base candles" | Real base counts for the 6 screenshots are 1–2 (ICICIGI weekly run 5); cap enforced by construction; user maintains the screenshots show 7+ and 20 | OPEN (R20) | — | open |
| 29 | 1 Oct | **LTF base cap 3 → 5** | see RULES X02 | Reverted | BUGGY, then re-scored | weak: corrected-exit net ≈ 0 R |
| 30 | 1 Oct | Congestion / band-based base counts, `reject_long_base` | see RULES X08, E01 | Not adopted | BUGGY | — |
| 31 | 1 Oct | **Exit fix** (R12) and 5-minute validation | Fixed rule agrees with 5-minute data on 15 of 16 recent trades (old rule 11 of 16) | Adopted | CLEAN | — |
| 32 | 1 Oct | Re-score every historical trade file with the fixed exit | 7 files; share of trades exiting on their own entry candle is flat 42–62% in every file → the bug was never introduced by a change, it was always there | Report | CLEAN | — |
| 33 | 1 Oct | Corrected-exit re-score of the current baselines | **DIT 207 / 31.4% / −Rs 12,221 / avg R −0.058; WIT 25 / 24.0% / −Rs 7,313 / −0.280; MIT 22 / 40.9% / +Rs 4,908 / +0.227** | These are the valid baselines | CLEAN | — |
| 34 | 2 Oct | 100-ticker subset (`universe_subset100.json`) with the fixed exit through the real pipeline | DIT n=45: old rule 55.6% / +Rs 19,340, fixed 35.6% / −Rs 406; WIT n=3 (0% fixed); MIT n=5 (20% fixed). WIT/MIT far too small to read | Report only | CLEAN | — |

Observation worth carrying into the rebuild: about **half of all trades exit on their own entry candle** (DIT 117 of 207). Entry-candle handling is therefore not a corner case — it decides a large share of the results. Many of those are 09:15 candles after a gap.

## What the user rejected or corrected that is NOT in the table above (verbatim in `corrections/`)
- Per-ticker chart feedback from 22 Sep, 26 Sep, 29 Sep and 1 Oct — the most important content in the pack; see `corrections/CORRECTIONS.md`.
- The user also said, about review process: the MIT review of 29 Sep was done on `mtf_trade_diagnostics_mit_live_fixed.csv` (an older file, losses only), **not** on any of the NEW_BASELINE files. As of 1 Oct the user had **not** reviewed the NEW_BASELINE files for DIT, WIT or MIT.

## Added records (2 Oct 2026, supplied by the user)
Both were measured under the OLD buggy exit. **Invalid for win rate — direction only.** They carry the results for the table rows that say "not recorded" above (#14 overfitting check, #18 distal-buffer sweep).

### Record A — 27 Sep overfitting check (rules developed on named tickers vs the same run without them)
15 evidence tickers excluded (3 of the 18 named tickers were not in the medium universe; which 3 is not recorded here). Full universe vs excluded run:

| | Full | Excluded |
|---|---|---|
| DIT | n 98, 40.8%, +Rs 12,317 | n 80, 46.2%, +Rs 17,215 |
| WIT | n 12, 33.3%, −Rs 478 | n 9, 33.3%, −Rs 1,072 |
| MIT | n 5, 60.0%, +Rs 3,960 | n 4, 50.0%, +Rs 1,972 |
| **Overall** | **n 115, 40.9%, +Rs 15,800** | **n 93, 45.2%, +Rs 18,116** |

Direction only: the run without the evidence tickers did not do worse (DIT and overall win rate higher, WIT equal, MIT lower on n = 5 vs 4). Sample sizes are tiny, especially WIT and MIT.

### Record B — LTF distal-buffer (SL-widening) sweep
R:R kept at 2:1; costs 0.20% round trip.

| buffer (× ATR) | n | win % | avg R | note |
|---|---|---|---|---|
| **0.1** | 131 | 49.6% | +0.49 | total R +64.0, cost-adjusted +32.5 |
| 0.2 | 158 | 46.2% | +0.39 | |
| 0.3 | 180 | 45.0% | +0.35 | |
| 0.5 | 207 | 40.6% | +0.22 | |
| 0.8 | 229 | 38.0% | +0.14 | |
| 1.0 | 241 | 34.9% | +0.05 | cost-adjusted total R −18.7 |
| 1.5 | 258 | 36.4% | +0.09 | cost-adjusted total R −0.2 |

Result: 0.1 was best both before and after costs, so no change (0.1 × ATR stays). The n at 0.1 is 131, not the full-universe baseline, so this was a subset run; which subset is not recorded here. (The chat log shows a 200-ticker sweep was started on 28 Sep after the user asked for "just 200 tickers", but I have not confirmed that this table is that run.)


2 Oct 2026: Option C chosen, new clean repo dz-engine; Stage 0 done.

2 Oct 2026: Standing exit-scoring rule added to CLAUDE.md. Every trade is replayed at 15minute; AMBIGUOUS trades are re-run at 1minute automatically; NO_MINUTE_DATA trades stay AMBIGUOUS and are counted in every table; Kite stays read-only. The legacy heuristic exit is kept only as a labelled comparison column. Ask the user only if one run needs more than 1,500 Kite requests.

2 Oct 2026: New base-candle logic built (src/base_candles.py, config.py, behind --new-base, default off, no DIT/WIT/MIT run yet): base candle = wick > 50% of body OR small body; count the whole consolidation and reject above the cap (LTF 3, HTF 5); zone lines from the nearest candles (HTF growth cap 0.4 ATR); base candle range <= 2.5 ATR; HTF base/legout range <= 1.25. Checked per chart on the user's examples only; golden cases in tests/golden/base_candle_cases.csv. Awaiting the user's go-ahead before any combo run.

2 Oct 2026 (later): User added RVNL, ACC and CONCORDBIO photos as genuinely very good trades. Their daily LTF zones need 7, 6 and 3 base candles, so the new-logic LTF cap is 8 (not 3), the count uses a price band (0.75 ATR) so a drift is not a coil, LTF lines come from the nearest 3 candles, and the LTF base/legout limit is 0.6. Golden cases B16-B19 added. Still no DIT/WIT/MIT run; awaiting the user.

2 Oct 2026 (review): User reviewed the 15 sample zones (basecandlefix.docx): 8 confirmed, B6 GLAND wrong (10+ candles), A2 KPITTECH zone low should be 1328, A3 ULTRACEMCO numbers unclear. Golden cases B20-B28 added; no logic change yet because B6 conflicts with ACC under any count rule. Awaiting the user's answers (see RULES R29).

2 Oct 2026 (review fix): After the user's review (A2 KPITTECH and B6 GLAND both wrong, ~20 and 10+ base candles) the base count is a plain contiguous count again (price-band count dropped) with LTF cap 9, HTF cap 5. All verdicts B20-B28 pass; ACC's daily zone is now rejected (known gap B17). No combo run yet.

2 Oct 2026: User set the caps: HTF 5, LTF 8 (was briefly 9). MIT run with --new-base started after this.

2 Oct 2026: LTF base cap 5, base logic V2. Adopted by user decision on chart judgement. Test result vs Baseline v1: WIT 43.1% vs 41.3%, MIT 44.4% vs 41.7%, intervals include zero. DIT15 not rerun under cap 5. Config: BASE_LOGIC_V2 = True, LTF_BASE_CAP = 5 (flags/`--legacy-base` keep Baseline v1 reproducible). Duplicate zones are dropped inside the pipeline (MIT cap-5 list is 18 trades, not 19).

2 Oct 2026 (follow-up): DIT15 rerun under LTF cap 5: 184 trades, 26.1% vs Baseline v1 29.9% (-3.8 pts, bootstrap 95% [-12, +5]). Cap 5 did not help DIT15; the interval includes zero. Baseline v1 remains the confirmed comparison.

2 Oct 2026: MIT review processed (RULES R31, R32). New rule built and ON by default: HTF legout must close over the base wick (cap-5 candidate lists predate it; none of the 18 MIT trades fail it). Open: CGPOWER/CCL area count, DEEPAKFERT whole-base stop, TMPV price-scale mismatch, NEWGEN second LTF entry, legout definition for IKS/MASTEK/LAURUS. No pipeline rerun yet.
