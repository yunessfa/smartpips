from rest_framework import serializers
from .models import Trade


class TradeSerializer(serializers.ModelSerializer):
    # Live unrealised P&L can be computed client-side; here we expose realised.
    class Meta:
        model = Trade
        fields = [
            "id", "symbol", "tradingview_symbol", "direction",
            "entry_price", "exit_price", "take_profit", "stop_loss",
            "size", "leverage", "status", "pnl", "pnl_percent",
            "source", "notes", "opened_at", "closed_at",
        ]
        read_only_fields = ["pnl", "pnl_percent", "status", "closed_at", "opened_at"]


class CloseTradeSerializer(serializers.Serializer):
    exit_price = serializers.FloatField()
