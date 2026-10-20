from rest_framework import serializers
from .models import Trade


class TradeSerializer(serializers.ModelSerializer):
    decision_token = serializers.CharField(required=False, write_only=True, max_length=65536)
    entry_strategy_version = serializers.IntegerField(required=False, min_value=1, write_only=True)
    net_pnl = serializers.ReadOnlyField()
    pnl_basis = serializers.ReadOnlyField()
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
            "fees_paid", "funding_paid", "costs_verified", "execution_verified",
            "external_order_id", "external_position_id", "net_pnl", "pnl_basis",
            "entry_strategy_version", "decision_token", "entry_snapshot", "entry_snapshot_hash",
        ]
        read_only_fields = ["entry_snapshot", "entry_snapshot_hash", "pnl", "pnl_percent", "status", "closed_at", "opened_at",
                           "tp1_done", "tp2_done", "tp3_done", "remaining_pct", "realized_pnl",
                           "strategy_name", "strategy_version", "fees_paid", "funding_paid",
                           "costs_verified", "execution_verified", "external_order_id",
                           "external_position_id", "exit_reason"]

    def validate(self, attrs):
        import math
        for key in ("entry_price", "exit_price", "size", "leverage",
                    "stop_loss", "take_profit", "tp1_price", "tp2_price", "tp3_price"):
            v = attrs.get(key)
            if v is not None and (not math.isfinite(v) or v <= 0):
                raise serializers.ValidationError({key: "Must be finite and positive."})
        for key in ("tp1_pct", "tp2_pct", "tp3_pct"):
            v = attrs.get(key)
            if v is not None and (not math.isfinite(v) or not 0 < v <= 100):
                raise serializers.ValidationError({key: "Must be in (0,100]."})
        if self.instance:
            if "entry_strategy_version" in attrs or "decision_token" in attrs:
                raise serializers.ValidationError("Entry version is immutable.")
            immutable = {"strategy", "timeframe", "confidence", "source", "entry_price",
                         "size", "leverage", "direction", "symbol"}
            if any(getattr(self.instance, key) != attrs[key] for key in immutable.intersection(attrs)):
                raise serializers.ValidationError("Entry attribution and sizing are immutable.")
        return attrs

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
        token = validated_data.pop("decision_token", None)
        analysis = None
        if token:
            from .snapshots import read_token
            analysis = read_token(token, validated_data["user"], validated_data["symbol"])
        strategy = validated_data.get("strategy")
        number = validated_data.pop("entry_strategy_version", None)
        if strategy is not None:
            validated_data["strategy_name"] = strategy.name
            current = (strategy.versions.filter(version=number).first()
                       if number is not None else strategy.current_version())
            if current is None:
                raise serializers.ValidationError("Unknown entry strategy version.")
            validated_data["strategy_version"] = current.version if current else None
        elif number is not None:
            raise serializers.ValidationError("Entry version requires a strategy.")
        if analysis:
            from .snapshots import validate_binding
            validate_binding(analysis, strategy_id=validated_data.get("strategy").pk if validated_data.get("strategy") else None,
                             strategy_version=validated_data.get("strategy_version"), timeframe=validated_data.get("timeframe"))
        obj = Trade(**validated_data)
        obj._entry_analysis = analysis
        obj.save()
        return obj


class CloseTradeSerializer(serializers.Serializer):
    exit_price = serializers.FloatField()

    def validate_exit_price(self, value):
        import math
        if not math.isfinite(value) or value <= 0:
            raise serializers.ValidationError("Must be finite and positive.")
        return value
