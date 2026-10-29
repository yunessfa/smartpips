"""Run the PRODUCT engine (apps.strategy.engine.run_strategy) on sampled bars of
multi-year BTC data and store every indicator reading + forward returns."""
import os, sys, json, time
from datetime import datetime, timezone
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/r7/backend")
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_SECRET_KEY="x", DJANGO_DEBUG="True")
os.environ.pop("POSTGRES_DB", None)
import django; django.setup()
import pandas as pd, numpy as np

TF = sys.argv[1]; STRIDE = int(sys.argv[2])
STEP = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
HTF = {"5m": ["15m", "1h"], "15m": ["1h", "4h"], "1h": ["4h"]}[TF]

def rows(name):
    d = pd.read_parquet(f"/home/claude/lab/btc_{name}.parquet")
    return d

D = rows(TF); H = {k: rows(k) for k in HTF}
REC = D[["time", "open", "high", "low", "close", "volume"]].to_dict("records")
HREC = {k: v[["time", "open", "high", "low", "close", "volume"]].to_dict("records") for k, v in H.items()}
HT = {k: v.time.values for k, v in H.items()}

def one(i):
    from apps.strategy.engine import run_strategy
    win = REC[i - 299:i + 1]
    tclose = REC[i]["time"] + STEP[TF]
    htf = {}
    for k in HTF:
        j = np.searchsorted(HT[k], tclose - STEP[k], side="right")
        htf[k] = HREC[k][max(0, j - 200):j]
    try:
        d = run_strategy("BTCUSDT:PERP", TF, win, htf, live_price=win[-1]["close"], mode="safe",
                         as_of=datetime.fromtimestamp(tclose, timezone.utc))
    except Exception as e:
        return {"i": i, "err": str(e)[:80]}
    ind = d.get("indicators") or {}
    rf = d.get("rule_features") or {}
    out = {"i": i, "time": REC[i]["time"], "signal": d.get("signal"), "score": d.get("score"),
           "conviction": d.get("conviction"), "htf_bias": d.get("htf_bias"),
           "regime": (d.get("market_regime") or {}).get("regime"), "session": (d.get("session") or {}).get("name"),
           "wait": [w.get("code") for w in (d.get("wait_reasons") or [])],
           "atr": d.get("atr"), "rsi": rf.get("rsi"), "macd_hist": rf.get("macd_hist"),
           "vwap_dist": (rf["price"] - rf["vwap"]) / rf["price"] if rf.get("vwap") else None,
           "ema_fast": rf.get("ema_fast"), "ema_slow": rf.get("ema_slow"),
           "ema200": ind.get("EMA200"), "vol_ratio": rf.get("volume_ratio"),
           "stoch_k": (ind.get("Stoch") or {}).get("k"), "stoch_d": (ind.get("Stoch") or {}).get("d"),
           "buy_pressure": (ind.get("OrderFlow") or {}).get("buy_pressure"),
           "pd_pct": (ind.get("PremiumDiscount") or {}).get("pct"),
           "mss": ind.get("MSS"), "sweep": ind.get("LiquiditySweep"), "ob": ind.get("OrderBlock"),
           "smc_bos": (ind.get("SMC") or {}).get("BOS"), "smc_choch": (ind.get("SMC") or {}).get("CHOCH"),
           "smc_fvg": (ind.get("SMC") or {}).get("FVG"), "level_sweep": ind.get("LevelSweep"),
           "poc_dist": rf.get("distance_to_poc_pct"), "va": rf.get("price_vs_value_area"),
           "entry": d.get("entry"), "sl": d.get("stop_loss"), "tp": d.get("take_profit"),
           "entry_type": (d.get("entry_plan") or {}).get("type")}
    for k, v in (d.get("score_breakdown") or {}).items():
        out["bd_" + k] = v
    return out

if __name__ == "__main__":
    idx = list(range(400, len(REC) - 50, STRIDE))
    t0 = time.time()
    with Pool(2) as p:
        res = p.map(one, idx, chunksize=200)
    df = pd.DataFrame(res)
    df.to_pickle(f"/home/claude/lab/ind/engine_{TF}.pkl")
    print(TF, len(df), "errors", df.get("err", pd.Series(dtype=object)).notna().sum(), "secs", round(time.time() - t0))
