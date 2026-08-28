from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0091_provedor_auto_resolve_keywords'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensagemsistema',
            name='superadmin_message_id',
            field=models.IntegerField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name='ID mensagem Superadmin',
            ),
        ),
    ]
