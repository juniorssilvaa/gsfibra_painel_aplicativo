from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0103_provedor_ai_inform_hours_after_comprovante_transfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='canal',
            name='somente_disparo',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Se ativo, este canal é tratado como canal de disparo: não gera protocolo, '
                    'não aplica timeout/transferência automática do chatbot e respostas do cliente '
                    'vão direto para a fila humana.'
                ),
                verbose_name='Somente disparo',
            ),
        ),
    ]
