from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0101_canal_tipo_app_mobile'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='attendance_national_holidays',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    'Overrides de ativação dos feriados nacionais. '
                    'Lista de {id, active}; ids ausentes ficam ativos por padrão. '
                    'Nome e data não são editáveis pelo provedor.'
                ),
                verbose_name='Feriados nacionais (overrides)',
            ),
        ),
    ]
