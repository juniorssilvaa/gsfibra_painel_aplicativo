from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0079_alter_systemconfig_billing_run_window_minutes"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemconfig",
            name="billing_provedor_auto_block_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name="Bloquear provedor automaticamente por fatura Asaas",
                help_text="Quando ligado, consulta o Asaas e suspende o provedor conforme os dias abaixo. Um ciclo roda em background cerca de a cada 15 minutos.",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_provedor_block_min_days_late",
            field=models.PositiveSmallIntegerField(
                default=4,
                verbose_name="Dias após o vencimento para bloquear",
                help_text="0 = qualquer fatura vencida (OVERDUE). 1 = pelo menos um dia após o vencimento. Valor 4 mantém o comportamento antigo do sistema.",
            ),
        ),
    ]
