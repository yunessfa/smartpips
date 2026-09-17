"""
Dynamic risk management for the decision engine.

Two jobs:
  1) position_size() — turn "risk X% of my balance" + the stop distance into an
     actual lot size, so the user isn't guessing volume.
  2) daily_risk_guard() — stop suggesting new trades once the user has hit a daily
     loss limit or a max-consecutive-losses rule ("stop after N losses").

Gold (XAUUSD): 1 lot = 100 oz, so $1 price move = $100 per lot. We use that to
convert risk dollars into lots. For silver (XAGUSD): 1 lot = 5000 oz.
"""
from datetime import timezone

CONTRACT_SIZE = {"XAUUSD": 100.0, "XAGUSD": 5000.0,
                 # crypto: 1 "lot" = 1 coin, so $1 move = $1 per unit
                 "BTCUSDT": 1.0, "ETHUSDT": 1.0, "SOLUSDT": 1.0, "BNBUSDT": 1.0}


def suggest_leverage(symbol, entry, stop_loss, regime="normal"):
    """Suggest a SAFE leverage for futures/CFD trading based on how far the stop is.

    Rule of thumb: leverage should let the stop-loss represent a controlled chunk of
    margin, never a blow-up. Tighter stops can take a bit more leverage; wider stops
    (high volatility) get less. This is a conservative guide, not a maximiser.
    """
    if not entry or stop_loss is None:
        return None
    stop_pct = abs(entry - stop_loss) / entry * 100  # stop distance in %
    if stop_pct <= 0:
        return None
    base = symbol.upper().replace(":PERP", "")
    is_crypto = base.endswith("USDT")

    # we want the stop to cost at most ~10% of margin at the suggested leverage
    raw = 10.0 / stop_pct
    # volatility + asset caps (crypto is wilder -> cap lower)
    cap = 10 if is_crypto else 30
    if regime == "high":
        cap = max(3, cap // 2)
    lev = max(1, min(cap, int(raw)))
    return {"leverage": lev, "stop_pct": round(stop_pct, 2),
            "note": "conservative — based on stop distance"}


def used_crypto_margin(user, exclude_trade_id=None, sources=None):
    """Sum of `size` (= margin in USD for crypto trades) across the user's
    currently OPEN crypto positions.

    `sources` scopes the sum so demo and real capital don't contaminate each
    other: passing {"bitunix_real"} counts only real committed margin, while
    the sizing engine (manual/assistant/demo journal) passes the non-real set.
    Previously everything was summed together, so open DEMO positions shrank
    the size of REAL signals (and vice-versa) — a real money-affecting bug.
    """
    from apps.trades.models import Trade
    qs = Trade.objects.filter(user=user, status="open")
    if exclude_trade_id:
        qs = qs.exclude(id=exclude_trade_id)
    if sources is not None:
        qs = qs.filter(source__in=list(sources))
    total = 0.0
    for t in qs:
        base = (t.symbol or "").upper().replace(":PERP", "")
        if base.endswith("USDT"):
            total += (t.size or 0)
    return round(total, 2)


# the sizing engine (scalp signal / journal) reasons about NON-real capital;
# real Bitunix margin is checked separately against the live exchange balance.
NON_REAL_SOURCES = {"manual", "assistant", "bitunix_demo"}


def position_size(symbol, balance, risk_pct, entry, stop_loss, leverage=None):
    """Size a position so that hitting the stop loses ~risk_pct of balance.

    The OUTPUT shape depends on the instrument:
      - metals (XAUUSD/XAGUSD): expressed in LOTS (MetaTrader-style).
      - crypto (BTCUSDT etc):   expressed in COIN QUANTITY + position value +
        required margin, the way a crypto exchange (LBank/Binance) shows it.
        No "lots" — that concept doesn't exist on a crypto exchange.
    """
    if not balance or not entry or stop_loss is None:
        return None
    stop_dist = abs(entry - stop_loss)
    if stop_dist <= 0:
        return None

    base = symbol.upper().replace(":PERP", "")
    is_crypto = base.endswith("USDT")
    risk_dollars = balance * (risk_pct / 100.0)

    if is_crypto:
        # On crypto, 1 unit = 1 coin. Loss at stop per coin = stop_dist (in USDT).
        qty = risk_dollars / stop_dist
        # sensible rounding per asset price scale
        if entry >= 1000:        # BTC
            qty = round(qty, 4)
        elif entry >= 100:       # ETH, BNB, SOL-ish
            qty = round(qty, 3)
        else:
            qty = round(qty, 2)
        position_value = round(qty * entry, 2)
        margin = round(position_value / leverage, 2) if leverage else position_value
        return {
            "mode": "crypto",
            "quantity": qty,                     # how many coins to buy/sell
            "unit": base.replace("USDT", ""),    # e.g. "BTC"
            "position_value": position_value,    # notional in USDT
            "margin": margin,                    # actual money tied up (with leverage)
            "leverage": leverage,
            "risk_dollars": round(risk_dollars, 2),
            "stop_distance": round(stop_dist, 3),
            "risk_pct": risk_pct,
        }

    # ---- metals: MetaTrader lots ----
    contract = CONTRACT_SIZE.get(base, 100.0)
    loss_per_lot = stop_dist * contract
    if loss_per_lot <= 0:
        return None
    raw_lots = risk_dollars / loss_per_lot
    min_lot, max_lot, step = 0.01, 100.0, 0.01
    lots = max(min_lot, min(max_lot, (int(raw_lots / step) * step)))
    return {
        "mode": "lots",
        "lots": round(lots, 2),
        "risk_dollars": round(risk_dollars, 2),
        "stop_distance": round(stop_dist, 3),
        "loss_per_lot": round(loss_per_lot, 2),
        "risk_pct": risk_pct,
    }


def daily_risk_guard(user, max_daily_loss_pct=5.0, max_consecutive_losses=3,
                     balance=None):
    """Check the user's CLOSED trades today against risk limits.

    Returns {blocked: bool, reason: str}. Used to stop new suggestions after a bad
    day so the user doesn't revenge-trade.
    """
    from django.utils import timezone as djtz
    today = djtz.now().astimezone(timezone.utc).date()

    closed_today = [t for t in user.trades.filter(status="closed").exclude(pnl=None)
                    if t.opened_at and t.opened_at.astimezone(timezone.utc).date() == today]
    if not closed_today:
        return {"blocked": False, "reason": ""}

    day_pnl = sum(t.pnl or 0 for t in closed_today)
    if balance and day_pnl < 0 and abs(day_pnl) >= balance * (max_daily_loss_pct / 100.0):
        return {"blocked": True,
                "reason": f"daily loss limit hit ({max_daily_loss_pct}% of balance)"}

    # consecutive losses (most recent first)
    streak = 0
    for t in sorted(closed_today, key=lambda x: x.opened_at, reverse=True):
        if (t.pnl or 0) < 0:
            streak += 1
        else:
            break
    if streak >= max_consecutive_losses:
        return {"blocked": True,
                "reason": f"{streak} losses in a row today — take a break"}

    return {"blocked": False, "reason": ""}
