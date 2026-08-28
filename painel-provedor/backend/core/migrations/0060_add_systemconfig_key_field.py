# Generated manually to fix missing 'key' field in SystemConfig
# CORRIGIDO: Verificar se a coluna já existe antes de adicionar
# A coluna 'key' já foi criada na migração 0042, então esta migração
# só adiciona se não existir (para ambientes onde a migração 0042 não foi aplicada)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0059_add_assignment_message'),
    ]

    operations = [
        # Usar RunSQL para adicionar condicionalmente apenas se não existir
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='core_systemconfig' AND column_name='key'
                    ) THEN
                        ALTER TABLE core_systemconfig 
                        ADD COLUMN key VARCHAR(255) UNIQUE DEFAULT '' NOT NULL;
                    END IF;
                END $$;
            """,
            reverse_sql="""
                -- Não remover a coluna na reversão para evitar problemas
            """
        ),
    ]

