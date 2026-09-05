from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0004_mobileappprofile_terms_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='privacy_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
