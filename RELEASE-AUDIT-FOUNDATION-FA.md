# شروع از اینجا — SmartPips Audit Foundation

این نسخه یک milestone ممیزی/اصلاحات است، نه اجرای کامل درخواست ۴۲فازی. جدول وضعیت هر فاز در SMARTPIPS_CHANGELOG.md است. استراتژی‌های V2/V3، کنترل کامل portfolio/liquidation، خروج stateful کامل و بازطراحی سینمایی هنوز کامل نشده‌اند. نتیجهٔ واقعی OOS ساخته نشده است.

۱. شش فایل SMARTPIPS_*.md را بخوانید؛ ابتدا AUDIT و TRADE_ANALYSIS.
۲. محدودیت‌ها و شواهد محلی در QA/full-audit/TEST-RESULTS.md قرار دارند.
۳. راهنمای استقرار: deploy/ENTRY-AUDIT-DEPLOY-FA.md. ابتدا بکاپ قابل بازیابی و staging PostgreSQL، سپس migrationهای افزایشیِ مشخص. این محیط PostgreSQL/Docker تولید را تست نکرده است.
۴. کتابخانهٔ backtesting.py در dependency/image پژوهشی جدا مانده؛ پیش‌فرض جایگزین نشده است.
۵. سورس جدید به GitHub push نشده است. دریافت origin/main به معنی دریافت این فایل ZIP نیست.
۶. برای جلوگیری از تغییر ریسک ناخواسته، demo-monitor با release helper پیش‌فرض خاموش می‌ماند و فقط با START_DEMO_MONITOR=1 صریح راه می‌افتد. سفارش‌گذارهای خارجی را خودتان قبل از migration متوقف کنید.

برای اجرای تست اپلیکیشن در محیط توسعهٔ وابستگی‌های نصب‌شده:

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.test_settings python manage.py test --noinput
# تست migration واقعی نیست: test_settings تاریخچه migrations اپ‌ها را اجرا نمی‌کند.
PYTHONPATH=. python ../QA/full-audit/installed-state-smoke.py
PYTHONPATH=. python ../QA/full-audit/model-state-check.py
cd ../frontend
npm ci
npm test
npm run build
```

fixtureهای UI دادهٔ واقعی بازار نیستند. آمار ژورنال دادهٔ واقعی/دموی ورودی است، نه گواه اجرای صرافی. Excel خام و دیتابیس/کلید خصوصی در ZIP قرار ندارند. گزارش‌ها و تجمیع خصوصی ژورنال را عمومی منتشر نکنید.
