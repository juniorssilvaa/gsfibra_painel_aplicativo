# Generated manually for AgentPushDevice

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0106_mensagemsistema_imagem_hotspots'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentPushDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=512, unique=True, verbose_name='FCM Token')),
                ('platform', models.CharField(blank=True, default='', max_length=20, verbose_name='Plataforma')),
                ('device_name', models.CharField(blank=True, default='', max_length=120, verbose_name='Aparelho')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='push_devices',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Usuário',
                )),
            ],
            options={
                'verbose_name': 'Dispositivo Push do Atendente',
                'verbose_name_plural': 'Dispositivos Push dos Atendentes',
                'ordering': ['-updated_at'],
            },
        ),
    ]
