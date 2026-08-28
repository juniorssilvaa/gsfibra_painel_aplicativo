from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0099_provedor_automation_schedule_fallback_team'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='invoice_intro_message_template',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Texto enviado ao cliente antes/junto dos dados de pagamento da fatura '
                    '(IA e chatbot). Vazio = padrão do sistema. Variáveis: {{vencimento}}, '
                    '{{valor}}, {{valor_original}}, {{multa}}, {{juros}}, {{valores_texto}}, '
                    '{{fatura_id}}, {{nome_cliente}}, {{nome_provedor}}.'
                ),
                verbose_name='Mensagem introdutória da fatura',
            ),
        ),
    ]
