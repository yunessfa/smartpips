"""Shared loaders. Data dir: $SP_LAB (default ./data). sim.py is reused from ../trend-pullback-research."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trend-pullback-research"))
from sim import run, stats  # noqa: E402,F401

DATA = os.environ.get("SP_LAB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")).rstrip("/") + "/"
CFG = {"5m": dict(tp=2.5, h1=True), "15m": dict(tp=2.5, h1=True), "1h": dict(tp=3.0, h1=False)}


def ema(s, n): return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def load(tf):
    df = pd.read_parquet(f"{DATA}btc_{tf}.parquet")
    df["atr"] = atr(df)
    for n in (21, 50, 200):
        df[f"e{n}"] = ema(df.close, n)
    return df


def htf_merge(df, htf, cols, prefix):
    """attach HTF columns using only CLOSED htf bars (no look-ahead)."""
    step = int(htf.time.iloc[1] - htf.time.iloc[0])
    h = htf[["time"] + cols].copy()
    h["avail"] = h.time + step
    step_l = int(df.time.iloc[1] - df.time.iloc[0])
    left = pd.DataFrame({"t_close": df.time + step_l})
    m = pd.merge_asof(left, h.drop(columns="time").sort_values("avail"), left_on="t_close", right_on="avail", direction="backward")
    for col in cols:
        df[f"{prefix}{col}"] = m[col].values
    return df


def signals(tf, trig=1.0, sl=1.5, minstop=0.4):
    """The validated trend-pullback rule set (same as ../trend-pullback-research/final.py)."""
    df = load(tf)
    df = htf_merge(df, load("4h"), ["e50", "e200", "close"], "h4_")
    if tf != "1h":
        df = htf_merge(df, load("1h"), ["e21", "e50", "e200", "close"], "h1_")
    U = (df.h4_close > df.h4_e200) & (df.h4_e50 > df.h4_e200)
    D = (df.h4_close < df.h4_e200) & (df.h4_e50 < df.h4_e200)
    if CFG[tf]["h1"]:
        U &= (df.h1_e21 > df.h1_e50) & (df.h1_close > df.h1_e200)
        D &= (df.h1_e21 < df.h1_e50) & (df.h1_close < df.h1_e200)
    st = (df.close - df.e21) / df.atr
    ok = (sl * df.atr / df.close * 100) >= minstop
    L = U & (df.e21 > df.e50) & (df.e50 > df.e200) & (st > trig) & ok
    S = D & (df.e21 < df.e50) & (df.e50 < df.e200) & (st < -trig) & ok
    return df, np.where(L, 1, np.where(S, -1, 0)), sl * df.atr
