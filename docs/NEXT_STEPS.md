# NEXT_STEPS.md (updated 3 Oct 2026)

## RUN IN PROGRESS: DIT15 from 2021, strict HTF legout (resume here after a crash)
What: HTF daily, trend 2h, LTF 15m, entries from 2021-01-01, base logic V2, LTF base cap 5, HTF cap default, `--strict-htf` (body >= 1.35 ATR, close in outer 22%; removes about 21% of trades, calibrated by scripts/htf_legout_calibration.py). The LTF cap-3 result = the subset of these trades with ltf_base_count <= 3.
Resume (per-ticker checkpoints in data/cache/checkpoints/dit15_v2_cap5_sh_lw, a rerun skips finished tickers):
  powershell -NoProfile -File scriptsun_dit15_strict_chain.ps1        (pipeline, 3 workers low priority, then exit scoring)
Kite session expires daily: run `python kite_login.py` in a normal terminal if the exit scoring says "run kite_login.py".
After it finishes: add base counts with
  python scripts/add_base_counts.py dit15 --file=<results/.../trades_dit15_kite_2024_v2_cap5_sh_lw_final.csv> --frames=kite_frames_dit15_long --long --strict-htf --workers=3
then report: all trades (cap 5), LTF base <= 3 (cap 3), by year 2021-2026, train vs holdout, bootstrap, vs the unstrict 2024+ DIT15 cap-5 list (results/9739e07, 184 trades, 26.1%).
Other data: data/cache/kite_frames_dit15_long (1d, 60m, 15m from 2020-11), kite_frames_wit_long (1d, 60m from 2020-11), kite_frames (originals).
Backups: scripts/backup.ps1 mirrors code, docs, results, checkpoints and data caches to E:\dz_backup (skips .env); scripts/backup_loop.ps1 repeats it every 30 minutes during a run.

Flags (scripts/_base_flags.py): --legacy-base, --ltf-cap=N, --htf-cap=N, --strict-htf, --no-legout-wick, --from=YYYY-MM-DD.
Finished runs this session: MIT 2021+ (35 trades, 48.6%), WIT 2021+ (98, 36.7%), QIT 2021+ (17, 31.2%), DIT15 cap5 2024+ (184, 26.1%); see docs/STATUS.md section 8 and the commit log.

---
(older notes below)

# NEXT_STEPS.md (saved 2 Oct 2026, evening)

## Where things stand
- Baseline v1 (user trade review IN PROGRESS), Kite data, 15m then 1m exit: docs/STATUS.md section 7, files results/53aecde/baseline_v1_{dit15,wit,mit}.csv.
- Base logic V2 (LTF cap 5, HTF cap 5) is now the DEFAULT (config.BASE_LOGIC_V2, LTF_BASE_CAP); `--legacy-base` reproduces Baseline v1. Output suffix: _v2_cap5 (V2) or none (legacy). It was built as: src/base_candles.py + config.py constants. Switch on with --new-base on the runners (output suffix _newbase).
  Rules: base candle = not impulsive AND (wick > 50% of body OR body <= 0.5 ATR) AND range <= 2.5 ATR; count the whole run; reject above the cap (HTF 5, LTF 8, user's numbers);
  LTF lines from the nearest 3 candles; HTF lines grow-capped 0.4 ATR; HTF base/legout <= 1.25, LTF <= 0.6. Docs: RULES.md R24-R29. Tests: python tests/test_base_candles.py (28 cases, 0 unexpected failures; known gaps B11-B15, B17).
- New-base runs done: MIT (30 trades, 46.7%, +10,400 Rs vs Baseline v1 41.7%, +5,897) and WIT (70 trades, 40.0%, +13,222 vs 41.3%, +14,090). Differences are inside the noise (bootstrap intervals about -20 to +30 points).
  Files in results/e7842da/ (*_newbase_*), review list of the 16 MIT trades added: results/mit_added_by_new_base.csv (user has not reviewed yet).
- Known issue: MIT new-base run has one duplicate row (ARE&M 2025-04-07, identical zones); compare_newbase.py removes duplicates.

## DIT15 new-base run: DONE (219 trades, 28.3% vs Baseline v1 29.9%, -1.6 pts, bootstrap 95% -10 to +7; files results/e7842da/trades_dit15_kite_2024_newbase_*). The resume steps below only matter if it is rerun.
Resume if the machine crashed (the runner now checkpoints per ticker, so it continues where it stopped):
1. python scripts/run_dit15_kite.py --new-base --workers=3        (low priority, 3 workers; prints "checkpoint: N tickers already done")
2. python scripts/run_dit15_replay.py --new-base                   (15m then 1m exit scoring; Kite token needed: run kite_login.py in a normal terminal if expired)
3. python scripts/compare_newbase.py dit15 results/<hash>/trades_dit15_kite_2024_newbase_final.csv results/53aecde/baseline_v1_dit15.csv
Note: a run started BEFORE this checkpoint code existed does not write checkpoints; if it dies, step 1 starts from zero once, then checkpoints.

## Other open items
- User answers needed: how many base candles he counts for ACC's daily zone (rejected now, plain run 15); review of the 16 added MIT trades; GLAND weekly distal ~1809 vs ours 1798 (buffer 0.1 ATR).
- Not fixed by base logic: CG POWER weak legout, IKS/MASTEK/LAURUSLABS no explosive leg, GRANULES (7 weekly base candles vs HTF cap 5).
- Rules: CPU - keep workers <= half the cores, low priority (user complained about 6+ python processes). Standing exit rule in CLAUDE.md. Never read .env.
