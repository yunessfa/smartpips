"""Product trend-pullback rules, unchanged, on every symbol."""
import sys, numpy as np, pandas as pd
from common import *
CFG = {"5m": dict(tp=2.5, h1=True), "15m": dict(tp=2.5, h1=True), "1h": dict(tp=3.0, h1=False)}
def tp_trades(sym, tf):
    df = load(sym, tf); df = htf_merge(df, load(sym, "4h"), ["e50","e200","close"], "h4_")
    if tf != "1h": df = htf_merge(df, load(sym, "1h"), ["e21","e50","e200","close"], "h1_")
    U = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200); D = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
    if CFG[tf]["h1"]:
        U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200); D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
    st = (df.close-df.e21)/df.atr; ok = (1.5*df.atr/df.close*100) >= 0.4
    L = U & (df.e21>df.e50)&(df.e50>df.e200)&(st>1)&ok; Sx = D&(df.e21<df.e50)&(df.e50<df.e200)&(st<-1)&ok
    sig = np.where(L,1,np.where(Sx,-1,0)); sig[:400] = 0
    return run(df, sig, 1.5*df.atr, lim_px=df.e21.values, wait=12, tgt_r=CFG[tf]["tp"], max_hold=72, bar_sec=BAR[tf], tp_taker=True)
if __name__ == "__main__":
    for tf in sys.argv[1:]:
        allt = []
        for s in SYMS:
            t = tp_trades(s, tf); t["sym"] = s; allt.append(t); print(fmt(f"TP {tf} {s}", t), flush=True)
        print(fmt(f"TP {tf} ALL-SYMBOLS", pd.concat(allt).sort_values("time")), flush=True)
