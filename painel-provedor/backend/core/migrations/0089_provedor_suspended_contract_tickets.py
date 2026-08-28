from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0088_canal_tipo_instagram'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='allow_ticket_when_contract_suspended',
            field=models.BooleanField(
                default=False,
                verbose_name='Permitir chamado com contrato suspenso',
                help_text=(
                    'Se desativado (padrão), clientes com contrato suspenso não conseguem '
                    'abrir chamado técnico no fluxo de atendimento (chatbot).'
                ),
            ),
        ),
        migrations.AddField(
            model_name='provedor',
            name='suspended_contract_ticket_message',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Mensagem ao bloquear chamado (contrato suspenso)',
                help_text='Mensagem enviada ao cliente quando o chamado é bloqueado. Vazio = mensagem padrão do sistema.',
            ),
        ),
    ]
