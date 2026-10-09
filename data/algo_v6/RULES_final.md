# RULES.md — every rule: definition, scope, reason, status

Written 2 Oct 2026 from the code (`code/`), the comments in it, and the chat history. Where something was not written down it says **not recorded**.
References like **C25** point to `corrections/CORRECTIONS_VERBATIM.md` (the user's own words). The user's corrections outrank everything in this file: if a rule here contradicts a correction there, the correction wins and this file is wrong.

Vocabulary the user uses (important, easy to get wrong):
- **legin** = the candle(s) just before the base. **base** = the small-bodied consolidation. **legout** = the explosive leg away from the base (the code calls the legout simply "leg").
- **proximal** = the zone edge nearest current price. **distal** = the far edge (the stop-loss side).
- **HTF** = higher timeframe, gives the bias zone. **LTF** = lower/execution timeframe, gives entry, stop and target. **trend timeframe** = a third, intermediate timeframe used only to classify trend.
- **DIT** = daily HTF, 2h trend, 60-minute LTF. **WIT** = weekly HTF, daily trend, 2h LTF. **MIT** = monthly HTF, weekly trend, daily LTF. (DIT's LTF was 15m at first; changed to 60m on 27 Sep because Yahoo caps 15m/30m at ~59 days.)
- **wick-to-wick** zone = proximal at the wick extreme of the base too (instead of the body edge).

Status key: **ACTIVE** (in the code and used) · **REJECTED** (tested, not adopted; result given) · **EXPERIMENTAL** (code exists behind a flag, default OFF) · **OPEN** (a correction exists that the code does not yet satisfy).

---

## A. Zone construction (`code/sd_zones.py`)

### R01 Impulsive leg ("legout") — ACTIVE
A candle with body ≥ `impulse_body_atr_mult` × ATR (default 1.3; MONTHLY_CONFIG 1.0; TREND config 0.8) that closes in the top/bottom 25% of its own range (`impulse_close_range_pct` 0.75). A leg may be several consecutive impulsive candles: `max_leg_candles` = 3 default, **2 on LTF** (`LTF_ENTRY_CONFIG`), 4 on the trend config. ATR is Wilder, period 14.
Why: user directive 22 Sep — "we will only take a trade if the lower tf has a clear explosive candle (signifying buying) or 2 candles even better" (C07). A 3-candle LTF leg is not accepted.

### R02 Base = walk back from the leg — ACTIVE (definition of "base candle" is OPEN, see R20)
Start at the candle before the leg and walk backward collecting contiguous candles with **body ≤ `base_body_atr_mult` × ATR** (0.5 default; 0.7 on the trend config). The walk stops at the first candle that fails, or when `max_base_candles` is reached. The cap **truncates** the base; it never rejects a zone for being too long.
Caps: **LTF 3** (default; user: "base candles are 3 or less cant be more than that", C07). **HTF 5** (WEEKLY_CONFIG / MONTHLY_CONFIG; was 8, cut to 5 on 27 Sep after "keep a limit of 5 base candles in htf", C17). Trend config inherits 5.
HTF-only extras in the walk: **range-growth cap** `base_extension_atr_mult` = 0.15 × ATR (a candle is not added if it grows the base's high-low range by more than that), and the code comment says a single-candle range cap `base_candle_max_range_atr_mult` is "set explicitly" on WEEKLY/MONTHLY — **in the actual code it is `inf` (no cap)**, i.e. the comment is wrong or the setting was lost (see STATUS).
Why the growth cap exists: fixes HTF proximal lines that were too low (NTPC, TCS, UPL, HINDALCO, 23 Sep); verified not to regress TECHM/POWERGRID.

### R03 Zone lines — ACTIVE
Demand: proximal = highest body edge (open/close max) of the base candles, distal = lowest wick of the base, pushed further out by a buffer `distal_buffer_atr_mult` = **0.1 × ATR** (all configs). Supply is the mirror image.
Why the buffer: user directive 25 Sep — "keep some gap bw wick and sl ... a lot of times the zone just gets swept and then rally comes ... only a little" (C13). The user's per-trade stop corrections (C17: "ADANIPORTS sl shudve been 1703", "KOTAK sl 399.1") were about this.

### R04 Wick-to-wick only on the execution timeframe — ACTIVE
If the legout is "strong" (R05) the **LTF** zone's proximal is drawn at the base's wick (wick-to-wick) instead of the body edge. **HTF and trend zones are never wick-to-wick**, `detect_zones(..., allow_wick_to_wick=False)` for them. User, 26 Sep, in capitals: "UR NOT SUPPOSED TO KEEP HTF wick to wick ever only execution timeframe gets wick to wick" (C18). Earlier (25 Sep, C13): a good explosive legout or 2 strong legouts → mark wick to wick.

### R05 Strong legout — ACTIVE as a quality signal, NOT a filter
`has_strong_legout` = the leg's anchor candle gapped open beyond `legout_gap_atr_mult` × ATR vs the prior close (1.0 default; 0.5 on HTF configs), OR the leg absorbed a second impulsive candle. User, 23 Sep: "a gap and 2nd strong legout is definitely a good thing but it shouldnt be a rule, its okay if it isnt there" (C12). On 26 Sep a backtest showed HTF strong-legout trades far better (+Rs 277/trade vs −Rs 82), only ~22% qualified, so the HTF gap bar was halved, "not too restrictive" (C14). Measured under the buggy exit (see DECISIONS).

### R06 Zone validity — ACTIVE
A candidate must also pass: base range ≤ `max_base_range_to_leg_range` × leg range (default 0.5; HTF configs 1.5; trend 2.5); clean departure (no leg candle wicks back past the distal by more than `departure_tolerance_atr_mult` × ATR: 0 default, 0.25 HTF, 0.4 trend); zone width ≥ `min_zone_width_atr_mult` × ATR (0.5 default, 0.4 HTF, 0.2 trend).

### R07 Rule 1 — legout must CLOSE beyond the legin candle — ACTIVE, LTF only
`require_legout_beyond_legin=True` on `LTF_ENTRY_CONFIG` only. The candle closing the leg must close above the legin candle's high (demand) / below its low (supply), where legin = the single candle just before the base. From the GTF reference notes p.24 ("legout candle should be closed above legin"). Tested isolated 29 Sep, adopted permanent 29–30 Sep. User: apply to the LTF/execution role only, never HTF/trend.

### R08 Freshness / "tested" — ACTIVE
`apply_freshness`: scan forward from the candle after the leg ends; the **first candle whose low (demand) / high (supply) reaches the proximal marks the zone tested** and that candle is the **entry candle** (`tested_at_index`). Based on the proximal (body edge), not the wick.

---

## B. HTF–LTF pairing (`code/mtf_zones.py`, `match_zones`)

### R09 Pairing — ACTIVE
One result per HTF zone: the best LTF candidate that (1) has the same type; (2) **formed during the HTF zone's own formation window** (HTF base start date → HTF leg end date) — i.e. the LTF zone is the LTF-resolution view of the same move, *not* a later retest (the founding correction, SBIN, C01/C02); (3) was **still untested at the moment the HTF zone finished forming** (`confirm_cutoff`); (4) at least `MIN_LTF_OVERLAP_FRAC` = **0.30** of the LTF zone's range lies inside the HTF zone (user: "keep a 30+% overlap", C09); (5) trend is not against the trade at the moment of entry (R11). Among candidates the most recently formed wins, overlap breaks ties.
Entry = the LTF zone's first touch after HTF confirmation (R08). Stop = LTF distal. Target = entry ± 2 × risk.

### R10 HTF zone must be fresh on its WICK — ACTIVE (wick-freshness; made permanent 30 Sep)
If price had already reached the HTF base's **true wick extreme** (demand: `base.high.max()`; supply: `base.low.min()`) before the LTF entry date, the HTF zone is used up and the trade is not taken. Implementation: `_htf_wick_tested_at` replaces the old proximal-based `hz.tested_at_timestamp` in `match_zones`.
Precise user wording: a touch of the HTF wick that **rallies/drops away and later returns** invalidates; a single continuous visit running through the wick into the body counts as one touch and the zone stays fresh (C28: "if it tocuhes wick rallies then again comes down and tocuhes body then it isnt okay" / "if it directly comes down and touches body straight after wick its okay"). The user's blunt version: "MAKE IT A RULE IF TESTED ON HTF AND MOVE HAS COME ZONE IS INVALID" (C25). Examples: USHAMART (HTF wick 371.70 tapped Nov 2024), GODFRYPHLP (wick 3276, Sept 2025 low 3136), INDIGO, BPCL, RAILTEL.

### R11 Trend — ACTIVE
Trend is read on the intermediate timeframe from **zone breaks**, using deliberately loose "bad zone" detection (`TREND_ZONE_CONFIG`): "if price breaks 2 sz its uptrend, 2 dz downtrend, 1 sideways" (C09/C10). Events = a trend-timeframe zone's close beyond its distal. State machine (`_classify_trend_from_events`): sideways → needs 2 consecutive same-direction breaks to become up/down; **one break against a confirmed trend drops it to sideways at once**; a close at an all-time high forces "up". Filter is **asymmetric**: a demand trade is blocked only by a confirmed downtrend, a supply trade only by a confirmed uptrend; sideways blocks neither (derived from the 9 annotated charts: ONGC rejected as supply in uptrend; BAJFINANCE/MAXHEALTH/IKS/LAURUSLABS/KEI/ORIENTCEM/MASTEK/MANAPPURAM demand in sideways/up were good).
Applied twice: at HTF formation (`filter_zones_by_trend_3tf`) **and again at the LTF entry moment** (added 28 Sep, "stale-trend fix": MIT 40 → 27 trades; user's examples GODREJPROP, NTPC, BAJAJ-AUTO "trend became down by the time price arrived").
Trend timeframe per combo: DIT 2h ("for trend we check 2h not 1h", C15), WIT daily, MIT weekly.

---

## C. Trade, sizing, exit (`code/mtf_backtest.py`)

### R12 Exit — ACTIVE (corrected 1 Oct) — **heuristic, not exact**
User rule: **"THE PRICE SHUD FIRST ENTER ZONE and then only target and sl is enabled"** (C45). The old loop started on the entry candle and tested that candle's full high/low for the target, so a target touched *before* price entered the zone counted as a win. Fixed in `simulate_exit`: the stop is checked first on every candle; on the **entry candle only**, the target counts only if the candle's direction fits the path entry→target (demand needs a bullish candle, supply a bearish candle). Validated against 5-minute bars on 16 recent trades: fixed rule agrees on 15, old rule on 11. Known miss: SUNTV 2026-09-11 (rule says loss, 5-minute data says win). A genuinely correct rule needs intra-candle data. See `golden/golden_exit_cases.csv`.

### R13 Sizing and capital — ACTIVE
Capital Rs 1,00,000 per combo; max loss per trade Rs 1,000; shares = min(floor(1000/risk), floor(100000/entry)); R:R fixed 2:1; concurrent trades allowed with total deployed ≤ Rs 1,00,000 (`run_capital_constrained`). **All baselines quoted in this pack are "all triggered signals, no capital limit"** (user, 28 Sep: "remove the fund restriction for now take all the trades i just wanna see the winrate"). WIT and MIT use a 730-day lookback on entry date; DIT has none (its data is already ~729 days).

### R14 Train / holdout — ACTIVE (process rule)
Entries before **2026-01-01** = train (may be tuned on), on/after = holdout (confirm only). Do not tune on holdout.

---

## D. Tested and REJECTED
(Result figures were measured under the old buggy exit unless stated; see DECISIONS.md.)

| ID | Rule | Result | Status |
|---|---|---|---|
| X01 | **Rule 2: use the legin candle's wick as distal if more extreme than the base's** | DIT Rs 88,225 → 73,313; WIT Rs 20,581 → 11,982; only MIT improved | REJECTED, code deleted |
| X02 | **LTF base cap 3 → 5** (user asked for it 1 Oct) | DIT n 213, 45.1%, Rs 58,003 vs 207, 48.3%, Rs 67,161 (buggy exit). Corrected exit: DIT avg R −0.058 → −0.070, WIT −0.280 → −0.217, MIT +0.227 → +0.350 = roughly a wash | REVERTED to 3; weakly justified |
| X03 | **Strong-LTF override**: re-admit a wick-freshness-rejected trade if its LTF has one explosive candle or 2 clean candles and ≤2 base candles | 11 wins / 13 losses on the added trades, no edge | REJECTED, scratch code deleted |
| X04 | **EMA20/EMA50 inside the zone / above-below price filters** (several versions) | EMA-in-zone trades: DIT n=19, 21% win, −Rs 5,742; "aligned" direction rule: DIT 3 trades all losses, WIT zero aligned; independent-EMA versions A/B/C: aligned trades 26.9% win. User: "no point in this ema thingy scrap it" | REJECTED |
| X05 | **Wider SL (distal buffer sweep 0.1 → 1.0)** | Started 28 Sep on 200 tickers; trade counts 131/158/180 for 0.1/0.2/0.3; final table **not recorded**. The user lists "SL-widening" as rejected | REJECTED; 0.1 × ATR kept |
| X06 | **GTF reference bot's multi-timeframe approach** | User reviewed its trades: "absolutely dogshit ... barely any htf confluence"; discarded 22 Sep | REJECTED |
| X07 | **Symmetric trend rule (exact match only)** | Wrongly blocked every sideways demand trade in the 9 examples | REPLACED by R11 asymmetric |
| X08 | **Congestion/"envelope" base count**, cap-based rejection (several versions) | Rejected 21–25 of 25 WIT trades; the rejected group was the *better* group (61.9% win) | REJECTED |

## E. EXPERIMENTAL

### E01 `reject_long_base` — flag in `ZoneConfig`, default OFF
Counts the whole consolidation before the leg with a flexible rule (a "small" candle has body ≤ 50% of its own range and always counts; an "exciting" candle counts only if it closes inside the band of the small candles), and **rejects** the zone if the count exceeds `max_base_candles`. It reproduces the user's three pen-circled counts only loosely (Bandhan 8 vs ~20, BoB 52 vs ~20, ICICIGI 8 vs 7) and on WIT it removes 22 of 25 trades (13 of them winners), leaving 3 losers. Not adopted.

## F. OPEN — user corrections the code does not satisfy

### R20 What counts as a base candle — BUILT 2 Oct 2026 behind --new-base (see section G); NOT yet backtested (the main correction)
The user counts the *whole consolidation* as the base and says all six WIT review screenshots have 7+ base candles (Bandhan ~20, Bank of Baroda ~20, ICICIGI 7 on weekly, Fincables over 3, Dalbharat 5). The code counts 1–2 for each, because the walk stops at the first candle with body > 0.5 × ATR (e.g. BoB: the candle just before has body 6.02 vs a 1.55 limit) and, on HTF, at the 0.15 × ATR range-growth cap (ICICIGI: the 31 May candle adds 85 vs 15 allowed). The user's own definition, said once and then called "not a good way to say it": **base candle = small candle, body < 50% of its high-low range; "exciting" candle = body > 50%** — and they want something *flexible*. They said they would send annotated screenshots defining base / legin / legout. **Not yet received.** The rule to build once defined: LTF base ≤ 3 candles and HTF base ≤ 5, **reject** the zone when longer (do not truncate), with the stop at the far wick of the whole base.

### R21 Stop at the far wick of the whole base — OPEN
NAUKRI: user says the SL "shudve been at wick of last base candle which is around 1463"; code stop 1448.78, and a whole-run geometry test gave the same 1448.78, so the user's 1463 is not reproduced. FINCABLES: "put the sl at the end of base candles in this case 1108" (code 1146.40). BEL: "kept sl at around 396".

### R22 LTF zone already tapped before it formed — OPEN
MRPL (C25): "THE LTF WAS ALR TAPPED on wick EVEN BEFORE THE ZONE WAS FORMED MAKING IT INVALID KINDLY DFI THIS". No specific code is recorded for this.

### R23 HTF zone should include its own base candle — OPEN
BEML (C25): "htf shudve been 1753 which wudve been a win cuz base candle of htf was there". Same family as the earlier BAJAJFINSV ("htf proximal shudve been 1940 cuz there was a base candle on top") and ADANIPORTS ("htf proximal shud be 1764"). The R02 growth cap is the suspected cause; not re-checked against these.


## G. Corrections of 2 Oct 2026 (user: `mit review.docx` and `photos imrove/`; tests in tests/golden/base_candle_cases.csv, tests/test_base_candles.py)
Code: `src/base_candles.py`, constants in `config.py`. Off by default; runners switch it on with `--new-base` (output files get the suffix `_newbase`). Legacy files are not edited; the logic is patched in at run time.

### R24 Base candle = wick test OR small-move test — BUILT (not backtested)
User: "if wick > 50% of body ... that is a base candle, or even if it is a small move it is a base candle; this is an OR operator, both cases are included."
A candle is a base candle if it is not impulsive AND (total wick, upper + lower, is more than 0.5 x its body OR its body is at most 0.5 x ATR). "Wick" is read as upper + lower wick; "small move" as the legacy body <= 0.5 x ATR test. Both readings are assumptions to confirm.

### R25 Count the whole consolidation; reject if longer than the cap — ADOPTED as default (base logic V2)
The whole contiguous run of base candles before the legout is counted (plain count; nothing hides behind the cap). Count above the cap -> zone rejected. Caps: HTF 5, LTF 5 (config.LTF_BASE_CAP; legacy truncated to LTF 3 / HTF 5 and accepted). V2 is the default (config.BASE_LOGIC_V2 = True); `BASE_LOGIC_V2 = False` or the runner flag `--legacy-base` reproduces Baseline v1 exactly; `--ltf-cap=N` tests another LTF cap (8 was tested first).
User's earlier verdicts that cap 5 now contradicts (known gaps in tests/golden): RVNL daily (7 base candles, "very very good") and KPITTECH B7 (user count 6, plain run 8) are rejected; ACC daily (15) was already rejected. Evidence used earlier: good LTF counts 8 (KPITTECH B7), 7 (RVNL), 5 (CONCORDBIO); bad 11 (KPITTECH A2), 12 (COFORGE), 15 (GLAND B6), 20 (CHOLAHLDNG).
Identical zones (same type and lines) from two adjacent legouts are kept once (earliest), so one trade cannot be counted twice (ARE&M 2025-04-07).

### R26 Zone lines — BUILT (not backtested)
LTF zones: lines from the nearest 3 base candles (this reproduces the lines of the user's good ACC, RVNL, CONCORDBIO trades). HTF zones: nearest candles of the run while each added candle grows the base's high-low range by at most 0.4 x ATR (legacy 0.15, which made most HTF bases one candle); far wick of the used candles = distal. Checks: FLUOROCHEM 3066/2489 vs user 3050/2450; IRCTC 988.5/852.3 vs user ~985/868; RVNL, ACC, CONCORDBIO (HTF), MANAPPURAM unchanged and within 1-3% of the user's boxes.
Leg back-absorption stays legacy: a directional candle just before the legout (body > 0.5 x ATR) belongs to the leg even if it has wicks (ACC Dec 2023).

### R27 A base candle must not be huge; the base must be small next to the legout — BUILT (not backtested)
Base candle range <= 2.5 x ATR. HTF base range <= 1.25 x legout range (legacy 1.5; the 2026-09-19 "HTF bases may be wide" directive is superseded by the MRPL correction: "the base candle is so big and the legout so small"; MRPL 1.31 and IRCTC's old marking 1.34 are above it). LTF base range <= 0.6 x legout range (legacy 0.5; CONCORDBIO daily, called genuinely very good by the user, is 0.57). Thin evidence for all three numbers.

### R28 OPEN, not explained by the base logic
Legout test (R01): the user's good photo zones that never appear have a legout candle that is not "explosive" by the numbers. IKS monthly July 2026: body 0.57 x ATR (monthly needs 1.0), close at 68% of its range (needs 75%). MASTEK monthly July 2026: body 0.71 x ATR (needs 1.0; close position 0.82 passes). LAURUSLABS daily 29 Jun 2026: body 1.22 x ATR (needs 1.3), close position 0.62 (needs 0.75); the 26 Jun 2026 bar is missing in the frame. With no explosive candle no legout, so no zone and no trade. The opposite case: CG POWER's legout (monthly body 1.11 x ATR) is accepted and the user calls it barely explosive. GRANULES weekly: 7 wicky candles before the leg, over the HTF cap of 5. IRCTC: LTF should be wick-to-wick (not changed).

### R29 User review of the 15 sample zones (basecandlefix.docx, 2 Oct 2026) — resolved
Confirmed: A1 GLAND weekly (1 candle), A4 VBL, A5 RAMCOCEM, B7 KPITTECH (count good), B8 ULTRACEMCO monthly (5), C12 KPITTECH weekly and C13 RAMCOCEM daily rejections. Wrong: B6 GLAND daily (10+ candles) and A2 KPITTECH daily (almost 20); both are now rejected by R25. User withdrew his A2 "zone low 1328" note. A3 ULTRACEMCO: the user's zone 12650-13112 (formed March 2026) matches ours (12423/12951) once the roughly 2% price-scale difference between his chart and Kite data is allowed for. Small known line differences from the same cause: GLAND weekly distal 1798.0 vs his ~1809. Golden cases B20-B28.

### R30 2 Oct 2026 — decision
LTF base cap 5, base logic V2. Adopted by user decision on chart judgement. Test result vs Baseline v1: WIT 43.1% vs 41.3%, MIT 44.4% vs 41.7%, intervals include zero. DIT15 not rerun under cap 5.
2 Oct 2026 (follow-up): DIT15 rerun under LTF cap 5: 184 trades, 26.1% vs Baseline v1 29.9% (-3.8 pts, bootstrap 95% -12 to +5, includes zero); train 22.1%, holdout 32.4%. WIT, MIT and DIT15 are now all tested under V2 cap 5.

### R31 HTF: the legout must close over the base wick — BUILT, default ON (config.HTF_LEGOUT_CLOSE_BEYOND_BASE_WICK; runner --no-legout-wick turns it off)
User, 2 Oct 2026 (MIT review): "Legout has to close over the wick of base in HTF!" Demand: the HTF legout's closing candle must close above the highest high of the base candles; supply: below their lowest low (the LTF already has the legin version of this, R07). HTF only. Tests B29 (RPOWER demand 2025-03: legout close 43.0 vs base high 48.5) and B30 (EMAMILTD supply 2024-01). Effect check without a rerun: it rejects 20 of 808 monthly zones in a 120-ticker scan, and none of the 18 trades in the MIT cap-5 list fail it. The cap-5 candidate lists (STATUS section 8) were produced BEFORE this rule; output files of runs with the rule carry the suffix _lw.

### R32 MIT review of the taken trades (user, 2 Oct 2026; tests/golden/mit_trade_verdicts.csv)
Very good: NEULANDLAB, HINDCOPPER, DEVYANI (very close loss), ASAHIINDIA, CRISIL, NEWGEN, SUNPHARMA, ARE&M (good); ok: LUPIN, DATAPATTNS. The review of the rejected (removed) MIT trades: "overall good, no changes as such".
Not good / wrong, all OPEN:
1. CGPOWER (not that good): the user sees a full garbage area, 29 Jan to 19 Mar 2024 (37 daily candles between 420 and 495). Our LTF count was 5 because the plain run of base candles is broken by one bigger candle. Same family as GLAND B6, KPITTECH A2 and ACC: the user counts the whole range; the code counts an unbroken run. A rule for "time spent in the area" is needed.
2. CCL (not a good trade): same family, not yet analysed.
3. DEEPAKFERT stop: the user wrote "above 950"; Kite highs in Jan-May 2024 are only 708.8 and the entry is 615.9, so 650 is likely. LTF lines use the nearest 3 base candles (stop 645.6); using all 5 counted candles gives 653.6 (R21, far wick of the whole base). Needs the user's confirmation before changing the line rule.
4. TMPV HTF proximal looks wrong to the user: the proximal 681.4 is the June 2024 monthly close (candle O 663.0 H 695.6 L 589.0 C 681.4, Kite). Our Kite series for TMPV sits about 11-13% above his TradingView chart for 2024 (his box 515-613 against our 582-681), most likely a different corporate-action adjustment for the 2025 demerger. Data issue, not zone logic (to confirm).
5. NEWGEN: the user wants one more LTF entry at 1135-1296 in the same HTF zone. Today the matcher takes one LTF zone per HTF zone (R09); allowing several needs a decision.

## Reporting rule (user correction, 3 Oct 2026)
R33. Whenever the user asks for 'the baseline' (or baselines), always give BOTH windows: entries from 2024-01-01 (Baseline v1, plus the v2 candidate if relevant) AND entries from 2021-01-01 (the long runs), for every combo that has both (MIT, WIT, DIT15/DIT, QIT where it exists). Name the file/commit used for each, and say plainly when a combo has no 2021 run yet. Golden case: tests/golden/reporting_rules.csv.
R34. The DIT15 2021+ strict-HTF run (results/4d02f6d) is part of the baseline set from 5 Oct 2026 (user request): every baseline report lists MIT, WIT and DIT15 for both windows (2024+ and 2021+), with the DIT15 2021+ strict run included. Golden case: tests/golden/reporting_rules.csv.
R35. Baseline set from 7 Oct 2026 (user): DIT15 = strict HTF + LTF base <=5; WIT = V2 cap 5 (no legout-over-wick); MIT = V2 + legout-over-wick. Compare every new run against this set (STATUS section 11), both windows (R33), and name it.

## WIT cap-5 review corrections (user, 8 Oct 2026; golden cases: tests/golden/wit_review_cap5_cases.csv). All implemented as OPT-IN runner flags (default OFF), run with scripts/run_wit_fixes.py
R36. LTF zone lines come from the WHOLE base run (up to the cap), not the nearest 3 candles. ACE supply: stop must be 1418.00 = high of the 4th base candle (we had 1407.11). Flag --ltf-lines-all.
R37. A same-direction candle with body > 0.5 ATR right before the legout belongs to the leg even when that makes the LTF leg 3 candles. IRFC demand: proximal ~157.98 (body tops before the 17 May gap-up candle), we had 161.40. Flag --leg-absorb.
R38. If the top LTF zone breaks (price trades through its distal at/after its entry bar), a lower, still fresh LTF zone of the same HTF zone may be taken (first touched at/after the break). NAVINFLUOR: 3596 / 3533. Flag --lower-zone (run_wit_fixes.py only).
R39. Reject an LTF zone whose base drifts into the legout: (last base close - first base close) / ATR >= 0.9 in the trade direction. KFINTECH 1.00, IRFC 0.99; every trade the user called good is <= 0.45. Flag --base-drift (config WIT_FIX_BASE_DRIFT_ATR).
R40. HTF base range must be <= 0.8 x the legout range (was 1.25). LALPATHLAB weekly 0.87 (user: bad); every HTF zone the user called good is <= 0.71. Flag --htf-base-leg (config WIT_FIX_HTF_BASE_TO_LEG).
R41. NOT applied yet (need user input): BAYERCROP HTF 'very bad' (no measure explains it); JSWDULUX base wick; LICHSGFIN LTF legout not explosive; stop direction (ACE wants wider, GLENMARK 1027 tighter, ZYDUSWELL no number); RBLBANK trend is down but engine label is sideways (sideways passes for demand); ULTRACEMCO/price-scale differences are data, not logic (TradingView vs Kite ~2%).

## R5 made permanent for WIT and DIT15 (user decision, 8 Oct 2026; golden case: tests/golden/reporting_rules.csv R42)
R42. PERMANENT: in the WIT and DIT15 runners the HTF base range must be <= 0.6 x the HTF legout range (config.HTF_BASE_TO_LEG_BY_COMBO = {wit: 0.6, dit15: 0.6}). MIT is NOT capped (the cap lowered MIT money at every cutoff tried). Output files carry the suffix _hc.
 Evidence (filter of the existing lists, 2021+): WIT 98 -> 70 trades, 36.7% -> 44.3%, +Rs 11,517 -> +Rs 22,935; DIT15 268 -> 195, 32.5% -> 34.9%, +Rs 3,421 -> +Rs 14,201. Overfitting tests: WIT permutation p 0.011 (0.004 corrected for choosing the cutoff), DIT15 p 0.064 (0.106 corrected). WIT is convincing, DIT15 only plausible; the cutoff was chosen after seeing the data, so it must be tracked live on new trades with the value frozen.
 --no-htf-cap reproduces the older (uncapped) baselines. The experiment scripts (run_tradescore.py, htf_supply_block.py, trend_strict_filter.py, wit_fix_report.py) do not apply the cap.
R43. Baseline set v2 from 9 Oct 2026 (user): DIT15 = strict HTF + LTF base <=5 + HTF base <=0.6x legout; WIT = V2 cap 5 + HTF base <=0.6x legout; MIT = V2 + legout-over-wick, uncapped (unchanged). STATUS section 14. Supersedes R35 for new comparisons: name this set, both windows (R33), and mention the older uncapped baselines only when asked.
R44. Reward-to-risk target per combo (user, 9 Oct 2026): MIT = 3R, DIT15 = 2R, WIT = 2R (config.REWARD_RISK_BY_COMBO = {mit: 3.0}; default 2.0). MIT output files carry the suffix _rr3; --no-combo-rr restores 2R. The legacy heuristic exit (ambiguous trades) uses the combo's multiple (+3R for MIT). 3R was chosen after seeing the data on 33 trades: track it live. Baseline set v3: STATUS section 15.
R45. Exit scoring has NO unresolved trades (user, 9 Oct 2026): a trade still AMBIGUOUS after the 1-minute drill-down is resolved from the open/high/low/close of that one minute with the TradingView convention: the price travels from the open to the NEARER extreme first, then to the other extreme, then to the close (O-H-L-C if high-open < open-low, else O-L-H-C). The path decides whether the entry filled before the target (target touched before the entry fill does not count), and stop vs target order. A gap-fill that opens beyond the stop is filled and stopped at the open (R = 0, counted as a loss). The legacy heuristic is no longer used for baselines. DZ_NO_INTRABAR=1 reproduces the old scoring. Tests: tests/test_exits_intrabar.py. Baselines v4: STATUS section 16.
R46. DIT15 LTF stop buffer = 0.2 ATR (user, 9 Oct 2026); WIT and MIT stay at 0.1 ATR (config.DISTAL_BUFFER_ATR_BY_COMBO = {dit15: 0.2}; suffix _db2; --no-combo-buffer restores 0.1). Chosen from a same-entries re-score, not a full re-run (+0.032 R, not significant, best of five values): track live. Baselines v5: STATUS section 17.

R47. Overnight experiment discipline (user, 9 Oct 2026, branch exp-score-sector, scripts/overnight_*.py): candidates are judged on TRAIN (entries before 2026-01-01) only; the 2026 holdout is shown once, only for the candidates chosen on train; adopt only if the win rate improves by >= 5 points in BOTH train and holdout AND the variant has >= 100 pooled resolved trades; report how many variants were tried; flag n < 30; bootstrap 95% intervals; counts must add up; if nothing passes say "nothing passed". All new logic is opt-in (new files, nothing in config.py, src/ or the engine changed), so the baseline reproduces with no flags. The 1,500-request cap and the report-only rule were waived for this one run only.
R48. Handbook trade score (GTF notes pages 34-35, 41): freshness 3 / 1.5 / 0 (HTF zone with 0 / 1 / 2+ prior visits of price into it before the visit that holds the entry), strength 2 (gap, or 2 exciting candles) / 1, time at base 2 (1-3 boring candles) / 1 (4-5) / 0 (more than 5), +1 if the 20 or 50 EMA runs through the zone on the execution timeframe, no trade below 5. Baseline trades have an untested HTF zone and a base of at most 5, so their basic score is always 5-7 (freshness 3 + strength 1-2 + base 1-2); thresholds above 5 are what bite.
R49. Entry types (GTF notes pages 36-37): type 1 = limit at the proximal line (the baseline entry); type 2 = after a candle closes inside the zone, enter at the open of the next candle if it opens inside the zone; type 3 = after a candle closes inside the zone, the next candle must close outside the zone on the trade's side (demand: above the proximal line), enter at the open of the candle after it. Stop = the baseline stop, target = RR x the new risk (2R, MIT 3R); the setup dies when a candle closes beyond the stop side or after 28 days. Score 7 -> type 1, 5-6 -> type 2 or 3, below 5 no trade. Sector rule: the sector index is in a same-side zone at any of daily/weekly/monthly (plain legacy HTF settings, touched within the last 3 HTF bars, not broken through, bars before the entry day only); used as a +1 score bonus or as a hard filter. Tests: tests/test_overnight.py.
R50. Baseline v6 CANDIDATE: minimum zone strength 2 (user, 10 Oct 2026, branch exp-score-sector, scripts/run_min_strength.py, flag --min-strength N, DEFAULT 0 = baseline v5 unchanged, live config NOT changed). Zone strength = LTF leg-out: 2 = gap out of the base or >= 2 exciting candles, 1 = one exciting candle (same definition as trade_score_components.py). Chosen IN-SAMPLE after about 90 filter/scope combinations on the same 300 trades; pooled train gain +4.95 pts (just under the +5 rule), holdout +7.79 (n=25), bootstrap intervals cross zero: record it as "candidate, not validated". Freshness is NOT scored (every baseline trade has a fresh HTF zone, it is a constant), time at base and EMA are not used. Adopt into the live config only after it holds on data after October 2026 or the user says so. Counts must add up: kept + dropped = candidates (140 + 160 = 300).
R51. v6 candidate scope = zone strength 2 on DIT15 ONLY (user, 10 Oct 2026): `python scripts/run_min_strength.py report --min-strength 2 --only=DIT15`; WIT and MIT keep every v5 trade (their strength-2 samples are 32 and 8, too small). Still a candidate, in-sample, live config unchanged. Pooled 2021+: n=205 (DIT15 100 + WIT 70 + MIT 35), 91 wins, 44.4% vs v5 40.3% (+4.06 pts); train 41.1% vs 38.5% (+2.55); holdout n=37 59.5% vs 48.2% (+11.25); net of 0.20% costs +Rs 50,219 vs +Rs 33,384. Kept + dropped = 205 + 95 = 300. Misses the +5 train rule: not validated.
R52. BASELINE v6 is FINAL (user, 10 Oct 2026): v5 + zone strength 2 on DIT15 only (R50-R51). `python scripts/run_min_strength.py report` (no flags) = v6; `--min-strength 0` = v5. Pooled 2021+ n=205, 91 wins, 44.4%, +Rs 79,362 gross / +50,219 net; train 41.1% (+2.55 vs v5), holdout n=37 59.5% (+11.25). Adopted by the user's decision although it misses the +5 train rule: it stays labelled in-sample / not independently validated, so track it on new data after October 2026. config.py and src/ are unchanged (editing them would invalidate engine checkpoints); the strength rule lives in scripts/run_min_strength.py. Work is on branch exp-score-sector, not merged to main.
