# Baseline و برنامهٔ بازگشت (Rollback)

## ۱. Baseline مرجع

| مورد | مقدار |
|---|---|
| شاخه | `main` |
| Commit | `a0d93ce` (fix: chart height 80% of screen) |
| Migrationها | ۳۸ فایل؛ `makemigrations --check` تمیز |
| تست بک‌اند | همه پاس (۱ Skip)؛ ۲۸۱ تابع تست |
| تست فرانت‌اند | ۳۲ از ۳۲ پاس؛ `vite build` موفق |
| وابستگی‌ها | `requirements.txt` و `package.json` بدون کتابخانهٔ بک‌اند جدید |

## ۲. Tagهای پیشنهادی (روی سیستم شما اجرا شود)

```powershell
git tag v3-phase0-baseline a0d93ce
git tag archive/prototype-2026-06 origin/master
git push origin v3-phase0-baseline archive/prototype-2026-06
```

شاخهٔ `master` حذف نشود؛ فقط Tag آرشیو بخورد.

## ۳. پشتیبان‌های موجود روی سرور

- شاخهٔ `backup-before-scalp-03a2bc5`
- فایل `/root/smartpips-server-changes-KEEP.tgz`
- پوشهٔ `~/smartpips-backups` (Dump دیتابیس با روال زیر)

## ۴. روال پشتیبان قبل از هر فاز (روی سرور)

```bash
cd /home/ubuntu/smartpips
mkdir -p ~/smartpips-backups
docker exec smartpips-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > ~/smartpips-backups/db-$(date +%Y%m%d-%H%M).dump
git rev-parse HEAD > ~/smartpips-backups/commit-$(date +%Y%m%d-%H%M).txt
```

متغیرها از محیط داخل Container خوانده می‌شوند؛ هیچ مقداری در مخزن یا گفتگو ثبت نمی‌شود. فایل Dump هرگز به گفتگو یا GitHub فرستاده نشود.

## ۵. Rollback کد

```bash
cd /home/ubuntu/smartpips
git fetch origin
git checkout <commit-قبلی>
docker compose up -d --build backend frontend
docker compose -f docker-compose.monitor.yml up -d --build
docker compose -f docker-compose.demo.yml up -d --build
```

## ۶. Rollback دیتابیس

- هر Migration جدید در V3 باید **برگشت‌پذیر** باشد (`migrate <app> <قبلی>`) و فقط افزایشی (ستون/جدول جدید، Nullable یا با Default).
- حذف ستون یا جدول فقط در فاز جداگانه و پس از یک دورهٔ مهاجرت.
- بازگردانی کامل فقط در صورت ضرورت و با تأیید صریح شما:

```bash
docker exec -i smartpips-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean' < ~/smartpips-backups/db-XXXX.dump
```

> این دستور داده‌های بعد از Dump را پاک می‌کند. بدون تأیید صریح اجرا نشود.

## ۷. قوانین هر فاز

1. شاخهٔ جدا برای هر فاز (`v3/phase-1a` و …).
2. Patch به‌همراه تست و SHA256؛ ابتدا روی سیستم شما، سپس GitHub، سپس سرور.
3. قبل از Deploy: پشتیبان طبق بخش ۴.
4. بعد از Deploy: `/api/auth/config/` و صفحهٔ هشدارها و یک سیگنال اسکالپ بررسی شود.
5. اگر خطا: بخش ۵.
6. هیچ تغییری مستقیم روی Production انجام نمی‌شود و هیچ سفارش واقعی بدون مجوز صریح ارسال نمی‌شود.

## ۸. بررسی وضعیت سیستم شما (قبل از Phase 1a)

```powershell
git status
git stash list
git tag
git log --oneline -5
```

اگر Stash یا فایل Untracked مهمی وجود دارد، قبل از شروع Phase 1a مشخص شود.
