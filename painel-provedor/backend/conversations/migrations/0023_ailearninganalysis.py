from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0107_agentpushdevice'),
        ('conversations', '0022_message_conversation_perf_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='AILearningAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('conversation_id', models.BigIntegerField()),
                ('contact_id', models.BigIntegerField(blank=True, null=True)),
                ('channel_type', models.CharField(blank=True, default='', max_length=30)),
                ('conversation_started_at', models.DateTimeField(blank=True, null=True)),
                ('conversation_closed_at', models.DateTimeField(blank=True, null=True)),
                ('customer_messages', models.PositiveIntegerField(default=0)),
                ('ai_messages', models.PositiveIntegerField(default=0)),
                ('chatbot_messages', models.PositiveIntegerField(default=0)),
                ('agent_messages', models.PositiveIntegerField(default=0)),
                ('outcome', models.CharField(choices=[('ai_resolved', 'Resolvido pela IA'), ('ai_transferred', 'IA transferiu para humano'), ('agent_took_over', 'Atendente assumiu da IA'), ('chatbot', 'Chatbot'), ('human_only', 'Somente atendente'), ('no_reply', 'Sem resposta')], max_length=20)),
                ('transfer_reason', models.TextField(blank=True, default='')),
                ('learning_candidate', models.BooleanField(default=False)),
                ('analyzed_at', models.DateTimeField(auto_now=True)),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_learning_analyses', to='core.provedor')),
            ],
            options={
                'db_table': 'ai_learning_analyses',
                'indexes': [models.Index(fields=['provedor', 'conversation_closed_at'], name='ai_learning_prov_closed_idx')],
                'constraints': [models.UniqueConstraint(fields=('provedor', 'conversation_id'), name='ai_learning_unique_conversation')],
            },
        ),
    ]
