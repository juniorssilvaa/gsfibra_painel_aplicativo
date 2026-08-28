from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0061_canal_ia_ativa'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatbotFlow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Nome do Fluxo')),
                ('nodes', models.JSONField(blank=True, default=list, verbose_name='Nós do Fluxo')),
                ('edges', models.JSONField(blank=True, default=list, verbose_name='Conexões do Fluxo')),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chatbot_flows', to='core.provedor', verbose_name='Provedor')),
            ],
            options={
                'verbose_name': 'Fluxo de Chatbot',
                'verbose_name_plural': 'Fluxos de Chatbot',
                'ordering': ['-updated_at'],
            },
        ),
    ]
