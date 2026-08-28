from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0021_team_horarios_atendimento'),
        ('core', '0098_provedor_automation_schedule_and_holidays'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='automation_schedule_fallback_team',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Usada no modo "dentro do horário comercial": fora do expediente (ou em feriado), '
                    'os atendimentos vão para esta equipe enquanto a IA/chatbot estão desligados.'
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='provedores_fallback_automacao',
                to='conversations.team',
                verbose_name='Equipe quando a automação estiver desligada',
            ),
        ),
    ]
