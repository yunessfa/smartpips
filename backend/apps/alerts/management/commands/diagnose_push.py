"""Diagnose Web-Push setup: VAPID keys, subscriptions, and a live send attempt."""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check why push notifications might not be sending."

    def handle(self, *args, **opts):
        pub = settings.VAPID_PUBLIC_KEY or ""
        priv = settings.VAPID_PRIVATE_KEY or ""
        claim = settings.VAPID_CLAIM_EMAIL or ""

        self.stdout.write("=== VAPID configuration ===")
        self.stdout.write(f"public key set:  {bool(pub)} (len={len(pub)})")
        self.stdout.write(f"private key set: {bool(priv)} (len={len(priv)})")
        self.stdout.write(f"claim email:     {claim!r}")
        if not pub or not priv:
            self.stdout.write(self.style.ERROR(
                "VAPID keys missing. Run: python manage.py gen_vapid  then put them in .env"))
            return
        if claim and not str(claim).startswith("mailto:"):
            self.stdout.write(self.style.WARNING(
                "claim email should start with 'mailto:' (the code now auto-fixes this)"))

        try:
            import pywebpush  # noqa
            self.stdout.write(f"pywebpush installed: yes")
        except ImportError:
            self.stdout.write(self.style.ERROR("pywebpush NOT installed (pip install pywebpush)"))
            return

        from apps.alerts.models import PushSubscription
        from apps.alerts.push import send_push

        total = PushSubscription.objects.count()
        enabled = PushSubscription.objects.filter(enabled=True).count()
        self.stdout.write("\n=== Subscriptions ===")
        self.stdout.write(f"total: {total} | enabled: {enabled}")
        if not enabled:
            self.stdout.write(self.style.WARNING(
                "No enabled subscriptions. Open the app, allow notifications, "
                "then re-run. On iPhone you must Add to Home Screen first."))
            return

        self.stdout.write("\n=== Live send attempt ===")
        payload = {"title": "SmartPips", "body": "Diagnostic ping ✅", "url": "/app/scalp"}
        ok_n = 0
        for sub in PushSubscription.objects.filter(enabled=True).select_related("user")[:10]:
            ok, err = send_push(sub, payload, debug=True)
            user = getattr(sub.user, "username", "?")
            endpoint = (sub.as_subscription_info().get("endpoint", "")[:45] + "…")
            if ok:
                ok_n += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ sent to {user} [{endpoint}]"))
            else:
                self.stdout.write(self.style.ERROR(f"  ✗ {user} [{endpoint}] -> {err}"))
        self.stdout.write(f"\nSent OK: {ok_n}/{enabled}")
        if ok_n == 0:
            self.stdout.write(self.style.WARNING(
                "\nAll sends failed. The most common cause is a VAPID key mismatch: the "
                "subscriptions were created with a DIFFERENT public key than the server "
                "now has. Fix: keep VAPID keys stable in .env, then have users toggle "
                "notifications OFF and ON again to re-subscribe with the current key."))
