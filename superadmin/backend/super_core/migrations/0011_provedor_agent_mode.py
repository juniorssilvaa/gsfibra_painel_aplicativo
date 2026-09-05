from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0010_alter_vpsserver_rabbitmq_url_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='agent_mode',
            field=models.CharField(
                default='isp',
                help_text='isp = provedor de internet; support = suporte/comercial da plataforma',
                max_length=20,
            ),
        ),
    ]
