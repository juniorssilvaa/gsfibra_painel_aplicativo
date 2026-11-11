from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0010_mobileappprofile_app_default_theme'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='app_bg_color',
            field=models.CharField(blank=True, default='', max_length=7),
        ),
        migrations.AddField(
            model_name='mobileappprofile',
            name='card_color',
            field=models.CharField(blank=True, default='', max_length=7),
        ),
    ]
