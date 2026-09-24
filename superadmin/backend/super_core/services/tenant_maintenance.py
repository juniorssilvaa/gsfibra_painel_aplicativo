"""Liga/desliga a tela de manutenção no painel do provedor durante o redeploy."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

# Tempo máximo que a tela fica ligada caso o desligamento final não chegue ao tenant
MAINTENANCE_TTL_SECONDS = 20 * 60


def _tenant_host(provedor) -> str:
    subdomain = (getattr(provedor, "subdomain", "") or "").strip()
    if subdomain and "." not in subdomain:
        subdomain = f"{subdomain}.niohub.com.br"
    return subdomain


def _tenant_boot_epoch(host: str):
    """Momento em que o backend do tenant iniciou (campo `boot` do /api/health/)."""
    try:
        resp = requests.get(f"https://{host}/api/health/", timeout=6)
        if resp.ok:
            return int((resp.json() or {}).get("boot") or 0)
    except Exception:
        pass
    return None


def set_tenant_maintenance(provedor, active: bool) -> bool:
    subdomain = _tenant_host(provedor)
    token = (getattr(provedor, "integration_token", "") or "").strip()
    if not subdomain or not token:
        return False

    url = f"https://{subdomain}/api/webhooks/admin/maintenance/"
    payload = {"active": bool(active), "ttl_seconds": MAINTENANCE_TTL_SECONDS}
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        if resp.ok:
            logger.info("[maintenance] %s → %s", subdomain, "on" if active else "off")
            return True
        logger.warning("[maintenance] %s respondeu %s: %s", subdomain, resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("[maintenance] falha ao contactar %s: %s", subdomain, exc)
    return False


def begin_tenant_maintenance(provedor):
    """Liga a tela de manutenção e devolve o `boot` do backend atual (para detectar o novo)."""
    previous_boot = _tenant_boot_epoch(_tenant_host(provedor))
    set_tenant_maintenance(provedor, True)
    return previous_boot


def set_tenant_maintenance_when_ready(
    provedor, previous_boot=None, timeout_sec: int = 300, interval_sec: int = 8
) -> bool:
    """
    Desliga a manutenção quando o backend recriado responder (boot diferente do anterior).
    Sem previous_boot, desliga na primeira resposta. No timeout, desliga mesmo assim
    (ex.: deploy falhou e o backend antigo segue no ar).
    """
    import time

    host = _tenant_host(provedor)
    deadline = time.monotonic() + max(interval_sec, timeout_sec)
    while True:
        boot = _tenant_boot_epoch(host) if previous_boot else None
        # boot == 0: tenant sem o campo (versão antiga) → não há como distinguir, segue
        new_backend_up = not previous_boot or (boot is not None and (boot == 0 or boot != previous_boot))
        timed_out = time.monotonic() >= deadline
        if (new_backend_up or timed_out) and set_tenant_maintenance(provedor, False):
            return True
        if time.monotonic() >= deadline:
            logger.warning(
                "[maintenance] não foi possível desligar em %s; expira sozinho em %ss",
                getattr(provedor, "subdomain", "?"),
                MAINTENANCE_TTL_SECONDS,
            )
            return False
        time.sleep(interval_sec)
