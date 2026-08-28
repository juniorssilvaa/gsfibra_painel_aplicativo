from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0094_provedor_support_transfer_notify_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='chatbot_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Nome exibido no canto superior das mensagens automáticas do bot '
                    'em todos os canais (WhatsApp, Telegram, Instagram, etc.).'
                ),
                max_length=80,
                verbose_name='Nome do chatbot',
            ),
        ),
    ]
