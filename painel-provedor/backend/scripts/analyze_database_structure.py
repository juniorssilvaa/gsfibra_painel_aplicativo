"""
Script para analisar a estrutura do banco de dados PostgreSQL local
e gerar relatório de análise para migração dual database
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

from django.db import connection
from django.apps import apps
from conversations.models import Conversation, Message, Contact, Inbox, CSATFeedback, CSATRequest
from core.models import Provedor, AuditLog

def analyze_postgresql_structure():
    """Analisa a estrutura do banco PostgreSQL local"""
    print("=" * 80)
    print("ANÁLISE DO BANCO POSTGRESQL LOCAL")
    print("=" * 80)
    
    with connection.cursor() as cursor:
        # Listar todas as tabelas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📊 TOTAL DE TABELAS: {len(tables)}")
        print("\n📋 LISTA DE TABELAS:")
        for table in tables:
            print(f"  - {table}")
        
        # Analisar tabelas relacionadas a conversas
        conversation_tables = [
            'conversations_conversation',
            'conversations_message',
            'conversations_contact',
            'conversations_inbox',
            'conversations_csatfeedback',
            'conversations_csatrequest',
            'core_auditlog'
        ]
        
        print("\n" + "=" * 80)
        print("ESTRUTURA DAS TABELAS DE CONVERSAS")
        print("=" * 80)
        
        for table_name in conversation_tables:
            if table_name not in tables:
                print(f"\n⚠️  Tabela {table_name} não encontrada")
                continue
                
            print(f"\n📌 TABELA: {table_name}")
            print("-" * 80)
            
            # Obter colunas
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
            
            columns = cursor.fetchall()
            print(f"  Colunas ({len(columns)}):")
            for col in columns:
                col_name, data_type, max_length, nullable, default = col
                length_str = f"({max_length})" if max_length else ""
                nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                print(f"    - {col_name}: {data_type}{length_str} {nullable_str}{default_str}")
            
            # Obter constraints (foreign keys, primary keys, etc)
            cursor.execute("""
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_name = %s
                ORDER BY tc.constraint_type, tc.constraint_name;
            """, [table_name])
            
            constraints = cursor.fetchall()
            if constraints:
                print(f"\n  Constraints ({len(constraints)}):")
                for constraint in constraints:
                    const_name, const_type, col_name, fk_table, fk_col = constraint
                    if const_type == 'FOREIGN KEY':
                        print(f"    - {const_name}: {col_name} -> {fk_table}.{fk_col}")
                    elif const_type == 'PRIMARY KEY':
                        print(f"    - {const_name}: PRIMARY KEY ({col_name})")
                    else:
                        print(f"    - {const_name}: {const_type}")
            
            # Obter índices
            cursor.execute("""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE tablename = %s
                ORDER BY indexname;
            """, [table_name])
            
            indexes = cursor.fetchall()
            if indexes:
                print(f"\n  Índices ({len(indexes)}):")
                for idx in indexes:
                    idx_name, idx_def = idx
                    print(f"    - {idx_name}: {idx_def[:100]}...")
        
        # Estatísticas das tabelas
        print("\n" + "=" * 80)
        print("ESTATÍSTICAS DAS TABELAS")
        print("=" * 80)
        
        for table_name in conversation_tables:
            if table_name not in tables:
                continue
                
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                print(f"  {table_name}: {count:,} registros")
            except Exception as e:
                print(f"  {table_name}: Erro ao contar - {e}")

def analyze_django_models():
    """Analisa os modelos Django relacionados a conversas"""
    print("\n" + "=" * 80)
    print("ANÁLISE DOS MODELOS DJANGO")
    print("=" * 80)
    
    models_to_analyze = [
        Conversation,
        Message,
        Contact,
        Inbox,
        CSATFeedback,
        CSATRequest,
        AuditLog
    ]
    
    for model in models_to_analyze:
        print(f"\n📌 MODELO: {model.__name__}")
        print("-" * 80)
        print(f"  Tabela: {model._meta.db_table}")
        print(f"  App: {model._meta.app_label}")
        
        # Campos
        fields = model._meta.get_fields()
        print(f"\n  Campos ({len(fields)}):")
        for field in fields:
            field_type = type(field).__name__
            if hasattr(field, 'related_model'):
                related = field.related_model.__name__ if field.related_model else None
                print(f"    - {field.name}: {field_type} -> {related}")
            else:
                print(f"    - {field.name}: {field_type}")

if __name__ == '__main__':
    try:
        analyze_postgresql_structure()
        analyze_django_models()
        print("\n" + "=" * 80)
        print("✅ ANÁLISE CONCLUÍDA")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()

