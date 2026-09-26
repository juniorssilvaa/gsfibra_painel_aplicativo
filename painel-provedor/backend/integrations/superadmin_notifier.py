"""
Superadmin Notifier Service - Painel do Provedor

Serviço responsável por notificar o Superadmin quando um canal WhatsApp
é conectado, para que o Dispatcher central saiba para onde encaminhar
os webhooks da Meta.

Auto-recuperação de credenciais:
  • SUPERADMIN_API_URL: fallback hardcoded para https://app.niohub.com.br
  • SUPERADMIN_PROVIDER_TOKEN: se vazio, chama lookup-by-subdomain usando
    ADMIN_WEBHOOK_SECRET para obter o integration_token registado no Superadmin.
    O resultado fica cacheado em memória por 10 minutos.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# URL canónica do Superadmin — usada quando a env var não está injectada no container.
_SUPERADMIN_FALLBACK_URL = "https://app.niohub.com.br"

# Cache de credenciais auto-recuperadas  subdomain -> (token, ts)
_token_cache: dict[str, tuple[str, float]] = {}
_TOKEN_CACHE_TTL = 600  # 10 minutos


# ---------------------------------------------------------------------------
# Helpers de leitura de settings / env
# ---------------------------------------------------------------------------

def _superadmin_api_url() -> str:
    """URL base preferida do Superadmin."""
    urls = _superadmin_api_urls()
    return urls[0] if urls else _SUPERADMIN_FALLBACK_URL


def _superadmin_api_urls() -> list[str]:
    """
    URLs do superadmin para tentar (local dev → produção).
    Ordem: env explícitas → localhost (DEBUG) → app.niohub.com.br.
    """
    seen: set[str] = set()
    out: list[str] = []

    def _add(url: str) -> None:
        u = (url or '').strip().rstrip('/')
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    for attr in ('SUPERADMIN_ID_PROVEDOR_API', 'SUPERADMIN_RESOLVE_API_URL', 'SUPERADMIN_API_URL'):
        _add(str(getattr(settings, attr, '') or ''))

    if getattr(settings, 'DEBUG', False):
        _add('http://127.0.0.1:8010')
    _add(_SUPERADMIN_FALLBACK_URL)
    return out


def _admin_webhook_secret() -> str:
    return str(getattr(settings, 'ADMIN_WEBHOOK_SECRET', '') or '').strip()


def _current_subdomain() -> str:
    import os
    subdomain = os.environ.get('SUBDOMAIN', '').strip()
    if subdomain:
        return subdomain
    host = os.environ.get('HOST', os.environ.get('ALLOWED_HOST', '')).strip()
    return host


def _resolve_provedor_id() -> Optional[int]:
    """
    Descobre o provedor_id canónico deste tenant.
    Prioridade: SUPERADMIN_PROVEDOR_ID env/settings → lookup superadmin por subdomain
    → Provedor local com maior id.
    """
    raw = str(getattr(settings, 'SUPERADMIN_PROVEDOR_ID', '') or '').strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass

    try:
        from core.support_account import resolve_niohub_provedor_id
        pid = resolve_niohub_provedor_id()
        if pid:
            return pid
    except Exception as exc:
        logger.debug("[SuperadminNotifier] Erro ao resolver provedor via superadmin: %s", exc)

    try:
        from core.models import Provedor
        p = Provedor.objects.order_by('-id').first()
        if p:
            return p.id
    except Exception:
        pass

    return None


def _fetch_token_by_provedor_id(superadmin_url: str, provedor_id: int, secret: str) -> str:
    try:
        url = f"{superadmin_url}/api/provedores/lookup-by-provedor-id/"
        resp = requests.get(
            url,
            params={'provedor_id': provedor_id, 'secret': secret},
            timeout=8,
        )
        if resp.status_code == 200:
            token = (resp.json().get('integration_token') or '').strip()
            if token:
                logger.info(
                    '[SuperadminNotifier] integration_token via lookup-by-provedor-id (id=%s).',
                    provedor_id,
                )
            return token
        logger.warning(
            '[SuperadminNotifier] lookup-by-provedor-id HTTP %s (id=%s).',
            resp.status_code,
            provedor_id,
        )
    except Exception as exc:
        logger.warning('[SuperadminNotifier] lookup-by-provedor-id erro: %s', exc)
    return ''


def fetch_superadmin_billing_block_settings() -> tuple[bool, int] | None:
    """Lê regras de bloqueio do SystemConfig central (superadmin)."""
    superadmin_url = _superadmin_api_url()
    secret = _admin_webhook_secret()
    if not secret:
        return None
    try:
        url = f"{superadmin_url}/api/provedores/billing-block-config/"
        resp = requests.get(url, params={'secret': secret}, timeout=8)
        if not resp.ok:
            return None
        data = resp.json() or {}
        enabled = bool(data.get('billing_provedor_auto_block_enabled', False))
        try:
            min_days = int(data.get('billing_provedor_block_min_days_late', 4))
        except (TypeError, ValueError):
            min_days = 4
        return enabled, max(0, min(365, min_days))
    except Exception as exc:
        logger.debug('[SuperadminNotifier] billing-block-config: %s', exc)
        return None


def _fetch_token_from_superadmin(superadmin_url: str, subdomain: str, secret: str) -> str:
    """
    Chama lookup-by-subdomain no Superadmin e extrai o integration_token.
    Retorna string vazia se falhar.
    """
    try:
        url = f"{superadmin_url}/api/provedores/lookup-by-subdomain/"
        resp = requests.get(
            url,
            params={'subdomain': subdomain, 'secret': secret},
            timeout=8,
        )
        if resp.status_code == 200:
            token = (resp.json().get('integration_token') or '').strip()
            if token:
                logger.info(
                    "[SuperadminNotifier] integration_token auto-recuperado via lookup-by-subdomain "
                    "(subdomain=%s).", subdomain,
                )
            else:
                logger.warning(
                    "[SuperadminNotifier] lookup-by-subdomain respondeu mas sem integration_token "
                    "(subdomain=%s). O provedor pode não ter token gerado ainda.", subdomain,
                )
            return token
        logger.warning(
            "[SuperadminNotifier] lookup-by-subdomain HTTP %s (subdomain=%s).",
            resp.status_code, subdomain,
        )
    except Exception as exc:
        logger.warning("[SuperadminNotifier] Erro em lookup-by-subdomain: %s", exc)
    return ''


def _resolve_provider_token(superadmin_url: str) -> str:
    """
    Retorna o Bearer token para autenticar junto ao Superadmin.

    Prioridade:
      1. SUPERADMIN_PROVIDER_TOKEN (variável de ambiente injectada no deploy).
      2. Cache de token auto-recuperado.
      3. Chamada a lookup-by-subdomain com ADMIN_WEBHOOK_SECRET (auto-heal).
    """
    # 1. Env/settings explícito
    token = str(getattr(settings, 'SUPERADMIN_PROVIDER_TOKEN', '') or '').strip()
    if token:
        return token

    # 2. Cache
    subdomain = _current_subdomain()
    if subdomain:
        cached = _token_cache.get(subdomain)
        if cached:
            t, ts = cached
            if time.monotonic() - ts < _TOKEN_CACHE_TTL:
                return t

    # 3. Auto-heal via lookup (subdomain ou provedor_id local)
    secret = _admin_webhook_secret()
    if not secret:
        logger.warning(
            '[SuperadminNotifier] SUPERADMIN_PROVIDER_TOKEN e ADMIN_WEBHOOK_SECRET vazios.'
        )
        return ''

    token = ''
    if subdomain:
        token = _fetch_token_from_superadmin(superadmin_url, subdomain, secret)
        if token and subdomain:
            _token_cache[subdomain] = (token, time.monotonic())
            return token

    provedor_id = _resolve_provedor_id()
    if provedor_id:
        token = _fetch_token_by_provedor_id(superadmin_url, provedor_id, secret)
        if token:
            cache_key = f'id:{provedor_id}'
            _token_cache[cache_key] = (token, time.monotonic())
            return token

    if not subdomain:
        logger.warning(
            '[SuperadminNotifier] Não foi possível recuperar token (sem SUBDOMAIN e lookup por id falhou). '
            'Configure SUPERADMIN_PROVIDER_TOKEN e SUPERADMIN_API_URL=http://127.0.0.1:8010 no .env do painel.'
        )
    return token


# ---------------------------------------------------------------------------
# Função principal de notificação
# ---------------------------------------------------------------------------

def notify_superadmin_channel_connected(canal) -> None:
    """
    Notifica o Superadmin sobre um canal recém-conectado (WhatsApp ou Instagram).
    Envia identificadores para que o dispatcher saiba rotear webhooks.

    Executado de forma segura — nunca vai quebrar o fluxo principal.
    """
    tipo = (getattr(canal, 'tipo', None) or '').strip()
    if tipo == 'instagram':
        _notify_superadmin_instagram_channel(canal)
        return

    try:
        superadmin_url = _superadmin_api_url()
        provider_token = _resolve_provider_token(superadmin_url)

        if not provider_token:
            logger.warning(
                "[SuperadminNotifier] Não foi possível obter token de integração. "
                "Notificação ao Superadmin ignorada."
            )
            return

        if not canal.waba_id:
            logger.warning(
                "[SuperadminNotifier] Canal %s não tem waba_id. Pulando notificação.", canal.id
            )
            return

        provedor_id = _resolve_provedor_id()
        if not provedor_id:
            logger.warning(
                "[SuperadminNotifier] Não foi possível determinar provedor_id. "
                "Pulando notificação."
            )
            return

        dados_extras = getattr(canal, 'dados_extras', None) or {}
        payload = {
            "provedor_id": int(provedor_id),
            "waba_id": canal.waba_id,
            "phone_number_id": getattr(canal, 'phone_number_id', '') or "",
            "phone_number": getattr(canal, 'phone_number', '') or "",
            "canal_nome": getattr(canal, 'nome', '') or "WhatsApp",
            "tipo": getattr(canal, 'tipo', '') or "whatsapp_oficial",
            # Perfil do WhatsApp Business
            "profile_picture_url": dados_extras.get('profile_picture_url') or dados_extras.get('profilePicUrl') or "",
            "business_name": dados_extras.get('verified_name') or dados_extras.get('display_phone_number') or "",
        }
        headers = {"Authorization": f"Bearer {provider_token}"}

        url = f"{superadmin_url}/api/webhooks/provider/channel-register/"
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            logger.info(
                "[SuperadminNotifier] Canal %s (%s) registrado no Superadmin. "
                "provedor_id=%s superadmin=%s",
                canal.id, canal.waba_id, provedor_id, superadmin_url,
            )
        else:
            logger.warning(
                "[SuperadminNotifier] Falha ao registrar canal no Superadmin: "
                "HTTP %s - %s",
                response.status_code, response.text[:200],
            )
    except Exception as e:
        logger.error("[SuperadminNotifier] Erro ao notificar Superadmin: %s", e)


def _notify_superadmin_instagram_channel(canal) -> None:
    """Registra canal Instagram no superadmin (mesmo padrão do WhatsApp Oficial)."""
    try:
        superadmin_url = _superadmin_api_url()
        provider_token = _resolve_provider_token(superadmin_url)
        if not provider_token:
            logger.warning(
                "[SuperadminNotifier] Token indisponível — registro Instagram no superadmin ignorado."
            )
            return

        dados_extras = getattr(canal, 'dados_extras', None) or {}
        instagram_user_id = str(dados_extras.get('instagram_user_id') or '').strip()
        if not instagram_user_id:
            logger.warning(
                "[SuperadminNotifier] Canal Instagram %s sem instagram_user_id.", canal.id
            )
            return

        provedor_id = _resolve_provedor_id()
        if not provedor_id:
            logger.warning(
                "[SuperadminNotifier] provedor_id indeterminado — registro Instagram ignorado."
            )
            return

        payload = {
            "provedor_id": int(provedor_id),
            "tipo": "instagram",
            "instagram_user_id": instagram_user_id,
            "instagram_username": dados_extras.get('instagram_username') or '',
            "canal_nome": getattr(canal, 'nome', '') or 'Instagram',
            "tenant_canal_id": canal.id,
            "profile_picture_url": dados_extras.get('profile_picture_url') or '',
        }
        headers = {"Authorization": f"Bearer {provider_token}"}
        url = f"{superadmin_url}/api/webhooks/provider/channel-register/"
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            logger.info(
                "[SuperadminNotifier] Canal Instagram %s (ig=%s) registrado no superadmin.",
                canal.id,
                instagram_user_id,
            )
        else:
            logger.warning(
                "[SuperadminNotifier] Falha ao registrar Instagram no superadmin: HTTP %s - %s",
                response.status_code,
                response.text[:200],
            )
    except Exception as exc:
        logger.error("[SuperadminNotifier] Erro ao registrar Instagram no superadmin: %s", exc)


def notify_superadmin_async(canal) -> None:
    """Wrapper assíncrono (thread daemon) para não bloquear o request."""
    t = threading.Thread(target=notify_superadmin_channel_connected, args=(canal,), daemon=True)
    t.start()


# Cache curto para não spammar log quando secret/token está errado
_lookup_auth_fail_cache: dict[str, float] = {}
_LOOKUP_AUTH_FAIL_TTL = 120


def _log_lookup_auth_fail_once(key: str, msg: str, *args) -> None:
    now = time.monotonic()
    if (now - _lookup_auth_fail_cache.get(key, 0)) < _LOOKUP_AUTH_FAIL_TTL:
        return
    _lookup_auth_fail_cache[key] = now
    logger.warning(msg, *args)


def _secret_get_json(path: str, params: dict) -> dict | None:
    """GET autenticado por ADMIN_WEBHOOK_SECRET; tenta todas as URLs do superadmin."""
    secret = _admin_webhook_secret()
    if not secret:
        _log_lookup_auth_fail_once(
            'no_secret',
            '[SuperadminNotifier] ADMIN_WEBHOOK_SECRET vazio — sync de suspensão desativada.',
        )
        return None

    last_status = None
    for base in _superadmin_api_urls():
        try:
            resp = requests.get(f"{base}{path}", params={**params, 'secret': secret}, timeout=8)
            last_status = resp.status_code
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                continue
            logger.warning(
                '[SuperadminNotifier] %s HTTP %s base=%s',
                path,
                resp.status_code,
                base,
            )
            return None
        except Exception as exc:
            logger.debug('[SuperadminNotifier] %s erro base=%s: %s', path, base, exc)

    _log_lookup_auth_fail_once(
        f'auth_fail:{path}',
        '[SuperadminNotifier] %s falhou (HTTP 401 em todas as URLs). '
        'Ajuste ADMIN_WEBHOOK_SECRET no .env para o valor do SystemConfig do superadmin '
        'ou configure SUPERADMIN_PROVIDER_TOKEN.',
        path,
    )
    if last_status and last_status != 401:
        logger.warning('[SuperadminNotifier] %s último HTTP %s', path, last_status)
    return None


def fetch_central_provedor_by_id(provedor_id: int) -> dict | None:
    """is_active/status no superadmin (id central, ex.: 10 vs local 6)."""
    if not provedor_id:
        return None
    return _secret_get_json(
        '/api/provedores/lookup-by-provedor-id/',
        {'provedor_id': int(provedor_id)},
    )


def fetch_central_provedor_by_subdomain(subdomain: str | None = None) -> dict | None:
    """Estado do provedor no superadmin via subdomínio do tenant."""
    subdomain = (subdomain or _current_subdomain()).strip()
    if not subdomain:
        return None
    return _secret_get_json(
        '/api/provedores/lookup-by-subdomain/',
        {'subdomain': subdomain},
    )


def fetch_superadmin_tenant_billing_status() -> dict | None:
    """
    Consulta o Superadmin (Bearer = integration_token do provedor) por dados de
    cobrança quando o painel está suspenso. Usa o Asaas do SystemConfig central.

    Retorna o JSON do endpoint ou None em falha de rede/HTTP não OK.
    """
    superadmin_url = _superadmin_api_url()
    provider_token = _resolve_provider_token(superadmin_url)
    if not provider_token:
        return None

    last_status = None
    for base in _superadmin_api_urls():
        url = f"{base}/api/webhooks/provider/tenant-billing-status/"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {provider_token}"},
                timeout=15,
            )
            last_status = resp.status_code
            if resp.status_code == 401:
                continue
            if not resp.ok:
                logger.warning(
                    "[SuperadminNotifier] tenant-billing-status HTTP %s base=%s: %s",
                    resp.status_code,
                    base,
                    (resp.text or "")[:200],
                )
                return None
            return resp.json()
        except Exception as exc:
            logger.debug("[SuperadminNotifier] tenant-billing-status erro base=%s: %s", base, exc)

    _log_lookup_auth_fail_once(
        'billing_401',
        "[SuperadminNotifier] tenant-billing-status HTTP 401 — verifique SUPERADMIN_PROVIDER_TOKEN.",
    )
    if last_status and last_status != 401:
        logger.warning("[SuperadminNotifier] tenant-billing-status último HTTP %s", last_status)
    return None


def report_running_version() -> bool:
    """Envia a versão do painel (APP_VERSION) ao Superadmin."""
    try:
        from niochat.__version__ import VERSION as app_version
    except Exception:
        app_version = ''
    version = str(app_version or '').strip()
    if not version:
        return False

    payload = {'version': version}
    try:
        from core.health_report import build_health_report
        payload['health'] = build_health_report()
    except Exception as exc:
        logger.debug('[SuperadminNotifier] boletim de saúde indisponível: %s', exc)

    last_status = None
    for base in _superadmin_api_urls():
        provider_token = _resolve_provider_token(base)
        if not provider_token:
            continue
        url = f"{base}/api/webhooks/provider/heartbeat/"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={'Authorization': f'Bearer {provider_token}'},
                timeout=12,
            )
            last_status = resp.status_code
            if resp.status_code == 401:
                continue
            if resp.ok:
                logger.info('[SuperadminNotifier] heartbeat versão=%s ok', version)
                return True
            logger.warning(
                '[SuperadminNotifier] heartbeat HTTP %s: %s',
                resp.status_code,
                (resp.text or '')[:200],
            )
        except Exception as exc:
            logger.debug('[SuperadminNotifier] heartbeat erro base=%s: %s', base, exc)

    if last_status == 401:
        logger.warning('[SuperadminNotifier] heartbeat 401 — verifique SUPERADMIN_PROVIDER_TOKEN.')
    return False


def notify_superadmin_system_message_read(
    *,
    superadmin_message_id: int,
    user_id: int,
    user_name: str,
    visualized_at: str,
    provedor_nome: str = '',
) -> bool:
    """
    Informa o Superadmin que um usuário do provedor leu o aviso.
    POST /api/webhooks/provider/system-message-read/
    Auth: Bearer integration_token do provedor.
    """
    if not superadmin_message_id:
        return False

    payload = {
        'superadmin_message_id': int(superadmin_message_id),
        'user_id': int(user_id) if user_id is not None else None,
        'user_name': (user_name or '').strip() or 'Usuário',
        'visualized_at': visualized_at,
        'provedor_nome': (provedor_nome or '').strip(),
    }

    last_status = None
    for base in _superadmin_api_urls():
        provider_token = _resolve_provider_token(base)
        if not provider_token:
            continue
        url = f"{base}/api/webhooks/provider/system-message-read/"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {provider_token}"},
                timeout=12,
            )
            last_status = resp.status_code
            if resp.status_code == 401:
                continue
            if resp.ok:
                logger.info(
                    "[SuperadminNotifier] leitura aviso superadmin_id=%s user=%s ok",
                    superadmin_message_id,
                    user_name,
                )
                return True
            logger.warning(
                "[SuperadminNotifier] system-message-read HTTP %s base=%s: %s",
                resp.status_code,
                base,
                (resp.text or "")[:200],
            )
        except Exception as exc:
            logger.debug(
                "[SuperadminNotifier] system-message-read erro base=%s: %s",
                base,
                exc,
            )

    if last_status == 401:
        logger.warning(
            "[SuperadminNotifier] system-message-read HTTP 401 — verifique SUPERADMIN_PROVIDER_TOKEN."
        )
    return False


def list_product_suggestions(*, voter_user_id: int | None = None, status_filter: str | None = None):
    """Lista sugestões publicas no Superadmin. Retorna (ok, data_or_error)."""
    urls = _superadmin_api_urls()
    last_error = 'Superadmin indisponivel'
    for base in urls:
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Token do provedor nao configurado'
            continue
        try:
            params = {}
            if voter_user_id:
                params['voter_user_id'] = voter_user_id
            if status_filter:
                params['status'] = status_filter
            resp = requests.get(
                f"{base}/api/webhooks/provider/suggestions/",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=15,
            )
            if resp.status_code == 401:
                last_error = 'Unauthorized no Superadmin'
                continue
            if resp.ok:
                data = resp.json()
                return True, data if isinstance(data, list) else (data.get('results') or [])
            last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        except Exception as exc:
            last_error = str(exc)
            logger.debug("[SuperadminNotifier] list suggestions erro base=%s: %s", base, exc)
    return False, last_error


def create_product_suggestion(*, title: str, description: str, author_name: str, author_user_id: int | None):
    """Cria sugestao publica no Superadmin. Retorna (ok, data_or_error)."""
    urls = _superadmin_api_urls()
    last_error = 'Superadmin indisponivel'
    for base in urls:
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Token do provedor nao configurado'
            continue
        try:
            resp = requests.post(
                f"{base}/api/webhooks/provider/suggestions/",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": title,
                    "description": description,
                    "author_name": author_name,
                    "author_user_id": author_user_id,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                last_error = 'Unauthorized no Superadmin'
                continue
            if resp.ok:
                return True, resp.json()
            last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        except Exception as exc:
            last_error = str(exc)
            logger.debug("[SuperadminNotifier] create suggestion erro base=%s: %s", base, exc)
    return False, last_error


def vote_product_suggestion(*, suggestion_id: int, voter_user_id: int, voter_name: str = ""):
    """Toggle voto no Superadmin. Retorna (ok, data_or_error)."""
    urls = _superadmin_api_urls()
    last_error = 'Superadmin indisponivel'
    for base in urls:
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Token do provedor nao configurado'
            continue
        try:
            resp = requests.post(
                f"{base}/api/webhooks/provider/suggestions/{suggestion_id}/vote/",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "voter_user_id": voter_user_id,
                    "voter_name": voter_name,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                last_error = 'Unauthorized no Superadmin'
                continue
            if resp.ok:
                return True, resp.json()
            last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        except Exception as exc:
            last_error = str(exc)
            logger.debug("[SuperadminNotifier] vote suggestion erro base=%s: %s", base, exc)
    return False, last_error


def list_product_suggestion_comments(*, suggestion_id: int):
    """Lista comentarios publicos de uma sugestao. Retorna (ok, data_or_error)."""
    urls = _superadmin_api_urls()
    last_error = 'Superadmin indisponivel'
    for base in urls:
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Token do provedor nao configurado'
            continue
        try:
            resp = requests.get(
                f"{base}/api/webhooks/provider/suggestions/{suggestion_id}/comments/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.status_code == 401:
                last_error = 'Unauthorized no Superadmin'
                continue
            if resp.ok:
                data = resp.json()
                return True, data if isinstance(data, list) else (data.get('results') or [])
            last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        except Exception as exc:
            last_error = str(exc)
            logger.debug("[SuperadminNotifier] list comments erro base=%s: %s", base, exc)
    return False, last_error


def create_product_suggestion_comment(
    *,
    suggestion_id: int,
    body: str,
    author_name: str,
    author_user_id: int,
):
    """Cria comentario publico. Retorna (ok, data_or_error)."""
    urls = _superadmin_api_urls()
    last_error = 'Superadmin indisponivel'
    for base in urls:
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Token do provedor nao configurado'
            continue
        try:
            resp = requests.post(
                f"{base}/api/webhooks/provider/suggestions/{suggestion_id}/comments/",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "body": body,
                    "author_name": author_name,
                    "author_user_id": author_user_id,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                last_error = 'Unauthorized no Superadmin'
                continue
            if resp.ok:
                return True, resp.json()
            last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        except Exception as exc:
            last_error = str(exc)
            logger.debug("[SuperadminNotifier] create comment erro base=%s: %s", base, exc)
    return False, last_error
