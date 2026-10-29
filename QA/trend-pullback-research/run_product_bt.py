import os, sys, json, time
sys.path.insert(0, "/home/claude/r5/backend")
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_SECRET_KEY="x", DJANGO_DEBUG="True")
os.environ.pop("POSTGRES_DB", None)
import django; django.setup()
import pandas as pd
from apps.strategy.backtest import backtest
tf = sys.argv[1]
def rows(name):
    d = pd.read_parquet(f"/home/claude/lab/btc_{name}.parquet")
    return [dict(time=int(r.time), open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume) for r in d.itertuples()]
c = rows(tf); htf = {"4h": rows("4h"), "1h": rows("1h")}
t0 = time.time()
r = backtest("BTCUSDT", c, timeframe=tf, mode="trend", htf_series=htf)
el = time.time() - t0
tl = pd.DataFrame(r["trade_list"])
tl["year"] = pd.to_datetime(tl.entry_time, unit="s").dt.year
by = tl.groupby("year").r.agg(["count", "mean", "sum"]).round(3)
def per(a, b):
    x = tl[(tl.year >= a) & (tl.year <= b)]
    return dict(n=len(x), e=round(x.r.mean(), 3))
print(json.dumps({"tf": tf, "secs": round(el, 1), "trades": r["trades"], "exp": r["expectancy_r"], "pf": r["profit_factor"],
                  "TR": per(2019, 2022), "VA": per(2023, 2024), "HO": per(2025, 2026), "verdict": r["evidence"]["verdict"],
                  "ci": r["evidence"]["expectancy_95ci"], "exits": r["exit_reasons"], "fills_missed": r["diagnostics"].get("limit_not_filled")}))
print(by.to_string())
