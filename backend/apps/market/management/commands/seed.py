import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from apps.market.models import Asset
from apps.sources.models import Source
from apps.ai.models import AIProvider
from apps.strategy.models import Indicator, TelegramChannel


# The Groq API key is read from the GROQ_API_KEY environment variable (set it in
# your .env). It is intentionally NOT stored in the source.
DEFAULT_GROQ_KEY = ""

ASSETS = [
    ("Bitcoin", "BTCUSDT", "crypto", "BINANCE:BTCUSDT", "BTCUSDT"),
    ("Ethereum", "ETHUSDT", "crypto", "BINANCE:ETHUSDT", "ETHUSDT"),
    ("Solana", "SOLUSDT", "crypto", "BINANCE:SOLUSDT", "SOLUSDT"),
    ("BNB", "BNBUSDT", "crypto", "BINANCE:BNBUSDT", "BNBUSDT"),
    ("XRP", "XRPUSDT", "crypto", "BINANCE:XRPUSDT", "XRPUSDT"),
    # Metals use TVC symbols which render reliably in all TradingView widgets.
    ("Gold (XAU/USD)", "XAUUSD", "metal", "TVC:GOLD", ""),
    ("Silver (XAG/USD)", "XAGUSD", "metal", "TVC:SILVER", ""),
]

SOURCES = [
    ("Binance", "https://www.binance.com", "https://www.binance.com/en/feed/rss", "exchange", "Largest crypto exchange.", 9),
    ("CoinDesk", "https://www.coindesk.com", "https://www.coindesk.com/arc/outboundfeeds/rss/", "news", "Crypto news.", 7),
    ("Cointelegraph", "https://cointelegraph.com", "https://cointelegraph.com/rss", "news", "Crypto news & analysis.", 7),
    ("CoinMarketCap", "https://coinmarketcap.com", "", "data", "Market caps and metrics.", 6),
    ("Investing.com", "https://www.investing.com", "https://www.investing.com/rss/news.rss", "news", "Macro, metals & forex.", 6),
]

INDICATORS = [
    ("RSI (14)", "rsi", "length 14, OB 70 / OS 30"),
    ("MACD", "macd", "12/26/9"),
    ("EMA 50 / 200", "ema", "trend & golden/death cross"),
    ("Fibonacci Retracement", "fibonacci", "0.382 / 0.5 / 0.618"),
    ("Support / Resistance", "support_resistance", "recent swing levels"),
]


class Command(BaseCommand):
    help = "Seed starter assets, sources, indicators, the default Groq model and a demo user."

    def handle(self, *args, **options):
        for name, symbol, cat, tv, binance in ASSETS:
            obj, _ = Asset.objects.get_or_create(
                symbol=symbol,
                defaults={"name": name, "category": cat,
                          "tradingview_symbol": tv, "binance_symbol": binance},
            )
            # keep tradingview symbol up to date (e.g. metals fix)
            if obj.tradingview_symbol != tv:
                obj.tradingview_symbol = tv
                obj.save()
        self.stdout.write(self.style.SUCCESS(f"Assets ready ({Asset.objects.count()})"))

        for name, url, feed, stype, desc, weight in SOURCES:
            Source.objects.get_or_create(
                name=name,
                defaults={"url": url, "feed_url": feed, "source_type": stype,
                          "description": desc, "weight": weight},
            )
        self.stdout.write(self.style.SUCCESS(f"Sources ready ({Source.objects.count()})"))

        for label, key, settings in INDICATORS:
            Indicator.objects.get_or_create(
                label=label, defaults={"key": key, "settings": settings}
            )
        self.stdout.write(self.style.SUCCESS(f"Indicators ready ({Indicator.objects.count()})"))

        TelegramChannel.objects.get_or_create(
            username="binanceexchange",
            defaults={"title": "Binance (sample)", "is_active": False},
        )

        # Default AI model: Groq. The key comes from the GROQ_API_KEY env var.
        groq_key = os.getenv("GROQ_API_KEY", DEFAULT_GROQ_KEY)
        provider, _ = AIProvider.objects.get_or_create(label="Groq (default)")
        provider.provider_type = "groq"
        provider.base_url = "https://api.groq.com/openai"
        provider.model = "llama-3.3-70b-versatile"
        if groq_key:
            provider.api_key = groq_key
        # Only activate it if we actually have a key, so chat doesn't error out.
        provider.is_active = bool(provider.api_key)
        provider.temperature = 0.35
        provider.save()
        if provider.is_active:
            AIProvider.objects.exclude(pk=provider.pk).update(is_active=False)
            self.stdout.write(self.style.SUCCESS("Default Groq model configured and activated."))
        else:
            self.stdout.write(self.style.WARNING(
                "Groq model created but INACTIVE — set GROQ_API_KEY in .env (or add a "
                "key on the AI page) and activate it there."
            ))

        if not User.objects.filter(username="demo").exists():
            User.objects.create_user("demo", password="demo12345")
            self.stdout.write(self.style.SUCCESS(
                "Created demo user -> username: demo  password: demo12345"
            ))
        else:
            self.stdout.write("Demo user already exists.")
