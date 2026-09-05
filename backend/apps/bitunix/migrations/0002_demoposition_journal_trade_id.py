from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bitunix", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="demoposition",
            name="journal_trade_id",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
