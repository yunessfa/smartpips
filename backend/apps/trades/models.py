from django.conf import settings
from django.db import models


class Trade(models.Model):
    DIRECTION = [("long", "Long"), ("short", "Short")]
    STATUS = [("open", "Open"), ("closed", "Closed")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="trades", on_delete=models.CASCADE
    )

    symbol = models.CharField(max_length=40)                # e.g. BTCUSDT
    tradingview_symbol = models.CharField(max_length=60, blank=True)
    direction = models.CharField(max_length=8, choices=DIRECTION, default="long")

    entry_price = models.FloatField()
    exit_price = models.FloatField(null=True, blank=True)
    take_profit = models.FloatField(null=True, blank=True)
    stop_loss = models.FloatField(null=True, blank=True)

    # Optional 3-level partial take-profit plan. When set, auto_close closes a
    # PORTION of the position at each level instead of the whole trade at once —
    # so a position is still managed (partially banked, stop trailed) even if the
    # user isn't watching. tp_done tracks which levels have already fired.
    tp1_price = models.FloatField(null=True, blank=True)
    tp1_pct = models.FloatField(default=40)
    tp1_done = models.BooleanField(default=False)
    tp2_price = models.FloatField(null=True, blank=True)
    tp2_pct = models.FloatField(default=35)
    tp2_done = models.BooleanField(default=False)
    tp3_price = models.FloatField(null=True, blank=True)
    tp3_pct = models.FloatField(default=25)
    tp3_done = models.BooleanField(default=False)
    # remaining fraction of the ORIGINAL size still open (1.0 = nothing closed yet)
    remaining_pct = models.FloatField(default=100)
    # realised P&L banked so far from partial closes (added to final pnl on full close)
    realized_pnl = models.FloatField(default=0)

    # Position size in quote currency (e.g. USDT margin the user committed).
    size = models.FloatField(default=0)
    leverage = models.FloatField(default=1)

    status = models.CharField(max_length=8, choices=STATUS, default="open")

    # Realised P&L (filled when the trade is closed).
    pnl = models.FloatField(null=True, blank=True)
    pnl_percent = models.FloatField(null=True, blank=True)

    # Where the idea came from (e.g. "assistant" or "manual").
    source = models.CharField(max_length=20, default="manual")
    setup_class = models.CharField(max_length=30, blank=True)  # e.g. trend_continuation
    notes = models.TextField(blank=True)

    # --- Attribution -------------------------------------------------------
    # Which configured strategy produced this trade. The FK is SET_NULL and the
    # name/version are ALSO stored as plain text on purpose: a strategy can be
    # archived or renamed years later, and journal history must still say what
    # actually generated the trade. Trades opened before this feature (or by
    # hand) simply leave these blank and are reported as "Unassigned".
    strategy = models.ForeignKey(
        "strategy.Strategy", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="trades",
    )
    strategy_name = models.CharField(max_length=80, blank=True)
    strategy_version = models.PositiveIntegerField(null=True, blank=True)

    # Context the engine had at entry, shown in the trade detail view.
    timeframe = models.CharField(max_length=10, blank=True)      # e.g. "5m"
    confidence = models.FloatField(null=True, blank=True)        # 0-100 at entry
    exit_reason = models.CharField(max_length=40, blank=True)    # tp1 / sl / manual / ...

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def compute_pnl(self):
        """Return (pnl_quote, pnl_percent) for the current/exit price.

        Percentage is on the raw price move; pnl_quote scales it by the
        leveraged notional (size * leverage).
        """
        if self.exit_price is None or not self.entry_price:
            return None, None
        if self.direction == "long":
            move = (self.exit_price - self.entry_price) / self.entry_price
        else:
            move = (self.entry_price - self.exit_price) / self.entry_price
        pct = move * 100 * (self.leverage or 1)
        notional = (self.size or 0) * (self.leverage or 1)
        pnl = notional * move
        return round(pnl, 4), round(pct, 4)

    def close(self, exit_price):
        from django.utils import timezone

        self.exit_price = exit_price
        pnl, pct = self.compute_pnl()
        # fold in whatever was already banked from earlier partial TP hits
        self.pnl = round((pnl or 0) + (self.realized_pnl or 0), 4)
        self.pnl_percent = pct
        self.status = "closed"
        self.closed_at = timezone.now()
        self.save()

    def close_partial(self, exit_price, pct_of_original, level_field):
        """Bank profit on a PORTION of the position (a TP1/TP2/TP3 hit) without
        fully closing the trade. Reduces remaining_pct and stores the realised
        P&L for that slice; the rest of the position keeps running toward the
        next level or the stop."""
        if self.direction == "long":
            move = (exit_price - self.entry_price) / self.entry_price
        else:
            move = (self.entry_price - exit_price) / self.entry_price
        notional = (self.size or 0) * (self.leverage or 1)
        slice_pnl = notional * move * (pct_of_original / 100.0)

        self.realized_pnl = round((self.realized_pnl or 0) + slice_pnl, 4)
        self.remaining_pct = round(max(0, (self.remaining_pct or 100) - pct_of_original), 2)
        setattr(self, level_field, True)  # e.g. tp1_done = True

        if self.remaining_pct <= 0.5:
            # all three slices banked -> fully close at this last level's price
            self.close(exit_price)
        else:
            self.save()
        return slice_pnl

    def __str__(self):
        return f"{self.direction} {self.symbol} @ {self.entry_price}"
