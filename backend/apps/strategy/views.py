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
    from .backtest_data import backtest_inputs, historical_window
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
    candles, data_info = historical_window(symbol, timeframe, with_diagnostics=True)
    result = backtest(symbol, candles, source=src, timeframe=timeframe, version=version)
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    result["candles_used"] = len(candles)
    result["data_quality"] = "candles"
    result["data_diagnostics"] = data_info
    result["strategy"] = strategy.name if strategy else "Base engine"
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
