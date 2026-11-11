from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0008_provedor_panel_bootstrap_password_ciphertext'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='integration_token',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='provedor',
            name='integration_token_last_used_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
