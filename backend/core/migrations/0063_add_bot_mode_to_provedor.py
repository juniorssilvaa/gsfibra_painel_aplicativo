from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0062_chatbotflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='bot_mode',
            field=models.CharField(
                choices=[('ia', 'Inteligência Artificial'), ('chatbot', 'Fluxo de Chatbot')],
                default='ia',
                help_text='Define se o provedor usa IA ou um fluxo de chatbot pré-definido',
                max_length=20,
                verbose_name='Modo de Atendimento'
            ),
        ),
    ]
