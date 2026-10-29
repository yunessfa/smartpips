"""Sequential simulation with explicit fees, slippage and funding.

Market plans enter at the next open; limit (pullback) plans only if price
trades back to the level before the order expires (never chased). Stops and
targets are exchange trigger orders, so both exit at market (taker fee +
slippage). When stop and target are touched in the same bar the stop is
assumed first. No historical news/order-book data is invented.

Live parity (2026-10):
  * the base engine sees the same 300-bar window the live decide() uses, and
    higher timeframes come from REAL closed HTF candles when they are supplied
    (`htf_series`), instead of being resampled from a 500-bar window — which
    could never build a 4h EMA200 and silently disabled the HTF filter;
  * the trend-pullback playbook is evaluated by the very same function the
    live signal uses (trend_pullback.setup_at), on a long history.

Results come with a sample-size verdict, a 95% confidence interval for the
expectancy, an in-sample/out-of-sample split and monthly results, so a lucky
handful of trades is not mistaken for an edge.
"""
import math
from bisect import bisect_right
from statistics import mean, stdev
from datetime import datetime, timezone
from . import engine

TF_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
FEE_RATE = 0.0006
MAKER_FEE_RATE = 0.0002  # resting limit entries
FUNDING_RATE_8H = 0.0001  # perpetual funding, charged against every position (conservative)
ENGINE_WINDOW = 300       # bars the live decide() gives the engine
HTF_WINDOW = 200          # HTF bars the live decide() fetches
DEFAULT_MAX_HOLD = 40
MIN_TRADES_FOR_VERDICT = 30


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


def _closed_htf(series, label, close_time, limit=HTF_WINDOW):
    """HTF bars fully closed at `close_time` (bar time + step <= close_time)."""
    step = TF_SECONDS[label]
    times = [c["time"] for c in series]
    k = bisect_right(times, close_time - step)
    return series[max(0, k - limit):k]


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


def _decide_at(symbol, candles_so_far, timeframe="5m", version=None, mode="safe", diagnostics=None,
               htf_series=None):
    if len(candles_so_far) < 60:
        return None
    from .decision import HTF
    step = TF_SECONDS[timeframe]
    timestamp = candles_so_far[-1].get("time")
    htf = {}
    for label in HTF.get(timeframe, []):
        if htf_series and htf_series.get(label) and timestamp:
            htf[label] = _closed_htf(htf_series[label], label, timestamp + step)
        else:
            factor = TF_SECONDS[label] // step
            htf[label] = _resample(candles_so_far[-HTF_WINDOW * factor:], factor, step)
    window = candles_so_far[-ENGINE_WINDOW:]
    # Unknown timestamp must not silently become today's market session.
    as_of = datetime.fromtimestamp(timestamp + step, timezone.utc) if timestamp else datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    decision = engine.run_strategy(symbol, timeframe, window, htf,
                                   live_price=window[-1]["close"], mode=mode, as_of=as_of)
    base_signal = decision.get("signal")
    base_reasons = decision.get("wait_reasons") or [
        {"code": "unspecified", "message": decision.get("reason") or "Base engine returned WAIT without a reason"}]
    if version:
        from .selection import apply_strategy
        apply_strategy(decision, version.strategy, version, symbol, timeframe,
                       candles=window)
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


def _playbook_decider(symbol, candles, timeframe, htf_series, version, diagnostics):
    """Per-bar decisions from the validated playbook (same code as live)."""
    from . import trend_pullback as tp
    htf = dict(htf_series or {})
    step = TF_SECONDS[timeframe]
    for label in ("4h", "1h"):
        if not htf.get(label) and TF_SECONDS[label] > step:
            factor = TF_SECONDS[label] // step
            htf[label] = _resample(candles, factor, step)
    at = tp.series_decider(candles, timeframe, htf, symbol)
    rules_version = version if (version and version.rules) else None

    def decide(i):
        s = at(i)
        if s["signal"] not in ("buy", "sell"):
            diagnostics["base_engine_wait"] += 1
            _record_reasons(diagnostics, "base_wait_reasons", s["wait_reasons"] or
                            [{"code": "unspecified", "message": "conditions not met"}])
            return None
        if rules_version is not None:
            # Extra user rules can only veto the playbook (engine readings are
            # computed only on the bars where the playbook actually fires).
            from .rule_engine import evaluate
            snap = _decide_snapshot(symbol, candles[:i + 1], timeframe, htf)
            snap.update(signal=s["signal"], entry=s["entry"], stop_loss=s["stop"],
                        take_profit=s["target"], risk_reward=s["target_r"])
            verdict = evaluate(rules_version, snap)
            if str(verdict.get("signal", "")).lower() != s["signal"]:
                diagnostics["strategy_veto"] += 1
                _record_reasons(diagnostics, "strategy_veto_reasons",
                                [{"code": "strategy_conditions", "message": verdict.get("reason") or "rules"}])
                return None
        return {"direction": s["signal"], "entry": s["entry"], "stop": s["stop"], "target": s["target"],
                "entry_type": "limit", "expiry_bars": tp.LIMIT_VALID_BARS, "max_hold": tp.MAX_HOLD_BARS}
    return decide


def _decide_snapshot(symbol, prefix, timeframe, htf_series):
    step = TF_SECONDS[timeframe]
    t = prefix[-1].get("time")
    from .decision import HTF
    htf = {label: _closed_htf(htf_series[label], label, t + step) for label in HTF.get(timeframe, [])
           if htf_series.get(label) and t}
    return engine.run_strategy(symbol, timeframe, prefix[-ENGINE_WINDOW:], htf,
                               live_price=prefix[-1]["close"], mode="safe",
                               as_of=datetime.fromtimestamp(t + step, timezone.utc) if t else None)


def uses_playbook(mode=None, version=None):
    if mode == "trend":
        return True
    risk = getattr(version, "risk", None) or {}
    return risk.get("signal_source") == "playbook"


def backtest(symbol, candles, warmup=60, max_hold=None, tick_mode=False,
             timeframe="5m", version=None, fee_rate=FEE_RATE, slippage_bps=2, mode="safe",
             maker_fee_rate=MAKER_FEE_RATE, htf_series=None, funding_rate_8h=FUNDING_RATE_8H):
    if timeframe not in TF_SECONDS:
        raise ValueError("Unsupported timeframe")
    if tick_mode:
        return {"trades": 0, "note": "Tick fallback is not valid OHLCV backtest data."}
    if len(candles) < warmup + 2:
        return {"trades": 0, "note": "not enough candles to backtest"}
    playbook = uses_playbook(mode, version)
    trades = []
    diagnostics = {"bars_evaluated": 0, "base_engine_wait": 0,
                   "strategy_veto": 0, "invalid_plan": 0, "unfillable_entry": 0,
                   "base_wait_reasons": {}, "strategy_veto_reasons": {}}
    i = max(warmup, 59)
    if playbook:
        from .trend_pullback import MIN_BARS
        decide_playbook = _playbook_decider(symbol, candles, timeframe, htf_series, version, diagnostics)
        i = max(i, MIN_BARS - 1)
    slip = slippage_bps / 10000
    step = TF_SECONDS[timeframe]
    while i < len(candles) - 1:
        diagnostics["bars_evaluated"] += 1
        if playbook:
            decision = decide_playbook(i)
        else:
            decision = _decide_at(symbol, candles[:i + 1], timeframe=timeframe, version=version,
                                  mode=mode, diagnostics=diagnostics, htf_series=htf_series)
        if not decision:
            i += 1
            continue
        long = decision["direction"] == "buy"
        stop, target = decision["stop"], decision["target"]
        hold_limit = decision.get("max_hold") or max_hold or DEFAULT_MAX_HOLD
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
            entry = o * (1 + slip if long else 1 - slip) if gapped else limit
            entry_fee_rate = fee_rate if gapped else maker_fee_rate
        else:
            entry = candles[i + 1]["open"] * (1 + slip if long else 1 - slip)
        # Gap beyond the planned stop/target makes this plan untradeable.
        if not (stop < entry < target if long else target < entry < stop):
            diagnostics["unfillable_entry"] += 1
            i += 1
            continue
        risk = abs(entry - stop)
        exit_index = min(fill_index + hold_limit, len(candles) - 1)
        raw_exit = candles[exit_index]["close"]
        reason = "timeout"
        for j in range(fill_index, exit_index + 1):
            c = candles[j]
            stop_hit = c["low"] <= stop if long else c["high"] >= stop
            tp_hit = c["high"] >= target if long else c["low"] <= target
            if j == fill_index and decision.get("entry_type") == "limit":
                tp_hit = False  # intrabar order unknown after a limit fill: never assume TP first
            if stop_hit:  # both touched: conservative stop-first assumption
                if j == fill_index:
                    raw_exit = stop
                else:
                    raw_exit = min(stop, c["open"]) if long else max(stop, c["open"])
                exit_index, reason = j, "stop"
                break
            if tp_hit:
                raw_exit = target
                exit_index, reason = j, "target"
                break
        exit_px = raw_exit * (1 - slip if long else 1 + slip)
        gross = exit_px - entry if long else entry - exit_px
        held_hours = (exit_index - fill_index + 1) * step / 3600
        funding = entry * funding_rate_8h * held_hours / 8 if symbol.upper().replace(":PERP", "") not in ("XAUUSD", "XAGUSD") else 0.0
        fee = entry * entry_fee_rate + exit_px * fee_rate + funding
        net = gross - fee
        trades.append({"r": net / risk, "pnl": net, "gross_r": gross / risk,
                       "pct": net / entry * 100,
                       "fee": fee, "fee_r": fee / risk, "entry_index": fill_index,
                       "entry_time": candles[fill_index].get("time"),
                       "direction": "long" if long else "short",
                       "entry_type": decision.get("entry_type", "market"),
                       "exit_index": exit_index, "exit_reason": reason})
        i = exit_index + 1  # no overlapping position/future re-use
    result = {"trades": len(trades), "fees_deducted": True, "fee_rate_per_side": fee_rate,
              "maker_fee_rate": maker_fee_rate, "funding_rate_8h": funding_rate_8h,
              "diagnostics": diagnostics, "signal_source": "playbook" if playbook else "engine",
              "playbook": "trend_pullback" if playbook else None,
              "slippage_bps_per_side": slippage_bps, "trade_list": trades,
              "limitations": ["No historical news guard, spread or order-book replay",
                              "Single target/fixed stop; no partial TP or trailing stop",
                              "Limit entries fill on touch (queue position ignored); exits pay taker fee + slippage",
                              "Funding approximated at a constant rate against every position",
                              "Account margin and daily-risk limits are not simulated"],
              "timeframe": timeframe, "mode": mode,
              "window": {"bars": len(candles), "start": candles[0].get("time"), "end": candles[-1].get("time")},
              "session_time_source": "historical candle timestamps" if all(c.get("time") for c in candles)
                  else "reference UTC noon; candle timestamps missing"}
    if not trades:
        return {**result, "note": "no qualifying setups in this window",
                "wins": 0, "losses": 0, "total_r": 0.0, "equity_curve": [],
                "win_rate": None, "profit_factor": None, "avg_r": None,
                "expectancy_r": None, "max_drawdown_r": None, "est_fee_r": 0.0,
                "evidence": evidence([])}
    return {**result, **summarize(trades), "evidence": evidence(trades)}


def summarize(trades):
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
    return {"win_rate": round(len(wins) / len(trades) * 100, 1),
            "profit_factor": round(positive / negative, 2) if negative else None,
            "avg_r": round(mean(t["r"] for t in trades), 4),
            "expectancy_r": round(equity / len(trades), 4),
            "max_drawdown_r": round(max_dd, 4), "total_r": round(equity, 4),
            "wins": len(wins), "losses": len(losses), "equity_curve": curve,
            "est_fee_r": round(sum(t["fee_r"] for t in trades), 4),
            "avg_gross_r": round(mean(t["gross_r"] for t in trades), 4),
            "exit_reasons": {k: sum(t["exit_reason"] == k for t in trades) for k in ("target", "stop", "timeout")}}


def evidence(trades):
    """How much can these trades be trusted? (sample size, CI, OOS, months)."""
    n = len(trades)
    out = {"n": n, "min_trades_for_verdict": MIN_TRADES_FOR_VERDICT}
    if n == 0:
        out.update(verdict="no_trades", expectancy_95ci=None)
        return out
    rs = [t["r"] for t in trades]
    m = mean(rs)
    if n >= 2:
        se = stdev(rs) / math.sqrt(n)
        lo, hi = m - 1.96 * se, m + 1.96 * se
        out["expectancy_95ci"] = [round(lo, 3), round(hi, 3)]
        out["t_stat"] = round(m / se, 2) if se > 0 else None
    else:
        lo = hi = m
        out["expectancy_95ci"] = None
    if n < MIN_TRADES_FOR_VERDICT:
        verdict = "insufficient_sample"
    elif lo > 0:
        verdict = "positive_edge"
    elif hi < 0:
        verdict = "negative_edge"
    else:
        verdict = "inconclusive"
    out["verdict"] = verdict
    # chronological split: first 70% of trades vs last 30% (out of sample for a reader
    # who tuned anything on the early part)
    k = max(1, int(n * 0.7))
    early, late = rs[:k], rs[k:]
    out["in_sample"] = {"n": len(early), "expectancy_r": round(mean(early), 3)}
    out["out_of_sample"] = {"n": len(late), "expectancy_r": round(mean(late), 3) if late else None}
    months = {}
    for t in trades:
        ts = t.get("entry_time")
        if not ts:
            continue
        key = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
        months.setdefault(key, []).append(t["r"])
    out["monthly"] = [{"month": k, "trades": len(v), "total_r": round(sum(v), 2)} for k, v in sorted(months.items())]
    if months:
        out["positive_months_pct"] = round(100 * sum(sum(v) > 0 for v in months.values()) / len(months), 1)
    by_dir = {}
    for t in trades:
        by_dir.setdefault(t.get("direction") or "?", []).append(t["r"])
    out["by_direction"] = {k: {"n": len(v), "expectancy_r": round(mean(v), 3)} for k, v in by_dir.items()}
    return out
