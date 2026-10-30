# SmartPips Intelligence V3 — فاز صفر: ممیزی کامل پروژه

- تاریخ ممیزی: ۲۰۲۶-۱۰-۳۰
- نسخهٔ مرجع: `main` @ `a0d93ce`
- در این فاز هیچ کدی، دیتابیسی، Migration‌ای یا سروری تغییر نکرده است. فقط مستندات `docs/audit/` اضافه شده‌اند.

## اسناد این ممیزی

| سند | محتوا |
|---|---|
| [PROJECT_AUDIT.md](PROJECT_AUDIT.md) | این خلاصه، فهرست کامل اجزا، نتیجهٔ تست‌ها، یافته‌های کلیدی و برنامهٔ فازها |
| [FILE_COMPARISON.md](FILE_COMPARISON.md) | مقایسهٔ نسخه‌ها (`smartpips/`، مخزن فعلی، شاخهٔ `master`) و Baseline پیشنهادی |
| [TRADING_ENGINE_AUDIT.md](TRADING_ENGINE_AUDIT.md) | مسیر کامل سیگنال از داده تا ژورنال، Look-ahead، بک‌تست، Order Flow |
| [DATA_SOURCE_AUDIT.md](DATA_SOURCE_AUDIT.md) | همه منابع داده، Mock Price، فلزات، داده‌های واقعی و تخمینی، کمبودها |
| [BASELINE_AND_ROLLBACK.md](BASELINE_AND_ROLLBACK.md) | نقطهٔ مرجع، Git، بکاپ و روش بازگشت |
| [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) | بدهی فنی با اولویت P0 تا P3 |

---

## ۱) فهرست اجزای پروژه

### Backend (Django 5.0.6، DRF 3.15، PostgreSQL در Production، SQLite در توسعه)

| App | مدل‌ها | Migration | فایل تست | Endpoint | دستورهای مدیریتی |
|---|---|---|---|---|---|
| accounts | ExpiringToken، RefreshSession | 5 | 2 | 10 | prepare_refresh |
| market | Asset | 1 | 1 | 4 | check_feeds، metals_probe، remove_forex، seed |
| sources | Source | 1 | 0 | 1 | — |
| strategy | Indicator، TelegramChannel، Strategy، StrategyVersion | 2 | 11 | 6 (+ViewSet) | evaluate_engine، research_backtest |
| trades | Trade، TradeEvent | 11 | 3 | 1 (+ViewSet) | audit_trade_accounting، prepare_entry_audit، prepare_trade_accounting |
| ai | AIProvider | 2 | 0 | 1 | — |
| chat | Conversation، Message | 1 | 2 | 4 | — |
| alerts | PushSubscription، WatchItem، Notification، AlertRule، AlertRuleState، SignalState، UserSignalState | 6 | 2 | 11 | check_alerts، diagnose_push، gen_vapid، monitor_scalp، prepare_alerts |
| mt5 | MT5Account، MT5Quote، MT5Candles، MT5Order، MT5Tick | 2 | 0 | 6 | — |
| ctrader | CTraderToken، OAuthAttempt | 2 | 1 | 5 | ctrader_bridge |
| lbank | — | 0 | 0 | 11 | — |
| bitunix | DemoPosition | 3 | 6 | 13 | monitor_demo، reconcile_bitunix |
| prefs | MarketAccess، RiskLimits | 2 | 1 | 6 | — |

- **مجموع:** ۳۸ Migration؛ ۲۸۱ تابع تست بک‌اند.
- **Endpointهای سراسری:** `/api/health/` (عمومی)، `/api/health/deep/` (فقط ادمین)، `/api/logs/` (فقط ادمین).

### Frontend (React + Vite + Tailwind، RTL)

- **صفحات پنل (۱۲):** Dashboard، Scalp، Bitunix، Trades، Strategies، Notifications، Chat، Sources، AISettings، Logs، Admin، Login.
- **سایت عمومی:** Landing، Product، Company، Commerce.
- **اجزا و تست‌ها:** ۲۱ کامپوننت مشترک؛ ۳۲ تست واحد (`node --test`).
- **داده زنده در مرورگر:** WebSocket مستقیم به `stream.binance.com` (Spot) برای قیمت لحظه‌ای.

### زیرساخت

| مورد | وضعیت فعلی |
|---|---|
| Docker Compose | سرویس‌های `backend` (gunicorn، `127.0.0.1:8001`) و `frontend` (nginx، `127.0.0.1:8082`). `docker-compose.monitor.yml` شامل `alert-monitor` است، `docker-compose.demo.yml` شامل `demo-monitor`، و `docker-compose.research.yml` شامل backtesting.py اختیاری. |
| PostgreSQL | کانتینر جدا `smartpips-postgres` روی شبکهٔ خارجی `smartpips_network` (خارج از compose این پروژه) |
| Redis | **ندارد**. Cache از نوع FileBasedCache است (`backend/.cache`). Throttle ورود هم روی همین Cache است. |
| Celery | **ندارد**. کارهای پس‌زمینه با `manage.py … --loop` در کانتینرهای جدا اجرا می‌شوند. قبلاً cron بود. |
| WebSocket سمت سرور | **ندارد**. فقط مرورگر به WebSocket بایننس وصل می‌شود. |
| Nginx | `deploy/nginx-smartpips.conf` قدیمی است: به پورت 8000 اشاره می‌کند در حالی که Docker پورت 8001 را باز می‌کند. Nginx واقعی سرور در مخزن نیست. |
| متغیرهای محیطی | ۴۵ متغیر. فهرست در DATA_SOURCE_AUDIT است. `backend/.env.example` موجود است و `.env` در `.gitignore` است. |

---

## ۲) نتیجهٔ تست‌ها (روی `main` @ `a0d93ce`)

| مجموعه | نتیجه |
|---|---|
| Backend `manage.py test apps` | **OK** (۱ تست Skip: موتور اختیاری backtesting.py نصب نیست). زمان اجرا ≈ ۴۴ ثانیه. |
| `makemigrations --check` | No changes detected |
| Frontend `node --test` | ۳۲ از ۳۲ پاس |
| `vite build` | موفق |

**نکته:** تست‌ها از Cache فایلی مشترک استفاده می‌کنند. دو کلاس تست ورود قبلاً به‌خاطر Throttle ‏(۸ بار در دقیقه) در اجرای پشت‌سرهم شکست می‌خوردند. در `6a16e07` با `cache.clear()` ایزوله شدند.

---

## ۳) یافته‌های کلیدی (به ترتیب اهمیت)

1. **ناهمخوانی قرارداد در فلزات (P0).**
   - قیمت XAUUSD و XAGUSD از قرارداد پرپچوال LBank (`GOLD(XAU)USDT`) گرفته می‌شود.
   - LBank درخواست کندل را رد می‌کند (HTTP 403). پس کندل‌ها ممکن است از Twelve Data (اسپات)، **Yahoo COMEX Futures** (`GC=F`/`SI=F`) یا کندل‌های ۵ دقیقه‌ای مشتق‌شده بیایند.
   - یعنی قیمت و ساختار قیمت، و در نتیجه حد ضرر و تارگت، ممکن است از دو قرارداد متفاوت باشند.
   - محافظ «Price provenance» فقط اختلاف بیش از max(1.5٪، ۶ برابر رنج میانگین) را رد می‌کند و فاصلهٔ قیمت بین این دو قرارداد را نمی‌گیرد.
2. **هیچ داده واقعی Order Flow یا مشتقات وارد موتور نمی‌شود (P0 برای V3).**
   - Delta، فشار خرید و فروش، Sweep، Order Block، FVG و MSS همه از OHLCV **تخمین** زده می‌شوند.
   - برای فلزات «tick direction» از quote کارگزار گرفته می‌شود که aggressor flow نیست.
   - Funding، OI، Liquidation، Basis و CVD واقعی وجود ندارند. `BitunixClient.funding_rate()` تعریف شده ولی هیچ‌جا استفاده نشده است.
   - Order Book فقط نمایشی است و وارد تصمیم نمی‌شود.
3. **Mock Price هنوز در دو مسیر وجود دارد (P1).**
   - `market/services._mock_quote` برای داشبورد استفاده می‌شود و برچسب `source=mock` دارد.
   - همین قیمت ساختگی وارد **پرامپت دستیار چت** می‌شود (`chat/services.py:158`). برچسب «UNVERIFIED» دارد ولی به هوش مصنوعی داده می‌شود.
   - موتور معاملاتی (`decide`) از این مسیر استفاده نمی‌کند. شرح کامل در DATA_SOURCE_AUDIT است.
4. **بک‌تست ۴ فرض خوش‌بینانهٔ مستند دارد (P1):**
   - پرشدن Limit با لمس قیمت (بدون مدل صف)؛
   - نبود Spread جدا از Slippage؛
   - Funding ثابت به‌جای تاریخی؛
   - نبود تقویم اقتصادی تاریخی.

   Look-ahead و کندل ناقص کنترل و تست شده‌اند.
5. **مشخصات قرارداد فلزات ثابت در کد است (P1).** ۱ لات طلا = ۱۰۰ اونس و ۱ لات نقره = ۵۰۰۰ اونس، به‌جای دریافت از کارگزار. اندازهٔ موقعیت کریپتو هم کارمزد را در مبلغ ریسک لحاظ نمی‌کند.
6. **سشن‌ها با ساعت ثابت UTC و بدون Daylight Saving هستند (P2).** باز شدن لندن و نیویورک بین تابستان و زمستان یک ساعت جابه‌جا می‌شود.
7. **تکرار و همبستگی ویژگی‌ها در موتور قدیمی (P1، اندازه‌گیری‌شده).**
   - ۱۲ جزء امتیاز در عمل ۲ تا ۳ اطلاع مستقل است (VWAP و EMA200 با ρ=0.85).
   - روی ۵ و ۱۵ دقیقه هیچ اندیکاتوری برتری‌ای بیش از هزینه ندارد (`QA/indicator-study`).
   - این موتور به‌عنوان «قدیمی/تأییدنشده» برچسب خورده است.
8. **دو نسخهٔ تکراری کد و یک شاخهٔ بی‌ربط (P2).**
   - پوشهٔ `smartpips/` (نسخهٔ leverage-ui) در آرشیو.
   - شاخهٔ `master` در GitHub: نمونهٔ اولیهٔ ژوئن ۲۰۲۶ بدون تاریخچهٔ مشترک.
   - جزئیات در FILE_COMPARISON است.
9. **زیرساخت (P2).**
   - Cache فایلی، بدون Redis و Celery.
   - کانفیگ Nginx مخزن با Docker نمی‌خواند.
   - Health، فقط برای ادمین، بخش‌هایی از متن خطای داخلی را برمی‌گرداند.
   - محیط Staging وجود ندارد.

---

## ۴) آنچه در نسخهٔ فعلی **درست و قابل اتکاست** (برای حفظ در V3)

- موتور روی **کندل بسته‌شده** تصمیم می‌گیرد. Data-quality gate روی فاصله و ترتیب کندل‌ها و OHLC نامعتبر، و محافظ Stale بودن داده وجود دارد. در نبود داده، تصمیم WAIT است.
- **پلی‌بوک تأییدشدهٔ Trend Pullback:**
  - روی ۸ سال داده خارج از نمونه آزموده شده؛
  - بک‌تست سایت همان اعداد پژوهش را بازتولید می‌کند (`QA/trend-pullback-research`)؛
  - شامل فیلتر هزینه (حداقل حد ضرر ۰٫۴٪) است.
- **بک‌تست:**
  - تا ۲۰ هزار کندل؛
  - HTF بسته‌شده با تراز زمانی؛
  - Stop-first وقتی حد ضرر و تارگت در یک کندل خورده شوند؛
  - کارمزد Maker و Taker، Slippage و Funding تقریبی؛
  - بازهٔ اطمینان ۹۵٪، تفکیک داخل و خارج نمونه، و حکم «نمونه ناکافی».
- **اجرای سفارش:**
  - سفارش واقعی فقط با `mode=real` و `confirm=true`؛
  - قیمت سفارش مارکت از سرور گرفته می‌شود، نه از مرورگر؛
  - پرشدن تأیید می‌شود؛
  - دمو کاملاً جدا ثبت می‌شود.
- **ژورنال:** `Trade.entry_snapshot` و hash آن، `fees_paid`، `funding_paid`، `execution_evidence`، `TradeEvent`، و `decision_token` امضاشده.
- **هوش مصنوعی** فقط توضیح می‌دهد و تصمیم و سطوح را تغییر نمی‌دهد.

---

## ۵) برنامهٔ تغییرات پیشنهادی (پس از تأیید شما)

هر فاز طبق پرامپت این مراحل را دارد: Inspect → Plan → Implement → Test → Review → Document → Commit. اگر تست‌های حیاتی یک فاز پاس نشوند، فاز بعد شروع نمی‌شود.

| فاز | محتوا | ریسک | Migration | پیش‌نیاز از شما |
|---|---|---|---|---|
| **1a** پاک‌سازی ایمنی | جدا کردن کامل Mock از چت؛ قفل منبع کندل فلزات به همان قرارداد قیمت (در غیر این صورت WAIT)؛ برچسب `is_estimated` روی ویژگی‌های OHLCV | کم | ندارد | — |
| **1b** معماری Provider | `market/providers/base.py` با قرارداد مشترک (`get_candles`، `get_quote`، `get_orderbook`، `get_funding`، `get_open_interest`، `health_check` و …) و آداپتور Bitunix و Binance روی کد موجود، بدون تغییر رفتار | کم تا متوسط | ندارد | — |
| **2** داده مشتقات کریپتو | Funding، OI، Mark/Index، Basis، Long/Short از Binance Futures (رایگان) با منبع و Timestamp؛ ثبت روزانهٔ Snapshot برای ساختن تاریخچه | متوسط | افزایشی (`derivatives_metrics`) | تأیید دسترسی سرور به `fapi.binance.com` |
| **3** معاملات و Order Book واقعی | CVD از aggTrades و Imbalance چندسطحی از depth، با ذخیرهٔ ویژگی‌ها و نه دادهٔ خام. نیازمند فرآیند جمع‌آوری دائمی | متوسط تا بالا | افزایشی | تصمیم دربارهٔ Redis و فضای دیسک |
| **4** موتور فلزات | Provider واقعی cTrader (Bid/Ask/Spread/Tick)، مشخصات قرارداد از کارگزار، سشن با DST | متوسط | افزایشی | Credential حساب cTrader |
| **5** Regime و استراتژی‌ها | Regime در Shadow Mode؛ پلی‌بوک‌های Breakout Retest، Liquidity Reversal و Range، **هر کدام فقط بعد از پاس شدن Walk-Forward و Holdout** | متوسط | ندارد | — |
| **6** Evidence و Calibration | سیستم Evidence خانواده‌محور (بدون شمارش تکراری)، Calibration فقط وقتی نمونهٔ کافی ثبت شده باشد | کم | افزایشی (`signal_candidates`، `signal_outcomes`) | — |
| **7** ریسک و اجرا | جدا کردن ماژول ریسک، لحاظ کارمزد و Funding در اندازهٔ موقعیت، ثبت Requested و Filled و Slippage و Latency | متوسط | افزایشی | — |
| **8** داشبورد پژوهش و Provider Health | گزارش‌ها با تعداد نمونه، و پنل سلامت منابع | کم | ندارد | — |
| **9** DevOps | Staging مستقل، بکاپ و بررسی آن، Canary و Rollback | متوسط | — | دسترسی و تصمیم دربارهٔ VPS |

**ترتیب پیشنهادی شروع:** 1a، سپس 1b، سپس 2. این‌ها کم‌ریسک‌اند، Migration ندارند (به‌جز فاز ۲ که افزایشی است) و مستقیماً اعتبار سیگنال را بالا می‌برند.

**تحقیق قیمت APIهای پولی (فاز 13 پرامپت)** هنوز انجام نشده است. طبق پرامپت باید از مستندات رسمی و به‌روز در زمان همان فاز بررسی شود و هیچ قیمتی حدس زده نشود.

---

## ۶) فرضیات و محدودیت‌های این ممیزی

- Git محلی کامپیوتر شما (تغییرات Commit‌نشده، Stash و Tagهای محلی) از اینجا قابل مشاهده نیست. دستورهای بررسی آن در BASELINE_AND_ROLLBACK آمده است.
- دیتابیس و سرور Production بررسی نشده‌اند (طبق قانون فاز صفر). وضعیت Migration از روی کد بررسی شد: ۳۸ Migration است و `makemigrations --check` تمیز است.
- دسترسی به APIهای بیرونی (Bitunix، Binance، LBank، Yahoo) از محیط ممیزی مسدود بود. رفتار منابع از روی کد و تست‌ها مستند شده، نه با فراخوانی زنده.
