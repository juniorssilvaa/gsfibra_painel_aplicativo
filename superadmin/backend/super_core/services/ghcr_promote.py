"""
Promove tags no GHCR (ex.: beta-prov → stable + 2.59.0).

O CI publica :latest / :beta-prov em todo push. :stable só anda quando
o Superadmin libera o canal estável.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GHCR_HOST = "https://ghcr.io"
IMAGE_PREFIX = "juniorssilvaa/niohub_chat"
TENANT_IMAGES = (
    f"{IMAGE_PREFIX}-backend",
    f"{IMAGE_PREFIX}-frontend",
    f"{IMAGE_PREFIX}-dramatiq",
    f"{IMAGE_PREFIX}-calls",
)

_ACCEPT = (
    "application/vnd.oci.image.index.v1+json,"
    "application/vnd.docker.distribution.manifest.list.v2+json,"
    "application/vnd.oci.image.manifest.v1+json,"
    "application/vnd.docker.distribution.manifest.v2+json"
)


def _credentials() -> Tuple[str, str, str]:
    """
    Retorna (username, token, origem).
    Prioridade: GHCR_TOKEN no ambiente do Superadmin, depois github_pat do SystemConfig.
    """
    username = (os.getenv("GITHUB_USERNAME") or "").strip()
    env_token = (os.getenv("GHCR_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    cfg_token = ""
    try:
        from super_core.models import SystemConfig

        config = SystemConfig.objects.first()
        if config and isinstance(config.payload, dict):
            username = str(config.payload.get("github_username") or username).strip()
            cfg_token = str(config.payload.get("github_pat") or "").strip()
    except Exception as exc:
        logger.warning("[ghcr] SystemConfig indisponível: %s", exc)

    if env_token:
        return username, env_token, "env:GHCR_TOKEN"
    if cfg_token:
        return username, cfg_token, "SystemConfig.github_pat"
    return username, "", ""


def _registry_bearer(session: requests.Session, username: str, pat: str, image: str) -> Optional[str]:
    """
    GHCR exige token do endpoint /token (Basic user:PAT), não o PAT cru como Bearer.
    """
    user = username or "token"
    basic = base64.b64encode(f"{user}:{pat}".encode("utf-8")).decode("ascii")
    try:
        res = session.get(
            f"{GHCR_HOST}/token",
            params={
                "service": "ghcr.io",
                "scope": f"repository:{image}:pull,push",
            },
            headers={"Authorization": f"Basic {basic}"},
            timeout=25,
        )
    except Exception as exc:
        logger.warning("[ghcr] token %s: %s", image, exc)
        return None
    if res.status_code != 200:
        logger.warning("[ghcr] token %s HTTP %s: %s", image, res.status_code, res.text[:200])
        return None
    data = res.json() if res.content else {}
    return (data.get("token") or data.get("access_token") or "").strip() or None


def promote_tenant_images(source_tag: str, dest_tags: List[str]) -> Tuple[bool, str]:
    """
    Copia o manifest de `source_tag` para cada tag em `dest_tags` (todas as imagens do tenant).
    """
    source_tag = (source_tag or "").strip()
    dests = [t.strip() for t in dest_tags if t and t.strip() and t.strip() != source_tag]
    if not source_tag or not dests:
        return False, "Tags de origem/destino inválidas."

    username, pat, origin = _credentials()
    if not pat:
        return (
            False,
            "Token do GitHub ausente. Em Superadmin → Servidores VPS → Registry, "
            "grave github_username + PAT com permissão read:packages e write:packages "
            "(ou defina GHCR_TOKEN no compose do Superadmin).",
        )

    lines: List[str] = [f"Auth: {origin} user={username or '(vazio)'}"]
    ok_all = True
    session = requests.Session()

    for image in TENANT_IMAGES:
        bearer = _registry_bearer(session, username, pat, image)
        if not bearer:
            ok_all = False
            lines.append(
                f"{image}: falha ao obter token GHCR (PAT inválido, expirado ou sem write:packages)."
            )
            continue

        headers_get = {
            "Authorization": f"Bearer {bearer}",
            "Accept": _ACCEPT,
        }
        get_url = f"{GHCR_HOST}/v2/{image}/manifests/{source_tag}"
        try:
            res = session.get(get_url, headers=headers_get, timeout=30)
        except Exception as exc:
            ok_all = False
            lines.append(f"{image}:{source_tag} GET erro: {exc}")
            continue
        if res.status_code != 200:
            ok_all = False
            lines.append(f"{image}:{source_tag} GET {res.status_code}: {res.text[:200]}")
            continue

        content_type = (res.headers.get("Content-Type") or "application/vnd.oci.image.index.v1+json").split(";")[0]
        body = res.content
        for dest in dests:
            put_url = f"{GHCR_HOST}/v2/{image}/manifests/{dest}"
            try:
                put = session.put(
                    put_url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {bearer}",
                        "Content-Type": content_type,
                    },
                    timeout=30,
                )
            except Exception as exc:
                ok_all = False
                lines.append(f"{image}:{dest} PUT erro: {exc}")
                continue
            if put.status_code not in (201, 200):
                ok_all = False
                lines.append(f"{image}:{dest} PUT {put.status_code}: {put.text[:200]}")
            else:
                lines.append(f"{image}:{source_tag} → :{dest} ok")

    log = "\n".join(lines)
    if ok_all:
        logger.info("[ghcr] promote %s → %s\n%s", source_tag, dests, log)
    else:
        logger.error("[ghcr] promote falhou %s → %s\n%s", source_tag, dests, log)
    return ok_all, log
