"""Send Web-Push messages to stored subscriptions (best-effort)."""
import json

from django.conf import settings


def vapid_configured():
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)


def _vapid_private_key():
    """Return the VAPID private key as a PEM string pywebpush accepts.

    Accepts whatever shape is stored in .env:
      - one-line base64 of DER PKCS8  (what gen_vapid now emits) -> rebuilt to PEM
      - PEM, possibly with escaped '\\n' newlines                -> newlines restored
      - raw base64url 32-byte secret                              -> handed back padded
    """
    key = (settings.VAPID_PRIVATE_KEY or "").strip().strip('"').strip("'")
    if not key:
        return key

    if "BEGIN" in key or "\\n" in key:
        return key.replace("\\n", "\n")

    # try: base64 DER PKCS8 -> load and re-serialize to PEM (most robust)
    try:
        import base64
        from cryptography.hazmat.primitives import serialization
        der = base64.b64decode(key + "=" * ((-len(key)) % 4))
        pk = serialization.load_der_private_key(der, password=None)
        return pk.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    except Exception:
        pass

    # fallback: raw base64url secret -> just fix padding and hope pywebpush groks it
    return key + "=" * ((-len(key)) % 4)


def send_push(subscription, payload: dict, debug=False):
    """Send one push. Returns True on success. Deletes dead subscriptions (410/404).

    When debug=True, returns (ok, error_message) so callers can show why it failed.
    """
    def result(ok, err=""):
        return (ok, err) if debug else ok

    if not vapid_configured():
        return result(False, "VAPID keys not configured on the server")
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return result(False, "pywebpush not installed")
    try:
        claims = {"sub": settings.VAPID_CLAIM_EMAIL}
        if not str(claims["sub"]).startswith("mailto:"):
            claims["sub"] = "mailto:" + str(claims["sub"])
        webpush(
            subscription_info=subscription.as_subscription_info(),
            data=json.dumps(payload),
            vapid_private_key=_vapid_private_key(),
            vapid_claims=claims,
            timeout=10,
        )
        return result(True)
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):  # subscription expired/gone
            subscription.delete()
        return result(False, f"WebPushException status={status}: {exc}")
    except Exception as exc:
        return result(False, f"{type(exc).__name__}: {exc}")


def broadcast(payload: dict, users=None):
    """Send a payload to all enabled subscriptions (optionally a subset of users)."""
    from .models import PushSubscription
    qs = PushSubscription.objects.filter(enabled=True)
    if users is not None:
        qs = qs.filter(user__in=users)
    sent = 0
    for sub in qs.select_related("user"):
        if send_push(sub, payload):
            sent += 1
    return sent
