import os,tempfile,json
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
from django.conf import settings
with tempfile.TemporaryDirectory() as folder:
 settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':folder+'/upgrade.sqlite3'}}
 import django;django.setup()
 from django.db import connection
 from django.db.migrations.executor import MigrationExecutor
 from django.db.migrations.recorder import MigrationRecorder
 from django.core.management import call_command
 old=('trades','0007_merge_20260812_1149')
 executor=MigrationExecutor(connection)
 state=executor.loader.project_state([old])
 # Recreate an ALREADY-INSTALLED schema from the exact historical migration state.
 # This deliberately does NOT claim the old conflicting migrations support fresh install.
 with connection.schema_editor() as editor:
  for model in state.apps.get_models():
   if model._meta.db_table not in connection.introspection.table_names():editor.create_model(model)
 recorder=MigrationRecorder(connection);recorder.ensure_schema()
 for app,name in executor.loader.graph.forwards_plan(old):recorder.record_applied(app,name)
 User=state.apps.get_model('auth','User');Trade=state.apps.get_model('trades','Trade')
 u=User.objects.create(username='old-user',password='fixture')
 t=Trade.objects.create(user_id=u.pk,symbol='BTCUSDT',entry_price=100,size=100,status='closed',pnl=214,realized_pnl=15,remaining_pct=60)
 before=set(recorder.applied_migrations())
 call_command('prepare_trade_accounting')
 after=set(recorder.applied_migrations())
 assert after-before=={('trades','0008_accounting_provenance')}
 from apps.trades.models import Trade as Current
 current=Current.objects.get(pk=t.pk)
 assert current.pnl==214 and current.realized_pnl==15 and current.remaining_pct==60
 assert current.fees_paid is None and current.net_pnl is None and not current.execution_verified
 call_command('prepare_trade_accounting')
 assert set(recorder.applied_migrations())==after
 print(json.dumps({'upgrade_migration':'PASS','repeat_idempotent':'PASS','historical_values_preserved':'PASS','db':'SQLite installed-state simulation, NOT PostgreSQL / fresh-install validation'}))
