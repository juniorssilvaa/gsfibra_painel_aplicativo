from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0063_add_bot_mode_to_provedor'),
    ]

    operations = [
        migrations.CreateModel(
            name='Plano',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=200, verbose_name='Nome do Plano')),
                ('descricao', models.TextField(blank=True, default='', verbose_name='Descrição')),
                ('velocidade_download', models.CharField(blank=True, default='', max_length=50, verbose_name='Velocidade Download')),
                ('velocidade_upload', models.CharField(blank=True, default='', max_length=50, verbose_name='Velocidade Upload')),
                ('preco', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Preço (R$)')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('ordem', models.IntegerField(default=0, verbose_name='Ordem de Exibição')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='planos_cadastrados', to='core.provedor', verbose_name='Provedor')),
            ],
            options={
                'verbose_name': 'Plano de Internet',
                'verbose_name_plural': 'Planos de Internet',
                'ordering': ['ordem', 'nome'],
            },
        ),
    ]
