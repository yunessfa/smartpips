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


def _journal_open(user, *, symbol, side, qty, entry, leverage, tp, sl, source, note=""):
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
        t = Trade.objects.create(
            user=user, symbol=symbol,
            direction="long" if side == "BUY" else "short",
            entry_price=entry, take_profit=tp, stop_loss=sl,
            size=margin, leverage=lev,
            status="open", source=source, notes=note,
        )
        return t.id
    except Exception:
        # THE WORST silent failure in the codebase: a real Bitunix fill existed
        # with no journal row, so the trades page, the PnL math and the daily
        # loss limit all under-counted a position that was really open.
        log.exception("journal mirror FAILED (position is open but unrecorded): "
                      "user=%s symbol=%s side=%s qty=%s entry=%s source=%s",
                      getattr(user, "username", user), symbol, side, qty, entry, source)
        return None


def _journal_close(user, trade_id, exit_price, note=""):
    """Close the mirrored journal entry with the real exit data."""
    if not trade_id:
        return
    try:
        from django.utils import timezone as _tz
        from apps.trades.models import Trade
        t = Trade.objects.get(pk=trade_id, user=user)
        if t.status == "closed":
            return
        t.exit_price = exit_price
        t.pnl, t.pnl_percent = t.compute_pnl()
        t.status = "closed"
        t.closed_at = _tz.now()
        if note:
            t.notes = (t.notes + "\n" + note).strip()
        t.save()
    except Exception:
        # A trade that stays "open" in the journal after really being closed
        # keeps eating the margin budget and skews the loss limit.
        log.exception("journal close FAILED: user=%s trade_id=%s exit=%s",
                      getattr(user, "username", user), trade_id, exit_price)


def _num(v, default=None):
    try:
        return float(v)
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
            hit = p.check_tp_sl(price)
            if hit:
                # atomic + row-locked close so two concurrent position reads
                # (5s polling → overlapping requests) can't double-close or
                # corrupt the mirrored journal row.
                from django.db import transaction
                with transaction.atomic():
                    locked = (DemoPosition.objects.select_for_update()
                              .filter(pk=p.pk, closed_at__isnull=True).first())
                    if locked is None:
                        continue    # already closed by a concurrent request
                    locked.closed_at = timezone.now()
                    locked.close_price = (locked.liq_price if hit == "liq"
                                          else locked.tp_price if hit == "tp" else locked.sl_price)
                    locked.close_reason = hit
                    locked.realized_pnl = (-locked.margin if hit == "liq"
                                           else locked.unrealized_pnl(locked.close_price))
                    locked.save()
                    _journal_close(request.user, locked.journal_trade_id,
                                   locked.close_price, note=f"closed by {hit}")
                continue
            rows.append({
                "id": p.id, "symbol": p.symbol, "side": p.side, "qty": p.qty,
                "entryPrice": p.entry_price, "leverage": p.leverage,
                "margin": p.margin, "tpPrice": p.tp_price, "slPrice": p.sl_price,
                "liqPrice": p.liq_price,
                "markPrice": price, "unrealizedPNL": p.unrealized_pnl(price),
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
        return Response({"mode": "demo", "positions": rows, "history": closed,
                         "marginUsed": margin_used, "unrealizedPNL": upnl})

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
    leverage = int(_num(d.get("leverage"), 1) or 1)
    tp = _num(d.get("tpPrice"))
    sl = _num(d.get("slPrice"))
    if not symbol or side not in ("BUY", "SELL") or not qty or qty <= 0:
        return Response({"error": "symbol, side (BUY/SELL) and positive qty are required."},
                        status=400)
    if order_type == "LIMIT" and not price:
        return Response({"error": "LIMIT order requires price."}, status=400)

    c = _client()

    # sanity-check TP/SL are on the correct side of entry (both modes)
    ref_price = price
    if ref_price is None:
        try:
            ref_price = c.last_price(symbol)
        except BitunixError as exc:
            return Response({"error": f"could not fetch live price: {exc}"}, status=502)
    if ref_price:
        if side == "BUY" and ((tp and tp <= ref_price) or (sl and sl >= ref_price)):
            return Response({"error": "For BUY: tpPrice must be above and slPrice below entry."},
                            status=400)
        if side == "SELL" and ((tp and tp >= ref_price) or (sl and sl <= ref_price)):
            return Response({"error": "For SELL: tpPrice must be below and slPrice above entry."},
                            status=400)

    # ---------------- demo: fill at live price, store locally ----------------
    if mode == "demo":
        fill = ref_price
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
        )
        pos.journal_trade_id = _journal_open(
            request.user, symbol=symbol, side=side, qty=qty, entry=fill,
            leverage=leverage, tp=tp, sl=sl, source="bitunix_demo")
        pos.save(update_fields=["journal_trade_id"])
        return Response({"mode": "demo", "filled": True, "positionId": pos.id,
                         "entryPrice": fill})

    # ---------------- real: guards, then Bitunix -----------------------------
    if d.get("confirm") is not True:
        return Response({"error": "REAL order refused: confirm=true is required."}, status=400)
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)

    # PER-USER RISK LIMITS (admin-set): leverage / notional / open count /
    # daily-loss kill-switch. Enforced here so neither a UI bug nor a direct
    # API call can bypass them.
    try:
        from apps.prefs.models import RiskLimits
        notional = qty * ref_price
        breach = RiskLimits.for_user(request.user).check_order(
            request.user, leverage=leverage, notional=notional)
        if breach:
            return Response({"error": breach, "risk_limit": True}, status=400)
    except Exception:
        # Still never blocks a legitimate order, but now it is visible: a
        # permanently failing check means the kill-switch is not protecting
        # anyone, which is exactly the situation you must not learn about late.
        log.exception("risk-limit pre-check failed for %s (order allowed through)",
                      getattr(request.user, "username", request.user))

    # HARD CAP: required margin must fit available balance from Bitunix itself.
    try:
        acct = c.account() or {}
        acct_row = acct[0] if isinstance(acct, list) and acct else acct
        available = _num(acct_row.get("available") or acct_row.get("availableBalance")
                         or acct_row.get("crossAvailable"), None)
    except BitunixError as exc:
        return Response({"error": f"could not read account before order: {exc}"}, status=502)
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
                pass  # non-fatal: order proceeds on current leverage
        res = c.place_order(symbol, side, qty, order_type=order_type, price=price,
                            tp_price=tp, sl_price=sl)
        order_id = (res or {}).get("orderId") if isinstance(res, dict) else None
        _journal_open(request.user, symbol=symbol, side=side, qty=qty,
                      entry=price or ref_price, leverage=leverage, tp=tp, sl=sl,
                      source="bitunix_real",
                      note=f"bitunix orderId {order_id}" if order_id else "bitunix real order")
        return Response({"mode": "real", "result": res})
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
            try:
                price = c.last_price(pos.symbol)
            except BitunixError:
                price = pos.entry_price
            pos.closed_at = timezone.now()
            pos.close_price = price
            pos.close_reason = "manual"
            pos.realized_pnl = pos.unrealized_pnl(price)
            pos.save()
            _journal_close(request.user, pos.journal_trade_id, price,
                           note="closed manually")
        return Response({"mode": "demo", "closed": True, "closePrice": price,
                         "realizedPNL": pos.realized_pnl})
    if d.get("confirm") is not True:
        return Response({"error": "REAL close refused: confirm=true is required."}, status=400)
    if not c.configured:
        return Response({"error": "Bitunix not configured."}, status=400)
    try:
        res = c.flash_close_position(d.get("positionId"))
        # best-effort journal close: exit at the live price (the exchange's
        # exact fill may differ slightly; noted in the journal entry)
        try:
            from apps.trades.models import Trade
            symbol = (d.get("symbol") or "").upper()
            qs = Trade.objects.filter(user=request.user, source="bitunix_real",
                                      status="open")
            if symbol:
                qs = qs.filter(symbol=symbol)
            t = qs.order_by("-opened_at").first()
            if t:
                _journal_close(request.user, t.id, c.last_price(t.symbol),
                               note="flash close (exit = live estimate)")
        except Exception:
            log.exception("flash-close journal update failed for %s",
                          getattr(request.user, "username", request.user))
        return Response({"mode": "real", "result": res})
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
