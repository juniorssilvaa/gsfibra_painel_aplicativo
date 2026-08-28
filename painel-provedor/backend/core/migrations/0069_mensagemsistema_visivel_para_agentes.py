from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0068_userreminder'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensagemsistema',
            name='visivel_para_agentes',
            field=models.BooleanField(default=True, verbose_name='Visível para Atendentes'),
        ),
    ]
