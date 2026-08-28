from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0089_provedor_suspended_contract_tickets'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='send_financial_menu_after_suspended_block',
            field=models.BooleanField(
                default=False,
                verbose_name='Enviar menu financeiro após bloquear chamado (suspenso)',
                help_text=(
                    'Se ativado, após a mensagem de bloqueio o chatbot envia o menu financeiro '
                    'do fluxo (2ª via, liberação por confiança, etc.), quando existir no fluxo ativo.'
                ),
            ),
        ),
    ]
