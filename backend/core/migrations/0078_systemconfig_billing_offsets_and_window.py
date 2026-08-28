from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0077_systemconfig_billing_whatsapp_template_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemconfig",
            name="billing_reminder_due_offsets",
            field=models.CharField(
                max_length=120,
                blank=True,
                default="",
                verbose_name="Offsets de vencimento (cobrança)",
                help_text="Ex.: -1,0,2 = 1 dia antes, no dia, e 2 dias após o vencimento. Vazio = usa só Dias antes (legado).",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_run_window_minutes",
            field=models.PositiveSmallIntegerField(
                default=12,
                verbose_name="Janela de minutos após o horário da rotina",
                help_text="Após HH:MM, por quantos minutos o ciclo pode rodar (ex.: 12). Evita disparar horas depois.",
            ),
        ),
    ]
