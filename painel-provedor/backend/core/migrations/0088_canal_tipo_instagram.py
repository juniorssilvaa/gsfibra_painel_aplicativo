# Generated manually for Instagram channel type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0087_user_totp_2fa'),
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
                ],
                default='whatsapp',
                max_length=50,
            ),
        ),
    ]
