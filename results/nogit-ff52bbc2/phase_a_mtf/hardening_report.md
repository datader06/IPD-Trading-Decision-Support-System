# WIT and MIT hardening: before vs hardened (strict lists, entries from 2021-01-01, gross unless stated)

Before = stored 2021+ results of the pre-hardening engine (Kite replay). Legacy mode = the same pipeline re-run through the new orchestrator (must reproduce the stored trade list) and re-scored with the unchanged replay and today's minute cache. Hardened = point-in-time mode. Resolved = WIN + LOSS; AMBIGUOUS never converted; max drawdown on the cumulative R curve by exit time.

## WIT

| Set | Trades | W | L | Ambig. | Open/Cens. | Resolved | Win rate (95% CI) | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WIT before, replay-only (stored) | 98 | 34 | 54 | 10 | 0 | 88 | 38.6% [28-49] | +0.181 | 1.30 | +15.9 | 11.0 |
| WIT before, as published (heuristic-filled) | 98 | 36 | 62 | 0 | 0 | 98 | 36.7% [28-46] | +0.122 | 1.19 | +11.9 | 9.5 |
| legacy mode, re-scored (reproduction) | 98 | 34 | 55 | 9 | 0 | 89 | 38.2% [28-48] | +0.166 | 1.27 | +14.8 | 11.0 |
| + trend look-ahead fix only | 114 | 36 | 66 | 12 | 0 | 102 | 35.3% [26-44] | +0.076 | 1.12 | +7.8 | 12.0 |
| **hardened (full point-in-time)** | 111 | 35 | 60 | 16 | 0 | 95 | 36.8% [27-46] | +0.105 | 1.16 | +10.0 | 9.9 |

Reproduction check: legacy mode gives 98 trades vs 98 stored; identical trade keys 98, only stored 0, only legacy mode 0. Corporate-action-excluded trades: legacy 0, pit_trend 0, pit 0.

Change, legacy to hardened:

| Win rate | Expectancy R | Profit factor | Total R | Max DD (R) | Resolved |
|---|---|---|---|---|---|
| -1.4 pts | -0.061 | -0.11 | -4.8 | -1.1 | +6 |

Bootstrap 95% interval of the expectancy change: [-0.497, +0.363] R (includes 0: not distinguishable from noise).

Trade-set change: 0 orders in both, 98 removed by the hardening, 111 added.

| Set | Trades | W | L | Ambig. | Open/Cens. | Resolved | Win rate (95% CI) | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kept in both (hardened outcomes) | 0 | 0 | 0 | 0 | 0 | 0 | nan% n/a | +nan | nan | +0.0 | 0.0 |
| removed | 98 | 34 | 55 | 9 | 0 | 89 | 38.2% [28-48] | +0.166 | 1.27 | +14.8 | 11.0 |
| added | 111 | 35 | 60 | 16 | 0 | 95 | 36.8% [27-46] | +0.105 | 1.16 | +10.0 | 9.9 |

Hardened ambiguity: {'MINUTE_NOT_CACHED': 13, 'target in fill bar': 2, 'stop+target in fill bar': 1}. Kite minute requests that would resolve the MINUTE_NOT_CACHED trades: 13 (one per symbol-day); not fetched (no authorisation in this task).

Hardened outcome classes: {'LOSS': 60, 'WIN': 35, 'AMBIGUOUS': 16}.

Cost scenarios (round trip, no slippage; the stored 'before' rows approximate the exit price by the entry fill, marked ~):

| Cost | Set | Resolved | Win rate | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| gross | before ~ | 88 | 38.6% | +0.181 | 1.30 | +15.9 | 11.0 |
| gross | legacy re-scored | 89 | 38.2% | +0.166 | 1.27 | +14.8 | 11.0 |
| gross | hardened | 95 | 36.8% | +0.105 | 1.16 | +10.0 | 9.9 |
| 0.10% | before ~ | 88 | 38.6% | +0.116 | 1.18 | +10.2 | 11.8 |
| 0.10% | legacy re-scored | 89 | 38.2% | +0.102 | 1.16 | +9.0 | 11.8 |
| 0.10% | hardened | 95 | 36.8% | +0.032 | 1.05 | +3.0 | 11.4 |
| 0.20% | before ~ | 88 | 38.6% | +0.052 | 1.08 | +4.5 | 12.5 |
| 0.20% | legacy re-scored | 89 | 38.2% | +0.037 | 1.05 | +3.3 | 12.5 |
| 0.20% | hardened | 95 | 36.8% | -0.041 | 0.94 | -3.9 | 13.5 |
| 0.30% | before ~ | 88 | 38.6% | -0.013 | 0.98 | -1.1 | 13.3 |
| 0.30% | legacy re-scored | 89 | 38.2% | -0.028 | 0.96 | -2.5 | 13.3 |
| 0.30% | hardened | 95 | 36.8% | -0.115 | 0.85 | -10.9 | 17.2 |

By year (resolved / win % / expectancy R): 2021: 17/35%/+0.06 vs 16/44%/+0.31; 2022: 8/25%/-0.25 vs 17/35%/+0.01; 2023: 10/30%/+0.10 vs 18/44%/+0.38; 2024: 20/50%/+0.49 vs 17/29%/-0.11; 2025: 18/28%/-0.17 vs 17/35%/+0.06; 2026: 16/50%/+0.50 vs 10/30%/-0.12 (legacy vs hardened)

## MIT

| Set | Trades | W | L | Ambig. | Open/Cens. | Resolved | Win rate (95% CI) | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MIT before, replay-only (stored) | 35 | 17 | 16 | 2 | 0 | 33 | 51.5% [33-67] | +0.501 | 1.94 | +16.5 | 5.2 |
| MIT before, as published (heuristic-filled) | 35 | 17 | 18 | 0 | 0 | 35 | 48.6% [31-66] | +0.415 | 1.74 | +14.5 | 5.2 |
| legacy mode, re-scored (reproduction) | 35 | 17 | 16 | 2 | 0 | 33 | 51.5% [33-67] | +0.501 | 1.94 | +16.5 | 5.2 |
| + trend look-ahead fix only | 35 | 17 | 16 | 2 | 0 | 33 | 51.5% [33-67] | +0.501 | 1.94 | +16.5 | 5.2 |
| **hardened (full point-in-time)** | 36 | 18 | 16 | 2 | 0 | 34 | 52.9% [35-71] | +0.545 | 2.05 | +18.5 | 5.2 |

Reproduction check: legacy mode gives 35 trades vs 35 stored; identical trade keys 35, only stored 0, only legacy mode 0. Corporate-action-excluded trades: legacy 0, pit_trend 0, pit 0.

Change, legacy to hardened:

| Win rate | Expectancy R | Profit factor | Total R | Max DD (R) | Resolved |
|---|---|---|---|---|---|
| +1.4 pts | +0.044 | +0.11 | +2.0 | +0.0 | +1 |

Bootstrap 95% interval of the expectancy change: [-0.686, +0.791] R (includes 0: not distinguishable from noise).

Trade-set change: 35 orders in both, 0 removed by the hardening, 1 added.

| Set | Trades | W | L | Ambig. | Open/Cens. | Resolved | Win rate (95% CI) | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kept in both (hardened outcomes) | 35 | 17 | 16 | 2 | 0 | 33 | 51.5% [33-67] | +0.501 | 1.94 | +16.5 | 5.2 |
| removed | 0 | 0 | 0 | 0 | 0 | 0 | nan% n/a | +nan | nan | +0.0 | 0.0 |
| added | 1 | 1 | 0 | 0 | 0 | 1 | 100.0% [100-100] | +2.000 | nan | +2.0 | 0.0 |

Hardened ambiguity: {'gap-fill opens beyond the stop': 2}. Kite minute requests that would resolve the MINUTE_NOT_CACHED trades: 0 (one per symbol-day); not fetched (no authorisation in this task).

Hardened outcome classes: {'WIN': 18, 'LOSS': 16, 'AMBIGUOUS': 2}.

Cost scenarios (round trip, no slippage; the stored 'before' rows approximate the exit price by the entry fill, marked ~):

| Cost | Set | Resolved | Win rate | Exp. R | PF | Total R | Max DD (R) |
|---|---|---|---|---|---|---|---|
| gross | before ~ | 33 | 51.5% | +0.501 | 1.94 | +16.5 | 5.2 |
| gross | legacy re-scored | 33 | 51.5% | +0.501 | 1.94 | +16.5 | 5.2 |
| gross | hardened | 34 | 52.9% | +0.545 | 2.05 | +18.5 | 5.2 |
| 0.10% | before ~ | 33 | 51.5% | +0.470 | 1.86 | +15.5 | 5.4 |
| 0.10% | legacy re-scored | 33 | 51.5% | +0.470 | 1.86 | +15.5 | 5.4 |
| 0.10% | hardened | 34 | 52.9% | +0.514 | 1.97 | +17.5 | 5.4 |
| 0.20% | before ~ | 33 | 51.5% | +0.440 | 1.78 | +14.5 | 5.5 |
| 0.20% | legacy re-scored | 33 | 51.5% | +0.439 | 1.78 | +14.5 | 5.5 |
| 0.20% | hardened | 34 | 52.9% | +0.483 | 1.88 | +16.4 | 5.5 |
| 0.30% | before ~ | 33 | 51.5% | +0.409 | 1.71 | +13.5 | 5.6 |
| 0.30% | legacy re-scored | 33 | 51.5% | +0.408 | 1.71 | +13.5 | 5.6 |
| 0.30% | hardened | 34 | 52.9% | +0.452 | 1.81 | +15.4 | 5.6 |

By year (resolved / win % / expectancy R): 2021: 4/50%/+0.50 vs 5/60%/+0.80; 2022: 6/50%/+0.50 vs 6/50%/+0.50; 2023: 6/67%/+0.77 vs 6/67%/+0.77; 2024: 7/71%/+1.16 vs 7/71%/+1.16; 2025: 7/29%/-0.18 vs 7/29%/-0.18; 2026: 3/33%/+0.00 vs 3/33%/+0.00 (legacy vs hardened)
