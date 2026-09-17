from django.contrib import admin
from .models import Trade


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("symbol", "direction", "user", "status", "entry_price", "exit_price", "pnl")
    list_filter = ("status", "direction")
    search_fields = ("symbol", "user__username")
