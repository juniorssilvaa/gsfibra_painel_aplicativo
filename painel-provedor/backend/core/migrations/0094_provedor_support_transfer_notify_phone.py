from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0093_provedor_agent_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='support_transfer_notify_phone',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Número que recebe resumo quando a IA transferir para qualquer equipe (ex.: 5599999999999)',
                max_length=30,
                verbose_name='WhatsApp para notificar transferências (Modo Suporte)',
            ),
        ),
    ]
