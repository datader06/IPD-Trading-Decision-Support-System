# PHOTO_AUDIT.md - why the "photos improve" trades are or are not flagged (2 Oct 2026)

Checked per ticker under the defaults at the time (base logic V2, LTF cap 5, HTF cap 5, HTF legout-over-wick rule on).
A backtest trade needs: (1) an HTF zone, (2) a valid LTF zone formed inside the HTF zone's formation window, still untested when the HTF zone confirmed and at least 30% inside it,
(3) the LTF zone then actually tapped (entry), (4) HTF wick still fresh at entry, (5) trend not against the trade at HTF formation and at entry. Photos taken on 23-24 Sep 2026 are live setups: no tap yet = no backtest trade.

| Ticker (combo) | HTF zone | What stops the trade |
|---|---|---|
| MANAPPURAM (MIT) | found 325.9/278.5 (your 283-325) | LTF zone rejected: legout wicks back into the base and the zone is narrower than 0.5 ATR |
| IKS (MIT) | none | monthly legout not explosive: Apr-2026 body 1.00 x ATR (needs 1.0, borderline), Jul-2026 body 0.57 and close at 68% |
| MASTEK (MIT) | none | monthly legout not explosive: Apr-2026 body 0.82 x ATR (needs 1.0), Jul-2026 body 0.71 |
| MAXHEALTH (MIT) | found but top 1056.5 (your 997): March's red candle (O 1056 C 962, wicks 32/25) counted as base by the wick rule | HTF wick-freshness: base wick first touched 2026-07-31, before the 2026-09-07 LTF entry |
| ONGC (MIT) | found 290.0/310.4 | the only LTF supply zone in the window (285.1/290.4, formed 27 May) sits below the HTF zone: overlap under 30% |
| ORIENTCEM (MIT) | found 136.0/118.3 (your 100-133, 44% overlap) | no explosive daily legout inside the HTF window |
| RVNL (MIT) | found 425.0/305.8 | LTF base run 7 > cap 5 (known gap, user called it very good) |
| ACC (MIT) | found 1890.0/1778.2 | LTF base run 15 > cap 5 (known gap) |
| CONCORDBIO (MIT) | found 2145.0/2438.1 | none: trade exists (supply entry 2025-06-10) |
| GRANULES (WIT) | none | weekly legout is explosive (1.47 x ATR, close 92%) but base run 7 > HTF cap 5 |
| KEI (WIT, a DEMAND long, not supply) | found 5287.0/4707.3 (your 4740-5010; top too high) | two valid 2h candidates tapped 4 and 7 Sep; the trade exists with the trend filter OFF (entry 5051.9); the trend filter blocks it |
| LAURUSLABS (DIT) | none | daily legout not explosive: 29 Jun body 1.22 x ATR (needs 1.3), close at 62% (needs 75%) |

Candidate changes (none applied yet):
1. Wick rule for LINES: keep the generous wick rule (total wick > 50% of body) to COUNT base candles, but draw zone lines only from candles that pass the strict test (the larger single wick > 50% of body, or body <= 0.5 ATR). Tested: all 30 golden cases unchanged, MAXHEALTH top becomes 993 (your 997), about 4% of monthly zones move.
2. Legout test: explosive by the numbers misses IKS, MASTEK, LAURUSLABS and GRANULES (base count). A relative test (legout body vs base candle size, plus the new close-over-base-wick rule) could replace the ATR threshold; needs the user's rule.
3. LTF cap 5 rejects RVNL (7), ACC (15), GRANULES (7) which the user rated good; user decision stands.
4. Trend filter blocks KEI (a good trade in the photos); user to decide whether the trend re-check at entry stays as is.
5. Minimum LTF zone width (0.5 ATR) kills MANAPPURAM's narrow daily zone.
