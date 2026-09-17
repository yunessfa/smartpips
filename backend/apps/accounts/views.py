import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from .throttles import LoginRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import ExpiringToken
from .settings_store import (
    DEFAULTS,
    REGISTRATION_ENABLED,
    all_settings,
    public_settings,
    registration_enabled,
    set_setting,
)

# Credential changes and data wipes are the two most sensitive actions in the
# app, so they are logged with the actor and the target. "Who reset my data?"
# needs an answer that does not depend on anyone's memory.
log = logging.getLogger("smartpips.accounts")


def _issue_token(user):
    # One token PER LOGIN (per device) — logging in elsewhere no longer kicks you out.
    token = ExpiringToken.objects.create(user=user)
    # Tidy up any expired tokens for this user so the table doesn't grow forever.
    for t in ExpiringToken.objects.filter(user=user):
        if t.is_expired:
            t.delete()
    return {
        "token": token.key,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_staff or user.is_superuser,
        "expires_in": settings.TOKEN_TTL_SECONDS,
        "expires_at": token.expires_at.isoformat(),
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    # Allow logging in with email as well as username.
    if username and "@" in username:
        match = User.objects.filter(email__iexact=username).first()
        if match:
            username = match.username
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({"error": "Invalid username or password."},
                        status=status.HTTP_401_UNAUTHORIZED)
    if not user.is_active:
        return Response({"error": "This account is disabled."},
                        status=status.HTTP_403_FORBIDDEN)
    return Response(_issue_token(user))


@api_view(["GET"])
@permission_classes([AllowAny])
def public_config_view(request):
    """Anonymous-safe system flags, read by /register before rendering a form.

    Only the switches the sign-up page needs are exposed here; the admin view
    below returns the full set and requires staff.
    """
    return Response(public_settings())


@api_view(["GET", "PATCH"])
@permission_classes([IsAdminUser])
def system_settings_view(request):
    """Read (staff) or change (super admin only) the system switches.

    Writing is restricted to superusers rather than any staff member: turning
    registration off is closer to an owner-level action than day-to-day user
    administration, and the brief asks for it to be a Super Admin control.
    """
    if request.method == "GET":
        data = all_settings()
        data["can_edit"] = bool(request.user.is_superuser)
        return Response(data)

    if not request.user.is_superuser:
        return Response({"error": "Only a super admin can change system settings."},
                        status=status.HTTP_403_FORBIDDEN)

    unknown = [k for k in request.data if k not in DEFAULTS]
    if unknown:
        return Response({"error": f"Unknown setting(s): {', '.join(unknown)}."},
                        status=status.HTTP_400_BAD_REQUEST)

    for key in DEFAULTS:
        if key in request.data:
            set_setting(key, bool(request.data[key]), user=request.user)

    data = all_settings()
    data["can_edit"] = True
    return Response(data)


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    # Server-side gate. The frontend also hides the form, but that is only a
    # courtesy: this check is what actually closes sign-ups, because the
    # endpoint is reachable directly. Existing users can still sign in --- this
    # only blocks account CREATION, and never affects admin_users() below, so
    # an administrator can still add accounts by hand while sign-up is closed.
    if not registration_enabled():
        return Response(
            {"error": "New user registration is currently disabled.",
             "code": "registration_disabled"},
            status=status.HTTP_403_FORBIDDEN,
        )
    username = (request.data.get("username") or "").strip()
    email = (request.data.get("email") or "").strip()
    password = request.data.get("password") or ""
    if not username or not password:
        return Response({"error": "Username and password are required."},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 6:
        return Response({"error": "Password must be at least 6 characters."},
                        status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({"error": "That username is taken."},
                        status=status.HTTP_400_BAD_REQUEST)
    if email and User.objects.filter(email__iexact=email).exists():
        return Response({"error": "That email is already registered."},
                        status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(username=username, password=password, email=email)
    return Response(_issue_token(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    # Only sign out THIS device (delete the current token), not all sessions.
    if request.auth:
        ExpiringToken.objects.filter(key=request.auth.key).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    auth = request.auth
    return Response({
        "username": request.user.username,
        "email": request.user.email,
        "is_admin": request.user.is_staff or request.user.is_superuser,
        # Exposed so the admin UI can show super-admin-only controls (password
        # / username takeover, data reset) instead of offering actions the
        # server would refuse with a 403. The server check is still the real
        # boundary; this only avoids dead buttons.
        "is_superuser": request.user.is_superuser,
        "expires_at": auth.expires_at.isoformat() if auth else None,
    })


# ----------------------------- Admin user management -----------------------------
def _user_dict(u):
    return {
        "id": u.id, "username": u.username, "email": u.email,
        "is_active": u.is_active, "is_admin": u.is_staff or u.is_superuser,
        # is_admin conflates staff and superuser; the UI needs to tell them
        # apart so it can refuse to let a staff admin reset a super-admin.
        "is_superuser": u.is_superuser,
        "date_joined": u.date_joined.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def admin_users(request):
    """List users (GET) or create a user (POST {username,email,password,is_admin})."""
    if request.method == "GET":
        return Response([_user_dict(u) for u in User.objects.order_by("-date_joined")])

    username = (request.data.get("username") or "").strip()
    email = (request.data.get("email") or "").strip()
    password = request.data.get("password") or ""
    make_admin = bool(request.data.get("is_admin"))
    if not username or not password:
        return Response({"error": "Username and password are required."}, status=400)
    if len(password) < 6:
        return Response({"error": "Password must be at least 6 characters."}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({"error": "That username is taken."}, status=400)
    if email and User.objects.filter(email__iexact=email).exists():
        return Response({"error": "That email is already registered."}, status=400)
    user = User.objects.create_user(username=username, password=password, email=email)
    if make_admin:
        user.is_staff = True
        user.save()
    return Response(_user_dict(user), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def admin_user_detail(request, user_id):
    """Update or delete a user.

    Staff admins may activate/deactivate, toggle admin and edit email.
    Changing a USERNAME or a PASSWORD is restricted to super-admins, because
    either one is a full account takeover of another person.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=404)

    if request.method == "DELETE":
        if user.id == request.user.id:
            return Response({"error": "You can't delete yourself."}, status=400)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    if "is_active" in request.data:
        if user.id == request.user.id:
            return Response({"error": "You can't disable yourself."}, status=400)
        user.is_active = bool(request.data["is_active"])
        if not user.is_active:
            ExpiringToken.objects.filter(user=user).delete()  # force logout everywhere
    if "is_admin" in request.data:
        user.is_staff = bool(request.data["is_admin"])
    # ---- username takeover (super-admin only) ----
    new_username = (request.data.get("username") or "").strip()
    if new_username and new_username != user.username:
        if not request.user.is_superuser:
            return Response({"error": "Only a super-admin can change a username."},
                            status=403)
        if len(new_username) < 3:
            return Response({"error": "Username must be at least 3 characters."},
                            status=400)
        # iexact + exclude(self): Django usernames are case-sensitive, so a
        # plain exact check would happily create "Ali" next to "ali" and make
        # logins ambiguous.
        if User.objects.filter(username__iexact=new_username).exclude(id=user.id).exists():
            return Response({"error": "That username is already taken."}, status=400)
        old_username = user.username
        user.username = new_username
        # The old session should not survive an identity change.
        ExpiringToken.objects.filter(user=user).delete()
        log.warning("super-admin %s renamed user %s -> %s",
                    request.user.username, old_username, new_username)

    # ---- password takeover (super-admin only) ----
    if request.data.get("password"):
        if not request.user.is_superuser:
            return Response({"error": "Only a super-admin can set a password."},
                            status=403)
        if len(request.data["password"]) < 6:
            return Response({"error": "Password must be at least 6 characters."}, status=400)
        user.set_password(request.data["password"])
        # Force every existing device to re-login with the new password,
        # otherwise an old token keeps working and the "reset" is cosmetic.
        ExpiringToken.objects.filter(user=user).delete()
        log.warning("super-admin %s changed the password for user %s",
                    request.user.username, user.username)
    if "email" in request.data:
        user.email = (request.data.get("email") or "").strip()
    user.save()
    return Response(_user_dict(user))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_user_reset(request, user_id):
    """Super-admin only: wipe a user's data so they start from scratch.

    Deletes their trades, notifications, alert rules, watchlist, push
    subscriptions, market access, risk limits and tokens. The ACCOUNT itself
    survives — same username, same password — because the point is a clean
    slate, not a deletion.

    Wrapped in a transaction: a half-wiped user (trades gone, alert rules
    still firing against them) would be worse than either extreme.
    """
    if not request.user.is_superuser:
        return Response({"error": "Only a super-admin can reset a user's data."},
                        status=403)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=404)

    # Guard against wiping the account you are using to do the wiping.
    if user.id == request.user.id:
        return Response({"error": "You can't reset your own data."}, status=400)

    from apps.alerts.models import (AlertRule, Notification, PushSubscription,
                                    WatchItem)
    from apps.prefs.models import MarketAccess, RiskLimits
    from apps.trades.models import Trade

    removed = {}

    def _wipe(label, qs):
        count = qs.count()
        if count:
            qs.delete()
        removed[label] = count

    with transaction.atomic():
        _wipe("trades", Trade.objects.filter(user=user))
        _wipe("notifications", Notification.objects.filter(user=user))
        # AlertRuleState rows cascade from AlertRule, so they need no pass.
        _wipe("alert_rules", AlertRule.objects.filter(user=user))
        _wipe("watchlist", WatchItem.objects.filter(user=user))
        _wipe("push_subscriptions", PushSubscription.objects.filter(user=user))
        _wipe("market_access", MarketAccess.objects.filter(user=user))
        _wipe("risk_limits", RiskLimits.objects.filter(user=user))
        # Log them out last: defaults are recreated on next login.
        _wipe("tokens", ExpiringToken.objects.filter(user=user))

    log.warning("super-admin %s RESET all data for user %s: %s",
                request.user.username, user.username, removed)

    return Response({"ok": True, "user": _user_dict(user), "removed": removed})
