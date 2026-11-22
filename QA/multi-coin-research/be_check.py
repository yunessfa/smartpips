import numpy as np, pandas as pd, sys
sys.argv=["x","none"]
from common import *
from extras import tp_sig
P={s: tp_sig(s,"1h") for s in SYMS}
def go(be, cost=1.0, pen=0.0):
    out=[]
    for s,(d,g) in P.items():
        t=run(d,g,1.5*d.atr,lim_px=d.e21.values,wait=12,tgt_r=3.0,be_r=be,max_hold=72,bar_sec=3600,tp_taker=True,taker=.0006*cost,maker=.0002*cost,slip=.0002*cost,pen=pen); t["sym"]=s; t["xt"]=d.time.values[t.xi.astype(int)]; out.append(t)
    return pd.concat(out).sort_values("time").reset_index(drop=True)
for name,kw in [("cost x1",{}),("cost x2",dict(cost=2.0)),("through .02%",dict(pen=.0002))]:
    for be in (0.0,1.0): print(fmt(f"1h BE={be} {name}",go(be,**kw)),flush=True)
for be in (0.0,1.0):
    t=go(be); per=t.groupby("sym").R.mean(); eq=t.sort_values("xt").R.cumsum(); dd=(eq-eq.cummax()).min()
    day=t.groupby(pd.to_datetime(t.xt,unit="s").dt.date).R.sum()
    streak=m=0
    for r in t.sort_values("xt").R:
        m=m+1 if r<=0 else 0; streak=max(streak,m)
    print(f"BE={be}: symbols positive {(per>0).sum()}/12 | portfolio maxDD {dd:.1f}R | worst day {day.min():.1f}R | longest losing streak {streak} | median win R {t.R[t.R>0].median():.2f} | share of wins <0.3R {(t.R[t.R>0]<0.3).mean()*100:.0f}%")
