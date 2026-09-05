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
    """Backtest the strategy on recent candles for a symbol/timeframe.

    GET  ?symbol=XAUUSD&timeframe=5m  -> uses real candles (needs TWELVEDATA_KEY)
    POST { symbol, timeframe, tick_series }  -> falls back to tick-built candles
    Reports win rate / profit factor / drawdown over the available window.
    """
    src = request.data if request.method == "POST" else request.query_params
    symbol = (src.get("symbol") or "XAUUSD").upper()
    timeframe = src.get("timeframe") or "5m"

    from apps.market.candles import fetch_candles
    from .backtest import backtest

    candles = fetch_candles(symbol, timeframe, limit=500)
    quality = "candles"
    if not candles:
        ticks = (request.data.get("tick_series") if request.method == "POST" else None) or []
        ticks = [float(t) for t in ticks if isinstance(t, (int, float))][-300:]
        if len(ticks) >= 60:
            candles = []
            for j, p in enumerate(ticks):
                prev = ticks[j - 1] if j > 0 else p
                candles.append({"open": prev, "high": max(prev, p),
                                "low": min(prev, p), "close": p, "volume": 1})
            quality = "ticks"
    if not candles:
        return Response({"trades": 0, "note": "Need more data: set TWELVEDATA_KEY for real "
                         "candles, or keep the Scalp page open ~1 min to gather ticks."})

    result = backtest(symbol, candles, warmup=40 if quality == "ticks" else 60,
                      tick_mode=(quality == "ticks"))
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    result["candles_used"] = len(candles)
    result["data_quality"] = quality
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
