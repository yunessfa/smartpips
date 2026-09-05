"""REAL order flow from cTrader ticks.

For crypto we get true volume from Binance. For metals (XAUUSD/XAGUSD) the
cTrader bridge streams live ticks into MT5Tick; this module turns those ticks
into a real buy/sell pressure + delta reading, instead of the candle-derived
approximation. If no ticks are available yet it returns None and the engine
falls back to its candle-based order flow.
"""
from datetime import timedelta

from django.utils import timezone


def real_order_flow(symbol, lookback_seconds=900):
    """Return {bias, buy_pressure, sell_pressure, delta, ticks} from stored ticks,
    or None if we don't have enough real ticks yet."""
    try:
        from apps.mt5.models import MT5Tick
    except Exception:
        return None

    since = timezone.now() - timedelta(seconds=lookback_seconds)
    ticks = list(MT5Tick.objects.filter(symbol=symbol.upper(), ts__gte=since)
                 .order_by("ts").values_list("tick_dir", flat=True))
    if len(ticks) < 30:
        return None  # not enough real data; caller uses candle-based flow

    up = sum(1 for d in ticks if d > 0)
    down = sum(1 for d in ticks if d < 0)
    total = up + down
    if total == 0:
        return None

    buy_pressure = round(up / total * 100, 1)
    sell_pressure = round(down / total * 100, 1)
    delta = up - down
    # bias: needs a clear lean, not a coin-flip
    if buy_pressure >= 58:
        bias = 1
    elif sell_pressure >= 58:
        bias = -1
    else:
        bias = 0

    return {
        "bias": bias,
        "buy_pressure": buy_pressure,
        "sell_pressure": sell_pressure,
        "delta": delta,
        "ticks": total,
        "source": "ctrader_ticks",
    }
