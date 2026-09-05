"""
cTrader OAuth flow.

1) Admin opens /api/ctrader/connect/  -> redirected to cTrader to authorize.
2) cTrader redirects back to /api/ctrader/callback/?code=...  -> we exchange the
   code for access/refresh tokens, fetch the account list, store everything, and
   show a small page listing the accounts so the admin can pick the one to trade.
3) Admin opens /api/ctrader/use/<account_id>/ to select the trading account.

Tokens are stored in the DB (CTraderToken); the bridge service reads them.
"""
import datetime

import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response

from .models import CTraderToken

AUTH_URL = "https://openapi.ctrader.com/apps/auth"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
# REST helper to list accounts for a token (host depends on env, but the web API is shared)
ACCOUNTS_URL = "https://api.spotware.com/connect/tradingaccounts"


@api_view(["GET"])
@permission_classes([IsAdminUser])
def connect(request):
    """Return the URL the admin should open to authorize SmartPips on cTrader."""
    if not settings.CTRADER_CLIENT_ID:
        return Response({"error": "CTRADER_CLIENT_ID not set on the server."}, status=400)
    url = (
        f"{AUTH_URL}?client_id={settings.CTRADER_CLIENT_ID}"
        f"&redirect_uri={settings.CTRADER_REDIRECT_URI}"
        f"&scope=trading"
    )
    return Response({"authorize_url": url})


@api_view(["GET"])
@permission_classes([AllowAny])  # cTrader redirects the browser here (no auth header)
def callback(request):
    """cTrader redirects here with ?code=... — exchange it for tokens."""
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Missing ?code from cTrader.", status=400)

    try:
        resp = requests.get(TOKEN_URL, params={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.CTRADER_REDIRECT_URI,
            "client_id": settings.CTRADER_CLIENT_ID,
            "client_secret": settings.CTRADER_CLIENT_SECRET,
        }, timeout=20)
    except Exception as exc:  # noqa: BLE001 — never 502 the browser
        return HttpResponse(
            f"<html><body style='font-family:sans-serif;padding:24px'>"
            f"<h3>Could not reach cTrader</h3><pre>{exc}</pre></body></html>",
            status=200)

    try:
        data = resp.json()
    except ValueError:
        # not JSON (e.g. 429 rate-limit page) — show the raw response so we can see it
        return HttpResponse(
            f"<html><body style='font-family:sans-serif;padding:24px'>"
            f"<h3>cTrader returned a non-JSON response</h3>"
            f"<p>HTTP status: <b>{resp.status_code}</b></p>"
            f"<pre>{resp.text[:500]}</pre>"
            f"<p>If status is 429 you're rate-limited — wait ~30 min and try once.</p>"
            f"</body></html>", status=200)

    access = data.get("accessToken") or data.get("access_token")
    refresh = data.get("refreshToken") or data.get("refresh_token")
    expires_in = data.get("expiresIn") or data.get("expires_in") or 0
    if not access:
        # show cTrader's actual error (e.g. expired/used code) instead of crashing
        return HttpResponse(
            f"<html><body style='font-family:sans-serif;padding:24px'>"
            f"<h3>No access token returned by cTrader</h3>"
            f"<p>HTTP status: <b>{resp.status_code}</b></p>"
            f"<pre>{data}</pre>"
            f"<p>'expired'/'already used' → click Connect again (don't refresh). "
            f"'ACCESS_DENIED' → wrong secret.</p>"
            f"</body></html>", status=200)

    # SAVE THE TOKEN FIRST — before any risky account-list call.
    token, _ = CTraderToken.objects.get_or_create(id=1)
    token.access_token = access
    token.refresh_token = refresh or token.refresh_token
    if expires_in:
        token.expires_at = timezone.now() + datetime.timedelta(seconds=int(expires_in))
    token.save()

    # fetch the account list (best-effort; never breaks the flow)
    accounts = []
    try:
        a = requests.get(ACCOUNTS_URL, params={"access_token": access}, timeout=15).json()
        accounts = a.get("data") or a if isinstance(a, (list, dict)) else []
        if isinstance(accounts, dict):
            accounts = accounts.get("data", [])
    except Exception:  # noqa: BLE001
        accounts = []
    token.accounts_json = accounts
    if len(accounts) == 1:
        token.account_id = accounts[0].get("traderLogin") or accounts[0].get("accountId")
    token.save()

    rows = ""
    for acc in accounts:
        aid = acc.get("traderLogin") or acc.get("accountId") or acc.get("ctidTraderAccountId")
        broker = acc.get("brokerName", "")
        live = acc.get("live", "")
        rows += (f"<li>account <b>{aid}</b> — {broker} {'(LIVE)' if live else '(demo)'} "
                 f"&nbsp; <a href='/api/ctrader/use/{aid}/'>use this</a></li>")
    # if no accounts came back, let the admin type the account id manually
    manual = ("<p>If your account isn't listed, enter its number (e.g. 9046655):</p>"
              "<form method='get' action='/api/ctrader/use_manual/'>"
              "<input name='account_id' placeholder='9046655' "
              "style='padding:8px;border-radius:6px;border:1px solid #555'/>"
              "<button style='padding:8px 14px;margin-inline-start:8px'>Use this</button></form>")
    html = (
        "<html><body style='font-family:sans-serif;background:#0B0E14;color:#eee;padding:24px'>"
        "<h2>cTrader connected ✅</h2>"
        "<p>Token stored. Pick the account to trade:</p>"
        f"<ul>{rows or '<li>No accounts returned by the API.</li>'}</ul>"
        f"{manual}"
        "</body></html>"
    )
    return HttpResponse(html)


@api_view(["GET"])
@permission_classes([AllowAny])
def use_account(request, account_id):
    token = CTraderToken.objects.filter(id=1).first()
    if not token:
        return HttpResponse("Connect cTrader first.", status=400)
    token.account_id = int(account_id)
    token.save()
    return HttpResponse(
        f"<html><body style='font-family:sans-serif;background:#0B0E14;color:#eee;padding:24px'>"
        f"<h2>Trading account set to {account_id} ✅</h2>"
        f"<p>Now (re)start the bridge service on the server.</p></body></html>")


@api_view(["GET"])
@permission_classes([IsAdminUser])
def status_view(request):
    token = CTraderToken.objects.filter(id=1).first()
    return Response({
        "connected": bool(token and token.is_valid()),
        "account_id": token.account_id if token else None,
        "has_token": bool(token and token.access_token),
        "accounts": token.accounts_json if token else [],
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def use_manual(request):
    """Let the admin type the account id directly if the API didn't list it."""
    account_id = request.GET.get("account_id")
    token = CTraderToken.objects.filter(id=1).first()
    if not token:
        return HttpResponse("Connect cTrader first.", status=400)
    if not account_id or not str(account_id).strip().isdigit():
        return HttpResponse("Provide a numeric account_id.", status=400)
    token.account_id = int(account_id)
    token.save()
    return HttpResponse(
        f"<html><body style='font-family:sans-serif;background:#0B0E14;color:#eee;padding:24px'>"
        f"<h2>Trading account set to {account_id} ✅</h2>"
        f"<p>Now restart the bridge service on the server:</p>"
        f"<pre>sudo systemctl restart smartpips-ctrader</pre></body></html>")
