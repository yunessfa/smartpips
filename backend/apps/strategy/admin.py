from django.contrib import admin
from .models import Indicator, TelegramChannel


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "settings", "is_active")
    list_filter = ("is_active", "key")


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ("username", "title", "is_active")
    list_filter = ("is_active",)
