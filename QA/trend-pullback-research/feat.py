import numpy as np, pandas as pd

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def load(tf):
    df = pd.read_parquet(f"/home/claude/lab/btc_{tf}.parquet")
    df["atr"] = atr(df)
    for n in (9, 21, 50, 100, 200):
        df[f"e{n}"] = ema(df.close, n)
    df["rsi"] = rsi(df.close)
    df["rsi2"] = rsi(df.close, 2)
    df["dt"] = pd.to_datetime(df.time, unit="s")
    return df

def htf_merge(df, htf, cols, prefix):
    """attach HTF columns using only CLOSED htf bars (no look-ahead)."""
    step = int(htf.time.iloc[1] - htf.time.iloc[0])
    h = htf[["time"] + cols].copy()
    h["avail"] = h.time + step          # value known once the htf bar has closed
    step_l = int(df.time.iloc[1] - df.time.iloc[0])
    left = pd.DataFrame({"t_close": df.time + step_l})
    m = pd.merge_asof(left, h.drop(columns="time").sort_values("avail"), left_on="t_close", right_on="avail", direction="backward")
    for col in cols:
        df[f"{prefix}{col}"] = m[col].values
    return df
