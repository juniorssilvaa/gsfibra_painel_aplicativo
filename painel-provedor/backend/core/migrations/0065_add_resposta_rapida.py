from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0064_create_plano_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='RespostaRapida',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(
                    help_text='Ex: Fatura, Saudação, Horário — usado para filtrar com /',
                    max_length=100,
                    verbose_name='Título / Atalho'
                )),
                ('conteudo', models.TextField(
                    help_text='Texto completo que será enviado ao cliente',
                    verbose_name='Conteúdo da Resposta'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provedor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='respostas_rapidas',
                    to='core.provedor',
                    verbose_name='Provedor'
                )),
                ('criado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='respostas_rapidas_criadas',
                    to='core.user',
                    verbose_name='Criado por'
                )),
            ],
            options={
                'verbose_name': 'Resposta Rápida',
                'verbose_name_plural': 'Respostas Rápidas',
                'ordering': ['titulo'],
            },
        ),
    ]
