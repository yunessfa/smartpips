# ممیزی موتور معاملاتی (Phase 0)

Baseline: `main` @ `a0d93ce`. همهٔ ارجاع‌ها به مسیر `backend/` هستند. این سند فقط وضعیت فعلی را ثبت می‌کند و هیچ کدی در Phase 0 تغییر نکرده است.

---

## ۱. مسیر کامل تصمیم (Pipeline)

```
Market Data ─► Data Validation ─► Indicators ─► Regime ─► Setup/Geometry ─► Strategy Filter ─► News/Session ─► Risk & Sizing ─► Signal ─► Execution ─► Journal ─► Exit/Monitor
```

| مرحله | فایل و تابع | چه می‌کند | وضعیت |
|---|---|---|---|
| دریافت کندل | `apps/market/candles.py: fetch_candles` (خط 463) | کریپتو: Bitunix → Binance. فلزات: MT5 → TwelveData → Yahoo → derived → stale-cache | مشکل منبع فلزات (بخش ۴) |
| اعتبارسنجی داده | `apps/strategy/data_quality.py: inspect_bars` | گپ، تکراری، کندل باز، ترتیب زمانی، OHLC نامعتبر | سالم، تست‌دار |
| محافظ قیمت | `apps/strategy/decision.py` خط 117 | قیمت لایو مرورگر در برابر آخرین Close سرور؛ تحمل `max(1.5%, 6×avg_range)` | سالم؛ تحمل برای 1m/5m گشاد است (P2) |
| اندیکاتورها | `apps/strategy/engine.py: analyse_timeframe` (خط 185) | EMA، RSI، MACD، ATR، VWAP، Stochastic، SMC، FVG، OB | فرمول‌ها غیراستاندارد (بخش ۲) |
| رژیم بازار | `apps/strategy/regime.py: detect_regime` | ترند/رنج/پرنوسان از EMA و ATR | بدون Backtest جداگانه |
| امتیاز و جهت | `engine.py: _score_direction`، `_validate_setup` (خط 241 و 370) | امتیاز وزنی و گیت‌های safe/aggressive | بدون اعتبار آماری (بخش ۵) |
| هندسهٔ معامله | `apps/strategy/scalp_plan.py: build_plan` | حد ضرر و تارگت بر اساس تایم‌فریم، Anti-chase، گیت هزینه | سالم، تست‌دار |
| پلی‌بوک | `apps/strategy/trend_pullback.py: apply` | ورود Limit پولبک در جهت ترند ۴h | تنها مسیر دارای شواهد خارج از نمونه |
| استراتژی کاربر | `apps/strategy/selection.py: apply_strategy` | `filter` / `strategy` / `playbook` | سالم |
| خبر | `apps/market/calendar_guard.py` | تقویم faireconomy (فقط هفتهٔ جاری) | بدون تاریخچه برای بک‌تست |
| سشن | `apps/market/sessions.py: session_factor` | پنجره‌های ثابت UTC | DST لحاظ نمی‌شود |
| ریسک و حجم | `decision.py: _apply_risk` (خط 196)، `apps/strategy/risk.py` | حجم از درصد ریسک و فاصلهٔ حد ضرر | کارمزد در حجم نیست؛ Contract size ثابت (بخش ۶) |
| تیکت سفارش | `decision.py: _build_order_ticket` (خط 333) | Market یا Limit با انقضا | سالم |
| مصرف‌کننده‌ها | `apps/chat/views.py: scalp_signal`، `apps/alerts/signal_check.py: evaluate_and_alert`، `apps/strategy/views.py: market_overview` | صفحهٔ اسکالپ، هشدارها، داشبورد | هر سه از یک `decide` می‌خوانند ✔ |
| اجرا | `apps/bitunix/views.py` | واقعی فقط با `mode=real` و `confirm=true`؛ قیمت از سرور؛ تأیید پرشدن | سالم |
| دمو | `apps/bitunix/demo_monitor.py` | تسویهٔ SL/TP و Limit دمو | سالم |
| ژورنال | `apps/trades/models.py`، `apps/trades/snapshots.py` | Snapshot ورود با Hash، Decision Token، رویدادها | سالم |
| خروج | `apps/strategy/exit_engine.py: evaluate_exit` | فقط توصیه؛ اقدام خودکار ندارد | سالم |

**نکتهٔ مثبت:** هر سه مصرف‌کننده (اسکالپ، هشدار، داشبورد) از همان `decide` استفاده می‌کنند، پس سیگنال صفحه با هشدار یکی است.

---

## ۲. صحت اندیکاتورها

| اندیکاتور | پیاده‌سازی فعلی | مرجع استاندارد | اثر | اولویت |
|---|---|---|---|---|
| RSI | `engine.py:38` میانگین ساده ۱۴ کندل آخر (Cutler) | Wilder smoothing | مقادیر با TradingView متفاوت؛ کاربر عدد متفاوت می‌بیند | P2 |
| ATR | `engine.py:63` میانگین سادهٔ TR | Wilder (RMA) | اختلاف کوچک؛ در `trend_pullback.atr_series` درست (Wilder) است | P2 |
| VWAP | `engine.py:73` روی کل پنجرهٔ کندل (Rolling) | Session VWAP با ریست روزانه | «VWAP» واقعی نیست؛ در مطالعه با EMA200 همبستگی ρ=0.85 داشت | P2 |
| Volume Profile | `volume_profile.py` توزیع یکنواخت حجم در رنج کندل | Tick/Trade-level | تخمینی؛ باید برچسب `is_estimated` بگیرد | P1 |
| Order Flow / Delta | `orderflow.py` از جهت کندل و حجم | Aggressor trades / CVD | تخمینی | P1 |
| EMA | `engine.py:18,28` | استاندارد | ✔ | — |
| MACD | `engine.py:54` | استاندارد | ✔ | — |

## ۳. داده‌های «Order Flow»

همهٔ ویژگی‌های جریان سفارش **از OHLCV تخمین زده می‌شوند**: `order_flow`، `liquidity_sweep`، `order_blocks`، `premium_discount`، MSS و `fvg_quality`.

- برای فلزات، `apps/market/tick_flow.py: real_order_flow` از `MT5Tick.tick_dir` استفاده می‌کند. این جهت تغییر Quote است، **نه Aggressor واقعی**، ولی در `engine.py:491` بایاس را بازنویسی می‌کند.
- Order Book فقط نمایشی است و در تصمیم وارد نمی‌شود.
- `BitunixClient.funding_rate` (`bitunix/client.py:227`) وجود دارد ولی هیچ‌جا مصرف نمی‌شود.
- CVD، Open Interest، Liquidations و Basis وجود ندارند.

برچسب فعلی `delta_unit: "normalized_proxy"` در `engine.py:725` درست است ولی در UI به کاربر نشان داده نمی‌شود.

## ۴. سازگاری داده با قرارداد معاملاتی (P0)

برای XAUUSD و XAGUSD قیمت لحظه‌ای از LBank می‌آید ولی کندل‌ها اگر MT5 در دسترس نباشد به ترتیب از TwelveData، **Yahoo `GC=F` / `SI=F` (فیوچرز COMEX)**، داده مشتق‌شده و در نهایت کش کهنه گرفته می‌شوند (`candles.py:49, 203–230, 513–524`).

نتیجه: اندیکاتورها روی قراردادی محاسبه می‌شوند که با قرارداد اجرای سفارش فرق دارد (اختلاف Basis و ساعات معاملاتی). محافظ `price_mismatch` بخشی از این را می‌گیرد ولی نه همه را. مگر اینکه `METALS_STRICT_SOURCE=1` تنظیم شود.

**پیشنهاد Phase 1a:** اگر کندل از همان منبعِ قیمت اجرا نیست، خروجی `WAIT` با دلیل `source_contract_mismatch`.

## ۵. اعتبار آماری استراتژی‌ها

| مسیر | شواهد | نتیجه |
|---|---|---|
| `trend_pullback` روی 1h | QA/trend-pullback-research: TR/VA/HO = +0.345 / +0.138 / +0.265R، مثبت در ۸ از ۸ سال | **تنها مسیر دارای شواهد خارج از نمونه.** این نتیجهٔ Backtest است، نه لایو |
| `trend_pullback` روی 5m/15m | مثبت ولی ضعیف‌تر؛ وابسته به هزینه | نیازمند تأیید با هزینهٔ واقعی |
| موتور امتیازی پایه (`run_strategy`) | QA/indicator-study: ۳۴۲ هزار ارزیابی، بدون Edge روی 5m/15m؛ IC مومنتوم کمی منفی | **بدون Edge اثبات‌شده.** ~۹۵٪ مواقع WAIT |
| پیش‌فرض‌های قدیمی `presets.py` | بدون تست خارج از نمونه | در UI با برچسب «تأییدنشده» |

## ۶. ریسک و حجم

- `risk.py:17`: `CONTRACT_SIZE = {"XAUUSD": 100, "XAGUSD": 5000}` ثابت است و از مشخصات قرارداد صرافی خوانده نمی‌شود (P1).
- کارمزد و Spread در محاسبهٔ حجم لحاظ نمی‌شوند؛ فقط گیت هزینه در `scalp_plan` وجود دارد (P1).
- محدودیت ضرر روزانه، حداکثر پوزیشن همزمان و همبستگی بین نمادها وجود ندارد (P1، Phase 5).

## ۷. بک‌تست و جلوگیری از Look-ahead

| مورد | وضعیت |
|---|---|
| تصمیم فقط روی کندل بسته | ✔ (`backtest._decide_at` با پنجرهٔ ۳۰۰ کندلی، مشابه لایو) |
| HTF بسته‌شده | ✔ (`_closed_htf`، `HTFView`) |
| Stop-first وقتی SL و TP در یک کندل | ✔ |
| کارمزد Maker/Taker و Funding | ✔ ولی Funding ثابت است، نه تاریخی |
| Spread | ✘ |
| پرشدن Limit | فقط با لمس؛ صف و پرشدن جزئی مدل نمی‌شود |
| خبر تاریخی | ✘ |
| فلزات | فقط ۵۰۰ کندل |
| Holdout | `evaluation.py:33` «Opt-in; no single-use enforcement» — اجباری نیست (P1) |

## ۸. اجرا و ایمنی سفارش

- سفارش واقعی فقط با `mode=real` و `confirm=true`؛ قیمت ورود Market از سرور، نه کلاینت.
- تأیید پرشدن (Fill verification) و ثبت شواهد اجرا در `Trade.execution_evidence`.
- خطاهای Bitunix به پیام عمومی تبدیل می‌شوند و جزئیات فقط در لاگ سرور است.
- در Phase 0 هیچ سفارشی ارسال نشد.

## ۹. خلاصهٔ یافته‌ها بر اساس اولویت

| # | یافته | اولویت | فاز پیشنهادی |
|---|---|---|---|
| E1 | کندل فلزات ممکن است از قرارداد دیگری (COMEX) باشد | **P0** | 1a |
| E2 | قیمت Mock وارد پرامپت AI چت می‌شود (با برچسب UNVERIFIED) | **P0** | 1a |
| E3 | Order flow تخمینی بدون برچسب `is_estimated` در UI | P1 | 1a |
| E4 | `tick_dir` فلزات به‌عنوان جریان واقعی بایاس را تغییر می‌دهد | P1 | 1b |
| E5 | Holdout اجباری نیست | P1 | 4 |
| E6 | Contract size ثابت؛ کارمزد در حجم نیست | P1 | 5 |
| E7 | RSI و ATR غیر Wilder؛ VWAP غلتان | P2 | 2 |
| E8 | سشن بدون DST | P2 | 2 |
| E9 | موتور امتیازی پایه بدون Edge | P2 (مستند شده) | 3 |
