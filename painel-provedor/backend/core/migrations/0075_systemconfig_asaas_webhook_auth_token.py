from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0074_user_provedor_alter_mensagemsistema_tipo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemconfig",
            name="asaas_webhook_auth_token",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="Asaas Webhook Auth Token",
            ),
        ),
    ]

