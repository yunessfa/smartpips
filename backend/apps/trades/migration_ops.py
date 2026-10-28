"""Idempotent schema operations for the trades migration history.

The regenerated ``0001_initial`` already creates columns that later migrations
(0002 setup_class, 0005 partial-TP fields) add again. Databases created from the
original history applied those later migrations long ago, so they are never
re-run there; a clean install, however, failed with ``duplicate column``.
``AddFieldIfMissing`` keeps the migration state identical to ``AddField`` but
only touches the database when the column is really absent.
"""
from django.db import migrations


def _has_column(schema_editor, model, column):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, model._meta.db_table)
    return any(col.name == column for col in description)


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        to_model = to_state.apps.get_model(app_label, self.model_name)
        field = to_model._meta.get_field(self.name)
        if _has_column(schema_editor, to_model, field.column):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # The column may belong to 0001_initial on clean installs; never drop it here.
        return

    def describe(self):
        return f"Add field {self.name} to {self.model_name} (skip if column exists)"
