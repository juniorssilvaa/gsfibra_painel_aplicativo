import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0011_mobileappprofile_app_bg_card_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='home_logo_position',
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
    ]
