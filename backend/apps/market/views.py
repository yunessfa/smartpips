from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Asset
from .serializers import AssetSerializer
from .services import get_quotes
from .metals import fetch_metal_price
from .crypto_symbols import SUPPORTED_CRYPTO as ALLOWED_CRYPTO


class AssetViewSet(viewsets.ModelViewSet):
    """CRUD for tracked assets + a /quotes/ action with live prices."""

    queryset = Asset.objects.all()
    serializer_class = AssetSerializer

    @action(detail=False, methods=["get"])
    def quotes(self, request):
        watched = self.get_queryset().filter(is_watched=True)
        return Response(get_quotes(watched))


# Lightweight endpoint polled rapidly by the scalp page for a metal tick.
ALLOWED_METALS = {"XAUUSD", "XAGUSD"}


def _crypto_price(symbol):
    """Live price from Binance spot or USD-M futures (':PERP' suffix)."""
    import requests
    is_perp = symbol.endswith(":PERP")
    base = symbol.replace(":PERP", "")
    if base not in ALLOWED_CRYPTO:
        return None
    host = ("https://fapi.binance.com/fapi/v1/ticker/price" if is_perp
            else "https://api.binance.com/api/v3/ticker/price")
    try:
        r = requests.get(host, params={"symbol": base}, timeout=6)
        r.raise_for_status()
        return float(r.json()["price"])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def metal_price(request):
    symbol = (request.query_params.get("symbol") or "XAUUSD").upper()
    base = symbol.replace(":PERP", "")
    if symbol in ALLOWED_METALS:
        # honour per-user access: a user with metals disabled shouldn't be able
        # to (accidentally, via a stale poller) spend server calls on metals.
        try:
            from apps.prefs.models import MarketAccess
            if not MarketAccess.for_user(request.user).allow_metals:
                return Response({"symbol": symbol, "price": None, "ok": False,
                                 "disabled": True}, status=403)
        except Exception:
            pass
        price = fetch_metal_price(symbol)
    elif base in ALLOWED_CRYPTO:
        price = _crypto_price(symbol)
    else:
        return Response({"error": "Unsupported symbol."}, status=400)
    return Response({"symbol": symbol, "price": price, "ok": price is not None})
