from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("super_core", "0007_add_waba_id_to_canal"),
    ]

    operations = [
        migrations.AddField(
            model_name="provedor",
            name="panel_bootstrap_password_ciphertext",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Senha de primeiro login no painel do provedor (encriptada). "
                "Preenchida ao criar/alterar utilizador do superadmin ligado a este provedor.",
            ),
        ),
    ]
