# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0058_add_openai_transcription_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='assignment_message',
            field=models.TextField(blank=True, help_text='Mensagem enviada automaticamente ao atribuir um atendimento a este usuário', null=True, verbose_name='Mensagem de Atribuição'),
        ),
    ]

