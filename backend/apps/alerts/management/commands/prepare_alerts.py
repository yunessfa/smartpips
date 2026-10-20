"""Apply only the new user-scoped signal-state migration on an installed DB."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.alerts.models import UserSignalState


class Command(BaseCommand):
    help = 'Verify/apply alerts.0004_usersignalstate only; never fake historical migrations.'

    def add_arguments(self, parser):
        parser.add_argument('--require-persistent-db', action='store_true')

    def handle(self, *args, **options):
        if options.get('require_persistent_db') and connection.vendor == 'sqlite':
            raise CommandError('SQLite detected; inspect the persistent mount before deploying.')
        target = ('alerts', '0004_usersignalstate')
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([target])
        if any((m.app_label, m.name) != target or backwards for m, backwards in plan):
            raise CommandError('Other prerequisite migrations are pending. Nothing was applied. '
                               'Inspect showmigrations alerts trades; do not use --fake.')
        table = UserSignalState._meta.db_table
        exists = table in connection.introspection.table_names()
        if bool(plan) == exists:
            raise CommandError('Table/migration history mismatch. No changes made; inspect DB.')
        if plan:
            executor.migrate([target])
        with connection.cursor() as cursor:
            columns = {c.name for c in connection.introspection.get_table_description(cursor, table)}
        if not {'user_id', 'symbol', 'timeframe', 'last_signal', 'context'}.issubset(columns):
            raise CommandError('User signal-state schema incomplete. Inspect database.')
        self.stdout.write(self.style.SUCCESS('User-scoped alert schema ready. Historical migrations untouched.'))
