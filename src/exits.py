"""Trade exit simulation on minute bars."""
import numpy as np

DEFAULT_REPLAY_INTERVAL = "15minute"  # Kite interval the bars passed to minute_replay are expected to have


def _first_event(o, h, l, start, demand, stop, target, fill):
    """First stop/target event at minute index >= start. Returns (label, j, exit_price, detail)."""
    n = len(o)
    if start >= n:
        return "OPEN", None, None, ""
    stop_hit = (l[start:] <= stop) if demand else (h[start:] >= stop)
    tgt_hit = (h[start:] >= target) if demand else (l[start:] <= target)
    ev = stop_hit | tgt_hit
    if not ev.any():
        return "OPEN", None, None, ""
    k = int(np.argmax(ev))
    j = start + k
    gap_stop = (o[j] <= stop) if demand else (o[j] >= stop)
    gap_tgt = (o[j] >= target) if demand else (o[j] <= target)
    if gap_stop:
        return "loss", j, float(o[j]), "gap through stop"
    if gap_tgt:
        return "win", j, float(target), "gap through target (booked at target)"
    if stop_hit[k] and tgt_hit[k]:
        return "AMBIGUOUS", j, None, "stop+target in same minute"
    if stop_hit[k]:
        return "loss", j, float(stop), ""
    return "win", j, float(target), ""


def minute_replay(minute_bars, zone_type, entry, stop, target, scan_start):
    """Replay one trade on intraday bars (default 15minute; the rules are bar-size agnostic, so "minute" below
    means one bar). Columns: timestamp, open, high, low, close.

    Fill = first minute at/after scan_start that trades into the zone (open if it gaps beyond the entry level).
    Stop and target exist only after the fill. In the fill minute only the stop counts; if that minute's range
    also reaches the target the outcome is AMBIGUOUS. Stop and target in the same later minute is AMBIGUOUS.
    A gap through the stop exits at the open (R below -1). Target exits are booked at the target price.
    Returns dict: outcome (win/loss/AMBIGUOUS/OPEN/NOFILL), r, fill_time, fill_price, gap_fill, exit_time,
    exit_price, detail, later (outcome if the fill-minute target is ignored, AMBIGUOUS-in-fill-minute only).
    """
    demand = zone_type == "demand"
    risk = abs(entry - stop)
    sign = 1.0 if demand else -1.0
    res = dict(outcome="NOFILL", r=None, fill_time=None, fill_price=None, gap_fill=False,
               exit_time=None, exit_price=None, detail="", later="")
    scan = minute_bars[minute_bars["timestamp"] >= scan_start].reset_index(drop=True)
    if scan.empty:
        return res
    ts = scan["timestamp"].to_numpy()
    o, h, l = (scan[c].to_numpy(dtype=float) for c in ("open", "high", "low"))
    reach = (l <= entry) if demand else (h >= entry)
    if not reach.any():
        return res
    i = int(np.argmax(reach))
    gap = bool((o[i] < entry) if demand else (o[i] > entry))
    fill = float(o[i]) if gap else float(entry)
    res.update(outcome="OPEN", fill_time=ts[i], fill_price=fill, gap_fill=gap)

    def finish(label, j, exit_price, detail):
        res.update(outcome=label, exit_time=ts[j] if j is not None else None, exit_price=exit_price, detail=detail)
        if label in ("win", "loss") and exit_price is not None:
            res["r"] = sign * (exit_price - fill) / risk
        return res

    s0 = bool((l[i] <= stop) if demand else (h[i] >= stop))
    t0 = bool((h[i] >= target) if demand else (l[i] <= target))
    gap_beyond_stop = gap and bool((o[i] <= stop) if demand else (o[i] >= stop))
    if gap_beyond_stop:
        return finish("AMBIGUOUS", i, None, "gap-fill opens beyond the stop")
    if s0 and t0:
        return finish("AMBIGUOUS", i, None, "stop+target both in fill minute")
    if t0:
        lab, j, px, det = _first_event(o, h, l, i + 1, demand, stop, target, fill)
        res["later"] = lab
        return finish("AMBIGUOUS", i, None, "target in fill minute (could be pre-entry)")
    if s0:
        return finish("loss", i, float(stop), "stop in fill minute")
    lab, j, px, det = _first_event(o, h, l, i + 1, demand, stop, target, fill)
    if lab == "OPEN":
        return res
    return finish(lab, j, px, det)


def replay_trade(kite, symbol, token, zone_type, entry, stop, target, scan_start, horizon_days=90, now=None):
    """Full automatic exit scoring (standing rule): 15minute replay, then a 1minute drill-down if AMBIGUOUS.

    `kite` is a KiteReadOnly (historical_data only); everything goes through its disk cache.
    Returns dict: outcome (win/loss/AMBIGUOUS/OPEN/NOFILL), decided_interval ("15minute"/"1minute"/None),
    reason (why still AMBIGUOUS, "" otherwise), r15_outcome, no_minute_data, plus r, fill_time, fill_price,
    gap_fill, exit_time, exit_price, detail from the deciding replay.
    No Kite data for the trade -> outcome AMBIGUOUS, reason NO_MINUTE_DATA, no_minute_data True.
    """
    from datetime import datetime, timedelta
    import pandas as pd

    now = now or datetime.now()
    scan_start = pd.Timestamp(scan_start)
    d0 = scan_start.normalize().to_pydatetime()
    horizon = timedelta(days=horizon_days)
    out = dict(outcome="AMBIGUOUS", decided_interval=None, reason="", r15_outcome="", no_minute_data=False,
               r=None, fill_time=None, fill_price=None, gap_fill=False, exit_time=None, exit_price=None, detail="")

    def run(interval, windows):
        bars = None
        res = None
        for a, b in windows:
            if bars is not None and a >= now:
                break
            m = kite.historical_data(token, a, b, interval, symbol=symbol)
            bars = m if bars is None else pd.concat([bars, m]).drop_duplicates("timestamp").sort_values("timestamp")
            if len(bars):
                bars["timestamp"] = pd.to_datetime(bars["timestamp"])
                if bars["timestamp"].min().normalize() > scan_start.normalize():
                    return None
                res = minute_replay(bars.reset_index(drop=True), zone_type, entry, stop, target, scan_start)
                if res["outcome"] not in ("OPEN", "NOFILL"):
                    return res
        return res

    def no_data(why):
        out.update(outcome="AMBIGUOUS", reason="NO_MINUTE_DATA" + (f" ({why})" if why else ""), no_minute_data=True)
        return out

    try:
        r15 = run("15minute", [(d0, d0 + horizon)])
        if r15 is None:
            return no_data("15minute")
        out["r15_outcome"] = r15["outcome"]
        if r15["outcome"] != "AMBIGUOUS":
            out.update({k: r15[k] for k in ("outcome", "r", "fill_time", "fill_price", "gap_fill", "exit_time", "exit_price", "detail")})
            out["decided_interval"] = "15minute"
            return out
        out.update({k: r15[k] for k in ("r", "fill_time", "fill_price", "gap_fill", "exit_time", "exit_price", "detail")})
        step = timedelta(days=60)
        r1 = run("minute", [(d0, d0 + step), (d0 + step, d0 + horizon)])
        if r1 is None:
            return no_data("1minute")
    except Exception as e:  # Kite refused the range (e.g. too old) -> keep AMBIGUOUS, count it
        return no_data(type(e).__name__)
    out.update({k: r1[k] for k in ("outcome", "r", "fill_time", "fill_price", "gap_fill", "exit_time", "exit_price", "detail")})
    out["decided_interval"] = "1minute"
    if r1["outcome"] == "AMBIGUOUS":
        out["reason"] = r1["detail"]
    return out
