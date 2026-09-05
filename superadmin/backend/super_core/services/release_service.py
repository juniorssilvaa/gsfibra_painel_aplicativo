"""Release assíncrono: redeploy Portainer 1 a 1 por canal + ponteiro :stable no GHCR."""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict

from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


def _append_result(update, row: Dict[str, Any]) -> None:
    results = list(update.results or [])
    results.append(row)
    update.results = results
    update.save(update_fields=["results"])


def execute_release(update_id: int) -> None:
    from super_core.models import Provedor, SystemUpdate
    from super_core.services.ghcr_promote import promote_tenant_images
    from super_core.services.portainer_service import PortainerService

    close_old_connections()
    try:
        update = SystemUpdate.objects.get(pk=update_id)
    except SystemUpdate.DoesNotExist:
        logger.error("[release] SystemUpdate id=%s não encontrado", update_id)
        return

    update.status = SystemUpdate.STATUS_RUNNING
    update.started_at = timezone.now()
    update.save(update_fields=["status", "started_at"])

    channel = (update.channel or "").strip()
    version = (update.version or "").strip()

    # Stable: promove a versão escolhida → :stable (avanço ou rollback).
    # Se o GHCR recusar, o Portainer ainda puxa :VERSION — o pin é o que importa.
    if channel == "stable" and version:
        ok, log = promote_tenant_images(version, ["stable"])
        update.promote_ok = ok
        update.promote_log = log[:8000]
        if not ok:
            update.promote_log = (
                "Promoção :stable falhou; seguindo com pin da versão no Portainer.\n" + update.promote_log
            )[:8000]
        update.save(update_fields=["promote_ok", "promote_log"])
    else:
        update.promote_ok = True
        update.promote_log = (
            "Canal beta: sem ponteiro :stable (imagens :beta-prov já publicadas no CI)."
        )
        update.save(update_fields=["promote_ok", "promote_log"])

    providers = list(
        Provedor.objects.filter(release_channel=channel, is_active=True).select_related("vps")
    )
    # Um provedor por vez. Nunca dois na mesma VPS ao mesmo tempo (pull + recreate estoura RAM).
    for provider in providers:
        if not provider.vps_id:
            _append_result(update, {"id": provider.id, "nome": provider.nome, "status": "no_vps"})
            continue
        if not (provider.subdomain or "").strip():
            _append_result(
                update,
                {"id": provider.id, "nome": provider.nome, "status": "no_subdomain"},
            )
            continue
        slug = (provider.subdomain or "").split(".")[0]
        stack_name = f"niohub-{slug}"
        try:
            service = PortainerService(provider.vps)
            # Libera disco/RAM dos exited de atualizações anteriores nesta VPS.
            service.prune_exited_containers()
            success = service.deploy_provider_stack(
                provider,
                image_tag=version if channel == "stable" else None,
            )
            cleanup = service.settle_and_cleanup(stack_name)
            if success:
                provider.current_version = version
                provider.last_update = timezone.now()
                provider.save(update_fields=["current_version", "last_update", "updated_at"])
                _append_result(
                    update,
                    {
                        "id": provider.id,
                        "nome": provider.nome,
                        "status": "success",
                        "pruned": cleanup.get("removed", 0),
                        "images_removed": cleanup.get("images_removed", 0),
                    },
                )
            else:
                _append_result(
                    update,
                    {
                        "id": provider.id,
                        "nome": provider.nome,
                        "status": "failed",
                        "pruned": cleanup.get("removed", 0),
                        "images_removed": cleanup.get("images_removed", 0),
                    },
                )
        except Exception as exc:
            logger.exception("[release] provedor %s: %s", provider.nome, exc)
            _append_result(
                update,
                {"id": provider.id, "nome": provider.nome, "status": "error", "msg": str(exc)[:400]},
            )
        close_old_connections()
        update.refresh_from_db(fields=["results", "status"])

    update.refresh_from_db()
    statuses = [r.get("status") for r in (update.results or [])]
    hard_fail = any(s in ("failed", "error") for s in statuses)
    any_ok = any(s == "success" for s in statuses)
    update.is_deployed = any_ok
    update.status = SystemUpdate.STATUS_FAILED if hard_fail and not any_ok else SystemUpdate.STATUS_DONE
    if hard_fail and any_ok:
        update.status = SystemUpdate.STATUS_DONE
    update.finished_at = timezone.now()
    update.save(update_fields=["status", "is_deployed", "finished_at"])


def start_release_async(update_id: int) -> None:
    thread = threading.Thread(target=execute_release, args=(update_id,), daemon=True)
    thread.start()


def queue_release(
    *,
    channel: str,
    version: str,
    source: str = "ui",
    description: str = "",
) -> Any:
    from super_core.models import SystemUpdate

    update = SystemUpdate.objects.create(
        version=version.strip(),
        channel=channel.strip(),
        source=(source or "ui")[:20],
        description=description or "",
        status=SystemUpdate.STATUS_PENDING,
        results=[],
    )
    start_release_async(update.id)
    return update


def ci_token_expected() -> str:
    import os
    from django.conf import settings

    token = (os.getenv("SUPERADMIN_CI_TOKEN") or getattr(settings, "SUPERADMIN_CI_TOKEN", "") or "").strip()
    if token:
        return token
    secret = (getattr(settings, "ADMIN_WEBHOOK_SECRET", "") or "").strip()
    if secret:
        return secret
    try:
        from super_core.models import SystemConfig

        config = SystemConfig.objects.first()
        payload = config.payload if config and isinstance(config.payload, dict) else {}
        return str(payload.get("ci_release_token") or payload.get("ADMIN_WEBHOOK_SECRET") or "").strip()
    except Exception:
        return ""


def request_has_ci_token(request) -> bool:
    import secrets as pysecrets

    incoming = (
        request.headers.get("X-CI-Token")
        or request.META.get("HTTP_X_CI_TOKEN")
        or ""
    ).strip()
    expected = ci_token_expected()
    if not incoming or not expected:
        return False
    if len(incoming) != len(expected):
        return False
    return pysecrets.compare_digest(incoming, expected)
