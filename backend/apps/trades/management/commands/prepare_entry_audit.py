"""Fail-closed additive upgrade from an already installed, consistent baseline."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

class Command(BaseCommand):
    help="Inspect/apply only trades.0009 and ctrader.0002. Never repairs/fakes historical migration conflicts."
    def add_arguments(self,p):
        p.add_argument("--apply",action="store_true")
        p.add_argument("--require-persistent-db",action="store_true")
    def handle(self,*args,**o):
        if o["require_persistent_db"] and connection.vendor!="postgresql":
            raise CommandError("Production release requires the inspected PostgreSQL database.")
        targets=[("trades","0009_entry_audit"),("ctrader","0002_oauthattempt")]
        executor=MigrationExecutor(connection);executor.loader.check_consistent_history(connection)
        plan=executor.migration_plan(targets)
        if any(backwards or (m.app_label,m.name) not in targets for m,backwards in plan):
            raise CommandError("Historical prerequisites or reverse migration in plan. STOP; restore/test baseline; do not --fake.")
        tables=set(connection.introspection.table_names())
        for app,table,target,columns in (
            ("trades","trades_trade",targets[0],{"entry_snapshot","entry_snapshot_hash"}),):
            if table not in tables:raise CommandError(f"Missing installed table {table}.")
            with connection.cursor() as c:
                actual={x.name for x in connection.introspection.get_table_description(c,table)}
            pending=any((m.app_label,m.name)==target for m,_ in plan)
            if pending and columns.intersection(actual):raise CommandError("Snapshot schema/history mismatch; nothing applied.")
            if not pending and not columns.issubset(actual):raise CommandError("Applied snapshot schema is incomplete.")
        pending_names={(m.app_label,m.name) for m,_ in plan}
        for target,table in ((targets[0],"trades_tradeevent"),(targets[1],"ctrader_oauthattempt")):
            if (target in pending_names)==(table in tables):
                raise CommandError(f"Schema/history mismatch for {table}; nothing applied.")
        self.stdout.write(json.dumps({"vendor":connection.vendor,"plan":[f"{m.app_label}.{m.name}" for m,_ in plan],"backwards":False,"apply":o["apply"]}))
        if o["apply"]:
            executor.migrate(targets)
            self.stdout.write("Additive audit schema ready; historical journal rows were not rewritten.")
