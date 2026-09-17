"""Serializers for the configurable strategy layer.

Validation lives in `rule_schema` rather than here so the same rules apply to
any other caller (management commands, future importers) and so a malformed
JSON blob can never reach the database through a different door.
"""

from rest_framework import serializers

from .config_models import Strategy, StrategyVersion
from .rule_schema import RuleError, validate_risk, validate_rules, validate_weights


class StrategyVersionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)

    class Meta:
        model = StrategyVersion
        fields = [
            "id", "version", "label", "rules", "weights", "min_confidence",
            "risk", "backtest", "backtest_at", "notes", "created",
        ]
        read_only_fields = ["id", "version", "label", "backtest", "backtest_at", "created"]

    def validate(self, attrs):
        try:
            if "rules" in attrs:
                attrs["rules"] = validate_rules(attrs["rules"])
            if "weights" in attrs:
                attrs["weights"] = validate_weights(attrs["weights"])
            if "risk" in attrs:
                attrs["risk"] = validate_risk(attrs["risk"])
        except RuleError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        confidence = attrs.get("min_confidence")
        if confidence is not None and not (0 <= float(confidence) <= 100):
            raise serializers.ValidationError(
                {"min_confidence": "Minimum confidence must be between 0 and 100."})
        return attrs


class StrategySerializer(serializers.ModelSerializer):
    is_preset = serializers.BooleanField(read_only=True)
    current = StrategyVersionSerializer(source="current_version", read_only=True)
    version_count = serializers.SerializerMethodField()
    can_activate = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = [
            "id", "name", "description", "market", "symbols", "timeframes",
            "direction", "is_active", "archived", "is_preset", "preset_key",
            "current", "version_count", "can_activate", "created", "updated",
        ]
        read_only_fields = ["id", "is_active", "is_preset", "preset_key",
                            "created", "updated"]

    def get_version_count(self, obj):
        return obj.versions.count()

    def get_can_activate(self, obj):
        """A version must be backtested before it can go live.

        Presets ship pre-vetted, so they are always activatable; user strategies
        have to prove themselves against history first.
        """
        if obj.is_preset:
            return True
        current = obj.current_version()
        return bool(current and current.backtest_at)

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A strategy needs a name.")
        return value

    def validate_symbols(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Symbols must be a list.")
        return [str(s).strip().upper() for s in value if str(s).strip()][:40]

    def validate_timeframes(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Timeframes must be a list.")
        return [str(t).strip().lower() for t in value if str(t).strip()][:12]


class StrategyWriteSerializer(StrategySerializer):
    """Accepts the version payload inline so the builder can save in one call."""

    rules = serializers.JSONField(required=False)
    weights = serializers.JSONField(required=False)
    risk = serializers.JSONField(required=False)
    min_confidence = serializers.FloatField(required=False)
    version_notes = serializers.CharField(required=False, allow_blank=True, max_length=200)

    class Meta(StrategySerializer.Meta):
        fields = StrategySerializer.Meta.fields + [
            "rules", "weights", "risk", "min_confidence", "version_notes",
        ]

    def validate(self, attrs):
        try:
            if "rules" in attrs:
                attrs["rules"] = validate_rules(attrs["rules"])
            if "weights" in attrs:
                attrs["weights"] = validate_weights(attrs["weights"])
            if "risk" in attrs:
                attrs["risk"] = validate_risk(attrs["risk"])
        except RuleError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        confidence = attrs.get("min_confidence")
        if confidence is not None and not (0 <= float(confidence) <= 100):
            raise serializers.ValidationError(
                {"min_confidence": "Minimum confidence must be between 0 and 100."})
        return attrs
