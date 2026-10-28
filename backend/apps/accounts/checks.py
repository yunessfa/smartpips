"""Deployment check for the cookie-based session refresh.

Behind Cloudflare/Nginx, Django sees plain HTTP unless SECURE_PROXY_SSL_HEADER
is set. The browser's refresh POST then carries `Origin: https://…`, Django
expects `http://…`, CSRF rejects it with 403, every access-token expiry looks
like a logout, and users "have to log in again". Either setting fixes it.
"""
from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def refresh_csrf_origin(app_configs, **kwargs):
    if getattr(settings, "DEBUG", False):
        return []
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None) or getattr(settings, "CSRF_TRUSTED_ORIGINS", None):
        return []
    return [Warning(
        "Session refresh will fail with CSRF 403 behind an HTTPS proxy.",
        hint="Set CSRF_TRUSTED_ORIGINS=https://your-domain (and/or USE_PROXY_SSL_HEADER=True).",
        id="smartpips.W001")]
