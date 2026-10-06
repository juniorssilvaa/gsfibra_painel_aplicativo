from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='marketingasset',
            name='descricao',
            field=models.TextField(blank=True, default='', help_text='Descrição visual da referência, lida pela IA do chat'),
        ),
    ]
