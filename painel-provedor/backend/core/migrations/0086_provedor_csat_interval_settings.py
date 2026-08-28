from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0085_provedor_csat_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='csat_enforce_min_interval',
            field=models.BooleanField(
                default=True,
                help_text='Se ativado, o sistema não envia novas pesquisas de CSAT para o mesmo contato em um intervalo menor que o configurado.',
                verbose_name='Respeitar intervalo mínimo entre envios de CSAT',
            ),
        ),
        migrations.AddField(
            model_name='provedor',
            name='csat_min_interval_hours',
            field=models.PositiveSmallIntegerField(
                default=24,
                help_text='Quantidade mínima de horas entre envios de CSAT para o mesmo contato.',
                verbose_name='Intervalo mínimo entre envios (horas)',
            ),
        ),
    ]
