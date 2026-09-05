from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0013_product_suggestion_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='preferred_language',
            field=models.CharField(blank=True, default='pt-BR', max_length=20),
        ),
    ]
