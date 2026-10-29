import pandas as pd, numpy as np
hist = pd.read_csv("/home/claude/data/bs/data/historical/btcusd_bitstamp_1min_2012-2025.csv.gz")
hist = hist[hist.timestamp >= 1546300800]  # 2019-01-01
upd = pd.read_csv("/home/claude/research/btc1m.csv")
df = pd.concat([hist, upd]).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
df["timestamp"] = df.timestamp.astype("int64")
print("rows", len(df), pd.to_datetime(df.timestamp.iloc[0], unit="s"), pd.to_datetime(df.timestamp.iloc[-1], unit="s"))
gaps = np.diff(df.timestamp.values)
print("gaps>60s:", (gaps > 60).sum(), "max gap min:", gaps.max() / 60)
df.to_parquet("/home/claude/lab/btc_1m.parquet", index=False)
idx = pd.to_datetime(df.timestamp, unit="s")
d = df.set_index(idx)
for name, rule in (("5m", "5min"), ("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
    r = d.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    r["time"] = ((r.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
    r.reset_index(drop=True).to_parquet(f"/home/claude/lab/btc_{name}.parquet", index=False)
    print(name, len(r))
