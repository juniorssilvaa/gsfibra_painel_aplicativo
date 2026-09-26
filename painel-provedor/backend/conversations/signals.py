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


def _notify_agent_push_for_customer_message(msg, conversation):
    """Envia push FCM ao(s) atendente(s) quando o cliente manda mensagem.

    - Com assignee: avisa o atendente da conversa
    - Em espera (waiting_for_agent): avisa atendentes do provedor/equipe
    - Com a IA / chatbot (sem assignee e fora da fila): avisa atendentes do provedor
    """
    from core.agent_push import notify_agents_push
    from core.agent_alert_notify import _resolve_push_user_ids

    contact = getattr(conversation, 'contact', None)
    nome = (getattr(contact, 'name', None) or 'Cliente').strip() or 'Cliente'
    preview = (getattr(msg, 'content', None) or '').strip()
    if not preview:
        preview = 'Nova mensagem'
    elif len(preview) > 120:
        preview = preview[:117] + '…'

    assignee = getattr(conversation, 'assignee', None)
    assignee_id = getattr(conversation, 'assignee_id', None) or (
        getattr(assignee, 'id', None) if assignee else None
    )

    provedor = getattr(getattr(conversation, 'inbox', None), 'provedor', None)
    team = getattr(conversation, 'team', None)
    waiting = bool(getattr(conversation, 'waiting_for_agent', False))

    user_ids = []
    event_type = 'new_message'
    title = nome

    if assignee_id:
        user_ids = [int(assignee_id)]
        event_type = 'new_message'
    elif provedor is not None and waiting:
        user_ids = _resolve_push_user_ids(
            provedor,
            target_user=None,
            team=team,
            exclude_user_id=None,
        )
        event_type = 'waiting'
        title = f'Espera · {nome}'
    elif provedor is not None:
        # Com a IA / chatbot (sem atendente humano)
        user_ids = _resolve_push_user_ids(
            provedor,
            target_user=None,
            team=None,
            exclude_user_id=None,
        )
        event_type = 'automation'
        bot_mode = (getattr(provedor, 'bot_mode', None) or 'ia').strip().lower()
        prefix = 'Chatbot' if bot_mode == 'chatbot' else 'IA'
        title = f'{prefix} · {nome}'

    if not user_ids:
        logger.info(
            "[MessageSignal] Push ignorado conv=%s assignee=%s waiting=%s (sem destinatários)",
            getattr(conversation, 'id', None),
            assignee_id,
            waiting,
        )
        return

    result = notify_agents_push(
        user_ids=user_ids,
        title=title,
        body=preview,
        conversation_id=getattr(conversation, 'id', None),
        event_type=event_type,
    )
    logger.info(
        "[MessageSignal] Push FCM conv=%s type=%s users=%s result=%s",
        getattr(conversation, 'id', None),
        event_type,
        len(user_ids),
        result,
    )


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
                from .serializers import MessageSerializer
                from .services import ConversationNotificationService

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

                message_data = MessageSerializer(msg).data
                conversation_data = ConversationNotificationService.serialize_conversation_realtime(
                    conversation.id
                )
                if conversation_data is not None:
                    conversation_data['last_message'] = message_data
                    conversation_data['last_message_at'] = message_data.get('created_at') or conversation_data.get('last_message_at')
                
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
                    # Push FCM no app do atendente (além do WebSocket do painel)
                    try:
                        _notify_agent_push_for_customer_message(msg, conversation)
                    except Exception as push_err:
                        logger.warning(
                            "[MessageSignal] Push FCM falhou msg=%s: %s",
                            instance.pk,
                            push_err,
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
def stamp_closed_at(sender, instance, **kwargs):
    """
    Grava additional_attributes.closed_at quando a conversa passa a encerrada (removido ao reabrir).
    As encerradas esperam a rotina noturna e updated_at muda nesse meio tempo; closed_at é o
    horário real usado como ended_at na migração e na auditoria. Via update() para não re-disparar signals
    e porque muitos encerramentos salvam com update_fields=['status'].
    """
    from conversations.inbound_routing import CLOSED_STATUSES

    attrs = instance.additional_attributes if isinstance(instance.additional_attributes, dict) else {}
    is_closed = instance.status in CLOSED_STATUSES
    if is_closed == bool(attrs.get('closed_at')):
        return
    try:
        db_attrs = Conversation.objects.filter(pk=instance.pk).values_list('additional_attributes', flat=True).first()
        db_attrs = dict(db_attrs) if isinstance(db_attrs, dict) else {}
        if is_closed:
            if not db_attrs.get('closed_at'):
                from django.utils import timezone as dj_tz
                db_attrs['closed_at'] = dj_tz.now().isoformat()
                Conversation.objects.filter(pk=instance.pk).update(additional_attributes=db_attrs)
            instance.additional_attributes = {**attrs, 'closed_at': db_attrs['closed_at']}
        else:
            if db_attrs.pop('closed_at', None):
                Conversation.objects.filter(pk=instance.pk).update(additional_attributes=db_attrs)
            instance.additional_attributes = {k: v for k, v in attrs.items() if k != 'closed_at'}
            # Reaberta: a análise do aprendizado é refeita no próximo encerramento, com o atendimento completo
            from conversations.models import AILearningAnalysis
            AILearningAnalysis.objects.filter(conversation_id=instance.pk).delete()
    except Exception as e:
        logger.warning(f"Erro ao marcar closed_at da conversa {instance.pk}: {e}")


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
            
            # 2. Mudança de last_message_at já é notificada pelo signal de Message (message_received/sent).
            # Evitar segundo broadcast com serialização pesada.

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


@receiver(post_save, sender=Conversation)
def ensure_protocol_on_conversation_create(sender, instance, created, **kwargs):
    """Gera protocolo NioHub assim que a conversa é criada em qualquer canal."""
    if not created:
        return
    try:
        from conversations.protocol_service import ensure_niohub_protocol

        ensure_niohub_protocol(instance, force_new=False, create_system_message=False)
    except Exception as e:
        logger.error(
            f"[Protocol] Falha ao gerar protocolo na criação da conversa {instance.pk}: {e}",
            exc_info=True,
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
