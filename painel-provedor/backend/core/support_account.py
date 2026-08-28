"""Utilizador de suporte «niohub» no painel do tenant (um Provedor por base)."""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# Cache por host normalizado: host -> (provedor_id, timestamp)
_superadmin_cache: dict[str, tuple[int, float]] = {}
_CACHE_TTL = 300  # 5 minutos


def is_niohub_support(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', True):
        return False
    return str(getattr(user, 'username', '') or '').lower() == 'niohub'


def is_hidden_from_provedor_user_lists(user) -> bool:
    """Conta de suporte/superadmin não deve aparecer nas listagens do painel do provedor."""
    if not user:
        return False
    if is_niohub_support(user):
        return True
    return str(getattr(user, 'user_type', '') or '').lower() == 'superadmin'


def exclude_hidden_provedor_users(queryset, viewer=None):
    """
    Remove niohub e user_type=superadmin das listagens do provedor.

    Atividade Recente / audit-logs NÃO usam este filtro — ações do suporte
    continuam visíveis pelo nome quando ocorrem no painel.
    """
    if viewer is not None and (
        is_niohub_support(viewer)
        or str(getattr(viewer, 'user_type', '') or '').lower() == 'superadmin'
    ):
        return queryset
    return queryset.exclude(username__iexact='niohub').exclude(user_type='superadmin')


# ---------------------------------------------------------------------------
# Lookup no superadmin pelo subdomínio do tenant
# ---------------------------------------------------------------------------

def _current_subdomain() -> str:
    """
    Retorna o subdomínio deste tenant.
    Preferência: variável de ambiente SUBDOMAIN > HOST > vazio.
    """
    subdomain = os.environ.get('SUBDOMAIN', '').strip()
    if subdomain:
        return subdomain
    host = os.environ.get('HOST', os.environ.get('ALLOWED_HOST', '')).strip()
    return host


def _superadmin_base_url_for_resolve() -> str:
    """
    URL base do superadmin para pedidos server-to-server (lookup de provedor).

    Ordem: SUPERADMIN_ID_PROVEDOR_API > SUPERADMIN_RESOLVE_API_URL > SUPERADMIN_API_URL
    Lê primeiro de django.conf.settings (decouple / .env); fallback para os.environ.
    """
    try:
        from django.conf import settings as _settings

        for attr in (
            'SUPERADMIN_ID_PROVEDOR_API',
            'SUPERADMIN_RESOLVE_API_URL',
            'SUPERADMIN_API_URL',
        ):
            v = str(getattr(_settings, attr, '') or '').strip().rstrip('/')
            if v:
                return v
    except Exception:
        pass

    for key in (
        'SUPERADMIN_ID_PROVEDOR_API',
        'SUPERADMIN_RESOLVE_API_URL',
        'SUPERADMIN_API_URL',
    ):
        v = os.environ.get(key, '').strip().rstrip('/')
        if v:
            return v
    return ''


def _admin_webhook_secret() -> str:
    try:
        from django.conf import settings as _settings

        s = str(getattr(_settings, 'ADMIN_WEBHOOK_SECRET', '') or '').strip()
        if s:
            return s
    except Exception:
        pass
    return os.environ.get('ADMIN_WEBHOOK_SECRET', '').strip()


def _normalize_host(host: str) -> str:
    host = (host or '').strip().lower()
    if not host:
        return ''
    # remove esquema (se vier por engano)
    host = host.replace('https://', '').replace('http://', '')
    # remove porta
    if ':' in host:
        host = host.split(':', 1)[0]
    return host


def resolve_provedor_id_from_superadmin(subdomain: str | None = None) -> int | None:
    """
    Consulta o superadmin para descobrir o provedor_id correcto para este tenant,
    identificado pelo seu subdomínio único.

    Retorna o int do provedor_id ou None se não for possível determinar.
    Cache em memória por 5 minutos para não sobrecarregar o superadmin.
    """
    global _superadmin_cache

    subdomain = _normalize_host(subdomain) if subdomain else _normalize_host(_current_subdomain())
    if not subdomain:
        logger.warning("[support_account] Host/subdomínio vazio — sem lookup no superadmin.")
        return None

    cached = _superadmin_cache.get(subdomain)
    if cached is not None:
        pid, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return pid

    superadmin_url = _superadmin_base_url_for_resolve()
    if not superadmin_url:
        logger.warning(
            "[support_account] SUPERADMIN_ID_PROVEDOR_API (ou RESOLVE/API_URL) "
            "não configurado — lookup ao superadmin desativado."
        )
        return None

    webhook_secret = _admin_webhook_secret()
    if not webhook_secret:
        logger.warning("[support_account] ADMIN_WEBHOOK_SECRET não configurado — lookup ao superadmin desativado.")
        return None

    try:
        import requests as _requests
        url = f"{superadmin_url}/api/provedores/lookup-by-subdomain/"
        resp = _requests.get(
            url,
            params={'subdomain': subdomain, 'secret': webhook_secret},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            pid = int(data['provedor_id'])
            _superadmin_cache[subdomain] = (pid, time.monotonic())
            logger.info(
                f"[support_account] provedor_id={pid} resolvido via superadmin "
                f"para subdomain='{subdomain}'."
            )
            return pid
        elif resp.status_code == 404:
            logger.warning(
                f"[support_account] Superadmin não encontrou Provedor para subdomain='{subdomain}'."
            )
        else:
            logger.warning(
                f"[support_account] Superadmin retornou HTTP {resp.status_code} "
                f"para lookup de subdomain='{subdomain}'."
            )
    except Exception as exc:
        logger.warning(f"[support_account] Erro ao consultar superadmin: {exc}")

    return None


# ---------------------------------------------------------------------------
# Fallback local (base de dados do tenant)
# ---------------------------------------------------------------------------

def fallback_provedor_for_niohub(user):
    """
    Se o niohub ainda não tiver FK/M2M (dados antigos), usa o primeiro Provedor da base.
    Preferência: id mais alto (o Provedor "real" criado pelo superadmin).
    """
    if not is_niohub_support(user):
        return None
    from core.models import Provedor

    return Provedor.objects.order_by('-id').first()


def fallback_provedor_id_for_niohub(user) -> int | None:
    p = fallback_provedor_for_niohub(user)
    return p.id if p else None


# ---------------------------------------------------------------------------
# Resolver principal
# ---------------------------------------------------------------------------

def resolve_niohub_provedor_id(subdomain: str | None = None) -> int | None:
    """
    Ordem de prioridade:
    1. Variável de ambiente SUPERADMIN_PROVEDOR_ID (configuração explícita)
    2. Lookup no superadmin pelo subdomínio
    3. Provedor com maior id no banco local (heurística)
    """
    # 1. Variável de ambiente explícita
    raw = ''
    try:
        from django.conf import settings as _settings

        raw = str(getattr(_settings, 'SUPERADMIN_PROVEDOR_ID', '') or '').strip()
    except Exception:
        pass
    if not raw:
        raw = os.environ.get('SUPERADMIN_PROVEDOR_ID', '').strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass

    # 2. Superadmin via subdomínio
    pid = resolve_provedor_id_from_superadmin(subdomain=subdomain)
    if pid:
        return pid

    # 3. Fallback local
    try:
        from core.models import Provedor
        p = Provedor.objects.order_by('-id').first()
        if p:
            logger.debug(f"[support_account] Usando fallback local: provedor_id={p.id}")
            return p.id
    except Exception as exc:
        logger.warning(f"[support_account] Erro ao buscar fallback local: {exc}")

    return None
