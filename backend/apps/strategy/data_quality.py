"""Strict live OHLCV boundary; no interpolation, hidden deduplication or fake ticks."""
import math


def inspect_bars(rows, step, now, continuous=True):
    bars=[]
    try:
        for row in rows:
            c={k:float(row[k]) for k in ("time","open","high","low","close")}
            c["volume"]=float(row.get("volume") or 0)
            if c["time"]>1e11:c["time"]/=1000
            if not all(math.isfinite(x) for x in c.values()):raise ValueError("nonfinite")
            if min(c[k] for k in ("time","open","high","low","close"))<=0 or c["volume"]<0:raise ValueError("range")
            if c["low"]>min(c["open"],c["close"]) or c["high"]<max(c["open"],c["close"]):raise ValueError("ohlc")
            if c["time"]+step>now:continue
            if bars and c["time"]<=bars[-1]["time"]:raise ValueError("nonmonotonic_or_duplicate")
            bars.append(c)
        if not bars:return [],{"valid":False,"reason":"NO_COMPLETED_BARS"}
        gaps=sum(b["time"]-a["time"]!=step for a,b in zip(bars,bars[1:]))
        if continuous and gaps:return [],{"valid":False,"reason":"CANDLE_GAPS","gap_count":gaps}
        return bars,{"valid":True,"completed_bars":len(bars),"gap_count":gaps,"volume_missing_or_zero":sum(c["volume"]==0 for c in bars)}
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        return [],{"valid":False,"reason":"INVALID_OHLCV","detail":str(exc)[:80]}
