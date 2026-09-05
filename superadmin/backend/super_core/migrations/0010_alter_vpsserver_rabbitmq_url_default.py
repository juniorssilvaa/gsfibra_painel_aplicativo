# Generated manually — default antigo apontava para localhost e quebrava Dramatiq em Docker.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("super_core", "0009_provedor_integration_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vpsserver",
            name="rabbitmq_url",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
