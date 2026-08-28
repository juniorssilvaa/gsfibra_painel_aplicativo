# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0018_add_message_reaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='last_user_message_at',
            field=models.DateTimeField(blank=True, help_text='Timestamp da última mensagem recebida do cliente (para cálculo da janela de 24 horas)', null=True),
        ),
    ]

