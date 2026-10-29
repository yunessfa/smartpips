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

A separate quantitative engine has ALREADY decided the trade on CLOSED candles.
Your job is ONLY to explain that decision like a calm trading mentor — do NOT
change the signal, entry, take-profit, stop-loss, and do NOT invent numbers.

Write in Persian, short (max 6 lines). Base the explanation on the "brief"
object: higher-timeframe trend, EMA alignment, distance from EMA21 (pullback),
volatility vs the 0.4% cost floor, and the "next" step. A multi-year study
found NO measurable edge in RSI, MACD, Stochastic, SMC (BOS/CHOCH/FVG), order
blocks, estimated order flow or premium/discount on 5m/15m — never present
them as reasons to enter. Never call any score a win probability. If the
decision is "wait", say what is missing and what would change it.

Use ✓ for confirmations and ✗ for risks. Return ONLY one minified JSON object,
ASCII digits, no markdown:
{{"summary":"<ONE plain-language sentence a beginner understands, no jargon>","explanation":"<mentor explanation with ✓/✗ bullet lines separated by \\n>"}}
"""


def build_explanation_prompt(symbol, timeframe, decision, profile_text=""):
    name = NAMES.get(symbol, symbol)
    keep = ("signal", "signal_source", "entry", "stop_loss", "take_profit", "risk_reward", "entry_plan",
            "exit_plan", "brief", "reason", "wait_reasons", "strategy_name", "strategy_evaluation",
            "risk_block", "news_guard", "support", "resistance", "data_quality")
    compact = {k: decision.get(k) for k in keep if decision.get(k) is not None}
    user = (
        f"ENGINE DECISION (do not change it):\n{json.dumps(compact, ensure_ascii=False, default=str)}\n\n"
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


def engine_explanation(symbol, timeframe, decision):
    """Short, decision-first explanation for THIS closed-candle snapshot.

    2026-10: the old version printed every indicator (EMA9, MACD, SMC dicts,
    FVG internals…) on every request, so each answer looked the same and buried
    the decision. The indicator study found no measurable edge in those
    readings on 5m/15m, so the text now carries only: the decision, the
    validated market facts (market_brief), the levels that matter, strategy
    vetoes and risk/news blocks. Nothing here is a win probability.
    """
    from apps.strategy import market_brief

    def num(value):
        try:
            n = float(value)
            return f"{n:,.10g}"
        except (TypeError, ValueError):
            return "ناموجود"

    signal = decision.get("signal", "wait")
    brief = decision.get("brief") or {}
    action = {"buy": "خرید", "sell": "فروش"}.get(signal)
    if action:
        plan = decision.get("entry_plan") or {}
        how = "سفارش لیمیت" if plan.get("type") == "limit" else "ورود"
        summary = f"{symbol} · {timeframe}: {action} — {how} روی {num(decision.get('entry'))}"
    else:
        summary = f"{symbol} · {timeframe}: انتظار — {market_brief.wait_text(decision)}"

    lines = []
    if decision.get("signal_source") == "playbook":
        lines.append("منبع: پلی‌بوک تأییدشده «پولبک روند» (آزمون ۸ساله بیت‌کوین، بعد از کارمزد).")
    else:
        lines.append(f"منبع: موتور امتیازی قدیمی — امتیاز {num(decision.get('score'))} از ۱۰۰ "
                     "(امتیاز، درصد برد نیست؛ این موتور در آزمون چندساله برتری آماری نشان نداد).")
    if decision.get("strategy_name"):
        lines.append(f"استراتژی فعال: {decision['strategy_name']} · نسخه {decision.get('strategy_version') or '—'}")
    if brief:
        lines += market_brief.lines(brief, decision)
    elif signal not in ("buy", "sell"):
        lines.append("✗ " + market_brief.wait_text(decision))

    if action:
        lines.append(f"سطوح: ورود {num(decision.get('entry'))} · حد ضرر {num(decision.get('stop_loss'))} · "
                     f"تارگت {num(decision.get('take_profit'))} · R:R {num(decision.get('risk_reward'))}")
    else:
        parts = []
        if brief.get("pullback_level"):
            parts.append(f"سطح پولبک (EMA21) {num(brief['pullback_level'])}")
        parts.append(f"حمایت {num(decision.get('support'))}")
        parts.append(f"مقاومت {num(decision.get('resistance'))}")
        lines.append("سطوح مهم: " + " · ".join(parts) + ". این‌ها دستور ورود نیستند.")

    for check in (decision.get("strategy_evaluation") or {}).get("checks") or []:
        if check.get("passed") is not True:
            state = "داده ناموجود" if check.get("passed") is None else "رد"
            lines.append(f"✗ شرط استراتژی «{check.get('label') or check.get('block')}» ({state}): "
                         f"مقدار {check.get('actual')}، شرط {check.get('operator')} {check.get('value')}")
    if decision.get("risk_block"):
        lines.append("⛔ مانع ریسک حساب: " + str(decision["risk_block"]))
    if decision.get("news_guard"):
        lines.append("📅 محافظ خبر: " + str(decision["news_guard"]))
    if decision.get("data_quality") not in (None, "candles"):
        lines.append("⚠ کیفیت داده: " + str(decision.get("data_quality")) + " — سیگنال معتبر نیست.")
    lines.append("تحلیل روی آخرین کندل بسته‌شده است؛ تا بسته‌شدن کندل بعدی نتیجه عوض نمی‌شود.")
    return summary, "\n".join(lines)
