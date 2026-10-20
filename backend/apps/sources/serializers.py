from rest_framework import serializers
from .models import Source


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = [
            "id", "name", "url", "feed_url", "source_type",
            "description", "weight", "is_active", "created_at",
        ]
        read_only_fields = ["created_at"]
