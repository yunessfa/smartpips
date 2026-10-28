from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [("ctrader", "0001_initial")]
    operations = [migrations.CreateModel(name="OAuthAttempt", fields=[
        ("nonce", models.CharField(max_length=64, primary_key=True, serialize=False)),
        ("expires_at", models.DateTimeField()), ("consumed", models.BooleanField(default=False))])]
