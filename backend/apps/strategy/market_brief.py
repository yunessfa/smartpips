"""Market brief: the few readings that measurably matter, in plain words.

Why (2026-10 indicator study, BTC 2019-2026, ~342k engine evaluations on
5m/15m/1h, see QA/indicator-study): on 5m/15m no single engine indicator —
RSI, MACD, Stochastic, VWAP, SMC (BOS/CHOCH/FVG), order blocks, estimated
order flow, premium/discount, sweeps, key levels — had a directional edge
above ~2 bp against ~10 bp of costs, and the sign flipped between 2019-22 and
2023-26. They are also highly redundant (VWAP vs EMA200 ρ=0.85; MACD/RSI/SMC/
flow one cluster). What held up: the higher-timeframe trend, EMA alignment,
buying the pullback instead of the stretch, and refusing stops that fees eat.

So the brief reports only those, plus what is missing for a setup and when the
reading can next change (closed-bar engine: nothing changes until the next
candle closes — repeated clicks inside one candle return the same answer).
"""
import hashlib
import json

from . import trend_pullback as tp

WAIT_FA = {
    # playbook
    "htf_no_trend": "روند ۴ساعته مشخص نیست (قیمت/EMA50 نسبت به EMA200 هم‌جهت نیستند)",
    "htf_unavailable": "داده تایم‌فریم ۴ساعته یا ۱ساعته در دسترس نیست",
    "h1_conflict": "روند ۱ساعته با روند ۴ساعته هم‌جهت نیست",
    "local_trend_conflict": "EMAهای این تایم‌فریم (۲۱/۵۰/۲۰۰) با روند بالاتر هم‌ردیف نیستند",
    "no_pullback_setup": "قیمت هنوز به‌اندازه کافی از EMA21 فاصله نگرفته؛ ستاپ پولبک فعال نیست",
    "stop_below_cost_floor": "نوسان کم است؛ حد ضرر ۱٫۵ ATR کمتر از ۰٫۴٪ می‌شود و کارمزد سود را می‌خورد",
    "insufficient_history": "تاریخچه کافی برای محاسبه EMA200 نیست",
    "playbook_timeframe": "این تایم‌فریم برای پلی‌بوک تأیید نشده (فقط ۵ دقیقه، ۱۵ دقیقه و ۱ ساعته)",
    "playbook_market": "پلی‌بوک فقط روی کریپتو تأیید شده است",
    "stale_htf": "داده تایم‌فریم بالاتر قدیمی است",
    # legacy engine
    "low_score": "امتیاز هم‌جهتی اندیکاتورها کم است",
    "weak_conviction": "دو طرف خرید و فروش تقریباً برابرند (بدون جهت روشن)",
    "htf_conflict": "تایم‌فریم بالاتر با جهت ستاپ مخالف است",
    "high_volatility": "نوسان غیرعادی بالاست",
    "quiet_market": "بازار برای اسکالپ خیلی آرام است",
    "setup_validation": "شروط ستاپ (ساختار/نقدینگی) کامل نیست",
    "range_trend_conflict": "در بازار رنج، ستاپ روندی مسدود شد",
    "stop_too_wide": "ساختار، حد ضرر خیلی دوری می‌خواهد",
    "fees_vs_target": "تارگت در برابر کارمزد ارزش ندارد",
    "chasing": "حرکت کشیده شده و سطح پولبک تمیزی نیست",
    "price_mismatch": "قیمت زنده با فید کندل نمی‌خواند",
    "insufficient_data": "داده کندل کافی نیست",
}

TF_FA = {"1m": "۱ دقیقه‌ای", "5m": "۵ دقیقه‌ای", "15m": "۱۵ دقیقه‌ای", "1h": "۱ ساعته", "4h": "۴ ساعته"}
TREND_FA = {1: "صعودی", -1: "نزولی", 0: "بدون روند", None: "نامشخص"}


def _trend_word(v):
    return TREND_FA.get(v, "نامشخص")


def _round(x, ref):
    if x is None:
        return None
    try:
        return float(f"{float(x):.{6 if ref and ref < 10 else 2}f}")
    except (TypeError, ValueError):
        return None


def build(decision, symbol, timeframe, tf_candles, htf_candles):
    """Return the brief dict (also stored at decision['brief'])."""
    step = tp.TF_SECONDS.get(timeframe, 300)
    brief = {"version": 1, "timeframe": timeframe, "status": decision.get("signal") or "wait",
             "source": "playbook" if decision.get("signal_source") == "playbook" else "engine",
             "validated_timeframe": timeframe in tp.TIMEFRAMES, "facts": [], "next": None}
    if not tf_candles:
        brief["next"] = {"code": "no_data"}
        return _finish(brief)
    last = tf_candles[-1]
    bar_time = int(float(last.get("time") or 0))
    brief["bar_time"] = bar_time or None
    brief["next_update_at"] = bar_time + 2 * step if bar_time else None  # next candle CLOSE

    ind = tp.indicators(tf_candles)
    i = len(tf_candles) - 1
    close, e21, e50, e200, a = (ind["close"][i], ind["e21"][i], ind["e50"][i], ind["e200"][i], ind["atr"][i])
    h4_view = tp.HTFView((htf_candles or {}).get("4h") or [], tp.TF_SECONDS["4h"])
    close_time = bar_time + step if bar_time else None
    h4, _ = tp._htf_trend(h4_view, close_time, "4h") if close_time else (None, "missing")
    facts = brief["facts"]
    facts.append({"key": "h4_trend", "value": h4, "state": "neutral" if h4 in (0, None) else "ok",
                  "validated": True})
    h1 = None
    if timeframe in ("1m", "5m", "15m"):
        h1_view = tp.HTFView((htf_candles or {}).get("1h") or [], tp.TF_SECONDS["1h"])
        h1, _ = tp._htf_trend(h1_view, close_time, "1h") if close_time else (None, "missing")
        agrees = h1 is not None and h4 not in (0, None) and h1 == h4
        facts.append({"key": "h1_trend", "value": h1, "state": "ok" if agrees else "neutral" if h1 in (0, None) else "bad",
                      "validated": True})
    enough = i + 1 >= tp.MIN_BARS
    stack = (1 if e21 > e50 > e200 else -1 if e21 < e50 < e200 else 0) if enough else None
    want = h4 if h4 in (1, -1) else 0
    facts.append({"key": "ema_stack", "value": stack,
                  "state": "ok" if want and stack == want else "neutral" if stack in (0, None) or not want else "bad",
                  "validated": True})
    stretch = (close - e21) / a if a else 0.0
    facts.append({"key": "stretch", "value": round(stretch, 2), "need": tp.STRETCH_ATR,
                  "state": "ok" if want and stretch * want > tp.STRETCH_ATR else "neutral", "validated": True})
    stop_pct = tp.STOP_ATR * a / close * 100 if close else 0.0
    facts.append({"key": "volatility", "value": round(stop_pct, 3), "need": tp.MIN_STOP_PCT,
                  "state": "ok" if stop_pct >= tp.MIN_STOP_PCT else "bad", "validated": True})

    brief["pullback_level"] = _round(e21, close)
    brief["atr"] = _round(a, close)
    brief["price"] = _round(close, close)
    brief["support"] = _round(decision.get("support"), close)
    brief["resistance"] = _round(decision.get("resistance"), close)

    status = brief["status"]
    if status in ("buy", "sell"):
        plan = decision.get("entry_plan") or {}
        brief["next"] = {"code": "limit_active" if plan.get("type") == "limit" else "signal_active",
                         "price": decision.get("entry"), "valid_bars": plan.get("valid_for_bars"),
                         "valid_minutes": plan.get("valid_for_minutes")}
    elif not brief["validated_timeframe"]:
        brief["next"] = {"code": "tf_not_validated"}
    elif h4 in (0, None):
        brief["next"] = {"code": "wait_trend"}
    elif h1 is not None and h1 != h4:
        brief["next"] = {"code": "wait_h1", "dir": h4}
    elif stack != h4:
        brief["next"] = {"code": "wait_stack", "dir": h4}
    elif stop_pct < tp.MIN_STOP_PCT:
        brief["next"] = {"code": "wait_volatility", "need_pct": tp.MIN_STOP_PCT, "now_pct": round(stop_pct, 2)}
    elif stretch * h4 <= tp.STRETCH_ATR:
        trigger = e21 + h4 * tp.STRETCH_ATR * a
        brief["next"] = {"code": "wait_stretch", "dir": h4, "trigger": _round(trigger, close),
                         "limit": _round(e21, close)}
    else:
        brief["next"] = {"code": "blocked", "reasons": [w.get("code") for w in (decision.get("wait_reasons") or [])][:3]}
    if decision.get("risk_block"):
        brief["blocked_by"] = "risk"
    elif decision.get("news_guard"):
        brief["blocked_by"] = "news"
    return _finish(brief)


def _finish(brief):
    key = {"s": brief.get("status"), "f": [(f["key"], f["state"]) for f in brief.get("facts", [])],
           "n": (brief.get("next") or {}).get("code"), "b": brief.get("bar_time")}
    brief["fingerprint"] = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]
    return brief


def _num(x):
    if x is None:
        return "—"
    try:
        return f"{float(x):,.10g}"
    except (TypeError, ValueError):
        return str(x)


def lines(brief, decision):
    """Short Persian text version (chat, notifications, AI context)."""
    out = []
    tf = TF_FA.get(brief.get("timeframe"), brief.get("timeframe"))
    for f in brief.get("facts", []):
        mark = "✓" if f["state"] == "ok" else "✗" if f["state"] == "bad" else "•"
        k = f["key"]
        if k == "h4_trend":
            out.append(f"{mark} روند ۴ساعته: {_trend_word(f['value'])}")
        elif k == "h1_trend":
            out.append(f"{mark} روند ۱ساعته: {_trend_word(f['value'])}")
        elif k == "ema_stack":
            word = {1: "صعودی مرتب", -1: "نزولی مرتب", 0: "نامرتب", None: "نامشخص"}[f["value"]]
            out.append(f"{mark} چیدمان EMA21/50/200 در {tf}: {word}")
        elif k == "stretch":
            out.append(f"{mark} فاصله قیمت از EMA21: {abs(f['value']):.1f} ATR (برای ستاپ بیش از {f['need']:g})")
        elif k == "volatility":
            out.append(f"{mark} اندازه حد ضرر ۱٫۵ ATR: {f['value']:.2f}٪ (حداقل {f['need']:g}٪)")
    nxt = brief.get("next") or {}
    code = nxt.get("code")
    side = lambda d: "خرید" if d == 1 else "فروش"
    if code == "limit_active":
        out.append(f"→ ستاپ فعال: سفارش لیمیت روی {_num(nxt.get('price'))}، معتبر {nxt.get('valid_bars')} کندل.")
    elif code == "signal_active":
        out.append(f"→ سیگنال فعال با ورود {_num(nxt.get('price'))}.")
    elif code == "wait_stretch":
        out.append(f"→ قدم بعد: اگر کندلی {'بالای' if nxt['dir'] == 1 else 'زیر'} {_num(nxt.get('trigger'))} بسته شود، "
                   f"لیمیت {side(nxt['dir'])} روی حدود {_num(nxt.get('limit'))} (EMA21) فعال می‌شود.")
    elif code == "wait_volatility":
        out.append(f"→ قدم بعد: منتظر نوسان بیشتر (الان {nxt['now_pct']}٪، لازم {nxt['need_pct']}٪). معامله در این حالت فقط کارمزد می‌دهد.")
    elif code == "wait_trend":
        out.append("→ قدم بعد: تا وقتی روند ۴ساعته روشن نشده، معامله‌ای نیست.")
    elif code == "wait_h1":
        out.append("→ قدم بعد: منتظر هم‌جهت شدن روند ۱ساعته با ۴ساعته.")
    elif code == "wait_stack":
        out.append(f"→ قدم بعد: منتظر مرتب شدن EMAهای {tf} در جهت {side(nxt['dir'])}.")
    elif code == "tf_not_validated":
        out.append("→ این تایم‌فریم تأییدشده نیست؛ ۵ دقیقه، ۱۵ دقیقه یا ۱ ساعته را انتخاب کنید.")
    elif code == "blocked":
        reasons = [WAIT_FA.get(c, c) for c in nxt.get("reasons") or []]
        if reasons:
            out.append("→ مانع: " + "؛ ".join(reasons))
    return out


def wait_text(decision):
    """First human reason for a WAIT, in Persian."""
    for w in decision.get("wait_reasons") or []:
        code = w.get("code")
        if code in WAIT_FA:
            return WAIT_FA[code]
    reason = decision.get("reason") or ""
    return reason.replace("Trend pullback: ", "") if reason else "شرایط ورود کامل نیست"
