import sys, itertools, json
import numpy as np, pandas as pd
from feat import load, htf_merge
from sim import run, stats
TF = sys.argv[1]; mode = sys.argv[2]
BAR = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}[TF]
df = load(TF)
h4 = load("4h"); df = htf_merge(df, h4, ["e50", "e200", "close"], "h4_")
if TF in ("5m", "15m"):
    h1 = load("1h"); df = htf_merge(df, h1, ["e21", "e50", "e200", "close", "atr"], "h1_")
SPL = [("TR", "2019-01-01", "2023-01-01"), ("VA", "2023-01-01", "2025-01-01"), ("HO", "2025-01-01", "2027-01-01")]

def report(name, t, extra=None):
    row = {"name": name}
    for lab, a, b in SPL:
        ta, tb = pd.Timestamp(a).timestamp(), pd.Timestamp(b).timestamp()
        s = stats(t[(t.time >= ta) & (t.time < tb)])
        row[lab] = (s.get("n"), s.get("win"), s.get("expR"), s.get("totR"), s.get("PF"), s.get("maxDD_R"))
    ys = stats(t); row["years"] = ys.get("by_year"); row["yp"] = ys.get("years_pos")
    if len(t):
        sd = (t.entry - (t.entry - 0)).abs()
    if extra: row.update(extra)
    print(json.dumps(row), flush=True)

up4 = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200)
dn4 = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
loc_up = (df.e21 > df.e50) & (df.e50 > df.e200); loc_dn = (df.e21 < df.e50) & (df.e50 < df.e200)
stretch = (df.close - df.e21) / df.atr

def pull(trig, sl, trail, wait, side="both", tp=0.0, cost=1.0, filt="h4", be=0.0):
    U, D = up4.copy(), dn4.copy()
    if filt == "h4h1":
        U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200)
        D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
    L = U & loc_up & (stretch > trig); S = D & loc_dn & (stretch < -trig)
    if side == "long": S[:] = False
    if side == "short": L[:] = False
    sig = np.where(L, 1, np.where(S, -1, 0))
    return run(df, sig, sl * df.atr, lim_px=df.e21.values, wait=wait, trail_k=trail, tgt_r=tp, be_r=be, bar_sec=BAR,
               taker=0.0006 * cost, maker=0.0002 * cost, slip=0.0002 * cost)

if mode == "grid":
    for trig, sl, trail, wait in itertools.product((0.5, 1.0, 1.5), (1.0, 1.5, 2.0), (2.0, 2.5, 3.0, 4.0), (6, 12, 24)):
        report(f"PULL trig={trig} sl={sl} trail={trail} wait={wait}", pull(trig, sl, trail, wait))

if mode == "stress":
    base = dict(trig=1.0, sl=1.5, trail=3.0, wait=12)
    report("BASE", pull(**base))
    report("LONG only", pull(**base, side="long"))
    report("SHORT only", pull(**base, side="short"))
    report("COST x2", pull(**base, cost=2.0))
    report("COST x3", pull(**base, cost=3.0))
    report("h4+h1 filter", pull(**base, filt="h4h1")) if "h1_e21" in df else None
    report("BE at 1R", pull(**base, be=1.0))
    for tp in (2.0, 3.0, 4.0):
        report(f"trail+TP{tp}", pull(**base, tp=tp))

if mode == "scalp":
    for filt, trig, sl, trail, wait in itertools.product(("h4", "h4h1"), (0.5, 1.0, 1.5), (1.0, 1.5, 2.0), (2.0, 3.0, 4.0), (6, 12)):
        report(f"PULL {filt} trig={trig} sl={sl} trail={trail} wait={wait}", pull(trig, sl, trail, wait, filt=filt))

if mode == "costfilt":
    for minpct, trig, sl, trail in itertools.product((0.0, 0.4, 0.6, 0.8), (1.0, 1.5), (1.5,), (3.0, 4.0)):
        okv = (sl * df.atr / df.close * 100) >= minpct
        U = up4 & loc_up & (stretch > trig) & okv; D = dn4 & loc_dn & (stretch < -trig) & okv
        sig = np.where(U, 1, np.where(D, -1, 0))
        report(f"PULL minstop%={minpct} trig={trig} sl={sl} trail={trail}",
               run(df, sig, sl * df.atr, lim_px=df.e21.values, wait=12, trail_k=trail, bar_sec=BAR))

if mode == "tpgrid":
    mins = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    okv = (1.5 * df.atr / df.close * 100) >= mins
    for tp, mh in itertools.product((2.0, 2.5, 3.0, 4.0, 5.0, 0.0), (10**9, 72, 168)):
        if tp == 0.0 and mh != 10**9: continue
        U = up4 & loc_up & (stretch > 1.0) & okv; D = dn4 & loc_dn & (stretch < -1.0) & okv
        sig = np.where(U, 1, np.where(D, -1, 0))
        t = run(df, sig, 1.5 * df.atr, lim_px=df.e21.values, wait=12, tgt_r=tp, trail_k=3.0 if tp == 0 else 0.0,
                max_hold=mh, bar_sec=BAR)
        hold = (t.xi - t.fi) * BAR / 3600
        report(f"tp={tp or 'trail3'} maxhold={mh if mh < 10**9 else 'inf'}", t,
               {"hold_h_med": round(float(hold.median()), 1), "hold_h_p90": round(float(hold.quantile(.9)), 1),
                "stop_pct_med": round(float((1.5 * df.atr / df.close * 100).iloc[t.fi.astype(int) - 1].median()), 3)})

if mode == "five":
    for filt, mins, tp in itertools.product(("h4", "h4h1"), (0.25, 0.4), (2.0, 2.5, 3.0)):
        okv = (1.5 * df.atr / df.close * 100) >= mins
        U, D = up4.copy(), dn4.copy()
        if filt == "h4h1":
            U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200); D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
        L = U & loc_up & (stretch > 1.0) & okv; S = D & loc_dn & (stretch < -1.0) & okv
        sig = np.where(L, 1, np.where(S, -1, 0))
        report(f"5m {filt} minstop={mins} tp={tp}", run(df, sig, 1.5 * df.atr, lim_px=df.e21.values, wait=12, tgt_r=tp, max_hold=72, bar_sec=BAR))
