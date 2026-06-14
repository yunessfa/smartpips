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

    # Position size in quote currency (e.g. USDT margin the user committed).
    size = models.FloatField(default=0)
    leverage = models.FloatField(default=1)

    status = models.CharField(max_length=8, choices=STATUS, default="open")

    # Realised P&L (filled when the trade is closed).
    pnl = models.FloatField(null=True, blank=True)
    pnl_percent = models.FloatField(null=True, blank=True)

    # Where the idea came from (e.g. "assistant" or "manual").
    source = models.CharField(max_length=20, default="manual")
    notes = models.TextField(blank=True)

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
        self.pnl, self.pnl_percent = self.compute_pnl()
        self.status = "closed"
        self.closed_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.direction} {self.symbol} @ {self.entry_price}"
