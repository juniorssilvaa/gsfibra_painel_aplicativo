# Generated manually for SGP dispatch webhook token
# Idempotente: coluna pode já existir em produção (deploy parcial / SQL manual).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0083_providergalleryimage_arquivo_db_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='provedor',
                    name='sgp_webhook_token',
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        help_text='Token único para o SGP autenticar webhooks de disparo de cobrança neste provedor.',
                        max_length=128,
                        null=True,
                        unique=True,
                        verbose_name='Token webhook SGP (disparos)',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'core_provedor'
                                  AND column_name = 'sgp_webhook_token'
                            ) THEN
                                ALTER TABLE core_provedor
                                ADD COLUMN sgp_webhook_token VARCHAR(128) NULL;
                            END IF;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint c
                                JOIN pg_class t ON c.conrelid = t.oid
                                WHERE t.relname = 'core_provedor'
                                  AND c.conname = 'core_provedor_sgp_webhook_token_key'
                            ) THEN
                                ALTER TABLE core_provedor
                                ADD CONSTRAINT core_provedor_sgp_webhook_token_key
                                UNIQUE (sgp_webhook_token);
                            END IF;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX IF NOT EXISTS core_provedor_sgp_webhook_token_idx
                        ON core_provedor (sgp_webhook_token);
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
