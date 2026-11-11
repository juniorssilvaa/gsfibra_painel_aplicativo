import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0012_product_suggestion'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductSuggestionComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('author_user_id', models.IntegerField()),
                ('author_name', models.CharField(blank=True, default='', max_length=200)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'author_provedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='product_suggestion_comments',
                        to='super_core.provedor',
                    ),
                ),
                (
                    'suggestion',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='comments',
                        to='super_core.productsuggestion',
                    ),
                ),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
