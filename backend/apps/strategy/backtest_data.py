"""Shared, validated historical-data boundary for both backtest endpoints."""
import math
import time
import requests
from rest_framework.exceptions import APIException, ValidationError
from apps.market.crypto_symbols import SUPPORTED_CRYPTO
from .backtest import TF_SECONDS


class MarketDataUnavailable(APIException):
    status_code = 503
    default_code = "market_data_unavailable"


def backtest_inputs(source, strategy=None):
    symbol = source.get("symbol") or (
        strategy.symbols[0] if strategy and strategy.symbols
        else "XAUUSD" if strategy and strategy.market == "metals" else "BTCUSDT")
    timeframe = source.get("timeframe") or (
        strategy.timeframes[0] if strategy and strategy.timeframes else "5m")
    if not isinstance(symbol, str) or not isinstance(timeframe, str):
        raise ValidationError({"error": "Symbol and timeframe must be strings."})
    symbol, timeframe = symbol.strip().upper(), timeframe.strip().lower()
    if symbol.replace(":PERP", "") not in ({"XAUUSD", "XAGUSD"} | SUPPORTED_CRYPTO):
        raise ValidationError({"error": "Unsupported symbol.", "code": "invalid_symbol"})
    if timeframe not in TF_SECONDS or timeframe == "3m":
        raise ValidationError({"error": "Unsupported timeframe.", "code": "invalid_timeframe"})
    if strategy:
        market = "metals" if symbol in ("XAUUSD", "XAGUSD") else "crypto"
        if (strategy.market != market
                or (strategy.symbols and symbol not in strategy.symbols)
                or (strategy.timeframes and timeframe not in strategy.timeframes)):
            raise ValidationError({"error": "Symbol/timeframe does not match this strategy.",
                                   "code": "strategy_scope_mismatch"})
    return symbol, timeframe


def historical_window(symbol, timeframe, minimum=62, with_diagnostics=False):
    from apps.market.candles import fetch_candles
    try:
        raw = fetch_candles(symbol, timeframe, limit=500)
    except (requests.RequestException, TimeoutError, ConnectionError) as exc:
        raise MarketDataUnavailable({"error": "Market data provider is unavailable. Try again.",
                                     "code": "market_data_unavailable"}) from exc
    if not raw:
        from apps.market.candles import FETCH_DIAGNOSTICS
        provider = FETCH_DIAGNOSTICS.get(f"{symbol}:{timeframe}", {})
        raise MarketDataUnavailable({"error": "No historical candles received from the market provider.",
                                     "code": "no_data", "provider": provider})
    candles, invalid, open_count = {}, 0, 0
    now, step = time.time(), TF_SECONDS[timeframe]
    for row in raw:
        try:
            values = {k: float(row[k]) for k in ("open", "high", "low", "close")}
            values["volume"] = float(row.get("volume") or 0)
            timestamp = float(row["time"])
            if timestamp > 1e11:
                timestamp /= 1000  # provider JSON may use milliseconds
            if not all(math.isfinite(v) for v in (*values.values(), timestamp)):
                raise ValueError
            if (timestamp <= 0 or min(values[k] for k in ("open", "high", "low", "close")) <= 0
                    or values["volume"] < 0
                    or values["low"] > min(values["open"], values["close"])
                    or values["high"] < max(values["open"], values["close"])):
                raise ValueError
            if timestamp + step > now:
                open_count += 1
                continue
            candles[timestamp] = {"time": timestamp, **values}
        except (TypeError, ValueError, KeyError, OverflowError):
            invalid += 1
    ordered = [candles[t] for t in sorted(candles)]
    if not ordered and invalid:
        raise MarketDataUnavailable({"error": "Historical candle data is malformed.",
                                     "code": "invalid_market_data"})
    received = len(raw)
    gaps = sum(b["time"] - a["time"] != step for a, b in zip(ordered, ordered[1:]))
    # Missing bars are real (including pagination seams). Do not fail an entire
    # 500-bar history because of one gap, and NEVER interpolate candles or let
    # the simulator hold a crypto position across that missing interval.
    if symbol not in ("XAUUSD", "XAGUSD") and gaps:
        segments = []
        for bar in ordered:
            if not segments or bar["time"] - segments[-1][-1]["time"] != step:
                segments.append([])
            segments[-1].append(bar)
        eligible = [segment for segment in segments if len(segment) >= minimum]
        if not eligible:
            raise ValidationError({
                "error": f"Need {minimum} consecutive completed candles; historical data has gaps.",
                "code": "insufficient_contiguous_history", "candles_received": received,
                "longest_segment": max(map(len, segments), default=0),
            })
        ordered = eligible[-1]  # most recent usable contiguous historical window
    if len(ordered) < minimum:
        raise ValidationError({"error": f"Need at least {minimum} completed historical candles.",
                               "code": "insufficient_history",
                               "candles_available": len(ordered)})
    from apps.market.candles import LAST_SOURCE, FETCH_DIAGNOSTICS
    diagnostics = {
        "received": received, "used": len(ordered), "invalid_rows": invalid,
        "open_rows_excluded": open_count, "gaps_detected": gaps,
        "window_start": ordered[0]["time"], "window_end": ordered[-1]["time"],
        "partial_history": bool(invalid or (gaps and len(ordered) < len(candles))),
        "short_window": len(ordered) < 200,
        "source": LAST_SOURCE.get(f"{symbol}:{timeframe}"),
        "provider": FETCH_DIAGNOSTICS.get(f"{symbol}:{timeframe}", {}),
    }
    return (ordered, diagnostics) if with_diagnostics else ordered