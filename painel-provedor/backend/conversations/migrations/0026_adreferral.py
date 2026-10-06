import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0025_ailearning_review_reason'),
        ('core', '0108_backfill_user_last_login'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdReferral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_external_id', models.CharField(max_length=255, unique=True)),
                ('source_type', models.CharField(blank=True, default='', max_length=20)),
                ('source_id', models.CharField(blank=True, default='', max_length=64)),
                ('source_url', models.TextField(blank=True, default='')),
                ('headline', models.CharField(blank=True, default='', max_length=500)),
                ('body', models.TextField(blank=True, default='')),
                ('media_type', models.CharField(blank=True, default='', max_length=20)),
                ('thumbnail_url', models.TextField(blank=True, default='')),
                ('ctwa_clid', models.CharField(blank=True, default='', max_length=512)),
                ('new_contact', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ad_referrals', to='conversations.contact')),
                ('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ad_referrals', to='conversations.conversation')),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ad_referrals', to='core.provedor')),
            ],
            options={
                'db_table': 'ad_referrals',
                'indexes': [
                    models.Index(fields=['provedor', 'created_at'], name='ad_ref_prov_created_idx'),
                    models.Index(fields=['provedor', 'source_id'], name='ad_ref_prov_source_idx'),
                ],
            },
        ),
    ]
