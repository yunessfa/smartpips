"""Spike strategies, pre-registered grid. Selection on TR (2021-2023) only."""
import sys, itertools, numpy as np, pandas as pd
from common import *
def prep(sym, tf):
    df = load(sym, tf); df = htf_merge(df, load(sym, "4h"), ["e50","e200","close"], "h4_")
    rng = df.high-df.low; a0 = df.atr.shift(1); v0 = df.vma.shift(1)
    df["rng_atr"] = rng/a0; df["vol_x"] = df.volume/v0
    df["pos"] = (df.close-df.low)/rng.replace(0,np.nan)         # close location 0..1
    df["lw"] = (np.minimum(df.open,df.close)-df.low)/rng.replace(0,np.nan)
    df["uw"] = (df.high-np.maximum(df.open,df.close))/rng.replace(0,np.nan)
    df["up4"] = (df.h4_close>df.h4_e200)&(df.h4_e50>df.h4_e200); df["dn4"] = (df.h4_close<df.h4_e200)&(df.h4_e50<df.h4_e200)
    return df
def variant(df, kind, K, V, tgt, tf, minstop=0.4):
    spike = (df.rng_atr>=K)&(df.vol_x>=V)
    n = len(df); sig = np.zeros(n); sd = np.full(n, np.nan); lim = np.zeros(n); wait = 0
    if kind == "fade":        # fade a momentum spike, market next open, stop beyond spike extreme
        L = spike&(df.pos<=0.3)&(df.close<df.open); S = spike&(df.pos>=0.7)&(df.close>df.open)
        sdist = np.where(L, df.close-df.low, df.high-df.close)+0.2*df.atr
    elif kind == "wick":      # liquidation-wick rejection: long lower wick, close back up
        L = spike&(df.lw>=0.6); S = spike&(df.uw>=0.6)
        sdist = np.where(L, df.close-df.low, df.high-df.close)+0.1*df.atr
    elif kind == "wick_trend":
        L = spike&(df.lw>=0.6)&df.up4; S = spike&(df.uw>=0.6)&df.dn4
        sdist = np.where(L, df.close-df.low, df.high-df.close)+0.1*df.atr
    elif kind == "mom":       # momentum continuation with 4h trend, market next open
        L = spike&(df.pos>=0.75)&(df.close>df.open)&df.up4; S = spike&(df.pos<=0.25)&(df.close<df.open)&df.dn4
        sdist = np.where(L, df.close-df.low, df.high-df.close)
    elif kind == "mom_retest":  # same, limit at 50% of spike bar
        L = spike&(df.pos>=0.75)&(df.close>df.open)&df.up4; S = spike&(df.pos<=0.25)&(df.close<df.open)&df.dn4
        mid = (df.high+df.low)/2; lim = np.where(L|S, mid, 0.0); wait = 6
        sdist = np.where(L, mid-df.low, df.high-mid)+0.1*df.atr
    sig = np.where(L,1,np.where(S,-1,0)); sig[:300] = 0
    ok = (sdist/df.close*100) >= minstop
    sig = np.where(ok, sig, 0)
    return run(df, sig, sdist, lim_px=lim if wait else None, wait=wait, tgt_r=tgt, max_hold=24, bar_sec=BAR[tf], tp_taker=True)
if __name__ == "__main__":
    tf = sys.argv[1]; kinds = sys.argv[2].split(",")
    D = {s: prep(s, tf) for s in SYMS}
    for kind in kinds:
        for K, V, tgt in itertools.product((2.0, 3.0, 4.0), (2.0, 3.0), (1.0, 1.5, 2.0)):
            ts = []
            for s in SYMS:
                t = variant(D[s], kind, K, V, tgt, tf); t["sym"] = s; ts.append(t)
            print(fmt(f"{tf} {kind} K{K} V{V} T{tgt}", pd.concat(ts).sort_values("time")), flush=True)
