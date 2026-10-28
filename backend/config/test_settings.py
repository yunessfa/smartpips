"""Isolated application tests, NOT migration validation.
The supplied trades migration history duplicates columns on clean installs.
Keep this override out of production; validate/fix migrations separately.
"""
from .settings import *  # noqa
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIGRATION_MODULES = {app: None for app in (
    "accounts", "market", "sources", "strategy", "trades", "ai", "chat", "alerts",
    "mt5", "ctrader", "lbank", "bitunix", "prefs")}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REFRESH_COOKIE_SECURE = False

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "10000/min"}}

# Existing legacy fixtures explicitly exercise old sizing; new tests enable v1.
DEMO_RISK_V1_ENABLED = False
