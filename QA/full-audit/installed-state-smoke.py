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
 old=[('trades','0008_accounting_provenance'),('ctrader','0001_initial')]
 executor=MigrationExecutor(connection);state=executor.loader.project_state(old)
 with connection.schema_editor() as editor:
  for model in state.apps.get_models():
   if model._meta.db_table not in connection.introspection.table_names():editor.create_model(model)
 recorder=MigrationRecorder(connection);recorder.ensure_schema()
 for target in old:
  for app,name in executor.loader.graph.forwards_plan(target):recorder.record_applied(app,name)
 User=state.apps.get_model('auth','User');Trade=state.apps.get_model('trades','Trade')
 u=User.objects.create(username='old-user',password='fixture')
 t=Trade.objects.create(user_id=u.pk,symbol='BTCUSDT',entry_price=100,size=100,status='closed',pnl=214,realized_pnl=15,remaining_pct=60)
 before=set(recorder.applied_migrations());call_command('prepare_entry_audit');assert set(recorder.applied_migrations())==before
 call_command('prepare_entry_audit',apply=True)
 after=set(recorder.applied_migrations());assert after-before=={('trades','0009_entry_audit'),('ctrader','0002_oauthattempt')}
 from apps.trades.models import Trade as Current
 current=Current.objects.get(pk=t.pk)
 assert current.pnl==214 and current.realized_pnl==15 and current.remaining_pct==60 and current.entry_snapshot=={} and current.entry_snapshot_hash==''
 call_command('prepare_entry_audit',apply=True);assert set(recorder.applied_migrations())==after
 print(json.dumps({'upgrade':'PASS','dry_run_no_writes':'PASS','repeat':'PASS','history_preserved':'PASS','db':'SQLite installed-state simulation; NOT PostgreSQL/fresh install'}))
