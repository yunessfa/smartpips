"""Evidence blocks (same shape as trend_pullback.RESEARCH['results']) for the shipped specs."""
import json, numpy as np, pandas as pd
from common import *
from final_v2 import build
SPL2 = {"train": ("2021-01-01", "2024-01-01"), "validation": ("2024-01-01", "2025-01-01"), "holdout": ("2025-01-01", "2027-01-01")}
def block(tf, mode, be):
    t = pd.concat([build(s, tf, mode, h1f="none", be=be) for s in SYMS]).sort_values("time").reset_index(drop=True)
    yrs = (t.time.iloc[-1] - t.time.iloc[0]) / 31557600
    exp, pf = {}, {}
    for k, (a, b) in SPL2.items():
        s = t[(t.time >= pd.Timestamp(a).timestamp()) & (t.time < pd.Timestamp(b).timestamp())].R
        exp[k] = round(float(s.mean()), 3); pf[k] = round(float(s[s > 0].sum() / -s[s <= 0].sum()), 2)
    dt = pd.to_datetime(t.time, unit="s")
    by_year = t.groupby(dt.dt.year).R.sum() / 12          # per coin, so it reads like one market
    months = t.groupby(dt.dt.to_period("M")).R.sum()
    eq = t.R.cumsum(); se = t.R.std(ddof=1) / np.sqrt(len(t))
    return {"trades_per_year": round(len(t) / yrs / 12), "win_rate_pct": round(float((t.R > 0).mean() * 100), 1),
            "expectancy_r": exp, "profit_factor": pf, "r_by_year": {str(k): round(float(v), 1) for k, v in by_year.items()},
            "positive_years": f"{int((by_year > 0).sum())}/{len(by_year)}", "positive_months_pct": round(float((months > 0).mean() * 100)),
            "max_drawdown_r": round(float((eq - eq.cummax()).min()), 1),
            "expectancy_95ci": [round(float(t.R.mean() - 1.96 * se), 3), round(float(t.R.mean() + 1.96 * se), 3)],
            "per": "coin-year (12 coins); drawdown is for all 12 coins together"}
out = {"v2": {tf: block(tf, "v2", 1.0 if tf == "1h" else 0.0) for tf in ("1h", "15m", "5m")}, "price": {"1h": block("1h", "price", 0.0)}}
print(json.dumps(out))
