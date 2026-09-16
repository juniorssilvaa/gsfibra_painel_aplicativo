from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0104_canal_somente_disparo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='canal',
            name='somente_disparo',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Se ativo, este canal é tratado como canal de disparo: não gera protocolo e '
                    'não aplica timeout/transferência automática do chatbot.'
                ),
                verbose_name='Somente disparo',
            ),
        ),
        migrations.AddField(
            model_name='canal',
            name='disparo_resposta_acao',
            field=models.CharField(
                choices=[
                    ('fila', 'Enviar para fila humana'),
                    ('encerrar', 'Manter atendimento encerrado'),
                ],
                default='fila',
                help_text=(
                    'Só vale com “Somente disparo” ativo: se o cliente responder, '
                    'enviar para a fila humana ou manter o atendimento encerrado.'
                ),
                max_length=20,
                verbose_name='Ao responder no canal de disparo',
            ),
        ),
    ]
