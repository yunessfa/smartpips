import numpy as np, pandas as pd, common
from common import *
import pa2
def go(tf, trend, anchor, cost=1.0):
    orig = pa2.run
    pa2.run = lambda *a, **k: orig(*a, **{**k, "taker": .0006*cost, "maker": .0002*cost, "slip": .0002*cost})
    out = []
    for s in SYMS:
        t = pa2.build(s, tf, trend, anchor); t["sym"] = s; out.append(t)
    pa2.run = orig
    return pd.concat(out).sort_values("time").reset_index(drop=True)
for tf in ("1h", "15m"):
    for trend, anchor, name in (("ema","ema","current (EMA)"), ("range","ema","price trend + EMA21 entry"), ("range","price","no EMA at all")):
        t = go(tf, trend, anchor); t2 = go(tf, trend, anchor, 2.0)
        per = t.groupby("sym").R.mean(); eq = t.R.cumsum(); dd = (eq - eq.cummax()).min()
        yrs = (t.time.iloc[-1]-t.time.iloc[0])/31557600
        print(f"{tf:3} {name:26} trades/yr {len(t)/yrs:6.0f} | win {100*(t.R>0).mean():4.1f}% | R/trade {t.R.mean():+.3f} | R/yr {t.R.sum()/yrs:6.0f} | PF {t.R[t.R>0].sum()/-t.R[t.R<=0].sum():.2f} | coins+ {(per>0).sum()}/12 | maxDD {dd:6.1f}R | 2x fees R/trade {t2.R.mean():+.3f}", flush=True)
