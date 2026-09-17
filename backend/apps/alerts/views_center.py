"""Notification centre + alert-rule API.

Every queryset here is filtered by `request.user` on the server. The frontend
also filters for display, but that is presentation only — authorisation is
enforced here so no client can read or mutate another user's notifications or
rules by guessing an id.
"""

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AlertRule, Notification
from .serializers import AlertRuleSerializer, NotificationSerializer

# Sections offered by the notification centre. "all" and "unread" are views over
# the same rows rather than categories, so they are handled separately.
VALID_CATEGORIES = {c[0] for c in Notification.CATEGORIES}


class NotificationViewSet(viewsets.ModelViewSet):
    """List / read / delete the signed-in user's notifications."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "post", "head", "options"]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        params = self.request.query_params

        category = (params.get("category") or "").strip()
        if category in VALID_CATEGORIES:
            qs = qs.filter(category=category)

        if (params.get("unread") or "").lower() in ("1", "true", "yes"):
            qs = qs.filter(read=False)

        return qs.select_related("trade", "rule")

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", 100))))
        except (TypeError, ValueError):
            limit = 100

        rows = self.get_serializer(qs[:limit], many=True).data
        # Counts are computed over the *unfiltered* set so the section tabs can
        # show badges without the client making one request per section.
        base = Notification.objects.filter(user=request.user)
        counts = {"all": base.count(), "unread": base.filter(read=False).count()}
        for cat in VALID_CATEGORIES:
            counts[cat] = base.filter(category=cat).count()

        return Response({"results": rows, "counts": counts})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, read=False).count()
        return Response({"unread": count})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = (Notification.objects
                   .filter(user=request.user, read=False)
                   .update(read=True))
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="clear")
    def clear(self, request):
        """Delete every notification for this user (read ones only by default)."""
        qs = Notification.objects.filter(user=request.user)
        if (request.data.get("scope") or "read") == "read":
            qs = qs.filter(read=True)
        deleted, _ = qs.delete()
        return Response({"deleted": deleted})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        note = self.get_object()
        note.read = bool(request.data.get("read", True))
        note.save(update_fields=["read"])
        return Response(self.get_serializer(note).data)


class AlertRuleViewSet(viewsets.ModelViewSet):
    """CRUD for the signed-in user's position alert rules."""

    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AlertRule.objects.filter(user=self.request.user).select_related("trade")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        rule = self.get_object()
        rule.enabled = not rule.enabled
        rule.save(update_fields=["enabled"])
        # Re-arm the latches so a re-enabled rule can fire on the next crossing.
        rule.states.update(latched=False)
        return Response(self.get_serializer(rule).data)

    @action(detail=False, methods=["get"], url_path="options")
    def options_list(self, request):
        """Vocabulary for the rule builder, so the UI never hard-codes it."""
        return Response({
            "scopes": [{"value": v, "label": l} for v, l in AlertRule.SCOPES],
            "conditions": [
                {
                    "value": v,
                    "label": l,
                    "needs_threshold": v not in AlertRule.NO_THRESHOLD,
                }
                for v, l in AlertRule.CONDITIONS
            ],
        })


# Minimum seconds between two evaluation passes for the same user. The panel
# polls this endpoint while it is open so alerts work even when the cron job is
# not installed; the throttle stops that polling from hammering the market feed.
EVALUATE_MIN_INTERVAL = 20


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def evaluate_now(request):
    """Run this user's rules immediately and report what was checked.

    Two callers:
    * the panel's "Check now" button, and
    * the panel's background poll, which passes auto=1.

    The cron job (`manage.py check_alerts`) remains the driver for users who are
    not looking at the panel. Returning the diagnostics from `evaluate_for_user`
    means an empty notification centre can always be explained: no rules, no
    open trades, or no price from the market feed.
    """
    from .rules import evaluate_for_user

    auto = str(request.data.get("auto") or "").lower() in ("1", "true", "yes")
    cache_key = f"alerts:last-eval:{request.user.id}"

    if auto:
        last = cache.get(cache_key)
        if last and (timezone.now() - last).total_seconds() < EVALUATE_MIN_INTERVAL:
            return Response({"throttled": True, "fired": 0})

    try:
        stats = evaluate_for_user(request.user)
    except Exception as exc:
        return Response({"detail": str(exc)},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    cache.set(cache_key, timezone.now(), 300)
    return Response({**stats, "throttled": False, "checked_at": timezone.now()})
