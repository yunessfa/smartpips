import binascii
import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExpiringToken(models.Model):
    """A bearer token that expires after settings.TOKEN_TTL_SECONDS (1 day)."""

    key = models.CharField(max_length=40, primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="auth_token", on_delete=models.CASCADE
    )
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @staticmethod
    def generate_key():
        return binascii.hexlify(os.urandom(20)).decode()

    @property
    def expires_at(self):
        return self.created + timedelta(seconds=settings.TOKEN_TTL_SECONDS)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return self.key
