"""Export sample zones from the NEW base-candle logic for manual review. Zone detection only (no backtest, no trades).

Groups: A = accepted, 3 or fewer base candles; B = accepted, 5 or more; C = rejected because the count is over the cap.
Writes results/base_logic_review.csv. Needs data/cache/kite_frames. Legacy files are not edited.
"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
sys.path.insert(0, str(LEGACY / "code"))
sys.path.insert(0, str(ROOT / "src"))
import offline_loader  # noqa: E402
offline_loader.install(data_dir=str(ROOT / "data" / "cache" / "kite_frames"))
import mtf_zones as mtz  # noqa: E402
import sd_zones as sz  # noqa: E402
import base_candles as bc  # noqa: E402
import config as C  # noqa: E402

bc.install(sz, mtz)
SINCE = pd.Timestamp("2024-01-01")
TF = {"M": ("ME", None, "htf"), "W": ("W", 400, "htf"), "D": (None, 750, "ltf")}
TF_NAME = {"M": "monthly", "W": "weekly", "D": "daily"}


def frame(t, tf):
    rule, win, _ = TF[tf]
    return mtz._build_frame(t, "daily", "1d", "max", rule, win)


def counts(df, atr, ls, cfg):
    """(contiguous base run, count inside the price band) before the leg starting at ls."""
    run = bc.base_run(df, atr, ls, cfg, sz)
    return len(run), len(run)


def counted_idx(df, atr, ls, cfg):
    """Indices of the candles counted as the consolidation (contiguous base run, inside the price band)."""
    return bc.base_run(df, atr, ls, cfg, sz)


def fmt_d(ts, tf):
    return f"{ts:%Y-%m}" if tf == "M" else f"{ts:%Y-%m-%d}"


def ohlc(df, idx, tf):
    return " | ".join(f"{fmt_d(df.iloc[j]['timestamp'], tf)} O{df.iloc[j]['open']:.1f} H{df.iloc[j]['high']:.1f} "
                      f"L{df.iloc[j]['low']:.1f} C{df.iloc[j]['close']:.1f}" for j in sorted(idx))


def main():
    tickers = [t for t in json.load(open(LEGACY / "code" / "webapp" / "universe_live.json"))["tickers"] if t != "HFCL.NS"]
    random.Random(7).shuffle(tickers)
    A, B, Cg = [], [], []
    want = {"A": {"M": 2, "W": 1, "D": 2}, "B": {"M": 1, "W": 1, "D": 3}, "C": {"M": 1, "W": 1, "D": 3}}
    have = {g: {k: 0 for k in v} for g, v in want.items()}
    used = {"A": set(), "B": set(), "C": set()}
    for t in tickers:
        if all(sum(have[g].values()) >= sum(want[g].values()) for g in want):
            break
        for tf in ("M", "W", "D"):
            df = frame(t, tf)
            if len(df) < 30:
                continue
            role = TF[tf][2]
            base = mtz.LTF_ENTRY_CONFIG if role == "ltf" else (mtz.MONTHLY_CONFIG if tf == "M" else mtz.WEEKLY_CONFIG)
            cfg = bc.new_base_config(base, role)
            atr = sz.wilder_atr(df)
            zones = sz.detect_zones(df, config=cfg, allow_wick_to_wick=(role == "ltf"))
            seen_legs = set()
            for z in zones:
                ls, le = z.leg_start_index, z.leg_end_index
                seen_legs.add(ls)
                if df.iloc[le]["timestamp"] < SINCE:
                    continue
                run, cnt = counts(df, atr, ls, cfg)
                grp = "A" if cnt <= 3 else ("B" if cnt >= 5 else None)
                if grp and have[grp][tf] < want[grp][tf] and t not in used[grp]:
                    used[grp].add(t); have[grp][tf] += 1
                    used_idx = list(range(z.base_start_index, z.base_end_index + 1))
                    cidx = counted_idx(df, atr, ls, cfg)
                    legbody = max(abs(df.iloc[k]["close"] - df.iloc[k]["open"]) / atr.iloc[k] for k in range(ls, le + 1))
                    (A if grp == "A" else B).append(dict(
                        group=grp, status="ACCEPTED", ticker=t, timeframe=TF_NAME[tf], type=z.type,
                        base_count_in_band=cnt, base_candles_used_for_lines=len(used_idx),
                        counted_first=fmt_d(df.iloc[min(cidx)]["timestamp"], tf), counted_last=fmt_d(df.iloc[max(cidx)]["timestamp"], tf),
                        lines_first=fmt_d(df.iloc[z.base_start_index]["timestamp"], tf), lines_last=fmt_d(df.iloc[z.base_end_index]["timestamp"], tf),
                        legout_start=fmt_d(df.iloc[ls]["timestamp"], tf), legout_end=fmt_d(df.iloc[le]["timestamp"], tf),
                        proximal=round(z.proximal_line, 2), distal=round(z.distal_line, 2), legout_body_atr=round(legbody, 2),
                        cap=cfg.max_base_candles, counted_candles_ohlc=ohlc(df, cidx, tf)))
            # rejected because the in-band count is over the cap (C)
            if have["C"][tf] < want["C"][tf] and t not in used["C"]:
                for ls, le in sz.find_impulsive_legs(df, atr, zones[0].type if False else "demand", cfg) + sz.find_impulsive_legs(df, atr, "supply", cfg):
                    if ls in seen_legs or df.iloc[le]["timestamp"] < SINCE:
                        continue
                    run, cnt = counts(df, atr, ls, cfg)
                    if cnt > cfg.max_base_candles:
                        typ = "demand" if df.iloc[le]["close"] > df.iloc[le]["open"] else "supply"
                        near = bc.base_run(df, atr, ls, cfg, sz)[:cnt]
                        legbody = max(abs(df.iloc[k]["close"] - df.iloc[k]["open"]) / atr.iloc[k] for k in range(ls, le + 1))
                        Cg.append(dict(group="C", status=f"REJECTED (count {cnt} > cap {cfg.max_base_candles})", ticker=t,
                                       timeframe=TF_NAME[tf], type=typ, base_count_in_band=cnt, base_candles_used_for_lines="",
                                       counted_first=fmt_d(df.iloc[min(near)]["timestamp"], tf), counted_last=fmt_d(df.iloc[max(near)]["timestamp"], tf),
                                       lines_first="", lines_last="",
                                       legout_start=fmt_d(df.iloc[ls]["timestamp"], tf), legout_end=fmt_d(df.iloc[le]["timestamp"], tf),
                                       proximal="", distal="", legout_body_atr=round(legbody, 2), cap=cfg.max_base_candles,
                                       counted_candles_ohlc=ohlc(df, near, tf)))
                        have["C"][tf] += 1; used["C"].add(t)
                        break
    rows = A + B + Cg
    out = pd.DataFrame(rows)
    out.insert(0, "id", [f"{r['group']}{i + 1}" for i, r in enumerate(rows)])
    for c in ("my_base_count", "agree_with_logic", "comments"):
        out[c] = ""
    p = ROOT / "results" / "base_logic_review.csv"
    out.to_csv(p, index=False)
    print(f"saved {p.relative_to(ROOT)}: A (accepted, <=3) {len(A)}, B (accepted, 5+) {len(B)}, C (rejected, over cap) {len(Cg)}")
    print(out[["id", "ticker", "timeframe", "type", "status", "base_count_in_band", "base_candles_used_for_lines", "counted_first",
               "counted_last", "legout_end", "proximal", "distal"]].to_string(index=False))


if __name__ == "__main__":
    main()
