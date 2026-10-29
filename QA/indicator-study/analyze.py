import json, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr
STEP = {"5m": 300, "15m": 900, "1h": 3600}
STRIDE = {"5m": 6, "15m": 2, "1h": 1}
H = {"5m": [3, 12, 48], "15m": [4, 12, 48], "1h": [3, 12, 48]}
SPLIT = pd.Timestamp("2023-01-01").timestamp()
COST_BPS = 10.0  # maker entry + taker exit + slippage ~0.10% round trip
CAT = {"mss": {"bullish": 1, "bearish": -1}, "sweep": {"sell_side_taken": 1, "buy_side_taken": -1},
       "ob": {"bullish": 1, "bearish": -1}, "smc_bos": {"bullish": 1, "bearish": -1},
       "smc_choch": {"bullish": 1, "bearish": -1}, "smc_fvg": {"bullish": 1, "bearish": -1},
       "level_sweep": {"AL sweep": 1, "PDL sweep": 1, "AH sweep": -1, "PDH sweep": -1},
       "va": {"above": 1, "below": -1, "inside": 0}, "signal": {"buy": 1, "sell": -1, "wait": 0}}
LABEL = {"bd_htf_trend": "HTF trend (15%)", "bd_ema": "EMA9 vs EMA50 (11%)", "bd_vwap": "Price vs VWAP (9%)",
         "bd_rsi": "RSI 50-line (7%)", "bd_macd": "MACD hist (7%)", "bd_stoch": "Stochastic K>D (3%)",
         "bd_smc": "SMC bias (10%)", "bd_orderflow": "Order flow est. (13%)", "bd_liquidity": "Liquidity sweep (8%)",
         "bd_orderblock": "Order block (7%)", "bd_premium_discount": "Premium/discount (4%)",
         "bd_key_levels": "Key levels (6%)", "score_dir": "Engine score direction (all combined)",
         "signal": "Engine final signal (buy/sell)", "mss": "MSS", "sweep": "Sweep (raw)", "ob": "Order block (raw)",
         "smc_bos": "BOS", "smc_choch": "CHOCH", "smc_fvg": "FVG (last 3 bars)", "level_sweep": "PDH/PDL/Asia sweep",
         "va": "Price vs value area", "trend200": "Price vs EMA200"}

def load(tf):
    d = pd.read_pickle(f"/home/claude/lab/ind/engine_{tf}.pkl")
    px = pd.read_parquet(f"/home/claude/lab/btc_{tf}.parquet")
    c = px.close.values
    for h in H[tf]:
        j = np.minimum(d.i.values + h, len(c) - 1)
        d[f"f{h}"] = (c[j] / c[d.i.values] - 1) * 1e4  # bps
    d["atr_bps"] = d.atr / px.close.values[d.i.values] * 1e4
    for k, m in CAT.items():
        d["s_" + k] = d[k].map(m).fillna(0)
    bd = [c for c in d.columns if c.startswith("bd_")]
    d["s_score_dir"] = np.sign(d[bd].sum(axis=1))
    for c in bd:
        d["s_" + c] = np.sign(d[c])
    d["s_trend200"] = np.sign(d.ema_fast - d.ema200).where(d.ema200.notna(), 0)
    d["tr"] = d.time < SPLIT
    return d

def signed(d, col, h, tf):
    out = {}
    for lab, m in (("TR", d.tr), ("HO", ~d.tr)):
        x = d[m]
        s = x[col]; act = s != 0
        r = (s[act] * x.loc[act, f"f{h}"])
        n = int(act.sum())
        if n < 30:
            out[lab] = None; continue
        eff = n * min(1.0, STRIDE[tf] / h)
        t = r.mean() / (r.std() / np.sqrt(eff)) if r.std() > 0 else 0
        out[lab] = {"n": n, "bps": round(float(r.mean()), 2), "hit": round(float((r > 0).mean() * 100), 1),
                    "t": round(float(t), 1), "active_pct": round(100 * n / len(x), 1)}
    return out

CONT = {"rsi": "RSI value", "macd_rel": "MACD hist / price", "vwap_dist": "Distance from VWAP",
        "ema_gap": "EMA9-EMA50 gap", "stoch_kd": "Stoch K-D", "flow": "Buy pressure (order-flow est.)",
        "pd_pct": "Premium/discount %", "poc_dist": "Distance from POC", "vol_ratio": "Volume ratio"}

def cont(d, h):
    d = d.copy()
    px_ = d.ema_fast
    d["macd_rel"] = d.macd_hist / d.ema_fast
    d["ema_gap"] = (d.ema_fast - d.ema_slow) / d.ema_slow
    d["stoch_kd"] = d.stoch_k - d.stoch_d
    d["flow"] = d.buy_pressure - 0.5
    out = {}
    for c in CONT:
        res = {}
        for lab, m in (("TR", d.tr), ("HO", ~d.tr)):
            x = d.loc[m, [c, f"f{h}"]].dropna()
            if len(x) < 100:
                res[lab] = None; continue
            ic = spearmanr(x[c], x[f"f{h}"]).statistic
            q = pd.qcut(x[c].rank(method="first"), 5, labels=False)
            spread = x[f"f{h}"][q == 4].mean() - x[f"f{h}"][q == 0].mean()
            res[lab] = {"ic": round(float(ic), 4), "q5_minus_q1_bps": round(float(spread), 2)}
        out[c] = res
    # volatility prediction: vol ratio vs |fwd|
    return out

if __name__ == "__main__":
    report = {}
    for tf in ("5m", "15m", "1h"):
        d = load(tf)
        rep = {"samples": len(d), "signal_dist": d.signal.value_counts(normalize=True).round(4).to_dict(),
               "regime_dist": d.regime.value_counts(normalize=True).round(3).to_dict(),
               "wait_reasons": d.wait.explode().value_counts(normalize=True).head(6).round(3).to_dict(),
               "median_atr_bps": round(float(d.atr_bps.median()), 1)}
        cols = ["s_" + k for k in LABEL]
        rep["signed"] = {}
        for c in cols:
            if c not in d: continue
            rep["signed"][LABEL[c[2:]]] = {f"h{h}": signed(d, c, h, tf) for h in H[tf]}
        rep["continuous"] = {CONT[k]: v for k, v in cont(d, H[tf][1]).items()}
        rep["continuous_h"] = H[tf][1]
        # conviction bins of score direction
        d["conv_bin"] = pd.cut(d.conviction, [-1, 20, 40, 60, 80, 101])
        cb = {}
        for b, x in d.groupby("conv_bin", observed=True):
            r = x.s_score_dir * x[f"f{H[tf][1]}"]
            cb[str(b)] = {"n": len(x), "bps": round(float(r.mean()), 2)}
        rep["conviction_bins"] = cb
        report[tf] = rep
        print("done", tf, file=sys.stderr)
    json.dump(report, open("/home/claude/lab/ind/report.json", "w"), indent=1, ensure_ascii=False)
