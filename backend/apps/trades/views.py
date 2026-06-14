from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Trade
from .serializers import TradeSerializer, CloseTradeSerializer


class TradeViewSet(viewsets.ModelViewSet):
    serializer_class = TradeSerializer

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        trade = self.get_object()
        ser = CloseTradeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        trade.close(ser.validated_data["exit_price"])
        return Response(TradeSerializer(trade).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        closed = [t for t in qs if t.status == "closed" and t.pnl is not None]
        wins = [t for t in closed if t.pnl > 0]
        total_pnl = round(sum(t.pnl for t in closed), 2)
        win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
        return Response(
            {
                "open": qs.filter(status="open").count(),
                "closed": len(closed),
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "wins": len(wins),
                "losses": len(closed) - len(wins),
            }
        )
