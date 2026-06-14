from django.db import models


class Indicator(models.Model):
    """A technical indicator the assistant should factor into its analysis."""

    KEY_CHOICES = [
        ("rsi", "RSI"),
        ("macd", "MACD"),
        ("ema", "EMA"),
        ("sma", "SMA"),
        ("bollinger", "Bollinger Bands"),
        ("fibonacci", "Fibonacci Retracement"),
        ("stoch", "Stochastic"),
        ("ichimoku", "Ichimoku"),
        ("volume", "Volume"),
        ("support_resistance", "Support / Resistance"),
        ("custom", "Custom"),
    ]

    label = models.CharField(max_length=80)
    key = models.CharField(max_length=24, choices=KEY_CHOICES, default="rsi")
    # Free-form settings, e.g. "length 14, overbought 70" or "EMA 50/200".
    settings = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "label"]

    def __str__(self):
        return self.label


class TelegramChannel(models.Model):
    """A public Telegram channel the assistant reads recent posts from.

    Only PUBLIC channels are supported (read via the t.me/s/ web preview,
    no bot token needed). Private channels would require a bot + admin access.
    """

    username = models.CharField(max_length=100, help_text="Without @, e.g. 'whalepool'")
    title = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "username"]

    def clean_username(self):
        return self.username.lstrip("@").strip()

    def __str__(self):
        return f"@{self.username}"
