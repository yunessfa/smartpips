"""Who is allowed to be notified, and when.

This module exists because of two concrete bugs reported from production use:

1. **Cross-user leakage.** `signal_check.evaluate_and_alert()` ended with a
   bare `broadcast(payload)`. `broadcast()` with no `users=` argument sends to
   EVERY enabled PushSubscription on the server. So the internal notification
   rows were correctly limited to people who watch the symbol, while the
   actual phone buzz went to everyone. That is exactly the reported symptom:
   two colleagues keep separate watchlists, yet gold alerts arrive for the
   person who never added gold.

2. **`min_score` was dead config.** `WatchItem.min_score` was stored, clamped
   and shown in the UI, but never compared against anything, so a user asking
   for "only 80+ setups" still got every flip.

3. **No respect for the daily loss limit.** Once a trader is stopped out for
   the day, more trade signals are worse than useless — they invite revenge
   trading against a limit the system itself is enforcing.

`recipients()` is now the single answer to "who should hear about this
signal", and it answers with an explicit, auditable list — never "everyone".
"""
import logging

from django.contrib.auth import get_user_model

log = logging.getLogger("smartpips.alerts")

# Categories that mean "here is a trade to take". These are the ones muted
# once a user has hit their loss limit. Risk/system/pnl messages still get
# through, because "you have been stopped for the day" is itself a message
# the user must receive.
TRADE_CATEGORIES = frozenset({"signal", "trading"})


def _risk_limits(user):
    try:
        from apps.prefs.models import RiskLimits
        return RiskLimits.for_user(user)
    except Exception:
        log.exception("could not load RiskLimits for user_id=%s", getattr(user, "id", None))
        return None


def loss_limit_state(user):
    """Has this user blown through their loss limit today?

    Returns {"blocked": bool, "reason": str, "lost": float, "limit": float}.

    Two independent guards are consulted, and either one is enough:

    * `RiskLimits.daily_loss_limit_usdt` — the hard, admin-set kill switch
      already enforced on real orders. Reusing it here means the notification
      behaviour and the execution behaviour can never disagree.
    * `strategy.risk.daily_risk_guard` — the softer behavioural guard
      (loss % of balance, consecutive losers). It already existed and already
      returns {"blocked", "reason"}; it just was never wired to alerts.

    Never raises: an error here degrades to "not blocked" so a monitoring bug
    can't silently switch off all alerts for everyone.
    """
    out = {"blocked": False, "reason": "", "lost": 0.0, "limit": 0.0}

    limits = _risk_limits(user)
    if limits is not None:
        try:
            limit = float(limits.daily_loss_limit_usdt or 0)
            if limit > 0:
                lost = float(limits.today_realized_loss(user) or 0)
                out["lost"], out["limit"] = lost, limit
                if lost >= limit:
                    out["blocked"] = True
                    out["reason"] = (f"daily loss limit reached "
                                     f"({lost:.0f}/{limit:.0f} USDT)")
                    return out
        except Exception:
            log.exception("daily_loss_limit check failed for %s", user)

        # An admin switching real trading off is also a "stop trading" signal.
        try:
            if limits.real_trading_enabled is False:
                out["blocked"] = True
                out["reason"] = "real trading disabled for this account"
                return out
        except Exception:
            log.exception("real_trading_enabled check failed for %s", user)

    # Behavioural guard (loss %, consecutive losers).
    try:
        from apps.strategy.risk import daily_risk_guard
        guard = daily_risk_guard(user) or {}
        if guard.get("blocked"):
            out["blocked"] = True
            out["reason"] = guard.get("reason") or "daily risk guard triggered"
    except Exception:
        log.exception("daily_risk_guard check failed for %s", user)

    return out


def trade_alerts_muted(user):
    """True when this user should NOT receive further trade/signal alerts today."""
    return bool(loss_limit_state(user).get("blocked"))


def notify_allowed(user, category="system"):
    """Central yes/no for "may we send this to this user right now?".

    Only trade-shaped categories are gated. Risk, pnl and system messages
    always go through — muting those would hide the very warning that explains
    why the trade alerts stopped.
    """
    if category not in TRADE_CATEGORIES:
        return True
    return not trade_alerts_muted(user)


def watchers(symbol, *, score=None, timeframe=None):
    """Users who explicitly asked to be alerted about `symbol`.

    This is the fix for the leak. The rules are:

    * There must be an ACTIVE `WatchItem` for that exact symbol, owned by that
      user. No watch item -> no notification, full stop. Nobody is ever
      included because they happen to have a push subscription.
    * If a score is supplied it must meet the user's own `min_score`, so two
      people watching the same symbol at different thresholds get genuinely
      different alerts.

    Returns a list of User objects (possibly empty). An empty list must be
    treated as "notify nobody", never as "notify everybody".
    """
    from .models import WatchItem

    symbol = (symbol or "").strip()
    if not symbol:
        return []

    User = get_user_model()

    # Match the plain symbol and its ':PERP' twin, since the watchlist stores
    # both shapes and a user watching "BTCUSDT" means the instrument.
    base = symbol.upper().replace(":PERP", "")
    variants = {base, f"{base}:PERP", symbol.upper()}

    items = (WatchItem.objects
             .filter(active=True, symbol__in=list(variants))
             .select_related("user"))

    allowed_ids = []
    for item in items:
        user = item.user
        if not user or not user.is_active:
            continue

        # Per-user score threshold — previously stored but never enforced.
        if score is not None:
            try:
                if int(score) < int(item.min_score or 0):
                    continue
            except (TypeError, ValueError):
                pass

        allowed_ids.append(user.id)

    if not allowed_ids:
        log.info("no watchers for %s %s — sending nothing",
                 symbol, timeframe or "")
        return []

    return list(User.objects.filter(id__in=allowed_ids, is_active=True))


def recipients(symbol, *, score=None, timeframe=None):
    """Watchers of `symbol`, minus anyone whose loss limit is already hit.

    Returns (users, skipped) where `skipped` is a list of
    {"user", "reason"} for logging/diagnostics, so "why didn't I get an
    alert?" has an answer in the log instead of being a mystery.
    """
    users, skipped = [], []
    for user in watchers(symbol, score=score, timeframe=timeframe):
        state = loss_limit_state(user)
        if state.get("blocked"):
            skipped.append({"user": user, "reason": state.get("reason", "blocked")})
            continue
        users.append(user)

    if skipped:
        log.info("muted %s trade alert for %d user(s): %s", symbol, len(skipped),
                 ", ".join(f"{s['user'].username}({s['reason']})" for s in skipped))
    return users, skipped
