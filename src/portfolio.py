"""Deterministic sequencing, drawdown, concurrency and summary metrics (Phase A, A9/A10).

Conventions (documented, unchanged from the legacy strategy):
  starting capital Rs 1,00,000; risk cap Rs 1,000 per trade; shares = min(floor(1000/risk), floor(100000/entry));
  no leverage (a position's notional never exceeds capital); 2:1 target; no time exit.
  "All signals" metrics (the legacy baseline convention, user 28 Sep) ignore the capital limit: every triggered trade counts.
  The capital-constrained variant replays legacy run_capital_constrained: trades taken in fill-time order (ties: ticker, then
  entry price) while deployed notional + new notional <= capital; a position frees its capital at its exit time; an unresolved
  position (OPEN / CENSORED / AMBIGUOUS without an exit time) holds its capital to the end.
R series: resolved trades (WIN/LOSS) ordered by exit time, then fill time, then ticker. Drawdown is measured on the cumulative
R curve (each trade = its own R, independent of rupee size) and, separately, on rupees.
"""
import numpy as np
import pandas as pd

CAPITAL = 100_000.0
MAX_LOSS_PER_TRADE = 1_000.0
RESOLVED = ("WIN", "LOSS")


def order(df):
    """Deterministic order for the R curve."""
    return df.sort_values(["exit_time", "fill_time", "ticker", "entry_price"], kind="mergesort")


def max_drawdown(values):
    """Largest peak-to-trough fall of the cumulative sum of `values` (>= 0), starting from 0."""
    if len(values) == 0:
        return 0.0
    cum = np.concatenate([[0.0], np.cumsum(np.asarray(values, dtype=float))])
    return float((np.maximum.accumulate(cum) - cum).max())


def concurrency(df):
    """Max number of simultaneously open positions and peak deployed notional (all signals, no capital limit)."""
    ev = []
    far = pd.Timestamp.max
    for t in df.itertuples():
        if pd.isna(t.fill_time):
            continue
        end = t.exit_time if not pd.isna(t.exit_time) else far
        ev.append((pd.Timestamp(t.fill_time), 1, t.shares * t.fill_price))
        ev.append((pd.Timestamp(end), -1, -t.shares * t.fill_price))
    ev.sort(key=lambda e: (e[0], e[1]))  # exits before entries at the same instant
    n = peak_n = 0
    dep = peak_dep = 0.0
    for _, dn, dv in ev:
        n += dn
        dep += dv
        peak_n, peak_dep = max(peak_n, n), max(peak_dep, dep)
    return peak_n, peak_dep


def capital_constrained(df, capital=CAPITAL):
    """Boolean Series: trade taken under the capital limit (deterministic version of legacy run_capital_constrained)."""
    d = df[~df["fill_time"].isna()].sort_values(["fill_time", "ticker", "entry_price"], kind="mergesort")
    taken = pd.Series(False, index=df.index)
    open_pos = []
    deployed = 0.0
    for idx, t in d.iterrows():
        now = pd.Timestamp(t["fill_time"])
        keep = []
        for end, cost in open_pos:
            if end <= now:
                deployed -= cost
            else:
                keep.append((end, cost))
        open_pos = keep
        cost = t["shares"] * t["fill_price"]
        if cost > capital:
            continue
        if deployed + cost <= capital + 1e-6:
            end = pd.Timestamp(t["exit_time"]) if not pd.isna(t["exit_time"]) else pd.Timestamp.max
            open_pos.append((end, cost))
            deployed += cost
            taken[idx] = True
    return taken


def boot_ci(wins, n, reps=5000):
    """Same bootstrap as scripts/replay_common.boot_ci (fixed seed)."""
    if n == 0:
        return "n/a"
    x = np.random.default_rng(12345).binomial(n, wins / n, reps) / n
    lo, hi = np.percentile(x, [2.5, 97.5])
    return f"[{100 * lo:.0f}-{100 * hi:.0f}]"


def summary(df, rcol="r_gross"):
    """Metrics over one slice. Win rate / expectancy / PF / total R / DD use resolved trades (WIN, LOSS) only.
    AMBIGUOUS trades are reported with best (+2R gross, all win) and worst (-1R, all loss) bounds; OPEN/CENSORED/NOFILL counted."""
    c = df["outcome"].value_counts()
    w, l = int(c.get("WIN", 0)), int(c.get("LOSS", 0))
    res = order(df[df["outcome"].isin(RESOLVED)])
    r = res[rcol].to_numpy(dtype=float)
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    out = dict(n=len(df), WIN=w, LOSS=l, AMBIGUOUS=int(c.get("AMBIGUOUS", 0)), OPEN=int(c.get("OPEN", 0)),
               CENSORED=int(c.get("CENSORED", 0)), NOFILL=int(c.get("NOFILL", 0)),
               win_rate=100 * w / (w + l) if w + l else np.nan, boot95=boot_ci(w, w + l),
               expectancy_r=r.mean() if len(r) else np.nan, profit_factor=pos / neg if neg > 0 else np.nan,
               total_r=r.sum(), max_dd_r=max_drawdown(r))
    amb = int(c.get("AMBIGUOUS", 0))
    if amb:
        out["win_rate_amb_best"] = 100 * (w + amb) / (w + l + amb)
        out["win_rate_amb_worst"] = 100 * w / (w + l + amb)
        out["total_r_amb_best"] = r.sum() + 2.0 * amb
        out["total_r_amb_worst"] = r.sum() - 1.0 * amb
    return out


def fmt(label, s):
    flag = "  SAMPLE<30" if s["n"] < 30 else ""
    txt = (f"{label:<22} n={s['n']:4d} W={s['WIN']:4d} L={s['LOSS']:4d} AMB={s['AMBIGUOUS']:3d} OPEN={s['OPEN']:3d} "
           f"CENS={s['CENSORED']:3d} NOFILL={s['NOFILL']:2d} win%={s['win_rate']:5.1f} {s['boot95']:>9} "
           f"expR={s['expectancy_r']:+.3f} PF={s['profit_factor']:.2f} totR={s['total_r']:+7.1f} maxDD_R={s['max_dd_r']:5.1f}{flag}")
    if s["AMBIGUOUS"]:
        txt += (f"\n{'':<22}   AMBIGUOUS bounds: win% {s['win_rate_amb_worst']:.1f}..{s['win_rate_amb_best']:.1f}, "
                f"totR {s['total_r_amb_worst']:+.1f}..{s['total_r_amb_best']:+.1f}")
    return txt
