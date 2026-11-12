"""Old price levels (untaken highs / lows of past days, weeks, months and swings).

CONTEXT ONLY. The 2026-11 study (QA/old-levels-research) tested these levels on
BTC 2019-2026 as entry signals (sweep & reclaim, break & retest, breakout) and
as a filter on the trend-pullback playbook: no edge after costs. They are drawn
on the chart and listed for the trader; they do not change any decision.

Rules (identical to the study, so what is drawn is what was tested):
  * a level exists only after the period that formed it has CLOSED
      D  = each completed day's high / low
      W  = each completed week's high / low (week starts Monday 00:00 UTC)
      M  = each completed calendar month's high / low
      PD = confirmed daily pivot (2 bars each side)
      P4 = confirmed 4h pivot (3 bars each side)
  * a level is UNTAKEN until a later bar trades through it; taken levels are
    dropped (the three "previous period" pairs are still reported, flagged).
"""
from bisect import bisect_left
from datetime import datetime, timezone

DAY = 86400
H4 = 14400
WEIGHT = {"M": 3, "W": 2, "D": 1, "PD": 1, "P4": 1}
ORDER = ("M", "W", "D", "PD", "P4")


def _clean(bars, step, now):
    """Sorted, de-duplicated, finite bars; returns (closed, all)."""
    seen, out = set(), []
    for c in bars or []:
        try:
            t = int(c["time"])
            o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if t in seen or not (h >= l > 0) or h != h or l != l:
            continue
        seen.add(t)
        out.append({"time": t, "open": o, "high": h, "low": l, "close": cl})
    out.sort(key=lambda c: c["time"])
    closed = [c for c in out if c["time"] + step <= now]
    return closed, out


def _utc(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _week_start(ts):
    d = _utc(ts)
    return ts - d.weekday() * DAY - d.hour * 3600 - d.minute * 60 - d.second


def _month_key(ts):
    d = _utc(ts)
    return d.year, d.month


def _next_month_start(key):
    y, m = key
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())


def _pivots(bars, k, step, src):
    out = []
    n = len(bars)
    for p in range(k, n - k):
        hi, lo = bars[p]["high"], bars[p]["low"]
        left, right = bars[p - k:p], bars[p + 1:p + k + 1]
        avail = bars[p + k]["time"] + step
        if hi > max(b["high"] for b in left) and hi >= max(b["high"] for b in right):
            out.append({"price": hi, "kind": "high", "src": src, "formed": bars[p]["time"], "avail": avail})
        if lo < min(b["low"] for b in left) and lo <= min(b["low"] for b in right):
            out.append({"price": lo, "kind": "low", "src": src, "formed": bars[p]["time"], "avail": avail})
    return out


def build_levels(daily_closed, h4_closed):
    """Every level that has ever formed, with the moment it became known (`avail`)."""
    levels = []
    if not daily_closed:
        return levels
    closed_until = daily_closed[-1]["time"] + DAY
    for c in daily_closed:
        for kind, key in (("high", "high"), ("low", "low")):
            levels.append({"price": c[key], "kind": kind, "src": "D", "formed": c["time"], "avail": c["time"] + DAY})
    weeks, months = {}, {}
    for c in daily_closed:
        for bucket, key in ((weeks, _week_start(c["time"])), (months, _month_key(c["time"]))):
            g = bucket.setdefault(key, {"high": c["high"], "low": c["low"], "t0": c["time"]})
            g["high"] = max(g["high"], c["high"])
            g["low"] = min(g["low"], c["low"])
    for start, g in weeks.items():
        avail = start + 7 * DAY
        if avail <= closed_until:                       # the forming week is never a level
            for kind in ("high", "low"):
                levels.append({"price": g[kind], "kind": kind, "src": "W", "formed": g["t0"], "avail": avail})
    for key, g in months.items():
        avail = _next_month_start(key)
        if avail <= closed_until:
            for kind in ("high", "low"):
                levels.append({"price": g[kind], "kind": kind, "src": "M", "formed": g["t0"], "avail": avail})
    levels += _pivots(daily_closed, 2, DAY, "PD")
    levels += _pivots(h4_closed or [], 3, H4, "P4")
    return levels


class _Suffix:
    """max high / min low of all bars whose OPEN time is >= t."""

    def __init__(self, bars):
        self.times = [b["time"] for b in bars]
        n = len(bars)
        self.hi = [float("-inf")] * (n + 1)
        self.lo = [float("inf")] * (n + 1)
        for i in range(n - 1, -1, -1):
            self.hi[i] = max(self.hi[i + 1], bars[i]["high"])
            self.lo[i] = min(self.lo[i + 1], bars[i]["low"])

    def after(self, t):
        i = bisect_left(self.times, t)
        return self.hi[i], self.lo[i]


def mark_taken(levels, *bar_sets):
    """Flag each level as taken if any bar that OPENED at/after `avail` traded through it.

    Bars are only counted when they open at or after the level became known, so a
    level is never "taken" by the very move that formed it. Several series can be
    passed (daily, 4h, a recent low-timeframe window); each is checked the same way.
    """
    views = [_Suffix(b) for b in bar_sets if b]
    for lv in levels:
        hi = max((v.after(lv["avail"])[0] for v in views), default=float("-inf"))
        lo = min((v.after(lv["avail"])[1] for v in views), default=float("inf"))
        lv["taken"] = hi > lv["price"] if lv["kind"] == "high" else lo < lv["price"]
    return levels


def _label(srcs, kind, previous):
    top = next(s for s in ORDER if s in srcs)
    suffix = "H" if kind == "high" else "L"
    if top in ("M", "W", "D"):
        return ("P" if top in previous else "") + top + suffix
    return ("Swing D " if top == "PD" else "Swing 4h ") + suffix


def _pick(side, minor, major):
    """Nearest `minor` ordinary levels plus nearest `major` week/month levels, nearest first.

    Without this split a trend prints a staircase of daily highs and the weekly and
    monthly levels - the ones that matter most - never make the list.
    """
    majors = [x for x in side if x["major"]][:major]
    minors = [x for x in side if not x["major"]][:minor]
    return sorted(majors + minors, key=lambda x: abs(x["distance_pct"] or 0))


def summarize(daily, h4, price=None, now=None, recent=None, minor=3, major=3):
    """Chart-ready old levels around `price`.

    `recent` is an optional low-timeframe window (e.g. the last 200 5m bars) used only
    to notice levels taken since the last daily / 4h refresh and to supply the price.
    Returns {"levels": [...above (nearest first), then below (nearest first)...],
             "previous": {...}, "price", "counts", "history_days"}; an empty result when
    there is no usable history.
    """
    import time as _time
    now = _time.time() if now is None else now
    d_closed, d_all = _clean(daily, DAY, now)
    h_closed, h_all = _clean(h4, H4, now)
    _, r_all = _clean(recent, 1, now)
    empty = {"levels": [], "previous": {}, "price": price, "counts": {"all": 0, "untaken": 0}, "history_days": 0}
    if len(d_closed) < 10:
        return empty
    if price is None:
        price = (r_all or h_all or d_all)[-1]["close"]
    price = float(price)
    levels = mark_taken(build_levels(d_closed, h_closed), d_all, h_all, r_all)

    # the most recent completed day / week / month, reported even when already taken
    last = {}
    for lv in levels:
        if lv["src"] in ("D", "W", "M"):
            cur = last.get(lv["src"])
            if cur is None or lv["avail"] > cur:
                last[lv["src"]] = lv["avail"]
    previous = {}
    for lv in levels:
        if lv["src"] in last and lv["avail"] == last[lv["src"]]:
            name = "P" + lv["src"] + ("H" if lv["kind"] == "high" else "L")
            previous[name] = {"price": lv["price"], "taken": lv["taken"]}

    merged = {}
    for lv in levels:
        if lv["taken"]:
            continue
        m = merged.setdefault((lv["kind"], lv["price"]), {"price": lv["price"], "kind": lv["kind"], "srcs": set(),
                                                         "prev": set(), "avail": lv["avail"], "formed": lv["formed"]})
        m["srcs"].add(lv["src"])
        if lv["src"] in last and lv["avail"] == last[lv["src"]]:
            m["prev"].add(lv["src"])
        m["avail"] = min(m["avail"], lv["avail"])
        m["formed"] = min(m["formed"], lv["formed"])
    out = []
    for m in merged.values():
        srcs = [s for s in ORDER if s in m["srcs"]]
        out.append({
            "price": m["price"], "kind": m["kind"], "sources": srcs,
            "label": _label(srcs, m["kind"], m["prev"]), "major": bool({"W", "M"} & m["srcs"]),
            "weight": max(WEIGHT[s] for s in srcs) + (1 if len(srcs) > 1 else 0),
            "formed": m["formed"], "age_days": round(max(0.0, (now - m["avail"]) / DAY), 1),
            "distance_pct": round((m["price"] - price) / price * 100, 3) if price else None,
        })
    above = sorted((x for x in out if x["kind"] == "high" and x["price"] > price), key=lambda x: x["price"])
    below = sorted((x for x in out if x["kind"] == "low" and x["price"] < price), key=lambda x: -x["price"])
    return {"levels": _pick(above, minor, major) + _pick(below, minor, major), "previous": previous, "price": price,
            "counts": {"all": len(levels), "untaken": len(out), "above": len(above), "below": len(below)},
            "history_days": len(d_closed)}
