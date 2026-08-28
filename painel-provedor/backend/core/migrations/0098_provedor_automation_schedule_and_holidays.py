from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0097_user_whatsapp_alert_prefs'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='attendance_holidays',
            field=models.JSONField(blank=True, default=list, help_text='Lista de feriados e datas especiais usadas para regras de atendimento.', verbose_name='Feriados do provedor'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='automation_schedule_apply_holidays',
            field=models.BooleanField(default=True, help_text='Se ativado, os feriados cadastrados também influenciam o acionamento automático da IA/chatbot.', verbose_name='Aplicar feriados na automação'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='automation_schedule_enabled',
            field=models.BooleanField(default=False, help_text='Se ativado, a IA/chatbot liga e desliga automaticamente com base no horário comercial.', verbose_name='Ativar automação por horário'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='automation_schedule_mode',
            field=models.CharField(choices=[('outside_business_hours', 'Automação fora do horário comercial'), ('inside_business_hours', 'Automação dentro do horário comercial')], default='outside_business_hours', help_text='Define se a IA/chatbot funciona dentro ou fora do horário comercial.', max_length=32, verbose_name='Modo da automação por horário'),
        ),
    ]
