from rest_framework import serializers
from .models import Indicator, TelegramChannel


class IndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = ["id", "label", "key", "settings", "notes", "is_active", "created_at"]
        read_only_fields = ["created_at"]


class TelegramChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChannel
        fields = ["id", "username", "title", "is_active", "created_at"]
        read_only_fields = ["created_at"]

    def validate_username(self, value):
        return value.lstrip("@").strip()
