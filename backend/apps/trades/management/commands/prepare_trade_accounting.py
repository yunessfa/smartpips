from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.trades.models import Trade


class Command(BaseCommand):
    help = "Apply only additive trades.0008; never rewrite PnL or fake old migrations."

    def add_arguments(self, parser):
        parser.add_argument("--require-persistent-db", action="store_true")

    def handle(self, *args, **options):
        if options["require_persistent_db"] and connection.vendor == "sqlite":
            raise CommandError("SQLite detected; inspect persistent DB configuration.")
        target = ("trades", "0008_accounting_provenance")
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([target])
        if any((m.app_label, m.name) != target or backwards for m, backwards in plan):
            raise CommandError("Historical prerequisites pending. Nothing applied; do not --fake.")
        with connection.cursor() as c:
            columns = {v.name for v in connection.introspection.get_table_description(c, Trade._meta.db_table)}
        expected = {"fees_paid", "funding_paid", "costs_verified", "execution_verified",
                    "external_order_id", "external_position_id", "execution_evidence"}
        if plan and expected.intersection(columns):
            raise CommandError("Schema/history mismatch. Nothing applied.")
        if plan:
            executor.migrate([target])
        with connection.cursor() as c:
            columns = {v.name for v in connection.introspection.get_table_description(c, Trade._meta.db_table)}
        if not expected.issubset(columns):
            raise CommandError("Accounting schema incomplete.")
        self.stdout.write("Accounting schema ready. Historical trade values untouched.")