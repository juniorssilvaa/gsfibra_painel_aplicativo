from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0020_rename_message_rea_message_emoji_idx_message_rea_message_7f9ef3_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='horarios_atendimento',
            field=models.TextField(
                blank=True,
                help_text='Horários desta equipe (JSON). Vazio = usa o horário global do provedor.',
                null=True,
            ),
        ),
    ]
