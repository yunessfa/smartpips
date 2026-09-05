from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PushSubscription
from .push import send_push, vapid_configured


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vapid_key(request):
    return Response({
        "public_key": settings.VAPID_PUBLIC_KEY,
        "configured": vapid_configured(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscribe(request):
    """Body: { endpoint, keys: { p256dh, auth } } from the browser PushManager."""
    sub = request.data or {}
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return Response({"error": "Invalid subscription."}, status=400)

    obj, _ = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": keys["p256dh"],
            "auth": keys["auth"],
            "enabled": True,
        },
    )
    return Response({"ok": True, "id": obj.id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unsubscribe(request):
    endpoint = (request.data or {}).get("endpoint")
    if endpoint:
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    return Response({
        "configured": vapid_configured(),
        "subscriptions": request.user.push_subscriptions.filter(enabled=True).count(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def test_push(request):
    """Send a test notification to all of the current user's devices."""
    if not vapid_configured():
        return Response({"error": "Push not configured on the server (VAPID keys missing)."},
                        status=400)
    subs = request.user.push_subscriptions.filter(enabled=True)
    if not subs:
        return Response({"error": "No subscriptions for this user yet."}, status=400)
    payload = {"title": "SmartPips", "body": "Test alert — notifications are working ✅",
               "url": "/app/scalp"}
    sent = 0
    errors = []
    for s in subs:
        ok, err = send_push(s, payload, debug=True)
        if ok:
            sent += 1
        elif err:
            errors.append(err)
    return Response({"sent": sent, "total": subs.count(), "errors": errors[:5]})


from apps.market.crypto_symbols import SUPPORTED_CRYPTO
ALLOWED_WATCH = ({"XAUUSD", "XAGUSD"} | SUPPORTED_CRYPTO
                | {f"{s}:PERP" for s in SUPPORTED_CRYPTO})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def watchlist(request):
    """GET: list the user's watched symbols. POST {symbol, min_score?}: add one."""
    from .models import WatchItem
    if request.method == "POST":
        symbol = (request.data.get("symbol") or "").upper()
        if symbol not in ALLOWED_WATCH:
            return Response({"error": "Unsupported symbol."}, status=400)
        min_score = int(request.data.get("min_score") or 68)
        item, _ = WatchItem.objects.update_or_create(
            user=request.user, symbol=symbol,
            defaults={"min_score": max(55, min(90, min_score)), "active": True})
        return Response({"symbol": item.symbol, "min_score": item.min_score, "active": item.active})

    items = request.user.watchlist.all().order_by("symbol")
    return Response([{"symbol": i.symbol, "min_score": i.min_score, "active": i.active}
                     for i in items])


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def watch_remove(request, symbol):
    from .models import WatchItem
    WatchItem.objects.filter(user=request.user, symbol=symbol.upper()).delete()
    return Response({"removed": symbol.upper()})
