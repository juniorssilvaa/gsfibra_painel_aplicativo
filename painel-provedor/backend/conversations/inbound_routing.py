"""
Roteamento de conversas em mensagens inbound (reabertura para bot após encerramento/CSAT).
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

CLOSED_STATUSES = frozenset(['closed', 'resolved', 'finalizada', 'encerrada'])


def sync_csat_request_if_feedback_exists(conversation) -> bool:
    """
    Corrige CSATRequest preso em sent/pending quando já existe CSATFeedback.
    Retorna True se algum request foi atualizado.

    csat_feedback é OneToOne: só um CSATRequest pode apontar para o mesmo feedback.
    """
    from django.db import IntegrityError, transaction
    from conversations.models import CSATRequest, CSATFeedback

    feedback = CSATFeedback.objects.filter(conversation=conversation).order_by('-id').first()
    if not feedback:
        return False

    pending_qs = CSATRequest.objects.filter(
        conversation=conversation,
        status__in=['sent', 'pending'],
    )
    if not pending_qs.exists():
        return False

    now = timezone.now()
    updated = 0

    try:
        with transaction.atomic():
            # Feedback já ligado a algum request (mesmo de outra conversa/status)
            linked = CSATRequest.objects.filter(csat_feedback=feedback).first()

            if linked:
                # Só fecha status dos pendentes — sem reatribuir o FK único
                if linked.status in ('sent', 'pending'):
                    linked.status = 'responded'
                    linked.responded_at = now
                    linked.save(update_fields=['status', 'responded_at', 'updated_at'])
                    updated += 1
                extra = pending_qs.exclude(pk=linked.pk).update(
                    status='responded',
                    responded_at=now,
                )
                updated += extra
            else:
                # Liga o feedback só ao request mais recente; demais sem FK
                latest = pending_qs.order_by('-id').first()
                latest.status = 'responded'
                latest.responded_at = now
                latest.csat_feedback = feedback
                latest.save(update_fields=[
                    'status', 'responded_at', 'csat_feedback', 'updated_at',
                ])
                updated += 1
                extra = pending_qs.exclude(pk=latest.pk).update(
                    status='responded',
                    responded_at=now,
                )
                updated += extra
    except IntegrityError:
        # Corrida / FK já ocupado: fecha pendentes sem tocar em csat_feedback
        logger.warning(
            '[InboundRouting] IntegrityError ao sincronizar CSAT conv=%s — fechando sem FK',
            conversation.id,
            exc_info=True,
        )
        updated = CSATRequest.objects.filter(
            conversation=conversation,
            status__in=['sent', 'pending'],
        ).update(status='responded', responded_at=now)

    if updated:
        logger.info(
            '[InboundRouting] CSATRequest(s) sincronizado(s) para responded — conv=%s count=%s',
            conversation.id,
            updated,
        )
    return bool(updated)


def has_blocking_csat(conversation) -> bool:
    """CSAT ainda aguardando resposta do cliente (nesta conversa ou no contato)."""
    from conversations.models import CSATRequest

    try:
        sync_csat_request_if_feedback_exists(conversation)
    except Exception:
        # Nunca bloquear inbound por falha de sincronização de CSAT
        logger.exception(
            '[InboundRouting] Falha ao sincronizar CSAT na conversa %s',
            getattr(conversation, 'id', None),
        )
    if CSATRequest.objects.filter(
        conversation=conversation,
        status__in=['sent', 'pending'],
    ).exists():
        return True
    contact = getattr(conversation, 'contact', None)
    if not contact:
        return False
    return CSATRequest.objects.filter(
        contact=contact,
        status__in=['sent', 'pending'],
    ).exists()


def reopen_conversation_for_bot(
    conversation,
    *,
    ia_team=None,
    provedor=None,
    allow_closing_reopen: bool = False,
) -> bool:
    """
    Reabre conversa encerrada para novo ciclo do chatbot.
    Não reabre se ainda há CSAT aguardando resposta.
    Estado `closing` só reabre com allow_closing_reopen=True (mensagem/postback do cliente).
    """
    if conversation.status == 'closing':
        if not allow_closing_reopen:
            return False
        from conversations.closing_service import closing_service

        if not closing_service.should_reopen(conversation):
            return False
    elif conversation.status not in CLOSED_STATUSES:
        return False

    if has_blocking_csat(conversation):
        logger.info(
            '[InboundRouting] Conversa %s não reaberta: CSAT pendente',
            conversation.id,
        )
        return False

    from conversations.message_visibility import mark_conversation_new_bot_session

    now = timezone.now()
    mark_conversation_new_bot_session(conversation)

    # Chatbot → pending (aparece em Espera + Automação).
    # IA → snoozed (controle do agente IA).
    bot_mode = 'ia'
    if provedor is not None:
        bot_mode = (getattr(provedor, 'bot_mode', None) or 'ia').strip().lower()
    else:
        try:
            inbox = getattr(conversation, 'inbox', None)
            prov = getattr(inbox, 'provedor', None) if inbox else None
            if prov is not None:
                bot_mode = (getattr(prov, 'bot_mode', None) or 'ia').strip().lower()
        except Exception:
            bot_mode = 'ia'

    conversation.status = 'snoozed' if bot_mode == 'ia' else 'pending'
    conversation.assignee = None
    conversation.waiting_for_agent = False
    conversation.team = ia_team
    conversation.closing_requested_at = None
    conversation.updated_at = now
    conversation.save(update_fields=[
        'status', 'team', 'assignee', 'waiting_for_agent',
        'additional_attributes', 'closing_requested_at', 'updated_at',
    ])

    if provedor:
        try:
            from asgiref.sync import async_to_sync
            from core.redis_memory_service import redis_memory_service

            phone = getattr(getattr(conversation, 'contact', None), 'phone', None) or 'unknown'
            channel = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
            async_to_sync(redis_memory_service.clear_memory)(
                provedor.id, conversation.id, channel, phone
            )
        except Exception as e:
            logger.warning(
                '[InboundRouting] Falha ao limpar memória do bot na reabertura conv=%s: %s',
                conversation.id,
                e,
            )

    try:
        from conversations.protocol_service import ensure_niohub_protocol

        # Novo ciclo de atendimento → novo protocolo NioHub
        ensure_niohub_protocol(conversation, force_new=True, create_system_message=True)
    except Exception as e:
        logger.warning(
            '[InboundRouting] Falha ao renovar protocolo na reabertura conv=%s: %s',
            conversation.id,
            e,
        )

    logger.info(
        '[InboundRouting] Conversa %s reaberta para bot (status=%s, bot_mode=%s)',
        conversation.id,
        conversation.status,
        bot_mode,
    )
    return True


def encaminhar_quando_automacao_desligada(provedor, conversation, automacao_info=None) -> dict:
    """
    No modo "dentro do horário comercial", quando a IA/chatbot está desligada pela agenda,
    envia a conversa para a equipe de fallback configurada e monta aviso ao cliente.

    Retorna dict com:
      - encaminhado: bool
      - primeira_vez: bool (True se acabou de colocar na fila — enviar aviso ao cliente)
      - aviso: str (texto sugerido ao cliente)
      - team: Team | None
      - motivo: str
    """
    from core.horario_utils import (
        formatar_aviso_transferencia_fora_horario,
        verificar_automacao_agendada,
    )
    from core.agent_alert_notify import notify_agents_waiting_alert

    result = {
        'encaminhado': False,
        'primeira_vez': False,
        'aviso': '',
        'team': None,
        'motivo': '',
    }

    if not provedor or not conversation:
        result['motivo'] = 'params'
        return result

    info = automacao_info if isinstance(automacao_info, dict) else verificar_automacao_agendada(provedor)
    if info.get('ativa', True):
        result['motivo'] = 'automacao_ativa'
        return result

    modo = (info.get('modo') or getattr(provedor, 'automation_schedule_mode', '') or '').strip().lower()
    if modo != 'inside_business_hours':
        result['motivo'] = 'modo_nao_aplica'
        return result

    if conversation.assignee_id:
        result['motivo'] = 'ja_atribuida'
        return result

    team = getattr(provedor, 'automation_schedule_fallback_team', None)
    if team is None:
        team_id = getattr(provedor, 'automation_schedule_fallback_team_id', None)
        if team_id:
            from conversations.models import Team
            team = Team.objects.filter(id=team_id, provedor=provedor, is_active=True).first()

    if not team:
        result['motivo'] = 'equipe_nao_configurada'
        return result

    ja_na_fila = bool(
        getattr(conversation, 'waiting_for_agent', False)
        and getattr(conversation, 'team_id', None) == team.id
    )

    horario_info = info.get('horario_info') or {}
    setor = team.name
    aviso = formatar_aviso_transferencia_fora_horario(horario_info, setor=setor).strip()
    if not aviso:
        aviso = (
            f'No momento nossa automação está desligada. '
            f'Sua mensagem foi encaminhada para a equipe *{setor}*, '
            f'que falará com você assim que possível.'
        )
    else:
        aviso = (
            f'Sua mensagem foi encaminhada para a equipe *{setor}*.\n\n{aviso}'
        )

    if not ja_na_fila:
        conversation.status = 'pending'
        conversation.assignee = None
        conversation.waiting_for_agent = True
        conversation.team = team
        attrs = conversation.additional_attributes or {}
        attrs['assigned_team'] = {'id': team.id, 'name': team.name}
        attrs['automation_fallback_routed'] = True
        conversation.additional_attributes = attrs
        conversation.save()

        try:
            notify_agents_waiting_alert(
                provedor,
                conversation,
                team=team,
                motivo='Automação desligada por horário — atendimento encaminhado',
            )
        except Exception as alert_err:
            logger.warning(
                '[InboundRouting] Falha ao notificar equipe fallback conv=%s: %s',
                conversation.id,
                alert_err,
            )

        result['primeira_vez'] = True
        logger.info(
            '[InboundRouting] Conversa %s encaminhada para equipe fallback %s (automação off)',
            conversation.id,
            team.id,
        )
    else:
        result['motivo'] = 'ja_na_fila'

    result['encaminhado'] = True
    result['team'] = team
    result['aviso'] = aviso
    if not result['motivo']:
        result['motivo'] = 'ok'
    return result
