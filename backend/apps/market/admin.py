from django.contrib import admin
from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "category", "is_watched", "sort_order")
    list_filter = ("category", "is_watched")
    search_fields = ("symbol", "name")
