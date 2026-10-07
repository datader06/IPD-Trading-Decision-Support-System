"""Command-line flags for the base-candle logic. V2 (cap from config.LTF_BASE_CAP, default 5) is the default.

  --legacy-base   legacy base logic (reproduces Baseline v1 exactly); output files get no suffix
  --ltf-cap=N     V2 with another LTF cap
  --from=YYYY-MM-DD  (MIT runner) keep entries from this date; also lifts the 750-bar daily window; adds _fromYYYY to the suffix
  --htf-cap=N     V2 with another HTF cap (default config.HTF_BASE_CAP = 5); adds _hN to the suffix
  --strict-htf    stricter HTF legout (config STRICT_HTF_*): body >= 1.35 ATR, close in outer 22%; removes about 20% of trades; adds _sh
  --no-trend      (MIT/WIT runners) turn the 3-timeframe trend filter OFF, i.e. also take trades against the trend; adds _nt to the suffix
  --no-legout-wick  V2 without the HTF "legout closes over the base wick" rule (reproduces the cap-5 candidate lists)
Returns the output-file suffix: "" for legacy, "_v2_cap<N>" for V2 (+ "_lw" when the legout-wick rule is on). Sets env vars read by src/base_candles.py (inherited by workers).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config as C  # noqa: E402


def resolve(argv=None):
    argv = argv if argv is not None else sys.argv
    v2 = C.BASE_LOGIC_V2 and "--legacy-base" not in argv
    os.environ["DZ_BASE_LOGIC_V2"] = "1" if v2 else "0"
    cap_arg = [a.split("=")[1] for a in argv if a.startswith("--ltf-cap=")]
    cap = int(cap_arg[0]) if cap_arg else C.LTF_BASE_CAP
    if cap_arg:
        os.environ["DZ_LTF_CAP"] = str(cap)
    lw = C.HTF_LEGOUT_CLOSE_BEYOND_BASE_WICK and "--no-legout-wick" not in argv
    os.environ["DZ_HTF_LEGOUT_WICK"] = "1" if lw else "0"
    fr = [a.split("=")[1] for a in argv if a.startswith("--from=")]
    hc = [a.split("=")[1] for a in argv if a.startswith("--htf-cap=")]
    sh = "--strict-htf" in argv
    os.environ["DZ_STRICT_HTF"] = "1" if sh else "0"
    if hc:
        os.environ["DZ_HTF_CAP"] = str(int(hc[0]))
    tag = (f"_v2_cap{cap}" + (f"_h{int(hc[0])}" if hc else "") + ("_sh" if sh else "") + ("_lw" if lw else "")) if v2 else ""
    return tag + ("_nt" if "--no-trend" in argv else "") + (f"_from{fr[0][:4]}" if fr else "")
