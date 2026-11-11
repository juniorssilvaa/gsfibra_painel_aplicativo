# Generated manually for notification log recipients detail

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0002_activity_log_and_app_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='notif_type',
            field=models.CharField(blank=True, default='info', max_length=20),
        ),
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='link',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='image_url',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='segment_type',
            field=models.CharField(blank=True, default='all', max_length=32),
        ),
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='recipients',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='mobilenotificationlog',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterModelOptions(
            name='mobilenotificationlog',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Log de notificação',
                'verbose_name_plural': 'Logs de notificação',
            },
        ),
    ]
