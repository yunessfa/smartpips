import numpy as np, pandas as pd, os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trend-pullback-research"))
from sim import run, stats
LAB = os.path.dirname(os.path.abspath(__file__))
SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","SUIUSDT","BNBUSDT","LTCUSDT","AAVEUSDT"]
SPL = [("TR","2021-01-01","2024-01-01"),("VA","2024-01-01","2025-01-01"),("HO","2025-01-01","2027-01-01")]
BAR = {"5m":300,"15m":900,"1h":3600,"4h":14400}
def ema(s,n): return s.ewm(span=n, adjust=False).mean()
def atr(df,n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high-df.low,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
_C = {}
def load(sym, tf):
    k = (sym, tf)
    if k in _C: return _C[k].copy()
    df = pd.read_pickle(f"{LAB}/{sym}_5m.pkl")
    if tf != "5m":
        step = BAR[tf]
        g = df.groupby(df.time // step * step)
        df = pd.DataFrame({"time": g.time.first() // step * step, "open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
                           "close": g.close.last(), "volume": g.volume.sum(), "tbv": g.tbv.sum(), "cnt": g.time.count()}).reset_index(drop=True)
        df = df[df.cnt == step // 300].drop(columns="cnt").reset_index(drop=True)
    df["atr"] = atr(df)
    for n in (21, 50, 200): df[f"e{n}"] = ema(df.close, n)
    df["vma"] = df.volume.rolling(50).mean()
    _C[k] = df
    return df.copy()
def htf_merge(df, htf, cols, prefix):
    step = int(htf.time.iloc[1]-htf.time.iloc[0]); h = htf[["time"]+cols].copy(); h["avail"] = h.time+step
    step_l = int(df.time.iloc[1]-df.time.iloc[0])
    m = pd.merge_asof(pd.DataFrame({"t": df.time+step_l}), h.drop(columns="time").sort_values("avail"), left_on="t", right_on="avail", direction="backward")
    for c in cols: df[prefix+c] = m[c].values
    return df
def split_stats(t):
    out = {}
    for lab,a,b in SPL:
        ta,tb = pd.Timestamp(a).timestamp(), pd.Timestamp(b).timestamp()
        s = stats(t[(t.time>=ta)&(t.time<tb)]); out[lab] = (s.get("n",0), s.get("win"), s.get("expR"))
    return out
def fmt(name, t):
    s = split_stats(t); a = stats(t)
    parts = " | ".join(f"{k} n={v[0]:4} w={v[1] if v[1] is not None else '-':>5} R={v[2] if v[2] is not None else '-':>7}" for k,v in s.items())
    return f"{name:34} {parts} | all n={a.get('n',0)} R={a.get('expR')} PF={a.get('PF')} yrs+={a.get('years_pos')}"
