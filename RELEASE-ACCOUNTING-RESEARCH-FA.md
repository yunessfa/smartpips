# اصلاح حسابداری و موتور تحقیقاتی اختیاری

این نسخه فایل‌های لاگین، رفرش توکن، هشدارها، UI پنل عمومی و ارتفاع چارت‌ها را تغییر نمی‌دهد.
قبل از استقرار از دیتابیس و سورس و env نسخه پشتیبان بگیرید. هیچ دستور down -v یا --fake اجرا نکنید.

## تغییرات

- خروج پله‌ای: سود تحقق‌یافتهٔ قبلی + سود حجم باقی‌مانده؛ بستن تکراری/سطح تکراری بی‌اثر؛ قفل ردیف.
- اکسل: اطلاعات انتساب و هزینه‌ها/مبنای PnL؛ هزینهٔ نامعلوم خالی است نه صفر.
- گزارش استراتژی: تفکیک نسخه و منبع، ترتیب زمانی صحیح محاسبه افت PnL؛ این افت درصد حساب نیست.
- مشخصات ورود پس از ثبت ثابت می‌ماند؛ سابقهٔ نامشخص به استراتژی فعال فعلی نسبت داده نمی‌شود.
- تمام سوابق گذشته حفظ می‌شوند. audit_trade_accounting فقط گزارش می‌دهد و چیزی اصلاح نمی‌کند.
- net_pnl فقط با هزینه‌های تأییدشده پر می‌شود؛ اجرای واقعیِ تأییدنشده برچسب تخمینی دارد.
- reconcile_bitunix فقط پیش‌نمایش تطبیق دقیق positionId/symbol/side از تاریخچهٔ رسمی است.
  از تطبیق مبهم بر اساس نماد یا حدس قرارداد علامت funding برای ساخت سود خالص خودداری می‌کند.
  این نسخه عمداً واردکنندهٔ خودکار هزینه یا بازنویس معاملات واقعی ندارد.
- پایش مستقل دمو هر ۱۰ ثانیه؛ فقط قیمت عمومی، بدون سفارش واقعی. GET پوزیشن هم از همان منطق استفاده می‌کند.
  خروج با قیمت مشاهده‌شده ثبت می‌شود؛ قیمت‌های بین دو نمونه و فاصلهٔ قطع سرویس قابل بازسازی نیستند.
  دموی LIMIT قبلاً بدون matcher فوراً fill می‌شد؛ اکنون صریحاً رد می‌شود؛ MARKET استفاده کنید.
- ریسک فقط دمو: ۰٫۵٪ هر معامله شامل هزینه تخمینی رفت‌وبرگشت، سقف اهرم۱۰، زیان خالص تخمینی روزانه۲٪،
  سه پوزیشن باز و مجموع ریسک استاپ۱٫۵٪ برای کل سبد (محافظه‌کارانه‌تر از فرض استقلال نمادها).
  این پروفایل با موجودی دمو واردشدهٔ کاربر محاسبه می‌شود، نه موجودی زنده حساب؛ افت شناور لحاظ نشده است.
  استاپ پوزیشن قدیمی اگر نامعلوم باشد ورود جدید مسدود می‌شود. پوزیشن‌های موجود تغییر نمی‌کنند.
  DEMO_RISK_V1_ENABLED=0 فقط پروفایل آزمایشی را خاموش می‌کند؛ به معاملات واقعی ارتباطی ندارد.
- در فرم تأیید دمو، دکمهٔ محاسبه حجم بر اساس استاپ اضافه شده؛ مقدار نهایی سمت سرور دوباره کنترل می‌شود.
- استراتژی‌ها فیلتر موتور پایه‌اند؛ سیگنال مستقل جدید یا شل‌کردن فیلترهای ایمنی اضافه نشده.
- موتور backtesting.py با نسخه ثابت۰٫۶٫۵ جداگانه و اختیاری است؛ نصب اصلی تغییر وابستگی ندارد.
  در صفحه استراتژی‌ها انتخاب موتور وجود دارد. نبود کتابخانه پیام503 مشخص می‌دهد، نه خطای مبهم500.
  نتیجه تحقیقاتی روی نتیجه معتبر موتور اصلی ذخیره نمی‌شود و مجوز فعال‌سازی ایجاد نمی‌کند.
- برآورد حجم موتور تحقیقاتی ریسک۰٫۵٪ و سقف سرمایه۱x دارد. ورودیِ بسته‌شده تاریخی و prefix-only.
  گپ ورود و خروج زمانی next-open با موتور اصلی یکسان نیستند؛ لغزش، funding، خبر تاریخی، تریلینگ و خروج پله‌ای
  در این adapter شبیه‌سازی نمی‌شوند. خروجی حساب تحقیقاتی با خروجی R موتور اصلی معادل نیست.
- دستور research_backtest پنجره را زمانی به train/holdout جدا می‌کند؛ پارامترها را روی holdout تنظیم نمی‌کند.
  فایل معاملات اکسل برای بهینه‌سازی معتبر کافی نیست؛ تاریخچهٔ OHLCV لازم است. سودآوری جدید اثبات نشده.

## استقرار روی نصب موجود PostgreSQL

ابتدا مطمئن شوید نام کانتینر و POSTGRES_DB واقعاً دیتابیس برنامه شماست؛ اگر نیست، آن‌ها را اصلاح کنید.
رمز را در چت نفرستید. هنگام dump سرویس را لازم نیست حذف کنید. برای مشاهده نام دیتابیس واقعی برنامه (بدون رمز) می‌توانید اجرا کنید:

```bash
docker compose exec -T backend python manage.py shell -c "from django.db import connection; print(connection.vendor, connection.settings_dict['NAME'])"
```

با مقدار POSTGRES_DB کانتینر زیر مقایسه کنید؛ در صورت تفاوت، در دستور pg_dump نام صحیح را به‌جای آن بگذارید:
```bash
docker exec smartpips-postgres sh -c 'printf "%s\n" "$POSTGRES_DB"'
```

```bash
cd /home/ubuntu/smartpips
mkdir -p /root/smartpips-backups
umask 077
BACKUP_FILE="/root/smartpips-backups/before-accounting-$(date +%Y%m%d-%H%M%S).dump"
docker exec smartpips-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP_FILE" || { rm -f "$BACKUP_FILE"; exit 1; }
test -s "$BACKUP_FILE"
docker exec -i smartpips-postgres sh -c 'pg_restore --list' < "$BACKUP_FILE" > "${BACKUP_FILE}.list"
test -s "${BACKUP_FILE}.list"
export BACKUP_FILE
```

فایل‌های ZIP را با حفظ backend/.env و تمام فایل‌های داده روی سورس نصب کنید. اگر از Git استفاده می‌کنید،
ابتدا این تغییرات باید در مخزن خودتان commit/push شده باشند؛ git reset به main قدیمی این اصلاحات را برمی‌گرداند.

موتور اصلی + پایش دمو:
```bash
bash deploy/release-accounting-research.sh
```

همراه کتابخانه اختیاری:
```bash
ENABLE_RESEARCH=1 bash deploy/release-accounting-research.sh
```

برای اجرای دستورات بعدی با همین ترکیب:
```bash
dc() { docker compose -f docker-compose.yml -f docker-compose.demo.yml -f docker-compose.research.yml "$@"; }
dc ps
dc exec -T backend python manage.py showmigrations trades
dc exec -T backend python manage.py audit_trade_accounting > /root/smartpips-backups/accounting-review.json
dc logs --tail=100 demo-monitor
```

اگر prepare_trade_accounting خطای prerequisite یا schema/history mismatch داد، ادامه ندهید و --fake نزنید.
تاریخچهٔ مهاجرت‌های قدیمی عمداً بازنویسی نشده و برای نصب صفر به بررسی جداگانه نیاز دارد.
هشدار Compose درباره متغیر تعریف‌نشده (مثلاً ynk) را نادیده نگیرید؛ وجود $ در مقدار .env ممکن است
interpolation ایجاد کند. فقط مقدار واقعی موجود را با syntax مناسب .env تک‌نقل‌قول کنید؛ secret جدید نسازید.

## تطبیق واقعی — فقط خواندن

شناسه کاربر/معامله و positionId واقعی صرافی را جایگزین کنید؛ انتخاب بر اساس نماد به‌تنهایی مجاز نیست:
```bash
dc exec -T backend python manage.py reconcile_bitunix --user-id USER_ID --trade-id TRADE_ID --position-id POSITION_ID
```

## ارزیابی خارج نمونه — فقط خواندن

input.json آرایهٔ OHLCV با time یونیکس و open/high/low/close/volume است. مسیر باید در کانتینر موجود باشد:
```bash
docker cp input.json "$(dc ps -q backend)":/tmp/input.json
dc exec -T backend python manage.py research_backtest --input /tmp/input.json --symbol BTCUSDT:PERP --timeframe 5m --engine native > native-holdout.json
dc exec -T backend python manage.py research_backtest --input /tmp/input.json --symbol BTCUSDT:PERP --timeframe 5m --engine backtesting > research-holdout.json
```

برای استراتژی خاص --version-id را از نسخهٔ خودتان اضافه کنید. مقایسه با پارامترهای ثابت است نه جستجوی
بهترین پارامترها. داده کم/گسسته گزارش خطا دارد و با داده مصنوعی جایگزین نمی‌شود.

## تست و محدودیت تحویل

تست‌های شبکه با mock اجرا می‌شوند؛ هیچ سفارش واقعی برای تست ارسال نمی‌شود.
قبل از استفاده واقعی، ورود/رفرش، خروجی اکسل، پایش دمو و تنظیم strategy scope را روی سرور خودتان smoke-test کنید.
پایش دمو جای سفارش محافظ ثبت‌شده در صرافی واقعی نیست. تنظیمات واقعی حساب تغییر نکرده‌اند.
این نسخه تضمین سود، افزایش نرخ برد یا بهینه‌شدن آماری استراتژی‌ها ندارد.
نصب Docker/PostgreSQL واقعیِ سرور مالک بدون دسترسی مستقیم قابل تأیید نیست.

گزارش تست این تحویل: QA/accounting-research/TEST-REPORT-FA.md. اطلاعات و داده‌های شخصی اکسل در بسته قرار نگرفته‌اند.
