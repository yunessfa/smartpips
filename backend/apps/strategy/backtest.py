"""Sequential simulation with explicit fees and slippage: market plans enter at the
next open, limit (pullback) plans only if price trades back to the level in time.
No historical news/order-book/funding data is invented. Partial exits and trailing
stops are NOT simulated; results describe a fixed-stop/single-target baseline.
"""
from statistics import mean
from datetime import datetime, timezone
from . import engine

TF_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
FEE_RATE = 0.0006
MAKER_FEE_RATE = 0.0002  # resting limit entries


def _resample(candles, factor, step_seconds=None):
    if not step_seconds or not all(isinstance(c.get("time"), (int, float)) for c in candles):
        chunks = [candles[k:k + factor] for k in range(0, len(candles) - factor + 1, factor)]
    else:
        buckets = {}
        for c in candles:
            key = int(c["time"]) // (step_seconds * factor)
            buckets.setdefault(key, []).append(c)
        chunks = [v for v in buckets.values() if len(v) == factor
                  and v[-1]["time"] - v[0]["time"] == (factor - 1) * step_seconds]
    return [{"time": chunk[0].get("time"), "open": chunk[0]["open"],
             "high": max(c["high"] for c in chunk), "low": min(c["low"] for c in chunk),
             "close": chunk[-1]["close"], "volume": sum(c.get("volume", 0) for c in chunk)}
            for chunk in chunks]


def _record_reasons(diagnostics, group, reasons):
    """Count each gate at most once per decision, retaining one observed example."""
    counts = diagnostics.setdefault(group, {})
    seen = set()
    for reason in reasons:
        code = reason.get("code") or "unspecified"
        if code in seen:
            continue
        seen.add(code)
        item = counts.setdefault(code, {"count": 0, "example": reason.get("message") or "Not supplied"})
        item["count"] += 1


def _decide_at(symbol, candles_so_far, timeframe="5m", version=None, mode="safe", diagnostics=None):
    if len(candles_so_far) < 60:
        return None
    from .decision import HTF
    step = TF_SECONDS[timeframe]
    htf = {tf: _resample(candles_so_far, TF_SECONDS[tf] // step, step)
           for tf in HTF.get(timeframe, [])}
    timestamp = candles_so_far[-1].get("time")
    # Unknown timestamp must not silently become today's market session.
    as_of = datetime.fromtimestamp(timestamp + step, timezone.utc) if timestamp else datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    decision = engine.run_strategy(symbol, timeframe, candles_so_far, htf,
                                   live_price=candles_so_far[-1]["close"], mode=mode, as_of=as_of)
    base_signal = decision.get("signal")
    base_reasons = decision.get("wait_reasons") or [
        {"code": "unspecified", "message": decision.get("reason") or "Base engine returned WAIT without a reason"}]
    if version:
        from .selection import apply_strategy
        apply_strategy(decision, version.strategy, version, symbol, timeframe,
                       candles=candles_so_far)
    if decision.get("signal") not in ("buy", "sell"):
        if diagnostics is not None:
            key = "strategy_veto" if base_signal in ("buy", "sell") else "base_engine_wait"
            diagnostics[key] += 1
            if key == "base_engine_wait":
                _record_reasons(diagnostics, "base_wait_reasons", base_reasons)
            else:
                assessment = decision.get("strategy_evaluation") or {}
                reason = decision.get("reason") or "Selected strategy rejected the setup"
                code = (assessment.get("code") or
                        ("strategy_scope" if "does not cover" in reason else
                         "strategy_min_rr" if "minimum R:R" in reason else "strategy_conditions"))
                _record_reasons(diagnostics, "strategy_veto_reasons", [{"code": code, "message": reason}])
        return None
    if any(decision.get(k) is None for k in ("entry", "stop_loss", "take_profit")):
        if diagnostics is not None:
            diagnostics["invalid_plan"] += 1
        return None
    plan = decision.get("entry_plan") or {}
    return {"direction": decision["signal"], "entry": decision["entry"],
            "stop": decision["stop_loss"], "target": decision["take_profit"],
            "entry_type": plan.get("type", "market"),
            "expiry_bars": int(plan.get("expiry_bars") or 0)}


def backtest(symbol, candles, warmup=60, max_hold=40, tick_mode=False,
             timeframe="5m", version=None, fee_rate=FEE_RATE, slippage_bps=2, mode="safe",
             maker_fee_rate=MAKER_FEE_RATE):
    if timeframe not in TF_SECONDS:
        raise ValueError("Unsupported timeframe")
    if tick_mode:
        return {"trades": 0, "note": "Tick fallback is not valid OHLCV backtest data."}
    if len(candles) < warmup + 2:
        return {"trades": 0, "note": "not enough candles to backtest"}
    trades = []
    diagnostics = {"bars_evaluated": 0, "base_engine_wait": 0,
                   "strategy_veto": 0, "invalid_plan": 0, "unfillable_entry": 0,
                   "base_wait_reasons": {}, "strategy_veto_reasons": {}}
    i = max(warmup, 59)
    slip = slippage_bps / 10000
    while i < len(candles) - 1:
        diagnostics["bars_evaluated"] += 1
        decision = _decide_at(symbol, candles[:i + 1], timeframe=timeframe, version=version,
                              mode=mode, diagnostics=diagnostics)
        if not decision:
            i += 1
            continue
        long = decision["direction"] == "buy"
        stop, target = decision["stop"], decision["target"]
        fill_index = i + 1
        entry_fee_rate = fee_rate
        if decision.get("entry_type") == "limit":
            # Resting limit at the pullback level: fills only if price trades
            # back to it before expiry; no fill = no trade (never chased).
            limit = decision["entry"]
            fill_index = None
            for j in range(i + 1, min(i + 1 + max(1, decision.get("expiry_bars") or 1), len(candles))):
                c = candles[j]
                if (c["low"] <= limit) if long else (c["high"] >= limit):
                    fill_index = j
                    break
            if fill_index is None:
                diagnostics["limit_not_filled"] = diagnostics.get("limit_not_filled", 0) + 1
                i += 1
                continue
            o = candles[fill_index]["open"]
            gapped = (o <= limit) if long else (o >= limit)
            entry = o if gapped else limit
            entry_fee_rate = fee_rate if gapped else maker_fee_rate
        else:
            entry = candles[i + 1]["open"] * (1 + slip if long else 1 - slip)
        # Gap beyond the planned stop/target makes this plan untradeable.
        if not (stop < entry < target if long else target < entry < stop):
            diagnostics["unfillable_entry"] += 1
            i += 1
            continue
        risk = abs(entry - stop)
        exit_index = min(fill_index + max_hold, len(candles) - 1)
        raw_exit = candles[exit_index]["close"]
        reason = "timeout"
        for j in range(fill_index, exit_index + 1):
            c = candles[j]
            stop_hit = c["low"] <= stop if long else c["high"] >= stop
            tp_hit = c["high"] >= target if long else c["low"] <= target
            if j == fill_index and decision.get("entry_type") == "limit":
                tp_hit = False  # intrabar order unknown after a limit fill: never assume TP first
            if stop_hit:  # both touched: conservative stop-first assumption
                raw_exit = min(stop, c["open"]) if long else max(stop, c["open"])
                exit_index, reason = j, "stop"
                break
            if tp_hit:
                raw_exit = target
                exit_index, reason = j, "target"
                break
        exit_px = raw_exit * (1 - slip if long else 1 + slip)
        gross = exit_px - entry if long else entry - exit_px
        fee = entry * entry_fee_rate + exit_px * fee_rate
        net = gross - fee
        trades.append({"r": net / risk, "pnl": net, "gross_r": gross / risk,
                       "fee": fee, "fee_r": fee / risk, "entry_index": fill_index,
                       "entry_type": decision.get("entry_type", "market"),
                       "exit_index": exit_index, "exit_reason": reason})
        i = exit_index + 1  # no overlapping position/future re-use
    result = {"trades": len(trades), "fees_deducted": True, "fee_rate_per_side": fee_rate,
              "diagnostics": diagnostics,
              "slippage_bps_per_side": slippage_bps, "trade_list": trades,
              "limitations": ["No historical news guard, funding, spread or order-book replay",
                              "Single target/fixed stop; no partial TP or trailing stop",
                              "Limit entries fill on touch (queue position ignored); exits taker fee",
                              "Account margin and daily-risk limits are not simulated"],
              "timeframe": timeframe, "mode": mode,
              "session_time_source": "historical candle timestamps" if all(c.get("time") for c in candles)
                  else "reference UTC noon; candle timestamps missing"}
    if not trades:
        return {**result, "note": "no qualifying setups in this window",
                "wins": 0, "losses": 0, "total_r": 0.0, "equity_curve": [],
                "win_rate": None, "profit_factor": None, "avg_r": None,
                "expectancy_r": None, "max_drawdown_r": None, "est_fee_r": 0.0}
    wins = [t for t in trades if t["r"] > 0]
    losses = [t for t in trades if t["r"] <= 0]
    positive, negative = sum(t["r"] for t in wins), -sum(t["r"] for t in losses)
    equity = peak = 0.0
    max_dd = 0.0
    curve = []
    for t in trades:
        equity += t["r"]
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        curve.append(round(equity, 4))
    return {**result, "win_rate": round(len(wins) / len(trades) * 100, 1),
            "profit_factor": round(positive / negative, 2) if negative else None,
            "avg_r": round(mean(t["r"] for t in trades), 4),
            "expectancy_r": round(equity / len(trades), 4),
            "max_drawdown_r": round(max_dd, 4), "total_r": round(equity, 4),
            "wins": len(wins), "losses": len(losses), "equity_curve": curve,
            "est_fee_r": round(sum(t["fee_r"] for t in trades), 4)}
