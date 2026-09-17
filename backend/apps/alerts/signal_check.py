"""Evaluate the scalp signal for a symbol/timeframe and push an alert when it
flips into a fresh buy/sell. Shared by the cron monitor AND the MT5 bridge push,
so notifications fire the moment new candles arrive (no waiting on cron).

2026-09 — two bugs fixed here, both about WHO gets the alert
-----------------------------------------------------------
This function used to end with:

    return broadcast(payload)

`broadcast()` without `users=` pushes to every enabled subscription on the
server. The internal Notification rows above it were correctly scoped to
watchers, so the database looked right while the phones were wrong — which is
why one colleague's gold alerts kept arriving for someone who never watched
gold. The push is now scoped to the same explicit recipient list as the rows.

Second, `WatchItem.min_score` and the daily loss limit are now both honoured
(see apps/alerts/gating.py). A user who asked for 80+ setups no longer gets
68s, and a user who has already hit their loss limit for the day gets no
further trade signals at all.
"""
import logging

from .models import SignalState
from .push import broadcast, vapid_configured

log = logging.getLogger("smartpips.alerts")

HTF = {"1m": ["5m", "15m"], "5m": ["15m", "1h"],
       "15m": ["1h", "4h"], "1h": ["4h"], "4h": []}


def evaluate_and_alert(symbol, timeframe):
    """Run the engine; if the signal changed to a new buy/sell, alert watchers.

    Returns the number of devices notified (0 if no change / nobody watching /
    everyone muted).

    Note the deliberate ordering change: the SignalState is still updated even
    when nobody is subscribed, so the "is this a fresh flip" bookkeeping stays
    correct regardless of who happens to be listening.
    """
    from apps.market.candles import fetch_candles
    from apps.strategy.engine import run_strategy

    candles = fetch_candles(symbol, timeframe, limit=300)
    if not candles or len(candles) < 30:
        # With metals now coming only from LBank, "no candles" is a real and
        # expected state (feed down / contract delisted). Log it so it is
        # visible in /api/logs/ instead of vanishing.
        log.info("signal skipped: %s %s has %d candles", symbol, timeframe,
                 len(candles or []))
        return 0

    htf_map = {}
    for htf in HTF.get(timeframe, []):
        hc = fetch_candles(symbol, htf, limit=200)
        if hc:
            htf_map[htf] = hc

    live = candles[-1]["close"]
    decision = run_strategy(symbol, timeframe, candles, htf_map, live_price=live)
    signal = decision.get("signal", "wait")
    score = int(decision.get("score") or 0)

    state, _ = SignalState.objects.get_or_create(symbol=symbol, timeframe=timeframe)
    changed = signal in ("buy", "sell") and signal != state.last_signal
    state.last_signal = signal
    state.last_score = score
    state.save()

    if not changed:
        return 0

    word = "BUY" if signal == "buy" else "SELL"
    payload = {
        "title": f"SmartPips · {symbol} {timeframe}",
        "body": (f"{word} setup (score {score}, R:R {decision.get('risk_reward')}). "
                 f"Entry {decision.get('entry')} · SL {decision.get('stop_loss')} "
                 f"· TP {decision.get('take_profit')}"),
        # The trading panel lives under /app since the public site took over the
        # root path, so push deep links must carry that prefix.
        "url": f"/app/scalp?symbol={symbol}&tf={timeframe}&quick=1",
        "symbol": symbol, "timeframe": timeframe, "signal": signal,
        "entry": decision.get("entry"), "sl": decision.get("stop_loss"),
        "tp": decision.get("take_profit"), "score": score,
    }

    # ------------------------------------------------------------------
    # ONE recipient list, used for BOTH the notification rows and the push.
    # This is the whole fix: there is no longer any code path that can send
    # to "everyone".
    #   * gating.recipients() = active WatchItem for this symbol
    #                           AND score >= that user's own min_score
    #                           AND not already past their daily loss limit
    # ------------------------------------------------------------------
    from .gating import recipients

    users, skipped = recipients(symbol, score=score, timeframe=timeframe)

    if not users:
        log.info("%s %s %s (score %s): no eligible recipients "
                 "(%d muted by loss limit)",
                 symbol, timeframe, signal, score, len(skipped))
        return 0

    # Mirror the alert into the internal notification centre so the setup is
    # still there when the user opens the panel later (or never granted
    # browser notification permission at all).
    from .notify import notify

    for user in users:
        try:
            notify(
                user,
                title=payload["title"],
                body=payload["body"],
                category="signal",
                level="success" if signal == "buy" else "danger",
                url=payload["url"],
                symbol=symbol,
                meta={"timeframe": timeframe, "signal": signal, "score": score,
                      "entry": decision.get("entry"),
                      "sl": decision.get("stop_loss"),
                      "tp": decision.get("take_profit")},
                # broadcast() below handles the push for this payload, once,
                # for the whole recipient list.
                push=False,
            )
        except Exception:
            # Per-user try/except so one bad row can't cost the other users
            # their alert. Logged, not swallowed silently (T-2).
            log.exception("could not store signal notification for %s",
                          getattr(user, "username", user))

    if not vapid_configured():
        # Rows are written; there is simply no push transport configured.
        log.info("VAPID not configured — %d notification row(s) stored, no push",
                 len(users))
        return 0

    # was: return broadcast(payload)   <-- unscoped, went to EVERY subscription
    sent = broadcast(payload, users=users)
    log.info("%s %s %s score=%s → %d device(s) across %d user(s)",
             symbol, timeframe, signal, score, sent, len(users))
    return sent
