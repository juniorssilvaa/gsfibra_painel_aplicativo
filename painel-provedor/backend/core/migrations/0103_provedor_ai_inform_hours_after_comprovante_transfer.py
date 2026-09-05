from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0102_provedor_attendance_national_holidays'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='ai_inform_hours_after_comprovante_transfer',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Se ativado, após receber comprovante a IA pode informar horário/feriado '
                    'quando a transferência for fora do expediente. '
                    'Desativado (padrão): confirma o comprovante e transfere sem informar '
                    'horário de funcionamento nem detalhes da transferência ao cliente.'
                ),
                verbose_name='Informar horário ao transferir comprovante',
            ),
        ),
    ]
