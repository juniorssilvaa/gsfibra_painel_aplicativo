from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0003_notification_log_recipients'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='terms_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
