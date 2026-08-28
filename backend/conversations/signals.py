from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.core.cache import cache
from .models import Conversation, Message, Inbox
from core.models import Canal
from .services import ConversationNotificationService
from .serializers import MessageSerializer, ConversationSerializer
import logging

logger = logging.getLogger(__name__)

# Usar cache do Redis ao invés de variáveis globais para evitar race conditions
# Cache com TTL de 60 segundos (suficiente para o ciclo de save)
CACHE_TTL = 60

@receiver(post_save, sender=Message)
def notify_new_message(sender, instance, created, **kwargs):
    """
    Notifica o painel e o ChatArea sobre novas mensagens via WebSocket.
    Envia DIRETO do banco de dados, sem depender de Dramatiq/Redis/fila.
    Usa transaction.on_commit para garantir que a mensagem já esteja salva.
    """
    if created:
        def _do_notify():
            try:
                from .serializers import MessageSerializer, ConversationSerializer
                
                # Carregar mensagem com relações necessárias
                msg = Message.objects.select_related(
                    'conversation',
                    'conversation__contact',
                    'conversation__assignee',
                    'conversation__inbox',
                    'conversation__inbox__provedor'
                ).get(id=instance.pk)
                
                conversation = msg.conversation
                provedor_id = conversation.inbox.provedor.id if conversation.inbox and conversation.inbox.provedor else None
                
                if not provedor_id:
                    return
                
                # Serializar dados completos para o front
                message_data = MessageSerializer(msg).data
                conversation_data = ConversationSerializer(conversation).data
                
                logger.info(
                    f"[MessageSignal] Notificando mensagem {instance.pk} "
                    f"para conversa {conversation.id}, provedor {provedor_id} (DIRETO)"
                )
                
                if msg.is_from_customer:
                    ConversationNotificationService.notify_message_received(
                        provedor_id,
                        conversation.id,
                        message_data,
                        conversation_data
                    )
                else:
                    ConversationNotificationService.notify_message_sent(
                        provedor_id,
                        conversation.id,
                        message_data,
                        conversation_data
                    )
                    
            except Message.DoesNotExist:
                logger.warning(f"[MessageSignal] Mensagem {instance.pk} não encontrada")
            except Exception as e:
                logger.error(f"[MessageSignal] Erro ao notificar mensagem {instance.pk}: {e}", exc_info=True)
        
        transaction.on_commit(_do_notify)


@receiver(pre_save, sender=Conversation)
def store_previous_status(sender, instance, **kwargs):
    """
    Armazena o status anterior da conversa antes de salvar usando cache thread-safe
    """
    if instance.pk:
        try:
            # Usar select_for_update para evitar race conditions em produção
            with transaction.atomic():
                old_instance = Conversation.objects.select_for_update().get(pk=instance.pk)
                previous_status = old_instance.status
                previous_assignee_id = old_instance.assignee_id if old_instance.assignee else None
                previous_last_message_at = old_instance.last_message_at.isoformat() if old_instance.last_message_at else None
                
                # Armazenar no cache com chave única por conversa
                cache_key_status = f"conversation_{instance.pk}_previous_status"
                cache_key_assignee = f"conversation_{instance.pk}_previous_assignee"
                cache_key_last_msg = f"conversation_{instance.pk}_previous_last_msg"
                
                cache.set(cache_key_status, previous_status, CACHE_TTL)
                cache.set(cache_key_assignee, previous_assignee_id, CACHE_TTL)
                cache.set(cache_key_last_msg, previous_last_message_at, CACHE_TTL)
        except Conversation.DoesNotExist:
            # Nova conversa - não há status anterior
            cache_key_status = f"conversation_{instance.pk}_previous_status"
            cache_key_assignee = f"conversation_{instance.pk}_previous_assignee"
            cache_key_last_msg = f"conversation_{instance.pk}_previous_last_msg"
            cache.set(cache_key_status, None, CACHE_TTL)
            cache.set(cache_key_assignee, None, CACHE_TTL)
            cache.set(cache_key_last_msg, None, CACHE_TTL)
        except Exception as e:
            logger.error(f"Erro ao armazenar status anterior da conversa {instance.pk}: {e}", exc_info=True)
    else:
        # Nova conversa - não há status anterior
        # Não armazenar nada no cache para novas conversas
        pass


@receiver(pre_save, sender=Conversation)
def stamp_agent_chat_visible_from_on_return_to_bot(sender, instance, **kwargs):
    """
    Quando a conversa volta ao bot (snoozed) sem atendente, após fase humana ou encerrada,
    marca agent_chat_visible_from para o painel não listar mensagens de ciclos anteriores.
    """
    if not instance.pk:
        return
    try:
        old = Conversation.objects.get(pk=instance.pk)
    except Conversation.DoesNotExist:
        return

    from_states = ("open", "pending", "closed", "resolved", "finalizada", "closing", "encerrada", "ended")
    if (
        instance.status == "snoozed"
        and not instance.assignee_id
        and old.status in from_states
    ):
        from django.utils import timezone as dj_tz

        attrs = dict(instance.additional_attributes or {})
        attrs["agent_chat_visible_from"] = dj_tz.now().isoformat()
        instance.additional_attributes = attrs


@receiver(post_save, sender=Conversation)
def notify_conversation_change(sender, instance, created, **kwargs):
    """
    Notifica mudanças de conversa via WebSocket
    Usa cache thread-safe para evitar race conditions
    """
    try:
        # Obter provedor_id da conversa
        provedor_id = instance.inbox.provedor.id if instance.inbox and instance.inbox.provedor else None
        
        if not provedor_id:
            logger.debug(f"Conversa {instance.pk} sem provedor_id, pulando notificação")
            return
        
        if created:
            # Nova conversa
            logger.info(f"Nova conversa criada: {instance.id} para provedor {provedor_id}")
            ConversationNotificationService.notify_conversation_updated(
                provedor_id, 
                instance.id, 
                'conversation_created'
            )
        else:
            # Obter status anterior do cache
            cache_key_status = f"conversation_{instance.pk}_previous_status"
            cache_key_assignee = f"conversation_{instance.pk}_previous_assignee"
            cache_key_last_msg = f"conversation_{instance.pk}_previous_last_msg"
            
            previous_status = cache.get(cache_key_status)
            previous_assignee_id = cache.get(cache_key_assignee)
            previous_last_msg = cache.get(cache_key_last_msg)
            
            current_status = instance.status
            current_assignee_id = instance.assignee_id if instance.assignee else None
            current_last_msg = instance.last_message_at.isoformat() if instance.last_message_at else None
            
            # 1. Notificar se o status mudou
            status_changed = previous_status != current_status
            if status_changed:
                logger.info(
                    f"Status da conversa {instance.id} mudou: {previous_status} -> {current_status}"
                )
                
                if current_status == 'closed':
                    ConversationNotificationService.notify_conversation_closed(provedor_id, instance.id)
                elif current_status == 'ended':
                    ConversationNotificationService.notify_conversation_ended(provedor_id, instance.id)
                else:
                    # Qualquer outra mudança de status (open, pending, snoozed)
                    ConversationNotificationService.notify_conversation_updated(provedor_id, instance.id, 'conversation_status_changed', {'status': current_status})
            
            # 2. Notificar se a última mensagem mudou (IMPORTANTE PARA ORDENAÇÃO NO TOPO)
            last_msg_changed = previous_last_msg != current_last_msg
            if last_msg_changed and not status_changed:
                # Se só mudou o horário da mensagem (e não o status), notificar como atualização
                # Isso forçará o front a mover para o topo
                logger.info(f"Horário da última mensagem da conversa {instance.id} atualizado: {previous_last_msg} -> {current_last_msg}")
                ConversationNotificationService.notify_conversation_updated(
                    provedor_id, 
                    instance.id, 
                    'conversation_updated',
                    {
                        'last_message_at': current_last_msg,
                        'status': current_status
                    }
                )
            
            # 3. Notificar se a atribuição mudou (Agente ou Equipe)
            current_team_id = instance.team_id
            # Obter time_id anterior do cache se necessário, mas aqui podemos simplificar
            # já que notify_conversation_updated manda o objeto completo.
            
            if previous_assignee_id != current_assignee_id:
                logger.info(f"Atribuição da conversa {instance.id} mudou")
                ConversationNotificationService.notify_conversation_updated(provedor_id, instance.id, 'conversation_assignment_changed')
            
            # Limpar cache após processar
            cache.delete(cache_key_status)
            cache.delete(cache_key_assignee)
            cache.delete(cache_key_last_msg)
                
    except Exception as e:
        logger.error(
            f"Erro ao notificar mudança de conversa {instance.pk}: {e}",
            exc_info=True
        )
@receiver(post_delete, sender=Conversation)
def notify_conversation_deleted(sender, instance, **kwargs):
    """
    Notifica quando uma conversa é deletada
    """
    try:
        provedor_id = instance.inbox.provedor.id if instance.inbox and instance.inbox.provedor else None
        
        if provedor_id:
            logger.info(f"Conversa {instance.id} deletada para provedor {provedor_id}")
            ConversationNotificationService.notify_conversation_updated(
                provedor_id, 
                instance.id, 
                'conversation_deleted'
            )
            
            # Limpar cache se existir
            cache_key_status = f"conversation_{instance.pk}_previous_status"
            cache_key_assignee = f"conversation_{instance.pk}_previous_assignee"
            cache.delete(cache_key_status)
            cache.delete(cache_key_assignee)
                
    except Exception as e:
        logger.error(
            f"Erro ao notificar deleção de conversa {instance.pk}: {e}",
            exc_info=True
        )


@receiver(post_delete, sender=Canal)
def cleanup_inbox_on_canal_delete(sender, instance, **kwargs):
    """
    Garante a exclusão em cascata do Inbox quando um Canal é deletado.
    Como channel_id é um CharField, o Django não faz isso automaticamente.
    """
    try:
        # Buscar inboxes que apontam para este canal
        # 1. Por ID numérico
        inboxes = Inbox.objects.filter(channel_id=str(instance.id), provedor=instance.provedor)

        # 2. Casos especiais (strings como whatsapp_cloud_api)
        if instance.tipo == 'whatsapp_oficial':
            special_inboxes = Inbox.objects.filter(channel_id='whatsapp_cloud_api', provedor=instance.provedor)
            inboxes = inboxes | special_inboxes

        for inbox in inboxes:
            logger.info(f"[CascadeDelete] Deletando Inbox órfão {inbox.id} ({inbox.name}) após exclusão do Canal {instance.id}")
            inbox.delete()

    except Exception as e:
        logger.error(f"[CascadeDelete] Erro ao limpar inboxes para o canal {instance.id}: {e}")
