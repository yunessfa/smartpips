# ممیزی منابع داده (Phase 0)

Baseline: `main` @ `a0d93ce`. هدف این سند: مشخص کردن این‌که هر عددی که کاربر یا موتور می‌بیند **از کجا می‌آید**، واقعی است یا تخمینی، و آیا داده ساختگی به موتور معاملاتی می‌رسد یا نه.

---

## ۱. نقشهٔ منابع

| داده | مصرف‌کننده | منبع اصلی | Fallback به ترتیب | واقعی / تخمینی | فایل |
|---|---|---|---|---|---|
| کندل کریپتو | موتور، بک‌تست، چارت تحلیل | Bitunix Futures | Binance | واقعی | `backend/apps/market/candles.py:293, 322, 463` |
| کندل فلزات | موتور، بک‌تست | MT5 (اگر Bridge فعال باشد) | TwelveData → Yahoo `GC=F`/`SI=F` → derived → stale-cache | واقعی، **ولی شاید قرارداد دیگر** | `candles.py:49, 203–230, 513–524` |
| تاریخچهٔ بلند | بک‌تست | Bitunix/Binance صفحه‌بندی‌شده تا ۲۰ هزار کندل | — | واقعی | `candles.py: fetch_history` |
| قیمت لحظه‌ای فلزات | صفحهٔ اسکالپ | سرور `marketApi.metal` (LBank) | Binance در مرورگر | واقعی | `frontend/src/live/useMetalTick.js` |
| قیمت لحظه‌ای کریپتو (نوار قیمت) | UI | WebSocket **Binance Spot** (`stream.binance.com`) | — | واقعی، **اسپات نه فیوچرز**؛ پسوند `:PERP` حذف می‌شود | `frontend/src/live/LivePrices.jsx:16` |
| Quote داشبورد | داشبورد، **پرامپت چت AI** | Binance / metals | `_mock_quote` (عدد تصادفی ثابت) | **ساختگی در حالت Fallback** | `backend/apps/market/services.py:14, 80`؛ `apps/chat/services.py:158–168` |
| Tick فلزات | `tick_flow` | cTrader/MT5 Bridge → `MT5Tick.tick_dir` | — | جهت Quote، نه Aggressor | `apps/ctrader/management/commands/ctrader_bridge.py:111`، `apps/market/tick_flow.py` |
| Order Book | UI | LBank / Bitunix | — | واقعی، فقط نمایش | `frontend/src/components/OrderBook.jsx` |
| Funding | بک‌تست | ثابت ورودی کاربر | — | فرضی | `backtest.py` |
| Funding لحظه‌ای | — | `BitunixClient.funding_rate` | — | **استفاده نمی‌شود** | `apps/bitunix/client.py:227` |
| تقویم اقتصادی | گیت خبر | `nfs.faireconomy.media/ff_calendar_thisweek.json` | — | واقعی، فقط هفتهٔ جاری | `apps/market/calendar_guard.py:11` |
| سشن | امتیاز | جدول ثابت UTC | — | قاعده، بدون DST | `apps/market/sessions.py` |

## ۲. آیا داده ساختگی به موتور معاملاتی می‌رسد؟

| مسیر | پاسخ | توضیح |
|---|---|---|
| `decide` (سیگنال اسکالپ، هشدار، داشبورد) | **خیر** | فقط از `fetch_candles` می‌خواند؛ `_mock_quote` در این مسیر نیست |
| بک‌تست | **خیر** | فقط کندل واقعی؛ کندل نامعتبر با `_clean_series` حذف می‌شود |
| پرامپت چت AI عمومی | **بله (P0)** | `_market_block` در صورت قطع منبع، قیمت Mock را با برچسب `FALLBACK / UNVERIFIED` به مدل می‌دهد. مدل ممکن است همان عدد را به کاربر بگوید |
| داشبورد Quote | بله، با برچسب `mock` | نمایشی؛ ولی کاربر ممکن است برچسب را نبیند |

**پیشنهاد Phase 1a:** حذف Mock از پرامپت چت (به‌جای عدد بنویسد «قیمت در دسترس نیست»)؛ در داشبورد به‌جای عدد تصادفی، خط تیره و پیام «منبع قطع است».

## ۳. ناسازگاری بین منابع

1. **Spot در برابر Futures:** نوار قیمت از Binance Spot است در حالی که معامله روی Bitunix Futures انجام می‌شود. اختلاف Basis معمولاً کوچک است ولی در نوسان شدید می‌تواند از Range یک کندل 1m بیشتر شود.
2. **فلزات:** قیمت اجرا از LBank، کندل‌ها شاید از COMEX فیوچرز. اختلاف قیمت و ساعت بسته شدن بازار.
3. **محافظ `price_mismatch`** (`decision.py:117`) با تحمل `max(1.5%, 6×avg_range)` اختلاف‌های بزرگ را می‌گیرد، ولی 1.5٪ برای اسکالپ 1m/5m گشاد است.

## ۴. تازگی و کش

- کش Django از نوع `FileBasedCache` است (`config/settings.py:110`). Redis و Celery وجود ندارد.
- کندل‌ها با `inspect_bars` از نظر تازگی بررسی می‌شوند و کندل کهنه → WAIT.
- `stale-cache` برای فلزات فقط با برچسب منبع برگردانده می‌شود و در تصمیم کیفیت داده را پایین می‌آورد.
- `overview` داشبورد برای هر کندل یک‌بار کش می‌شود.

## ۵. داده‌هایی که وجود ندارند

| داده | اهمیت برای فیوچرز کریپتو | پیشنهاد |
|---|---|---|
| CVD واقعی (Aggressor trades) | بالا | Phase 1b/2 از WebSocket معاملات صرافی؛ نیاز به Redis یا جدول تجمیعی |
| Open Interest | متوسط | API عمومی صرافی (قیمت و محدودیت‌ها در Phase 13 از مستندات رسمی) |
| Funding تاریخی | متوسط | برای بک‌تست دقیق |
| Liquidations | پایین تا متوسط | اختیاری |
| تقویم خبر تاریخی | متوسط برای بک‌تست | منبع آرشیوی؛ هزینه بررسی شود |

## ۶. کلیدها و تنظیمات

- ۴۵ متغیر محیطی؛ `.env.example` در مخزن هست و `.env` در `.gitignore`.
- در Phase 0 هیچ کلیدی درخواست یا خوانده نشد.
- `TWELVEDATA_KEY` و Bridge MT5/cTrader اختیاری‌اند؛ نبودشان مسیر Fallback فلزات را فعال می‌کند.

## ۷. یافته‌ها

| # | یافته | اولویت |
|---|---|---|
| D1 | قیمت Mock در پرامپت چت AI | **P0** |
| D2 | کندل فلزات از قرارداد دیگر بدون قفل منبع | **P0** |
| D3 | نوار قیمت Spot برای معاملهٔ Futures | P1 |
| D4 | `funding_rate` موجود ولی بی‌استفاده | P2 |
| D5 | نبود CVD/OI | P2 (Phase 2) |
| D6 | تقویم فقط هفتهٔ جاری | P2 |
