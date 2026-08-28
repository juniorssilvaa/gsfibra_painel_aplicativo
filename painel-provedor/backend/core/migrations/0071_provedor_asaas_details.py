from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0070_add_asaas_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='cpf_cnpj',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='CPF/CNPJ'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Telefone Fixo'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='mobile_phone',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Celular'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='address_number',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Número'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='complement',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Complemento'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='province',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Bairro'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='postal_code',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='CEP'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='group_name',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Grupo'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='company',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Nome da Empresa (Asaas)'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='municipal_inscription',
            field=models.CharField(blank=True, max_length=30, null=True, verbose_name='Inscrição Municipal'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='state_inscription',
            field=models.CharField(blank=True, max_length=30, null=True, verbose_name='Inscrição Estadual'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='observations',
            field=models.TextField(blank=True, null=True, verbose_name='Observações'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='additional_emails',
            field=models.TextField(blank=True, help_text='Separados por vírgula', null=True, verbose_name='E-mails Adicionais'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='notification_disabled',
            field=models.BooleanField(default=False, verbose_name='Notificações Desativadas'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='foreign_customer',
            field=models.BooleanField(default=False, verbose_name='Cliente Estrangeiro'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='asaas_customer_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Asaas Customer ID'),
        ),
    ]
