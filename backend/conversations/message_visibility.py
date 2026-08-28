"""
Visibilidade de mensagens para atendentes: após voltar ao fluxo do bot,
histórico anterior ao marco agent_chat_visible_from não é listado no painel
(exceto com for_audit=1 por admin/superadmin na aba de auditoria).
"""
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _user_has_permission(user, *permission_keys):
    user_permissions = getattr(user, "permissions", [])
    if not isinstance(user_permissions, list):
        return False
    return any(key in user_permissions for key in permission_keys)


def is_unassigned_waiting_conversation(conversation):
    """Fila de espera humana: aguardando atendente e sem assignee no modelo."""
    return bool(
        getattr(conversation, "waiting_for_agent", False)
        and getattr(conversation, "assignee_id", None) is None
    )


def waiting_queue_content_redacted_for_agent(request, conversation):
    """
    Atendente sem permissão não deve ver conteúdo (lista, histórico, WS) até a conversa ser atribuída.
    Admins/superadmin não são afetados.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "user_type", None) != "agent":
        return False
    if not is_unassigned_waiting_conversation(conversation):
        return False
    return not _user_has_permission(
        user,
        "view_waiting_history_before_assignment",
    )


def mark_conversation_new_bot_session(conversation):
    """
    Reabertura para o bot na MESMA conversa: marca corte para o painel e zera
    chatbot_memory (evita IA repetir confirmação de transferência / fila do ciclo anterior).
    """
    if conversation is None:
        return
    attrs = dict(conversation.additional_attributes or {})
    attrs["agent_chat_visible_from"] = timezone.now().isoformat()
    attrs.pop("chatbot_memory", None)
    for stale in ("assigned_team", "assigned_user", "transfer_decision", "pending_transfer"):
        attrs.pop(stale, None)
    conversation.additional_attributes = attrs


def apply_agent_message_visibility_filter(queryset, conversation, request):
    """
    Restringe o queryset de mensagens ao período visível para o painel.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return queryset

    for_audit = request.query_params.get("for_audit") in ("1", "true", "True", "yes")
    if for_audit and getattr(user, "user_type", None) in ("superadmin", "admin"):
        return queryset

    # Em fila de espera sem atribuição: atendente sem permissão não vê nenhuma mensagem
    # até assumir (evita conteúdo de cliente/bot na fila).
    if waiting_queue_content_redacted_for_agent(request, conversation):
        return queryset.none()

    attrs = getattr(conversation, "additional_attributes", None) or {}
    cutoff_iso = attrs.get("agent_chat_visible_from")
    if not cutoff_iso:
        return queryset

    dt = parse_datetime(str(cutoff_iso))
    if not dt:
        return queryset
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    return queryset.filter(created_at__gte=dt)
