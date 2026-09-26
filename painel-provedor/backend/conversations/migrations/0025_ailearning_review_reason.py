from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0024_ailearning'),
    ]

    operations = [
        migrations.AddField(
            model_name='ailearning',
            name='review_reason',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
