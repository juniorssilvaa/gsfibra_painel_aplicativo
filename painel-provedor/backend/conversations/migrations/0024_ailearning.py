from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0107_agentpushdevice'),
        ('conversations', '0023_ailearninganalysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='ailearninganalysis',
            name='suggestion_status',
            field=models.CharField(default='pending', max_length=10),
        ),
        migrations.AddField(
            model_name='ailearninganalysis',
            name='suggestion_attempted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='AILearning',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('situation', models.CharField(max_length=300)),
                ('answer', models.TextField()),
                ('keywords', models.CharField(blank=True, default='', max_length=500)),
                ('status', models.CharField(choices=[('suggested', 'Sugerido'), ('approved', 'Aprovado'), ('disabled', 'Desativado'), ('rejected', 'Rejeitado')], default='suggested', max_length=10)),
                ('source', models.CharField(choices=[('llm', 'Sugerido pela IA'), ('manual', 'Cadastrado pelo provedor')], default='llm', max_length=10)),
                ('source_conversation_ids', models.JSONField(blank=True, default=list)),
                ('times_used', models.PositiveIntegerField(default=0)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_learnings', to='core.provedor')),
            ],
            options={
                'db_table': 'ai_learnings',
                'indexes': [models.Index(fields=['provedor', 'status'], name='ai_learning_prov_status_idx')],
            },
        ),
    ]
