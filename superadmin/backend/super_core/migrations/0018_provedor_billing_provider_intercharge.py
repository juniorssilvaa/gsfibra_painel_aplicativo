# Generated manually for Inter dual-gateway billing

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0017_mensagemsistema_imagem_hotspots'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='billing_provider',
            field=models.CharField(
                choices=[('asaas', 'Asaas'), ('inter', 'Banco Inter')],
                default='asaas',
                help_text='Gateway usado para assinatura/cobrança deste provedor',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='InterBillingCharge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_solicitacao', models.CharField(db_index=True, max_length=80, unique=True)),
                ('seu_numero', models.CharField(blank=True, db_index=True, default='', max_length=15)),
                ('valor', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('data_vencimento', models.DateField(blank=True, null=True)),
                ('situacao', models.CharField(blank=True, default='', max_length=40)),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pendente'),
                        ('RECEIVED', 'Recebido'),
                        ('OVERDUE', 'Vencido'),
                        ('CANCELLED', 'Cancelado'),
                    ],
                    default='PENDING',
                    max_length=20,
                )),
                ('linha_digitavel', models.CharField(blank=True, default='', max_length=120)),
                ('pix_copia_cola', models.TextField(blank=True, default='')),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provedor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inter_charges',
                    to='super_core.provedor',
                )),
            ],
            options={
                'ordering': ['-data_vencimento', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='interbillingcharge',
            index=models.Index(fields=['provedor', 'status'], name='super_core__proveedo_inter_idx'),
        ),
        migrations.AddIndex(
            model_name='interbillingcharge',
            index=models.Index(fields=['data_vencimento', 'status'], name='super_core__data_ve_inter_idx'),
        ),
    ]
