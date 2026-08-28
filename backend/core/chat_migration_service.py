"""
Service para migração de conversas encerradas do PostgreSQL local para o Supabase
Implementa arquitetura dual database:
- PostgreSQL Local: Conversas ATIVAS (status IN ('open', 'pending', 'snoozed'))
- Supabase: Conversas ENCERRADAS (status = 'closed') - apenas histórico
"""
import logging
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.utils import timezone
from conversations.models import Conversation, Message, Contact
from core.supabase_service import supabase_service

logger = logging.getLogger(__name__)


class ChatMigrationService:
    """
    Service responsável por migrar conversas encerradas do PostgreSQL local para o Supabase
    e remover os dados do local após confirmação de sucesso.
    """
    
    def __init__(self):
        self.supabase_service = supabase_service
    
    def buscar_conversa_completa(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        Busca todos os dados de uma conversa do PostgreSQL local
        
        Args:
            conversation_id: ID da conversa a ser buscada
            
        Returns:
            Dict com todos os dados da conversa ou None se não encontrada
        """
        try:
            conversation = Conversation.objects.select_related(
                'contact', 'inbox', 'assignee', 'team'
            ).prefetch_related('messages').get(id=conversation_id)
            
            # Buscar todas as mensagens
            messages = Message.objects.filter(conversation=conversation).order_by('created_at')
            
            # Buscar CSAT feedbacks se houver
            csat_feedbacks = []
            try:
                from conversations.models import CSATFeedback
                csat_feedbacks = CSATFeedback.objects.filter(conversation=conversation)
            except Exception:
                pass
            
            return {
                'conversation': conversation,
                'contact': conversation.contact,
                'inbox': conversation.inbox,
                'messages': list(messages),
                'csat_feedbacks': list(csat_feedbacks),
                'provedor_id': conversation.inbox.provedor_id if conversation.inbox else None
            }
        except Conversation.DoesNotExist:
            logger.warning(f"Conversa {conversation_id} não encontrada no PostgreSQL local")
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar conversa {conversation_id}: {e}", exc_info=True)
            return None
    
    def verificar_conversa_no_supabase(self, conversation_id: int, provedor_id: int) -> bool:
        """
        Verifica se a conversa já existe no Supabase (evitar duplicatas)
        
        Args:
            conversation_id: ID da conversa
            provedor_id: ID do provedor
            
        Returns:
            True se já existe, False caso contrário
        """
        try:
            import requests
            from django.conf import settings
            
            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json',
                'X-Provedor-ID': str(provedor_id)
            }
            params = {
                'id': f'eq.{conversation_id}',
                'provedor_id': f'eq.{provedor_id}',
                'select': 'id'
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return len(data) > 0
            return False
        except Exception as e:
            logger.warning(f"Erro ao verificar conversa no Supabase: {e}")
            # Em caso de erro, assumir que não existe para tentar migrar
            return False
    
    def migrar_para_supabase(self, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migra todos os dados de uma conversa para o Supabase
        
        Args:
            conversation_data: Dict retornado por buscar_conversa_completa()
            
        Returns:
            Dict com resultado da migração:
            {
                'success': bool,
                'conversation_sent': bool,
                'contact_sent': bool,
                'messages_sent': int,
                'total_messages': int,
                'audit_sent': bool,
                'errors': List[str]
            }
        """
        if not conversation_data:
            return {
                'success': False,
                'errors': ['Dados da conversa não fornecidos']
            }
        
        conversation = conversation_data['conversation']
        contact = conversation_data['contact']
        inbox = conversation_data['inbox']
        messages = conversation_data['messages']
        provedor_id = conversation_data['provedor_id']
        
        if not provedor_id:
            return {
                'success': False,
                'errors': ['Provedor não encontrado para a conversa']
            }
        
        result = {
            'success': True,
            'conversation_sent': False,
            'contact_sent': False,
            'messages_sent': 0,
            'total_messages': len(messages),
            'audit_sent': False,
            'errors': []
        }
        
        # 1. Verificar se já existe no Supabase
        if self.verificar_conversa_no_supabase(conversation.id, provedor_id):
            result['success'] = True
            result['conversation_sent'] = True
            result['contact_sent'] = True
            result['messages_sent'] = len(messages)
            return result
        
        # 2. Enviar contato primeiro (necessário para foreign keys)
        try:
            contact_success = self.supabase_service.save_contact(
                provedor_id=provedor_id,
                contact_id=contact.id,
                name=contact.name,
                phone=getattr(contact, 'phone', None),
                email=getattr(contact, 'email', None),
                avatar=getattr(contact, 'avatar', None),
                created_at_iso=contact.created_at.isoformat() if contact.created_at else None,
                updated_at_iso=contact.updated_at.isoformat() if contact.updated_at else None,
                additional_attributes=contact.additional_attributes
            )
            result['contact_sent'] = contact_success
            if not contact_success:
                result['errors'].append('Falha ao enviar contato para Supabase')
        except Exception as e:
            logger.error(f"Erro ao enviar contato {contact.id} para Supabase: {e}", exc_info=True)
            result['errors'].append(f'Erro ao enviar contato: {str(e)}')
            result['success'] = False
        
        # 3. Enviar conversa
        try:
            conversation_success = self.supabase_service.save_conversation(
                provedor_id=provedor_id,
                conversation_id=conversation.id,
                contact_id=contact.id,
                inbox_id=inbox.id if inbox else None,
                status=conversation.status,
                assignee_id=conversation.assignee_id,
                team_id=conversation.team_id,
                created_at_iso=conversation.created_at.isoformat() if conversation.created_at else None,
                updated_at_iso=conversation.updated_at.isoformat() if conversation.updated_at else None,
                last_message_at_iso=conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                ended_at_iso=conversation.updated_at.isoformat() if conversation.status == 'closed' else None,
                additional_attributes=conversation.additional_attributes
            )
            result['conversation_sent'] = conversation_success
            if not conversation_success:
                result['errors'].append('Falha ao enviar conversa para Supabase')
                result['success'] = False
        except Exception as e:
            logger.error(f"Erro ao enviar conversa {conversation.id} para Supabase: {e}", exc_info=True)
            result['errors'].append(f'Erro ao enviar conversa: {str(e)}')
            result['success'] = False
        
        # 4. Enviar todas as mensagens
        messages_sent = 0
        for msg in messages:
            try:
                msg_success = self.supabase_service.save_message(
                    provedor_id=provedor_id,
                    conversation_id=conversation.id,
                    contact_id=contact.id,
                    content=msg.content,
                    message_type=msg.message_type,
                    is_from_customer=msg.is_from_customer,
                    external_id=msg.external_id,
                    file_url=msg.file_url,
                    file_name=msg.file_name,
                    file_size=msg.file_size,
                    additional_attributes=msg.additional_attributes,
                    created_at_iso=msg.created_at.isoformat() if msg.created_at else None,
                    updated_at_iso=msg.updated_at.isoformat() if msg.updated_at else None
                )
                if msg_success:
                    messages_sent += 1
                else:
                    result['errors'].append(f'Falha ao enviar mensagem {msg.id} para Supabase')
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem {msg.id} para Supabase: {e}", exc_info=True)
                result['errors'].append(f'Erro ao enviar mensagem {msg.id}: {str(e)}')
        
        result['messages_sent'] = messages_sent
        
        # Se menos de 90% das mensagens foram enviadas, considerar falha parcial
        if messages and (messages_sent / len(messages)) < 0.9:
            result['success'] = False
            result['errors'].append(f'Apenas {messages_sent}/{len(messages)} mensagens foram enviadas')
        
        # 5. Enviar auditoria (opcional - não bloqueia migração)
        try:
            from core.models import AuditLog
            audit_logs = AuditLog.objects.filter(
                conversation_id=conversation.id,
                provedor_id=provedor_id
            ).order_by('-timestamp')[:10]  # Últimos 10 logs
            
            for audit in audit_logs:
                try:
                    audit_success = self.supabase_service.save_audit(
                        provedor_id=provedor_id,
                        conversation_id=conversation.id,
                        action=audit.action,
                        details={'details': audit.details} if audit.details else {},
                        user_id=audit.user_id,
                        ended_at_iso=audit.timestamp.isoformat() if hasattr(audit, 'timestamp') and audit.timestamp else None
                    )
                    if audit_success:
                        result['audit_sent'] = True
                except Exception:
                    pass  # Não bloquear por erro em auditoria
        except Exception as e:
            logger.warning(f"Erro ao enviar auditoria para Supabase: {e}")
            # Não bloquear migração por erro em auditoria
        
        return result
    
    def _merge_closure_metadata_into_conversation(
        self, conversation, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Mescla metadata de encerramento em conversation.additional_attributes para que
        o registro migrado (Supabase) e consultas locais identifiquem resolução por IA/chatbot vs agente.
        """
        metadata = metadata or {}
        attrs = dict(conversation.additional_attributes or {})
        for key, value in metadata.items():
            if value is not None:
                attrs[key] = value
        if metadata.get('encerrado_por') == 'agent':
            attrs['resolucao_automacao'] = False
        elif metadata.get('encerrado_por') == 'ai' or metadata.get('resolucao_automacao') is True:
            attrs['resolucao_automacao'] = True
        elif metadata.get('resolucao_automacao') is False:
            attrs['resolucao_automacao'] = False
        conversation.additional_attributes = attrs
        conversation.save(update_fields=['additional_attributes'])
    
    def remover_do_local(self, conversation_id: int) -> bool:
        """
        Remove dados da conversa do PostgreSQL local APENAS após confirmação de migração
        
        Args:
            conversation_id: ID da conversa a ser removida
            
        Returns:
            True se removido com sucesso, False caso contrário
        """
        try:
            with transaction.atomic():
                conversation = Conversation.objects.get(id=conversation_id)
                
                # Verificar se realmente está fechada
                if conversation.status != 'closed':
                    logger.warning(f"Conversa {conversation_id} não está fechada, não removendo do local")
                    return False
                
                # Remover mensagens primeiro (devido a foreign key)
                Message.objects.filter(conversation=conversation).delete()
                
                # Remover conversa
                conversation.delete()
                
                return True
        except Conversation.DoesNotExist:
            logger.warning(f"Conversa {conversation_id} não encontrada para remoção")
            return False
        except Exception as e:
            logger.error(f"Erro ao remover conversa {conversation_id} do local: {e}", exc_info=True)
            return False
    
    def encerrar_e_migrar(self, conversation_id: int, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Processo completo: encerra conversa, migra para Supabase e remove do local
        
        IMPORTANTE: Esta função é SEGURA - se falhar em qualquer etapa, NÃO remove dados do local
        
        Args:
            conversation_id: ID da conversa
            metadata: Metadados adicionais (ex: resolution_type, user_id, etc)
            
        Returns:
            Dict com resultado completo:
            {
                'success': bool,
                'migration_success': bool,
                'removed_from_local': bool,
                'errors': List[str],
                'warnings': List[str]
            }
        """
        result = {
            'success': False,
            'migration_success': False,
            'removed_from_local': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # 1. Buscar dados completos da conversa
            conversation_data = self.buscar_conversa_completa(conversation_id)
            if not conversation_data:
                result['errors'].append(f'Conversa {conversation_id} não encontrada')
                return result
            
            conversation = conversation_data['conversation']
            
            # 2. Verificar se já está fechada (closed) - não migrar se estiver em 'closing'
            # A migração só deve acontecer quando a conversa está definitivamente fechada
            if conversation.status != 'closed':
                result['warnings'].append(f'Conversa {conversation_id} não está fechada (status: {conversation.status})')
                # Não migrar se não estiver fechada (incluindo 'closing')
                return result
            
            # 2b. Persistir metadados de encerramento em additional_attributes (histórico no Supabase / dashboards)
            self._merge_closure_metadata_into_conversation(conversation, metadata)
            
            # 3. Migrar para Supabase
            migration_result = self.migrar_para_supabase(conversation_data)
            
            if not migration_result.get('success'):
                result['errors'].extend(migration_result.get('errors', []))
                result['warnings'].append('Migração para Supabase falhou - dados mantidos no local')
                logger.error(f"Falha na migração da conversa {conversation_id} - dados não removidos do local")
                return result
            
            result['migration_success'] = True
            
            # 4. Validar que dados críticos foram enviados
            if not migration_result.get('conversation_sent'):
                result['errors'].append('Conversa não foi enviada para Supabase')
                result['migration_success'] = False
                return result
            
            if not migration_result.get('contact_sent'):
                result['errors'].append('Contato não foi enviado para Supabase')
                result['migration_success'] = False
                return result
            
            # Verificar se pelo menos 90% das mensagens foram enviadas
            messages_sent = migration_result.get('messages_sent', 0)
            total_messages = migration_result.get('total_messages', 0)
            if total_messages > 0 and (messages_sent / total_messages) < 0.9:
                result['errors'].append(f'Apenas {messages_sent}/{total_messages} mensagens foram enviadas')
                result['migration_success'] = False
                return result
            
            # 5. Se tudo OK, remover do local
            removed = self.remover_do_local(conversation_id)
            result['removed_from_local'] = removed
            
            if removed:
                result['success'] = True
            else:
                result['warnings'].append('Dados migrados mas não removidos do local (verificar logs)')
            
        except Exception as e:
            logger.error(f"Erro crítico ao encerrar e migrar conversa {conversation_id}: {e}", exc_info=True)
            result['errors'].append(f'Erro crítico: {str(e)}')
            # Em caso de erro, NUNCA remover dados do local
        
        return result


# Instância singleton do service
chat_migration_service = ChatMigrationService()

