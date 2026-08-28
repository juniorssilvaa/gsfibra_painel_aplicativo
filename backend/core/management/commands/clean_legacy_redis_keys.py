"""
Comando para limpar chaves legadas do Redis.

Formato atual (um único dado por provedor+conversa):
- ai:memory:{provedor_id}:{channel}:{conversation_id}:{phone}  (state + context juntos)

Chaves legadas (removidas por este comando):
- ai:state:* e ai:context:* (formato antigo: dois dados por conversa)
- ai:memory:* que não seguem o padrão com telefone
- conversation:* (CSAT legado)
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import redis
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Limpa chaves legadas do Redis que causam vazamento de dados entre provedores'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas mostrar o que será removido, sem realmente apagar',
        )
        parser.add_argument(
            '--pattern',
            type=str,
            default='all',
            help='Padrão: all, legacy (ai:state/ai:context), conversation',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        pattern = options.get('pattern', 'all')
        
        self.stdout.write(self.style.WARNING('🔍 LIMPANDO CHAVES LEGADAS DO REDIS - VAZAMENTO DE DADOS'))
        self.stdout.write('=' * 70)
        
        try:
            # Conectar ao Redis
            redis_host = getattr(settings, 'REDIS_HOST', 'localhost')
            redis_port = getattr(settings, 'REDIS_PORT', 6379)
            redis_password = getattr(settings, 'REDIS_PASSWORD', None)
            redis_db = getattr(settings, 'REDIS_DB', 0)
            redis_username = getattr(settings, 'REDIS_USERNAME', None)
            
            if redis_username:
                redis_url = f'redis://{redis_username}:{redis_password}@{redis_host}:{redis_port}/{redis_db}'
            else:
                redis_url = f'redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}'
            
            redis_conn = redis.from_url(redis_url, decode_responses=True)
            
            # Contador de chaves removidas
            total_removed = 0
            
            # 1. Limpar chaves legadas ai:state:* e ai:context:* (formato antigo, substituído por ai:memory:*)
            if pattern in ['all', 'legacy']:
                self.stdout.write('\n📊 Procurando chaves legadas "ai:state:*" e "ai:context:*"...')
                removed = self._clean_pattern(redis_conn, 'ai:state:*', dry_run)
                total_removed += removed
                removed = self._clean_pattern(redis_conn, 'ai:context:*', dry_run)
                total_removed += removed
            
            # 2. Limpar chaves legadas "conversation:*" (CSAT)
            if pattern in ['all', 'conversation']:
                self.stdout.write('\n📊 Procurando chaves "conversation:*"...')
                removed = self._clean_pattern(redis_conn, 'conversation:*', dry_run)
                total_removed += removed
            
            # 3. Verificar chaves ai:memory:* corrompidas (sem telefone ou formato antigo)
            self.stdout.write('\n📊 Procurando chaves "ai:memory:*" corrompidas/legadas...')
            removed = self._clean_corrupted_keys(redis_conn, dry_run)
            total_removed += removed
            
            self.stdout.write('=' * 70)
            if dry_run:
                self.stdout.write(self.style.WARNING(f'📋 MODO DRY RUN: {total_removed} chaves seriam removidas'))
                self.stdout.write(self.style.WARNING('Execute novamente sem --dry-run para realmente limpar'))
            else:
                self.stdout.write(self.style.SUCCESS(f'✅ Limpeza concluída: {total_removed} chaves legadas removidas'))
            
            # 4. Mostrar estatísticas atuais
            self._show_stats(redis_conn)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Erro ao executar limpeza: {str(e)}'))
            logger.exception(f"Erro ao limpar chaves legadas do Redis: {e}")

    def _clean_pattern(self, redis_conn, pattern, dry_run):
        """Limpa todas as chaves que correspondem ao padrão"""
        keys = redis_conn.keys(pattern)
        count = len(keys)
        
        if count == 0:
            self.stdout.write(f'   ✓ Nenhuma chave encontrada com padrão "{pattern}"')
            return 0
        
        self.stdout.write(f'   📋 {count} chaves encontradas com padrão "{pattern}"')
        
        if dry_run:
            self.stdout.write(f'   ⚠️  DRY RUN: {count} chaves seriam removidas')
        else:
            # Mostrar algumas chaves de exemplo
            for key in keys[:5]:
                self.stdout.write(f'      - {key}')
            if len(keys) > 5:
                self.stdout.write(f'      ... e mais {len(keys) - 5} chaves')
            
            redis_conn.delete(*keys)
            self.stdout.write(f'   ✅ {count} chaves removidas')
        
        return count

    def _clean_corrupted_keys(self, redis_conn, dry_run):
        """Limpa chaves ai:memory:* que não seguem o padrão (provedor:channel:conv:phone = 4 partes após ai:memory)"""
        # Padrão correto: ai:memory:{provedor_id}:{channel}:{conversation_id}:{phone} -> 5 partes
        memory_keys = redis_conn.keys('ai:memory:*')
        count = 0
        
        self.stdout.write(f'   📋 {len(memory_keys)} chaves ai:memory:* encontradas')
        
        for key in memory_keys:
            parts = key.split(':')
            # ai:memory:provedor:channel:conv:phone = 6 partes no total
            if len(parts) != 6:
                is_corrupted = True  # formato antigo ou inválido
            else:
                is_corrupted = parts[-1] in ('unknown', 'Unknown', '')
            
            if is_corrupted:
                count += 1
                if dry_run:
                    if count <= 5:
                        self.stdout.write(f'      ⚠️  {key} (corrompida/legada)')
                    elif count == 6:
                        self.stdout.write(f'   ⚠️  {count} chaves corrompidas/legadas seriam removidas')
                else:
                    redis_conn.delete(key)
                    if count <= 5:
                        self.stdout.write(f'      ✅ {key} (removida)')
        
        if dry_run and count:
            self.stdout.write(f'   ⚠️  DRY RUN: {count} chaves corrompidas seriam removidas')
        elif not dry_run and count:
            self.stdout.write(f'   ✅ {count} chaves corrompidas removidas')
        
        return count

    def _show_stats(self, redis_conn):
        """Mostra estatísticas atuais do Redis"""
        self.stdout.write('\n📊 Estatísticas atuais do Redis:')
        self.stdout.write('-' * 70)
        
        ai_memory_keys = redis_conn.keys('ai:memory:*')
        ai_state_keys = redis_conn.keys('ai:state:*')
        ai_context_keys = redis_conn.keys('ai:context:*')
        ai_lock_keys = redis_conn.keys('ai:lock:*')
        conversation_keys = redis_conn.keys('conversation:*')
        
        corrupted_count = sum(
            1 for key in ai_memory_keys
            if (lambda p: len(p) != 6 or p[-1] in ('unknown', 'Unknown', ''))(key.split(':'))
        )
        
        self.stdout.write(f'   ai:memory:* (atual) : {len(ai_memory_keys)} chaves (state+context unificado)')
        self.stdout.write(f'   ai:state:* (legado) : {len(ai_state_keys)} chaves')
        self.stdout.write(f'   ai:context:* (legado): {len(ai_context_keys)} chaves')
        self.stdout.write(f'   ai:lock:*           : {len(ai_lock_keys)} chaves')
        self.stdout.write(f'   conversation:*      : {len(conversation_keys)} chaves (CSAT)')
        self.stdout.write(f'   🔴 ai:memory corrompidas: {corrupted_count} chaves')
        
        if ai_memory_keys:
            ok = [k for k in ai_memory_keys if len(k.split(':')) == 6 and k.split(':')[-1] not in ('unknown', 'Unknown', '')]
            if ok:
                self.stdout.write('\n   ✅ Exemplo de chave correta:')
                self.stdout.write(f'      {ok[0]}')
