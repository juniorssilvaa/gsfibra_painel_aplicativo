"""Webhooks de mensagens Instagram (object=instagram)."""
import logging
import re
import threading
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from conversations.models import Contact, Conversation, Inbox, Message, MessageReaction, Team
from core.horario_utils import verificar_automacao_agendada
from core.models import Canal
from integrations.instagram_media import download_instagram_attachment, map_inbound_attachment_type
from integrations.instagram_profiles import enrich_instagram_contact

logger = logging.getLogger(__name__)


def find_instagram_canal(ig_account_id: str):
    if not ig_account_id:
        return None
    target = str(ig_account_id)
    canais = list(Canal.objects.filter(tipo='instagram').select_related('provedor'))
    for canal in canais:
        extras = canal.dados_extras or {}
        ids = {
            str(extras.get('instagram_user_id') or ''),
            str(extras.get('instagram_webhook_account_id') or ''),
        }
        if target in ids:
            return canal

    if len(canais) == 1:
        canal = canais[0]
        extras = dict(canal.dados_extras or {})
        if extras.get('instagram_webhook_account_id') != target:
            extras['instagram_webhook_account_id'] = target
            canal.dados_extras = extras
            canal.save(update_fields=['dados_extras', 'updated_at'])
            logger.info(
                '[InstagramWebhook] Vinculado webhook account_id=%s ao canal %s',
                target,
                canal.id,
            )
        return canal

    known = [
        {
            'canal_id': c.id,
            'user_id': (c.dados_extras or {}).get('instagram_user_id'),
            'webhook_id': (c.dados_extras or {}).get('instagram_webhook_account_id'),
        }
        for c in canais
    ]
    logger.warning('[InstagramWebhook] Canal não encontrado para IG %s. Conhecidos: %s', target, known)
    return None


def get_or_create_instagram_inbox(canal: Canal) -> Inbox:
    """Evita MultipleObjectsReturned quando há inboxes Instagram duplicados."""
    qs = Inbox.objects.filter(
        provedor=canal.provedor,
        channel_type='instagram',
        channel_id=str(canal.id),
    ).order_by('id')
    inbox = qs.first()
    if inbox:
        dup_count = qs.count()
        if dup_count > 1:
            logger.warning(
                '[InstagramWebhook] %s inboxes Instagram duplicados para canal=%s; usando inbox=%s',
                dup_count,
                canal.id,
                inbox.id,
            )
        return inbox

    return Inbox.objects.create(
        provedor=canal.provedor,
        channel_type='instagram',
        channel_id=str(canal.id),
        name=f'Instagram - {canal.nome}',
        additional_attributes={
            'canal_id': canal.id,
            'instagram_user_id': (canal.dados_extras or {}).get('instagram_user_id'),
        },
    )


def _timestamp_to_aware(ts_ms) -> timezone.datetime:
    try:
        ts = int(ts_ms) / 1000.0
        return timezone.make_aware(datetime.fromtimestamp(ts, tz=dt_timezone.utc))
    except Exception:
        return timezone.now()


def process_instagram_webhook_payload(data: dict) -> None:
    for entry in data.get('entry') or []:
        ig_account_id = entry.get('id')
        messaging = entry.get('messaging') or []
        if messaging:
            logger.info('[InstagramWebhook] messaging events=%s ig=%s', len(messaging), ig_account_id)
            process_instagram_messaging_events(ig_account_id, messaging)
            continue

        for change in entry.get('changes') or []:
            field = change.get('field')
            value = change.get('value') or {}
            logger.info('[InstagramWebhook] change field=%s ig=%s keys=%s', field, ig_account_id, list(value.keys())[:8])

            if field == 'messages':
                if value.get('sender') and (value.get('message') or value.get('text')):
                    process_instagram_messaging_events(ig_account_id, [value])
                elif isinstance(value.get('messaging'), list):
                    process_instagram_messaging_events(ig_account_id, value['messaging'])
            elif field == 'messaging_reactions' and value.get('sender'):
                process_instagram_messaging_events(ig_account_id, [value])
            elif field == 'messaging_postbacks' and value.get('sender'):
                process_instagram_messaging_events(ig_account_id, [value])


def process_instagram_messaging_events(ig_account_id: str, events: list) -> None:
    try:
        canal = find_instagram_canal(ig_account_id)
        if not canal or not canal.provedor:
            logger.warning('[InstagramWebhook] Canal não encontrado para conta IG %s', ig_account_id)
            return

        provedor = canal.provedor
        inbox = get_or_create_instagram_inbox(canal)
        bot_mode = getattr(provedor, 'bot_mode', 'ia')
        ia_team = Team.get_or_create_ia_team(provedor) if bot_mode == 'ia' else None
    except Exception:
        logger.exception(
            '[InstagramWebhook] Falha ao preparar canal/inbox para IG %s',
            ig_account_id,
        )
        return

    for event in events:
        try:
            if event.get('reaction'):
                _process_instagram_reaction_event(event, ig_account_id, canal, provedor, inbox)
            elif event.get('postback'):
                _process_instagram_postback_event(
                    event, ig_account_id, canal, provedor, inbox, ia_team, bot_mode
                )
            else:
                _process_single_messaging_event(event, ig_account_id, canal, provedor, inbox, ia_team, bot_mode)
        except Exception:
            logger.exception('[InstagramWebhook] Erro ao processar evento IG')


def _business_ids(ig_account_id, canal):
    return {
        str(ig_account_id or ''),
        str((canal.dados_extras or {}).get('instagram_webhook_account_id') or ''),
        str((canal.dados_extras or {}).get('instagram_user_id') or ''),
    }


def _get_or_create_contact_conversation(sender_id, provedor, inbox, ia_team, canal):
    profile_name = f'Instagram {sender_id}'
    contact, _created = Contact.objects.get_or_create(
        phone=str(sender_id)[:20],
        provedor=provedor,
        defaults={
            'name': profile_name,
            'additional_attributes': {'instagram_scoped_id': str(sender_id)},
        },
    )
    try:
        enrich_instagram_contact(contact, canal, sender_id)
    except Exception:
        logger.exception(
            '[InstagramWebhook] Falha ao enriquecer perfil do contato %s (sender=%s)',
            contact.id,
            sender_id,
        )

    conversation = Conversation.objects.filter(contact=contact, inbox=inbox).first()
    if not conversation:
        conversation = Conversation.objects.create(
            contact=contact,
            inbox=inbox,
            status='snoozed',
            team=ia_team,
            assignee=None,
        )

    return contact, conversation


def _process_instagram_reaction_event(event, ig_account_id, canal, provedor, inbox):
    reaction = event.get('reaction') or {}
    sender_id = (event.get('sender') or {}).get('id')
    if not sender_id:
        return

    if str(sender_id) in _business_ids(ig_account_id, canal):
        return

    mid = reaction.get('mid')
    action = (reaction.get('action') or 'react').lower()
    emoji = reaction.get('emoji') or reaction.get('reaction') or '❤️'

    if not mid:
        return

    contact, conversation = _get_or_create_contact_conversation(
        sender_id, provedor, inbox, None, canal
    )
    target = Message.objects.filter(external_id=str(mid), conversation=conversation).first()
    if not target:
        logger.info('[InstagramWebhook] Reação em mensagem não encontrada mid=%s', mid)
        return

    if action == 'unreact':
        MessageReaction.objects.filter(message=target, is_from_customer=True).delete()
        return

    MessageReaction.objects.update_or_create(
        message=target,
        is_from_customer=True,
        emoji=str(emoji)[:32],
        defaults={
            'additional_attributes': {
                'source': 'instagram_messaging',
                'instagram_mid': str(mid),
            }
        },
    )
    logger.info('[InstagramWebhook] Reação recebida conversa=%s emoji=%s', conversation.id, emoji)


def _parse_attachments(attachments, conversation_id, mid):
    if not attachments:
        return 'text', None, None, {}

    att = attachments[0] or {}
    raw_type = att.get('type') or 'attachment'
    message_type = map_inbound_attachment_type(raw_type)
    payload = att.get('payload') or {}
    source_url = payload.get('url')
    file_url = source_url
    extra_attrs = {
        'instagram_attachment_type': raw_type,
    }

    if payload.get('title'):
        extra_attrs['attachment_title'] = payload.get('title')
    if payload.get('id'):
        extra_attrs['instagram_media_id'] = payload.get('id')

    if source_url and message_type not in ('sticker', 'share', 'location'):
        local_url, meta = download_instagram_attachment(
            conversation_id,
            source_url,
            raw_type,
            mid=mid,
        )
        if local_url:
            file_url = local_url
            extra_attrs.update(meta or {})

    if raw_type == 'like_heart':
        content = '❤️'
    elif raw_type in ('share', 'ig_reel', 'story_mention') and source_url:
        content = source_url
    else:
        # Mídia pura: UI usa message_type + file_url (sem rótulo [image]/[audio])
        content = ''

    return message_type, content, file_url, extra_attrs


def _maybe_process_csat(conversation, contact, content: str, button_id=None) -> bool:
    """
    Processa CSAT explícito se houver pesquisa pendente.
    Se a mensagem não for nota CSAT, expira a pesquisa e reabre atendimento (retorna False).
    """
    if not content and not button_id:
        return False
    try:
        from conversations.inbound_routing import (
            expire_blocking_csat,
            has_blocking_csat,
            is_explicit_csat_reply,
            reopen_conversation_for_bot,
        )
        from conversations.csat_automation import CSATAutomationService

        if not has_blocking_csat(conversation):
            return False

        provedor = getattr(getattr(conversation, 'inbox', None), 'provedor', None)

        if not is_explicit_csat_reply(content or '', button_id):
            expire_blocking_csat(conversation)
            reopen_conversation_for_bot(
                conversation, provedor=provedor, allow_closing_reopen=True
            )
            conversation.refresh_from_db()
            logger.info(
                '[InstagramWebhook] CSAT expirado — novo atendimento conv=%s',
                conversation.id,
            )
            return False

        csat_feedback = CSATAutomationService.process_csat_response(
            message_text=str(content or ''),
            conversation=conversation,
            contact=contact,
            button_id=button_id,
        )
        if not csat_feedback:
            expire_blocking_csat(conversation)
            reopen_conversation_for_bot(
                conversation, provedor=provedor, allow_closing_reopen=True
            )
            conversation.refresh_from_db()
            return False

        logger.info(
            '[InstagramWebhook] CSAT processado conv=%s rating=%s (%s)',
            conversation.id,
            csat_feedback.rating_value,
            csat_feedback.emoji_rating,
        )
        if conversation.status != 'closed':
            conversation.status = 'closed'
            conversation.save(update_fields=['status'])

        try:
            from core.chat_migration_service import chat_migration_service
            migration_result = chat_migration_service.encerrar_e_migrar(
                conversation_id=conversation.id,
                metadata={
                    'migrado_apos_csat': True,
                    'csat_feedback_id': csat_feedback.id,
                    'rating': csat_feedback.rating_value,
                    'channel': 'instagram',
                },
            )
            if not migration_result.get('success'):
                logger.warning(
                    '[InstagramWebhook] Falha migração pós-CSAT conv=%s: %s',
                    conversation.id,
                    migration_result.get('errors', []),
                )
        except Exception as migration_err:
            logger.warning(
                '[InstagramWebhook] Falha migração pós-CSAT conv=%s: %s',
                conversation.id,
                migration_err,
            )
        return True
    except Exception as exc:
        logger.error('[InstagramWebhook] Erro CSAT: %s', exc, exc_info=True)
        return False


def _maybe_invoke_chatbot(
    *,
    provedor,
    conversation,
    contact,
    inbox,
    canal,
    ia_team,
    bot_mode,
    message_content: str,
    button_id=None,
):
    """Espelha regras de supressão do WhatsApp (coexistence_webhooks)."""
    if bot_mode != 'chatbot':
        return False

    if not getattr(provedor, 'is_active', True):
        logger.info(
            '[InstagramWebhook] Chatbot suprimido provedor=%s: inativo (%s)',
            provedor.id,
            getattr(provedor, 'block_reason', ''),
        )
        return False

    if canal and canal.ia_ativa is False:
        logger.info('[InstagramWebhook] Chatbot suprimido canal=%s: ia_ativa=False', canal.id)
        return False

    automacao_agendada = verificar_automacao_agendada(provedor)
    if not automacao_agendada.get('ativa', True):
        logger.info(
            '[InstagramWebhook] Chatbot suprimido por agenda automática provedor=%s modo=%s motivo=%s',
            provedor.id,
            automacao_agendada.get('modo'),
            automacao_agendada.get('motivo'),
        )
        try:
            from conversations.inbound_routing import encaminhar_quando_automacao_desligada
            from core.chatbot_engine import ChatbotEngine
            route = encaminhar_quando_automacao_desligada(
                provedor, conversation, automacao_agendada
            )
            if route.get('encaminhado') and route.get('primeira_vez') and route.get('aviso'):
                ChatbotEngine.send_message_agnostic_sync(conversation, route['aviso'])
        except Exception as route_err:
            logger.warning(
                '[InstagramWebhook] Falha ao encaminhar fallback de automação conv=%s: %s',
                getattr(conversation, 'id', None),
                route_err,
            )
        return False

    from conversations.inbound_routing import reopen_conversation_for_bot

    if reopen_conversation_for_bot(
        conversation,
        ia_team=ia_team,
        provedor=provedor,
        allow_closing_reopen=True,
    ):
        conversation.refresh_from_db()

    is_assigned = conversation.assignee_id is not None
    is_human_queue = bool(getattr(conversation, 'waiting_for_agent', False))
    is_active_agent_status = conversation.status in (
        'open',
        'closed',
        'closing',
        'resolved',
        'finalizada',
        'encerrada',
    )
    if is_assigned or is_human_queue or is_active_agent_status:
        logger.info(
            '[InstagramWebhook] Chatbot suprimido conv=%s assignee=%s waiting=%s status=%s',
            conversation.id,
            conversation.assignee_id,
            is_human_queue,
            conversation.status,
        )
        return False

    if getattr(contact, 'bloqueado_atender', False):
        logger.info(
            '[InstagramWebhook] Chatbot suprimido conv=%s: contato bloqueado',
            conversation.id,
        )
        return False

    if not (message_content or button_id):
        return False

    try:
        from asgiref.sync import async_to_sync
        from core.chatbot_engine import ChatbotEngine

        async def run_chatbot():
            return await ChatbotEngine.process_message(
                provedor_id=provedor.id,
                conversation_id=conversation.id,
                message_content=message_content or '',
                button_id=button_id,
                canal_id=canal.id,
            )

        result = async_to_sync(run_chatbot)()
        handled = result[0] if isinstance(result, tuple) else result
        if handled:
            logger.info(
                '[InstagramWebhook] Chatbot processou conv=%s: %s',
                conversation.id,
                result[1] if isinstance(result, tuple) else '',
            )
        else:
            logger.warning(
                '[InstagramWebhook] Chatbot não executou nó conv=%s: %s',
                conversation.id,
                result[1] if isinstance(result, tuple) else '',
            )
        return handled
    except Exception as exc:
        logger.error('[InstagramWebhook] Erro ChatbotEngine: %s', exc, exc_info=True)
        return False


def _maybe_invoke_ai(
    *,
    provedor,
    conversation,
    contact,
    canal,
    bot_mode,
    message_content: str,
    reply_to_mid=None,
    sender_id=None,
):
    """Chama o agente de IA (chave do provedor) e responde no Instagram."""
    # Modo controlado pelo superadmin: só responde em modo IA
    if (bot_mode or '').strip().lower() != 'ia':
        logger.info(
            '[InstagramWebhook] IA suprimida provedor=%s bot_mode=%s',
            getattr(provedor, 'id', None),
            bot_mode,
        )
        return False

    if not (message_content or '').strip():
        return False

    if not getattr(provedor, 'is_active', True):
        logger.info(
            '[InstagramWebhook] IA suprimida provedor=%s: inativo (%s)',
            provedor.id,
            getattr(provedor, 'block_reason', ''),
        )
        return False

    if canal and canal.ia_ativa is False:
        logger.info('[InstagramWebhook] IA suprimida canal=%s: ia_ativa=False', canal.id)
        return False

    automacao_agendada = verificar_automacao_agendada(provedor)
    if not automacao_agendada.get('ativa', True):
        logger.info(
            '[InstagramWebhook] IA suprimida por agenda automática provedor=%s modo=%s motivo=%s',
            provedor.id,
            automacao_agendada.get('modo'),
            automacao_agendada.get('motivo'),
        )
        try:
            from conversations.inbound_routing import encaminhar_quando_automacao_desligada
            from core.chatbot_engine import ChatbotEngine
            route = encaminhar_quando_automacao_desligada(
                provedor, conversation, automacao_agendada
            )
            if route.get('encaminhado') and route.get('primeira_vez') and route.get('aviso'):
                ChatbotEngine.send_message_agnostic_sync(conversation, route['aviso'])
        except Exception as route_err:
            logger.warning(
                '[InstagramWebhook] Falha ao encaminhar fallback de automação (IA) conv=%s: %s',
                getattr(conversation, 'id', None),
                route_err,
            )
        return False

    conversation.refresh_from_db()
    if conversation.assignee_id or conversation.status in (
        'pending', 'closed', 'closing', 'resolved', 'finalizada', 'encerrada',
    ):
        logger.info(
            '[InstagramWebhook] IA ignorada conv=%s assignee=%s status=%s',
            conversation.id,
            conversation.assignee_id,
            conversation.status,
        )
        return False

    if getattr(conversation, 'waiting_for_agent', False):
        logger.info('[InstagramWebhook] IA ignorada conv=%s: waiting_for_agent', conversation.id)
        return False

    if getattr(contact, 'bloqueado_atender', False):
        logger.info('[InstagramWebhook] IA ignorada conv=%s: contato bloqueado', conversation.id)
        return False

    from ai.providers.config import get_provedor_openai_api_key
    if not get_provedor_openai_api_key(provedor):
        logger.warning(
            '[InstagramWebhook] IA sem chave configurada provedor=%s. '
            'Configure em Integrações → Agente de IA.',
            provedor.id,
        )
        return False

    recipient_id = str(
        sender_id
        or (contact.additional_attributes or {}).get('instagram_scoped_id')
        or contact.phone
        or ''
    )
    if not recipient_id:
        logger.warning('[InstagramWebhook] IA sem recipient IGSID conv=%s', conversation.id)
        return False

    def _run():
        try:
            _call_ai_and_respond_instagram(
                conversation=conversation,
                contact=contact,
                provedor=provedor,
                canal=canal,
                content=message_content.strip(),
                recipient_igsid=recipient_id,
                reply_to_mid=reply_to_mid,
            )
        except Exception as exc:
            logger.error(
                '[InstagramWebhook] Erro na thread da IA conv=%s: %s',
                conversation.id,
                exc,
                exc_info=True,
            )

    threading.Thread(target=_run, daemon=True).start()
    logger.info('[InstagramWebhook] Thread da IA iniciada conv=%s', conversation.id)
    return True


def _call_ai_and_respond_instagram(
    *,
    conversation,
    contact,
    provedor,
    canal,
    content: str,
    recipient_igsid: str,
    reply_to_mid=None,
):
    from ai.response_formatter import AIResponseFormatter
    from ai.service import openai_service
    from core.redis_memory_service import redis_memory_service
    from integrations.instagram_send import send_instagram_text

    conversation.refresh_from_db()
    if conversation.assignee_id or conversation.status in (
        'pending', 'closed', 'closing', 'resolved', 'finalizada', 'encerrada',
    ):
        logger.info(
            '[InstagramWebhook] IA abortada (estado mudou) conv=%s status=%s assignee=%s',
            conversation.id,
            conversation.status,
            conversation.assignee_id,
        )
        return

    contexto = {
        'conversation': conversation,
        'contact': contact,
        'canal': 'instagram',
        'provedor_id': provedor.id,
        'conversation_id': conversation.id,
        'contact_phone': contact.phone,
    }

    ia_result = openai_service.generate_response_sync(
        mensagem=content,
        provedor=provedor,
        contexto=contexto,
    )

    if not ia_result.get('success'):
        motivo = ia_result.get('motivo', ia_result.get('erro', 'desconhecido'))
        if motivo == 'IA_BUSY':
            logger.info('[InstagramWebhook] IA já em execução conv=%s', conversation.id)
        else:
            logger.warning('[InstagramWebhook] Falha na IA conv=%s: %s', conversation.id, motivo)
        return

    resposta_ia = (ia_result.get('resposta') or '').strip()
    if not resposta_ia:
        logger.warning('[InstagramWebhook] IA retornou resposta vazia conv=%s', conversation.id)
        return

    formatter = AIResponseFormatter()
    resposta_ia = formatter.remover_exposicao_funcoes(resposta_ia)
    # Instagram não usa markdown de negrito do WhatsApp
    resposta_ia = re.sub(r'\*\*([^*]+?)\*\*', r'\1', resposta_ia)
    resposta_ia = re.sub(r'\*([^*]+?)\*', r'\1', resposta_ia)

    try:
        import time
        delay = min(max(len(resposta_ia) / 60, 1.0), 4.0)
        time.sleep(delay)
    except Exception:
        pass

    # Não usar reply_to: a API do Instagram rejeita com subcode 2534002 em vários casos.
    ok, response_data, err = send_instagram_text(
        canal,
        recipient_igsid,
        resposta_ia,
        reply_to_mid=None,
    )
    if not ok and reply_to_mid:
        # Fallback explícito (caso algum caminho ainda passe mid)
        logger.warning(
            '[InstagramWebhook] Retry sem reply_to conv=%s (erro anterior: %s)',
            conversation.id,
            err,
        )
        ok, response_data, err = send_instagram_text(
            canal,
            recipient_igsid,
            resposta_ia,
            reply_to_mid=None,
        )
    if not ok:
        logger.error(
            '[InstagramWebhook] Falha ao enviar resposta IA conv=%s: %s',
            conversation.id,
            err,
        )
        return

    external_id = None
    if isinstance(response_data, dict):
        external_id = (
            response_data.get('message_id')
            or (response_data.get('messages') or [{}])[0].get('id')
        )

    Message.objects.create(
        conversation=conversation,
        content=resposta_ia,
        message_type='text',
        is_from_customer=False,
        external_id=external_id,
        additional_attributes={
            'is_ai_response': True,
            'from_ai': True,
            'ai_conversation_id': ia_result.get('ai_conversation_id'),
            'source': 'instagram_messaging',
        },
    )

    try:
        redis_memory_service.add_message_to_conversation_sync(
            provedor_id=provedor.id,
            conversation_id=conversation.id,
            sender='ai',
            content=resposta_ia,
            channel='instagram',
            phone=contact.phone,
        )
    except Exception as exc:
        logger.warning('[InstagramWebhook] Falha ao gravar memória Redis: %s', exc)

    # Se a IA transferiu (pending = Em Espera para equipe), não reverter para snoozed
    conversation.refresh_from_db(fields=['status', 'assignee_id'])
    if conversation.status not in (
        'pending', 'closed', 'closing', 'resolved', 'finalizada', 'encerrada',
    ) and not conversation.assignee_id and conversation.status != 'snoozed':
        conversation.status = 'snoozed'
        conversation.save(update_fields=['status'])

    logger.info(
        '[InstagramWebhook] IA respondeu conv=%s ai_id=%s status=%s',
        conversation.id,
        ia_result.get('ai_conversation_id'),
        conversation.status,
    )


def _process_instagram_postback_event(
    event, ig_account_id, canal, provedor, inbox, ia_team, bot_mode
):
    postback = event.get('postback') or {}
    sender_id = (event.get('sender') or {}).get('id')
    if not sender_id:
        return

    if str(sender_id) in _business_ids(ig_account_id, canal):
        return

    mid = postback.get('mid')
    if mid and Message.objects.filter(external_id=str(mid)).exists():
        return

    payload = (postback.get('payload') or '').strip()
    title = (postback.get('title') or payload or 'Botão').strip()
    if not payload and not title:
        return

    contact, conversation = _get_or_create_contact_conversation(
        sender_id, provedor, inbox, ia_team, canal
    )

    ts = _timestamp_to_aware(event.get('timestamp'))
    attrs = {
        'source': 'instagram_messaging',
        'instagram_user_id': ig_account_id,
        'sender_id': str(sender_id),
        'is_postback': True,
        'button_id': payload or None,
        'button_title': title,
    }

    Message.objects.create(
        conversation=conversation,
        content=title,
        message_type='text',
        is_from_customer=True,
        external_id=str(mid) if mid else None,
        created_at=ts,
        additional_attributes=attrs,
    )

    conversation.last_message_at = ts
    conversation.last_user_message_at = ts
    conversation.save(update_fields=['last_message_at', 'last_user_message_at'])

    logger.info(
        '[InstagramWebhook] Postback recebido conv=%s payload=%s title=%s',
        conversation.id,
        payload,
        title,
    )

    if _maybe_process_csat(conversation, contact, title, button_id=payload):
        return

    chatbot_handled = _maybe_invoke_chatbot(
        provedor=provedor,
        conversation=conversation,
        contact=contact,
        inbox=inbox,
        canal=canal,
        ia_team=ia_team,
        bot_mode=bot_mode,
        message_content=title,
        button_id=payload or None,
    )
    if not chatbot_handled:
        _maybe_invoke_ai(
            provedor=provedor,
            conversation=conversation,
            contact=contact,
            canal=canal,
            bot_mode=bot_mode,
            message_content=title or payload or '',
            reply_to_mid=mid,
            sender_id=sender_id,
        )


def _process_single_messaging_event(event, ig_account_id, canal, provedor, inbox, ia_team, bot_mode):
    message = event.get('message') or {}
    if isinstance(message, str):
        message = {'text': message, 'mid': event.get('mid')}
    if event.get('text') and not message.get('text'):
        message = {**message, 'text': event.get('text')}
    if message.get('is_echo'):
        return
    if message.get('is_deleted'):
        return

    sender_id = (event.get('sender') or {}).get('id')
    if not sender_id:
        return

    if str(sender_id) in _business_ids(ig_account_id, canal):
        return

    mid = message.get('mid')
    if mid and Message.objects.filter(external_id=mid).exists():
        return

    text = (message.get('text') or '').strip()
    attachments = message.get('attachments') or []

    contact, conversation = _get_or_create_contact_conversation(
        sender_id, provedor, inbox, ia_team, canal
    )

    if attachments:
        message_type, att_content, file_url, att_attrs = _parse_attachments(
            attachments,
            conversation.id,
            mid,
        )
        content = text or att_content
    else:
        message_type = 'text'
        file_url = None
        att_attrs = {}
        content = text

    if not content and not file_url:
        return

    ts = _timestamp_to_aware(event.get('timestamp'))
    attrs = {
        'source': 'instagram_messaging',
        'instagram_user_id': ig_account_id,
        'sender_id': str(sender_id),
        **att_attrs,
    }

    reply_to = message.get('reply_to') or {}
    reply_mid = reply_to.get('mid')
    if reply_mid:
        attrs['is_reply'] = True
        attrs['reply_to_external_id'] = str(reply_mid)
        original = Message.objects.filter(
            external_id=str(reply_mid),
            conversation=conversation,
        ).first()
        if original:
            attrs['reply_to_message_id'] = original.id
            attrs['reply_to_content'] = original.content
        else:
            attrs['reply_to_message_id'] = str(reply_mid)

    Message.objects.create(
        conversation=conversation,
        content=content,
        message_type=message_type,
        is_from_customer=True,
        external_id=mid,
        file_url=file_url,
        created_at=ts,
        additional_attributes=attrs,
    )

    if (
        file_url
        and message_type in ('audio', 'ptt', 'image', 'video')
        and provedor
    ):
        try:
            from ai.media_inbound import enrich_inbound_media_for_ai, resolve_media_file_path

            media_path = resolve_media_file_path(file_url, conversation.id)
            ai_text, media_extra = enrich_inbound_media_for_ai(
                provedor,
                message_type,
                media_path,
                caption=content or '',
            )
            if media_extra:
                attrs.update(media_extra)
            if ai_text:
                content = ai_text
                db_content = (text or '').strip() or ai_text
                Message.objects.filter(
                    conversation=conversation,
                    external_id=mid,
                ).update(
                    content=db_content,
                    additional_attributes=attrs,
                )
        except Exception as media_ai_err:
            logger.warning(
                '[InstagramWebhook] Falha ao preparar mídia para IA conv=%s: %s',
                conversation.id,
                media_ai_err,
            )

    conversation.last_message_at = ts
    conversation.last_user_message_at = ts
    conversation.save(update_fields=['last_message_at', 'last_user_message_at'])

    logger.info(
        '[InstagramWebhook] Mensagem recebida conversa=%s tipo=%s canal=%s sender=%s',
        conversation.id,
        message_type,
        canal.id,
        sender_id,
    )

    if _maybe_process_csat(conversation, contact, text or content):
        return

    chatbot_handled = _maybe_invoke_chatbot(
        provedor=provedor,
        conversation=conversation,
        contact=contact,
        inbox=inbox,
        canal=canal,
        ia_team=ia_team,
        bot_mode=bot_mode,
        message_content=text or content,
        button_id=None,
    )
    # Modo IA, ou chatbot sem fluxo: responde com o agente de IA do provedor.
    if not chatbot_handled:
        _maybe_invoke_ai(
            provedor=provedor,
            conversation=conversation,
            contact=contact,
            canal=canal,
            bot_mode=bot_mode,
            message_content=text or content,
            reply_to_mid=mid,
            sender_id=sender_id,
        )
