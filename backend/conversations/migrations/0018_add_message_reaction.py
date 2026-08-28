# Generated migration for MessageReaction model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0017_add_closing_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='MessageReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emoji', models.CharField(max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_from_customer', models.BooleanField(default=True)),
                ('external_id', models.CharField(blank=True, max_length=255, null=True)),
                ('additional_attributes', models.JSONField(blank=True, default=dict)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='conversations.message')),
            ],
            options={
                'db_table': 'message_reactions',
            },
        ),
        migrations.AddIndex(
            model_name='messagereaction',
            index=models.Index(fields=['message', 'emoji'], name='message_rea_message_emoji_idx'),
        ),
    ]



