from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0069_mensagemsistema_visivel_para_agentes'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemconfig',
            name='asaas_access_token',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Asaas Access Token'),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='asaas_sandbox',
            field=models.BooleanField(default=True, verbose_name='Asaas Sandbox Mode'),
        ),
    ]
