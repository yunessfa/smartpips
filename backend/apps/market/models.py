from django.db import models


class Asset(models.Model):
    """A tracked market instrument shown on the dashboard."""

    CATEGORY_CHOICES = [
        ("crypto", "Crypto"),
        ("metal", "Metal"),
        ("forex", "Forex"),
        ("stock", "Stock"),
        ("index", "Index"),
    ]

    symbol = models.CharField(max_length=32, unique=True, help_text="e.g. BTCUSDT")
    name = models.CharField(max_length=120, help_text="e.g. Bitcoin")
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default="crypto")
    # TradingView symbol, e.g. BINANCE:BTCUSDT or OANDA:XAUUSD
    tradingview_symbol = models.CharField(max_length=64, blank=True)
    # Binance ticker used to pull a live price (optional, crypto only).
    binance_symbol = models.CharField(max_length=32, blank=True)
    is_watched = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "symbol"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"
