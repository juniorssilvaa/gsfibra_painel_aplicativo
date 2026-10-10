import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0019_provedorhealth'),
    ]

    operations = [
        migrations.CreateModel(
            name='Plano',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True)),
                ('descricao', models.TextField(blank=True, default='')),
                ('valor', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('ciclo', models.CharField(default='MONTHLY', max_length=20)),
                ('max_canais', models.PositiveIntegerField(default=0, help_text='0 = ilimitado. O canal do App Mobile não conta.')),
                ('max_usuarios', models.PositiveIntegerField(default=0, help_text='0 = ilimitado.')),
                ('ativo', models.BooleanField(default=True)),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plano',
                'verbose_name_plural': 'Planos',
                'ordering': ['ordem', 'valor', 'nome'],
            },
        ),
        migrations.AddField(
            model_name='provedor',
            name='plano',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='provedores', to='super_core.plano'),
        ),
        migrations.AddField(
            model_name='provedor',
            name='canais_extras',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='provedor',
            name='usuarios_extras',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
