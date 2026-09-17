"""Single source of truth for which crypto symbols SmartPips supports.

~50 liquid, well-known pairs on Binance (spot; most also on USD-M futures via
the ':PERP' suffix elsewhere in the app). Adding a coin here makes it show up
everywhere at once — candles, live price, scalp signals, watchlist alerts, and
position sizing all import this instead of keeping their own separate lists,
so there's exactly one place to extend the coin list.
"""

SUPPORTED_CRYPTO_BASE = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "DOT",
    "MATIC", "LTC", "AVAX", "LINK", "ATOM", "UNI", "XLM", "ETC", "FIL", "APT",
    "ARB", "OP", "NEAR", "INJ", "SUI", "SEI", "RNDR", "IMX", "AAVE", "MKR",
    "GRT", "SAND", "MANA", "EOS", "XTZ", "ALGO", "FTM", "THETA", "KAVA", "FLOW",
    "CHZ", "ENJ", "ZIL", "ONE", "HBAR", "VET", "ICP", "QNT", "EGLD", "CRV",
]

# Full USDT pair symbols, e.g. "BTCUSDT" — what the rest of the app works with.
SUPPORTED_CRYPTO = {f"{b}USDT" for b in SUPPORTED_CRYPTO_BASE}


def is_supported_crypto(symbol):
    """True if `symbol` (with or without ':PERP') is one we support."""
    base = (symbol or "").upper().replace(":PERP", "")
    return base in SUPPORTED_CRYPTO
