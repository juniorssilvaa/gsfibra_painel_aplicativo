from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0006_mobilesupportmedia'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='app_default_team_id',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text='ID da equipe no painel de atendimento que recebe chats do app (aba Espera).',
            ),
        ),
    ]
