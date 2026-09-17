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

    htf_map = {}
    if data_quality == "candles":
        for label in HTF.get(timeframe, []):
            hc = fetch_candles(symbol, label, limit=200)
            if hc:
                htf_map[label] = hc

    price = float(live_price) if live_price else tf_candles[-1]["close"]

    # 2) STRATEGY ENGINE decides
    decision = run_strategy(symbol, timeframe, tf_candles, htf_map, live_price=price, mode=mode)
    decision["data_quality"] = decision.get("data_quality", data_quality)
    # Freshness stamp: WHEN this decision was made and against WHAT price, so
    # the UI can show signal age and refuse late/chased entries.
    import time as _time
    decision["generated_at"] = int(_time.time() * 1000)
    decision["price_at_signal"] = price

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
        pass

    # 4) DYNAMIC RISK — position size + daily guard (needs a user + account/balance)
    if user is not None:
        _apply_risk(decision, symbol, user, manual_balance=balance,
                    manual_risk_pct=risk_pct)

    return decision


def _apply_risk(decision, symbol, user, default_risk_pct=1.0,
                manual_balance=None, manual_risk_pct=None):
    """Attach position sizing and a daily-loss guard to the decision.

    If manual_balance is given (user typed their account size), use it; otherwise
    fall back to the connected broker account balance.
    """
    from .risk import position_size, daily_risk_guard

    balance = None
    if manual_balance and float(manual_balance) > 0:
        balance = float(manual_balance)
    else:
        try:
            from apps.mt5.models import MT5Account
            acc = MT5Account.objects.first()
            if acc and acc.balance:
                balance = acc.balance
        except Exception:
            balance = None

    risk_pct = float(manual_risk_pct) if manual_risk_pct else default_risk_pct
    risk_pct = max(0.1, min(10.0, risk_pct))  # clamp to a sane 0.1%-10%

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
        pass

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
            lev_value = lev["leverage"]

    # position sizing (uses leverage to show required margin for crypto)
    is_crypto = base.endswith("USDT")
    used_margin = 0.0
    if balance and is_crypto:
        from .risk import used_crypto_margin, NON_REAL_SOURCES
        try:
            used_margin = used_crypto_margin(user, sources=NON_REAL_SOURCES)
        except Exception:
            used_margin = 0.0
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
