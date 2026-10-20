from django.core.management.base import BaseCommand

from apps.market.models import Asset


class Command(BaseCommand):
    help = "Remove forex assets from the watchlist (kept crypto + metals only)."

    def handle(self, *args, **options):
        qs = Asset.objects.filter(category="forex")
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {count} forex asset(s)."))
