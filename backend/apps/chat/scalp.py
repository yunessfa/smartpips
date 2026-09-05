"""
Scalp explanation layer.

IMPORTANT ARCHITECTURE: the Python strategy engine (apps.strategy.engine) decides
buy/sell/wait, the levels, and the confidence score. GPT does NOT decide — it only
turns the engine's decision into a clear, human explanation. This makes signals
deterministic, testable and far more reliable than asking the model to "trade".
"""
import json
import re

NAMES = {"XAUUSD": "Gold (XAU/USD)", "XAGUSD": "Silver (XAG/USD)"}

EXPLAIN_SYSTEM = """You are SmartPips SCALP mentor for {name} on the {timeframe} timeframe.

A separate quantitative engine has ALREADY decided the trade from real indicators
(EMA stack, VWAP, RSI, MACD, Stochastic, SMC structure: BOS/CHOCH/MSS/FVG/liquidity,
order-flow pressure/delta, liquidity sweeps, order blocks, premium/discount zones,
and key levels: previous-day high/low (PDH/PDL) and Asian high/low (AH/AL)),
multi-timeframe agreement, the market session and a volatility-adaptive risk
manager. Your job is ONLY to EXPLAIN that decision like a trading mentor — do NOT
change the signal, entry, take-profit, stop-loss or confidence, and do NOT invent
numbers.

Write in the user's language (Persian if they use Persian). Structure it like a
mentor briefing, not a dry line:
  - one sentence on the market context (trend / session).
  - "reasons to enter" as a short bullet checklist using the engine's data: cite
    things like BOS/CHOCH, unfilled FVG, liquidity (equal highs/lows), EMA/VWAP
    alignment, RSI/MACD, higher-timeframe agreement, and the session quality.
  - "risks" as a short bullet checklist (nearby support/resistance, weak score,
    quiet session, news, anything conflicting).
  - where stop & target sit vs structure, the Risk:Reward, and what invalidates it.
If the engine says "wait", explain in the same style WHAT is missing and what to
wait for — remember sometimes the best trade is no trade.

Use ✓ for confirmations and ✗ for risks. Return ONLY one minified JSON object,
ASCII digits, no markdown:
{{"summary":"<ONE plain-language sentence a beginner understands, no jargon>","explanation":"<mentor explanation with ✓/✗ bullet lines separated by \\n>"}}
"""


def build_explanation_prompt(symbol, timeframe, decision, profile_text=""):
    name = NAMES.get(symbol, symbol)
    user = (
        f"ENGINE DECISION (do not change it):\n{json.dumps(decision, ensure_ascii=False)}\n\n"
        f"TRADER PROFILE (mention only if relevant):\n{profile_text or '- (none)'}\n\n"
        f"Explain this {timeframe} decision for {symbol}."
    )
    return [
        {"role": "system", "content": EXPLAIN_SYSTEM.format(name=name, timeframe=timeframe)},
        {"role": "user", "content": user},
    ]


def parse_explanation(raw: str):
    """Return (summary, explanation). summary is a plain one-liner for beginners."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and (d.get("explanation") or d.get("summary")):
                return str(d.get("summary", "")), str(d.get("explanation", ""))
        except json.JSONDecodeError:
            pass
    return "", raw[:600]
