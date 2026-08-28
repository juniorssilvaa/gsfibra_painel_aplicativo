"""Tools NioHub — faturas Asaas (modo suporte da plataforma)."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _phone_from_contexto(contexto) -> str:
    if not contexto or not isinstance(contexto, dict):
        return "unknown"
    contact = contexto.get("contact")
    if contact is not None:
        phone = getattr(contact, "phone", None)
        if phone:
            return str(phone)
    return str(contexto.get("contact_phone") or "unknown")


def _conversation_from_contexto(contexto, conversation_id):
    if contexto and isinstance(contexto, dict):
        conv = contexto.get("conversation")
        if conv is not None:
            return conv
    if not conversation_id:
        return None
    try:
        from conversations.models import Conversation

        return Conversation.objects.filter(pk=conversation_id).first()
    except Exception:
        return None


def buscar_faturas_asaas(*, provedor, arguments, contexto, conversation_id, **_kw) -> Dict[str, Any]:
    """Lista cobranças Asaas do provedor pelo CPF/CNPJ."""
    from integrations.asaas_support_fatura import buscar_faturas_por_cpf_cnpj

    args = arguments or {}
    cpf = args.get("cpf_cnpj") or args.get("cpf") or args.get("cnpj")
    customer_id = args.get("customer_id") or args.get("asaas_customer_id")
    incluir_pagas = bool(args.get("incluir_pagas") or False)
    result = buscar_faturas_por_cpf_cnpj(
        cpf,
        customer_id=customer_id,
        incluir_pagas=incluir_pagas,
    )
    if result.get("success") and conversation_id and cpf:
        try:
            from core.redis_memory_service import redis_memory_service

            phone = _phone_from_contexto(contexto)
            channel = "wa"
            if contexto and isinstance(contexto, dict):
                channel = contexto.get("channel") or "wa"
            redis_memory_service.update_ai_state_sync(
                provedor.id,
                conversation_id,
                {
                    "asaas_cpf_cnpj": "".join(ch for ch in str(cpf) if ch.isdigit()),
                    "asaas_customer_id": (result.get("cliente") or {}).get("id"),
                },
                channel,
                phone,
            )
        except Exception:
            logger.debug("[buscar_faturas_asaas] Falha ao gravar estado Redis", exc_info=True)
    return result


def enviar_fatura_asaas(*, provedor, arguments, contexto, conversation_id, **_kw) -> Dict[str, Any]:
    """Envia cobrança Asaas (PIX/boleto) na conversa atual."""
    from integrations.asaas_support_fatura import enviar_fatura_asaas as _enviar

    args = arguments or {}
    payment_id = args.get("payment_id") or args.get("fatura_id") or args.get("id")
    tipo = (args.get("tipo_pagamento") or "ambos").strip().lower()
    cpf = args.get("cpf_cnpj")
    phone = _phone_from_contexto(contexto)
    conv = _conversation_from_contexto(contexto, conversation_id)

    # Idempotência leve
    try:
        from core.redis_memory_service import redis_memory_service

        channel = "wa"
        if contexto and isinstance(contexto, dict):
            channel = contexto.get("channel") or "wa"
        state = {}
        if conversation_id:
            state = redis_memory_service.get_ai_state_sync(
                provedor.id, conversation_id, channel, phone
            ) or {}
        if state.get("asaas_fatura_enviada") and str(state.get("asaas_fatura_enviada_id") or "") == str(
            payment_id or ""
        ):
            return {
                "success": True,
                "enviada": True,
                "ja_enviada": True,
                "payment_id": payment_id,
                "nota": "Esta fatura Asaas já foi enviada nesta conversa. Confirme ao provedor sem reenviar.",
            }
        if not cpf:
            cpf = state.get("asaas_cpf_cnpj")
    except Exception:
        state = {}

    result = _enviar(
        provedor,
        payment_id=payment_id,
        phone=phone,
        conversation=conv,
        tipo_pagamento=tipo,
        cpf_cnpj=cpf,
    )
    if result.get("success") and conversation_id:
        try:
            from core.redis_memory_service import redis_memory_service

            channel = "wa"
            if contexto and isinstance(contexto, dict):
                channel = contexto.get("channel") or "wa"
            redis_memory_service.update_ai_state_sync(
                provedor.id,
                conversation_id,
                {
                    "asaas_fatura_enviada": True,
                    "asaas_fatura_enviada_id": str(payment_id),
                },
                channel,
                phone,
            )
        except Exception:
            logger.debug("[enviar_fatura_asaas] Falha ao gravar estado Redis", exc_info=True)
    return result
