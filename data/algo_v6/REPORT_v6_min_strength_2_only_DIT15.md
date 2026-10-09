```
# Baseline v5 vs v6 candidate (min zone strength 2 on DIT15 only); 2021+ entries, 15m/1m exit scoring, costs 0.20% of position value

candidates 300 (DIT15 195, WIT 70, MIT 35); kept 205; dropped 95; unresolved 0

######## DIT15
 -- 2021+
  v5 baseline (all)          n=195 wins= 73 losses=122 win%= 37.4 [31-45] avgR=+0.154 Rs gross=  +25,259 net=  -10,924
  v6 strength >= 2           n=100 wins= 43 losses= 57 win%= 43.0 [33-52] avgR=+0.322 Rs gross=  +24,371 net=   +5,911
  dropped                    n= 95 wins= 30 losses= 65 win%= 31.6 [22-41] avgR=-0.022 Rs gross=     +888 net=  -16,835
  win-rate change v6 minus v5: +5.56 pts
 -- train (<2026)
  v5 baseline (all)          n=155 wins= 56 losses= 99 win%= 36.1 [28-43] avgR=+0.115 Rs gross=  +15,576 net=  -13,109
  v6 strength >= 2           n= 79 wins= 31 losses= 48 win%= 39.2 [29-51] avgR=+0.203 Rs gross=  +11,329 net=   -3,299
  dropped                    n= 76 wins= 25 losses= 51 win%= 32.9 [22-43] avgR=+0.025 Rs gross=   +4,247 net=   -9,810
  win-rate change v6 minus v5: +3.11 pts
 -- holdout 2026
  v5 baseline (all)          n= 40 wins= 17 losses= 23 win%= 42.5 [28-57] avgR=+0.304 Rs gross=   +9,683 net=   +2,185
  v6 strength >= 2           n= 21 wins= 12 losses=  9 win%= 57.1 [38-76] avgR=+0.770 Rs gross=  +13,042 net=   +9,210  SAMPLE<30
  dropped                    n= 19 wins=  5 losses= 14 win%= 26.3 [11-47] avgR=-0.211 Rs gross=   -3,359 net=   -7,025  SAMPLE<30
  win-rate change v6 minus v5: +14.64 pts
 by year (v6 kept: n, win%, avg R): 2021: 8, 50%, +0.50 | 2022: 14, 36%, +0.16 | 2023: 20, 45%, +0.40 | 2024: 21, 43%, +0.27 | 2025: 16, 25%, -0.24 | 2026: 21, 57%, +0.77

######## WIT
 -- 2021+
  v5 baseline (all)          n= 70 wins= 32 losses= 38 win%= 45.7 [34-57] avgR=+0.417 Rs gross=  +27,506 net=  +18,887
  v6 strength >= 2           n= 70 wins= 32 losses= 38 win%= 45.7 [34-57] avgR=+0.417 Rs gross=  +27,506 net=  +18,887
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 -- train (<2026)
  v5 baseline (all)          n= 57 wins= 23 losses= 34 win%= 40.4 [28-53] avgR=+0.263 Rs gross=  +14,243 net=   +7,186
  v6 strength >= 2           n= 57 wins= 23 losses= 34 win%= 40.4 [28-53] avgR=+0.263 Rs gross=  +14,243 net=   +7,186
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 -- holdout 2026
  v5 baseline (all)          n= 13 wins=  9 losses=  4 win%= 69.2 [46-92] avgR=+1.095 Rs gross=  +13,263 net=  +11,700  SAMPLE<30
  v6 strength >= 2           n= 13 wins=  9 losses=  4 win%= 69.2 [46-92] avgR=+1.095 Rs gross=  +13,263 net=  +11,700  SAMPLE<30
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 by year (v6 kept: n, win%, avg R): 2021: 14, 36%, +0.07 | 2022: 5, 40%, +0.20 | 2023: 12, 25%, -0.05 | 2024: 16, 50%, +0.53 | 2025: 10, 50%, +0.50 | 2026: 13, 69%, +1.09

######## MIT
 -- 2021+
  v5 baseline (all)          n= 35 wins= 16 losses= 19 win%= 45.7 [29-63] avgR=+0.844 Rs gross=  +27,485 net=  +25,421
  v6 strength >= 2           n= 35 wins= 16 losses= 19 win%= 45.7 [29-63] avgR=+0.844 Rs gross=  +27,485 net=  +25,421
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 -- train (<2026)
  v5 baseline (all)          n= 32 wins= 15 losses= 17 win%= 46.9 [31-62] avgR=+0.892 Rs gross=  +26,889 net=  +25,102
  v6 strength >= 2           n= 32 wins= 15 losses= 17 win%= 46.9 [31-62] avgR=+0.892 Rs gross=  +26,889 net=  +25,102
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 -- holdout 2026
  v5 baseline (all)          n=  3 wins=  1 losses=  2 win%= 33.3 [0-100] avgR=+0.333 Rs gross=     +596 net=     +319  SAMPLE<30
  v6 strength >= 2           n=  3 wins=  1 losses=  2 win%= 33.3 [0-100] avgR=+0.333 Rs gross=     +596 net=     +319  SAMPLE<30
  dropped                    n=  0
  win-rate change v6 minus v5: +0.00 pts
 by year (v6 kept: n, win%, avg R): 2021: 4, 50%, +1.00 | 2022: 6, 50%, +1.00 | 2023: 6, 50%, +0.77 | 2024: 8, 62%, +1.64 | 2025: 8, 25%, +0.10 | 2026: 3, 33%, +0.33

######## ALL 3 pooled
 -- 2021+
  v5 baseline (all)          n=300 wins=121 losses=179 win%= 40.3 [35-46] avgR=+0.296 Rs gross=  +80,250 net=  +33,384
  v6 strength >= 2           n=205 wins= 91 losses=114 win%= 44.4 [38-51] avgR=+0.444 Rs gross=  +79,362 net=  +50,219
  dropped                    n= 95 wins= 30 losses= 65 win%= 31.6 [22-41] avgR=-0.022 Rs gross=     +888 net=  -16,835
  win-rate change v6 minus v5: +4.06 pts
 -- train (<2026)
  v5 baseline (all)          n=244 wins= 94 losses=150 win%= 38.5 [32-45] avgR=+0.252 Rs gross=  +56,708 net=  +19,179
  v6 strength >= 2           n=168 wins= 69 losses= 99 win%= 41.1 [34-49] avgR=+0.354 Rs gross=  +52,461 net=  +28,989
  dropped                    n= 76 wins= 25 losses= 51 win%= 32.9 [22-43] avgR=+0.025 Rs gross=   +4,247 net=   -9,810
  win-rate change v6 minus v5: +2.55 pts
 -- holdout 2026
  v5 baseline (all)          n= 56 wins= 27 losses= 29 win%= 48.2 [36-61] avgR=+0.489 Rs gross=  +23,542 net=  +14,204
  v6 strength >= 2           n= 37 wins= 22 losses= 15 win%= 59.5 [43-76] avgR=+0.849 Rs gross=  +26,901 net=  +21,229
  dropped                    n= 19 wins=  5 losses= 14 win%= 26.3 [11-47] avgR=-0.211 Rs gross=   -3,359 net=   -7,025  SAMPLE<30
  win-rate change v6 minus v5: +11.25 pts
 by year (v6 kept: n, win%, avg R): 2021: 26, 42%, +0.35 | 2022: 25, 40%, +0.37 | 2023: 38, 39%, +0.32 | 2024: 45, 49%, +0.61 | 2025: 34, 32%, +0.06 | 2026: 37, 59%, +0.85
```
