# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_add_systemconfig_key_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='canal',
            name='ia_ativa',
            field=models.BooleanField(default=True, help_text='Se desativado, a IA não responderá automaticamente neste canal, mas o provedor ainda poderá enviar e receber mensagens normalmente.', verbose_name='IA Ativa'),
        ),
    ]
