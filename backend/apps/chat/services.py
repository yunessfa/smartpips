"""
Builds the system prompt (live prices + sources + news + indicators + telegram
signals + the user's own trade history) and parses the assistant's reply.
"""
import json
import re

from apps.sources.models import Source
from apps.sources.services import gather_news
from apps.market.models import Asset
from apps.market.services import get_quotes
from apps.strategy.models import Indicator
from apps.strategy.services import gather_telegram_signals

DISCLAIMER = (
    "This is an AI-generated market analysis for educational purposes only. "
    "It is NOT financial advice."
)

SYSTEM_TEMPLATE = """You are SmartPips, a professional crypto and markets analysis assistant inside a trading dashboard.

CRITICAL RULE ABOUT PRICES:
The LIVE MARKET SNAPSHOT below is the ONLY source of truth for current prices.
- Never invent or recall prices from memory. If a number isn't in the snapshot,
  say you don't have a live price for it rather than guessing.
- If the snapshot says prices are UNAVAILABLE/fallback, clearly tell the user you
  can't confirm a live price right now, and keep any levels clearly hypothetical.
- Base every entry / take-profit / stop-loss on the live price shown.

WORKFLOW for every answer:
1. Scan RECENT NEWS and TELEGRAM SIGNALS. If anything is relevant, summarise it
   briefly and name the source BEFORE your analysis. If nothing is relevant, say so.
2. Analyse using the INDICATORS the user configured. For EACH relevant indicator,
   state what it currently implies (e.g. "RSI ~ overbought", "price above EMA200 = uptrend").
3. Identify concrete levels: trend, momentum, key support & resistance, and a
   bullish vs bearish scenario.
4. Consider the USER'S TRADE HISTORY to match their style (direction bias,
   typical leverage, risk size) when proposing ideas.
5. Then give trade ideas anchored to the live price.

Be thorough and specific. The "reply" field should be a complete, well-structured
analysis (several short paragraphs), not one or two sentences. Use the user's
language. Give real numbers from the live snapshot, not vague statements.

CORRECT TradingView symbols to use in "tradingview_symbol":
- Crypto: BINANCE:<PAIR>  e.g. BINANCE:BTCUSDT, BINANCE:ETHUSDT
- Gold: TVC:GOLD   ·   Silver: TVC:SILVER
- Never put metals on BINANCE (BINANCE:XAUUSD is invalid and the chart will break).

Answer ONLY with a single valid JSON object, no markdown, with this shape:

{{
  "reply": "<news (if any) + indicator-based analysis, in the user's language>",
  "news_used": [
    {{"title": "<headline>", "source": "<source name>", "link": "<url>"}}
  ],
  "recommendations": [
    {{
      "symbol": "BTCUSDT",
      "tradingview_symbol": "BINANCE:BTCUSDT",
      "action": "buy" | "sell" | "hold",
      "entry": "<price or range near the live price>",
      "take_profit": "<price or range>",
      "stop_loss": "<price>",
      "timeframe": "<e.g. 4h / 1d>",
      "confidence": "low" | "medium" | "high",
      "indicators_used": ["RSI", "Fibonacci"],
      "rationale": "<one or two sentences citing the indicators>"
    }}
  ]
}}

Rules:
- General chit-chat -> empty "recommendations" and empty "news_used".
- Only cite news/signals that actually appear below.
- Be honest about uncertainty; never promise profits.
- End "reply" with this disclaimer on its own line: "{disclaimer}"

=== LIVE MARKET SNAPSHOT ({price_status}) ===
{market}

=== INDICATORS TO USE ===
{indicators}

=== ACTIVE REFERENCE SOURCES ===
{sources}

=== RECENT NEWS FROM THOSE SOURCES ===
{news}

=== TELEGRAM SIGNALS ===
{telegram}

=== USER'S RECENT TRADES (their trading style) ===
{trades}
"""


def _market_block():
    watched = Asset.objects.filter(is_watched=True)
    quotes = get_quotes(watched)
    if not quotes:
        return "- (no assets tracked yet)", "no data"
    is_mock = any(q.get("source") == "mock" for q in quotes)
    lines = "\n".join(
        f"- {q['name']} [{q['symbol']}]: price {q['price']} USD, "
        f"24h change {q['change_percent']}%"
        for q in quotes
    )
    status = "FALLBACK / UNVERIFIED" if is_mock else "live"
    return lines, status


def _indicators_block():
    indicators = Indicator.objects.filter(is_active=True)
    if not indicators:
        return "- (none configured — use standard price action)"
    return "\n".join(
        f"- {i.label}" + (f" ({i.settings})" if i.settings else "")
        + (f" — {i.notes}" if i.notes else "")
        for i in indicators
    )


def _sources_block():
    active = Source.objects.filter(is_active=True)
    if not active:
        return "- (none configured yet)"
    return "\n".join(
        f"- {s.name} ({s.get_source_type_display()}, trust {s.weight}/10): {s.url}"
        for s in active
    )


def _news_block():
    items = gather_news()
    if not items:
        return "- (no live news available right now)"
    return "\n".join(
        f"- [{n['source']}] {n['title']} ({n['link']})"
        + (f"\n    {n['summary']}" if n["summary"] else "")
        for n in items
    )


def _telegram_block():
    signals = gather_telegram_signals()
    if not signals:
        return "- (no telegram channels configured or reachable)"
    return "\n".join(f"- @{s['channel']}: {s['text']}" for s in signals)


def _trades_block(user):
    if user is None or not user.is_authenticated:
        return "- (no trade history)"
    from apps.trades.models import Trade

    recent = Trade.objects.filter(user=user)[:12]
    if not recent:
        return "- (user hasn't logged any trades yet)"
    lines = []
    for t in recent:
        base = f"- {t.direction.upper()} {t.symbol} @ {t.entry_price}, lev {t.leverage}x"
        if t.status == "closed" and t.pnl_percent is not None:
            base += f", closed {t.exit_price} -> {t.pnl_percent:+.1f}%"
        else:
            base += ", still open"
        lines.append(base)
    return "\n".join(lines)


def build_system_prompt(user=None) -> str:
    market, price_status = _market_block()
    return SYSTEM_TEMPLATE.format(
        disclaimer=DISCLAIMER,
        price_status=price_status,
        market=market,
        indicators=_indicators_block(),
        sources=_sources_block(),
        news=_news_block(),
        telegram=_telegram_block(),
        trades=_trades_block(user),
    )


def parse_assistant_reply(raw: str) -> dict:
    """Extract the JSON object from the model reply, tolerating stray text."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    candidates = [raw]
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "reply" in data:
                data.setdefault("recommendations", [])
                data.setdefault("news_used", [])
                return data
        except json.JSONDecodeError:
            continue

    return {"reply": raw, "recommendations": [], "news_used": []}
