from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0065_add_resposta_rapida'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='new_message_sound_volume',
            field=models.FloatField(default=1.0, verbose_name='Volume das Novas Mensagens'),
        ),
        migrations.AddField(
            model_name='user',
            name='new_conversation_sound_volume',
            field=models.FloatField(default=1.0, verbose_name='Volume das Novas Conversas'),
        ),
    ]
