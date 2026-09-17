from django.contrib import admin
from .models import AIProvider


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    list_display = ("label", "provider_type", "model", "is_active")
    list_filter = ("provider_type", "is_active")
