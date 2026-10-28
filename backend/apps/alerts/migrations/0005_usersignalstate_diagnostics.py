from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0004_usersignalstate")]
    operations = [
        migrations.AddField(model_name="usersignalstate", name="last_checked",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="usersignalstate", name="last_reason",
                            field=models.CharField(blank=True, max_length=200)),
    ]
