from django.contrib import admin
from .models import Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "weight", "is_active", "feed_url")
    list_filter = ("source_type", "is_active")
    search_fields = ("name", "url")
