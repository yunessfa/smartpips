from django.conf import settings
from django.db import models


class MT5Account(models.Model):
    """Latest account snapshot pushed by the EA (one row per login, demo = 1)."""
    login = models.CharField(max_length=40, default="demo", unique=True)
    broker = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    balance = models.FloatField(default=0)
    equity = models.FloatField(default=0)
    margin = models.FloatField(default=0)
    free_margin = models.FloatField(default=0)
    leverage = models.IntegerField(default=0)
    profit = models.FloatField(default=0)
    # broker symbol names as the EA discovered them
    gold_symbol = models.CharField(max_length=40, blank=True)
    silver_symbol = models.CharField(max_length=40, blank=True)
    updated = models.DateTimeField(auto_now=True)


class MT5Quote(models.Model):
    """Latest bid/ask per canonical symbol (XAUUSD / XAGUSD)."""
    symbol = models.CharField(max_length=20, unique=True)
    bid = models.FloatField(default=0)
    ask = models.FloatField(default=0)
    spread = models.FloatField(default=0)
    updated = models.DateTimeField(auto_now=True)


class MT5Candles(models.Model):
    """Latest OHLC candles per symbol+timeframe, stored as JSON, pushed by the EA."""
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    candles = models.JSONField(default=list)  # [{time,open,high,low,close,volume}, ...]
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("symbol", "timeframe")


class MT5Order(models.Model):
    """An order queued by the app for the EA to execute, then acknowledged."""
    STATUS = [("pending", "pending"), ("filled", "filled"),
              ("rejected", "rejected"), ("error", "error")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="mt5_orders")
    symbol = models.CharField(max_length=20)       # canonical (XAUUSD/XAGUSD)
    action = models.CharField(max_length=4)         # buy / sell
    volume = models.FloatField(default=0.01)        # lots
    stop_loss = models.FloatField(null=True, blank=True)
    take_profit = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    ticket = models.BigIntegerField(null=True, blank=True)   # broker ticket once filled
    message = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class MT5Tick(models.Model):
    """Rolling buffer of recent ticks from the cTrader bridge, used to build REAL
    order flow (bid/ask movement -> buy/sell pressure & delta) for metals, the
    way we already get real volume for crypto from Binance."""
    symbol = models.CharField(max_length=20, db_index=True)
    bid = models.FloatField(default=0)
    ask = models.FloatField(default=0)
    # +1 if the trade printed at/above the ask (buyer aggressor), -1 at/below bid
    tick_dir = models.SmallIntegerField(default=0)
    ts = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["symbol", "ts"])]
