from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mobile_app', '0007_mobileappprofile_app_default_team_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='mobileappprofile',
            name='erp_type',
            field=models.CharField(
                choices=[('sgp', 'SGP'), ('receitanet', 'ReceitaNet')],
                default='sgp',
                help_text='ERP usado pelo app mobile (SGP ou ReceitaNet).',
                max_length=20,
            ),
        ),
    ]
