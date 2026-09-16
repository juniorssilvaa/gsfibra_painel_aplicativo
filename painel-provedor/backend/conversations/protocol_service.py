"""
Protocolo de atendimento NioHub.

- Ao abrir conversa (ou reabrir ciclo), gera protocolo NioHub.
- Ao abrir chamado no SGP, passa a usar o protocolo do SGP.
- Trocas geram mensagem de sistema no chat (visível aos atendentes).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

ATTR_PROTOCOLO = "protocolo"
ATTR_SOURCE = "protocol_source"
ATTR_SGP_CHAMADO_ID = "sgp_chamado_id"
ATTR_PROTOCOLO_NIOHUB = "protocolo_niohub"
ATTR_PROTOCOLO_ANTERIOR = "protocolo_anterior"


def get_conversation_protocol(conversation) -> Optional[str]:
    attrs = getattr(conversation, "additional_attributes", None) or {}
    value = attrs.get(ATTR_PROTOCOLO)
    return str(value).strip() if value else None


def get_protocol_source(conversation) -> str:
    attrs = getattr(conversation, "additional_attributes", None) or {}
    return str(attrs.get(ATTR_SOURCE) or "niohub").strip().lower()


def _provedor_id(conversation) -> Optional[int]:
    try:
        inbox = getattr(conversation, "inbox", None)
        provedor = getattr(inbox, "provedor", None) if inbox else None
        if provedor is not None:
            return int(provedor.id)
        provedor_id = getattr(inbox, "provedor_id", None) if inbox else None
        return int(provedor_id) if provedor_id else None
    except Exception:
        return None


def generate_niohub_protocol(conversation) -> str:
    """Gera um protocolo numérico único por ciclo de atendimento (sem prefixo NIO)."""
    cid = getattr(conversation, "id", None) or 0
    pid = _provedor_id(conversation) or 0
    stamp = timezone.now().strftime("%y%m%d%H%M%S")
    # Apenas dígitos: provedor + conversa + timestamp
    return f"{pid}{cid}{stamp}"


def _create_system_message(
    conversation,
    *,
    old_protocol: Optional[str],
    new_protocol: str,
    source: str,
) -> None:
    from conversations.models import Message

    if not old_protocol or str(old_protocol) == str(new_protocol):
        return

    Message.objects.create(
        conversation=conversation,
        content=f"Protocolo alterado de {old_protocol} para {new_protocol}",
        message_type="text",
        is_from_customer=False,
        additional_attributes={
            "system_message": True,
            "action": "protocol_changed",
            "protocolo_anterior": old_protocol,
            "protocolo_novo": new_protocol,
            "protocol_source": source,
            "apenas_atendentes": True,
        },
    )


def _notify_conversation_updated(conversation) -> None:
    try:
        provedor_id = _provedor_id(conversation)
        if not provedor_id:
            return
        from conversations.services import ConversationNotificationService

        ConversationNotificationService.notify_conversation_updated(
            provedor_id,
            conversation.id,
            "protocol_updated",
            {
                "protocolo": get_conversation_protocol(conversation),
                "protocol_source": get_protocol_source(conversation),
            },
        )
    except Exception as exc:
        logger.debug("[Protocol] Falha ao notificar update: %s", exc)


def set_conversation_protocol(
    conversation,
    protocolo: str,
    *,
    source: str = "niohub",
    chamado_id: Any = None,
    create_system_message: bool = True,
    notify: bool = True,
) -> dict:
    """
    Define o protocolo atual da conversa.
    Retorna dict com old/new e se mudou.
    """
    protocolo = str(protocolo or "").strip()
    if not protocolo or not conversation:
        return {"changed": False, "protocolo": None}

    attrs = dict(getattr(conversation, "additional_attributes", None) or {})
    old = str(attrs.get(ATTR_PROTOCOLO) or "").strip() or None
    old_source = str(attrs.get(ATTR_SOURCE) or "").strip().lower() or None

    if old == protocolo and old_source == source:
        return {"changed": False, "protocolo": protocolo, "protocolo_anterior": old}

    if source == "niohub":
        attrs[ATTR_PROTOCOLO_NIOHUB] = protocolo
    if old:
        attrs[ATTR_PROTOCOLO_ANTERIOR] = old

    attrs[ATTR_PROTOCOLO] = protocolo
    attrs[ATTR_SOURCE] = source
    if chamado_id is not None:
        attrs[ATTR_SGP_CHAMADO_ID] = chamado_id

    conversation.additional_attributes = attrs
    conversation.save(update_fields=["additional_attributes", "updated_at"])

    # Mensagem de sistema só na troca de número (atendentes veem no chat)
    if create_system_message and old and old != protocolo:
        try:
            _create_system_message(
                conversation,
                old_protocol=old,
                new_protocol=protocolo,
                source=source,
            )
        except Exception as exc:
            logger.warning("[Protocol] Falha ao criar mensagem de sistema: %s", exc)

    if notify:
        _notify_conversation_updated(conversation)

    logger.info(
        "[Protocol] conv=%s %s → %s (source=%s)",
        getattr(conversation, "id", None),
        old,
        protocolo,
        source,
    )
    return {
        "changed": True,
        "protocolo": protocolo,
        "protocolo_anterior": old,
        "protocol_source": source,
    }


def ensure_niohub_protocol(
    conversation,
    *,
    force_new: bool = False,
    create_system_message: bool = False,
) -> Optional[str]:
    """Garante protocolo NioHub na conversa (criação ou novo ciclo)."""
    if not conversation or not getattr(conversation, "id", None):
        return None

    # Canal só de disparo: não gera/renova protocolo para o cliente
    try:
        inbox = getattr(conversation, "inbox", None)
        canal = inbox.get_canal_instance() if inbox and hasattr(inbox, "get_canal_instance") else None
        if canal and getattr(canal, "somente_disparo", False):
            return None
    except Exception:
        pass

    attrs = dict(getattr(conversation, "additional_attributes", None) or {})
    current = str(attrs.get(ATTR_PROTOCOLO) or "").strip()
    source = str(attrs.get(ATTR_SOURCE) or "niohub").strip().lower()

    if not force_new and current:
        return current

    protocolo = generate_niohub_protocol(conversation)
    result = set_conversation_protocol(
        conversation,
        protocolo,
        source="niohub",
        create_system_message=create_system_message and bool(current),
        notify=True,
    )
    return result.get("protocolo")


def format_protocol_update_customer_message(
    protocolo_anterior: Optional[str],
    protocolo_novo: str,
) -> str:
    """
    Mensagem enviada ao cliente quando o protocolo NioHub é substituído
    pelo protocolo do chamado SGP.
    """
    novo = str(protocolo_novo or "").strip()
    anterior = str(protocolo_anterior or "").strip()
    if anterior and anterior != novo:
        return (
            "Devido à abertura do chamado, o número de protocolo do seu atendimento "
            f"foi atualizado.\n\nProtocolo anterior: {anterior}\n"
            f"Novo protocolo: {novo}"
        )
    return (
        "Devido à abertura do chamado, o número de protocolo do seu atendimento "
        f"foi atualizado.\n\nNovo protocolo: {novo}"
    )


def apply_sgp_protocol(
    conversation,
    protocolo_sgp: str,
    *,
    chamado_id: Any = None,
) -> dict:
    """Troca o protocolo atual pelo número do chamado SGP e avisa no chat."""
    if not conversation or not protocolo_sgp:
        return {"changed": False}
    return set_conversation_protocol(
        conversation,
        str(protocolo_sgp).strip(),
        source="sgp",
        chamado_id=chamado_id,
        create_system_message=True,
        notify=True,
    )
