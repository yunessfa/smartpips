"""Paper-trading ("demo") storage for the Bitunix panel.

Real mode talks to Bitunix; demo mode fills orders against LIVE Bitunix
prices but keeps everything in our DB — same request shape, zero risk. TP/SL
on demo positions are evaluated lazily every time positions are read (good
enough for a journal-grade simulator; an exchange-grade matcher is explicitly
NOT the goal here).
"""
from django.conf import settings
from django.db import models


# Bitunix taker fee (~0.06%); round-trip = open + close.
#
# 2026-09: the fee is NO LONGER deducted from demo PnL. The demo tab now shows
# the same gross number the manual "test" journal shows, so the two can never
# disagree, and the fee travels to the UI as an ESTIMATE for display only
# (`round_trip_fee`). Set DEMO_PNL_NET_OF_FEES=1 to restore the old behaviour.
FEE_RATE = 0.0006


def _net_of_fees_enabled():
    import os
    return str(os.getenv("DEMO_PNL_NET_OF_FEES", "")).lower() in ("1", "true", "yes")


class DemoPosition(models.Model):
    SIDE_CHOICES = [("LONG", "LONG"), ("SHORT", "SHORT")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="bitunix_demo_positions")
    symbol = models.CharField(max_length=24)
    side = models.CharField(max_length=8, choices=SIDE_CHOICES)
    qty = models.FloatField()                       # base coin
    entry_price = models.FloatField()
    leverage = models.PositiveIntegerField(default=1)
    margin = models.FloatField(default=0)           # USDT committed
    tp_price = models.FloatField(null=True, blank=True)
    sl_price = models.FloatField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    # set when closed (by user, TP, or SL)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_price = models.FloatField(null=True, blank=True)
    close_reason = models.CharField(max_length=16, blank=True)  # manual|tp|sl
    realized_pnl = models.FloatField(null=True, blank=True)
    # journal mirror: every Bitunix trade (demo or real) also lives in the
    # main Trade journal; this links the demo position to its journal row so
    # closes (manual/tp/sl/liq) close the journal entry too.
    journal_trade_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    @property
    def is_open(self):
        return self.closed_at is None

    def round_trip_fee(self, exit_price):
        """Taker fee for opening and closing this position."""
        notional_in = self.qty * self.entry_price
        notional_out = self.qty * (exit_price if exit_price else self.entry_price)
        return round((notional_in + notional_out) * FEE_RATE, 6)

    def gross_pnl(self, price):
        """Raw price move x quantity. No fee, no adjustment — this is the number
        that must move the instant the price moves."""
        if price is None:
            return None
        d = (price - self.entry_price) if self.side == "LONG" else (self.entry_price - price)
        return round(d * self.qty, 4)

    def unrealized_pnl(self, price):
        """PnL as shown in the app: GROSS by default.

        The round-trip fee is still calculated (`round_trip_fee`) and sent to
        the UI beside this number, but it is not subtracted here.
        """
        gross = self.gross_pnl(price)
        if gross is None:
            return None
        if _net_of_fees_enabled():
            return round(gross - self.round_trip_fee(price), 4)
        return gross

    @property
    def liq_price(self):
        """Isolated-margin liquidation estimate: the price where loss eats
        ~95% of the committed margin (maintenance margin approximated)."""
        if not self.leverage:
            return None
        frac = 0.95 / self.leverage
        return round(self.entry_price * (1 - frac) if self.side == "LONG"
                     else self.entry_price * (1 + frac), 8)

    def check_tp_sl(self, price):
        """Return 'liq'|'sl'|'tp'|None for the given live price — liquidation
        wins over SL/TP, exactly like a real isolated position."""
        if price is None or not self.is_open:
            return None
        liq = self.liq_price
        if self.side == "LONG":
            if liq and price <= liq:
                return "liq"
            if self.sl_price and price <= self.sl_price:
                return "sl"
            if self.tp_price and price >= self.tp_price:
                return "tp"
        else:
            if liq and price >= liq:
                return "liq"
            if self.sl_price and price >= self.sl_price:
                return "sl"
            if self.tp_price and price <= self.tp_price:
                return "tp"
        return None
