import logging

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import MT5Account, MT5Quote, MT5Candles, MT5Order

CANON = {"XAUUSD", "XAGUSD"}

log = logging.getLogger("smartpips.mt5")


def _bridge_ok(request):
    key = request.headers.get("X-Bridge-Key") or request.headers.get("x-bridge-key")
    return settings.MT5_BRIDGE_KEY and key == settings.MT5_BRIDGE_KEY


# ===================== EA <-> server (shared-secret, no user token) =====================
@api_view(["POST"])
@permission_classes([AllowAny])
def bridge_push(request):
    """The EA posts account + quotes + candles here every few seconds.

    Body: {
      account: {login, broker, currency, balance, equity, margin, free_margin,
                leverage, profit, gold_symbol, silver_symbol},
      quotes: [{symbol, bid, ask}],
      candles: [{symbol, timeframe, candles: [{time,open,high,low,close,volume}]}]
    }
    On each push we also re-evaluate the scalp signal and fire alerts when it flips.
    """
    if not _bridge_ok(request):
        return Response({"error": "bad bridge key"}, status=403)

    data = request.data or {}

    acc = data.get("account") or {}
    if acc:
        MT5Account.objects.update_or_create(
            login=str(acc.get("login") or "demo"),
            defaults={k: acc.get(k) for k in (
                "broker", "currency", "balance", "equity", "margin", "free_margin",
                "leverage", "profit", "gold_symbol", "silver_symbol") if acc.get(k) is not None},
        )

    for q in data.get("quotes") or []:
        sym = (q.get("symbol") or "").upper()
        if sym in CANON:
            bid = float(q.get("bid") or 0)
            ask = float(q.get("ask") or 0)
            MT5Quote.objects.update_or_create(
                symbol=sym, defaults={"bid": bid, "ask": ask, "spread": round(ask - bid, 5)})

    touched = []
    for c in data.get("candles") or []:
        sym = (c.get("symbol") or "").upper()
        tf = c.get("timeframe") or "5m"
        rows = c.get("candles") or []
        if sym in CANON and rows:
            MT5Candles.objects.update_or_create(
                symbol=sym, timeframe=tf, defaults={"candles": rows})
            touched.append((sym, tf))

    # Re-evaluate signals on the freshly pushed candles and push alerts on a flip.
    alerts = 0
    try:
        from apps.alerts.signal_check import evaluate_and_alert
        for sym, tf in touched:
            alerts += evaluate_and_alert(sym, tf)
    except Exception:
        # Was a bare `pass`: the EA kept posting candles and getting 200 OK
        # while alerting was completely dead, with no trace anywhere.
        log.exception("signal evaluation failed after MT5 bridge push (touched=%s)",
                      touched)

    return Response({"ok": True, "alerts_sent": alerts})


@api_view(["GET"])
@permission_classes([AllowAny])
def bridge_pending_orders(request):
    """EA polls this for orders to execute."""
    if not _bridge_ok(request):
        return Response({"error": "bad bridge key"}, status=403)
    pending = MT5Order.objects.filter(status="pending").order_by("created")[:20]
    acc = MT5Account.objects.first()
    sym_map = {"XAUUSD": acc.gold_symbol if acc else "", "XAGUSD": acc.silver_symbol if acc else ""}
    return Response([{
        "id": o.id,
        "symbol": o.symbol,
        "broker_symbol": sym_map.get(o.symbol) or o.symbol,
        "action": o.action,
        "volume": o.volume,
        "sl": o.stop_loss,
        "tp": o.take_profit,
    } for o in pending])


@api_view(["POST"])
@permission_classes([AllowAny])
def bridge_ack_order(request, order_id):
    """EA reports the result of executing an order."""
    if not _bridge_ok(request):
        return Response({"error": "bad bridge key"}, status=403)
    try:
        o = MT5Order.objects.get(id=order_id)
    except MT5Order.DoesNotExist:
        return Response({"error": "not found"}, status=404)
    o.status = request.data.get("status", "error")
    o.ticket = request.data.get("ticket")
    o.message = (request.data.get("message") or "")[:255]
    o.save()
    return Response({"ok": True})


# ===================== Frontend (user token) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def account_view(request):
    acc = MT5Account.objects.order_by("-updated").first()
    quotes = {q.symbol: {"bid": q.bid, "ask": q.ask, "spread": q.spread}
              for q in MT5Quote.objects.all()}
    if not acc:
        return Response({"connected": False, "quotes": quotes})
    # consider it "connected" only if updated in the last 2 minutes
    from django.utils import timezone
    fresh = (timezone.now() - acc.updated).total_seconds() < 120
    return Response({
        "connected": fresh,
        "broker": acc.broker, "currency": acc.currency,
        "balance": acc.balance, "equity": acc.equity,
        "free_margin": acc.free_margin, "leverage": acc.leverage,
        "profit": acc.profit,
        "gold_symbol": acc.gold_symbol, "silver_symbol": acc.silver_symbol,
        "quotes": quotes,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order(request):
    """Queue an order for the EA to execute (from a scalp signal)."""
    symbol = (request.data.get("symbol") or "").upper()
    action = (request.data.get("action") or "").lower()
    if symbol not in CANON or action not in ("buy", "sell"):
        return Response({"error": "symbol must be gold/silver and action buy/sell"}, status=400)
    try:
        volume = float(request.data.get("volume") or 0.01)
    except (TypeError, ValueError):
        volume = 0.01
    if not MT5Account.objects.exists():
        return Response({"error": "MT5 is not connected yet."}, status=400)

    order = MT5Order.objects.create(
        user=request.user, symbol=symbol, action=action, volume=volume,
        stop_loss=request.data.get("sl"), take_profit=request.data.get("tp"),
    )
    return Response({"ok": True, "order_id": order.id, "status": order.status})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    orders = request.user.mt5_orders.order_by("-created")[:20]
    return Response([{
        "id": o.id, "symbol": o.symbol, "action": o.action, "volume": o.volume,
        "sl": o.stop_loss, "tp": o.take_profit, "status": o.status,
        "ticket": o.ticket, "message": o.message, "created": o.created.isoformat(),
    } for o in orders])
