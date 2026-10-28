"""Bitunix panel API.

Real-money rules enforced here (not just in the UI):
  * every REAL order needs confirm=true AND mode="real" — two separate,
    explicit fields, so a demo request can never accidentally become real;
  * REAL orders are hard-capped: required margin must fit the account's
    available balance (checked against Bitunix's own account response);
  * demo mode never touches Bitunix private endpoints — it fills against the
    live public price and stores in our DB.
"""
import logging
import math
from django.conf import settings
from django.db import transaction

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from apps.accounts.throttles import OrderRateThrottle
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .client import BitunixClient, BitunixError
from .models import DemoPosition

# smartpips.orders is already wired at INFO in settings.LOGGING — order paths
# are the one place where a swallowed error costs real money.
log = logging.getLogger("smartpips.orders")


def _client():
    return BitunixClient()


def _journal_open(user, *, symbol, side, qty, entry, leverage, tp, sl, source, note="", context=None, order_id=""):
    """Mirror a Bitunix trade (demo or real) into the main Trade journal so
    the trades page / analytics see everything in one place.

    IMPORTANT: the app-wide convention (PositionsPanel, risk sizing, PnL math)
    is that Trade.size = committed MARGIN in USD for crypto, from which
    notional = size*leverage and qty = notional/entry are derived. So we store
    the margin here, NOT the coin qty — storing qty made the in-app account
    panel read the coin count as dollars and inflate value/qty by ~leverage×."""
    try:
        from apps.trades.models import Trade
        lev = leverage or 1
        margin = round((qty * entry) / lev, 6) if entry else 0
        context = dict(context or {})
        analysis = context.pop("_entry_analysis_context", None)
        t = Trade(
            user=user, symbol=symbol,
            direction="long" if side == "BUY" else "short",
            entry_price=entry, take_profit=tp, stop_loss=sl,
            size=margin, leverage=lev,
            status="open", source=source, notes=note,
            external_order_id=str(order_id or ""), **(context or {}),
        )
        t._entry_analysis = analysis
        t.save()
        return t.id
    except Exception:
        # THE WORST silent failure in the codebase: a real Bitunix fill existed
        # with no journal row, so the trades page, the PnL math and the daily
        # loss limit all under-counted a position that was really open.
        log.exception("journal mirror FAILED (position is open but unrecorded): "
                      "user=%s symbol=%s side=%s qty=%s entry=%s source=%s",
                      getattr(user, "username", user), symbol, side, qty, entry, source)
        return None


def _verify_market_fill(client, symbol, side, attempts=3, wait=0.4):
    """Best-effort read of the position a MARKET order just opened.

    Returns {entry, position_id} from the exchange or None when it cannot be
    confirmed. Never raises: the order is already live at this point."""
    import time as _t
    want = "LONG" if side == "BUY" else "SHORT"
    for i in range(attempts):
        try:
            rows = client.pending_positions(symbol) or []
        except Exception:
            rows = []
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            if (r.get("symbol") or "").upper() != symbol.upper():
                continue
            if str(r.get("side") or "").upper() not in (want, side):
                continue
            entry = _num(r.get("avgOpenPrice")) or _num(r.get("entryPrice"))
            if entry and entry > 0:
                return {"entry": entry, "position_id": r.get("positionId") or r.get("id")}
        if i + 1 < attempts:
            _t.sleep(wait)
    return None


def _journal_close(user, trade_id, exit_price, note="", reason="manual"):
    if not trade_id:
        return
    from apps.trades.models import Trade
    with transaction.atomic():
        t = Trade.objects.select_for_update().filter(pk=trade_id, user=user).first()
        if t is None or t.status == "closed":
            return
        if note:
            t.notes = (t.notes + "\n" + note).strip()
            t.save(update_fields=["notes"])
        t.close(exit_price, reason=reason)



def _num(v, default=None):
    try:
        value = float(v)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- status ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    c = _client()
    out = {"configured": c.configured, "connected": False,
           "diagnostics": c.diagnostics()}
    if c.configured:
        try:
            c.account()
            out["connected"] = True
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def self_test_view(request):
    """Read-only end-to-end test (public + private), never places orders."""
    return Response(_client().self_test())


# --------------------------------------------------------------- account ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def account_view(request):
    c = _client()
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        return Response({"account": c.account(request.query_params.get("marginCoin") or "USDT")})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


def _enrich_real_positions(c, rows):
    """Normalise REAL Bitunix positions so they carry the same fields the demo
    rows do.

    Bitunix's pending-positions payload has no `markPrice` (and often no
    unrealized PnL), so the REAL tab showed "—" under Mark and a dead PnL
    cell. We join the mark price in from the public tickers feed and derive
    the missing numbers from it.
    """
    if not isinstance(rows, list):
        return rows
    marks = c.mark_prices([r.get("symbol") for r in rows if isinstance(r, dict)])
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            out.append(raw)
            continue
        r = dict(raw)
        sym = (r.get("symbol") or "").upper()
        mark = _num(r.get("markPrice")) or marks.get(sym)
        if mark is not None:
            r["markPrice"] = mark
        entry = (_num(r.get("entryPrice")) or _num(r.get("avgOpenPrice"))
                 or _num(r.get("entryValue")))
        if entry is not None:
            r["entryPrice"] = entry
        qty = _num(r.get("qty"))
        side = (r.get("side") or "").upper()
        is_long = ("BUY" in side) or (side == "LONG")
        upnl = _num(r.get("unrealizedPNL"))
        if upnl is None:
            upnl = _num(r.get("unrealizedPnl"))
        if upnl is None and None not in (mark, entry, qty):
            diff = (mark - entry) if is_long else (entry - mark)
            upnl = round(diff * qty, 4)
        if upnl is not None:
            r["unrealizedPNL"] = upnl
        lev = _num(r.get("leverage"), 1) or 1
        margin = _num(r.get("margin"))
        if margin is None and entry and qty:
            margin = round((entry * qty) / lev, 4)
        if margin is not None:
            r["margin"] = margin
            if margin and upnl is not None:
                r["roe"] = round(upnl / margin * 100, 2)
        if mark and qty:
            r["positionValue"] = round(mark * qty, 4)
        r["liqPrice"] = (_num(r.get("liqPrice"))
                         or _num(r.get("liquidationPrice")))
        r["side"] = "LONG" if is_long else "SHORT"
        r["mode"] = "real"
        out.append(r)
    return out


# ------------------------------------------------------------- positions ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def positions_view(request):
    """mode=real -> live Bitunix positions; mode=demo -> our paper positions
    (TP/SL evaluated against the live price on every read)."""
    mode = (request.query_params.get("mode") or "real").lower()
    c = _client()
    if mode == "demo":
        symbol_prices = {}
        rows = []
        open_qs = DemoPosition.objects.filter(user=request.user, closed_at__isnull=True)
        for p in open_qs:
            price = symbol_prices.get(p.symbol)
            if price is None:
                try:
                    price = c.last_price(p.symbol)
                except BitunixError:
                    price = None
                symbol_prices[p.symbol] = price
            if p.is_pending:
                from .demo_monitor import progress_pending
                state = progress_pending(p.pk, price)
                if state == "expired":
                    continue
                p.refresh_from_db()
            hit = p.check_tp_sl(price)
            if hit:
                from .demo_monitor import settle_demo
                settle_demo(p.pk, price)
                continue
            if p.is_pending:
                rows.append({
                    "id": p.id, "symbol": p.symbol, "side": p.side, "qty": p.qty,
                    "entryPrice": p.entry_price, "limitPrice": p.entry_price,
                    "leverage": p.leverage, "margin": p.margin,
                    "tpPrice": p.tp_price, "slPrice": p.sl_price, "markPrice": price,
                    "unrealizedPNL": 0.0, "pnlGross": 0.0, "estFee": 0.0,
                    "pending": True, "orderType": "LIMIT", "expiresAt": p.expires_at,
                    "mode": "demo", "openedAt": p.opened_at,
                })
                continue
            rows.append({
                "id": p.id, "symbol": p.symbol, "side": p.side, "qty": p.qty,
                "entryPrice": p.entry_price, "leverage": p.leverage,
                "margin": p.margin, "tpPrice": p.tp_price, "slPrice": p.sl_price,
                "liqPrice": p.liq_price,
                "markPrice": price, "unrealizedPNL": p.unrealized_pnl(price),
                # DISPLAY ONLY — these are never subtracted from unrealizedPNL.
                "pnlGross": p.gross_pnl(price),
                "estFee": p.round_trip_fee(price),
                "positionValue": (round(price * p.qty, 4) if price else None),
                "roe": (round(p.unrealized_pnl(price) / p.margin * 100, 2)
                        if price and p.margin else None),
                "mode": "demo",
                "openedAt": p.opened_at,
            })
        closed = [{
            "id": p.id, "symbol": p.symbol, "side": p.side, "qty": p.qty,
            "entryPrice": p.entry_price, "closePrice": p.close_price,
            "closeReason": p.close_reason, "realizedPNL": p.realized_pnl,
            "closedAt": p.closed_at,
        } for p in DemoPosition.objects.filter(
            user=request.user, closed_at__isnull=False)[:20]]
        margin_used = round(sum(r["margin"] or 0 for r in rows), 4)
        upnl = round(sum(r["unrealizedPNL"] or 0 for r in rows), 4)
        est_fee = round(sum(r["estFee"] or 0 for r in rows), 4)
        return Response({"mode": "demo", "positions": rows, "history": closed,
                         "marginUsed": margin_used, "unrealizedPNL": upnl,
                         # estimate shown next to PnL, not deducted from it
                         "estFee": est_fee})

    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        rows = _enrich_real_positions(
            c, c.pending_positions(request.query_params.get("symbol")))
        upnl = round(sum(_num(r.get("unrealizedPNL"), 0) or 0
                         for r in rows if isinstance(r, dict)), 4)
        margin_used = round(sum(_num(r.get("margin"), 0) or 0
                                for r in rows if isinstance(r, dict)), 4)
        return Response({"mode": "real", "positions": rows,
                         "marginUsed": margin_used, "unrealizedPNL": upnl,
                         "history": c.history_positions(limit=20)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


# ---------------------------------------------------------------- orders ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def orders_view(request):
    c = _client()
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        return Response({"pending": c.pending_orders(request.query_params.get("symbol")),
                         "history": c.history_orders(request.query_params.get("symbol"), 20)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([OrderRateThrottle])
@transaction.atomic
def place_order_view(request):
    """Demo or REAL order. Shared payload:
      {mode: demo|real, confirm: bool, symbol, side: BUY|SELL,
       orderType: MARKET|LIMIT, qty, price?, leverage?, tpPrice?, slPrice?}"""
    d = request.data
    mode = (d.get("mode") or "").lower()
    if mode not in ("demo", "real"):
        return Response({"error": "mode must be 'demo' or 'real'."}, status=400)
    symbol = (d.get("symbol") or "").upper()
    side = (d.get("side") or "").upper()
    order_type = (d.get("orderType") or "MARKET").upper()
    qty = _num(d.get("qty"))
    price = _num(d.get("price"))
    requested_leverage = _num(d.get("leverage", 1))
    if requested_leverage is None or requested_leverage < 1 or not float(requested_leverage).is_integer():
        return Response({"error": "Leverage must be a positive whole number."}, status=400)
    leverage = int(requested_leverage)
    tp = _num(d.get("tpPrice"))
    sl = _num(d.get("slPrice"))
    if not symbol or side not in ("BUY", "SELL") or not qty or qty <= 0:
        return Response({"error": "symbol, side (BUY/SELL) and positive qty are required."},
                        status=400)
    if order_type == "LIMIT" and not price:
        return Response({"error": "LIMIT order requires price."}, status=400)

    # Validate attribution before any order can be sent; never infer an old trade's strategy.
    from apps.trades.attribution import order_context
    from rest_framework.exceptions import ValidationError
    try:
        context = order_context(request.user, d, symbol)
    except ValidationError as exc:
        return Response({"error": str(exc.detail)}, status=400)
    c = _client()

    # Reference price. A MARKET order fills at the market, so the server's own
    # public quote is the ONLY acceptable reference — a client-supplied "price"
    # is ignored (it could be stale, mocked or tampered with) for sizing,
    # margin checks, TP/SL side validation and demo fills. LIMIT orders keep
    # their own price, which is what the exchange will honour.
    client_price = price
    if order_type == "MARKET":
        try:
            ref_price = _num(c.last_price(symbol))
        except BitunixError as exc:
            return Response({"error": f"could not fetch live price: {exc}"}, status=502)
        if not ref_price or ref_price <= 0:
            return Response({"error": "Live public price unavailable; no order submitted.",
                             "code": "no_public_price"}, status=503)
        price = None  # never forward a client price with a MARKET order
    else:
        ref_price = price
    if ref_price:
        if side == "BUY" and ((tp and tp <= ref_price) or (sl and sl >= ref_price)):
            return Response({"error": "For BUY: tpPrice must be above and slPrice below entry."},
                            status=400)
        if side == "SELL" and ((tp and tp >= ref_price) or (sl and sl <= ref_price)):
            return Response({"error": "For SELL: tpPrice must be below and slPrice above entry."},
                            status=400)

    risk_warnings = []
    # ---------------- demo: fill at live price, store locally ----------------
    if mode == "demo":
        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        fill = ref_price
        is_limit = order_type == "LIMIT"
        expires_at = None
        if is_limit:
            # Resting demo LIMIT (pullback entry). It becomes a position only
            # when the public price trades through the limit; it expires after
            # `expiryMinutes` (default 30, max 24h).
            try:
                expiry_min = float(d.get("expiryMinutes") or 30)
            except (TypeError, ValueError):
                expiry_min = 30
            expiry_min = max(1.0, min(expiry_min, 1440.0))
            from datetime import timedelta
            expires_at = timezone.now() + timedelta(minutes=expiry_min)
            try:
                public = _num(c.last_price(symbol))
            except BitunixError:
                public = None
            if public and ((side == "BUY" and public <= fill) or (side == "SELL" and public >= fill)):
                # marketable limit: an exchange fills it immediately at the market
                is_limit, expires_at, fill = False, None, public
        if not fill or fill <= 0 or leverage < 1:
            return Response({"error": "Valid public price and leverage required."}, status=400)
        if getattr(settings, "DEMO_RISK_V1_ENABLED", True):
            from .demo_risk import assess
            assessment = assess(request.user, balance=_num(d.get("demoBalance")),
                                entry=fill, stop=sl, qty=qty, leverage=leverage, side=side)
            risk_warnings = assessment.get("warnings", [])
            if not assessment["allowed"]:
                return Response({"error": "; ".join(assessment["errors"]),
                                 "code": "demo_risk_blocked", "risk": assessment}, status=400)
        # Demo sizing runs on the balance the USER entered at the top of the
        # Scalp page (passed as demoBalance) — never the real Bitunix wallet.
        demo_balance = _num(d.get("demoBalance"))
        if demo_balance is not None and demo_balance > 0:
            used = sum(p.margin or 0 for p in DemoPosition.objects.filter(
                user=request.user, closed_at__isnull=True))
            need = qty * fill / max(leverage, 1)
            free = demo_balance - used
            if need > free * 1.001:
                return Response({"error": f"insufficient demo balance: need "
                                          f"≈{need:.2f} USDT, free {max(free,0):.2f} "
                                          f"of {demo_balance:.2f}.",
                                 "needMargin": round(need, 2),
                                 "available": round(max(free, 0), 2)}, status=400)
        pos = DemoPosition.objects.create(
            user=request.user, symbol=symbol,
            side="LONG" if side == "BUY" else "SHORT",
            qty=qty, entry_price=fill, leverage=leverage,
            margin=round(qty * fill / max(leverage, 1), 4),
            tp_price=tp, sl_price=sl,
            order_type="LIMIT" if is_limit else "MARKET",
            filled_at=None if is_limit else timezone.now(),
            expires_at=expires_at,
        )
        if is_limit:
            # no journal row until it fills — a resting order is not a trade
            return Response({"mode": "demo", "filled": False, "pending": True,
                             "positionId": pos.id, "limitPrice": fill,
                             "expiresAt": expires_at, "warnings": risk_warnings,
                             "leverage_policy": "warning_only"})
        pos.journal_trade_id = _journal_open(
            request.user, symbol=symbol, side=side, qty=qty, entry=fill,
            leverage=leverage, tp=tp, sl=sl, source="bitunix_demo", context=context)
        if not pos.journal_trade_id:
            transaction.set_rollback(True)
            return Response({"error": "Demo journal unavailable; position creation rolled back."}, status=503)
        pos.save(update_fields=["journal_trade_id"])
        return Response({"mode": "demo", "filled": True, "positionId": pos.id,
                         "entryPrice": fill, "warnings": risk_warnings,
                         "leverage_policy": "warning_only"})

    # ---------------- real: guards, then Bitunix -----------------------------
    if d.get("confirm") is not True:
        return Response({"error": "REAL order refused: confirm=true is required."}, status=400)
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)

    # Internal leverage is advisory; notional / open count /
    # daily-loss kill-switch. Enforced here so neither a UI bug nor a direct
    # API call can bypass them.
    try:
        from apps.prefs.models import RiskLimits
        notional = qty * ref_price
        limits = RiskLimits.for_user(request.user)
        risk_warnings = limits.order_warnings(leverage=leverage)
        breach = limits.check_order(request.user, leverage=leverage, notional=notional)
        if breach:
            return Response({"error": breach, "risk_limit": True}, status=400)
    except Exception:
        log.exception("risk-limit pre-check failed; real order BLOCKED")
        return Response({"error": "Risk verification unavailable; no order submitted.",
                         "risk_limit": True}, status=503)

    # HARD CAP: required margin must fit available balance from Bitunix itself.
    try:
        acct = c.account() or {}
        acct_row = acct[0] if isinstance(acct, list) and acct else acct
        raw_available = next((acct_row[k] for k in ("available", "availableBalance", "crossAvailable")
                              if acct_row.get(k) is not None), None)
        available = _num(raw_available, None)
    except (BitunixError, AttributeError, IndexError, TypeError):
        return Response({"error": "Account verification unavailable; no order submitted."}, status=502)
    import math
    if available is None or not math.isfinite(available) or available < 0:
        return Response({"error": "Available balance unknown; no order submitted."}, status=503)
    need_margin = qty * ref_price / max(leverage, 1)
    if available is not None and need_margin > available * 1.001:
        return Response({"error": f"insufficient margin: need ≈{need_margin:.2f} USDT, "
                                  f"available {available:.2f} USDT. Reduce qty or raise leverage.",
                         "needMargin": round(need_margin, 2),
                         "available": round(available, 2)}, status=400)

    try:
        if d.get("leverage"):
            try:
                c.change_leverage(symbol, leverage)
            except BitunixError:
                return Response({"error": "Leverage verification failed; no order submitted."}, status=502)
        res = c.place_order(symbol, side, qty, order_type=order_type, price=price,
                            tp_price=tp, sl_price=sl)
        order_id = (res or {}).get("orderId") if isinstance(res, dict) else None
        # An exchange ACK only means "accepted", not "filled". For MARKET we
        # look the position up once to record the REAL average entry; LIMIT
        # orders are journalled as pending-fill so nobody mistakes them for a
        # filled position (they still count toward exposure — conservative).
        fill = _verify_market_fill(c, symbol, side) if order_type == "MARKET" else None
        if fill:
            entry_px, fill_note = fill["entry"], f"fill verified (position {fill['position_id']})"
        elif order_type == "MARKET":
            entry_px, fill_note = ref_price, "ACK only — fill NOT verified, entry = pre-trade quote; reconcile"
        else:
            entry_px, fill_note = price, "LIMIT accepted — PENDING FILL, not a confirmed position"
        _journal_open(request.user, symbol=symbol, side=side, qty=qty,
                      entry=entry_px, leverage=leverage, tp=tp, sl=sl,
                      source="bitunix_real",
                      note=(f"bitunix orderId {order_id}" if order_id else "bitunix real order")
                           + f"; {fill_note}"
                           + ("; leverage_above_recommended" if risk_warnings else ""),
                      context=context, order_id=order_id)
        return Response({"mode": "real", "result": res, "warnings": risk_warnings,
                         "fill_status": "verified" if fill else
                         ("unverified" if order_type == "MARKET" else "pending_limit"),
                         "entryPrice": entry_px,
                         "client_price_ignored": order_type == "MARKET" and client_price is not None,
                         "leverage_policy": "warning_only"})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([OrderRateThrottle])
def close_position_view(request):
    """Close a position. demo -> close locally at live price;
    real -> Bitunix flash close (requires confirm=true)."""
    d = request.data
    mode = (d.get("mode") or "").lower()
    c = _client()
    if mode == "demo":
        from django.db import transaction
        with transaction.atomic():
            pos = (DemoPosition.objects.select_for_update()
                   .filter(pk=d.get("positionId"), user=request.user,
                           closed_at__isnull=True).first())
            if pos is None:
                return Response({"error": "demo position not found or already closed."},
                                status=404)
            if pos.is_pending:
                pos.closed_at, pos.close_reason, pos.realized_pnl = timezone.now(), "cancelled", 0.0
                pos.save()
                return Response({"mode": "demo", "cancelled": True, "positionId": pos.id})
            try:
                price = c.last_price(pos.symbol)
            except BitunixError as exc:
                return Response({"error": "Public price unavailable; demo close not fabricated."}, status=503)
            price = _num(price)
            if not price or price <= 0:
                return Response({"error": "Valid public price unavailable."}, status=503)
            pos.closed_at = timezone.now()
            pos.close_price = price
            pos.close_reason = "manual"
            pos.realized_pnl = pos.gross_pnl(price)
            pos.save()
            _journal_close(request.user, pos.journal_trade_id, price,
                           note="closed manually")
        return Response({"mode": "demo", "closed": True, "closePrice": price,
                         "realizedPNL": pos.realized_pnl})
    if d.get("confirm") is not True:
        return Response({"error": "REAL close refused: confirm=true is required."}, status=400)
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    if mode != "real":
        return Response({"error": "mode must be 'demo' or 'real'."}, status=400)
    position_id = str(d.get("positionId") or "").strip()
    if not position_id:
        return Response({"error": "positionId is required for a real close."}, status=400)
    # Identify the exact exchange position BEFORE closing so the journal row we
    # settle is the one that belongs to it — never "the newest open trade".
    try:
        live_rows = c.pending_positions()
    except BitunixError as exc:
        return Response({"error": f"could not verify position: {exc}"}, status=502)
    target = next((r for r in (live_rows or []) if isinstance(r, dict)
                   and str(r.get("positionId") or r.get("id") or "") == position_id), None)
    if target is None:
        return Response({"error": "Position not found on the exchange (already closed?).",
                         "code": "position_not_found"}, status=404)
    try:
        res = c.flash_close_position(position_id)
        journal = "not_matched"
        try:
            from apps.trades.models import Trade
            symbol = (target.get("symbol") or "").upper()
            direction = "long" if str(target.get("side") or "").upper() in ("LONG", "BUY") else "short"
            qs = Trade.objects.filter(user=request.user, source="bitunix_real", status="open",
                                      symbol=symbol, direction=direction)
            matches = list(qs.order_by("-opened_at")[:2])
            if len(matches) == 1:
                _journal_close(request.user, matches[0].id, c.last_price(symbol),
                               note=f"flash close position {position_id} (exit = live estimate; reconcile for exact fill)")
                journal = "closed_estimate"
            elif matches:
                journal = "ambiguous_needs_reconcile"
                log.warning("flash close %s: %d open journal rows for %s %s — left for reconciliation",
                            position_id, qs.count(), symbol, direction)
        except Exception:
            log.exception("flash-close journal update failed for %s",
                          getattr(request.user, "username", request.user))
            journal = "error"
        return Response({"mode": "real", "result": res, "journal": journal})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_orders_view(request):
    symbol = (request.data.get("symbol") or "").upper()
    ids = request.data.get("orderIds") or []
    if not symbol or not ids:
        return Response({"error": "symbol and orderIds are required."}, status=400)
    c = _client()
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        return Response({"result": c.cancel_orders(symbol, ids)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def leverage_view(request):
    symbol = (request.data.get("symbol") or "").upper()
    lev = request.data.get("leverage")
    if not symbol or not lev:
        return Response({"error": "symbol and leverage are required."}, status=400)
    c = _client()
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        return Response({"result": c.change_leverage(symbol, int(lev))})
    except (BitunixError, ValueError) as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def margin_mode_view(request):
    symbol = (request.data.get("symbol") or "").upper()
    mode = (request.data.get("marginMode") or "").upper()
    c = _client()
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        return Response({"result": c.change_margin_mode(symbol, mode)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


# --------------------------------------------------------- market proxies ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def depth_view(request):
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper().replace(":PERP", "")
    # Bitunix serves fixed depth levels; free values (e.g. 16) come back empty
    # — the self-test at 5 worked while the panel at 16 showed nothing.
    try:
        want = int(request.query_params.get("depth") or 15)
    except ValueError:
        want = 15
    depth = next((lv for lv in (5, 15, 50, 100) if lv >= want), 100)
    try:
        book = _client().depth(symbol, depth)
        if not book["asks"] and not book["bids"] and depth != 5:
            # depth=5 is known-good on this exchange (proven by the live
            # self-test), so fall back before reporting nothing
            book = _client().depth(symbol, 5)
        return Response({"symbol": symbol, "book": book, "depth": depth})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def klines_view(request):
    """OHLCV candles for the in-app position chart (entry / TP / SL overlay).

    Same venue as execution, so the lines drawn on the chart sit on exactly
    the prices the exchange will trigger against.
    """
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper().replace(":PERP", "")
    interval = request.query_params.get("interval") or "5m"
    try:
        limit = int(request.query_params.get("limit") or 300)
    except ValueError:
        limit = 300
    limit = max(50, min(limit, 1000))
    try:
        c = _client()
        return Response({"symbol": symbol, "interval": interval,
                         "candles": c.klines_paginated(symbol, interval, limit),
                         "markPrice": c.mark_prices([symbol]).get(symbol)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ticker_view(request):
    symbol = (request.query_params.get("symbol") or "BTCUSDT").upper().replace(":PERP", "")
    try:
        return Response({"symbol": symbol, "price": _client().last_price(symbol)})
    except BitunixError as exc:
        return Response({"error": str(exc)}, status=502)
