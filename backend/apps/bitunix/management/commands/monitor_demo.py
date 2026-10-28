import json
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from apps.bitunix.client import BitunixClient
from apps.bitunix.demo_monitor import sweep_demo


class Command(BaseCommand):
    help = "Independent DEMO polling monitor. Never sends real orders."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=10)

    def handle(self, *args, **opts):
        if opts["interval"] < 5:
            raise CommandError("Minimum polling interval is 5 seconds.")
        while True:
            close_old_connections()
            try:
                self.stdout.write(json.dumps(sweep_demo(BitunixClient())))
                self.stdout.flush()
            except Exception as exc:
                if not opts["loop"]:
                    raise CommandError(str(exc))
                self.stderr.write(f"Demo sweep failed: {type(exc).__name__}")
            if not opts["loop"]:
                break
            time.sleep(opts["interval"])