import sys, itertools, json
import numpy as np, pandas as pd
from feat import load, htf_merge
from sim import run, stats
TF = sys.argv[1]
BAR = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}[TF]
df = load(TF)
h4 = load("4h") if TF != "4h" else df
df = htf_merge(df, h4, ["e50", "e200", "close"], "h4_")
SPL = [("TR", "2019-01-01", "2023-01-01"), ("VA", "2023-01-01", "2025-01-01"), ("HO", "2025-01-01", "2027-01-01")]

def report(name, t):
    row = {"name": name}
    for lab, a, b in SPL:
        ta, tb = pd.Timestamp(a).timestamp(), pd.Timestamp(b).timestamp()
        s = stats(t[(t.time >= ta) & (t.time < tb)])
        row[lab] = (s.get("n"), s.get("win"), s.get("expR"), s.get("totR"), s.get("PF"), s.get("maxDD_R"))
    ys = stats(t)
    row["years"] = ys.get("by_year"); row["yp"] = ys.get("years_pos")
    print(json.dumps(row), flush=True)

mode = sys.argv[2]
up4 = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200)
dn4 = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)

if mode == "random":
    rng = np.random.default_rng(1)
    sig = rng.choice([-1, 0, 1], size=len(df), p=[0.01, 0.98, 0.01])
    for k, r in ((1.5, 1.5), (2, 2)):
        report(f"RANDOM sl={k}atr tp={r}R", run(df, sig, k * df.atr, tgt_r=r, bar_sec=BAR))

if mode == "donch":
    for n, filt, sl, ex in itertools.product((20, 55), ("none", "h4"), (2.0, 3.0), ("trail3", "trail4", "don_half", "tp2", "tp3")):
        hh = df.high.rolling(n).max().shift(1); ll = df.low.rolling(n).min().shift(1)
        L = df.close > hh; S = df.close < ll
        if filt == "h4":
            L &= up4; S &= dn4
        sig = np.where(L, 1, np.where(S, -1, 0))
        kw = dict(bar_sec=BAR)
        if ex.startswith("trail"):
            kw["trail_k"] = float(ex[5:])
        elif ex.startswith("tp"):
            kw["tgt_r"] = float(ex[2:])
        else:
            m = n // 2
            kw["exit_long"] = (df.close < df.low.rolling(m).min().shift(1)).values
            kw["exit_short"] = (df.close > df.high.rolling(m).max().shift(1)).values
        report(f"DONCH n={n} f={filt} sl={sl} ex={ex}", run(df, sig, sl * df.atr, **kw))

if mode == "pull":
    # trend pullback: 4h trend + local trend, limit at EMA21 after price stretched
    loc_up = (df.e21 > df.e50) & (df.e50 > df.e200); loc_dn = (df.e21 < df.e50) & (df.e50 < df.e200)
    for trig, sl, ex, wait in itertools.product((1.0, 2.0), (1.5, 2.5), ("tp1.5", "tp2", "tp3", "trail3"), (6, 12)):
        stretch = (df.close - df.e21) / df.atr
        L = up4 & loc_up & (stretch > trig); S = dn4 & loc_dn & (stretch < -trig)
        sig = np.where(L, 1, np.where(S, -1, 0))
        kw = dict(bar_sec=BAR, lim_px=df.e21.values, wait=wait)
        if ex.startswith("tp"):
            kw["tgt_r"] = float(ex[2:])
        else:
            kw["trail_k"] = float(ex[5:])
        report(f"PULL trig={trig} sl={sl} ex={ex} wait={wait}", run(df, sig, sl * df.atr, **kw))

if mode == "mr":
    # Connors-style RSI2 mean reversion with 200 EMA / h4 trend filter; exit close>e9
    for lo, filt, sl in itertools.product((5, 10, 20), ("e200", "h4"), (2.0, 3.0)):
        base_up = df.close > df.e200 if filt == "e200" else up4
        base_dn = df.close < df.e200 if filt == "e200" else dn4
        L = base_up & (df.rsi2 < lo); S = base_dn & (df.rsi2 > 100 - lo)
        sig = np.where(L, 1, np.where(S, -1, 0))
        report(f"MR rsi2<{lo} f={filt} sl={sl}", run(df, sig, sl * df.atr, bar_sec=BAR, max_hold=48,
               exit_long=(df.close > df.e9).values, exit_short=(df.close < df.e9).values))
