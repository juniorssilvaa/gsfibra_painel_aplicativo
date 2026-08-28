from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0086_provedor_csat_interval_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='totp_secret',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='Secret TOTP (2FA)'),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_enabled',
            field=models.BooleanField(default=False, verbose_name='2FA ativo'),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_enabled_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='2FA ativado em'),
        ),
    ]
