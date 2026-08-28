#!/usr/bin/env python
"""
Script para limpar completamente a tabela 'auditoria' do banco de dados PostgreSQL.
"""
import sys
import os

# Adicionar o caminho do backend ao sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("❌ Erro: psycopg2 não está instalado.")
    print("   Instale com: pip install psycopg2-binary")
    sys.exit(1)

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Configurações do banco PostgreSQL
POSTGRES_CONFIG = {
    'host': '168.194.174.234',
    'port': 5432,
    'database': 'niochat',
    'user': 'niochat_user',
    'password': 'E0sJT3wAYFuahovmHkxgy'
}


def check_table_exists(cursor, table_name):
    """Verifica se uma tabela existe no banco de dados"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        );
    """, [table_name])
    return cursor.fetchone()[0]


def get_table_count(cursor, table_name):
    """Retorna o número de registros na tabela"""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Erro ao contar registros na tabela {table_name}: {e}")
        return 0


def list_audit_tables(cursor):
    """Lista todas as tabelas relacionadas a auditoria"""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND (table_name LIKE '%audit%' OR table_name = 'auditoria')
        ORDER BY table_name;
    """)
    return [row[0] for row in cursor.fetchall()]


def clear_table(cursor, table_name):
    """Deleta todos os registros da tabela usando TRUNCATE"""
    try:
        # TRUNCATE é mais rápido que DELETE e reseta os contadores de auto-incremento
        cursor.execute(f'TRUNCATE TABLE "{table_name}" CASCADE;')
        logger.info(f"✓ Todos os registros da tabela '{table_name}' foram deletados com sucesso!")
        return True
    except Exception as e:
        logger.error(f"✗ Erro ao limpar tabela '{table_name}': {e}")
        # Tentar com DELETE se TRUNCATE falhar
        try:
            logger.info(f"   Tentando com DELETE...")
            cursor.execute(f'DELETE FROM "{table_name}";')
            logger.info(f"✓ Tabela '{table_name}' limpa com DELETE!")
            return True
        except Exception as e2:
            logger.error(f"✗ Erro ao deletar registros: {e2}")
            return False


def connect_to_postgres(config):
    """Conecta ao PostgreSQL"""
    try:
        conn = psycopg2.connect(**config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"✗ Erro ao conectar ao PostgreSQL: {e}")
        logger.error(f"   Verifique se o PostgreSQL está rodando e as credenciais estão corretas.")
        return None


def main():
    """Função principal"""
    import sys
    
    # Verificar se deve ser automático
    auto_mode = '--yes' in sys.argv or '-y' in sys.argv
    
    logger.info("=" * 70)
    logger.info("SCRIPT DE LIMPEZA DA TABELA 'auditoria' - PostgreSQL")
    logger.info("=" * 70)
    
    logger.info(f"\n📊 Configurações de Conexão:")
    logger.info(f"   Host: {POSTGRES_CONFIG['host']}")
    logger.info(f"   Port: {POSTGRES_CONFIG['port']}")
    logger.info(f"   Database: {POSTGRES_CONFIG['database']}")
    logger.info(f"   User: {POSTGRES_CONFIG['user']}")
    
    # Conectar ao PostgreSQL
    logger.info(f"\n🔌 Conectando ao PostgreSQL...")
    conn = connect_to_postgres(POSTGRES_CONFIG)
    
    if not conn:
        logger.error("✗ Falha na conexão. Abortando...")
        sys.exit(1)
    
    logger.info("✓ Conectado com sucesso!")
    
    try:
        cursor = conn.cursor()
        
        # Listar tabelas relacionadas a auditoria
        logger.info(f"\n🔍 Procurando tabelas relacionadas a auditoria...")
        audit_tables = list_audit_tables(cursor)
        
        if not audit_tables:
            logger.warning("⚠ Nenhuma tabela relacionada a auditoria encontrada!")
            return
        
        logger.info(f"   Tabelas encontradas: {', '.join(audit_tables)}")
        
        # Tentar primeiro 'auditoria', depois 'core_auditlog'
        target_table = None
        
        if check_table_exists(cursor, 'auditoria'):
            target_table = 'auditoria'
            logger.info(f"\n🎯 Tabela 'auditoria' encontrada!")
        elif 'core_auditlog' in audit_tables and check_table_exists(cursor, 'core_auditlog'):
            target_table = 'core_auditlog'
            logger.info(f"\n🎯 Tabela 'auditoria' não encontrada, mas 'core_auditlog' (modelo Django) existe!")
            logger.info(f"   Limpando 'core_auditlog' que representa a tabela de auditoria do sistema.")
        
        if not target_table:
            logger.warning("⚠ Nenhuma tabela de auditoria encontrada para limpar!")
            return
        
        # Contar registros antes de deletar
        count_before = get_table_count(cursor, target_table)
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
        if clear_table(cursor, target_table):
            count_after = get_table_count(cursor, target_table)
            logger.info(f"\n✅ Resultado:")
            logger.info(f"   Registros antes: {count_before}")
            logger.info(f"   Registros depois: {count_after}")
            
            if count_after == 0:
                logger.info(f"✓ Tabela '{target_table}' limpa com sucesso!")
            else:
                logger.warning(f"⚠ Ainda existem {count_after} registros na tabela!")
        else:
            logger.error("✗ Falha ao limpar a tabela!")
            
    except Exception as e:
        logger.error(f"✗ Erro durante a execução: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()
        logger.info("\n🔌 Conexão fechada.")
    
    logger.info("\n" + "=" * 70)
    logger.info("Script finalizado!")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()

