import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0011_provedor_agent_mode'),
        ('mobile_app', '0005_mobileappprofile_privacy_text'),
    ]

    operations = [
        migrations.CreateModel(
            name='MobileSupportMedia',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('cpf', models.CharField(db_index=True, max_length=20)),
                ('file', models.FileField(upload_to='mobile_support/%Y/%m/')),
                ('content_type', models.CharField(blank=True, default='', max_length=120)),
                ('original_name', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provedor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mobile_support_media',
                    to='super_core.provedor',
                )),
            ],
            options={
                'verbose_name': 'Mídia do chat do app',
                'verbose_name_plural': 'Mídias do chat do app',
                'ordering': ['-created_at'],
            },
        ),
    ]
