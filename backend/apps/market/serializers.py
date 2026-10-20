from rest_framework import serializers
from .models import Asset


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = [
            "id", "symbol", "name", "category",
            "tradingview_symbol", "binance_symbol",
            "is_watched", "sort_order", "created_at",
        ]
        read_only_fields = ["created_at"]
