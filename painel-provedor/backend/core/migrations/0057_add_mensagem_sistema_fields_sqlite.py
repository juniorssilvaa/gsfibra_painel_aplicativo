# Generated manually to add fields to MensagemSistema - compatível com SQLite e PostgreSQL
from django.db import migrations, connection


def add_fields_cross_db(apps, schema_editor):
    """Adiciona campos apenas se não existirem - compatível com SQLite e PostgreSQL"""
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
        
        # Adicionar campos apenas se não existirem
        if 'assunto' not in existing_columns:
            try:
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
            except Exception as e:
                print(f"Erro ao adicionar campo assunto: {e}")
        
        if 'mensagem' not in existing_columns:
            try:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN mensagem TEXT DEFAULT ''
                """)
            except Exception as e:
                print(f"Erro ao adicionar campo mensagem: {e}")
        
        if 'provedores' not in existing_columns:
            try:
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
            except Exception as e:
                print(f"Erro ao adicionar campo provedores: {e}")
        
        if 'provedores_count' not in existing_columns:
            try:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN provedores_count INTEGER DEFAULT 0
                """)
            except Exception as e:
                print(f"Erro ao adicionar campo provedores_count: {e}")
        
        if 'visualizacoes' not in existing_columns:
            try:
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
            except Exception as e:
                print(f"Erro ao adicionar campo visualizacoes: {e}")
        
        if 'visualizacoes_count' not in existing_columns:
            try:
                cursor.execute("""
                    ALTER TABLE core_mensagemsistema 
                    ADD COLUMN visualizacoes_count INTEGER DEFAULT 0
                """)
            except Exception as e:
                print(f"Erro ao adicionar campo visualizacoes_count: {e}")


def reverse_add_fields(apps, schema_editor):
    """Não faz nada - não vamos remover campos"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0056_remove_systemconfig_openai_api_key_and_more'),
    ]

    operations = [
        migrations.RunPython(add_fields_cross_db, reverse_add_fields),
    ]

