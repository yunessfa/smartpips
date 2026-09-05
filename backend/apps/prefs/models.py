"""Per-user product access, managed from the admin panel.

Which market groups a user may see/trade on the Scalp page:
metals (XAU/XAG), crypto spot, crypto futures. Defaults: everything on —
rows are created lazily, so existing users need no backfill.
"""
from django.conf import settings
from django.db import models


class MarketAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="market_access")
    allow_metals = models.BooleanField(default=True)
    allow_spot = models.BooleanField(default=True)
    allow_futures = models.BooleanField(default=True)

    def as_dict(self):
        return {"metals": self.allow_metals, "spot": self.allow_spot,
                "futures": self.allow_futures}

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj


class RiskLimits(models.Model):
    """Per-user hard ceilings for REAL Bitunix orders, enforced server-side.
    Defaults are conservative; admins raise them per user. daily_loss_limit is
    a kill-switch: once realized REAL losses today exceed it, real orders are
    blocked until tomorrow (UTC)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="risk_limits")
    max_leverage = models.PositiveIntegerField(default=20)
    max_position_usdt = models.FloatField(default=500)      # notional cap per order
    max_open_positions = models.PositiveIntegerField(default=5)
    daily_loss_limit_usdt = models.FloatField(default=100)  # kill-switch, 0 = off
    real_trading_enabled = models.BooleanField(default=True)

    def as_dict(self):
        return {"max_leverage": self.max_leverage,
                "max_position_usdt": self.max_position_usdt,
                "max_open_positions": self.max_open_positions,
                "daily_loss_limit_usdt": self.daily_loss_limit_usdt,
                "real_trading_enabled": self.real_trading_enabled}

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj

    def today_realized_loss(self, user):
        """Sum of today's REAL realized losses (positive number = loss)."""
        from datetime import datetime, timezone as _tz
        from apps.trades.models import Trade
        start = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = Trade.objects.filter(user=user, source="bitunix_real",
                                    status="closed", closed_at__gte=start)
        loss = sum(min(0.0, (t.pnl or 0)) for t in rows)
        return round(-loss, 2)

    def check_order(self, user, *, leverage, notional):
        """Return an error string if this REAL order breaches a limit, else None."""
        if not self.real_trading_enabled:
            return "Real trading is disabled for this account by the admin."
        if leverage and leverage > self.max_leverage:
            return f"Leverage {leverage}x exceeds your limit ({self.max_leverage}x)."
        if notional and notional > self.max_position_usdt:
            return (f"Position value {notional:.0f} USDT exceeds your limit "
                    f"({self.max_position_usdt:.0f} USDT).")
        from apps.trades.models import Trade
        open_real = Trade.objects.filter(user=user, source="bitunix_real",
                                         status="open").count()
        if open_real >= self.max_open_positions:
            return f"You already have {open_real} open real positions (max {self.max_open_positions})."
        if self.daily_loss_limit_usdt > 0:
            lost = self.today_realized_loss(user)
            if lost >= self.daily_loss_limit_usdt:
                return (f"Daily loss limit reached ({lost:.0f}/{self.daily_loss_limit_usdt:.0f} "
                        f"USDT). Real trading is paused until tomorrow (UTC).")
        return None
