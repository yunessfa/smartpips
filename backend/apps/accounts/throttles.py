"""Fixed-scope throttles for sensitive endpoints.

Rates live in settings.DEFAULT_THROTTLE_RATES. These SimpleRateThrottle
subclasses pin a scope so we can attach them to function-based views with
@throttle_classes without relying on a per-view throttle_scope attribute.

Note: uses Django's default cache. For a single gunicorn worker LocMemCache
is fine; with multiple workers switch CACHES to Redis so the counter is
shared (documented in .env.example).
"""
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        # throttle by client IP for anonymous login attempts
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class OrderRateThrottle(SimpleRateThrottle):
    scope = "order"

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated \
            else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
