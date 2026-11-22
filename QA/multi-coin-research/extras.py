"""1) Spike fade with a sane stop. 2) Exit variants for win-rate vs expectancy. 3) External filters. Fixed grids; judged on TR, reported on VA/HO."""
import json, sys, urllib.request, itertools, numpy as np, pandas as pd
from common import *
from spike import prep
from tp_alts import CFG
# ---------- 1) fade with ATR stop
def fade(df, K, V, sl, tgt, tf):
    sp = (df.rng_atr>=K)&(df.vol_x>=V)
    L = sp&(df.close<df.open)&(df.pos<=0.3); Sx = sp&(df.close>df.open)&(df.pos>=0.7)
    sig = np.where(L,1,np.where(Sx,-1,0)); sig[:300]=0; sd = sl*df.atr
    sig = np.where((sd/df.close*100)>=0.4, sig, 0)
    return run(df, sig, sd, tgt_r=tgt, max_hold=24, bar_sec=BAR[tf], tp_taker=True)
if len(sys.argv)>1 and sys.argv[1] == "fade":
    for tf in ("15m","1h"):
        D = {s: prep(s,tf) for s in SYMS}
        for K,V,sl,tgt in itertools.product((3.0,4.0),(2.0,3.0),(1.5,2.5),(1.0,1.5)):
            print(fmt(f"{tf} fadeATR K{K} V{V} SL{sl} T{tgt}", pd.concat([fade(D[s],K,V,sl,tgt,tf) for s in SYMS]).sort_values("time")), flush=True)
# ---------- shared trend-pullback signals
def tp_sig(sym, tf):
    df = load(sym, tf); df = htf_merge(df, load(sym,"4h"), ["e50","e200","close"], "h4_")
    if tf!="1h": df = htf_merge(df, load(sym,"1h"), ["e21","e50","e200","close"], "h1_")
    U=(df.h4_close>df.h4_e200)&(df.h4_e50>df.h4_e200); D=(df.h4_close<df.h4_e200)&(df.h4_e50<df.h4_e200)
    if CFG[tf]["h1"]: U&=(df.h1_e21>df.h1_e50)&(df.h1_close>df.h1_e200); D&=(df.h1_e21<df.h1_e50)&(df.h1_close<df.h1_e200)
    st=(df.close-df.e21)/df.atr; ok=(1.5*df.atr/df.close*100)>=0.4
    L=U&(df.e21>df.e50)&(df.e50>df.e200)&(st>1)&ok; Sx=D&(df.e21<df.e50)&(df.e50<df.e200)&(st<-1)&ok
    sig=np.where(L,1,np.where(Sx,-1,0)); sig[:400]=0
    return df, sig
if len(sys.argv)>1 and sys.argv[1] == "exits":
    for tf in ("15m","1h"):
        P={s: tp_sig(s,tf) for s in SYMS}
        for name,kw in [("base",dict(tgt_r=CFG[tf]["tp"])),("T1.0",dict(tgt_r=1.0)),("T1.5",dict(tgt_r=1.5)),("T2.0",dict(tgt_r=2.0)),
                        ("BE@1R",dict(tgt_r=CFG[tf]["tp"],be_r=1.0)),("BE@1.5R",dict(tgt_r=CFG[tf]["tp"],be_r=1.5))]:
            ts=[run(d,g,1.5*d.atr,lim_px=d.e21.values,wait=12,max_hold=72,bar_sec=BAR[tf],tp_taker=True,**kw) for d,g in P.values()]
            print(fmt(f"{tf} exit {name}", pd.concat(ts).sort_values("time")), flush=True)
if len(sys.argv)>1 and sys.argv[1] == "filters":
    fg = json.load(urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json", timeout=30))["data"]
    fg = pd.DataFrame({"d":[int(x["timestamp"]) for x in fg],"fg":[int(x["value"]) for x in fg]}).sort_values("d")
    fg["avail"] = fg.d + 86400   # only known after that day closes
    dv=[]; t=int(pd.Timestamp("2021-03-24").timestamp()*1000); end=int(pd.Timestamp("2026-11-01").timestamp()*1000)
    while t<end:
        u=f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp={t}&end_timestamp={min(end,t+900*86400000)}&resolution=86400"
        r=json.load(urllib.request.urlopen(u,timeout=30))["result"]["data"]
        if r: dv+= [(x[0]//1000, x[4]) for x in r]
        t+=900*86400000
    dv=pd.DataFrame(dv,columns=["d","dvol"]).drop_duplicates("d").sort_values("d"); dv["avail"]=dv.d+86400
    dv["dvol_pct"]=dv.dvol.rolling(180,min_periods=60).rank(pct=True)
    print("fng",len(fg),"dvol",len(dv),flush=True)
    for tf in ("15m","1h"):
        rows=[]
        for s in SYMS:
            d,g=tp_sig(s,tf); t=run(d,g,1.5*d.atr,lim_px=d.e21.values,wait=12,tgt_r=CFG[tf]["tp"],max_hold=72,bar_sec=BAR[tf],tp_taker=True); rows.append(t)
        t=pd.concat(rows).sort_values("time").reset_index(drop=True)
        t=pd.merge_asof(t,fg[["avail","fg"]],left_on="time",right_on="avail",direction="backward").drop(columns="avail")
        t=pd.merge_asof(t,dv[["avail","dvol_pct"]],left_on="time",right_on="avail",direction="backward").drop(columns="avail")
        print(fmt(f"{tf} no filter",t))
        for name,m in [("FG<25 (fear)",t.fg<25),("FG 25-75",t.fg.between(25,75)),("FG>75 (greed)",t.fg>75),
                       ("long&FG<50",(t.dir>0)&(t.fg<50)),("long&FG>=50",(t.dir>0)&(t.fg>=50)),("short&FG<50",(t.dir<0)&(t.fg<50)),("short&FG>=50",(t.dir<0)&(t.fg>=50)),
                       ("DVOL low third",t.dvol_pct<1/3),("DVOL mid third",t.dvol_pct.between(1/3,2/3)),("DVOL high third",t.dvol_pct>2/3)]:
            print(fmt(f"{tf} {name}",t[m].reset_index(drop=True)),flush=True)
