"""Exploration on the TRAIN period only (2019-2022). VA/HO are revealed later, once, for the chosen rules.

usage: python explore.py 15m            -> TRAIN tables
"""
import sys, json
import numpy as np, pandas as pd
from common import load, htf_merge
from lv import build_levels, detect, outcomes, SRC

TF = sys.argv[1]
REVEAL = len(sys.argv) > 2 and sys.argv[2] == "reveal"
BAR = {"5m": 300, "15m": 900, "1h": 3600}[TF]
TAKER, MAKER, SLIP, FUND = 0.0006, 0.0002, 0.0002, 0.0001
SPL = {"TR": ("2019-01-01", "2023-01-01"), "VA": ("2023-01-01", "2025-01-01"), "HO": ("2025-01-01", "2027-01-01")}

df = load(TF)
df = htf_merge(df, load("4h"), ["e50", "e200", "close"], "h4_")
lv = build_levels()
r = detect(df.time.values, df.high.values, df.low.values, df.close.values,
           lv.avail.values.astype(np.int64), lv.price.values, lv.is_high.values.astype(np.int64), lv.src.values.astype(np.int64))
for k, v in zip("hn hmax hmin hsrc hage ln lmax lmin lsrc lage up_room dn_room".split(), r):
    df[k] = v
up4 = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200)
dn4 = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
df["trend"] = np.where(up4, 1, np.where(dn4, -1, 0))
o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))


def ev_table():
    """one row per bar that swept at least one old level on exactly one side"""
    hi = (df.hn > 0) & (df.ln == 0); lo = (df.ln > 0) & (df.hn == 0)
    e = df[hi | lo].copy()
    e["side"] = np.where(e.hn > 0, 1, -1)                     # +1 = highs were taken, -1 = lows were taken
    e["Lout"] = np.where(e.side > 0, e.hmax, e.lmin)          # outermost swept level
    e["Lin"] = np.where(e.side > 0, e.hmin, e.lmax)           # innermost swept level
    e["src"] = np.where(e.side > 0, e.hsrc, e.lsrc)
    e["age"] = np.where(e.side > 0, e.hage, e.lage)
    e["nlev"] = np.where(e.side > 0, e.hn, e.ln)
    # reclaim = closed back inside ALL swept levels ; breakout = closed beyond ALL swept levels
    e["reclaim"] = np.where(e.side > 0, e.close < e.Lin, e.close > e.Lin)
    e["breakout"] = np.where(e.side > 0, e.close > e.Lout + 0.25 * e.atr, e.close < e.Lout - 0.25 * e.atr)
    e["ext"] = np.where(e.side > 0, e.high, e.low)            # extreme of the sweep bar
    return e


def seg(e, name):
    a, b = (pd.Timestamp(x).timestamp() for x in SPL[name])
    return e[(e.time >= a) & (e.time < b)]


def line(lbl, R):
    R = R[~np.isnan(R)]
    if len(R) < 30:
        return f"{lbl:34s} n={len(R):5d}  (too few)"
    se = R.std(ddof=1) / np.sqrt(len(R))
    pos, neg = R[R > 0].sum(), -R[R <= 0].sum()
    return f"{lbl:34s} n={len(R):5d} win={100*(R>0).mean():5.1f}% expR={R.mean():+.3f} t={R.mean()/se:+.1f} PF={pos/neg:.2f}"


def run_events(e, kind, tgt, minstop=0.40, maxstop_atr=3.0):
    """kind = 'fade' (sweep & reclaim, market next open, stop behind the wick)
              'retest' (breakout, LIMIT back at the level, stop 1.5 ATR)
              'follow' (breakout, market next open, stop 1.5 ATR)"""
    if kind == "fade":
        e = e[e.reclaim]
        d = -e.side.values
        sd = np.abs(e.ext.values - e.close.values) + 0.1 * e.atr.values
        lim = np.zeros(len(e))
    else:
        e = e[e.breakout]
        d = e.side.values
        sd = 1.5 * e.atr.values
        lim = e.Lout.values if kind == "retest" else np.zeros(len(e))
    ok = (sd / e.close.values * 100 >= minstop) & (sd <= maxstop_atr * e.atr.values)
    e = e[ok]; d = d[ok]; sd = sd[ok]; lim = lim[ok]
    R = outcomes(o, h, l, c, e.index.values.astype(np.int64), d.astype(np.int64), sd, lim, float(tgt), 72, 12,
                 float(BAR), TAKER, MAKER, SLIP, FUND)
    e = e.assign(R=R, dir=d, sd=sd)
    return e


if __name__ == "__main__":
    E = ev_table()
    print(f"== {TF}: bars={len(df)} sweep-bars={len(E)} levels={len(lv)}")
    parts = ["TR", "VA", "HO"] if REVEAL else ["TR"]
    for kind, tgt in (("fade", 2.0), ("fade", 3.0), ("retest", 2.5), ("follow", 2.5)):
        full = run_events(E, kind, tgt)
        for part in parts:
            x = seg(full, part)
            print(f"\n--- {kind} tgt={tgt}R [{part}]")
            print(line("ALL", x.R.values))
            al = x.dir * x.trend
            print(line("with 4h trend", x.R[al > 0].values))
            print(line("against 4h trend", x.R[al < 0].values))
            print(line("no 4h trend", x.R[al == 0].values))
            for nm, bit in SRC.items():
                print(line(f"src has {nm}", x.R[(x.src & bit) > 0].values))
            print(line("W or M (major)", x.R[(x.src & 6) > 0].values))
            print(line("age < 2d", x.R[x.age < 2].values))
            print(line("age 2-14d", x.R[(x.age >= 2) & (x.age < 14)].values))
            print(line("age 14-90d", x.R[(x.age >= 14) & (x.age < 90)].values))
            print(line("age > 90d", x.R[x.age >= 90].values))
            print(line("nlev >= 3", x.R[x.nlev >= 3].values))
            print(line("major & with trend", x.R[((x.src & 6) > 0) & (al > 0)].values))
            print(line("major & against trend", x.R[((x.src & 6) > 0) & (al < 0)].values))
            print(line("age>=14 & with trend", x.R[(x.age >= 14) & (al > 0)].values))
            print(line("age>=14 & against trend", x.R[(x.age >= 14) & (al < 0)].values))
