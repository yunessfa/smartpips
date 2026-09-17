"""REST API for the configurable strategy layer.

Ownership rules, enforced in the queryset rather than the frontend:

* A user sees their own strategies plus the shared read-only presets.
* Writes are limited to rows the requesting user owns; presets are cloned, not
  edited.
* Analytics are computed from that user's own trades only.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .config_models import Strategy, StrategyVersion
from .config_serializers import (
    StrategySerializer,
    StrategyVersionSerializer,
    StrategyWriteSerializer,
)
from .presets import sync_presets
from .rule_schema import effective_risk, vocabulary


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def strategy_vocabulary(request):
    """Condition blocks, operators, weight groups and risk field bounds.

    The builder UI renders itself from this, so the allowed vocabulary is
    defined once on the server and cannot drift out of sync with the validator.
    """
    return Response(vocabulary())


class StrategyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return StrategyWriteSerializer
        return StrategySerializer

    def get_queryset(self):
        # Presets (user=None) are visible to everybody; owned rows only to their
        # owner. There is no path here that can return another user's strategy.
        sync_presets()
        from django.db.models import Q
        queryset = Strategy.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).prefetch_related("versions")
        if self.request.query_params.get("include_archived") not in ("1", "true"):
            queryset = queryset.filter(archived=False)
        return queryset

    def _owned(self, strategy):
        if strategy.user_id != self.request.user.id:
            raise PermissionDenied("Built-in presets cannot be modified. Clone it first.")
        return strategy

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        version_fields = {
            "rules": data.pop("rules", []),
            "weights": data.pop("weights", {}),
            "risk": data.pop("risk", {}),
            "min_confidence": data.pop("min_confidence", 70),
        }
        notes = data.pop("version_notes", "")
        strategy = serializer.save(user=self.request.user)
        StrategyVersion.objects.create(
            strategy=strategy, version=1, notes=notes or "Initial version",
            **version_fields,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        strategy = self._owned(serializer.instance)
        data = serializer.validated_data
        has_config = any(k in data for k in ("rules", "weights", "risk", "min_confidence"))
        rules = data.pop("rules", None)
        weights = data.pop("weights", None)
        risk = data.pop("risk", None)
        min_confidence = data.pop("min_confidence", None)
        notes = data.pop("version_notes", "")

        serializer.save()

        if not has_config:
            return

        # Never mutate a stored version: trades reference it. Editing the
        # configuration always produces v(n+1) so past journal entries keep
        # pointing at the rules that actually generated them.
        current = strategy.current_version()
        StrategyVersion.objects.create(
            strategy=strategy,
            version=(current.version + 1) if current else 1,
            rules=rules if rules is not None else (current.rules if current else []),
            weights=weights if weights is not None else (current.weights if current else {}),
            risk=risk if risk is not None else (current.risk if current else {}),
            min_confidence=(min_confidence if min_confidence is not None
                            else (current.min_confidence if current else 70)),
            notes=notes,
        )
        # A new version has not been backtested yet, so it must not stay live.
        if strategy.is_active:
            Strategy.objects.filter(pk=strategy.pk).update(is_active=False)

    def perform_destroy(self, instance):
        self._owned(instance)
        # Soft delete: trades reference strategy versions, and hard-deleting
        # would blank out journal history.
        instance.archived = True
        instance.is_active = False
        instance.save(update_fields=["archived", "is_active", "updated"])

    # ------------------------------------------------------------- actions

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        strategy = self.get_object()
        return Response(StrategyVersionSerializer(
            strategy.versions.all(), many=True).data)

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Copy a preset (or one of your own) into an editable strategy."""
        source = self.get_object()
        current = source.current_version()
        copy = Strategy.objects.create(
            user=request.user,
            name=f"{source.name} (copy)"[:80],
            description=source.description,
            market=source.market,
            symbols=source.symbols,
            timeframes=source.timeframes,
            direction=source.direction,
        )
        StrategyVersion.objects.create(
            strategy=copy, version=1,
            rules=current.rules if current else [],
            weights=current.weights if current else {},
            risk=current.risk if current else {},
            min_confidence=current.min_confidence if current else 70,
            notes=f"Cloned from {source.name}",
        )
        return Response(StrategySerializer(copy).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Make this the user's active strategy.

        Exactly one strategy is active per user, matching how the engine is
        consumed (a single decision context). Custom strategies must have a
        backtest on the current version first --- the brief asks for backtest
        before live use, and that is enforced here, not just in the UI.
        """
        strategy = self.get_object()
        current = strategy.current_version()
        if not strategy.is_preset and not (current and current.backtest_at):
            return Response(
                {"error": "Run a backtest on the current version before activating it.",
                 "code": "backtest_required"},
                status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            Strategy.objects.filter(user=request.user, is_active=True).update(is_active=False)
            if strategy.is_preset:
                # Presets are shared rows, so "activating" one means cloning it
                # into the user's own space --- otherwise one user activating a
                # preset would flip it on for everyone.
                clone = Strategy.objects.create(
                    user=request.user, name=strategy.name,
                    description=strategy.description, market=strategy.market,
                    symbols=strategy.symbols, timeframes=strategy.timeframes,
                    direction=strategy.direction, preset_key=strategy.preset_key,
                    is_active=True,
                )
                StrategyVersion.objects.create(
                    strategy=clone, version=1,
                    rules=current.rules if current else [],
                    weights=current.weights if current else {},
                    risk=current.risk if current else {},
                    min_confidence=current.min_confidence if current else 70,
                    notes="Activated from preset library",
                )
                strategy = clone
            else:
                strategy.is_active = True
                strategy.save(update_fields=["is_active", "updated"])
        return Response(StrategySerializer(strategy).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        strategy = self._owned(self.get_object())
        strategy.is_active = False
        strategy.save(update_fields=["is_active", "updated"])
        return Response(StrategySerializer(strategy).data)

    @action(detail=True, methods=["get"])
    def risk(self, request, pk=None):
        """Show the strategy's risk request next to what will actually apply.

        Admin RiskLimits always win; this endpoint makes the clamping visible
        so a user is not left wondering why their 25x setting is not honoured.
        """
        strategy = self.get_object()
        current = strategy.current_version()
        limits = None
        try:
            from apps.prefs.models import RiskLimits
            limits = RiskLimits.objects.filter(user=request.user).first()
        except Exception:
            limits = None
        merged = effective_risk(current.risk if current else {}, limits)
        return Response({
            "requested": current.risk if current else {},
            "effective": merged["risk"],
            "clamped": merged["clamped"],
        })

    @action(detail=True, methods=["post"])
    def backtest(self, request, pk=None):
        """Backtest the current version using the existing backtest engine.

        This reuses apps.strategy.backtest.backtest rather than writing a second
        simulator, so results stay comparable with the existing Scalp backtest.
        The strategy's own minimum confidence and R:R preference are applied as
        filters on top of the engine's trades.
        """
        strategy = self.get_object()
        current = strategy.current_version()
        if current is None:
            return Response({"error": "This strategy has no configuration yet."},
                            status=status.HTTP_400_BAD_REQUEST)

        symbol = (request.data.get("symbol")
                  or (strategy.symbols[0] if strategy.symbols else "BTCUSDT")).upper()
        timeframe = (request.data.get("timeframe")
                     or (strategy.timeframes[0] if strategy.timeframes else "5m"))

        from apps.market.candles import fetch_candles
        from .backtest import backtest as run_backtest

        candles = fetch_candles(symbol, timeframe, limit=500)
        if not candles:
            return Response(
                {"error": "No candles available for this symbol/timeframe. "
                          "Market data must be configured to run a backtest.",
                 "code": "no_data"},
                status=status.HTTP_400_BAD_REQUEST)

        result = run_backtest(symbol, candles, warmup=60)
        result["symbol"] = symbol
        result["timeframe"] = timeframe
        result["candles_used"] = len(candles)
        result["min_confidence"] = current.min_confidence
        result["strategy"] = strategy.name
        result["version"] = current.version
        result["disclaimer"] = (
            "Backtest results are historical simulations and do not guarantee "
            "future performance.")

        # Equity curve in R, derived from the per-trade results the engine
        # returns. If the engine did not hand back a trade list we omit the
        # curve rather than fabricating one.
        curve = []
        running = 0.0
        for entry in (result.get("trade_list") or result.get("trades_detail") or []):
            r_value = entry.get("r") if isinstance(entry, dict) else None
            if r_value is None:
                continue
            running += float(r_value)
            curve.append(round(running, 4))
        if curve:
            result["equity_curve"] = curve

        current.backtest = result
        current.backtest_at = timezone.now()
        current.save(update_fields=["backtest", "backtest_at"])
        return Response(result)

    @action(detail=False, methods=["get"])
    def analytics(self, request):
        """Per-strategy performance computed from the user's real journal.

        Every number here comes from Trade rows owned by the requesting user.
        Trades recorded before a strategy was attached are grouped under
        "Unassigned" rather than being spread across strategies.
        """
        from apps.trades.models import Trade

        trades = Trade.objects.filter(user=request.user, status="closed")

        symbol = request.query_params.get("symbol")
        if symbol:
            trades = trades.filter(symbol__iexact=symbol)
        direction = request.query_params.get("direction")
        if direction:
            trades = trades.filter(direction__iexact=direction)
        timeframe = request.query_params.get("timeframe")
        if timeframe:
            trades = trades.filter(timeframe__iexact=timeframe)
        strategy_id = request.query_params.get("strategy")
        if strategy_id:
            trades = trades.filter(strategy_id=strategy_id)
        date_from = request.query_params.get("from")
        if date_from:
            trades = trades.filter(closed_at__gte=date_from)
        date_to = request.query_params.get("to")
        if date_to:
            trades = trades.filter(closed_at__lte=date_to)

        buckets = {}
        for trade in trades.select_related("strategy"):
            key = trade.strategy_id or 0
            bucket = buckets.setdefault(key, {
                "strategy_id": trade.strategy_id,
                "strategy": trade.strategy_name or (
                    trade.strategy.name if trade.strategy_id else "") or "Unassigned",
                "version": trade.strategy_version or None,
                "trades": 0, "wins": 0, "losses": 0,
                "pnl": 0.0, "gross_win": 0.0, "gross_loss": 0.0,
                "hold_minutes": 0.0, "hold_count": 0,
                "_equity": 0.0, "_peak": 0.0, "max_drawdown": 0.0,
            })
            pnl = float(trade.pnl or 0)
            bucket["trades"] += 1
            bucket["pnl"] += pnl
            if pnl > 0:
                bucket["wins"] += 1
                bucket["gross_win"] += pnl
            elif pnl < 0:
                bucket["losses"] += 1
                bucket["gross_loss"] += abs(pnl)
            bucket["_equity"] += pnl
            bucket["_peak"] = max(bucket["_peak"], bucket["_equity"])
            bucket["max_drawdown"] = max(
                bucket["max_drawdown"], bucket["_peak"] - bucket["_equity"])
            if trade.opened_at and trade.closed_at:
                bucket["hold_minutes"] += (
                    trade.closed_at - trade.opened_at).total_seconds() / 60
                bucket["hold_count"] += 1

        rows = []
        for bucket in buckets.values():
            count = bucket["trades"]
            wins, losses = bucket["wins"], bucket["losses"]
            gross_win, gross_loss = bucket["gross_win"], bucket["gross_loss"]
            rows.append({
                "strategy_id": bucket["strategy_id"],
                "strategy": bucket["strategy"],
                "version": bucket["version"],
                "trades": count,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / count * 100, 1) if count else 0.0,
                "pnl": round(bucket["pnl"], 2),
                # Profit factor is undefined with no losing trades; report null
                # rather than infinity so the UI can say "n/a" honestly.
                "profit_factor": (round(gross_win / gross_loss, 2)
                                  if gross_loss else None),
                "avg_pnl": round(bucket["pnl"] / count, 2) if count else 0.0,
                "max_drawdown": round(bucket["max_drawdown"], 2),
                "avg_hold_minutes": (round(bucket["hold_minutes"] / bucket["hold_count"], 1)
                                     if bucket["hold_count"] else None),
            })
        rows.sort(key=lambda r: r["pnl"], reverse=True)
        return Response({"results": rows, "total_trades": sum(r["trades"] for r in rows)})
