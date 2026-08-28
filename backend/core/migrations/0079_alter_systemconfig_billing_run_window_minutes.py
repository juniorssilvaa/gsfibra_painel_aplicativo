from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0078_systemconfig_billing_offsets_and_window"),
    ]

    operations = [
        migrations.AlterField(
            model_name="systemconfig",
            name="billing_reminder_due_offsets",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Lista separada por vírgula. Negativos/zero = antes ou no vencimento; positivos = dias após vencido. Vazio = usa só o campo legado “dias antes”.",
                max_length=120,
                verbose_name="Dias de cobrança em relação ao vencimento",
            ),
        ),
        migrations.AlterField(
            model_name="systemconfig",
            name="billing_run_window_minutes",
            field=models.SmallIntegerField(
                default=0,
                help_text="0 = roda só no minuto escolhido (ex.: 08:30). Maior que 0 = aceita até N minutos depois, se a tarefa atrasar.",
                verbose_name="Margem em minutos após o horário (0 = minuto exato)",
            ),
        ),
    ]
