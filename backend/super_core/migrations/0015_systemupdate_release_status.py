from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('super_core', '0014_user_phone_preferred_language'),
    ]

    operations = [
        migrations.AlterField(
            model_name='systemupdate',
            name='version',
            field=models.CharField(max_length=50),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Na fila'),
                    ('running', 'Em andamento'),
                    ('done', 'Concluído'),
                    ('failed', 'Falhou'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='source',
            field=models.CharField(default='ui', max_length=20),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='results',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='promote_ok',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='promote_log',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='systemupdate',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='systemupdate',
            options={'ordering': ['-release_date']},
        ),
    ]
