from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0020_plano'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedor',
            name='payment_promise_until',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='provedor',
            name='payment_promise_note',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='provedor',
            name='payment_promise_created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='provedor',
            name='payment_promise_created_by',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
