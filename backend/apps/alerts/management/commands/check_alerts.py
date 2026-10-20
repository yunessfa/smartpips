"""Evaluate every user's position alert rules once.

Run this from cron next to monitor_scalp, e.g. every minute:

    * * * * * cd /var/www/smartpips/backend && /var/www/smartpips/backend/.venv/bin/python manage.py check_alerts >> /var/log/smartpips_alerts.log 2>&1

Unlike monitor_scalp this does not need VAPID: rules always write an internal
notification, and Web Push is only a bonus delivery channel when configured.
"""
from django.core.management.base import BaseCommand

from apps.alerts.rules import run_all


class Command(BaseCommand):
    help = "Check user-defined alert rules against their open trades."

    def handle(self, *args, **options):
        fired = run_all()
        if fired:
            self.stdout.write(self.style.SUCCESS(f"{fired} alert(s) fired."))
        else:
            self.stdout.write("No alerts fired.")
