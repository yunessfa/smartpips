"""Old-level research helpers (no look-ahead).

A level becomes usable only after the period that formed it has CLOSED:
  D  = each completed UTC day's high / low
  W  = each completed week's high / low (Mon 00:00 UTC)
  M  = each completed calendar month's high / low
  P4 = confirmed 4h pivot high / low (3 bars each side)
  PD = confirmed daily pivot high / low (2 bars each side)
A level stays ACTIVE (untaken liquidity) until a later bar trades through it.
"""
import numpy as np, pandas as pd
from numba import njit

from common import DATA, PREFIX

SRC = {"D": 1, "W": 2, "M": 4, "P4": 8, "PD": 16}


def _pivots(df, k, step, bit):
    h, l, t = df.high.values, df.low.values, df.time.values
    rows = []
    for p in range(k, len(df) - k):
        if h[p] > h[p - k:p].max() and h[p] >= h[p + 1:p + k + 1].max():
            rows.append((t[p + k] + step, h[p], 1, bit, t[p]))
        if l[p] < l[p - k:p].min() and l[p] <= l[p + 1:p + k + 1].min():
            rows.append((t[p + k] + step, l[p], 0, bit, t[p]))
    return rows


def build_levels():
    d = pd.read_parquet(f"{DATA}{PREFIX}_1d.parquet")
    h4 = pd.read_parquet(f"{DATA}{PREFIX}_4h.parquet")
    rows = []
    for _, r in d.iterrows():
        rows.append((r.time + 86400, r.high, 1, SRC["D"], r.time))
        rows.append((r.time + 86400, r.low, 0, SRC["D"], r.time))
    dt = pd.to_datetime(d.time, unit="s")
    wk = d.groupby(dt.dt.to_period("W-SUN")).agg(high=("high", "max"), low=("low", "min"), t0=("time", "min"), n=("time", "size"))
    for per, r in wk.iterrows():
        avail = int(per.end_time.timestamp()) + 1
        rows.append((avail, r.high, 1, SRC["W"], r.t0)); rows.append((avail, r.low, 0, SRC["W"], r.t0))
    mo = d.groupby(dt.dt.to_period("M")).agg(high=("high", "max"), low=("low", "min"), t0=("time", "min"))
    for per, r in mo.iterrows():
        avail = int(per.end_time.timestamp()) + 1
        rows.append((avail, r.high, 1, SRC["M"], r.t0)); rows.append((avail, r.low, 0, SRC["M"], r.t0))
    rows += _pivots(h4, 3, 14400, SRC["P4"])
    rows += _pivots(d, 2, 86400, SRC["PD"])
    lv = pd.DataFrame(rows, columns=["avail", "price", "is_high", "src", "formed"]).sort_values("avail").reset_index(drop=True)
    last = int(d.time.iloc[-1]) + 86400          # the still-forming last day/week/month is never used
    return lv[lv.avail <= last].reset_index(drop=True)


@njit(cache=True)
def detect(time, h, l, c, lv_t, lv_p, lv_hi, lv_src):
    """Per bar: which ACTIVE old levels did this bar trade through, and how much room is left.

    Returns arrays (n = bars):
      hn, hmax, hmin, hsrc, hage  : swept highs  (count, highest, lowest, source mask, oldest age in days)
      ln, lmax, lmin, lsrc, lage  : swept lows
      up_room, dn_room            : nearest still-active high above / low below the close (price, nan if none)
    Levels are added only when avail <= bar OPEN time, so the bar never sees a level formed inside itself.
    """
    n = len(c); m = len(lv_t)
    hn = np.zeros(n, np.int64); ln = np.zeros(n, np.int64)
    hmax = np.full(n, np.nan); hmin = np.full(n, np.nan); lmax = np.full(n, np.nan); lmin = np.full(n, np.nan)
    hsrc = np.zeros(n, np.int64); lsrc = np.zeros(n, np.int64)
    hage = np.zeros(n); lage = np.zeros(n)
    up_room = np.full(n, np.nan); dn_room = np.full(n, np.nan)
    ah = np.empty(m, np.int64); al = np.empty(m, np.int64)   # active level indices
    nh = 0; nl = 0; p = 0
    for i in range(n):
        while p < m and lv_t[p] <= time[i]:
            if lv_hi[p] == 1:
                ah[nh] = p; nh += 1
            else:
                al[nl] = p; nl += 1
            p += 1
        # highs
        k = 0; best = np.inf
        for q in range(nh):
            j = ah[q]; px = lv_p[j]
            if h[i] > px:
                hn[i] += 1; hsrc[i] |= lv_src[j]
                if np.isnan(hmax[i]) or px > hmax[i]: hmax[i] = px
                if np.isnan(hmin[i]) or px < hmin[i]: hmin[i] = px
                a = (time[i] - lv_t[j]) / 86400.0
                if a > hage[i]: hage[i] = a
            else:
                ah[k] = j; k += 1
                if px > c[i] and px < best: best = px
        nh = k
        if best < np.inf: up_room[i] = best
        k = 0; best = -np.inf
        for q in range(nl):
            j = al[q]; px = lv_p[j]
            if l[i] < px:
                ln[i] += 1; lsrc[i] |= lv_src[j]
                if np.isnan(lmax[i]) or px > lmax[i]: lmax[i] = px
                if np.isnan(lmin[i]) or px < lmin[i]: lmin[i] = px
                a = (time[i] - lv_t[j]) / 86400.0
                if a > lage[i]: lage[i] = a
            else:
                al[k] = j; k += 1
                if px < c[i] and px > best: best = px
        nl = k
        if best > -np.inf: dn_room[i] = best
    return hn, hmax, hmin, hsrc, hage, ln, lmax, lmin, lsrc, lage, up_room, dn_room


@njit(cache=True)
def nearest_hist(time, px, lv_t, lv_p, lookback_days):
    """Distance from px[i] to the nearest level (taken or not) that became known in the last N days."""
    n = len(px); m = len(lv_t); out = np.full(n, np.nan)
    lo = 0; hi = 0
    for i in range(n):
        while hi < m and lv_t[hi] <= time[i]: hi += 1
        while lo < hi and lv_t[lo] < time[i] - lookback_days * 86400: lo += 1
        if np.isnan(px[i]): continue
        best = np.inf
        for j in range(lo, hi):
            dd = abs(lv_p[j] - px[i])
            if dd < best: best = dd
        if best < np.inf: out[i] = best
    return out


@njit(cache=True)
def outcomes(o, h, l, c, idx, dirs, sd, lim, tgt_r, max_hold, wait, bar_sec, taker, maker, slip, fund8h):
    """Independent outcome of each event (R net of costs; nan = limit never filled). TP is paid as a market exit."""
    n = len(c); out = np.full(len(idx), np.nan)
    for a in range(len(idx)):
        i = idx[a]; d = dirs[a]; s = sd[a]
        if i + 1 >= n or s <= 0: continue
        fee_in = taker; fi = -1; is_lim = lim[a] > 0
        if is_lim:
            lp = lim[a]
            for j in range(i + 1, min(i + 1 + wait, n)):
                if (d > 0 and l[j] <= lp) or (d < 0 and h[j] >= lp):
                    fi = j
                    if (d > 0 and o[j] <= lp) or (d < 0 and o[j] >= lp): e = o[j]
                    else:
                        e = lp; fee_in = maker
                    break
            if fi < 0: continue
        else:
            fi = i + 1; e = o[fi] * (1 + slip * d)
        stop = e - d * s; tgt = e + d * s * tgt_r
        ex = np.nan; xi = fi; j = fi
        while j < n:
            if (d > 0 and l[j] <= stop) or (d < 0 and h[j] >= stop):
                if d > 0: ex = min(stop, o[j]) if j > fi else stop
                else: ex = max(stop, o[j]) if j > fi else stop
                ex = ex * (1 - slip * d); xi = j; break
            if not (is_lim and j == fi):
                if (d > 0 and h[j] >= tgt) or (d < 0 and l[j] <= tgt):
                    ex = tgt * (1 - slip * d); xi = j; break
            if j - fi >= max_hold:
                ex = c[j] * (1 - slip * d); xi = j; break
            j += 1
        if j >= n: ex = c[n - 1]; xi = n - 1
        pct = (ex - e) * d / e - fee_in - taker - fund8h * ((xi - fi + 1) * bar_sec / 3600.0) / 8.0
        out[a] = pct * e / s
    return out
