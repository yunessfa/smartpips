from django.contrib import admin
from .models import ExpiringToken


@admin.register(ExpiringToken)
class ExpiringTokenAdmin(admin.ModelAdmin):
    list_display = ("key", "user", "created", "is_expired")
    readonly_fields = ("key", "created")
