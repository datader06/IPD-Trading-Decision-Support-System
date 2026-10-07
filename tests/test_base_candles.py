"""Golden checks for the new base-candle logic (src/base_candles.py) on the user's own charts.

Per-chart zone detection only (no backtest). Needs data/cache/kite_frames (gitignored); skipped if missing.
Run: python tests/test_base_candles.py   (exit code 1 if a non-known-gap case fails)
"""
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "data" / "cache" / "kite_frames"
sys.path.insert(0, str(ROOT / "legacy" / "handoff" / "handoff" / "code"))
sys.path.insert(0, str(ROOT / "src"))


def _setup():
    import offline_loader
    offline_loader.install(data_dir=str(FRAMES))
    import mtf_zones as mtz
    import sd_zones as sz
    import base_candles as bc
    bc.install(sz, mtz)
    return mtz, sz, bc


def _frame(mtz, t, tf):
    if tf == "M":
        return mtz._build_frame(t, "daily", "1d", "max", "ME", None)
    if tf == "W":
        return mtz._build_frame(t, "daily", "1d", "max", "W", 400)
    return mtz._build_frame(t, "daily", "1d", "max", None, 750)


def run_case(mtz, sz, bc, c):
    df = _frame(mtz, c.ticker, c.timeframe)
    base = mtz.LTF_ENTRY_CONFIG if c.role == "ltf" else (mtz.MONTHLY_CONFIG if c.timeframe == "M" else mtz.WEEKLY_CONFIG)
    cfg = bc.new_base_config(base, c.role)
    zs = [z for z in sz.detect_zones(df, config=cfg, allow_wick_to_wick=(c.role == "ltf")) if z.type == c.type]
    f = pd.Timestamp(c.formed_date)
    days = 45 if c.timeframe == "M" else 20
    near = [z for z in zs if abs((df.iloc[z.leg_end_index]["timestamp"] - f).days) <= days]
    if c.expected == "REJECT":
        return (not near), ("no zone" if not near else f"zone {near[-1].proximal_line:.1f}/{near[-1].distal_line:.1f} found")
    if not near:
        return False, "no zone"
    if c.expected == "ACCEPT":
        return True, f"zone {near[-1].proximal_line:.1f}/{near[-1].distal_line:.1f}"
    z = near[-1]
    tol = float(c.tol_pct) / 100
    ok = (abs(z.proximal_line - c.expect_proximal) <= tol * c.expect_proximal and
          abs(z.distal_line - c.expect_distal) <= tol * c.expect_distal)
    return ok, f"zone {z.proximal_line:.1f}/{z.distal_line:.1f} vs user {c.expect_proximal:g}/{c.expect_distal:g} (+-{c.tol_pct:g}%)"


def main():
    if not FRAMES.exists():
        print("SKIP: data/cache/kite_frames missing")
        return 0
    mtz, sz, bc = _setup()
    cases = pd.read_csv(ROOT / "tests" / "golden" / "base_candle_cases.csv")
    bad = 0
    for c in cases.itertuples():
        ok, msg = run_case(mtz, sz, bc, c)
        gap = isinstance(c.known_gap, str) and c.known_gap == "yes"
        tag = "PASS" if ok else ("KNOWN-GAP" if gap else "FAIL")
        bad += (tag == "FAIL")
        print(f"{c.case_id} {c.ticker:14} expected {c.expected:8} {tag:9} {msg}")
    print(f"\nunexpected failures: {bad}")
    return 1 if bad else 0


def mit_verdicts():
    """Informational: the user's MIT trade verdicts vs the current candidate list (results/21e3482/review/review_mit_cap5.csv)."""
    v = pd.read_csv(ROOT / "tests" / "golden" / "mit_trade_verdicts.csv")
    f = ROOT / "results" / "21e3482" / "review" / "review_mit_cap5.csv"
    if not f.exists():
        print("SKIP mit verdicts: candidate list missing")
        return
    have = set(pd.read_csv(f).ticker.str.replace(".NS", "", regex=False))
    for r in v.itertuples():
        want_in = r.verdict in ("very_good", "good", "ok")
        status = "ok" if (r.ticker in have) == want_in else "DIFFERS"
        print(f"  {r.ticker:12} {r.verdict:20} in current list: {r.ticker in have!s:5} {status}")


def test_base_candle_golden():
    assert main() == 0


if __name__ == "__main__":
    code = main()
    mit_verdicts()
    sys.exit(code)
