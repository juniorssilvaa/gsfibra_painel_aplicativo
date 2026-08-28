from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0080_systemconfig_billing_provedor_auto_block'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProviderGalleryImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=120, verbose_name='Nome do arquivo')),
                ('imagem', models.ImageField(upload_to=core.models.provider_gallery_upload_to, verbose_name='Imagem')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gallery_images_created', to=settings.AUTH_USER_MODEL, verbose_name='Criado por')),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_images', to='core.provedor', verbose_name='Provedor')),
            ],
            options={
                'verbose_name': 'Imagem da Galeria',
                'verbose_name_plural': 'Galeria de Imagens',
                'ordering': ['nome', '-created_at'],
            },
        ),
    ]
