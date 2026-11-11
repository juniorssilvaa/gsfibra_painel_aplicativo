"""
Desativa todas as notificações granulares de um cliente no Asaas.

Documentação:
- PUT /v3/notifications/{id}
- PUT /v3/notifications/batch
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from integrations.asaas_config import get_asaas_access_token, get_asaas_base_url
from integrations.asaas_entity import asaas_customer_is_active, asaas_entity_is_removed

logger = logging.getLogger(__name__)


def _headers() -> Dict[str, str]:
    return {
        "access_token": get_asaas_access_token(),
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def _notification_disabled_body() -> Dict[str, bool]:
    return {
        "enabled": False,
        "emailEnabledForProvider": False,
        "smsEnabledForProvider": False,
        "emailEnabledForCustomer": False,
        "smsEnabledForCustomer": False,
        "whatsappEnabledForCustomer": False,
        "phoneCallEnabledForCustomer": False,
    }


def _list_notifications(customer_id: str) -> List[Dict[str, Any]]:
    base = get_asaas_base_url()
    headers = _headers()
    if not headers.get("access_token"):
        logger.error("[AsaasNotifications] access_token ausente")
        return []

    items: List[Dict[str, Any]] = []

    try:
        r = requests.get(
            f"{base}/notifications",
            params={"customer": customer_id},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 200:
            body = r.json()
            items = body.get("data") or []
    except Exception as exc:
        logger.warning("[AsaasNotifications] Falha ao listar /notifications: %s", exc)

    if not items:
        try:
            r2 = requests.get(
                f"{base}/customers/{customer_id}/notifications",
                headers=headers,
                timeout=30,
            )
            if r2.status_code == 200:
                body2 = r2.json()
                items = body2.get("data") or (body2 if isinstance(body2, list) else [])
        except Exception as exc:
            logger.warning("[AsaasNotifications] Falha ao listar /customers/.../notifications: %s", exc)

    return items


def _update_one(notification_id: str, body: Dict[str, Any]) -> bool:
    base = get_asaas_base_url()
    url = f"{base}/notifications/{notification_id}"
    try:
        response = requests.put(url, json=body, headers=_headers(), timeout=30)
        if response.status_code == 200:
            return True
        logger.error(
            "[AsaasNotifications] PUT %s falhou (%s): %s",
            notification_id,
            response.status_code,
            response.text[:500],
        )
    except Exception as exc:
        logger.error("[AsaasNotifications] PUT %s exceção: %s", notification_id, exc)
    return False


def disable_all_customer_notifications(customer_id: str) -> Dict[str, Any]:
    """
    Desmarca todos os canais de todas as notificações do cliente.
    """
    if not customer_id:
        return {"success": False, "error": "customer_id vazio"}

    notifications = _list_notifications(customer_id)
    if not notifications:
        logger.warning("[AsaasNotifications] Nenhuma notificação para %s", customer_id)
        return {"success": True, "updated": 0}

    disabled_body = _notification_disabled_body()
    batch_items = []
    for notif in notifications:
        notif_id = notif.get("id")
        if not notif_id:
            continue
        batch_items.append({"id": notif_id, **disabled_body})

    if batch_items:
        base = get_asaas_base_url()
        try:
            response = requests.put(
                f"{base}/notifications/batch",
                json={"customer": customer_id, "notifications": batch_items},
                headers=_headers(),
                timeout=60,
            )
            if response.status_code == 200:
                logger.info(
                    "[AsaasNotifications] Batch PUT: %s notificações desativadas (%s)",
                    len(batch_items),
                    customer_id,
                )
                return {"success": True, "updated": len(batch_items), "mode": "batch"}
            logger.warning(
                "[AsaasNotifications] Batch PUT falhou (%s): %s",
                response.status_code,
                response.text[:500],
            )
        except Exception as exc:
            logger.warning("[AsaasNotifications] Batch PUT exceção: %s", exc)

    ok = 0
    for item in batch_items:
        notif_id = item["id"]
        body = {k: v for k, v in item.items() if k != "id"}
        if _update_one(notif_id, body):
            ok += 1

    if ok < len(batch_items):
        return {
            "success": False,
            "updated": ok,
            "error": f"Falha ao desativar {len(batch_items) - ok} notificação(ões)",
            "mode": "individual",
        }
    return {"success": True, "updated": ok, "mode": "individual"}


def _get_customer_data(customer_id: str) -> Dict[str, Any] | None:
    base = get_asaas_base_url()
    try:
        response = requests.get(
            f"{base}/customers/{customer_id}",
            headers=_headers(),
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        if asaas_entity_is_removed(response.status_code, response.text):
            return None
    except Exception as exc:
        logger.warning("[AsaasNotifications] GET customer %s: %s", customer_id, exc)
    return None


def set_customer_notification_disabled(customer_id: str, *, disabled: bool, customer_payload: Dict[str, Any] | None = None) -> bool:
    """Atualiza notificationDisabled no cadastro do cliente (PUT /customers/{id})."""
    existing = _get_customer_data(customer_id)
    if existing is None or not asaas_customer_is_active(existing):
        logger.warning(
            "[AsaasNotifications] Cliente %s excluído ou inexistente — ignorando PUT",
            customer_id,
        )
        return False

    base = get_asaas_base_url()
    payload = dict(customer_payload or {})
    payload["notificationDisabled"] = disabled
    try:
        response = requests.put(
            f"{base}/customers/{customer_id}",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        if response.status_code == 200:
            return True
        if asaas_entity_is_removed(response.status_code, response.text):
            logger.warning(
                "[AsaasNotifications] Cliente %s excluído no Asaas (PUT rejeitado)",
                customer_id,
            )
            return False
        logger.error(
            "[AsaasNotifications] PUT customer %s (%s): %s",
            customer_id,
            response.status_code,
            response.text[:500],
        )
    except Exception as exc:
        logger.error("[AsaasNotifications] PUT customer %s: %s", customer_id, exc)
    return False


def apply_provedor_notification_settings(
    customer_id: str,
    *,
    notification_disabled: bool,
    customer_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Se notification_disabled: marca notificationDisabled no cliente e desativa todas as notificações.
    """
    if not notification_disabled:
        return {"success": True, "skipped": True}

    existing = _get_customer_data(customer_id)
    if existing is None or not asaas_customer_is_active(existing):
        return {
            "success": False,
            "customer_removed": True,
            "error": "Cliente excluído ou inexistente no Asaas",
        }

    set_customer_notification_disabled(
        customer_id, disabled=True, customer_payload=customer_payload
    )
    return disable_all_customer_notifications(customer_id)
