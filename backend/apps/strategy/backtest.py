"""
Lightweight walk-forward backtester for the SmartPips strategy engine.

It replays the candles bar by bar (no look-ahead): at each bar it runs the same
indicator/scoring logic on data up to that bar, and if the engine would enter,
simulates the trade against the FOLLOWING bars until TP or SL is hit. Reports the
metrics the review asked for: win rate, profit factor, max drawdown, expectancy.

This is what turns "the AI guessed" into "this rule-set did X over the last N bars".
"""
from statistics import mean

from . import engine


def _decide_at(symbol, candles_so_far, min_score=None, min_rr=None, quiet=None):
    """Decide at this point using the REAL engine (run_strategy), so the backtest
    reflects exactly what happens live — same stops, same trend filters, same gates.

    A higher-timeframe map is built by resampling the trading-TF candles (5m -> 15m,
    1h) so the trend-alignment filter works in the backtest too.
    """
    if len(candles_so_far) < 60:
        return None

    htf_map = {"15m": _resample(candles_so_far, 3),
               "1h": _resample(candles_so_far, 12)}
    price = candles_so_far[-1]["close"]
    decision = engine.run_strategy(symbol, "5m", candles_so_far, htf_map, live_price=price)
    if decision.get("signal") not in ("buy", "sell"):
        return None
    if decision.get("entry") is None or decision.get("stop_loss") is None:
        return None
    return {
        "direction": "buy" if decision["signal"] == "buy" else "sell",
        "entry": decision["entry"],
        "stop": decision["stop_loss"],
        "target": decision["take_profit"],
    }


def _resample(candles, factor):
    """Group `factor` candles into one higher-timeframe candle (OHLCV)."""
    out = []
    for k in range(0, len(candles) - factor + 1, factor):
        chunk = candles[k:k + factor]
        if not chunk:
            continue
        out.append({
            "time": chunk[0].get("time"),
            "open": chunk[0]["open"],
            "high": max(c["high"] for c in chunk),
            "low": min(c["low"] for c in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(c.get("volume", 1) for c in chunk),
        })
    return out


FEE_RATE = 0.0006  # taker fee per side; round-trip subtracted from each trade


def backtest(symbol, candles, warmup=60, max_hold=40, tick_mode=False):
    """Replay candles and simulate trades. Returns a metrics dict."""
    if len(candles) < warmup + 20:
        return {"trades": 0, "note": "not enough candles to backtest"}

    trades = []
    i = warmup
    while i < len(candles) - 1:
        # In tick mode the bars are tiny, so loosen the volatility/score gates a bit.
        if tick_mode:
            decision = _decide_at(symbol, candles[:i + 1], min_score=55, min_rr=1.6, quiet=8e-5)
        else:
            decision = _decide_at(symbol, candles[:i + 1])
        if not decision:
            i += 1
            continue
        entry = decision["entry"]
        stop = decision["stop"]
        target = decision["target"]
        direction = decision["direction"]
        risk = abs(entry - stop)

        # Walk forward until TP or SL hits (or max_hold bars).
        outcome = None
        for j in range(i + 1, min(i + 1 + max_hold, len(candles))):
            hi, lo = candles[j]["high"], candles[j]["low"]
            if direction == "buy":
                if lo <= stop:
                    outcome = -risk; break
                if hi >= target:
                    outcome = target - entry; break
            else:
                if hi >= stop:
                    outcome = -risk; break
                if lo <= target:
                    outcome = entry - target; break
        if outcome is None:
            # close at last seen price
            last_close = candles[min(i + max_hold, len(candles) - 1)]["close"]
            outcome = (last_close - entry) if direction == "buy" else (entry - last_close)
        # subtract round-trip taker fee (entry + exit), expressed in price units
        exit_px = entry + outcome if direction == "buy" else entry - outcome
        fee = (entry + exit_px) * FEE_RATE
        outcome -= fee
        trades.append({"r": outcome / risk if risk else 0, "pnl": outcome})
        i += 2  # step past the trade to avoid overlapping entries

    if not trades:
        return {"trades": 0, "note": "no qualifying setups in this window"}

    rs = [t["r"] for t in trades]
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    # Equity curve in R units -> max drawdown.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "profit_factor": (round(gross_win / gross_loss, 2) if gross_loss
                          else (999.0 if gross_win else None)),
        "avg_r": round(mean(rs), 2),
        "expectancy_r": round(mean(rs), 2),
        "max_drawdown_r": round(max_dd, 2),
        "total_r": round(sum(rs), 2),
        "wins": len(wins),
        "losses": len(losses),
    }
