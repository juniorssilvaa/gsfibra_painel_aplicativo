"""Utilitários para nome de contato (WhatsApp genérico vs nome real do SGP)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_GENERIC_NAME_RE = re.compile(r'^Cliente\s+\d{6,}$', re.I)

def is_generic_contact_name(name: Optional[str]) -> bool:
    """True para placeholders como 'Cliente 81419938', telefone puro ou vazio."""
    if not name or not str(name).strip():
        return True
    n = str(name).strip()
    if n in ('Cliente', 'Cliente WhatsApp', 'Contato Desconhecido'):
        return True
    if _GENERIC_NAME_RE.match(n):
        return True
    digits = re.sub(r'\D', '', n)
    if digits and len(digits) >= 10 and digits == re.sub(r'\D', '', n):
        return True
    return False


def normalize_sgp_contact_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = str(name).strip()
    if len(n) < 3 or n.lower() == 'cliente':
        return None
    return n[:255]


def extract_sgp_client_name(sgp_res: Dict[str, Any]) -> Optional[str]:
    """Extrai razaoSocial/nome do JSON retornado pelo SGP."""
    if not isinstance(sgp_res, dict):
        return None
    for key in ('razaoSocial', 'nome', 'nomeCliente'):
        val = sgp_res.get(key)
        if val and isinstance(val, str) and val.strip():
            return normalize_sgp_contact_name(val.strip())
    cliente = sgp_res.get('cliente')
    if isinstance(cliente, dict):
        for key in ('razaoSocial', 'nome', 'nomeCliente'):
            val = cliente.get(key)
            if val and isinstance(val, str) and val.strip():
                return normalize_sgp_contact_name(val.strip())
    contratos = sgp_res.get('contratos') or []
    if contratos and isinstance(contratos[0], dict):
        val = contratos[0].get('razaoSocial') or contratos[0].get('nomeCliente') or contratos[0].get('nome')
        if val and isinstance(val, str) and val.strip():
            return normalize_sgp_contact_name(val.strip())
    return None


def maybe_update_contact_whatsapp_name(contact, wa_name: str) -> bool:
    """Atualiza nome do WhatsApp quando o CRM ainda tem placeholder genérico."""
    nome = str(wa_name or '').strip()[:255]
    if not contact or not nome or is_generic_contact_name(nome):
        return False
    atual = str(getattr(contact, 'name', '') or '').strip()
    if atual == nome or not is_generic_contact_name(atual):
        return False
    contact.name = nome
    contact.save(update_fields=['name'])
    return True


def maybe_update_contact_from_sgp(
    contact,
    sgp_name: str,
    cpf_cnpj: str = '',
    *,
    conversation_id: Optional[int] = None,
    provedor_id: Optional[int] = None,
) -> bool:
    """Grava nome real do titular (SGP) e CPF/CNPJ no contato após consulta."""
    nome = normalize_sgp_contact_name(sgp_name)
    if not contact or not nome:
        return False

    update_fields = []
    attrs = dict(contact.additional_attributes or {}) if isinstance(contact.additional_attributes, dict) else {}
    cpf_digits = re.sub(r'\D', '', str(cpf_cnpj or ''))

    atual = str(getattr(contact, 'name', '') or '').strip()
    if atual != nome:
        contact.name = nome
        update_fields.append('name')

    if attrs.get('sgp_name') != nome:
        attrs['sgp_name'] = nome
    if cpf_digits:
        if attrs.get('document') != cpf_digits:
            attrs['document'] = cpf_digits
        if attrs.get('cpf_cnpj') != cpf_digits:
            attrs['cpf_cnpj'] = cpf_digits
        if attrs.get('sgp_document') != cpf_digits:
            attrs['sgp_document'] = cpf_digits

    if attrs != (contact.additional_attributes or {}):
        contact.additional_attributes = attrs
        if 'additional_attributes' not in update_fields:
            update_fields.append('additional_attributes')

    if not update_fields:
        return False

    contact.save(update_fields=update_fields)
    logger.info(
        '[ContactName] contato %s atualizado via SGP: "%s" -> "%s" (conv=%s)',
        contact.id,
        atual,
        nome,
        conversation_id,
    )

    _notify_contact_name_updated(
        contact=contact,
        conversation_id=conversation_id,
        provedor_id=provedor_id or getattr(contact, 'provedor_id', None),
    )
    return True


def update_contact_from_sgp_by_id(
    contact_id: int,
    sgp_name: str,
    cpf_cnpj: str = '',
    *,
    conversation_id: Optional[int] = None,
    provedor_id: Optional[int] = None,
) -> bool:
    """Recarrega o contato no thread sync antes de gravar (seguro em async)."""
    from conversations.models import Contact

    contact = Contact.objects.filter(pk=contact_id).first()
    if not contact:
        return False
    return maybe_update_contact_from_sgp(
        contact,
        sgp_name,
        cpf_cnpj,
        conversation_id=conversation_id,
        provedor_id=provedor_id,
    )


def _notify_contact_name_updated(
    contact,
    conversation_id: Optional[int] = None,
    provedor_id: Optional[int] = None,
) -> None:
    try:
        from conversations.models import Conversation
        from conversations.services import ConversationNotificationService

        pid = provedor_id or getattr(contact, 'provedor_id', None)
        if not pid:
            return

        conv_id = conversation_id
        if not conv_id:
            conv_id = (
                Conversation.objects.filter(contact_id=contact.id, inbox__provedor_id=pid)
                .order_by('-updated_at')
                .values_list('id', flat=True)
                .first()
            )
        if not conv_id:
            return

        ConversationNotificationService.notify_conversation_updated(
            int(pid),
            int(conv_id),
            'contact_updated',
            {'contact_id': contact.id, 'contact_name': contact.name},
        )
    except Exception as exc:
        logger.warning('[ContactName] falha ao notificar painel: %s', exc)