"""Apply ONLY the refresh-session migration on an already installed database."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.accounts.models import RefreshSession


class Command(BaseCommand):
    help = 'Check/apply accounts.0004_refreshsession only; never fake or modify historical migrations.'

    def add_arguments(self, parser):
        parser.add_argument('--require-persistent-db', action='store_true',
                            help='Refuse SQLite in an ephemeral one-off Docker container.')

    def handle(self, *args, **options):
        if options.get('require_persistent_db') and connection.vendor == 'sqlite':
            raise CommandError('SQLite detected. One-off Docker migration would not update the running DB. '
                               'Back up and verify the persistent database mount before rebuilding/releasing.')
        target = ('accounts', '0004_refreshsession')
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([target])
        unexpected = [(m.app_label, m.name, backwards) for m, backwards in plan
                      if (m.app_label, m.name) != target or backwards]
        if unexpected:
            raise CommandError('Other prerequisite migrations are pending. No migration was applied. '
                               'Inspect showmigrations accounts auth contenttypes before proceeding.')
        table = RefreshSession._meta.db_table
        exists = table in connection.introspection.table_names()
        if plan and exists:
            raise CommandError('Refresh table exists but migration is not recorded; schema drift. '
                               'No changes made. Do not use --fake without inspection.')
        if not plan and not exists:
            raise CommandError('Refresh migration is recorded but table is missing; schema drift. '
                               'No changes made. Restore/inspect the database.')
        if plan:
            executor.migrate([target])
        with connection.cursor() as cursor:
            columns = {c.name for c in connection.introspection.get_table_description(cursor, table)}
        if not {'digest', 'user_id', 'access_id', 'expires_at', 'created'}.issubset(columns):
            raise CommandError('Refresh schema is incomplete. Inspect database before starting.')
        self.stdout.write(self.style.SUCCESS('Refresh-session schema ready. Historical migrations untouched.'))
