"""
Central Decision Engine.

One entry point that runs the WHOLE pipeline so the scalp view, the alert monitor
and the chat assistant all share identical logic:

    candles (cTrader/MT5 -> TwelveData -> ticks)
        -> multi-timeframe structure + liquidity + order-flow + session
        -> strategy engine score & decision (run_strategy)
        -> economic-news guard
        -> dynamic risk: position size + daily-loss guard
        -> a single decision object (signal, grade, levels, lots, reasons)

This is the "Decision Engine" layer: everything funnels through decide().
"""
HTF = {"1m": ["5m", "15m"], "5m": ["15m", "1h"],
       "15m": ["1h", "4h"], "1h": ["4h"], "4h": []}


def decide(symbol, timeframe="5m", user=None, tick_series=None, live_price=None,
           balance=None, risk_pct=None, mode="safe"):
    """Run the full pipeline and return the engine decision (enriched).

    balance/risk_pct (optional): if the user provides their account size and the
    percent they want to risk, position sizing uses those instead of a broker
    account, so the signal includes a concrete suggested lot size.
    """
    from apps.market.candles import fetch_candles
    from .engine import run_strategy

    symbol = symbol.upper()

    # 1) DATA — real candles first (broker via candles.py), tick fallback handled below
    tf_candles = fetch_candles(symbol, timeframe, limit=300)
    data_quality = "candles"

    if not tf_candles and tick_series:
        ticks = [float(t) for t in tick_series if isinstance(t, (int, float))][-300:]
        if len(ticks) >= 30:
            tf_candles = []
            for j, p in enumerate(ticks):
                prev = ticks[j - 1] if j > 0 else p
                tf_candles.append({"open": prev, "high": max(prev, p),
                                   "low": min(prev, p), "close": p, "volume": 1})
            data_quality = "ticks"

    if not tf_candles:
        return {"signal": "wait", "confidence": "low", "score": 0,
                "reason": "no candle/tick data available", "data_quality": "none"}

    # Use completed bars, not the currently forming bar, for stable signals.
    import time as _clock
    from .backtest import TF_SECONDS
    step = TF_SECONDS.get(timeframe, 300)
    if data_quality == "candles":
        from .data_quality import inspect_bars
        tf_candles, quality = inspect_bars(tf_candles, step, _clock.time(),
                                         continuous=symbol not in ("XAUUSD", "XAGUSD"))
        if not quality["valid"]:
            from .evidence import enrich_explanation
            return enrich_explanation({"signal": "wait", "score": 0, "confidence": "low",
                "data_quality": "invalid", "data_quality_gate": quality,
                "reason": "DATA_QUALITY_GATE: " + quality["reason"]})
        newest = tf_candles[-1].get("time")
        if newest and _clock.time() - (newest + step) > max(step * 3, 180):
            return {"signal": "wait", "score": 0, "confidence": "low", "data_quality": "stale",
                    "reason": "Candle feed is stale; new entries disabled."}

    htf_map = {}
    if data_quality == "candles":
        for label in HTF.get(timeframe, []):
            hc = fetch_candles(symbol, label, limit=200)
            if hc:
                htf_step = TF_SECONDS[label]
                clean, htf_quality = inspect_bars(hc, htf_step, _clock.time(),
                    continuous=symbol not in ("XAUUSD", "XAGUSD"))
                if htf_quality["valid"]:
                    htf_map[label] = clean


    price = float(live_price) if live_price else tf_candles[-1]["close"]

    # 2) STRATEGY ENGINE decides
    decision = run_strategy(symbol, timeframe, tf_candles, htf_map, live_price=price, mode=mode)
    decision["data_quality"] = decision.get("data_quality", data_quality)
    # Freshness stamp: WHEN this decision was made and against WHAT price, so
    # the UI can show signal age and refuse late/chased entries.
    import time as _time
    decision["generated_at"] = int(_time.time() * 1000)
    decision["price_at_signal"] = price

    # Apply the selected configuration to the SAME plan used by alerts and chat.
    if user is not None:
        from .config_models import Strategy
        from .selection import apply_strategy
        strategy = Strategy.objects.filter(user=user, is_active=True, archived=False).first()
        if strategy:
            apply_strategy(decision, strategy, strategy.current_version(), symbol, timeframe)
    # Tick-shaped pseudo-candles cannot establish volume/structure reliably.
    if data_quality == "ticks":
        decision.update(signal="wait", confidence="low", data_quality="ticks",
                        reason="Real OHLCV candles required; tick fallback is display-only.")

    # 3) NEWS GUARD
    try:
        from apps.market.calendar_guard import high_impact_soon
        blocked, info = high_impact_soon(within_min=30)
        if blocked and decision.get("signal") in ("buy", "sell"):
            decision["signal"] = "wait"
            decision["confidence"] = "low"
            decision["reason"] = f"high-impact news guard: {info}"
            decision["news_guard"] = info
    except Exception:
        decision["news_status"] = "unavailable"
    else:
        decision["news_status"] = "checked_current_feed_only"

    # 4) DYNAMIC RISK — position size + daily guard (needs a user + account/balance)
    if user is not None:
        _apply_risk(decision, symbol, user, manual_balance=balance,
                    manual_risk_pct=risk_pct)

    from .evidence import enrich_explanation
    enrich_explanation(decision)
    if user is not None:
        from apps.trades.snapshots import issue_token
        decision["decision_token"] = issue_token(user, symbol, timeframe, decision)
    return decision


def _apply_risk(decision, symbol, user, default_risk_pct=1.0,
                manual_balance=None, manual_risk_pct=None):
    """Attach position sizing and a daily-loss guard to the decision.

    If manual_balance is given (user typed their account size), use it; otherwise
    fall back to the connected broker account balance.
    """
    from .risk import position_size, daily_risk_guard

    import math
    balance = None
    if manual_balance is not None and manual_balance != "":
        try:
            balance = float(manual_balance)
            if not math.isfinite(balance) or balance <= 0:
                raise ValueError
        except (ValueError, TypeError):
            decision.update(signal="wait", confidence="low", reason="Invalid account balance.", risk_block="INVALID_BALANCE")
            return
    else:
        try:
            from apps.mt5.models import MT5Account
            acc = MT5Account.objects.first()
            if acc and acc.balance and math.isfinite(acc.balance) and acc.balance > 0:
                balance = acc.balance
        except Exception:
            balance = None
    try:
        risk_pct = float(manual_risk_pct) if manual_risk_pct is not None and manual_risk_pct != "" else default_risk_pct
        if not math.isfinite(risk_pct) or risk_pct <= 0:
            raise ValueError
    except (ValueError, TypeError):
        decision.update(signal="wait", confidence="low", reason="Invalid requested risk.", risk_block="INVALID_RISK")
        return
    strategy_risk = decision.get("strategy_risk") or {}
    if strategy_risk.get("risk_per_trade_pct") is not None:
        risk_pct = min(risk_pct, strategy_risk["risk_per_trade_pct"])
    risk_pct = min(10.0, risk_pct)  # Never raise a user's smaller risk request.

    # daily loss / consecutive-loss guard
    try:
        guard = daily_risk_guard(user, balance=balance)
        if guard["blocked"] and decision.get("signal") in ("buy", "sell"):
            decision["signal"] = "wait"
            decision["confidence"] = "low"
            decision["reason"] = guard["reason"]
            decision["risk_block"] = guard["reason"]
            return
    except Exception:
        decision.update(signal="wait", confidence="low", reason="Risk verification unavailable.", risk_block="RISK_CHECK_UNAVAILABLE")
        return

    if decision.get("signal") in ("buy", "sell") and strategy_risk.get("max_open_positions"):
        from apps.trades.models import Trade
        if Trade.objects.filter(user=user, status="open").count() >= strategy_risk["max_open_positions"]:
            decision.update(signal="wait", confidence="low", reason="Strategy open-position limit reached.")
            return

    # leverage suggestion (futures / metals only — spot has no leverage)
    base = symbol.upper()
    is_spot = base.endswith("USDT") and not base.endswith(":PERP")
    lev_value = None
    if decision.get("signal") in ("buy", "sell") and not is_spot:
        from .risk import suggest_leverage
        lev = suggest_leverage(symbol, decision.get("entry"),
                               decision.get("stop_loss"), decision.get("regime", "normal"))
        if lev:
            decision["leverage"] = lev
            lev_value = min(lev["leverage"], strategy_risk.get("max_leverage", lev["leverage"]))
            from apps.prefs.models import RiskLimits
            limits = RiskLimits.objects.filter(user=user).first()
            if limits:
                lev_value = min(lev_value, limits.max_leverage)
            lev["leverage"] = lev_value

    # position sizing (uses leverage to show required margin for crypto)
    is_crypto = base.replace(":PERP", "").endswith("USDT")
    used_margin = 0.0
    if balance and is_crypto:
        from .risk import used_crypto_margin, NON_REAL_SOURCES
        try:
            used_margin = used_crypto_margin(user, sources=NON_REAL_SOURCES)
        except Exception:
            decision.update(signal="wait", confidence="low", reason="Open exposure verification unavailable.", risk_block="EXPOSURE_UNAVAILABLE")
            return
        available_margin = round(balance - used_margin, 2)
        decision["margin_status"] = {
            "balance": balance, "used_margin": used_margin,
            "available_margin": available_margin,
        }
        # No meaningful capital left to open another position — say so plainly
        # instead of suggesting a trade the user can't actually place.
        if decision.get("signal") in ("buy", "sell") and available_margin < max(1.0, balance * 0.02):
            decision["signal"] = "wait"
            decision["confidence"] = "low"
            decision["reason"] = (
                f"no available margin — ${used_margin} of ${balance} already "
                f"committed to open position(s)")
            decision["risk_block"] = decision["reason"]
            return

    if decision.get("signal") in ("buy", "sell") and balance:
        size = position_size(symbol, balance, risk_pct,
                             decision.get("entry"), decision.get("stop_loss"),
                             leverage=lev_value)
        if not size:
            decision.update(signal="wait", confidence="low", reason="No valid position size within the requested risk budget.", risk_block="POSITION_SIZE_UNAVAILABLE")
            return
        if size:
            # HARD CAP: the trade's required margin must NEVER exceed what is
            # actually free (balance minus margin already committed to open
            # positions). The old code only capped when used_margin > 0, so a
            # tight stop with zero open trades could size a position needing
            # more margin than the whole account. Cap unconditionally now.
            if is_crypto:
                available_margin = round(balance - used_margin, 2)
                if size.get("margin") and available_margin > 0 and size["margin"] > available_margin:
                    scale = available_margin / size["margin"]
                    size["quantity"] = round(size["quantity"] * scale,
                                             8 if size["quantity"] < 1 else 4)
                    size["position_value"] = round(size["quantity"] * decision["entry"], 2)
                    size["margin"] = round(size["position_value"] / (lev_value or 1), 2)
                    size["risk_dollars"] = round(size["risk_dollars"] * scale, 2)
                    size["capped_by_available_margin"] = True
            decision["position_size"] = size

    # ---- ORDER TICKET: everything needed to place this on an exchange, the
    # way the exchange app itself frames it (margin mode / order type / size /
    # margin / estimated liquidation), so nothing is left to guesswork. ------
    if decision.get("signal") in ("buy", "sell") and decision.get("entry"):
        try:
            decision["order_ticket"] = _build_order_ticket(
                decision, symbol, lev_value, is_spot)
        except Exception:
            pass


def _build_order_ticket(decision, symbol, lev_value, is_spot):
    """Concrete execution parameters for the signal.

    order_type: 'market' when the engine's entry is at/inside a tiny band of
    the live price (chasing a limit there would just miss the move); 'limit'
    with limit_price when the entry sits meaningfully away (pullback entry).
    est_liquidation: isolated-margin approximation entry*(1 -/+ 0.95/lev) —
    clearly labelled an estimate; the exchange's own maintenance margin decides
    the real level.
    """
    entry = float(decision["entry"])
    live = decision.get("price_at_signal") or entry
    side = decision["signal"]
    sl = decision.get("stop_loss")

    # entry vs live distance, as a fraction of the stop distance
    stop_dist = abs(entry - float(sl)) if sl is not None else None
    gap = abs(entry - float(live))
    use_limit = stop_dist is not None and stop_dist > 0 and gap > 0.15 * stop_dist

    ticket = {
        "side": "long" if side == "buy" else "short",
        "order_type": "limit" if use_limit else "market",
        "limit_price": round(entry, 6) if use_limit else None,
        "margin_mode": None if is_spot else "isolated",
        "leverage": None if is_spot else (lev_value or 1),
        "quantity": (decision.get("position_size") or {}).get("quantity"),
        "unit": (decision.get("position_size") or {}).get("unit"),
        "position_value": (decision.get("position_size") or {}).get("position_value"),
        "margin": (decision.get("position_size") or {}).get("margin"),
    }
    if not is_spot and lev_value:
        liq_frac = 0.95 / lev_value
        est_liq = entry * (1 - liq_frac) if side == "buy" else entry * (1 + liq_frac)
        ticket["est_liquidation"] = round(est_liq, 6)
        ticket["est_liquidation_note"] = "estimate — exchange maintenance margin decides the real level"
    # Freshness / anti-chase: past this price the entry is LATE — don't chase.
    if stop_dist:
        chase = 0.35 * stop_dist
        ticket["max_chase_price"] = round(entry + chase, 6) if side == "buy" else round(entry - chase, 6)
    return ticket
