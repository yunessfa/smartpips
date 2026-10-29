"""Final playbook validation: one rule set, three timeframes."""
import sys, json
import numpy as np, pandas as pd
from feat import load, htf_merge
from sim import run, stats

CFG = {"5m": dict(tp=2.5, h1=True), "15m": dict(tp=2.5, h1=True), "1h": dict(tp=3.0, h1=False)}
SPL = [("TR", "2019-01-01", "2023-01-01"), ("VA", "2023-01-01", "2025-01-01"), ("HO", "2025-01-01", "2027-01-01")]

def signals(tf, trig=1.0, sl=1.5, minstop=0.4, h1=None):
    df = load(tf)
    df = htf_merge(df, load("4h"), ["e50", "e200", "close"], "h4_")
    use_h1 = CFG[tf]["h1"] if h1 is None else h1
    if tf != "1h":
        df = htf_merge(df, load("1h"), ["e21", "e50", "e200", "close"], "h1_")
    U = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200)
    D = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
    if use_h1:
        U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200)
        D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
    st = (df.close - df.e21) / df.atr
    ok = (sl * df.atr / df.close * 100) >= minstop
    L = U & (df.e21 > df.e50) & (df.e50 > df.e200) & (st > trig) & ok
    S = D & (df.e21 < df.e50) & (df.e50 < df.e200) & (st < -trig) & ok
    return df, np.where(L, 1, np.where(S, -1, 0)), sl * df.atr

def go(tf, cost=1.0, pen=0.0, tp_taker=False, **kw):
    df, sig, sd = signals(tf, **kw)
    bar = {"5m": 300, "15m": 900, "1h": 3600}[tf]
    return run(df, sig, sd, lim_px=df.e21.values, wait=12, tgt_r=CFG[tf]["tp"], max_hold=72, bar_sec=bar,
               taker=0.0006 * cost, maker=0.0002 * cost, slip=0.0002 * cost, pen=pen, tp_taker=tp_taker)

def row(name, t):
    r = {"name": name}
    for lab, a, b in SPL:
        ta, tb = pd.Timestamp(a).timestamp(), pd.Timestamp(b).timestamp()
        s = stats(t[(t.time >= ta) & (t.time < tb)]); r[lab] = (s.get("n"), s.get("win"), s.get("expR"), s.get("PF"), s.get("maxDD_R"))
    s = stats(t); r["all"] = {k: s[k] for k in ("n", "win", "expR", "totR", "PF", "maxDD_R", "years_pos", "tpy")}; r["by_year"] = s["by_year"]
    m = t.groupby(pd.to_datetime(t.time, unit="s").dt.to_period("M")).R.sum()
    r["months_pos_pct"] = round((m > 0).mean() * 100, 1)
    rng = np.random.default_rng(7); R = t.R.values
    dds = []
    for _ in range(2000):
        eq = np.cumsum(rng.choice(R, size=len(R), replace=True)); dds.append((eq - np.maximum.accumulate(eq)).min())
    r["mc_dd_R_p50_p95"] = (round(float(np.percentile(dds, 50)), 1), round(float(np.percentile(dds, 5)), 1))
    se = R.std(ddof=1) / np.sqrt(len(R)); r["expR_95ci"] = (round(R.mean() - 1.96 * se, 3), round(R.mean() + 1.96 * se, 3))
    r["avg_stop_pct"] = None
    print(json.dumps(r), flush=True)
    return r

if __name__ == "__main__":
    tf = sys.argv[1]
    base = go(tf); row(f"{tf} FINAL", base)
    base.to_csv(f"/home/claude/lab/final_trades_{tf}.csv", index=False)
    row(f"{tf} cost x2", go(tf, cost=2.0))
    row(f"{tf} limit must trade through 0.02%", go(tf, pen=0.0002))
    row(f"{tf} through 0.05% + cost x1.5", go(tf, pen=0.0005, cost=1.5))
    for trig in (0.75, 1.25):
        row(f"{tf} trig={trig}", go(tf, trig=trig))
    for sl in (1.25, 1.75):
        row(f"{tf} sl={sl}", go(tf, sl=sl))
    for ms in (0.3, 0.5):
        row(f"{tf} minstop={ms}", go(tf, minstop=ms))
    if tf != "1h":
        row(f"{tf} without 1h filter", go(tf, h1=False))
    row(f"{tf} WITHOUT min-stop filter", go(tf, minstop=0.0))
