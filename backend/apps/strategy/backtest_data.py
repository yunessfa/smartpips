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


# Default backtest length per timeframe. A 500-bar window (the old default)
# held ~41 hours of 5m data and produced a handful of trades: pure noise.
DEFAULT_BARS = {"1m": 3000, "5m": 6000, "15m": 6000, "1h": 4000, "4h": 2000}
MIN_REQUEST_BARS, MAX_REQUEST_BARS = 300, 20000


def requested_bars(source, timeframe):
    raw = (source or {}).get("bars")
    if raw in (None, ""):
        return DEFAULT_BARS.get(timeframe, 3000)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({"error": "bars must be a whole number.", "code": "invalid_bars"})
    if not MIN_REQUEST_BARS <= value <= MAX_REQUEST_BARS:
        raise ValidationError({"error": f"bars must be between {MIN_REQUEST_BARS} and {MAX_REQUEST_BARS}.",
                               "code": "invalid_bars"})
    return value


def _clean_series(raw, step):
    out = {}
    for row in raw or []:
        try:
            t = float(row["time"])
            if t > 1e11:
                t /= 1000
            vals = {k: float(row[k]) for k in ("open", "high", "low", "close")}
            if not all(math.isfinite(v) and v > 0 for v in vals.values()):
                continue
            if t + step > time.time():
                continue  # forming bar
            out[t] = {"time": t, **vals, "volume": float(row.get("volume") or 0)}
        except (TypeError, ValueError, KeyError):
            continue
    return [out[t] for t in sorted(out)]


def htf_history(symbol, timeframe, window, labels=("4h", "1h"), warmup=300):
    """Closed higher-timeframe candles covering the backtest window + warm-up.

    The backtester aligns them bar-by-bar (closed HTF bars only), exactly as
    the live engine sees them, instead of resampling a short window.
    """
    from apps.market.candles import fetch_history
    if not window:
        return {}, {}
    span = window[-1]["time"] - window[0]["time"] + TF_SECONDS[timeframe]
    series, info = {}, {}
    for label in labels:
        step = TF_SECONDS[label]
        if step <= TF_SECONDS[timeframe]:
            continue
        need = int(span // step) + warmup + 2
        try:
            raw, meta = fetch_history(symbol, label, need)
        except Exception:
            raw, meta = [], {"error": "fetch failed"}
        rows = _clean_series(raw, step)
        if rows:
            series[label] = rows
        info[label] = {**meta, "used": len(rows)}
    return series, info


def historical_window(symbol, timeframe, minimum=62, with_diagnostics=False, bars=None):
    from apps.market.candles import fetch_candles
    history_info = None
    try:
        raw = []
        if bars:
            from apps.market.candles import fetch_history
            try:
                raw, history_info = fetch_history(symbol, timeframe, bars)
            except Exception:
                raw, history_info = [], {"error": "history fetch failed"}
        if not raw:
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
        "source": (history_info or {}).get("source") or LAST_SOURCE.get(f"{symbol}:{timeframe}"),
        "provider": FETCH_DIAGNOSTICS.get(f"{symbol}:{timeframe}", {}),
        "requested_bars": bars, "history": history_info,
        "days_covered": round((ordered[-1]["time"] - ordered[0]["time"]) / 86400, 1),
    }
    return (ordered, diagnostics) if with_diagnostics else ordered

BACKTEST_MODES = ("safe", "aggressive", "trend")


def run_backtest_request(src, symbol, timeframe, version, runner, **extra):
    """One code path for both backtest endpoints: long history, real HTF
    candles, the requested engine mode (or the strategy's playbook)."""
    from .backtest import uses_playbook
    from .decision import HTF
    mode = str((src or {}).get("mode") or "safe").lower()
    if mode not in BACKTEST_MODES:
        raise ValidationError({"error": "mode must be safe, aggressive or trend.", "code": "invalid_mode"})
    if uses_playbook(None, version):
        mode = "trend"
    bars = requested_bars(src, timeframe)
    candles, data_info = historical_window(symbol, timeframe, with_diagnostics=True, bars=bars)
    labels = set(HTF.get(timeframe, [])) | {"4h", "1h"}
    htf_series, htf_info = htf_history(symbol, timeframe, candles, labels=tuple(sorted(labels)))
    data_info["htf"] = htf_info
    result = runner(symbol, candles, source=src, timeframe=timeframe, version=version,
                    mode=mode, htf_series=htf_series, **extra)
    result["candles_used"] = len(candles)
    result["data_diagnostics"] = data_info
    result["mode"] = mode
    if uses_playbook(mode, version):
        from . import trend_pullback
        result["research_evidence"] = {
            "summary": trend_pullback.RESEARCH["results"].get(timeframe),
            "data": trend_pullback.RESEARCH["data"], "costs": trend_pullback.RESEARCH["costs"],
            "caveats": trend_pullback.RESEARCH["caveats"],
            "validated_timeframes": list(trend_pullback.TIMEFRAMES)}
    return result
