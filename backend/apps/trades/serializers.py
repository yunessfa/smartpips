from rest_framework import serializers
from .models import Trade


class TradeSerializer(serializers.ModelSerializer):
    # Live unrealised P&L can be computed client-side; here we expose realised.
    class Meta:
        model = Trade
        fields = [
            "id", "symbol", "tradingview_symbol", "direction",
            "entry_price", "exit_price", "take_profit", "stop_loss",
            "tp1_price", "tp1_pct", "tp1_done",
            "tp2_price", "tp2_pct", "tp2_done",
            "tp3_price", "tp3_pct", "tp3_done",
            "remaining_pct", "realized_pnl",
            "size", "leverage", "status", "pnl", "pnl_percent",
            "source", "setup_class", "notes", "opened_at", "closed_at",
            # Attribution + entry context, surfaced in the trade detail view
            # and the journal export. All optional: older trades report blank.
            "strategy", "strategy_name", "strategy_version",
            "timeframe", "confidence", "exit_reason",
        ]
        read_only_fields = ["pnl", "pnl_percent", "status", "closed_at", "opened_at",
                           "tp1_done", "tp2_done", "tp3_done", "remaining_pct", "realized_pnl",
                           "strategy_name", "strategy_version"]

    def validate_strategy(self, value):
        """A trade may only be tagged with a strategy the caller can use.

        Without this check a client could post another user's strategy id and
        pollute somebody else's analytics.
        """
        if value is None:
            return value
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if value.user_id not in (None, getattr(user, "id", None)):
            raise serializers.ValidationError("Unknown strategy.")
        return value

    def create(self, validated_data):
        # Snapshot the strategy's name and version at entry so the journal keeps
        # reading correctly after the strategy is edited, renamed or archived.
        strategy = validated_data.get("strategy")
        if strategy is not None:
            validated_data["strategy_name"] = strategy.name
            current = strategy.current_version()
            validated_data["strategy_version"] = current.version if current else None
        return super().create(validated_data)


class CloseTradeSerializer(serializers.Serializer):
    exit_price = serializers.FloatField()
