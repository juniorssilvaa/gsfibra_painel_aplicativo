from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0015_systemupdate_release_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillingSendLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asaas_payment_id', models.CharField(blank=True, default='', max_length=60)),
                ('asaas_customer_id', models.CharField(blank=True, default='', max_length=60)),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('template_name', models.CharField(blank=True, default='', max_length=120)),
                ('due_offset', models.IntegerField(default=0)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('success', models.BooleanField(default=False)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provedor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='billing_send_logs',
                    to='super_core.provedor',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='billingsendlog',
            index=models.Index(fields=['-created_at'], name='super_core__created_a8b1c0_idx'),
        ),
        migrations.AddIndex(
            model_name='billingsendlog',
            index=models.Index(fields=['success', 'created_at'], name='super_core__success_7e2d4f_idx'),
        ),
    ]
