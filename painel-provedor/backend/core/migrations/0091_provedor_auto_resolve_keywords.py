from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0090_provedor_send_financial_menu_suspended'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='auto_resolve_keyword_filter_enabled',
            field=models.BooleanField(
                default=False,
                verbose_name='Filtrar mensagens automáticas',
                help_text=(
                    'Quando ligado, mensagens automáticas de confirmação de pagamento '
                    'enviadas por integração externa não reabrem atendimentos já encerrados pelo chatbot.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='provedor',
            name='auto_resolve_keywords',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Termos do filtro',
                help_text='Um termo por linha. Obrigatório quando o filtro estiver ligado.',
            ),
        ),
    ]
