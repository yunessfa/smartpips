"""Pure price-action setups (no moving averages). ATR is used only as a volatility unit for buffers/filters.
Swing pivots are confirmed k bars after the pivot (no look-ahead). Selection on TR (2021-2023) only."""
import sys, itertools, numpy as np, pandas as pd
from numba import njit
from common import *

@njit(cache=True)
def swings(h, l, k):
    """Per bar: last and previous CONFIRMED swing high/low (known at bar i)."""
    n = len(h); sh1 = np.full(n, np.nan); sh2 = np.full(n, np.nan); sl1 = np.full(n, np.nan); sl2 = np.full(n, np.nan)
    a1 = np.nan; a2 = np.nan; b1 = np.nan; b2 = np.nan
    for i in range(n):
        j = i - k
        if j >= k:
            hi = True; lo = True
            for m in range(j - k, j + k + 1):
                if h[m] > h[j]: hi = False
                if l[m] < l[j]: lo = False
            if hi: a2 = a1; a1 = h[j]
            if lo: b2 = b1; b1 = l[j]
        sh1[i] = a1; sh2[i] = a2; sl1[i] = b1; sl2[i] = b2
    return sh1, sh2, sl1, sl2

def structure(df, k):
    sh1, sh2, sl1, sl2 = swings(df.high.values, df.low.values, k)
    up = (sh1 > sh2) & (sl1 > sl2) & (df.close.values > sl1)
    dn = (sh1 < sh2) & (sl1 < sl2) & (df.close.values < sh1)
    return sh1, sl1, np.where(up, 1, np.where(dn, -1, 0))

def prep(sym, tf, k, khtf):
    df = load(sym, tf)
    h4 = load(sym, "4h"); _, _, st4 = structure(h4, khtf); h4["st"] = st4
    df = htf_merge(df, h4, ["st"], "h4_")
    sh, sl, st = structure(df, k)
    df["sh"], df["sl"], df["st"] = sh, sl, st
    return df

def setup(df, kind, tgt, tf, wait=12, minstop=0.4, maxstop=4.0):
    c, h, l, a = df.close.values, df.high.values, df.low.values, df.atr.values
    sh, sl, h4 = df.sh.values, df.sl.values, df.h4_st.values
    n = len(df); sig = np.zeros(n); lim = np.zeros(n); sd = np.full(n, np.nan)
    prev_sh = np.r_[np.nan, sh[:-1]]; prev_sl = np.r_[np.nan, sl[:-1]]; pc = np.r_[np.nan, c[:-1]]
    if kind in ("bos_retest", "bos_50"):
        L = (h4 == 1) & (c > sh) & (pc <= prev_sh) & (sh == prev_sh)      # first close above the last swing high
        S = (h4 == -1) & (c < sl) & (pc >= prev_sl) & (sl == prev_sl)
        if kind == "bos_retest":
            lp = np.where(L, sh, np.where(S, sl, 0.0))
        else:
            lp = np.where(L, (sl + h) / 2, np.where(S, (sh + l) / 2, 0.0))
        stop = np.where(L, sl - 0.1 * a, np.where(S, sh + 0.1 * a, np.nan))
        sig = np.where(L, 1, np.where(S, -1, 0)); lim = lp; sd = np.abs(lp - stop)
        w = wait
    elif kind == "sweep":                                                    # stop-hunt below swing low, close back above
        L = (h4 == 1) & (l < sl) & (c > sl); S = (h4 == -1) & (h > sh) & (c < sh)
        stop = np.where(L, l - 0.1 * a, np.where(S, h + 0.1 * a, np.nan))
        sig = np.where(L, 1, np.where(S, -1, 0)); sd = np.abs(c - stop); lim = None; w = 0
    elif kind == "breakout":                                                 # market entry on the break, structure stop
        L = (h4 == 1) & (c > sh) & (pc <= prev_sh) & (sh == prev_sh); S = (h4 == -1) & (c < sl) & (pc >= prev_sl) & (sl == prev_sl)
        stop = np.where(L, sl - 0.1 * a, np.where(S, sh + 0.1 * a, np.nan))
        sig = np.where(L, 1, np.where(S, -1, 0)); sd = np.abs(c - stop); lim = None; w = 0
    ref = lim if lim is not None else c
    pct = sd / np.where(ref > 0, ref, np.nan) * 100
    ok = (pct >= minstop) & (pct <= maxstop) & np.isfinite(sd)
    sig = np.where(ok, sig, 0); sig[:400] = 0
    return run(df, sig, np.nan_to_num(sd), lim_px=lim, wait=w, tgt_r=tgt, max_hold=72, bar_sec=BAR[tf], tp_taker=True)

if __name__ == "__main__":
    tf = sys.argv[1]
    for k, khtf in ((3, 3), (5, 3), (5, 5)):
        D = {s: prep(s, tf, k, khtf) for s in SYMS}
        for kind, tgt in itertools.product(("bos_retest", "bos_50", "sweep", "breakout"), (2.0, 3.0)):
            t = pd.concat([setup(D[s], kind, tgt, tf) for s in SYMS]).sort_values("time")
            print(fmt(f"{tf} k{k}/{khtf} {kind} T{tgt}", t), flush=True)
