"""Admin-only account changes; browser-bound, expiring, single-use OAuth."""
import datetime
import secrets
from urllib.parse import urlencode
import requests
from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from .models import CTraderToken, OAuthAttempt

AUTH_URL = "https://openapi.ctrader.com/apps/auth"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
ACCOUNTS_URL = "https://api.spotware.com/connect/tradingaccounts"
COOKIE = "sp_ctrader_oauth"
SALT = "smartpips.ctrader.oauth.v1"
TTL = 600

@api_view(["GET"])
@permission_classes([IsAdminUser])
def connect(request):
    if not settings.CTRADER_CLIENT_ID:
        return Response({"error": "CTRADER_CLIENT_ID not set on the server."}, status=400)
    nonce = secrets.token_urlsafe(32)
    state = signing.dumps({"user": request.user.pk, "nonce": nonce}, salt=SALT)
    OAuthAttempt.objects.create(nonce=nonce, expires_at=timezone.now() + datetime.timedelta(seconds=TTL))
    response = Response({"authorize_url": AUTH_URL + "?" + urlencode({
        "client_id": settings.CTRADER_CLIENT_ID, "redirect_uri": settings.CTRADER_REDIRECT_URI,
        "scope": "trading", "state": state})})
    response.set_cookie(COOKIE, state, max_age=TTL, httponly=True,
                        secure=request.is_secure(), samesite="Lax", path="/api/ctrader/")
    response["Cache-Control"] = "no-store"
    return response

@api_view(["GET"])
@permission_classes([AllowAny])
def callback(request):
    state = request.GET.get("state", "")
    cookie = request.COOKIES.get(COOKIE, "")
    try:
        if not state or not cookie or not secrets.compare_digest(state, cookie):
            raise ValueError("State mismatch")
        payload = signing.loads(state, salt=SALT, max_age=TTL)
        if not get_user_model().objects.filter(pk=payload["user"], is_active=True, is_staff=True).exists():
            raise ValueError("Admin no longer active")
        code = request.GET.get("code")
        if not code:
            raise ValueError("Missing code")
        if not OAuthAttempt.objects.filter(nonce=payload["nonce"], consumed=False,
                                          expires_at__gt=timezone.now()).update(consumed=True):
            raise ValueError("Already consumed")
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        return HttpResponse("OAuth request invalid or expired. Start Connect again in Admin.", status=400)
    def finish(text, status=200):
        response = HttpResponse(text, status=status, content_type="text/plain; charset=utf-8")
        response.delete_cookie(COOKIE, path="/api/ctrader/")
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
    try:
        response = requests.get(TOKEN_URL, params={"grant_type": "authorization_code", "code": code,
            "redirect_uri": settings.CTRADER_REDIRECT_URI, "client_id": settings.CTRADER_CLIENT_ID,
            "client_secret": settings.CTRADER_CLIENT_SECRET}, timeout=20)
        response.raise_for_status()
        data = response.json()
        access = data.get("accessToken") or data.get("access_token")
        refresh = data.get("refreshToken") or data.get("refresh_token")
        expires = int(data.get("expiresIn") or data.get("expires_in") or 0)
        if not access or expires < 0:
            raise ValueError("Invalid provider payload")
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return finish("cTrader authorization failed. Start Connect again; provider details are not displayed.", 502)
    token, _ = CTraderToken.objects.get_or_create(id=1)
    token.access_token = access
    # Never retain a refresh token/account from a different authorization.
    token.refresh_token = refresh or ""
    token.account_id = None
    token.expires_at = timezone.now() + datetime.timedelta(seconds=expires) if expires else None
    token.accounts_json = []
    token.save()
    try:
        r = requests.get(ACCOUNTS_URL, params={"access_token": access}, timeout=15)
        r.raise_for_status()
        accounts = r.json()
        if isinstance(accounts, dict):
            accounts = accounts.get("data", [])
        if not isinstance(accounts, list):
            accounts = []
        token.accounts_json = [a for a in accounts if isinstance(a, dict)]
        token.save(update_fields=["accounts_json"])
    except (requests.RequestException, ValueError):
        pass
    return finish("cTrader connected. Return to Admin, refresh status and explicitly select the account. No account was auto-selected.")


def _select(request, account_id):
    value = str(account_id or "").strip()
    if not value.isdigit() or not 0 < int(value) <= 9223372036854775807:
        return Response({"error": "Provide a positive numeric account_id."}, status=400)
    token = CTraderToken.objects.filter(id=1).first()
    if not token or not token.access_token:
        return Response({"error": "Connect cTrader first."}, status=400)
    token.account_id = int(value)
    token.save(update_fields=["account_id"])
    return Response({"account_id": token.account_id, "restart_bridge_required": True})

@api_view(["POST"])
@permission_classes([IsAdminUser])
def use_account(request, account_id):
    return _select(request, account_id)

@api_view(["POST"])
@permission_classes([IsAdminUser])
def use_manual(request):
    return _select(request, request.data.get("account_id"))

@api_view(["GET"])
@permission_classes([IsAdminUser])
def status_view(request):
    token = CTraderToken.objects.filter(id=1).first()
    return Response({"connected": bool(token and token.is_valid()),
        "account_id": token.account_id if token else None,
        "has_token": bool(token and token.access_token),
        "accounts": token.accounts_json if token else []})
