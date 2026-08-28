from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0055_mensagemsistema_assunto_mensagemsistema_mensagem_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='provedor',
            name='redes_sociais',
            field=models.JSONField(default=dict, blank=True, help_text='Redes sociais da empresa'),
        ),
    ]
