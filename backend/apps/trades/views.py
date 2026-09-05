from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import Trade
from .serializers import TradeSerializer, CloseTradeSerializer


class TradeViewSet(viewsets.ModelViewSet):
    serializer_class = TradeSerializer

    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Optional margin guard: if the client sends `balance` (the account size
        # they've set in the Risk panel), block opening a new crypto trade that
        # would commit more capital than is actually free. e.g. $500 balance with
        # $300 already tied up in an open position leaves $200 — a new trade
        # asking for $250 margin gets rejected with a clear reason.
        balance = self.request.data.get("balance")
        symbol = (serializer.validated_data.get("symbol") or "").upper()
        size = serializer.validated_data.get("size") or 0
        is_crypto = symbol.replace(":PERP", "").endswith("USDT")
        if balance and is_crypto and size:
            from apps.strategy.risk import used_crypto_margin, NON_REAL_SOURCES
            try:
                balance = float(balance)
                used = used_crypto_margin(self.request.user, sources=NON_REAL_SOURCES)
                available = round(balance - used, 2)
                if size > available + 0.01:
                    raise ValidationError(
                        f"Not enough available margin: this trade needs "
                        f"${size:.2f} but only ${available:.2f} is free "
                        f"(${used:.2f} of ${balance:.2f} already committed to "
                        f"open position(s)).")
            except ValidationError:
                raise
            except Exception:
                pass  # never block a trade over a margin-check plumbing error
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def margin_status(self, request):
        """Current margin usage across open crypto positions, given a balance."""
        from apps.strategy.risk import used_crypto_margin, NON_REAL_SOURCES
        try:
            balance = float(request.query_params.get("balance") or 0)
        except ValueError:
            balance = 0
        used = used_crypto_margin(request.user, sources=NON_REAL_SOURCES)
        return Response({"balance": balance, "used_margin": used,
                         "available_margin": round(balance - used, 2) if balance else None})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        trade = self.get_object()
        ser = CloseTradeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        trade.close(ser.validated_data["exit_price"])
        return Response(TradeSerializer(trade).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        closed = [t for t in qs if t.status == "closed" and t.pnl is not None]
        wins = [t for t in closed if t.pnl > 0]
        total_pnl = round(sum(t.pnl for t in closed), 2)
        win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
        return Response(
            {
                "open": qs.filter(status="open").count(),
                "closed": len(closed),
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "wins": len(wins),
                "losses": len(closed) - len(wins),
            }
        )

    @action(detail=False, methods=["get"])
    def profile(self, request):
        from .profile import compute_trader_profile
        return Response(compute_trader_profile(request.user))

    @action(detail=False, methods=["get"])
    def journal(self, request):
        from .journal import analyze_journal
        return Response(analyze_journal(request.user))

    @action(detail=False, methods=["get"])
    def setup_stats(self, request):
        from .journal import setup_statistics
        return Response({"setups": setup_statistics(request.user)})

    @action(detail=False, methods=["get"])
    def exit_advice(self, request):
        """For each OPEN trade, run the smart exit engine and return a recommendation
        (hold / trail / partial / exit) with a suggested trailed stop and reasons."""
        from apps.market.candles import fetch_candles
        from apps.market.quotes_resolver import live_price as resolve_price
        from apps.strategy.exit_engine import evaluate_exit

        out = []
        for tr in request.user.trades.filter(status="open"):
            try:
                px = resolve_price(tr.symbol)
                candles = fetch_candles(tr.symbol, "5m", limit=120)
                if not px or not candles:
                    continue
                rec = evaluate_exit(tr.direction, tr.entry_price, px,
                                    tr.stop_loss, tr.take_profit, candles)
                rec["trade_id"] = tr.id
                rec["symbol"] = tr.symbol
                rec["current_price"] = px
                out.append(rec)
            except Exception:
                continue
        return Response({"advice": out})

    @action(detail=False, methods=["post"])
    def auto_close(self, request):
        """Check the user's OPEN trades against the live price and settle them:

        - If the trade has a 3-level TP plan (tp1/tp2/tp3), close each slice as
          its level is reached (partial exits), and close fully on SL or once all
          three slices are done. This is the "manage it even if I'm not
          watching" behaviour.
        - Older trades without TP levels keep the original single-TP/SL logic.

        Called when the Trades page loads so positions settle without manual entry.
        """
        from apps.market.quotes_resolver import live_price as resolve_price

        closed = []
        partial = []
        price_cache = {}
        for tr in request.user.trades.filter(status="open"):
            has_levels = tr.tp1_price or tr.tp2_price or tr.tp3_price
            if not has_levels and tr.take_profit is None and tr.stop_loss is None:
                continue
            sym = tr.symbol.upper()
            if sym not in price_cache:
                try:
                    price_cache[sym] = resolve_price(sym)
                except Exception:
                    price_cache[sym] = None
            px = price_cache[sym]
            if not px:
                continue

            is_long = tr.direction == "long"

            # ---- SL always takes priority: close whatever remains, immediately ----
            if tr.stop_loss:
                sl_hit = (px <= tr.stop_loss) if is_long else (px >= tr.stop_loss)
                if sl_hit:
                    tr.close(tr.stop_loss)
                    closed.append({"id": tr.id, "symbol": tr.symbol, "exit": tr.stop_loss,
                                   "pnl": tr.pnl, "pnl_percent": tr.pnl_percent, "reason": "sl"})
                    continue

            if has_levels:
                # ---- check each un-fired TP level in order ----
                levels = [
                    ("tp1_price", "tp1_pct", "tp1_done"),
                    ("tp2_price", "tp2_pct", "tp2_done"),
                    ("tp3_price", "tp3_pct", "tp3_done"),
                ]
                for price_f, pct_f, done_f in levels:
                    lvl_price = getattr(tr, price_f)
                    if not lvl_price or getattr(tr, done_f):
                        continue
                    hit = (px >= lvl_price) if is_long else (px <= lvl_price)
                    if hit:
                        pct = getattr(tr, pct_f)
                        slice_pnl = tr.close_partial(lvl_price, pct, done_f)
                        partial.append({"id": tr.id, "symbol": tr.symbol,
                                        "level": price_f, "exit": lvl_price,
                                        "slice_pnl": round(slice_pnl, 4),
                                        "remaining_pct": tr.remaining_pct})
                        if tr.status == "closed":
                            closed.append({"id": tr.id, "symbol": tr.symbol, "exit": lvl_price,
                                           "pnl": tr.pnl, "pnl_percent": tr.pnl_percent, "reason": "tp_final"})
                        break  # one level per pass; next auto_close call checks the rest
            else:
                # ---- legacy single TP/SL behaviour ----
                hit = None
                if is_long and tr.take_profit and px >= tr.take_profit:
                    hit = tr.take_profit
                elif not is_long and tr.take_profit and px <= tr.take_profit:
                    hit = tr.take_profit
                if hit is not None:
                    tr.close(hit)
                    closed.append({"id": tr.id, "symbol": tr.symbol, "exit": hit,
                                   "pnl": tr.pnl, "pnl_percent": tr.pnl_percent, "reason": "tp"})

        return Response({"closed": closed, "partial": partial,
                         "count": len(closed), "partial_count": len(partial)})
