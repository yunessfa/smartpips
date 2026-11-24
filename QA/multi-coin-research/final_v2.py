"""Exact specs to ship. Choices (1h filter on 5m/15m, breakeven on price mode) judged on TR only."""
import numpy as np, pandas as pd
from common import *
def rng_mid(df, n): return (df.high.rolling(n).max() + df.low.rolling(n).min()) / 2
def build(sym, tf, mode, h1f="none", be=0.0, cost=1.0):
    df = load(sym, tf)
    h4 = load(sym, "4h"); h4["mid50"] = rng_mid(h4, 50)
    df = htf_merge(df, h4, ["close", "mid50"], "h4_")
    U = df.h4_close > df.h4_mid50; D = df.h4_close < df.h4_mid50
    if tf != "1h" and h1f != "none":
        h1 = load(sym, "1h"); h1["mid50"] = rng_mid(h1, 50)
        df = htf_merge(df, h1, ["close", "mid50", "e21", "e50", "e200"], "h1_")
        if h1f == "range":
            U &= df.h1_close > df.h1_mid50; D &= df.h1_close < df.h1_mid50
        else:
            U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200); D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
    if mode == "v2":
        lu = (df.e21 > df.e50) & (df.e50 > df.e200); ld = (df.e21 < df.e50) & (df.e50 < df.e200); lvl = df.e21
    else:
        m20, m100 = rng_mid(df, 20), rng_mid(df, 100); lu = m20 > m100; ld = m20 < m100; lvl = m20
    st = (df.close - lvl) / df.atr; ok = (1.5 * df.atr / df.close * 100) >= 0.4
    sig = np.where(U & lu & (st > 1) & ok, 1, np.where(D & ld & (st < -1) & ok, -1, 0)); sig[:400] = 0
    t = run(df, sig, 1.5 * df.atr, lim_px=lvl.values, wait=12, tgt_r=3.0 if tf == "1h" else 2.5, be_r=be, max_hold=72,
            bar_sec=BAR[tf], tp_taker=True, taker=.0006*cost, maker=.0002*cost, slip=.0002*cost)
    t["sym"] = sym; return t
def show(name, tf, **kw):
    t = pd.concat([build(s, tf, **kw) for s in SYMS]).sort_values("time").reset_index(drop=True)
    t2 = pd.concat([build(s, tf, **{**kw, "cost": 2.0}) for s in SYMS])
    per = t.groupby("sym").R.mean(); yrs = (t.time.iloc[-1] - t.time.iloc[0]) / 31557600
    print(fmt(name, t), f"| coins+ {(per>0).sum()}/12 | R/yr {t.R.sum()/yrs:.0f} | 2x fees {t2.R.mean():+.3f}", flush=True)
if __name__ == "__main__":
    show("1h  v2 (no BE)", "1h", mode="v2")
    show("1h  v2 BE@1R  <- ship", "1h", mode="v2", be=1.0)
    show("1h  price (no BE)", "1h", mode="price")
    show("1h  price BE@1R", "1h", mode="price", be=1.0)
    for tf in ("15m", "5m"):
        for h1f in ("none", "range", "ema"):
            show(f"{tf} v2 1h-filter={h1f}", tf, mode="v2", h1f=h1f)
