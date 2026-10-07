"""New base-candle logic (user corrections, 2 Oct 2026). Plugs into the unmodified legacy sd_zones by patching walk_back_base
at runtime; legacy files are never edited. Off unless install() is called (runners: --new-base).

Base candle = NOT an impulsive candle AND (wick test OR small-move test):
  wick test:       total wick (upper + lower) > BASE_WICK_TO_BODY * body          (user: "wick > 50% of body")
  small-move test: body <= base_body_atr_mult * ATR                               (the legacy test, kept as the OR branch)
  size guard:      candle range <= BASE_CANDLE_MAX_RANGE_ATR * ATR                (MRPL: "base candle is so big")
COUNT: the whole contiguous run of base candles right before the legout is counted (nothing hides behind the cap).
       Count above the cap (LTF 5 / HTF 5) -> zone REJECTED (legacy truncated to a cap of 3 / 5 and accepted it).
LINES: LTF zones are drawn from the nearest LTF_LINE_CANDLES (3) candles, which reproduces the lines of the user's good
       trades (ACC, RVNL, CONCORDBIO). HTF zones use the nearest candles of the run while each one grows the base's
       high-low range by <= BASE_EXTENSION_ATR, so a swing-low candle further back does not drag the distal away
       (MANAPPURAM). Far wick of the used base candles = distal, as the user marks it (FLUOROCHEM).
"""
from dataclasses import replace

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C  # noqa: E402
import os  # noqa: E402

C.LTF_BASE_CAP = int(os.environ.get("DZ_LTF_CAP", C.LTF_BASE_CAP))  # runners: --ltf-cap=N

MAX_SCAN = 80


def is_base_candle(row, atr_value, cfg, sz):
    """True if this candle counts as a base candle under the new definition."""
    if atr_value is None or pd.isna(atr_value):
        return False
    if sz._is_impulsive_candle(row, atr_value, "demand", cfg) or sz._is_impulsive_candle(row, atr_value, "supply", cfg):
        return False
    body = abs(row["close"] - row["open"])
    rng = row["high"] - row["low"]
    if rng <= 0:
        return True
    if rng > C.BASE_CANDLE_MAX_RANGE_ATR * atr_value:
        return False
    wick_test = (rng - body) > C.BASE_WICK_TO_BODY * body
    small_move = body <= cfg.base_body_atr_mult * atr_value
    return bool(wick_test or small_move)


def base_run(df, atr, leg_start_idx, cfg, sz):
    """Indices (nearest first) of the contiguous base candles before the leg."""
    idx, j = [], leg_start_idx - 1
    while j >= 0 and len(idx) < MAX_SCAN:
        if not is_base_candle(df.iloc[j], atr.iloc[j], cfg, sz):
            break
        idx.append(j)
        j -= 1
    return idx


def make_walk_back_base(sz, legacy):
    def walk_back_base(df, atr, leg_start_idx, config=sz.DEFAULT_CONFIG):
        if not getattr(config, "new_base", False):
            return legacy(df, atr, leg_start_idx, config)
        if leg_start_idx == 0:
            return None
        idx = base_run(df, atr, leg_start_idx, config, sz)
        if not idx:
            return None
        if len(idx) > config.max_base_candles:
            if C.BASE_CAP_MODE == "reject":
                return None
            idx = idx[:config.max_base_candles]
        lc = getattr(config, "line_candles", None)
        if lc:
            idx = idx[:lc]
        ref_atr = atr.iloc[leg_start_idx]
        ext = config.base_extension_atr_mult * ref_atr if not pd.isna(ref_atr) else float("inf")
        used, lo, hi = [], None, None
        for j in idx:  # nearest first
            r = df.iloc[j]
            nlo = r["low"] if lo is None else min(lo, r["low"])
            nhi = r["high"] if hi is None else max(hi, r["high"])
            if lo is not None and (nhi - nlo) - (hi - lo) > ext:
                break
            used.append(j)
            lo, hi = nlo, nhi
        return min(used), max(used)
    return walk_back_base


def make_is_base_candidate(sz, legacy):
    def _is_base_candidate(row, atr_value, config):
        if not getattr(config, "new_base", False):
            return legacy(row, atr_value, config)
        return is_base_candle(row, atr_value, config, sz)
    return _is_base_candidate


def new_base_config(cfg, role):
    """Copy of a legacy ZoneConfig with the new base logic switched on. role: 'htf' or 'ltf'."""
    kw = {"base_extension_atr_mult": float("inf")}
    if role == "ltf":
        kw["max_base_candles"] = C.LTF_BASE_CAP
        kw["max_base_range_to_leg_range"] = C.LTF_MAX_BASE_TO_LEG_RANGE
    if role == "htf":
        kw["max_base_candles"] = int(os.environ.get("DZ_HTF_CAP", C.HTF_BASE_CAP))  # runners: --htf-cap=N
        kw["base_extension_atr_mult"] = C.BASE_EXTENSION_ATR
        kw["max_base_range_to_leg_range"] = C.HTF_MAX_BASE_TO_LEG_RANGE
        if os.environ.get("DZ_STRICT_HTF") == "1":  # runners: --strict-htf
            kw["impulse_body_atr_mult"] = C.STRICT_HTF_IMPULSE_BODY_ATR
            kw["impulse_close_range_pct"] = C.STRICT_HTF_IMPULSE_CLOSE_POS
            kw["max_base_range_to_leg_range"] = C.STRICT_HTF_MAX_BASE_TO_LEG_RANGE
    out = replace(cfg, **kw)
    out.new_base = True
    out.legout_beyond_base_wick = bool(C.HTF_LEGOUT_CLOSE_BEYOND_BASE_WICK and os.environ.get("DZ_HTF_LEGOUT_WICK") != "0") if role == "htf" else False
    out.line_candles = C.LTF_LINE_CANDLES if role == "ltf" else None
    return out


def install(sz, mtz, combos=("dit", "dit15", "wit", "mit")):
    """Patch the legacy modules in this process. Call once, after offline_loader.install and any combo overrides."""
    if os.environ.get("DZ_BASE_LOGIC_V2") == "0" or not C.BASE_LOGIC_V2 and os.environ.get("DZ_BASE_LOGIC_V2") != "1":
        return  # legacy base logic (Baseline v1 reproduction)
    if getattr(sz, "_new_base_installed", False):
        return
    sz.walk_back_base = make_walk_back_base(sz, sz.walk_back_base)

    _legacy_valid = sz._is_valid_zone

    def _is_valid_zone(df, atr, base_start_idx, base_end_idx, leg_start_idx, leg_end_idx, proximal_line, distal_line,
                       direction, config=sz.DEFAULT_CONFIG):
        ok = _legacy_valid(df, atr, base_start_idx, base_end_idx, leg_start_idx, leg_end_idx, proximal_line, distal_line,
                           direction, config)
        if ok and getattr(config, "legout_beyond_base_wick", False):  # user rule: HTF legout closes over the base wick
            base = df.iloc[base_start_idx:base_end_idx + 1]
            close = df.iloc[leg_end_idx]["close"]
            ok = bool(close > base["high"].max()) if direction == "demand" else bool(close < base["low"].min())
        return ok

    sz._is_valid_zone = _is_valid_zone
    # sz._is_base_candidate (leg back-absorption) stays legacy on purpose: a directional candle just before the legout
    # (body > 0.5 ATR) belongs to the leg even if it has wicks (ACC Dec-2023).
    for name in combos:
        spec = mtz.COMBOS.get(name)
        if spec is None:
            continue
        spec.htf_config = new_base_config(spec.htf_config, "htf")
        spec.ltf_config = new_base_config(spec.ltf_config, "ltf")
        # trend_config stays legacy on purpose: trend zones are deliberately loose.
    # Identical zones (same type and lines) from two adjacent legouts would create the same trade twice (ARE&M 2025-04-07):
    # keep the earliest. Only for V2 configs, so the legacy trend zones are untouched.
    def _dedupe(legacy):
        def detect_zones(df, *args, **kwargs):
            zones = legacy(df, *args, **kwargs)
            cfg = kwargs.get("config", args[1] if len(args) > 1 else None)
            if not getattr(cfg, "new_base", False):
                return zones
            seen, out = set(), []
            for z in sorted(zones, key=lambda z: z.leg_start_index):
                key = (z.type, round(z.proximal_line, 6), round(z.distal_line, 6))
                if key not in seen:
                    seen.add(key)
                    out.append(z)
            return out
        return detect_zones
    sz.detect_zones = _dedupe(sz.detect_zones)
    mtz.detect_zones = _dedupe(mtz.detect_zones)
    sz._new_base_installed = True
