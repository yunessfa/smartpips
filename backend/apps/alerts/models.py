from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """A browser Web-Push subscription belonging to a user (one per device)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="push_subscriptions",
        on_delete=models.CASCADE,
    )
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    def as_subscription_info(self):
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    def __str__(self):
        return f"{self.user} · {self.endpoint[:40]}"


class WatchItem(models.Model):
    """A symbol the user wants the system to watch across ALL timeframes and push a
    notification when a strong setup appears — so they don't have to stare at charts.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="watchlist", on_delete=models.CASCADE,
    )
    symbol = models.CharField(max_length=20)
    min_score = models.IntegerField(default=68)   # only alert on B-grade or better
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "symbol")

    def __str__(self):
        return f"{self.user} watches {self.symbol}"


class Notification(models.Model):
    """An internal, per-user notification row.

    This is deliberately separate from Web Push. Push is a *delivery channel*
    that can be unavailable (no VAPID keys, permission denied, iOS without an
    installed PWA, browser closed). The notification centre must still work in
    all of those cases, so every alert is persisted here first and pushed only
    as a best-effort extra.
    """

    CATEGORIES = [
        ("system", "System"),
        ("trading", "Trading"),
        ("pnl", "PnL"),
        ("signal", "Signal"),
        ("position", "Position"),
        ("risk", "Risk"),
    ]
    LEVELS = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("danger", "Danger"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE,
    )
    category = models.CharField(max_length=12, choices=CATEGORIES, default="system")
    level = models.CharField(max_length=8, choices=LEVELS, default="info")
    title = models.CharField(max_length=140)
    body = models.TextField(blank=True)
    # Where tapping the notification should land, e.g. "/app/trades".
    url = models.CharField(max_length=300, blank=True)
    symbol = models.CharField(max_length=20, blank=True)
    trade = models.ForeignKey(
        "trades.Trade", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notifications",
    )
    rule = models.ForeignKey(
        "alerts.AlertRule", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notifications",
    )
    # Free-form extras (score, entry, pnl at trigger time...) for the UI.
    meta = models.JSONField(default=dict, blank=True)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        # Names are explicit so the hand-written migration matches the model
        # exactly (Django would otherwise auto-generate hashed index names).
        indexes = [
            models.Index(fields=["user", "read"], name="alerts_note_user_read_idx"),
            models.Index(fields=["user", "category"], name="alerts_note_user_cat_idx"),
        ]

    def __str__(self):
        return f"{self.user} · {self.title}"


class AlertRule(models.Model):
    """A user-defined condition on their own open positions.

    Deliberately *advisory*: firing a rule creates a notification and nothing
    else. It never closes, modifies or hedges a position. The user decides what
    to do from the notification, which is why the payload carries a deep link
    to the trade rather than an action.

    Conditions are a fixed vocabulary rather than a user-supplied expression,
    so nothing user-provided is ever evaluated as code.
    """

    SCOPE_ANY = "any"
    SCOPE_SYMBOL = "symbol"
    SCOPE_TRADE = "trade"
    SCOPES = [
        (SCOPE_ANY, "Any open trade"),
        (SCOPE_SYMBOL, "A specific symbol"),
        (SCOPE_TRADE, "One specific trade"),
    ]

    CONDITIONS = [
        ("pnl_above", "PnL at or above (USDT)"),
        ("pnl_below", "PnL at or below (USDT)"),
        ("pnl_pct_above", "PnL % at or above"),
        ("pnl_pct_below", "PnL % at or below"),
        ("price_above", "Price at or above"),
        ("price_below", "Price at or below"),
        ("reaches_tp", "Price reaches take profit"),
        ("reaches_sl", "Price reaches stop loss"),
        ("move_pct_from_entry", "Price moved % from entry"),
        ("open_longer_than", "Trade open longer than (minutes)"),
    ]
    # Conditions whose threshold field is meaningless (TP/SL come from the trade).
    NO_THRESHOLD = {"reaches_tp", "reaches_sl"}

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="alert_rules", on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=80, blank=True)
    scope = models.CharField(max_length=8, choices=SCOPES, default=SCOPE_ANY)
    symbol = models.CharField(max_length=20, blank=True)
    trade = models.ForeignKey(
        "trades.Trade", null=True, blank=True, on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    condition = models.CharField(max_length=24, choices=CONDITIONS, default="pnl_above")
    threshold = models.FloatField(default=0)
    enabled = models.BooleanField(default=True)
    # Also attempt a browser push when this fires (internal row is always made).
    push = models.BooleanField(default=True)
    # Fire once per crossing instead of once per evaluation pass.
    once_per_crossing = models.BooleanField(default=True)

    trigger_count = models.PositiveIntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def describe(self):
        label = dict(self.CONDITIONS).get(self.condition, self.condition)
        if self.condition in self.NO_THRESHOLD:
            return label
        return f"{label} {self.threshold:g}"

    def __str__(self):
        return f"{self.user} · {self.name or self.describe()}"


class AlertRuleState(models.Model):
    """Per (rule, trade) latch used to stop a fired alert repeating every pass.

    Without this, a rule like "PnL >= +25" would notify on every monitor tick
    for as long as the position stayed above the threshold. The latch is set
    when the condition becomes true and cleared once it goes false again, so
    the user gets exactly one message per crossing.
    """

    rule = models.ForeignKey(AlertRule, related_name="states", on_delete=models.CASCADE)
    trade = models.ForeignKey(
        "trades.Trade", related_name="alert_states", on_delete=models.CASCADE,
    )
    latched = models.BooleanField(default=False)
    last_value = models.FloatField(null=True, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("rule", "trade")

    def __str__(self):
        return f"rule {self.rule_id} · trade {self.trade_id} · latched={self.latched}"


class SignalState(models.Model):
    """Remembers the last emitted signal per symbol+timeframe so the monitor only
    notifies when a NEW opportunity appears (no spamming the same setup)."""

    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    last_signal = models.CharField(max_length=8, default="wait")
    last_score = models.IntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("symbol", "timeframe")

    def __str__(self):
        return f"{self.symbol} {self.timeframe} -> {self.last_signal}"
