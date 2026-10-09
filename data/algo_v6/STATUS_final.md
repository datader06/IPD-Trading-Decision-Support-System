# STATUS.md — where things stand on 2 Oct 2026

## 1. Valid baselines (corrected exit, rule 1 + wick-freshness + LTF base cap 3)
All triggered signals, no capital limit, full 504-ticker `universe_live.json`, live Yahoo data fetched 29 Sep – 1 Oct, re-scored on 1 Oct with the corrected exit (RULES R12).

| Combo | n | Win rate | Total P&L | avg R | Train (n / win / P&L) | Holdout (n / win / P&L) |
|---|---|---|---|---|---|---|
| **DIT** | 207 | **31.4%** | **−Rs 12,221** | −0.058 | 123 / 32.5% / −Rs 5,940 | 84 / 29.8% / −Rs 6,281 |
| **WIT** | 25 | **24.0%** | **−Rs 7,313** | −0.280 | 12 / 25.0% / −Rs 3,028 | 13 / 23.1% / −Rs 4,285 |
| **MIT** | 22 | **40.9%** | **+Rs 4,908** | +0.227 | 14 / 42.9% / +Rs 3,881 | 8 / 37.5% / +Rs 1,028 |

These come from re-scoring the *same trade set* (same zones, entries, stops, targets) with the new exit; zones were not re-detected. Files: `results/mtf_trade_diagnostics_{dit,wit,mit}_FIXEDEXIT.csv`. They replace the earlier "standing baselines", which are **invalid** (DIT 207 / 48.3% / +Rs 67,161; WIT 25 / 52.0% / +Rs 12,563; MIT 22 / 50.0% / +Rs 10,886).
A full re-run of the real pipeline with the fixed exit on the whole universe has **not** been done. On the 100-ticker subset it was run: DIT n=45, old rule 55.6% / +Rs 19,340, fixed 35.6% / −Rs 406; WIT n=3; MIT n=5 (`results/*_100_FIXEDEXIT.csv`).
Caveat on all of these: the exit fix is a heuristic (RULES R12). It agreed with 5-minute data on 15 of 16 recent trades and is wrong in at least one direction (SUNTV). The true result is somewhere between these numbers and the old ones, but clearly below the old ones.

## 2. Files: valid vs invalid
**Valid (corrected exit, or exit-independent):** everything in `results/`; `code/` (current); `golden/`; `corrections/`; `data/`.
**Invalid for any win-rate / P&L / avg-R comparison:** everything in `old_invalid/` (details in `old_invalid/README.md`). They are kept because the *trade lists* are what the user reviewed by eye, and for provenance. Their `outcome` / `pnl` columns carry the exit bug.
Known data corruption: in the old `mtf_trade_diagnostics_wit_NEW_BASELINE.csv` one ticker reads `nau`; it is **NAUKRI.NS** (its HTF lines 1399.40 / 1497.73 match exactly). The file's dates are also in `DD-MM-YYYY HH:MM`, i.e. it was opened and re-saved in Excel. Do not open the CSVs in Excel; read them with pandas (`format="mixed", dayfirst=True` only for those re-saved files; the files in `results/` are ISO).

## 3. Canonical code and what differs from the older copies
`code/sd_zones.py`, `code/mtf_zones.py`, `code/mtf_backtest.py` are byte-for-byte the current files from `D:\technical analysis\ml_pipeline\` (modified 1 Oct). `code/webapp/universe*.py|json` come from `ml_pipeline\webapp\` (identical to the root `webapp\universe.py`).
Older copies exist in `D:\technical analysis\` (root; last modified 27 Sep) and are **not** included. They differ: no rule 1 (`require_legout_beyond_legin`), no wick-freshness (`_htf_wick_tested_at`), no trend re-check at the entry moment, no `timeout=5` in the fetch, no train/holdout split, no `reject_long_base` flag, and — important — **the root `mtf_backtest.py` still has the unfixed exit loop**. Anything run from the root copy still has the exit bug. Because the project is not under git, nothing older than 27 Sep exists, and the exit loop and `apply_freshness` are identical in the 27 Sep copy and the pre-fix `ml_pipeline` copy.
`code/offline_loader.py` is new (not part of the original code): it lets the unmodified code run with no internet by replacing `mtf_zones._fetch`.

## 4. Open issues
1. **Base-candle definition (R20) — the main open correction.** The user counts whole consolidations (7 / ~20 / ~20 candles on the pen-circled screenshots); the code counts 1–2 and cannot be made to agree by changing a cap. The user still has to supply annotated legin / base / legout screenshots, and wants a *flexible* definition (small candle = body < 50% of its range; "exciting" = more). Reject over-long bases (LTF > 3, HTF > 5), don't truncate. Six reference cases in `golden/`.
2. **NAUKRI stop (R21).** User: ~1463. Code: 1448.78; whole-run geometry also 1448.78. Not explained. Same family: FINCABLES (user 1108, code 1146.40), BEL (user ~396).
3. **Trend-mask closed-bars check.** `_classify_trend_from_events` uses `timestamp <= entry_ts`, so a daily trend bar dated the entry day (full-day high/low/close, not known yet) is included, and the all-time-high override can be flipped by it. The check was proposed on 28 Sep and **never run**. The user expects it to matter little; unquantified.
4. **Root `mtf_backtest.py` unfixed** (see 3).
5. **Stale comments in the code.** The standing-baseline block inside `code/mtf_zones.py` (above `LTF_ENTRY_CONFIG`) quotes the old, invalid numbers. The WEEKLY/MONTHLY config comments say `base_candle_max_range_atr_mult` is set explicitly, but the value is `inf` (no cap) in the code. Not corrected here, because the code was included unchanged.
6. **The exit heuristic is not exact.** Entry-candle target uses candle direction only. Needs intra-candle data to be right (SUNTV is a stored regression target, golden E09). Roughly half of all trades exit on their own entry candle (DIT 117/207), many at the 09:15 open after a gap.
7. **Unresolved single trades.** DIVISLAB (user says it should be a loss; fixed-exit run still scores a win via a later candle); GESHIP (the zone the user means — entry 13 March — is not the one the system listed); COROMANDEL ("weird, let it be"); MRPL (LTF tapped before it formed: user says "fix this", no code recorded); CCL, POWERINDIA, BEML (base-candle wick vs HTF zone / HTF line should include its base candle, R23).
8. **Review gap.** The user has not reviewed the NEW_BASELINE trade lists for DIT, WIT or MIT. The MIT review of 29 Sep was of `mtf_trade_diagnostics_mit_live_fixed.csv` (losses only). The WIT review was of the *removed-by-wick-fix* list plus the 6 screenshots.
9. **Data reproducibility.** There is no retry on failed downloads and no disk cache; a transient failure silently drops a ticker (BLUEJET was dropped once). `walk_back_base` drifts between days as the live window shifts, so a re-run on another day changes a few percent of trades (verified on SCI.NS, GABRIEL.NS). Baselines are therefore not bit-reproducible from the code alone — hence the stored sample bars in `data/`.
10. **Sample sizes.** WIT has 25 trades and MIT 22 over ~2 years; the 100-ticker subset gives 3 and 5. Nothing about WIT or MIT should be concluded from them. In WIT's holdout, 5 trades made 75% of the profit (27 Sep analysis).
11. Rules whose effect was only ever measured under the exit bug and cannot be re-judged (no file pair with the needed columns): trend re-check, rule 1, rule 2. Wick-freshness can be re-judged and is weakened (DECISIONS #24).
12. Time zone: timestamps in `corrections/CORRECTIONS_VERBATIM.md` are UTC (as stored in the chat log); the user is in India (IST = UTC+5:30).
13. **DIT wick-freshness breakdown** — not done (added 2 Oct 2026, see PACK_FINDINGS.md).
14. **ANURAS check** — not done (added 2 Oct 2026).
15. **EMA-in-zone concentration check** — not done (added 2 Oct 2026).

## 5. How to reproduce offline (what the receiving chat can do)
```
python golden/run_golden_checks.py          # needs pandas + numpy only
```
Part A re-simulates the 13 exit cases with `mtf_backtest.simulate_exit` and compares to the expected corrected outcome and to the 5-minute truth. Part B runs the real `build_trades_for_ticker` on the sample bars and compares to `results/*_FIXEDEXIT.csv`. On 2 Oct (yfinance blocked): exit cases 13/13; pipeline reproduction DIT 13/13 (golden exit tickers only), WIT 8/8, MIT 22/22, no extra trades.
Sample bars (`data/bars/{TICKER}__1d.csv` and `__60m.csv`) are raw Yahoo bars as `timestamp,open,high,low,close`, timezone-stripped, exactly what `mtf_zones._fetch` returns. `data/data_index.csv` lists each file and its span. 60m windows are trimmed to [first golden entry − 240 days, last + 60 days] for WIT tickers and are full 729-day history for the 10 DIT exit tickers (the trend filter needs the history). Daily MIT tickers are full history because the monthly HTF uses all of it; WIT/DIT daily is the last 900 bars. `data/bars5m/` holds 5-minute bars around the 9 recent exit cases (Yahoo keeps only 60 days of them, so they cannot be re-fetched later).

## 6. Pack contents map
`RULES.md` · `DECISIONS.md` · `STATUS.md` (this) · `corrections/` (**read first**) · `code/` · `golden/` · `results/` · `old_invalid/` · `data/` · `tools/` · `MANIFEST.md`


## 7. Baseline v1 (user trade review: IN PROGRESS), Kite data, 15m then 1m exit, ambiguous trades scored by heuristic, gross of costs, entries from 2024-01-01
Status: lists frozen, NOT yet confirmed. The user is reviewing the trades (results/b47e89b/review_dit15.csv, review_wit.csv, review_mit.csv, column my_verdict). Do not treat as a confirmed baseline until the user says so.
Data: Kite only (daily 2012+, 60m and 15m from 2023-01-01). Universe: 503 tickers of legacy universe_live.json (HFCL.NS skipped, Kite lists only HFCL-BE). Legacy zone pipeline unmodified; DIT15 = legacy dit spec with LTF overridden to Kite 15m bars (runner override, legacy files untouched).
Exit: every trade replayed at 15minute; AMBIGUOUS re-run at 1minute; still-AMBIGUOUS trades take the saved legacy heuristic outcome (source "heuristic"); a real replay outcome is never overwritten. R: replay trades use replay R (gap fills/stops included), heuristic-scored use +2/-1. Gross: no brokerage, tax or slippage. Sizing: Rs 1,000 max loss per trade.
Generated at commit 53aecde (this entry is committed in the next commit, see git log). Source trade lists: results/b47e89b/trades_dit15_kite_2024_final.csv, results/b47e89b/trades_mit_kite_2024_final.csv, results/12d4238/trades_wit_kite_2024_final.csv. Output files: results/53aecde/baseline_v1_dit15.csv, baseline_v1_wit.csv, baseline_v1_mit.csv (columns outcome_final, outcome_source, r_final, pnl_final), baseline_v1_tables.txt.
Caveats: DIT15 has 49 of 231 trades (21%) scored by the heuristic; with those all wins/all losses the DIT15 win rate would be 46.8% / 25.5% (replay-only trades). WIT has 3 heuristic-scored trades, MIT none. Kite prices are unadjusted for splits/bonuses. Samples under 30 are flagged. Not comparable to the older Yahoo baselines in section 1 (different data source, period and universe window).

```
DIT15 (231 trades; source counts {'15m': 120, '1m': 62, 'heuristic': 49}; file results/53aecde/baseline_v1_dit15.csv)
  ALL                  n=231 wins= 69 losses=162 win%= 29.9 boot95=[24-36] avgR=-0.112 totalRs=  -15,380 heuristic-scored=49 (21% of n)
  2024                 n= 84 wins= 34 losses= 50 win%= 40.5 boot95=[30-51] avgR=+0.207 totalRs=  +10,546 heuristic-scored=19 (23% of n)
  2025                 n= 67 wins= 12 losses= 55 win%= 17.9 boot95=[9-27] avgR=-0.479 totalRs=  -19,386 heuristic-scored=13 (19% of n)
  2026                 n= 80 wins= 23 losses= 57 win%= 28.8 boot95=[19-39] avgR=-0.140 totalRs=   -6,541 heuristic-scored=17 (21% of n)
  TRAIN (<2026-01-01)  n=151 wins= 46 losses=105 win%= 30.5 boot95=[23-38] avgR=-0.097 totalRs=   -8,839 heuristic-scored=32 (21% of n)
  HOLDOUT (2026)       n= 80 wins= 23 losses= 57 win%= 28.8 boot95=[19-39] avgR=-0.140 totalRs=   -6,541 heuristic-scored=17 (21% of n)
  per-year n add up: 231 of 231

WIT (63 trades; source counts {'15m': 51, '1m': 9, 'heuristic': 3}; file results/53aecde/baseline_v1_wit.csv)
  ALL                  n= 63 wins= 26 losses= 37 win%= 41.3 boot95=[30-54] avgR=+0.241 totalRs=  +14,090 heuristic-scored=3 (5% of n)
  2024                 n= 29 wins= 10 losses= 19 win%= 34.5 boot95=[17-52] avgR=+0.046 totalRs=   +2,185 heuristic-scored=3 (10% of n)  SAMPLE<30
  2025                 n= 17 wins=  9 losses=  8 win%= 52.9 boot95=[29-76] avgR=+0.588 totalRs=   +8,641 heuristic-scored=0 (0% of n)  SAMPLE<30
  2026                 n= 17 wins=  7 losses= 10 win%= 41.2 boot95=[18-65] avgR=+0.227 totalRs=   +3,264 heuristic-scored=0 (0% of n)  SAMPLE<30
  TRAIN (<2026-01-01)  n= 46 wins= 19 losses= 27 win%= 41.3 boot95=[28-57] avgR=+0.247 totalRs=  +10,826 heuristic-scored=3 (7% of n)
  HOLDOUT (2026)       n= 17 wins=  7 losses= 10 win%= 41.2 boot95=[18-65] avgR=+0.227 totalRs=   +3,264 heuristic-scored=0 (0% of n)  SAMPLE<30
  per-year n add up: 63 of 63

MIT (24 trades; source counts {'15m': 23, '1m': 1}; file results/53aecde/baseline_v1_mit.csv)
  ALL                  n= 24 wins= 10 losses= 14 win%= 41.7 boot95=[21-62] avgR=+0.250 totalRs=   +5,897 heuristic-scored=0 (0% of n)  SAMPLE<30
  2024                 n= 10 wins=  5 losses=  5 win%= 50.0 boot95=[20-80] avgR=+0.497 totalRs=   +4,942 heuristic-scored=0 (0% of n)  SAMPLE<30
  2025                 n=  9 wins=  3 losses=  6 win%= 33.3 boot95=[11-67] avgR=+0.000 totalRs=     -106 heuristic-scored=0 (0% of n)  SAMPLE<30
  2026                 n=  5 wins=  2 losses=  3 win%= 40.0 boot95=[0-80] avgR=+0.207 totalRs=   +1,061 heuristic-scored=0 (0% of n)  SAMPLE<30
  TRAIN (<2026-01-01)  n= 19 wins=  8 losses= 11 win%= 42.1 boot95=[21-63] avgR=+0.262 totalRs=   +4,836 heuristic-scored=0 (0% of n)  SAMPLE<30
  HOLDOUT (2026)       n=  5 wins=  2 losses=  3 win%= 40.0 boot95=[0-80] avgR=+0.207 totalRs=   +1,061 heuristic-scored=0 (0% of n)  SAMPLE<30
  per-year n add up: 24 of 24
```

## 8. Baseline v2 CANDIDATE (cap 5): MIT, WIT and DIT15, pending user review. Baseline v1 remains the confirmed comparison.
Base logic V2 with LTF base cap 5 (HTF cap 5), Kite data, 15m then 1m exit, ambiguous trades scored by heuristic, gross of costs, entries from 2024-01-01. Same method as section 7; only the base-candle logic differs (docs/RULES.md R24-R30). DIT15 was rerun under cap 5 on 2 Oct 2026 (late entry below).
Results (replay win/loss stands, still-ambiguous trades take the heuristic outcome; heuristic-scored: WIT 6 of 58, MIT 1 of 18):
- WIT cap 5: n=58, 25 wins, 33 losses, 43.1% [31-55], avg R +0.292, +Rs 15,681. Train n=41, 41.5%, +Rs 9,678; holdout n=17, 47.1%, +Rs 6,003 (under 30, flagged). Baseline v1 WIT: n=63, 41.3%, +Rs 14,090. Difference +1.8 pts, bootstrap 95% [-16, +20].
- MIT cap 5: n=18, 8 wins, 10 losses, 44.4% [22-67], avg R +0.327, +Rs 4,742. Train n=15, 46.7%; holdout n=3, 33.3% (all under 30, flagged). Baseline v1 MIT: n=24, 41.7%, +Rs 5,897. Difference +2.8 pts, bootstrap 95% [-28, +33].
Overlap with Baseline v1: WIT 28 in both, 35 removed (15 wins, 20 losses), 30 added; MIT 7 in both, 17 removed (7 wins, 10 losses), 11 added.
Files: results/c0b74c8/trades_{wit,mit}_kite_2024_newbase_cap5_final.csv (committed in 21e3482); review sheets results/21e3482/review/review_{wit,mit}_cap5.csv and review_{wit,mit}_removed.csv (ltf_base_count / htf_base_count included; my_verdict empty). Not a baseline until the user confirms.
- DIT15 cap 5 (added later; Baseline v1 DIT15 = 231 trades, 29.9%, -Rs 15,380): n=184, 48 wins, 136 losses, 26.1% [20-32], avg R -0.249, -Rs 26,987. Train n=113, 22.1%, -Rs 27,420; holdout n=71, 32.4%, +Rs 433. Heuristic-scored 35 of 184 (19%); on replay-only trades, all ambiguous winning would give 40.2%, all losing 21.2%. Difference vs Baseline v1: -3.8 pts, bootstrap 95% [-12, +5]. Overlap: 91 in both, 140 removed, 93 added. Identical to the filter estimate from the cap-8 run (no replacement trades). Files: results/9739e07/trades_dit15_kite_2024_v2_cap5_{heuristic,final}.csv; review sheets results/9739e07/review/review_dit15_{cap5,removed}.csv.
Note (2 Oct 2026, later): the candidate lists above were produced WITHOUT the new HTF rule 'legout must close over the base wick' (RULES R31, now on by default). None of the 18 MIT trades fail it; WIT and DIT15 not yet checked. The user's review of the taken MIT trades is in RULES R32.

## 9. Long-history runs (entries from 2021-01-01), V2 base logic cap 5 + legout-over-wick (R31); DIT15 added to the baseline set on 5 Oct 2026 at the user's request
Same scoring as section 7 (replay win/loss stands, still-ambiguous trades take the heuristic outcome, gross, Rs 1,000 risk). Not confirmed baselines (review pending); reported together with section 7 and 8 per RULES R33/R34.
- MIT 2021+: n=35, 17 wins, 18 losses, 48.6% [31-66], avg R +0.415, +Rs 13,330; train n=32 50.0%, holdout n=3 33.3% (flagged). results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv
- WIT 2021+: n=98, 36 wins, 62 losses, 36.7% [28-46], avg R +0.122, +Rs 11,517; train n=81 34.6%, holdout n=17 47.1% (flagged). results/50f701a/trades_wit_kite_2024_v2_cap5_lw_from2021_final.csv
- DIT15 2021+ (strict HTF, LTF base <=5): n=268, 87 wins, 181 losses, 32.5% [27-38], avg R -0.039, +Rs 3,421; train n=213 31.9%, holdout n=55 34.5%; 42 of 268 heuristic-scored; 0 NO_MINUTE_DATA. LTF base <=3 subset: n=200, 31.0%, -Rs 5,674. Strict HTF rule removed ~21% of trades. results/4d02f6d/trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv (base counts included).
- DIT15 strict, 2024+ slice: n=147, 28.6% [21-36], -Rs 11,740 (previous unstrict cap 5: n=184, 26.1%, -Rs 26,987; diff +2.5 pts, bootstrap [-7,+12]).

## 10. Experiment (5 Oct 2026, report only): take a trade only if the trend is in favour (demand needs UP, supply needs DOWN; sideways excluded)
Method: filter of the existing 2021+ trade lists (scripts/trend_strict_filter.py), same trend frame/functions/flags as the runs. Sanity: 0 counter-trend trades in all three lists (reproduces the legacy filter, which only blocks counter-trend and lets sideways pass). A rerun could in principle add replacement trades (an LTF zone matching a different HTF zone); not checked. Labelled files: results/{132d5d8,50f701a,4d02f6d}/*_trendlabels.csv. No config changed.
- MIT 2021+: all 35 (48.6%, +Rs 13,330) -> aligned 30 (43.3%, +Rs 6,491); the 5 sideways trades were 4 wins/1 loss. 2024+: 19 (42.1%) -> 16 (37.5%).
- WIT 2021+: all 98 (36.7%, +Rs 11,517) -> aligned 79 (39.2%, +Rs 15,111); 19 sideways were 5 wins/14 losses (26.3%). 2024+: 59 (42.4%) -> 48 (45.8%, +Rs 17,132).
- DIT15 2021+: all 268 (32.5%, +Rs 3,421) -> aligned 139 (32.4%, +Rs 1,641); 129 sideways were 32.6%. 2024+: 147 (28.6%) -> 77 (27.3%). No effect.

## 11. CURRENT BASELINE SET (user decision, 7 Oct 2026; supersedes "Baseline v1 is the confirmed comparison" for new comparisons)
- DIT15 = strict HTF (--strict-htf), LTF base <= 5, V2 + legout-over-wick. 2021+: n=268, 32.5% [27-38], +Rs 3,421. 2024+ slice: n=147, 28.6% [21-36], -Rs 11,740. results/4d02f6d/trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv
- WIT = V2 cap 5 (the section 8 candidate, WITHOUT the legout-over-wick rule). 2024+: n=58, 43.1% [31-55], +Rs 15,681. results/c0b74c8/trades_wit_kite_2024_newbase_cap5_final.csv. No 2021+ run exists for this exact setting: the 2021+ WIT run (n=98, 36.7%) was made WITH legout-over-wick.
- MIT = V2 + legout-over-wick. 2021+: n=35, 48.6% [31-66], +Rs 13,330. 2024+ slice: n=19, 42.1% [21-63], +Rs 3,756. results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv
Baseline v1 (section 7) stays on file as the old reference. Report only; no live config changed.

## 12. Experiment (8 Oct 2026, report only): no demand (long) trade when price is coming down from a FRESH higher-timeframe supply zone (MIT: monthly or higher; WIT: weekly or higher), on the section 11 baseline
Definition (scripts/htf_supply_block.py): supply zone on W/ME/QE (QE+ME for MIT) = first touch of the zone is the "reaction"; "just" = reaction at most K bars of that timeframe before the entry bar (K=3 main, 1 and 6 sensitivity); not broken (no close above distal since); entry price below the zone's proximal. Filter of the existing lists, no re-run. Supply trades untouched.
- MIT 2021+ (35): rule blocks 2 (both wins, 2021-23); kept 33 = 45.5% vs 48.6%. 2024+ slice (19): rule did not fire.
- WIT 2021+ (98, plain V2, results/9a8a93d/trades_wit_kite_2024_v2_cap5_from2021_final.csv; identical result to the legout-over-wick run): blocks 10; kept 88 = 35.2% vs 36.7% (-1.5 pts, bootstrap -5 to +2); blocked 10 won 50.0%. 2024+ official list (58): blocks 9; kept 49 = 42.9% vs 43.1%.
Results: results/9a8a93d/supplyblock/. Not adopted.

## 13. R5 PERMANENT for WIT and DIT15 (8 Oct 2026): HTF base <= 0.6 x HTF legout (R42). MIT unchanged.
Expected new baselines (filter of the section 11 lists, 2021+; 2024+ slice in brackets; confirmed by a real re-run where noted below):
- WIT: 70 trades, 44.3%, +Rs 22,935 (2024+ slice: 39 trades, 53.8%, +Rs 21,967). Section 11 WIT baseline was 98 trades, 36.7%, +Rs 11,517 (59 trades, 42.4%, +Rs 14,898).
- DIT15 (strict HTF, LTF base <= 5): 195 trades, 34.9%, +Rs 14,201 (2024+ slice: 114 trades, 31.6%, +Rs 46). Section 11 baseline was 268 trades, 32.5%, +Rs 3,421 (147 trades, 28.6%, -Rs 11,740).
- MIT (V2 + legout-over-wick): unchanged, 35 trades, 48.6%, +Rs 13,330 (19 trades, 42.1%, +Rs 3,756).
The old (uncapped) section 11 baselines remain reproducible with --no-htf-cap.

## 14. CURRENT BASELINE SET v2 (user decision, 9 Oct 2026; supersedes section 11 for new comparisons). Both windows always (R33).
Section 13 estimates are now CONFIRMED by real re-runs: WIT and DIT15 trade lists equal the filter lists exactly (no replacement trades). Same scoring as before (replay result stands, ambiguous -> heuristic), gross, Rs 1,000 risk.
- DIT15 = strict HTF + LTF base <= 5 + HTF base <= 0.6 x legout (suffix _hc). 2021+: n=195, 68 wins, 34.9% [28-42], avg R +0.045, +Rs 14,201 (train n=155 33.5%; holdout n=40 40.0%). 2024+ slice: n=114, 31.6% [24-40], avg R -0.064, +Rs 46. results/e7ce9ba/trades_dit15_kite_2024_v2_cap5_sh_lw_hc_final.csv
- WIT = V2 cap 5 (no legout-over-wick) + HTF base <= 0.6 x legout (suffix _hc). 2021+: n=70, 31 wins, 44.3% [33-56], avg R +0.349, +Rs 22,935 (train n=57 40.4%; holdout n=13 61.5%, under 30). 2024+ slice: n=39, 53.8% [38-69], avg R +0.615, +Rs 21,967. results/e7ce9ba/trades_wit_kite_2024_v2_cap5_hc_from2021_final.csv
- MIT = UNCHANGED: V2 + legout-over-wick, no cap. 2021+: n=35, 48.6% [31-66], +Rs 13,330; 2024+ slice: n=19, 42.1% [21-63], +Rs 3,756. results/132d5d8/trades_mit_kite_2024_v2_cap5_lw_from2021_final.csv
Previous (uncapped) DIT15 / WIT baselines (section 11) stay reproducible with --no-htf-cap: DIT15 268 trades 32.5% +Rs 3,421; WIT 98 trades 36.7% +Rs 11,517.
Caveat: the 0.6 cutoff was chosen after seeing the data (overfitting tests: WIT p 0.011, DIT15 p 0.064); track both live with the cutoff frozen.

## 15. MIT target changed to 3R (user decision, 9 Oct 2026); DIT15 and WIT stay at 2R. Baseline set v3 (supersedes section 14 for MIT only).
Real MIT run from 2021 with the 3R target (same 35 trades as the 2R list; only target and exits differ), exit scoring as always (replay stands, ambiguous -> heuristic with +3R / -1R):
- MIT 3R 2021+: n=35, 16 wins, 45.7% [31-63], avg R +0.787, +Rs 25,507 (2R baseline: 48.6%, avg R +0.415, +Rs 13,330). 2024+ slice: n=19, 42.1%, avg R +0.678, +Rs 11,032 (2R: +Rs 3,756). Train n=32 +Rs 24,911; holdout n=3 +Rs 596 (2R: -Rs 245, under 30).
- results/65512a0/trades_mit_kite_2024_v2_cap5_lw_rr3_from2021_final.csv. The 2R list stays reproducible with --no-combo-rr (results/132d5d8/...).
- Evidence: 3R beat 2R on the 33 trades resolved at both (avg R +0.895 vs +0.501, bootstrap 95% +0.09 to +0.64, sign-flip p 0.04, chosen after looking, tiny sample); higher targets (4R-6R) did NOT hold up (walk-forward -6R out of sample, 2024+ slice collapses beyond 3R).
- WIT: 2R stays (2.5R -0.049 R vs 2R [-0.31,+0.16], 3R -0.127 [-0.47,+0.20], p 0.67 / 0.78); 1R, breakeven and scale-out also not better. DIT15: 2R stays (1R, breakeven, scale-out and 2.5R-6R all within noise of 2R).

## 16. FINAL BASELINES v4 (9 Oct 2026): every trade is now resolved - no AMBIGUOUS left (supersedes sections 11, 13-15 for the numbers; settings unchanged)
Change: the last-resort INTRA-MINUTE PATH RULE (RULES R45) replaces the legacy heuristic for trades still AMBIGUOUS after the 1-minute drill-down (all of them: no NO_MINUTE_DATA). Re-scored from cached Kite data, 0 new requests. Files: results/46f0556/.
- DIT15 (strict HTF, base <=5, HTF base <=0.6x legout, 2R): 2021+ n=195, 71 wins, 36.4% [30-43], avg R +0.122, +Rs 21,467. 2024+ slice n=114, 33.3% [25-42], +Rs 4,789. Train n=155 35.5% +Rs 11,639; holdout n=40 40.0% +Rs 9,828. (Heuristic version was 34.9% +Rs 14,201; of the 32 ambiguous trades 21 loss / 11 win, 3 differ from the old heuristic.)
- WIT (V2 cap 5, HTF base <=0.6x legout, 2R): 2021+ n=70, 32 wins, 45.7% [34-57], avg R +0.417, +Rs 27,506. 2024+ slice n=39, 56.4% [41-72], +Rs 25,546. Train n=57 40.4% +Rs 14,243; holdout n=13 69.2% +Rs 13,263 (under 30). (Heuristic version 44.3% +Rs 22,935; of 8 ambiguous: 6 loss / 2 win.)
- MIT (V2 + legout-over-wick, uncapped, 3R): 2021+ n=35, 16 wins, 45.7% [31-63], avg R +0.844, +Rs 27,485. 2024+ slice n=19, 42.1% [21-63], +Rs 13,010. Train n=32 46.9% +Rs 26,889; holdout n=3 33.3% +Rs 596. (Both ambiguous trades were gap-fills beyond the stop = filled and stopped at the open, R = 0, counted as losses.)
Files: results/46f0556/trades_dit15_kite_2024_v2_cap5_sh_lw_hc_final.csv, trades_wit_kite_2024_v2_cap5_hc_from2021_final.csv, trades_mit_kite_2024_v2_cap5_lw_rr3_from2021_final.csv. DZ_NO_INTRABAR=1 reproduces the older heuristic-scored numbers.

## 17. DIT15 LTF stop buffer = 0.2 ATR (user decision, 9 Oct 2026). Baselines v5 = v4 with this one change for DIT15; WIT and MIT unchanged (0.1 ATR).
Numbers below come from the stop-buffer TEST (scripts/stop_buffer_test.py): the SAME 195 entries re-scored with the stop 0.2 ATR beyond the base wick (target re-set to 2R of the new risk). NOTHING was re-run for this decision.
- DIT15 (strict HTF, base <=5, HTF base <=0.6x legout, 2R, buffer 0.2): 2021+ n=195, 73 wins, 37.4% [31-44], avg R +0.154, +Rs 25,259 (v4 with 0.1: 36.4%, +0.122, +Rs 21,467). 2024+ slice n=114, 36.0%, avg R +0.105, +Rs 9,035 (v4 +Rs 4,789). Train n=155 36.1% avg R +0.115 +Rs 15,576; holdout n=40 42.5% avg R +0.304 +Rs 9,683.
- By year avg R: 2021 +0.64 (19), 2022 -0.08 (24), 2023 +0.21 (38), 2024 +0.25 (38), 2025 -0.27 (36), 2026 +0.30 (40).
- Evidence quality: +0.032 R per trade vs 0.1 (bootstrap -0.06 to +0.11, sign-flip p 0.21), chosen after trying 5 values (0, 0.1, 0.2, 0.3, 0.5). Not significant: track live.
CAVEAT: the test kept the entries fixed. In a full DIT15 run the buffer is applied when the zone is built (config.DISTAL_BUFFER_ATR_BY_COMBO = {dit15: 0.2}), so the validity checks (clean departure, zone width) see the wider zone and the trade set can change slightly. The first full DIT15 run with suffix _db2 becomes the new reference; --no-combo-buffer reproduces v4.
WIT and MIT v4 numbers (section 16) stand: WIT 70 trades 45.7% +Rs 27,506 (2R, 0.1 ATR); MIT 35 trades 45.7% +Rs 27,485 (3R, 0.1 ATR).

## 18. Baseline v6 CANDIDATE (10 Oct 2026, branch exp-score-sector, NOT merged, live config unchanged): minimum zone strength 2. In-sample, not validated.
Rule: take a trade only if the LTF leg-out is strength 2 (gap out of the base, or >= 2 exciting candles). Flag `--min-strength N` in scripts/run_min_strength.py; default 0 = baseline v5. Freshness is not scored (constant for the baseline trades); time at base and EMA are not used (no consistent edge, see results/2d78520/overnight/REPORT_*.md).
Compared with baseline v5 (sections 16-17: DIT15 buffer 0.2, WIT, MIT), 2021+ entries, 15m replay + 1m drill-down, costs 0.20% of position value. Full list: results/2d78520/overnight/v6/REPORT_v6_min_strength_2.md.
- Pooled 3 combos: v5 n=300, 121 wins, 40.3% [35-46], avg R +0.296, +Rs 80,250 gross / +33,384 net. v6 n=140, 64 wins, 45.7% [37-54], avg R +0.446, +Rs 51,300 gross / +28,392 net. Dropped (strength 1): n=160, 57 wins, 35.6%. Kept + dropped = 300.
- Train (<2026): v5 n=244 38.5% -> v6 n=115 43.5% (+4.95 pts, JUST UNDER the +5 rule). Holdout 2026: v5 n=56 48.2% -> v6 n=25 56.0% (+7.79, under 30).
- DIT15: v5 n=195 37.4%, net -Rs 10,924 -> v6 n=100 43.0%, net +Rs 5,911 (train +3.1 pts, holdout n=21 57.1%). WIT: n=70 45.7% -> n=32 50.0% (train +9.6, holdout n=4 50.0% vs 69.2% = reversed). MIT: n=35 45.7% -> n=8 62.5% (under 30; no 2026 strength-2 trade).
- Evidence: bootstrap 95% of strength-2 minus strength-1 win rate: train +9.4 pts [-3.0, +21.5]; holdout +14.1 pts [-11.6, +39.7]. Chosen after about 90 filter/scope combinations on the same trades: treat as a candidate. Pooled n 140 passes the n >= 100 rule; the train +5 rule is missed by 0.05; costs: net P&L is lower than v5 overall (28.4k vs 33.4k) because it takes fewer trades.
- Baseline reproduction check (no flags, engine re-run vs repo): WIT 70/70 identical (32 wins), MIT 35/35 identical (16 wins), DIT15 v4 195/195 identical (71 wins); the DIT15 v5 (0.2 ATR) stop-buffer step was not re-run, v5 DIT15 numbers come from results/59497e3.
- SCOPE DECISION (user, 10 Oct 2026): keep the strength filter on DIT15 only (R51). Pooled v6 = DIT15 strength 2 (n=100) + WIT v5 (n=70) + MIT v5 (n=35): n=205, 91 wins, 44.4% [38-51], avg R +0.444, +Rs 79,362 gross / +50,219 net (v5: n=300, 40.3%, +80,250 / +33,384). Train n=168 41.1% vs 38.5% (+2.55 pts); holdout n=37 59.5% vs 48.2% (+11.25). Dropped n=95 (30 wins, 31.6%). 205 + 95 = 300. Misses the +5 train rule; candidate, in-sample, live config unchanged. Report: results/2d78520/overnight/v6/REPORT_v6_min_strength_2_only_DIT15.md.

## 19. BASELINE v6 = FINAL baseline (user decision, 10 Oct 2026): v5 + zone strength 2 on DIT15 only. Supersedes sections 16-18 as the current baseline.
- Rule: DIT15 takes only strength-2 trades (gap out of the base, or >= 2 exciting candles in the leg-out); WIT and MIT unchanged (WIT 2R, MIT 3R, DIT15 2R with 0.2 ATR buffer).
- Pooled 2021+: n=205, 91 wins, 44.4% [38-51], avg R +0.444, +Rs 79,362 gross / +50,219 net of 0.20% costs. DIT15 n=100 (43 wins, 43.0%, net +5,911); WIT n=70 (32 wins, 45.7%, net +18,887); MIT n=35 (16 wins, 45.7%, net +25,421).
- Train n=168 41.1%, +Rs 28,989 net; holdout 2026 n=37 59.5%, +Rs 21,229 net (under 40 trades). 2024+ slice n=116 47.4%, +Rs 34,346 net.
- Compared with v5 (n=300, 121 wins, 40.3%, net +33,384): +4.06 pts pooled, +2.55 train, +11.25 holdout. 205 kept + 95 dropped (DIT15 strength 1, 30 wins) = 300.
- CAVEAT stays: adopted by the user's decision, chosen in-sample after many filter/scope combinations on the same trades, misses the +5 train rule, bootstrap intervals for strength 2 vs 1 cross zero. Track on data after October 2026.
- Command: python scripts/run_min_strength.py compute DIT15|WIT|MIT, then python scripts/run_min_strength.py report. Files: results/2d78520/overnight/v6/.
