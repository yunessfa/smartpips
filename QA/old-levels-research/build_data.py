"""Build BTC candles from github.com/ff137/bitstamp-btcusd-minute-data (clone it, pass its path as argv[1])."""
import sys, os
import pandas as pd, numpy as np
OUT = os.environ.get("SP_LAB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")); os.makedirs(OUT, exist_ok=True)
hist = pd.read_csv(sys.argv[1] + "/data/historical/btcusd_bitstamp_1min_2012-2025.csv.gz")
hist = hist[hist.timestamp >= 1514764800]  # 2018-01-01 (one extra year = warm-up for old levels)
upd = pd.read_csv(sys.argv[1] + "/data/updates/btcusd_bitstamp_1min_latest.csv")
df = pd.concat([hist, upd]).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
df["timestamp"] = df.timestamp.astype("int64")
print("rows", len(df), pd.to_datetime(df.timestamp.iloc[0], unit="s"), pd.to_datetime(df.timestamp.iloc[-1], unit="s"))
gaps = np.diff(df.timestamp.values)
print("gaps>60s:", (gaps > 60).sum(), "max gap min:", gaps.max() / 60)
idx = pd.to_datetime(df.timestamp, unit="s")
d = df.set_index(idx)
for name, rule in (("5m", "5min"), ("15m", "15min"), ("1h", "1h"), ("4h", "4h"), ("1d", "1D")):
    r = d.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    r["time"] = ((r.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
    r.reset_index(drop=True).to_parquet(os.path.join(OUT, f"btc_{name}.parquet"), index=False)
    print(name, len(r), pd.to_datetime(r.time.iloc[-1], unit="s"))
