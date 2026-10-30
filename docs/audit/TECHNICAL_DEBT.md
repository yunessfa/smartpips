# بدهی فنی (Phase 0)

اولویت‌ها: **P0** = خطر مستقیم برای تصمیم یا پول؛ **P1** = دقت یا ایمنی مهم؛ **P2** = کیفیت و سازگاری؛ **P3** = نگهداری.

## معاملاتی و داده

| # | مورد | شواهد | اولویت | فاز |
|---|---|---|---|---|
| T1 | قیمت Mock در پرامپت چت AI | `apps/market/services.py:14,80`؛ `apps/chat/services.py:158` | P0 | 1a |
| T2 | کندل فلزات از قرارداد COMEX بدون قفل منبع | `apps/market/candles.py:49,513` | P0 | 1a |
| T3 | Order flow تخمینی بدون برچسب `is_estimated` در API/UI | `apps/strategy/orderflow.py`، `engine.py:725` | P1 | 1a |
| T4 | `tick_dir` Quote به‌عنوان جریان واقعی | `apps/market/tick_flow.py`، `engine.py:491` | P1 | 1b |
| T5 | Holdout اختیاری | `apps/strategy/evaluation.py:33` | P1 | 4 |
| T6 | Contract size ثابت؛ کارمزد در حجم نیست | `apps/strategy/risk.py:17,122` | P1 | 5 |
| T7 | نبود محدودیت ضرر روزانه و همبستگی | `decision.py: _apply_risk` | P1 | 5 |
| T8 | نوار قیمت Binance Spot برای معاملهٔ Futures | `frontend/src/live/LivePrices.jsx:16` | P1 | 2 |
| T9 | RSI و ATR غیر Wilder؛ VWAP غلتان | `engine.py:38,63,73` | P2 | 2 |
| T10 | Volume profile با توزیع یکنواخت | `volume_profile.py` | P2 | 2 |
| T11 | سشن بدون DST | `apps/market/sessions.py` | P2 | 2 |
| T12 | تحمل `price_mismatch` گشاد برای 1m/5m | `decision.py:117` | P2 | 1b |
| T13 | بک‌تست بدون Spread، Funding تاریخی و خبر تاریخی | `backtest.py` | P2 | 4 |
| T14 | فلزات فقط ۵۰۰ کندل در بک‌تست | `backtest_data.py` | P2 | 4 |
| T15 | تقویم فقط هفتهٔ جاری | `apps/market/calendar_guard.py:11` | P2 | 2 |
| T16 | `funding_rate` بی‌استفاده | `apps/bitunix/client.py:227` | P3 | 2 |
| T17 | پیش‌فرض‌های قدیمی بدون شواهد | `presets.py` | P3 (برچسب خورده) | 3 |

## زیرساخت و امنیت

| # | مورد | شواهد | اولویت | فاز |
|---|---|---|---|---|
| I1 | مخزن GitHub عمومی است | تنظیمات مخزن | **P0** (اقدام شما: Private) | فوری |
| I2 | پیام خطای خام به کلاینت | `apps/ai/views.py:29`، `apps/lbank/views.py:29,44`، health deep `str(exc)[:200]` | P1 | 1a |
| I3 | `FileBasedCache`؛ نبود Redis/Celery/WebSocket سرور | `config/settings.py:110` | P2 | تصمیم شما |
| I4 | ناسازگاری پورت: Nginx نمونه 8000، Docker 8001 | `deploy/nginx-smartpips.conf:29`، `docker-compose.yml:24` | P2 (مستندات) | 1a |
| I5 | فایل‌های `docker-compose*.before-raw-*` Untracked روی سرور | سرور | P3 | 1a |
| I6 | شاخهٔ `master` بی‌ربط | GitHub | P3 | Tag آرشیو |

## کیفیت کد

| # | مورد | اولویت |
|---|---|---|
| C1 | دو پیاده‌سازی EMA/ATR (`engine.py`، `regime.py`، `trend_pullback.py`، `scalp_plan.py`) | P2 — یکی شود در Phase 2 |
| C2 | `engine.py` با ۷۴۱ خط؛ امتیازدهی، اعتبارسنجی و خروجی در یک فایل | P3 |
| C3 | چند فایل QA بزرگ (PNG/JSON) در مخزن | P3 |

## چیزهایی که بدهی نیستند (عمداً حفظ شوند)

- `data_quality.inspect_bars`، محافظ `price_mismatch`، Decision Token و Hash ورود، تأیید پرشدن سفارش، الزام `confirm=true` برای سفارش واقعی، Stop-first در بک‌تست، HTF بسته‌شده.
