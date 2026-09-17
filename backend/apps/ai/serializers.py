from rest_framework import serializers
from .models import AIProvider


class AIProviderSerializer(serializers.ModelSerializer):
    # Never expose the full key back to the client; show a masked preview.
    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = AIProvider
        fields = [
            "id", "label", "provider_type", "base_url", "model",
            "api_key", "api_key_masked", "temperature", "is_active", "created_at",
        ]
        read_only_fields = ["created_at", "api_key_masked"]
        extra_kwargs = {
            # write-only: clients send a key but never read it back.
            "api_key": {"write_only": True, "required": False},
        }

    def get_api_key_masked(self, obj):
        if not obj.api_key:
            return ""
        if len(obj.api_key) <= 8:
            return "•" * len(obj.api_key)
        return f"{obj.api_key[:4]}{'•' * 8}{obj.api_key[-4:]}"

    def update(self, instance, validated_data):
        # Keep the existing key if the client submits an empty string.
        if validated_data.get("api_key", None) == "":
            validated_data.pop("api_key")
        return super().update(instance, validated_data)
