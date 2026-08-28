"""
Notifica um WhatsApp configurado quando a IA (modo support) transfere uma conversa.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _digits_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _build_summary_message(
    *,
    conversa,
    equipe_nome: str,
    motivo: str,
) -> str:
    contact = getattr(conversa, "contact", None)
    nome = (getattr(contact, "name", None) or "Cliente").strip()
    telefone = (getattr(contact, "phone", None) or "").strip()
    conv_id = getattr(conversa, "id", "")
    motivo_limpo = (motivo or "Transferência pela IA").strip()

    linhas = [
        "🔔 *NioHub — Transferência da IA*",
        "",
        f"*Equipe:* {equipe_nome}",
        f"*Conversa:* #{conv_id}",
        f"*Cliente:* {nome}",
    ]
    if telefone:
        linhas.append(f"*Telefone/contato:* {telefone}")
    linhas.extend([
        "",
        "*Resumo / motivo:*",
        motivo_limpo,
        "",
        "A conversa está *Em Espera* para a equipe.",
    ])
    return "\n".join(linhas)


def _send_via_cloud(provedor, to_phone: str, message: str) -> bool:
    from core.models import Canal
    from integrations.whatsapp_cloud_api import WhatsAppCloudAPIService

    canal = (
        Canal.objects.filter(
            provedor=provedor,
            tipo="whatsapp_oficial",
            ativo=True,
        )
        .exclude(phone_number_id="")
        .exclude(token="")
        .first()
    )
    if not canal:
        return False

    phone_number_id = (canal.phone_number_id or "").strip()
    token = (canal.token or "").strip()
    if not phone_number_id or not token:
        return False

    svc = WhatsAppCloudAPIService(phone_number_id=phone_number_id, access_token=token)
    result = svc.send_text_message(to=to_phone, message=message)
    return bool(result.get("success"))


def _send_via_uazapi(provedor, to_phone: str, message: str) -> bool:
    from integrations.utils import send_whatsapp_message

    return bool(send_whatsapp_message(to_phone, message, provedor))


def notify_support_transfer(
    provedor,
    conversa,
    *,
    equipe_nome: str,
    motivo: str,
) -> dict[str, Any]:
    """
    Se agent_mode=support e houver número configurado, envia resumo da transferência.
    """
    if not provedor:
        return {"sent": False, "reason": "sem_provedor"}

    try:
        from core.models import Provedor

        fresh = Provedor.objects.filter(pk=provedor.pk).first()
        if fresh:
            provedor = fresh
    except Exception:
        pass

    agent_mode = (getattr(provedor, "agent_mode", None) or "isp").strip().lower()
    if agent_mode != "support":
        return {"sent": False, "reason": "nao_modo_support"}

    notify_phone = _digits_phone(getattr(provedor, "support_transfer_notify_phone", "") or "")
    if len(notify_phone) < 10:
        return {"sent": False, "reason": "numero_nao_configurado"}

    message = _build_summary_message(
        conversa=conversa,
        equipe_nome=equipe_nome or "Equipe",
        motivo=motivo or "",
    )

    try:
        if _send_via_cloud(provedor, notify_phone, message):
            logger.info(
                "[SupportNotify] Transferência notificada via Cloud API | provedor=%s to=%s conv=%s equipe=%s",
                provedor.id,
                notify_phone[-4:],
                getattr(conversa, "id", None),
                equipe_nome,
            )
            return {"sent": True, "channel": "whatsapp_oficial"}

        if _send_via_uazapi(provedor, notify_phone, message):
            logger.info(
                "[SupportNotify] Transferência notificada via Uazapi | provedor=%s to=%s conv=%s equipe=%s",
                provedor.id,
                notify_phone[-4:],
                getattr(conversa, "id", None),
                equipe_nome,
            )
            return {"sent": True, "channel": "uazapi"}

        logger.warning(
            "[SupportNotify] Falha ao enviar notificação | provedor=%s conv=%s",
            provedor.id,
            getattr(conversa, "id", None),
        )
        return {"sent": False, "reason": "envio_falhou"}
    except Exception as exc:
        logger.error("[SupportNotify] Erro: %s", exc, exc_info=True)
        return {"sent": False, "reason": str(exc)}
