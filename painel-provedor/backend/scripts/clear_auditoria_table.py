#!/usr/bin/env python
"""
Script para limpar completamente a tabela 'auditoria' do banco de dados.
Suporta PostgreSQL e SQLite.
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

from django.db import connection
from django.conf import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_table_exists(table_name):
    """Verifica se uma tabela existe no banco de dados"""
    with connection.cursor() as cursor:
        db_engine = settings.DATABASES['default']['ENGINE']
        
        if 'postgresql' in db_engine:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, [table_name])
            return cursor.fetchone()[0]
        elif 'sqlite' in db_engine:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?;
            """, [table_name])
            return cursor.fetchone() is not None
        else:
            logger.error(f"Banco de dados não suportado: {db_engine}")
            return False


def get_table_count(table_name):
    """Retorna o número de registros na tabela"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Erro ao contar registros na tabela {table_name}: {e}")
        return 0


def clear_table(table_name):
    """Deleta todos os registros da tabela"""
    try:
        db_engine = settings.DATABASES['default']['ENGINE']
        
        with connection.cursor() as cursor:
            if 'postgresql' in db_engine:
                # PostgreSQL: usar TRUNCATE para melhor performance
                cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE;")
            elif 'sqlite' in db_engine:
                # SQLite: usar DELETE (TRUNCATE não é suportado)
                cursor.execute(f"DELETE FROM {table_name};")
                # Resetar o auto-increment
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}';")
            else:
                raise ValueError(f"Banco de dados não suportado: {db_engine}")
            
            logger.info(f"✓ Todos os registros da tabela '{table_name}' foram deletados com sucesso!")
            return True
    except Exception as e:
        logger.error(f"✗ Erro ao limpar tabela '{table_name}': {e}")
        return False


def list_audit_tables():
    """Lista todas as tabelas relacionadas a auditoria"""
    tables = []
    with connection.cursor() as cursor:
        db_engine = settings.DATABASES['default']['ENGINE']
        
        if 'postgresql' in db_engine:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND (table_name LIKE '%audit%' OR table_name = 'auditoria')
                ORDER BY table_name;
            """)
        elif 'sqlite' in db_engine:
            cursor.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' 
                AND (name LIKE '%audit%' OR name = 'auditoria')
                ORDER BY name;
            """)
        
        tables = [row[0] for row in cursor.fetchall()]
    return tables


def main():
    """Função principal"""
    import sys
    
    # Verificar se deve ser automático (sem confirmação)
    auto_mode = '--yes' in sys.argv or '-y' in sys.argv
    
    logger.info("=" * 60)
    logger.info("SCRIPT DE LIMPEZA DA TABELA 'auditoria'")
    logger.info("=" * 60)
    
    # Verificar qual banco está sendo usado
    db_engine = settings.DATABASES['default']['ENGINE']
    db_name = settings.DATABASES['default'].get('NAME', 'N/A')
    
    logger.info(f"\n📊 Informações do Banco de Dados:")
    logger.info(f"   Engine: {db_engine}")
    logger.info(f"   Database: {db_name}")
    
    # Listar tabelas relacionadas a auditoria
    logger.info(f"\n🔍 Procurando tabelas relacionadas a auditoria...")
    audit_tables = list_audit_tables()
    
    if not audit_tables:
        logger.warning("⚠ Nenhuma tabela relacionada a auditoria encontrada!")
        return
    
    logger.info(f"   Tabelas encontradas: {', '.join(audit_tables)}")
    
    # Tentar primeiro 'auditoria', depois 'core_auditlog'
    target_table = None
    
    if check_table_exists('auditoria'):
        target_table = 'auditoria'
        logger.info(f"\n🎯 Tabela 'auditoria' encontrada!")
    elif 'core_auditlog' in audit_tables and check_table_exists('core_auditlog'):
        target_table = 'core_auditlog'
        logger.info(f"\n🎯 Tabela 'auditoria' não encontrada, mas 'core_auditlog' (modelo Django) existe!")
        logger.info(f"   Limpando 'core_auditlog' que representa a tabela de auditoria do sistema.")
    
    if not target_table:
        logger.warning("⚠ Nenhuma tabela de auditoria encontrada para limpar!")
        return
    
    # Contar registros antes de deletar
    count_before = get_table_count(target_table)
    logger.info(f"   Registros encontrados: {count_before}")
    
    if count_before == 0:
        logger.info(f"✓ A tabela '{target_table}' já está vazia!")
        return
    
    # Confirmar ação (a menos que esteja em modo automático)
    if not auto_mode:
        logger.warning(f"\n⚠ ATENÇÃO: Você está prestes a deletar TODOS os {count_before} registros da tabela '{target_table}'!")
        try:
            response = input("❓ Tem certeza que deseja continuar? (digite 'SIM' para confirmar): ").strip()
            if response != 'SIM':
                logger.info("Operação cancelada pelo usuário.")
                return
        except (EOFError, KeyboardInterrupt):
            logger.info("\nOperação cancelada.")
            return
    else:
        logger.info(f"\n🗑️  Modo automático ativado. Deletando {count_before} registros...")
    
    # Limpar tabela
    logger.info(f"\n🗑️  Deletando registros...")
    if clear_table(target_table):
        count_after = get_table_count(target_table)
        logger.info(f"\n✅ Resultado:")
        logger.info(f"   Registros antes: {count_before}")
        logger.info(f"   Registros depois: {count_after}")
        
        if count_after == 0:
            logger.info(f"✓ Tabela '{target_table}' limpa com sucesso!")
        else:
            logger.warning(f"⚠ Ainda existem {count_after} registros na tabela!")
    else:
        logger.error("✗ Falha ao limpar a tabela!")
    
    logger.info("\n" + "=" * 60)
    logger.info("Script finalizado!")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()

