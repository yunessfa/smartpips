from rest_framework import serializers

from .models import AlertRule, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "category", "level", "title", "body", "url", "symbol",
            "trade", "rule", "meta", "read", "created",
        ]
        # Notifications are raised by the server, never authored by the client.
        read_only_fields = [
            "id", "category", "level", "title", "body", "url", "symbol",
            "trade", "rule", "meta", "created",
        ]


class AlertRuleSerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()

    class Meta:
        model = AlertRule
        fields = [
            "id", "name", "scope", "symbol", "trade", "condition", "threshold",
            "enabled", "push", "once_per_crossing", "trigger_count",
            "last_triggered_at", "created", "description",
        ]
        read_only_fields = ["id", "trigger_count", "last_triggered_at", "created"]

    def get_description(self, obj):
        return obj.describe()

    def validate_symbol(self, value):
        return (value or "").strip().upper()

    def validate_trade(self, value):
        """A rule may only ever point at a trade the requesting user owns.

        Without this check a caller could attach a rule to somebody else's
        trade id and receive notifications describing that position.
        """
        request = self.context.get("request")
        if value is not None and request is not None:
            if value.user_id != request.user.id:
                raise serializers.ValidationError("Unknown trade.")
        return value

    def validate(self, attrs):
        merged = {**getattr(self, "initial_data", {}), **attrs}
        scope = merged.get("scope") or AlertRule.SCOPE_ANY
        condition = merged.get("condition") or "pnl_above"

        if scope == AlertRule.SCOPE_SYMBOL and not (merged.get("symbol") or "").strip():
            raise serializers.ValidationError(
                {"symbol": "Choose a symbol for a symbol-scoped alert."})
        if scope == AlertRule.SCOPE_TRADE and not merged.get("trade"):
            raise serializers.ValidationError(
                {"trade": "Choose a trade for a trade-scoped alert."})

        if condition not in AlertRule.NO_THRESHOLD:
            threshold = merged.get("threshold")
            if threshold in (None, ""):
                raise serializers.ValidationError(
                    {"threshold": "This condition needs a value."})
        return attrs
