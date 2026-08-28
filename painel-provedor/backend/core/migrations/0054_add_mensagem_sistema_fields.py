# Generated manually to fix MensagemSistema model
from django.db import migrations, models, connection


def add_fields_if_not_exists(apps, schema_editor):
    """Adiciona campos apenas se não existirem"""
    with connection.cursor() as cursor:
        # Verificar quais campos já existem (compatível com SQLite e PostgreSQL)
        if connection.vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(core_mensagemsistema)")
            existing_columns = {row[1] for row in cursor.fetchall()}
        elif connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='core_mensagemsistema'
            """)
            existing_columns = {row[0] for row in cursor.fetchall()}
        else:
            # Para outros bancos, tentar adicionar e ignorar erro se já existir
            existing_columns = set()
        
        # Adicionar campos apenas se não existirem usando SQL direto
        if 'assunto' not in existing_columns:
            if connection.vendor == 'sqlite':
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN assunto TEXT DEFAULT ''
                """)
            else:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN assunto VARCHAR(200) DEFAULT ''
                """)
        
        if 'mensagem' not in existing_columns:
            cursor.execute("""
                ALTER TABLE core_mensagemsistema 
                ADD COLUMN mensagem TEXT DEFAULT ''
            """)
        
        if 'provedores' not in existing_columns:
            if connection.vendor == 'sqlite':
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN provedores TEXT DEFAULT '[]'
                """)
            else:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN provedores JSONB DEFAULT '[]'::jsonb
                """)
        
        if 'provedores_count' not in existing_columns:
            cursor.execute("""
                ALTER TABLE core_mensagemsistema 
                ADD COLUMN provedores_count INTEGER DEFAULT 0
            """)
        
        if 'visualizacoes' not in existing_columns:
            if connection.vendor == 'sqlite':
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN visualizacoes TEXT DEFAULT '{}'
                """)
            else:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN visualizacoes JSONB DEFAULT '{}'::jsonb
                """)
        
        if 'visualizacoes_count' not in existing_columns:
            cursor.execute("""
                ALTER TABLE core_mensagemsistema 
                ADD COLUMN visualizacoes_count INTEGER DEFAULT 0
            """)


def reverse_add_fields(apps, schema_editor):
    """Remove os campos adicionados (opcional, para rollback)"""
    pass  # Não precisamos reverter, pois os campos podem já existir


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0053_canal_api_id'),
    ]

    operations = [
        migrations.RunPython(add_fields_if_not_exists, reverse_add_fields),
        migrations.AlterField(
            model_name='mensagemsistema',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('notificacao', 'Notificação'),
                    ('aviso', 'Aviso'),
                    ('manutencao', 'Manutenção'),
                    ('info', 'Informação'),
                    ('warning', 'Aviso'),
                    ('error', 'Erro'),
                    ('success', 'Sucesso'),
                ],
                default='notificacao',
                max_length=50,
                verbose_name='Tipo'
            ),
        ),
    ]

