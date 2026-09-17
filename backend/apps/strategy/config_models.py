"""Configurable strategies layered ON TOP of the deterministic engine.

Design
------
The existing `apps.strategy.engine.run_strategy` stays exactly as it is: it is
the thing that actually reads candles and produces market structure, liquidity,
order flow, EMA/RSI/MACD/VWAP/ATR readings and a signal. A Strategy here does
not replace any of that. It is a *configuration* that says which of those
findings matter, how much each is worth, and what confidence is required before
a signal is worth acting on.

Why structured JSON and never code
----------------------------------
A rule is `{block, operator, value}` drawn from a closed vocabulary declared in
`rule_schema.py`. Nothing the user types is ever evaluated, exec'd, eval'd or
imported. The evaluator walks the validated structure and compares numbers.

Versioning
----------
Editing a strategy creates a NEW `StrategyVersion` instead of mutating the old
one, and every trade records the version that produced it. Without that, the
journal answer to "which strategy performs best?" silently mixes results from
rules that no longer exist.
"""

from django.conf import settings
from django.db import models


class Strategy(models.Model):
    """A named strategy owned by a user, or a built-in preset (user=None)."""

    MARKETS = [("crypto", "Crypto"), ("forex", "Forex"), ("metals", "Metals")]
    DIRECTIONS = [("both", "Both"), ("long", "Long only"), ("short", "Short only")]

    # Presets are shared read-only rows with user=None so every account sees the
    # same library without duplicating eight rows per user.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="strategies", on_delete=models.CASCADE,
        null=True, blank=True,
    )
    preset_key = models.CharField(max_length=40, blank=True, db_index=True)

    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    market = models.CharField(max_length=8, choices=MARKETS, default="crypto")
    symbols = models.JSONField(default=list, blank=True)      # ["BTCUSDT", ...]
    timeframes = models.JSONField(default=list, blank=True)   # ["5m", "15m"]
    direction = models.CharField(max_length=6, choices=DIRECTIONS, default="both")

    # Only one strategy per user may be active at a time (enforced in the view
    # layer), matching how the engine is consumed: one decision context.
    is_active = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        indexes = [models.Index(fields=["user", "is_active"], name="strat_user_active_idx")]

    @property
    def is_preset(self):
        return self.user_id is None

    def current_version(self):
        return self.versions.order_by("-version").first()

    def __str__(self):
        owner = "preset" if self.is_preset else self.user
        return f"{self.name} ({owner})"


class StrategyVersion(models.Model):
    """An immutable snapshot of a strategy's rules, weights and risk settings."""

    strategy = models.ForeignKey(Strategy, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)

    # Validated against rule_schema.validate_rules() before saving.
    rules = models.JSONField(default=list, blank=True)
    # {"market_structure": 20, "liquidity": 20, ...} — percentages summing to 100.
    weights = models.JSONField(default=dict, blank=True)
    min_confidence = models.FloatField(default=70)

    # Strategy-level risk preferences. These are a CEILING REQUEST, not an
    # override: apps.prefs.RiskLimits still has the final say for real orders.
    risk = models.JSONField(default=dict, blank=True)

    # Filled by the backtest endpoint; a strategy may not be activated until a
    # backtest has been run against the version being activated.
    backtest = models.JSONField(default=dict, blank=True)
    backtest_at = models.DateTimeField(null=True, blank=True)

    notes = models.CharField(max_length=200, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        unique_together = ("strategy", "version")

    @property
    def label(self):
        return f"{self.strategy.name} v{self.version}"

    def __str__(self):
        return self.label
