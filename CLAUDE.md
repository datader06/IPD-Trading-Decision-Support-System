# CLAUDE.md — standing rules

- No number counts as a baseline unless it is in docs/STATUS.md or was produced by the new engine.
- One change at a time. Always report train (before 2026-01-01) vs holdout, flag any sample under 30, and give a bootstrap interval for any win-rate difference.
- Every correction the user gives becomes a rule line in docs/RULES.md plus a test case in tests/golden/.
- Compare any new run to the correct current baseline and name which one you used.
- Report only. Change no live config until the user says yes.
- Never open or re-save CSVs in Excel.
- Kite: use ONLY historical-data and instruments calls. Never place, modify or read orders, positions or holdings. Key, secret and daily token come from environment variables / .env, and are never printed, logged, passed on a command line, or put in any file that gets uploaded.
- Never read .env.
- Do not trust summaries: give raw numbers; counts must add up (wins before and after a rule); a result identical to an old baseline means the change probably did not fire.
- If an earlier claim was wrong, say so plainly and fix it.
- Explain in simple words but cover every technical point.
- Legacy pack path is legacy/handoff/handoff/ (not legacy/handoff/).
- Exit scoring is automatic. Replay every trade at 15minute. If a trade is AMBIGUOUS, re-run it at 1minute without asking. Use minute data whenever it is needed to settle a trade. Do not stop to ask about minute-replay requests; stop only if one run would need more than 1,500 Kite requests, and print the count first. If Kite has no data for a trade, mark it NO_MINUTE_DATA, keep it AMBIGUOUS, and count it in every table. Kite stays read-only: only instruments() and historical_data().
