"""Evaluate user-defined AlertRules against that user's own OPEN trades.

Design notes
------------
* **Advisory only.** Firing a rule creates a notification. It never closes,
  resizes or modifies a position. The user decides what to do next, which is
  why every message links back to the trade.
* **No user code.** A rule is a fixed condition keyword plus a number. Nothing
  supplied by the user is ever evaluated as an expression.
* **One message per crossing.** `AlertRuleState` latches when a condition turns
  true and unlatches when it turns false again, so "PnL >= +25" notifies once
  rather than on every monitor pass for as long as the trade stays in profit.
* **PnL is not recomputed by hand.** We reuse `Trade.compute_pnl()` by putting
  the live price into `exit_price` on an unsaved instance, so the alert number
  always matches what the journal would show.
"""

import logging

from django.utils import timezone

from .models import AlertRule, AlertRuleState
from .notify import notify

log = logging.getLogger("smartpips.alerts")


def _base_symbol(symbol):
    """BTCUSDT:PERP -> BTCUSDT. Alert rules should not care about the venue."""
    return (symbol or "").split(":")[0].strip().upper()


def current_price(symbol, _cache=None):
    """Best-effort last traded price for a symbol, or None.

    Uses the same candle pipeline the strategy engine uses so the alert and the
    chart agree. Returns None rather than guessing when no data is available;
    callers skip the rule in that case instead of firing on bad data.
    """
    if _cache is not None and symbol in _cache:
        return _cache[symbol]
    price = None
    try:
        from apps.market.candles import fetch_candles
        candles = fetch_candles(_base_symbol(symbol), "1m", limit=2)
        if candles:
            price = float(candles[-1]["close"])
    except Exception:
        price = None
    if _cache is not None:
        _cache[symbol] = price
    return price


def unrealized(trade, price):
    """(pnl_quote, pnl_percent) for an open trade at `price`, via the model."""
    if not price or not trade.entry_price:
        return None, None
    original_exit = trade.exit_price
    try:
        trade.exit_price = price
        return trade.compute_pnl()
    finally:
        trade.exit_price = original_exit


def _condition_met(rule, trade, price):
    """Return (met, value) for one rule against one trade at `price`.

    `value` is the number the user cares about, used in the message body.
    Returns (False, None) when the inputs needed are missing.
    """
    cond = rule.condition
    thr = rule.threshold

    if cond in ("pnl_above", "pnl_below", "pnl_pct_above", "pnl_pct_below"):
        pnl, pct = unrealized(trade, price)
        if pnl is None:
            return False, None
        if cond == "pnl_above":
            return pnl >= thr, pnl
        if cond == "pnl_below":
            return pnl <= thr, pnl
        if cond == "pnl_pct_above":
            return pct >= thr, pct
        return pct <= thr, pct

    if cond == "price_above":
        return (price is not None and price >= thr), price
    if cond == "price_below":
        return (price is not None and price <= thr), price

    if cond == "reaches_tp":
        tp = trade.take_profit
        if not tp or price is None:
            return False, None
        met = price >= tp if trade.direction == "long" else price <= tp
        return met, price

    if cond == "reaches_sl":
        sl = trade.stop_loss
        if not sl or price is None:
            return False, None
        met = price <= sl if trade.direction == "long" else price >= sl
        return met, price

    if cond == "move_pct_from_entry":
        if price is None or not trade.entry_price:
            return False, None
        moved = abs((price - trade.entry_price) / trade.entry_price) * 100
        return moved >= thr, round(moved, 4)

    if cond == "open_longer_than":
        if not trade.opened_at:
            return False, None
        minutes = (timezone.now() - trade.opened_at).total_seconds() / 60
        return minutes >= thr, round(minutes, 1)

    return False, None


def _message(rule, trade, value):
    """Human sentence for the notification body."""
    sym = trade.symbol
    cond = rule.condition
    if cond in ("pnl_above", "pnl_below"):
        sign = "+" if (value or 0) >= 0 else ""
        return f"{sym} position reached {sign}{value:.2f} USDT PnL."
    if cond in ("pnl_pct_above", "pnl_pct_below"):
        sign = "+" if (value or 0) >= 0 else ""
        return f"{sym} position reached {sign}{value:.2f}% PnL."
    if cond in ("price_above", "price_below"):
        return f"{sym} price reached {value:g}."
    if cond == "reaches_tp":
        return f"{sym} price reached your take profit ({trade.take_profit:g})."
    if cond == "reaches_sl":
        return f"{sym} price reached your stop loss ({trade.stop_loss:g})."
    if cond == "move_pct_from_entry":
        return f"{sym} moved {value:g}% away from entry."
    if cond == "open_longer_than":
        return f"{sym} position has been open for {value:g} minutes."
    return f"{sym}: {rule.describe()}"


def _level(rule, value):
    if rule.condition in ("pnl_below", "pnl_pct_below", "reaches_sl"):
        return "danger"
    if rule.condition in ("pnl_above", "pnl_pct_above", "reaches_tp"):
        return "success"
    return "warning" if rule.condition == "open_longer_than" else "info"


def _category(rule):
    if rule.condition.startswith("pnl"):
        return "pnl"
    if rule.condition in ("reaches_sl",):
        return "risk"
    return "position"


def _matching_trades(rule, open_trades):
    if rule.scope == AlertRule.SCOPE_TRADE:
        return [t for t in open_trades if rule.trade_id and t.id == rule.trade_id]
    if rule.scope == AlertRule.SCOPE_SYMBOL:
        want = _base_symbol(rule.symbol)
        return [t for t in open_trades if _base_symbol(t.symbol) == want]
    return list(open_trades)


def evaluate_for_user(user, price_cache=None):
    """Run every enabled rule this user owns.

    Returns a diagnostics dict rather than a bare count. Silence here has
    several very different causes -- no rules, no open trades, or a market feed
    that returned no price -- and the user cannot tell them apart from an empty
    notification centre. The panel surfaces these numbers so "nothing happened"
    is always explainable.
    """
    from apps.trades.models import Trade

    stats = {
        "fired": 0,
        "rules": 0,
        "open_trades": 0,
        "checked": 0,
        "no_price": 0,
        "symbols_without_price": [],
        # Surfaced so "my alerts went quiet" has a visible reason instead of
        # looking like a broken cron.
        "muted": False,
        "muted_reason": "",
    }

    rules = list(AlertRule.objects.filter(user=user, enabled=True))
    stats["rules"] = len(rules)
    if not rules:
        return stats

    # LOSS-LIMIT MUTE, pre-flight.
    # Checked HERE rather than relying on notify() to drop each message, for
    # one specific reason: bailing out before the loop means AlertRuleState
    # never latches. If we let the rules latch while muted, then tomorrow —
    # when the limit resets — a condition that is still true would be treated
    # as "already reported" and stay silent until it cleared and re-crossed.
    try:
        from .gating import loss_limit_state
        limit_state = loss_limit_state(user)
        if limit_state.get("blocked"):
            stats["muted"] = True
            stats["muted_reason"] = limit_state.get("reason") or "loss limit reached"
            log.info("alert rules skipped for %s: %s",
                     getattr(user, "username", user), stats["muted_reason"])
            return stats
    except Exception:
        log.exception("loss-limit pre-flight failed for %s", user)

    open_trades = list(Trade.objects.filter(user=user, status="open"))
    stats["open_trades"] = len(open_trades)
    if not open_trades:
        return stats

    if price_cache is None:
        price_cache = {}
    fired = 0

    for rule in rules:
        for trade in _matching_trades(rule, open_trades):
            price = current_price(trade.symbol, price_cache)
            stats["checked"] += 1
            if price is None:
                stats["no_price"] += 1
                if trade.symbol not in stats["symbols_without_price"]:
                    stats["symbols_without_price"].append(trade.symbol)
            met, value = _condition_met(rule, trade, price)

            state, _ = AlertRuleState.objects.get_or_create(rule=rule, trade=trade)

            if not met:
                # Condition cleared -> re-arm so the next crossing notifies again.
                if state.latched:
                    state.latched = False
                    state.last_value = value
                    state.save(update_fields=["latched", "last_value", "updated"])
                continue

            if state.latched and rule.once_per_crossing:
                continue  # already told them about this crossing

            notify(
                user,
                title=f"{trade.symbol} · {rule.name or rule.describe()}",
                body=_message(rule, trade, value),
                category=_category(rule),
                level=_level(rule, value),
                url=f"/app/trades?trade={trade.id}",
                symbol=trade.symbol,
                trade=trade,
                rule=rule,
                meta={
                    "value": value,
                    "price": price,
                    "threshold": rule.threshold,
                    "condition": rule.condition,
                    "direction": trade.direction,
                    "entry": trade.entry_price,
                },
                push=rule.push,
            )

            state.latched = True
            state.last_value = value
            state.save(update_fields=["latched", "last_value", "updated"])

            rule.trigger_count += 1
            rule.last_triggered_at = timezone.now()
            rule.save(update_fields=["trigger_count", "last_triggered_at"])
            fired += 1

    stats["fired"] = fired
    return stats


def run_all():
    """Evaluate rules for every user that has at least one enabled rule."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user_ids = (AlertRule.objects.filter(enabled=True)
                .values_list("user_id", flat=True).distinct())
    price_cache = {}
    total = 0
    for user in User.objects.filter(id__in=list(user_ids)):
        try:
            total += evaluate_for_user(user, price_cache).get("fired", 0)
        except Exception:
            # One user's bad data must not stop the cron for everyone else.
            continue
    return total
