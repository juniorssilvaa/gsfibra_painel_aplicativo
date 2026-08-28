"""
Serviço para gerenciar o encerramento de conversas com janela de tolerância.
"""
import logging
from django.utils import timezone
from datetime import timedelta
from .models import Conversation

logger = logging.getLogger(__name__)


def stamp_automation_closure_trace(conversation, source: str = 'unknown') -> None:
    """
    Marca conversa como encerramento iniciado por IA/chatbot antes do estado 'closing',
    para dashboards e migração identificarem resolução automática.
    """
    try:
        attrs = dict(conversation.additional_attributes or {})
        attrs['resolucao_automacao'] = True
        attrs['closure_source'] = source
        conversation.additional_attributes = attrs
        conversation.save(update_fields=['additional_attributes'])
    except Exception as e:
        logger.warning("stamp_automation_closure_trace falhou (conv=%s): %s", getattr(conversation, "id", None), e)


class ClosingService:
    """
    Serviço para gerenciar o estado intermediário 'closing' e encerramento definitivo.
    """
    
    # Janela de tolerância padrão: 2 minutos
    DEFAULT_TOLERANCE_MINUTES = 2
    
    @classmethod
    def request_closing(cls, conversation: Conversation, tolerance_minutes: int = None) -> bool:
        """
        Solicita o encerramento de uma conversa, colocando-a em estado 'closing'.
        
        Args:
            conversation: Conversa a ser encerrada
            tolerance_minutes: Período de tolerância em minutos (padrão: 2)
            
        Returns:
            bool: True se o encerramento foi solicitado com sucesso
        """
        if conversation.status == 'closed':
            logger.warning(f"Conversa {conversation.id} já está fechada")
            return False
        
        try:
            conversation.status = 'closing'
            conversation.closing_requested_at = timezone.now()
            conversation.assignee = None  # Garantir que não fique "atribuída" após IA finalizar
            conversation.save(update_fields=['status', 'closing_requested_at', 'assignee'])
            
            tolerance = tolerance_minutes or cls.DEFAULT_TOLERANCE_MINUTES
            logger.info(
                f"Encerramento solicitado para conversa {conversation.id}. "
                f"Janela de tolerância: {tolerance} minutos"
            )
            return True
        except Exception as e:
            logger.error(f"Erro ao solicitar encerramento da conversa {conversation.id}: {e}", exc_info=True)
            return False
    
    @classmethod
    def finalize_closing(cls, conversation: Conversation) -> bool:
        """
        Finaliza o encerramento de uma conversa, mudando de 'closing' para 'closed'.
        Deve ser chamado apenas após o período de tolerância ter expirado.
        
        Args:
            conversation: Conversa em estado 'closing' a ser finalizada
            
        Returns:
            bool: True se o encerramento foi finalizado com sucesso
        """
        if conversation.status != 'closing':
            logger.warning(f"Conversa {conversation.id} não está em estado 'closing' (status: {conversation.status})")
            return False
        
        try:
            conversation.status = 'closed'
            conversation.assignee = None  # Garantir que não fique "atribuída" ao reabrir na próxima mensagem
            # Manter closing_requested_at para histórico
            conversation.save(update_fields=['status', 'assignee'])
            logger.info(f"Encerramento finalizado para conversa {conversation.id}")
            
            # Criar CSAT agora que a conversa está definitivamente fechada
            try:
                from conversations.csat_service import CSATService
                csat_request = CSATService.schedule_csat_request(
                    conversation_id=conversation.id,
                    ended_by_user_id=None  # Encerramento automático
                )
                if csat_request:
                    logger.info(f"✓ CSAT criado para conversa {conversation.id} após finalização (id={csat_request.id})")
                else:
                    logger.warning(f"✗ Falha ao criar CSAT para conversa {conversation.id} após finalização")
            except Exception as csat_error:
                logger.error(f"Erro ao criar CSAT para conversa {conversation.id} após finalização: {str(csat_error)}", exc_info=True)
            
            # Verificar se a conversa já foi migrada (pode ter sido migrada imediatamente quando encerrada)
            try:
                from core.chat_migration_service import chat_migration_service
                provedor_id = conversation.inbox.provedor_id if conversation.inbox else None
                if provedor_id:
                    already_migrated = chat_migration_service.verificar_conversa_no_supabase(conversation.id, provedor_id)
                    if already_migrated:
                        logger.info(f"✓ Conversa {conversation.id} já foi migrada para Supabase anteriormente (pulando migração)")
                    else:
                        # Migrar para Supabase agora que está definitivamente fechada
                        migration_result = chat_migration_service.encerrar_e_migrar(
                            conversation_id=conversation.id,
                            metadata={
                                'encerrado_por': 'ai',
                                'finalizado_por': 'job_assincrono'
                            }
                        )
                        if migration_result.get('success'):
                            logger.info(f"✓ Conversa {conversation.id} migrada para Supabase após finalização")
                        else:
                            logger.warning(f"✗ Falha ao migrar conversa {conversation.id} para Supabase: {migration_result.get('errors', [])}")
                else:
                    logger.warning(f"✗ Provedor não encontrado para conversa {conversation.id}, não é possível migrar")
            except Exception as migration_error:
                logger.error(f"Erro ao verificar/migrar conversa {conversation.id} para Supabase: {str(migration_error)}", exc_info=True)
            
            # Verificar se o Redis já foi limpo (pode ter sido limpo imediatamente quando encerrada)
            # Tentar limpar novamente apenas se necessário (não causa erro se já foi limpo)
            try:
                from core.redis_memory_service import redis_memory_service
                provedor_id = conversation.inbox.provedor_id if conversation.inbox else None
                # Normalização estrita de canal e telefone para limpeza total
                channel = redis_memory_service.normalize_channel(conversation.inbox.channel_type if conversation.inbox else "whatsapp")
                phone = conversation.contact.phone if conversation.contact else "unknown"
                
                redis_memory_service.clear_memory_sync(
                    provedor_id=provedor_id,
                    conversation_id=conversation.id,
                    channel=channel,
                    phone=phone
                )
                logger.info(f"✓ Memória Redis limpa para conversa {conversation.id} ({channel}:{phone})")
            except Exception as redis_error:
                logger.error(f"Erro ao limpar memória Redis da conversa {conversation.id}: {str(redis_error)}", exc_info=True)
            
            return True
        except Exception as e:
            logger.error(f"Erro ao finalizar encerramento da conversa {conversation.id}: {e}", exc_info=True)
            return False
    
    @classmethod
    def should_reopen(cls, conversation: Conversation, tolerance_minutes: int = None) -> bool:
        """
        Verifica se uma conversa em 'closing' deve ser reaberta.
        
        Args:
            conversation: Conversa em estado 'closing'
            tolerance_minutes: Período de tolerância em minutos (padrão: 2)
            
        Returns:
            bool: True se a conversa deve ser reaberta (dentro da janela de tolerância)
        """
        return conversation.is_closing_within_tolerance(tolerance_minutes or cls.DEFAULT_TOLERANCE_MINUTES)
    
    @classmethod
    def process_final_closures(cls, tolerance_minutes: int = None) -> dict:
        """
        Processa conversas em estado 'closing' que excederam a janela de tolerância
        e as finaliza (muda para 'closed').
        
        Este método deve ser chamado periodicamente por um job assíncrono.
        
        Args:
            tolerance_minutes: Período de tolerância em minutos (padrão: 2)
            
        Returns:
            dict: Estatísticas do processamento
        """
        tolerance = tolerance_minutes or cls.DEFAULT_TOLERANCE_MINUTES
        cutoff_time = timezone.now() - timedelta(minutes=tolerance)
        
        # Buscar conversas em 'closing' que excederam a tolerância
        conversations_to_close = Conversation.objects.filter(
            status='closing',
            closing_requested_at__lte=cutoff_time
        )
        
        stats = {
            'total_found': conversations_to_close.count(),
            'finalized': 0,
            'errors': 0
        }
        
        for conversation in conversations_to_close:
            try:
                if cls.finalize_closing(conversation):
                    stats['finalized'] += 1
                else:
                    stats['errors'] += 1
            except Exception as e:
                logger.error(f"Erro ao processar encerramento da conversa {conversation.id}: {e}", exc_info=True)
                stats['errors'] += 1
        
        if stats['total_found'] > 0:
            logger.info(
                f"Processamento de encerramentos: {stats['finalized']} finalizadas, "
                f"{stats['errors']} erros (total: {stats['total_found']})"
            )
        
        return stats


# Instância singleton do serviço
closing_service = ClosingService()

