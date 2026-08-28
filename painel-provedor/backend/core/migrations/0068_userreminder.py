from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0067_add_canal_to_chatbotflow'),
        ('conversations', '0019_add_last_user_message_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(verbose_name='Mensagem do Lembrete')),
                ('scheduled_time', models.DateTimeField(verbose_name='Data/Hora Agendada')),
                ('is_notified', models.BooleanField(default=False, verbose_name='Já Notificado')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reminders', to='conversations.contact')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Lembrete de Usuário',
                'verbose_name_plural': 'Lembretes de Usuários',
                'ordering': ['scheduled_time'],
            },
        ),
    ]
