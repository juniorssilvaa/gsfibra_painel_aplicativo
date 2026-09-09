"""
Avisos WhatsApp para atendentes do provedor.

Quando o atendente cadastra o telefone no perfil, recebe alerta ao:
- receber transferência direta (assigned_user);
- entrar conversa na fila de espera da equipe / aba Espera.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)


def digits_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def normalize_agent_phone(phone: str) -> str:
    """Normaliza telefone do agente preservando DDI internacional."""
    from core.phone_utils import normalize_whatsapp_phone
    return normalize_whatsapp_phone(phone)

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


def _send_whatsapp(provedor, to_phone: str, message: str) -> bool:
    try:
        if _send_via_cloud(provedor, to_phone, message):
            return True
        if _send_via_uazapi(provedor, to_phone, message):
            return True
    except Exception as exc:
        logger.warning("[AgentAlert] Falha no envio para %s: %s", to_phone[-4:], exc)
    return False


DIVIDER = "━━━━━━━━━━━━━━━━━━"


def _format_br_phone(phone: str) -> str:
    """Formata telefone BR para leitura (+55 63 99248-4773)."""
    digits = digits_phone(phone)
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) in (12, 13):
        ddd = digits[2:4]
        resto = digits[4:]
        meio = resto[:-4]
        fim = resto[-4:]
        return f"+55 {ddd} {meio}-{fim}"
    return phone.strip()


def _build_message(
    *,
    conversa,
    motivo: str = "",
    equipe_nome: str = "",
    direta: bool = False,
) -> str:
    from django.utils import timezone

    contact = getattr(conversa, "contact", None)
    nome = (getattr(contact, "name", None) or "Cliente").strip()
    telefone = _format_br_phone(getattr(contact, "phone", None) or "")
    conv_id = getattr(conversa, "id", "")

    attrs = getattr(conversa, "additional_attributes", None) or {}
    protocolo = str(attrs.get("protocolo") or "").strip()

    try:
        agora = timezone.localtime(timezone.now()).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        agora = ""

    titulo = (
        "*Atendimento transferido para você*"
        if direta
        else "🔔 *Novo atendimento na fila de espera*"
    )

    linhas = [titulo, DIVIDER, f"*Cliente:* {nome}"]
    if telefone:
        linhas.append(f"*WhatsApp:* {telefone}")
    if equipe_nome:
        linhas.append(f"*Equipe:* {equipe_nome}")
    linhas.append(f"*Conversa:* #{conv_id}")
    if protocolo:
        linhas.append(f"*Protocolo:* {protocolo}")
    if agora:
        linhas.append(f"*Recebido:* {agora}")

    if (motivo or "").strip():
        linhas.extend(["", "*Motivo*", (motivo or "").strip()])

    linhas.extend([
        DIVIDER,
        "_Acesse o painel para assumir o atendimento._",
    ])
    return "\n".join(linhas)


def _users_with_alert_phone(users: Iterable, *, pref_attr: Optional[str] = None) -> List:
    """Filtra usuários ativos com telefone válido e com o aviso habilitado.

    pref_attr: nome do campo booleano de preferência (ex.: 'whatsapp_alert_transfer').
    Quando informado, só inclui quem tiver a preferência ligada.
    """
    out = []
    seen_phones: Set[str] = set()
    for user in users:
        if not user or not getattr(user, "is_active", True):
            continue
        if pref_attr and not bool(getattr(user, pref_attr, True)):
            continue
        phone = normalize_agent_phone(getattr(user, "phone", "") or "")
        if len(phone) < 12:
            continue
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        out.append((user, phone))
    return out


def _resolve_recipients(
    provedor,
    *,
    target_user=None,
    team=None,
    exclude_user_id: Optional[int] = None,
) -> List:
    from django.contrib.auth import get_user_model
    from conversations.models import TeamMember

    User = get_user_model()
    only_fields = (
        "id", "phone", "first_name", "last_name", "username", "is_active",
        "whatsapp_alert_transfer", "whatsapp_alert_waiting",
    )
    candidates = []

    # Transferência direta para um atendente usa a preferência de "transferido para mim";
    # equipe/fila usam a preferência de "fila de espera".
    if target_user is not None:
        candidates = [target_user]
        pref_attr = "whatsapp_alert_transfer"
    elif team is not None:
        member_ids = TeamMember.objects.filter(team=team).values_list("user_id", flat=True)
        candidates = list(
            User.objects.filter(id__in=member_ids, is_active=True).only(*only_fields)
        )
        # Sem membros na equipe: avisar atendentes do provedor com telefone
        if not candidates:
            candidates = list(
                User.objects.filter(provedor=provedor, is_active=True)
                .exclude(user_type="superadmin")
                .only(*only_fields)
            )
        pref_attr = "whatsapp_alert_waiting"
    else:
        # Fila geral (aba Espera): todos os atendentes/admins do provedor com telefone
        candidates = list(
            User.objects.filter(provedor=provedor, is_active=True)
            .exclude(user_type="superadmin")
            .only(*only_fields)
        )
        pref_attr = "whatsapp_alert_waiting"

    if exclude_user_id:
        candidates = [u for u in candidates if getattr(u, "id", None) != exclude_user_id]

    return _users_with_alert_phone(candidates, pref_attr=pref_attr)


def notify_agents_waiting_alert(
    provedor,
    conversa,
    *,
    target_user=None,
    team=None,
    motivo: str = "",
    exclude_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Envia WhatsApp aos atendentes com telefone no perfil.

    - target_user: transferência direta para o atendente
    - team: transferência para equipe (membros com telefone)
    - sem target/team: fila geral do provedor
    """
    if not provedor or not conversa:
        return {"sent": False, "reason": "sem_provedor_ou_conversa", "notified": 0}

    recipients = _resolve_recipients(
        provedor,
        target_user=target_user,
        team=team,
        exclude_user_id=exclude_user_id,
    )
    if not recipients:
        return {"sent": False, "reason": "nenhum_atendente_com_telefone", "notified": 0}

    message = _build_message(
        conversa=conversa,
        motivo=motivo,
        equipe_nome=(getattr(team, "name", "") or "") if team is not None else "",
        direta=target_user is not None,
    )
    notified = 0
    failures = 0

    for user, phone in recipients:
        ok = _send_whatsapp(provedor, phone, message)
        if ok:
            notified += 1
            logger.info(
                "[AgentAlert] Aviso enviado | provedor=%s user=%s to=***%s conv=%s",
                provedor.id,
                user.id,
                phone[-4:],
                getattr(conversa, "id", None),
            )
        else:
            failures += 1

    return {
        "sent": notified > 0,
        "notified": notified,
        "failures": failures,
        "reason": "ok" if notified else "envio_falhou",
    }
