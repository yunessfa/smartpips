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

Write in Persian. Explicitly distinguish measured readings, estimates and
missing data. Never call the engine score a win probability. Do not claim
unavailable news, volume-at-price or order-book evidence. Explain the FINAL
decision including strategy vetoes/news/risk gates, not just the initial setup.
The engine's deterministic explanation is factual context; add clarity rather
than inventing missing confirmations. Structure it like a
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


def engine_explanation(symbol, timeframe, decision):
    """Deterministic explanation for THIS snapshot, even without an AI provider.

    Report supplied readings only. A score is not a calibrated win probability;
    absent checks/data are never described as confirmed evidence.
    """
    import math

    def number(value):
        try:
            n = float(value)
            return f"{n:.10g}" if math.isfinite(n) else 'ناموجود'
        except (TypeError, ValueError):
            return 'ناموجود'

    def text(value):
        if value is None:
            return 'ناموجود'
        if isinstance(value, bool):
            return 'بله' if value else 'خیر'
        names = {'bullish': 'صعودی', 'bearish': 'نزولی', 'neutral': 'خنثی',
                 'trending': 'رونددار', 'ranging': 'رنج', 'quiet': 'کم‌تحرک',
                 'volatile': 'پرنوسان', 'above': 'بالاتر', 'below': 'پایین‌تر',
                 'inside': 'داخل محدوده', 'normal': 'عادی'}
        if isinstance(value, dict):
            return '، '.join(f'{k}: {text(v)}' for k, v in value.items())
        return names.get(str(value), str(value))

    signal = decision.get('signal', 'wait')
    action = {'buy': 'خرید', 'sell': 'فروش', 'wait': 'انتظار / عدم ورود'}.get(signal, 'عدم ورود')
    summary = f'{symbol} در {timeframe}: تصمیم فعلی موتور «{action}» است؛ این نتیجه تضمین سود نیست.'
    indicators = decision.get('indicators') or {}
    regime = decision.get('market_regime') or {}
    session = decision.get('session') or {}
    lines = [f'۱) وضعیت فعلی — {symbol} · {timeframe}',
             f'تصمیم: {action} | امتیاز: {number(decision.get("score"))} از ۱۰۰. امتیاز، درصد برد نیست.',
             f'کیفیت داده: {text(decision.get("data_quality"))}؛ سشن: {text(session.get("name"))}؛ وضعیت بازار: {text(regime.get("regime") or decision.get("regime"))}.']
    reason = decision.get('reason')
    if reason:
        reasons = {
            'market too quiet to scalp (low volatility)': 'نوسان بازار برای اسکالپ کافی نیست',
            'wide, directionless bars — too risky': 'کندل‌ها بزرگ و بدون جهت روشن‌اند',
            'higher timeframe conflicts with the setup': 'تایم‌فریم بالاتر با ستاپ تعارض دارد',
            'over-extended from EMA9 — wait for a pullback': 'قیمت از EMA9 دور شده؛ باید منتظر پولبک ماند',
            'could not place a stop with acceptable R:R': 'حد ضرر با نسبت سود به زیان قابل قبول پیدا نشد',
            'all layers aligned': 'لایه‌های بررسی‌شده موتور هم‌جهت بوده‌اند',
            'Candle feed is stale; new entries disabled.': 'کندل‌ها قدیمی‌اند؛ ورود جدید غیرفعال است',
            'no candle/tick data available': 'داده کندل یا تیک برای تحلیل موجود نیست',
        }
        lines.append('علت ثبت‌شده موتور: ' + reasons.get(reason, reason))
    lines += ['', '۲) شواهد عددی همین تحلیل']
    for key in ('EMA9', 'EMA50', 'EMA200', 'VWAP', 'RSI', 'MACD_hist'):
        lines.append(f'{key}: {number(indicators.get(key))}')
    lines.append('Stochastic: ' + text(indicators.get('Stoch')))
    for key in ('SMC', 'MSS', 'LiquiditySweep', 'OrderBlock', 'PremiumDiscount', 'FVG_quality'):
        lines.append(f'{key}: {text(indicators.get(key))}')
    flow = indicators.get('OrderFlow') or {}
    lines.append(f'فشار محاسبه‌شده: دلتا {number(flow.get("delta"))}؛ خرید {number(flow.get("buy_pressure"))}؛ فروش {number(flow.get("sell_pressure"))}. این مقادیر تضمین جهت آینده نیستند.')
    lines.append('تایید تایم‌فریم‌های بالاتر: ' + text(decision.get('htf_detail')))
    lines += ['', '۳) شروط استراتژی انتخاب‌شده',
              f'استراتژی: {decision.get("strategy_name") or "موتور پایه"}؛ نسخه: {text(decision.get("strategy_version"))}.']
    evaluation = decision.get('strategy_evaluation') or {}
    checks = evaluation.get('checks') or []
    for check in checks:
        passed = check.get('passed')
        state = 'تأیید' if passed is True else 'رد' if passed is False else 'داده ناموجود'
        mandatory = ' (اجباری)' if check.get('required') else ''
        lines.append(f'{state}{mandatory}: {check.get("label") or check.get("block")}؛ مشاهده {text(check.get("actual"))}؛ شرط {check.get("operator")} {text(check.get("value"))}.')
    if not checks:
        lines.append(evaluation.get('reason') or 'ارزیابی جداگانه‌ای از شروط سفارشی در این پاسخ ثبت نشده است.')
    lines += ['', '۴) سطوح و ریسک',
              f'حمایت: {number(decision.get("support"))}؛ مقاومت: {number(decision.get("resistance"))}.',
              'سطوح کلیدی: ' + text(indicators.get('KeyLevels'))]
    vp = decision.get('volume_profile') or {}
    if vp:
        lines.append(f'پروفایل حجمی تخمینی OHLCV: POC {number(vp.get("poc"))}؛ VAH {number(vp.get("vah"))}؛ VAL {number(vp.get("val"))}. حجم واقعی معامله‌شده در هر قیمت نیست.')
    if signal in ('buy', 'sell'):
        lines.append(f'ورود: {number(decision.get("entry"))}؛ حد ضرر: {number(decision.get("stop_loss"))}؛ هدف: {number(decision.get("take_profit"))}؛ R:R: {number(decision.get("risk_reward"))}.')
        lines.append('برنامه فعلی با رسیدن به حد ضرر یا تغییر شروط تأییدشده نیازمند بازبینی است؛ این خط لزوماً ابطال کل ساختار بازار نیست.')
    else:
        lines.append('چون تصمیم نهایی انتظار است، سطوح باقی‌مانده از ستاپ اولیه دستور ورود نیستند. برای ورود باید مانع ثبت‌شده رفع و تحلیل تازه دوباره تأیید شود.')
    if decision.get('position_size'):
        lines.append('اندازه پیشنهادی موقعیت: ' + text(decision['position_size']))
    for key, label in (('risk_block', 'مانع ریسک'), ('news_guard', 'محافظ خبر')):
        if decision.get(key):
            lines.append(label + ': ' + str(decision[key]))
    if not decision.get('news_guard'):
        lines.append('در این پاسخ هشدار مسدودکننده خبر ثبت نشده؛ این به معنی نبود خبر یا پوشش کامل اخبار نیست.')
    if decision.get('risk_settings_not_executed'):
        lines.append('تنظیمات استراتژی که موتور اجرا نمی‌کند: ' + ', '.join(decision['risk_settings_not_executed']))
    lines.append('کارمزد، اسپرد، لغزش و تغییرات سریع بازار می‌توانند نتیجه واقعی را عوض کنند؛ سود یا نرخ برد از این تحلیل قابل تضمین نیست.')
    return summary, '\n'.join(lines)
