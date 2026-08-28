from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0084_provedor_sgp_webhook_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='csat_delay_minutes',
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text='Minutos após o encerramento automático para disparar a pesquisa de satisfação ao cliente.',
                verbose_name='Delay CSAT (minutos)',
            ),
        ),
        migrations.AddField(
            model_name='provedor',
            name='csat_send_on_bot_inactivity_closure',
            field=models.BooleanField(
                default=True,
                help_text='Se ativado, o sistema envia CSAT quando o chatbot encerra a conversa por inatividade.',
                verbose_name='Enviar CSAT no encerramento por inatividade do bot',
            ),
        ),
    ]
