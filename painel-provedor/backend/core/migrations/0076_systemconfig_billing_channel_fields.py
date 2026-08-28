from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0075_systemconfig_asaas_webhook_auth_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemconfig",
            name="billing_channel_enabled",
            field=models.BooleanField(default=False, verbose_name="Canal de Cobranca Ativo"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_days_before_due",
            field=models.IntegerField(default=3, verbose_name="Dias Antes do Vencimento"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_run_days",
            field=models.CharField(default="0,1,2,3,4,5,6", max_length=20, verbose_name="Dias da Semana da Rotina"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_run_time",
            field=models.CharField(default="09:00", max_length=5, verbose_name="Horario da Rotina (HH:MM)"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_template_due_soon",
            field=models.TextField(
                blank=True,
                default="Olá {{nome}}, sua fatura de {{valor}} vence em {{vencimento}} (ID: {{fatura_id}}).",
                verbose_name="Mensagem para Fatura a Vencer",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_template_overdue",
            field=models.TextField(
                blank=True,
                default="Olá {{nome}}, sua fatura {{fatura_id}} de {{valor}} venceu em {{vencimento}}. Evite bloqueio realizando o pagamento.",
                verbose_name="Mensagem para Fatura Vencida",
            ),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_whatsapp_phone_number_id",
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name="Billing Phone Number ID"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_whatsapp_token",
            field=models.TextField(blank=True, null=True, verbose_name="Billing WhatsApp Access Token"),
        ),
        migrations.AddField(
            model_name="systemconfig",
            name="billing_whatsapp_waba_id",
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name="Billing WABA ID"),
        ),
    ]

