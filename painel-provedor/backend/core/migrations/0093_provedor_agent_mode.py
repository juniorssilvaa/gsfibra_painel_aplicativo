from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0092_mensagemsistema_superadmin_message_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='agent_mode',
            field=models.CharField(
                choices=[
                    ('isp', 'Provedor de Internet'),
                    ('support', 'Suporte da Plataforma'),
                ],
                default='isp',
                help_text='isp = regras de ISP/SGP; support = atendimento da plataforma (sem SGP/fatura de internet)',
                max_length=20,
                verbose_name='Modo do Agente de IA',
            ),
        ),
    ]
