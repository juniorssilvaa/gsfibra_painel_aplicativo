from dataclasses import dataclass
import logging
from typing import Optional

from django.conf import settings
from django.core.cache import cache

from core.models import Provedor

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    host: str
    subdomain: Optional[str] = None
    provedor_id: Optional[int] = None
    source: str = "none"

    @property
    def resolved(self) -> bool:
        return self.provedor_id is not None

    def as_dict(self) -> dict:
        return {
            "host": self.host,
            "subdomain": self.subdomain,
            "provedor_id": self.provedor_id,
            "source": self.source,
            "resolved": self.resolved,
        }


def _normalize_host(raw_host: str) -> str:
    if not raw_host:
        return ""
    host = raw_host.split(",")[0].strip().lower()
    if ":" in host:
        host = host.split(":")[0]
    return host


def _extract_subdomain(host: str) -> Optional[str]:
    if not host:
        return None

    root_domains = [d.strip().lower() for d in getattr(settings, "SUBDOMAIN_PRIMARY_DOMAINS", []) if d]
    if not root_domains:
        return None

    reserved = {s.strip().lower() for s in getattr(settings, "SUBDOMAIN_RESERVED_LABELS", []) if s}

    for root_domain in root_domains:
        if host == root_domain:
            return None
        suffix = f".{root_domain}"
        if not host.endswith(suffix):
            continue

        prefix = host[: -len(suffix)]
        if not prefix:
            return None
        label = prefix.split(".")[-1].strip().lower()
        if not label or label in reserved:
            return None
        return label

    return None


def _matches_subdomain(provedor: Provedor, subdomain: str) -> bool:
    ext = provedor.integracoes_externas or {}
    configured = (
        ext.get("subdomain")
        or ext.get("subdominio")
        or ext.get("tenant_subdomain")
        or ""
    )
    return configured.strip().lower() == subdomain


def _find_provedor_id_by_subdomain(subdomain: str) -> Optional[int]:
    cache_key = f"tenant_subdomain_resolve:{subdomain}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == 0 else int(cached)

    provedor_id: Optional[int] = None
    for provedor in Provedor.objects.filter(is_active=True).only("id", "integracoes_externas"):
        if _matches_subdomain(provedor, subdomain):
            provedor_id = provedor.id
            break

    ttl = int(getattr(settings, "SUBDOMAIN_TENANT_CACHE_TTL", 300))
    cache.set(cache_key, provedor_id or 0, timeout=max(30, ttl))
    return provedor_id


def resolve_tenant_context_from_host(host: str) -> TenantContext:
    normalized_host = _normalize_host(host)
    context = TenantContext(host=normalized_host)

    if not getattr(settings, "SUBDOMAIN_TENANT_ENABLED", False):
        return context

    subdomain = _extract_subdomain(normalized_host)
    if not subdomain:
        return context

    context.subdomain = subdomain
    provedor_id = _find_provedor_id_by_subdomain(subdomain)
    if provedor_id:
        context.provedor_id = provedor_id
        context.source = "subdomain"
    return context


def resolve_tenant_context_for_request(request) -> TenantContext:
    host = (
        request.META.get("HTTP_X_FORWARDED_HOST")
        or request.META.get("HTTP_HOST")
        or request.META.get("SERVER_NAME")
        or ""
    )
    return resolve_tenant_context_from_host(host)


def attach_tenant_context_to_request(request) -> TenantContext:
    context = resolve_tenant_context_for_request(request)
    request.tenant_context = context.as_dict()
    request.tenant_provedor_id = context.provedor_id
    request.tenant_subdomain = context.subdomain
    return context


def attach_tenant_context_to_scope(scope: dict) -> TenantContext:
    headers = dict(scope.get("headers", []))
    host = (
        headers.get(b"x-forwarded-host", b"").decode("utf-8", errors="ignore")
        or headers.get(b"host", b"").decode("utf-8", errors="ignore")
        or scope.get("server", ["", ""])[0]
        or ""
    )
    context = resolve_tenant_context_from_host(host)
    scope["tenant_context"] = context.as_dict()
    return context
