from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Indicator, TelegramChannel
from .serializers import IndicatorSerializer, TelegramChannelSerializer
from apps.accounts.permissions import IsAdminOrReadOnly
from .services import fetch_channel_messages


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def backtest_view(request):
    """Backtest completed real OHLCV only; tick buffers are not historical bars."""
    src = request.data if request.method == "POST" else request.query_params
    from .backtest_data import backtest_inputs, run_backtest_request
    from .backtest_runner import run_selected as backtest
    from .config_models import Strategy
    strategy = Strategy.objects.filter(user=request.user, is_active=True, archived=False).first()
    version = strategy.current_version() if strategy else None
    if strategy and version is None:
        return Response({"error": "Active strategy has no version.",
                         "code": "invalid_strategy_config"}, status=400)
    if version:
        from .rule_engine import evaluate
        checked = evaluate(version, {})
        if checked.get("code") == "invalid_strategy_config":
            return Response({"error": checked["reason"], "code": checked["code"]}, status=400)
    symbol, timeframe = backtest_inputs(src, strategy)
    result = run_backtest_request(src, symbol, timeframe, version, backtest)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    result["data_quality"] = "candles"
    result["strategy"] = (strategy.name if strategy
                          else "Trend pullback playbook" if result.get("mode") == "trend" else "Base engine")
    result["strategy_id"] = strategy.pk if strategy else None
    result["strategy_version_id"] = version.pk if version else None
    return Response(result)


class IndicatorViewSet(viewsets.ModelViewSet):
    # Indicators are global assistant configuration (see apps.chat.services,
    # which reads every active one to build the prompt), not per-user data.
    # Everyone reads them; only staff may change them.
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer
    permission_classes = [IsAdminOrReadOnly]


class TelegramChannelViewSet(viewsets.ModelViewSet):
    # Global feed configuration, consumed by apps.strategy.services without a
    # user context. Read-only for non-staff.
    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAdminOrReadOnly]

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Fetch a few recent posts to confirm the channel is readable."""
        channel = self.get_object()
        messages = fetch_channel_messages(channel.username, limit=3)
        return Response({"ok": bool(messages), "messages": messages})


OVERVIEW_DEFAULT = ("BTCUSDT:PERP", "ETHUSDT:PERP", "SOLUSDT:PERP")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def market_overview(request):
    """Validated-playbook brief for a few crypto futures (dashboard card).

    Same decide() path as the Scalp page in "trend" mode, without a user (no
    personal strategy/risk sizing). Results are cached per closed candle.
    """
    from django.core.cache import cache
    from apps.market.crypto_symbols import SUPPORTED_CRYPTO
    from .decision import decide
    from . import trend_pullback
    timeframe = (request.query_params.get("tf") or "1h").lower()
    if timeframe not in trend_pullback.TIMEFRAMES:
        return Response({"error": "Unsupported timeframe.", "code": "invalid_timeframe"}, status=400)
    raw = request.query_params.get("symbols")
    symbols = [s.strip().upper() for s in raw.split(",")] if raw else list(OVERVIEW_DEFAULT)
    symbols = [s if s.endswith(":PERP") else f"{s}:PERP" for s in symbols if s][:6]
    rows = []
    step = trend_pullback.TF_SECONDS[timeframe]
    import time as _t
    bucket = int(_t.time()) // step
    for symbol in symbols:
        if symbol.replace(":PERP", "") not in SUPPORTED_CRYPTO:
            rows.append({"symbol": symbol, "error": "unsupported"})
            continue
        key = f"overview:{symbol}:{timeframe}:{bucket}"
        row = cache.get(key)
        if row is None:
            try:
                d = decide(symbol, timeframe, mode="trend", brief=True)
                row = {k: d.get(k) for k in ("signal", "entry", "stop_loss", "take_profit", "entry_plan",
                                             "brief", "data_quality", "price_at_signal")}
            except Exception:
                import logging
                logging.getLogger("smartpips.strategy").exception("overview failed for %s", symbol)
                row = {"error": "unavailable"}
            if not row.get("error"):
                cache.set(key, row, min(step, 300))
        rows.append({"symbol": symbol, "timeframe": timeframe, **row})
    return Response({"timeframe": timeframe, "results": rows})
