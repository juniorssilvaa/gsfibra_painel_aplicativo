from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0096_provider_suggestion'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='whatsapp_alert_transfer',
            field=models.BooleanField(
                default=True,
                verbose_name='Avisar quando um atendimento for transferido para mim',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='whatsapp_alert_waiting',
            field=models.BooleanField(
                default=True,
                verbose_name='Avisar quando entrar um atendimento na fila de espera',
            ),
        ),
    ]
