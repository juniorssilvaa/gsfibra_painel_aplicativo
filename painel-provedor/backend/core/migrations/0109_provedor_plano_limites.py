from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0108_backfill_user_last_login'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='plano_nome',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Plano contratado'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='plano_max_canais',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Limite de canais do plano'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='plano_max_usuarios',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Limite de usuários do plano'),
        ),
    ]
