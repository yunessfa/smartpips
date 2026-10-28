"""NO-OP: WatchItem is already created by alerts/0001_initial.

History: two branches were developed in parallel (0002_notification_alertrule
and 0002_watchitem) and merged in 0003. Meanwhile 0001_initial also gained a
`CreateModel("WatchItem")`, so the table ended up being created twice in the
migration graph.

On the production database nobody noticed: 0001 created the table, 0002 was
recorded as applied at a time when it did not yet duplicate it. But any
migration run from an EMPTY database - which is exactly what
`manage.py test` does when it builds the test database - hits:

    psycopg2.errors.DuplicateTable: relation "alerts_watchitem" already exists

The operation list is therefore emptied. The migration stays in place (it must,
because 0003 depends on it and production has it recorded as applied); it
simply no longer tries to create a table that 0001 already created.

Nothing else to do: no data migration, no schema change, no reverse step.
"""
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = []
