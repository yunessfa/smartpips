# مقایسهٔ نسخه‌ها و Baseline مرجع

## نسخه‌های موجود

| شناسه | محل | توضیح |
|---|---|---|
| **O** | `smartpips/` در آرشیو (همان `smartpips-leverage-ui-release.zip`) | نسخهٔ «leverage-ui» قبل از ممیزی اکتبر. Git ندارد. |
| **M** | `smartpips-scalp-integrity-v2/smartpips/`، همان مخزن GitHub، شاخهٔ `main` @ `a0d93ce` | O به‌علاوهٔ همهٔ اصلاحات بعدی، و تغییرات Commit‌نشدهٔ سرور که در `5e49fec` ادغام شدند |
| **P** | شاخهٔ `master` در GitHub @ `23e551b` (ژوئن ۲۰۲۶) | نمونهٔ اولیه: فقط ۷ App، بدون موتور استراتژی، بدون Migration، و **بدون تاریخچهٔ مشترک** با `main` |

تاریخچهٔ `main`:

```
a0d93ce fix: chart height 80% of screen
b8934d1 fix: TradingView chart sizing, one chart height site-wide, scrollable alert-health list
f4bc1fe feat: indicator study, decision-first market brief, decluttered scalp and futures dashboard
6a16e07 feat: validated trend-pullback playbook + long-history, statistically honest backtests
5e49fec merge: production hotfixes (demo risk advisory, panel navigation, TP plan, order risk) into scalp-integrity release
ef7a61d fix: scalp engine geometry, execution safety, strategy mode, alerts health, public site restyle
```

**تفاوت کلی O با M:**
- ۷۴ فایل تغییر کرده؛
- ۴۰ فایل یا پوشه فقط در M وجود دارد (کد، تست، Migration و مستندات)؛
- هیچ کدی در M حذف نشده. تنها مورد «فقط در O»، پوشهٔ `qa/leverage-ui` است که با همان محتوا به `QA/leverage-ui` منتقل شده.

---

## مقایسهٔ فایل‌های خواسته‌شده (O در برابر M)

| فایل | O (خط) | M (خط) | تفاوت کد و رفتار | تفاوت API | تفاوت منطق معاملاتی | نسخهٔ پیشنهادی |
|---|---|---|---|---|---|---|
| `decision.py` | 308 | 381 | حذف HTF قدیمی (`stale_htf`)؛ محافظ `price_mismatch` (قیمت مرورگر در برابر کندل سرور)؛ `timeframe` در خروجی؛ تیکت سفارش بر اساس `entry_plan` (Limit و انقضا)؛ پشتیبانی پلی‌بوک (`mode="trend"` یا استراتژی فعال از نوع playbook)؛ دریافت ۶۰۰ کندل و HTF ۴h/۱h؛ پارامتر `brief` | آرگومان‌های جدید اختیاری `mode="trend"` و `brief=True`. فیلدهای جدید خروجی: `entry_plan`، `exit_plan`، `playbook`، `brief`، `signal_source` | در O قیمت مرورگر بدون بررسی مبنای ورود بود؛ در M رد می‌شود. ورود Limit پولبک اضافه شده | **M** |
| `backtest.py` | 166 | 368 | پرشدن Limit فقط با لمس؛ کارمزد Maker؛ HTF از کندل واقعی بسته‌شده (O از همان ۵۰۰ کندل Resample می‌کرد)؛ پنجرهٔ ۳۰۰ کندلی مشابه لایو؛ Funding؛ Slippage روی پرشدن با گپ؛ بخش Evidence (CI، داخل و خارج نمونه، ماهانه)؛ مسیر پلی‌بوک | پارامترهای جدید `htf_series`، `funding_rate_8h` و `mode`. خروجی‌های جدید `evidence` و `exit_reasons` | در O بک‌تست با لایو برابر نبود: EMA200 روی ۴ساعته ساخته نمی‌شد | **M** |
| `presets.py` | 305 | 320 | افزوده شدن پیش‌فرض `trend_pullback` (signal_source=playbook) | — | پیش‌فرض‌های قدیمی بدون تغییر ولی در UI «تأییدنشده» برچسب خورده‌اند | **M** |
| `selection.py` | 35 | 153 | حالت `signal_source="strategy"` (قوانین کاربر جهت را تعیین می‌کنند) و حالت `playbook` (قوانین فقط Veto می‌کنند) | `apply_strategy(..., candles=)` | در O استراتژی کاربر فقط فیلتر موتور پایه بود | **M** |
| `regime.py` | 138 | 138 | یکسان | — | — | یکسان |
| `orderflow.py` | 209 | 219 | `fvg_quality`: پرشدن گپ از مسیر high/low محاسبه می‌شود (O فقط close را نگاه می‌کرد و گپ کاملاً پرشده را ۰٪ گزارش می‌داد)؛ پارامتر `max_age=30` | خروجی‌های جدید `top` و `bottom` | FVG کهنه یا مصرف‌شده دیگر «ناحیه» حساب نمی‌شود | **M** |
| `volume_profile.py` | 36 | 36 | یکسان (تخمین OHLCV با رنج یکنواخت) | — | — | یکسان. در V3 باید بازنویسی شود |
| `evaluation.py` | 43 | 43 | یکسان (پروتکل ۷۰/۱۵/۱۵ و Walk-forward با پارامتر ثابت) | — | — | یکسان. اجبار Holdout ندارد |
| `research_backtesting.py` | 116 | 116 | یکسان (backtesting.py اختیاری، فقط پژوهشی) | — | — | یکسان |
| `trend_pullback.py` | — | 339 | جدید: پلی‌بوک تأییدشده و شواهد پژوهش | تابع‌های `apply` و `setup_at` و `series_decider` | تنها استراتژی دارای شواهد خارج از نمونه | **M** |

### فایل‌های مرتبط دیگر

| فایل | O → M | خلاصه |
|---|---|---|
| `engine.py` | 774 → 741 | حذف کف ثابت ۰٫۸٪ حد ضرر و ضریب ۳R، و حذف گیت EMA9 > 2.2ATR که عملاً اجرا نمی‌شد. هندسهٔ حد ضرر و تارگت به `scalp_plan.py` منتقل شد. فیلتر FVG کهنه و روند محلی ۴ساعته اضافه شد. |
| `scalp_plan.py` | — → 187 | جدید: حد ضرر و تارگت به اندازهٔ تایم‌فریم، Anti-chase (لیمیت پولبک) و گیت هزینه |
| `market_brief.py` | — → 211 | جدید: خلاصهٔ تصمیم با واقعیت‌های آزموده‌شده |
| `backtest_data.py` | 108 → 217 | تاریخچهٔ بلند و HTF واقعی، و اعتبارسنجی `bars` |
| `market/candles.py` | +`fetch_history` | صفحه‌بندی Bitunix و Binance تا ۲۰ هزار کندل |
| `bitunix/views.py` و `models.py` | تغییر یافته | سفارش مارکت فقط با قیمت سرور، تأیید پرشدن، Limit دمو، ایمنی بستن پوزیشن واقعی، Migration `0003` |
| `alerts/*` | تغییر یافته | Heartbeat مانیتور، `last_checked` و `last_reason`، Migration `0005` |
| `bitunix/demo_risk.py` | ادغام از سرور | پروفایل ریسک دمو (هشداری) |

### تغییرات Commit‌نشده و ثبت‌نشده

- **تغییرات Commit‌نشدهٔ سرور** (`03a2bc5` روی سرور: demo risk advisory، رفع ناوبری، TakeProfitPlan، orderRisk و QA) در `5e49fec` ادغام و در GitHub ثبت شدند.
- **نسخه‌های پشتیبان روی سرور:** شاخهٔ `backup-before-scalp-03a2bc5` و فایل `/root/smartpips-server-changes-KEEP.tgz`.
- **فایل‌های بلاتکلیف روی سرور:** `docker-compose*.before-raw-20261019-102913` Untracked بودند و در مخزن نیستند (قصداً). باید روی سرور بررسی و آرشیو شوند.

### وابستگی‌ها

- `requirements.txt` بین O و M **بدون تغییر** است: Django 5.0.6، DRF 3.15.1، requests، pywebpush، ctrader-open-api و psycopg2-binary.
- `frontend/package.json` فقط `@fontsource/*` و تنظیم `manualChunks` را اضافه کرده است.
- هیچ کتابخانهٔ بک‌اند جدیدی اضافه نشده.

---

## Baseline مرجع پیشنهادی

**`main` @ `a0d93ce` به‌عنوان Baseline مرجع V3.** دلیل این انتخاب «جدیدتر بودن» نیست:

1. هر قابلیت O در M موجود است و هیچ رفتاری حذف نشده (بررسی با `diff -rq`).
2. اصلاحات M با تست پوشش داده شده‌اند:
   - `test_scalp_plan`، `test_trend_pullback`، `test_market_brief`، `test_execution_integrity`، `test_strategy_source`، `test_alert_diagnostics`؛
   - همهٔ ۲۸۱ تابع تست بک‌اند پاس هستند.
3. رفتارهای خطرناک O (قیمت مرورگر به‌عنوان ورود، بک‌تست ناهمسان با لایو، FVG مصرف‌شده) در M بسته شده‌اند.
4. موارد هم‌سان (`regime`، `volume_profile`، `evaluation`، `research_backtesting`) تغییری ندارند و در V3 بازطراحی می‌شوند.

**پیشنهاد برای شاخهٔ P (`master`):** حذف نشود. با نام Tag ‏`archive/prototype-2026-06` نگه داشته و از شاخه‌های فعال خارج شود. ارزش اجرایی ندارد ولی تاریخچه است.

**پیشنهاد برای پوشهٔ O در آرشیو:** فقط مرجع است. هیچ فایلی از آن نباید دوباره کپی شود، چون همه در M موجودند.
