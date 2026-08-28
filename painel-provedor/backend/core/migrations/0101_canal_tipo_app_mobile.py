# Generated manually for Aplicativo (app_mobile) channel type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0100_provedor_invoice_intro_message_template'),
    ]

    operations = [
        migrations.AlterField(
            model_name='canal',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('whatsapp', 'WhatsApp'),
                    ('whatsapp_session', 'WhatsApp QR code'),
                    ('whatsapp_oficial', 'WhatsApp Oficial'),
                    ('telegram', 'Telegram'),
                    ('email', 'Email'),
                    ('webchat', 'WebChat'),
                    ('instagram', 'Instagram'),
                    ('app_mobile', 'Aplicativo'),
                ],
                default='whatsapp',
                max_length=50,
            ),
        ),
    ]
