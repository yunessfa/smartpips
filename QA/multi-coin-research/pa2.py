"""Which part of the playbook carries the edge? Swap EMA pieces for pure price pieces, one at a time."""
import sys, numpy as np, pandas as pd
from common import *
from pa import structure
CFG = {"15m": dict(tp=2.5, h1=True), "1h": dict(tp=3.0, h1=False)}
def build(sym, tf, trend, anchor, n_mid=20):
    df = load(sym, tf)
    h4 = load(sym, "4h"); _, _, st4 = structure(h4, 3); h4["st"] = st4
    h4["mid"] = (h4.high.rolling(50).max() + h4.low.rolling(50).min()) / 2
    df = htf_merge(df, h4, ["e50", "e200", "close", "st", "mid"], "h4_")
    mid = (df.high.rolling(n_mid).max() + df.low.rolling(n_mid).min()) / 2
    if trend == "ema":
        U = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200); D = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
    elif trend == "structure":
        U = df.h4_st == 1; D = df.h4_st == -1
    else:  # range: 4h close vs the middle of its 50-bar high-low range
        U = df.h4_close > df.h4_mid; D = df.h4_close < df.h4_mid
    if anchor == "ema":
        local_up = (df.e21 > df.e50) & (df.e50 > df.e200); local_dn = (df.e21 < df.e50) & (df.e50 < df.e200); lvl = df.e21
    else:  # price-range midpoint of the last 20 bars; local trend = 20-bar mid rising vs 50 bars ago
        m50 = (df.high.rolling(100).max() + df.low.rolling(100).min()) / 2
        local_up = mid > m50; local_dn = mid < m50; lvl = mid
    st = (df.close - lvl) / df.atr; ok = (1.5 * df.atr / df.close * 100) >= 0.4
    L = U & local_up & (st > 1) & ok; Sx = D & local_dn & (st < -1) & ok
    sig = np.where(L, 1, np.where(Sx, -1, 0)); sig[:400] = 0
    return run(df, sig, 1.5 * df.atr, lim_px=lvl.values, wait=12, tgt_r=CFG[tf]["tp"], max_hold=72, bar_sec=BAR[tf], tp_taker=True)
if __name__ == "__main__":
    for tf in ("1h", "15m"):
        for trend, anchor in (("ema", "ema"), ("structure", "ema"), ("range", "ema"), ("ema", "price"), ("structure", "price"), ("range", "price")):
            t = pd.concat([build(s, tf, trend, anchor) for s in SYMS]).sort_values("time")
            print(fmt(f"{tf} trend={trend:9} entry={anchor}", t), flush=True)
