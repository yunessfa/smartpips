from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .client import LBankClient, LBankFuturesClient, LBankError


def _spot():
    return LBankClient()


def _futures():
    return LBankFuturesClient()


# ---------------------------------------------------------------- status ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    """Is LBank configured, and does a real signed call succeed?"""
    client = _spot()
    if not client.configured:
        return Response({"configured": False, "connected": False,
                         "message": "LBANK_API_KEY / LBANK_SECRET_KEY not set in .env."})
    try:
        client.test_connection()
        return Response({"configured": True, "connected": True})
    except Exception as exc:  # noqa: BLE001 — never 500 the browser over this
        return Response({"configured": True, "connected": False, "error": str(exc),
                         "diagnostics": client.diagnostics()})


# --------------------------------------------------------------- balance ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def balance_view(request):
    """Normalized spot balances: {uid, canTrade, balances:[{asset,free,locked,total}]}."""
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response(client.account_info())
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


# ---------------------------------------------------------------- orders ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def orders_view(request):
    """Order history for a symbol, e.g. ?symbol=btc_usdt . Normalized list."""
    symbol = (request.query_params.get("symbol") or "btc_usdt").lower()
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response(client.order_history(symbol))
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def open_orders_view(request):
    symbol = (request.query_params.get("symbol") or "btc_usdt").lower()
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response(client.open_orders(symbol))
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def trades_view(request):
    """Actual executed fills (true 'past trades') for a symbol.
    Optional ?start=yyyy-MM-dd&end=yyyy-MM-dd (window <= 2 days)."""
    symbol = (request.query_params.get("symbol") or "btc_usdt").lower()
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response({"trades": client.transaction_history(symbol, start, end)})
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


# ------------------------------------------------------------ place order ----
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order_view(request):
    """Place a REAL spot order. Requires explicit confirm=true — this moves
    real money, so we never fire it from a stray request."""
    if not request.data.get("confirm"):
        return Response({"error": "Missing confirm=true — refusing to place a real order."},
                        status=400)
    symbol = request.data.get("symbol")
    order_type = request.data.get("type")   # buy | sell | buy_market | sell_market
    price = request.data.get("price")
    amount = request.data.get("amount")
    if not symbol or not order_type:
        return Response({"error": "symbol and type are required."}, status=400)
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response({"raw": client.place_order(symbol, order_type, price, amount)})
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order_view(request):
    symbol = request.data.get("symbol")
    order_id = request.data.get("orderId") or request.data.get("order_id")
    if not symbol or not order_id:
        return Response({"error": "symbol and orderId are required."}, status=400)
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        return Response({"raw": client.cancel_order(symbol, order_id)})
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


# --------------------------------------------------------------- futures ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def futures_market_view(request):
    """Public futures market data (no auth needed on LBank's side)."""
    client = _futures()
    try:
        return Response({"market": client.market_data()})
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def futures_account_view(request):
    """Read-only futures account. Returns LBank's raw data body."""
    client = _futures()
    if not client.configured:
        return Response({"configured": False, "error": "LBank not configured."}, status=400)
    try:
        return Response({"account": client.account()})
    except LBankError as exc:
        # read-only: surface the error but don't 500
        return Response({"error": str(exc)}, status=502)


# --------------------------------------------------------- debug (compat) ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def debug_signatures_view(request):
    """Kept for the frontend's disconnected-state diagnostic. The signing bug
    is fixed, so this simply runs the one correct HmacSHA256 variant against a
    real call and reports it in the shape the UI expects."""
    client = _spot()
    if not client.configured:
        return Response({"error": "LBank not configured."}, status=400)
    try:
        client.test_connection()
        return Response({"results": [{"variant": "hmac_md5upper_lower",
                                      "ok": True, "detail": "connected"}]})
    except Exception as exc:  # noqa: BLE001
        return Response({"results": [{"variant": "hmac_md5upper_lower",
                                      "ok": False, "detail": str(exc)}]})


# ------------------------------------------------------------- order book ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def futures_orderbook_view(request):
    """Public futures order book (depth) for the scalp page — LBank pub
    endpoint, no API key needed on LBank's side. ?symbol=BTCUSDT&depth=15"""
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper().replace(":PERP", "")
    try:
        depth = max(5, min(50, int(request.query_params.get("depth") or 15)))
    except ValueError:
        depth = 15
    client = _futures()
    try:
        return Response({"book": client.order_book(symbol, depth), "symbol": symbol})
    except LBankError as exc:
        return Response({"error": str(exc)}, status=502)
