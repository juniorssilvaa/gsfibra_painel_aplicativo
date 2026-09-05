# Generated manually for outdated apps + activity logs

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0013_product_suggestion_comment'),
        ('mobile_app', '0001_initial_mobile_app'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='latest_app_version',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='mobiledevice',
            name='app_version',
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True),
        ),
        migrations.CreateModel(
            name='MobileActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.CharField(choices=[
                    ('login', 'Login'),
                    ('logout', 'Logout'),
                    ('register', 'Cadastro no app'),
                    ('wifi_password_changed', 'Alterou senha Wi-Fi'),
                    ('wifi_ssid_changed', 'Alterou SSID Wi-Fi'),
                    ('ticket_opened', 'Abriu chamado'),
                    ('invoice_viewed', 'Visualizou fatura'),
                    ('push_received', 'Recebeu push'),
                    ('device_registered', 'Registrou dispositivo'),
                    ('other', 'Outro'),
                ], db_index=True, max_length=64)),
                ('event_label', models.CharField(blank=True, max_length=120)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=255, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('provedor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mobile_activity_logs',
                    to='super_core.provedor',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='activity_logs',
                    to='mobile_app.mobileappuser',
                )),
            ],
            options={
                'verbose_name': 'Log de atividade do App',
                'verbose_name_plural': 'Logs de atividade do App',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='mobileactivitylog',
            index=models.Index(fields=['provedor', '-created_at'], name='mobile_app__provedo_actlog_idx'),
        ),
    ]
