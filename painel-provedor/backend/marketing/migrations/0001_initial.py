import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0108_backfill_user_last_login'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketingThread',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Nova conversa', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marketing_threads', to='core.provedor')),
            ],
            options={
                'db_table': 'marketing_threads',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='MarketingMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'Usuário'), ('assistant', 'IA')], max_length=10)),
                ('content', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('done', 'Concluída'), ('pending', 'Processando'), ('error', 'Erro')], default='done', max_length=10)),
                ('asset_ids', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('thread', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='marketing.marketingthread')),
            ],
            options={
                'db_table': 'marketing_messages',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='MarketingAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('creative', 'Arte gerada'), ('reference', 'Referência')], max_length=10)),
                ('image', models.BinaryField()),
                ('base_image', models.BinaryField(blank=True, null=True)),
                ('mime_type', models.CharField(default='image/jpeg', max_length=50)),
                ('width', models.PositiveIntegerField(default=0)),
                ('height', models.PositiveIntegerField(default=0)),
                ('formato', models.CharField(blank=True, default='', max_length=20)),
                ('modo_texto', models.CharField(blank=True, default='', max_length=10)),
                ('prompt', models.TextField(blank=True, default='')),
                ('textos', models.JSONField(blank=True, default=dict)),
                ('original_name', models.CharField(blank=True, default='', max_length=200)),
                ('engine', models.CharField(blank=True, default='', max_length=60)),
                ('approved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='versions', to='marketing.marketingasset')),
                ('plano', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='core.plano')),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marketing_assets', to='core.provedor')),
                ('thread', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assets', to='marketing.marketingthread')),
            ],
            options={
                'db_table': 'marketing_assets',
                'indexes': [models.Index(fields=['provedor', 'kind', 'created_at'], name='mkt_asset_prov_kind_idx')],
            },
        ),
    ]
