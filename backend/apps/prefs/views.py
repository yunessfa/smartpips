from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import MarketAccess, RiskLimits

User = get_user_model()
_FIELDS = {"metals": "allow_metals", "spot": "allow_spot", "futures": "allow_futures"}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_access(request):
    """The current user's allowed market groups — the Scalp page filters
    its symbol list with this."""
    return Response(MarketAccess.for_user(request.user).as_dict())


@api_view(["GET"])
@permission_classes([IsAdminUser])
def all_access(request):
    """Admin: one call returns every user's access map {user_id: {...}}."""
    existing = {a.user_id: a.as_dict() for a in MarketAccess.objects.all()}
    default = {"metals": True, "spot": True, "futures": True}
    return Response({str(u.id): existing.get(u.id, dict(default))
                     for u in User.objects.all()})


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def user_access(request, user_id):
    """Admin: toggle groups for one user. Body: any of
    {metals: bool, spot: bool, futures: bool}."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=404)
    access = MarketAccess.for_user(user)
    changed = False
    for key, field in _FIELDS.items():
        if key in request.data:
            setattr(access, field, bool(request.data[key]))
            changed = True
    if changed:
        access.save()
    return Response(access.as_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_limits(request):
    """The current user's risk limits + today's realized real loss (for the
    kill-switch banner)."""
    lim = RiskLimits.for_user(request.user)
    data = lim.as_dict()
    data["today_loss"] = lim.today_realized_loss(request.user)
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def all_limits(request):
    existing = {l.user_id: l.as_dict() for l in RiskLimits.objects.all()}
    default = RiskLimits().as_dict()
    return Response({str(u.id): existing.get(u.id, dict(default))
                     for u in User.objects.all()})


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def user_limits(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=404)
    lim = RiskLimits.for_user(user)
    for field in ("max_leverage", "max_position_usdt", "max_open_positions",
                  "daily_loss_limit_usdt", "real_trading_enabled"):
        if field in request.data:
            val = request.data[field]
            if field == "real_trading_enabled":
                setattr(lim, field, bool(val))
            else:
                try:
                    setattr(lim, field, type(getattr(lim, field))(val))
                except (TypeError, ValueError):
                    return Response({"error": f"invalid value for {field}"}, status=400)
    lim.save()
    return Response(lim.as_dict())
