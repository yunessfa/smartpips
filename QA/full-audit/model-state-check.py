import os,tempfile
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django;django.setup()
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.apps import apps
loader=MigrationLoader(connection)
changes=MigrationAutodetector(loader.project_state(),ProjectState.from_apps(apps),NonInteractiveMigrationQuestioner()).changes(graph=loader.graph)
owned={k:[m.name for m in v] for k,v in changes.items() if k in ('trades','ctrader')}
print({'migration_model_drift':owned,'scope':'Model-state check only; not SQL/PostgreSQL execution'})
assert not owned
