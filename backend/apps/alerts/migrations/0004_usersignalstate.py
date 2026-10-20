from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('alerts', '0003_merge_0002_notification_alertrule_0002_watchitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name='UserSignalState',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('symbol', models.CharField(max_length=20)),
            ('timeframe', models.CharField(max_length=8)),
            ('last_signal', models.CharField(default='wait', max_length=8)),
            ('last_score', models.IntegerField(default=0)),
            ('context', models.CharField(blank=True, max_length=64)),
            ('updated', models.DateTimeField(auto_now=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                      related_name='alert_signal_states', to=settings.AUTH_USER_MODEL)),
        ],
        options={'constraints': [models.UniqueConstraint(fields=('user', 'symbol', 'timeframe'),
                                                         name='alerts_user_signal_unique')]},
    )]
