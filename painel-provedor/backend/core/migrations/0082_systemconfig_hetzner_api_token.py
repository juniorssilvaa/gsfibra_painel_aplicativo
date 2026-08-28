from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0081_providergalleryimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemconfig',
            name='hetzner_api_token',
            field=models.TextField(blank=True, null=True, verbose_name='Hetzner API Token'),
        ),
    ]
