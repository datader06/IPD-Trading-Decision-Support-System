"""Add ltf_base_count / htf_base_count to the trade files (new-base runs). No strategy re-run, no network.

For each trade: rebuild its HTF and LTF frames (same specs as the runners), find the zone's legout by (type, legout-bar timestamp = ltf_formed_at /
htf_formed_at) and count the contiguous base candles before it with the new base definition (src/base_candles.base_run; uncounted cap).
Usage: python scripts/add_base_counts.py [combo ...]   (default: mit wit dit15), optional --workers=N (default 2), low priority.
"""
import multiprocessing as mp
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy" / "handoff" / "handoff"
_fr = [a.split("=")[1] for a in sys.argv if a.startswith("--frames=")]
FRAMES = ROOT / "data" / "cache" / (_fr[0] if _fr else "kite_frames")
RES = ROOT / "results" / "e7842da"
LONG = "--long" in sys.argv  # lift the HTF 750-bar window like the 2021 runners (dit15)
sys.path.insert(0, str(ROOT / "scripts"))
import _base_flags  # noqa: E402  (sets DZ_STRICT_HTF / caps env from --strict-htf, --htf-cap, --ltf-cap)
_base_flags.resolve()
mtz = sz = bc = None


def _low_priority():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _init():
    global mtz, sz, bc
    _low_priority()
    sys.path.insert(0, str(LEGACY / "code"))
    sys.path.insert(0, str(ROOT / "src"))
    import offline_loader
    offline_loader.install(data_dir=str(FRAMES))
    import mtf_zones as _m
    import sd_zones as _s
    import base_candles as _b
    _m.COMBOS["dit15"] = replace(_m.COMBOS["dit"], ltf_interval="15m", ltf_resample=None, ltf_source="intraday",
                                 ltf_fetch_period="1400d", trend_fetch_period="1400d", **({"htf_window": None} if LONG else {}))
    _b.install(_s, _m)
    mtz, sz, bc = _m, _s, _b


def _count(df, cfg, typ, formed):
    atr = sz.wilder_atr(df)
    for ls, le in sz.find_impulsive_legs(df, atr, typ, cfg):
        if df.iloc[le]["timestamp"] == formed:
            return len(bc.base_run(df, atr, ls, cfg, sz))
    return None


def _work(args):
    combo, ticker, rows = args
    spec = mtz.COMBOS[combo]
    htf = mtz._build_frame(ticker, spec.htf_source, spec.htf_interval, spec.ltf_fetch_period, spec.htf_resample, spec.htf_window)
    ltf = mtz._build_frame(ticker, spec.ltf_source, spec.ltf_interval, spec.ltf_fetch_period, spec.ltf_resample, spec.ltf_window)
    out = []
    for idx, typ, hf, lf in rows:
        out.append((idx, _count(ltf, spec.ltf_config, typ, pd.Timestamp(lf)), _count(htf, spec.htf_config, typ, pd.Timestamp(hf))))
    return out


def main():
    combos = [a for a in sys.argv[1:] if not a.startswith("--")] or ["mit", "wit", "dit15"]
    files = [a.split("=")[1] for a in sys.argv if a.startswith("--file=")]
    arg = [a.split("=")[1] for a in sys.argv if a.startswith("--workers=")]
    workers = int(arg[0]) if arg else 2
    _low_priority()
    for combo in combos:
        src = Path(files[0]) if files else RES / f"trades_{combo}_kite_2024_newbase_final.csv"
        df = pd.read_csv(src, parse_dates=["entry_time", "ltf_formed_at", "htf_formed_at"])
        jobs = [(combo, t, [(i, r.type, r.htf_formed_at, r.ltf_formed_at) for i, r in g.iterrows()]) for t, g in df.groupby("ticker")]
        res = {}
        with mp.Pool(workers, initializer=_init) as pool:
            for k, part in enumerate(pool.imap_unordered(_work, jobs, chunksize=1), 1):
                for idx, lc, hc in part:
                    res[idx] = (lc, hc)
                if k % 25 == 0:
                    print(f"  {combo} {k}/{len(jobs)} tickers", flush=True)
        df["ltf_base_count"] = [res[i][0] for i in df.index]
        df["htf_base_count"] = [res[i][1] for i in df.index]
        miss = int(df["ltf_base_count"].isna().sum() + df["htf_base_count"].isna().sum())
        df.to_csv(src, index=False)
        print(f"{combo}: {len(df)} trades, counts added to {src.name}; unmatched zones: {miss}")
        for col in ("ltf_base_count", "htf_base_count"):
            print(f"  {col}: " + ", ".join(f"{k}:{v}" for k, v in sorted(df[col].value_counts(dropna=False).items(), key=lambda x: (str(x[0]) == 'nan', x[0]))))


if __name__ == "__main__":
    main()
