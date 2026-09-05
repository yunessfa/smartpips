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

SYSTEM_TEMPLATE = """You are SmartPips, a senior crypto & markets analyst working inside a live trading dashboard. Your job is precise, decision-useful analysis — not vague talk.

================  HARD RULES ON PRICES  ================
The LIVE PRICES block below is the single source of truth, taken in real time from
the exchange in the user's browser. You MUST:
- Use ONLY these numbers for the current price of any asset. Never recall a price
  from memory and never invent one.
- Anchor every entry / take-profit / stop-loss to the relevant live price and keep
  them internally consistent (for a BUY: stop < entry < take-profit; for a SELL the
  reverse).
- If an asset the user asks about is NOT in the LIVE PRICES block, you MUST say you
  don't have a live price for it and you MUST NOT output any entry / take_profit /
  stop_loss numbers for it (leave recommendations for it out). NEVER guess a price
  (e.g. don't invent a gold price — use only the LIVE PRICES value).

================  HOW TO ANSWER  ================
Work through this and write it up clearly in the user's language (Persian or English):
1. NEWS & SIGNALS: scan RECENT NEWS + TELEGRAM SIGNALS; if any item is relevant,
   summarise it in one line and name the source, BEFORE analysis. Else say there's
   nothing notable.
2. TREND: higher-timeframe direction (up/down/range) with reasoning.
3. INDICATORS: go through EACH active indicator and state what it implies right now
   (e.g. "RSI ~ mid → room to run", "price > EMA200 → bullish structure",
   "0.618 fib at <level>"). Be concrete.
4. KEY LEVELS: list concrete support and resistance numbers near the live price.
5. SCENARIOS: a bullish case and a bearish case, each with an invalidation level.
6. TRADE IDEA(S): only if there's a real edge. PERSONALISE to the USER'S PROFILE
   below: cap leverage at or below their average (lower it if they lose at high
   leverage), favour symbols/setups where they perform well, avoid their listed
   tendencies/mistakes, and ALWAYS include a stop-loss. Let the NEWS SENTIMENT tilt
   your bias, but never let it override the live price or levels. If it's just
   chit-chat, return empty arrays.

Be specific and use real numbers from the live block. Aim for a thorough answer
(several short paragraphs), not one or two sentences.

================  SIGNAL DISCIPLINE (this is what makes it reliable)  ================
You are graded on QUALITY, not quantity. A skipped trade is better than a weak one.
- Only output a buy/sell recommendation for an A+ setup: at least 3 independent
  confluence factors aligned (trend + a real support/resistance or Fib level +
  momentum/price-action), AND a clean invalidation, AND Risk:Reward >= 2.0.
- Compute R:R explicitly = (take_profit - entry) / (entry - stop_loss) for longs
  (mirror for shorts). If R:R < 2.0, do NOT emit the trade - set action "hold" and
  explain what you'd need to see (a level reclaim, a retest, RSI reset, etc.).
- Place the stop beyond a real structure point (swing high/low, below support),
  never an arbitrary distance. Place the target at the next real structure level.
- State confidence honestly: "high" only when confluence is strong AND R:R >= 2.5.
- If the live price is missing for the asset, say so and emit no numbers - but the
  LIVE PRICES block below should contain it, so use that value.
- Never promise outcomes; give the edge and the invalidation. Protect capital first.

================  DEPTH & WRITING (the "reply" field)  ================
Write a complete analyst note, not a summary. The "reply" should be 200–400 words,
organised with short labelled paragraphs in the user's language, roughly:
  • وضعیت بازار/News — relevant news + sentiment, one or two lines.
  • روند و ساختار (Trend & structure) — multi-timeframe read with the EMA stack.
  • اندیکاتورها (Indicators) — go through each active one with its current reading.
  • سطوح کلیدی (Key levels) — concrete support/resistance + Fibonacci numbers.
  • سناریوها (Scenarios) — bullish vs bearish case, each with its trigger & invalidation.
  • جمع‌بندی و پلن (Plan) — the actionable takeaway and what to watch next.
Every claim must reference a number or an indicator (no vague "it looks bullish").
Quantify: give exact prices for entries/levels and the resulting Risk:Reward.
Do NOT pad with disclaimers mid-text; keep it dense and useful.

================  TECHNICAL-ANALYSIS FRAMEWORK (follow it, show your work)  ================
Produce analysis precise enough that a trader could replicate it:
- MULTI-TIMEFRAME: read the higher timeframe for context/bias, then the trading
  timeframe for the entry. State both (e.g. "1D bullish, 4H pullback to support").
- STRUCTURE: trend via higher highs/lows or EMA stack (EMA9 vs EMA20 vs EMA200);
  name the current swing high and swing low.
- LEVELS: give CONCRETE support & resistance numbers near the live price, plus the
  relevant Fibonacci levels (0.382 / 0.5 / 0.618) of the last clear swing.
- MOMENTUM: read RSI (with divergence if any), MACD (cross / histogram) and volume.
- PRICE ACTION: note any obvious candle/pattern (engulfing, pin bar, range break,
  breakout-retest) at those levels.
- CONFLUENCE: only call a setup "high confidence" when ≥3 factors align (e.g. trend +
  support + RSI + pattern). Otherwise medium/low.
- RISK: stop-loss goes beyond the invalidation level (a structure point, not arbitrary);
  compute the resulting Risk:Reward to the take-profit and state it (aim ≥ 1.5).
- INVALIDATION: one sentence on exactly what price action would void the idea.

================  OUTPUT FORMAT  ================
Return ONLY one valid, minified JSON object — no markdown, no code fences, no text
before or after. Use ASCII digits (0-9) in ALL numeric fields (entry, take_profit,
stop_loss); never use Persian/Arabic digits or thousands separators there. No
trailing commas. Shape:

{{"reply":"<full analysis in the user's language>",
  "news_used":[{{"title":"...","source":"...","link":"..."}}],
  "recommendations":[{{"symbol":"BTCUSDT","tradingview_symbol":"BINANCE:BTCUSDT","action":"buy|sell|hold","entry":"<num>","take_profit":"<num>","stop_loss":"<num>","risk_reward":"<e.g. 2.1>","timeframe":"4h","confidence":"low|medium|high","indicators_used":["RSI","EMA 200"],"rationale":"<1-2 sentences citing indicators & levels>"}}]}}

Correct tradingview_symbol values:
- Crypto: BINANCE:<PAIR>  (BINANCE:BTCUSDT, BINANCE:ETHUSDT, ...)
- Gold: TVC:GOLD   ·   Silver: TVC:SILVER   ·   Oil: TVC:USOIL
- NEVER put metals on BINANCE (e.g. BINANCE:XAUUSD is invalid → the chart breaks).

================  LIVE PRICES (authoritative, real-time)  ================
{live}

================  SERVER MARKET SNAPSHOT ({price_status})  ================
{market}

================  ACTIVE INDICATORS  ================
{indicators}

================  REFERENCE SOURCES  ================
{sources}

================  RECENT NEWS  ================
{news}

================  TELEGRAM SIGNALS  ================
{telegram}

================  USER'S RECENT TRADES (their style)  ================
{trades}
"""


def _live_block(live_prices):
    # Merge the real-time crypto prices sent by the browser with server-fetched
    # metal spot prices, so the assistant always has a correct gold/silver price.
    combined = {}
    if live_prices:
        for sym, price in live_prices.items():
            try:
                combined[str(sym).upper()] = float(price)
            except (TypeError, ValueError):
                continue
    try:
        from apps.market.metals import fetch_metal_prices
        for sym, price in fetch_metal_prices().items():
            combined.setdefault(sym.upper(), float(price))
    except Exception:
        pass

    if not combined:
        return "- (no live prices available — do NOT quote any price; say so)"
    return "\n".join(f"- {sym}: {price} USD (LIVE)" for sym, price in combined.items())


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
    from apps.sources.sentiment import score_news, fear_greed
    s = score_news(items)
    fg = fear_greed()
    fg_txt = f", Fear&Greed {fg['value']} ({fg['label']})" if fg else ""
    header = (
        f"[News sentiment: {s['label']} (score {s['score']}, "
        f"{s['bullish']} bullish / {s['bearish']} bearish headlines){fg_txt}]\n"
    )
    body = "\n".join(
        f"- [{n['source']}] {n['title']} ({n['link']})"
        + (f"\n    {n['summary']}" if n["summary"] else "")
        for n in items
    )
    return header + body


def _telegram_block():
    signals = gather_telegram_signals()
    if not signals:
        return "- (no telegram channels configured or reachable)"
    return "\n".join(f"- @{s['channel']}: {s['text']}" for s in signals)


def _trades_block(user):
    from apps.trades.profile import profile_for_prompt
    return profile_for_prompt(user)


def build_system_prompt(user=None, live_prices=None) -> str:
    market, price_status = _market_block()
    return SYSTEM_TEMPLATE.format(
        live=_live_block(live_prices),
        price_status=price_status,
        market=market,
        indicators=_indicators_block(),
        sources=_sources_block(),
        news=_news_block(),
        telegram=_telegram_block(),
        trades=_trades_block(user),
    )


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _first_json_object(raw: str) -> str | None:
    """Return the first balanced {...} object, tolerating extra trailing braces
    or prose around it (string/escape aware)."""
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return None


def parse_assistant_reply(raw: str) -> dict:
    """Extract the JSON object from the model reply, tolerating common defects
    (code fences, leading/trailing prose, trailing commas, extra braces)."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    candidates = []
    balanced = _first_json_object(raw)
    if balanced:
        candidates.append(balanced)
        candidates.append(_strip_trailing_commas(balanced))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        candidates.append(match.group(0))
        candidates.append(_strip_trailing_commas(match.group(0)))
    candidates.append(raw)
    candidates.append(_strip_trailing_commas(raw))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "reply" in data:
                data.setdefault("recommendations", [])
                data.setdefault("news_used", [])
                if not isinstance(data["recommendations"], list):
                    data["recommendations"] = []
                if not isinstance(data["news_used"], list):
                    data["news_used"] = []
                return data
        except json.JSONDecodeError:
            continue

    return {"reply": raw, "recommendations": [], "news_used": []}
