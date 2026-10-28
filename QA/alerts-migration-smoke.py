import os,tempfile,json
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
from django.conf import settings
with tempfile.TemporaryDirectory() as folder:
 settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':folder+'/test.sqlite3'}}
 import django;django.setup()
 from django.core.management import call_command
 from django.db.migrations.recorder import MigrationRecorder
 from django.db import connection
 from apps.alerts.models import UserSignalState
 from django.contrib.auth.models import User
 call_command('migrate','auth',verbosity=0)
 call_command('migrate','alerts','0003_merge_0002_notification_alertrule_0002_watchitem',verbosity=0)
 before=set(MigrationRecorder.Migration.objects.values_list('app','name'))
 call_command('prepare_alerts',verbosity=0)
 after=set(MigrationRecorder.Migration.objects.values_list('app','name'))
 assert after-before=={('alerts','0004_usersignalstate')}
 call_command('prepare_alerts',verbosity=0)
 u=User.objects.create_user('migration-fixture')
 UserSignalState.objects.create(user=u,symbol='BTCUSDT',timeframe='1m')
 assert UserSignalState.objects.count()==1
 print(json.dumps({'real_migrations':'pass','only_new_alert_migration_applied':'pass','idempotent':'pass','db':'SQLite, not PostgreSQL'}))
