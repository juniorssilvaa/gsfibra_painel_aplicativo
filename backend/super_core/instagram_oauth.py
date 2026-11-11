"""
Callback OAuth Instagram centralizado em api.niohub.com.br (superadmin).

A Meta valida redirect_uri contra o painel; o token exchange ocorre aqui e o
canal é finalizado no tenant via webhook interno (ADMIN_WEBHOOK_SECRET).
"""
from __future__ import annotations

import base64
import os
import json
import logging
import re

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

INSTAGRAM_APP_ID = (getattr(settings, 'INSTAGRAM_APP_ID', None) or '').strip()
INSTAGRAM_APP_SECRET = (getattr(settings, 'INSTAGRAM_APP_SECRET', None) or '').strip()


LOCAL_OAUTH_API_URL_DEFAULT = 'https://api-local.niohub.com.br'


def get_central_instagram_redirect_uri(is_local: bool = False) -> str:
    if is_local:
        custom = (
            (getattr(settings, 'BACKEND_URL', None) or '').strip().rstrip('/')
            or (os.environ.get('BACKEND_URL') or '').strip().rstrip('/')
        )
        base = custom or LOCAL_OAUTH_API_URL_DEFAULT
        return f'{base.rstrip("/")}/api/auth/instagram/callback/'
    return 'https://api.niohub.com.br/api/auth/instagram/callback/'


def _b64url_decode(value: str) -> str:
    pad = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad).decode('utf-8')


def parse_instagram_state(state: str):
    raw = state or ''
    is_local = raw.endswith('_local') or '_local' in raw
    frontend_origin = None
    origin_match = re.search(r'_r([A-Za-z0-9_-]+)', raw)
    if origin_match:
        try:
            frontend_origin = _b64url_decode(origin_match.group(1))
        except Exception:
            frontend_origin = None
    clean = re.sub(r'_r[A-Za-z0-9_-]+', '', raw).replace('_local', '')
    match = re.match(r'instagram_c(\d+)_p(\d+)', clean)
    if not match:
        return None, None, is_local, frontend_origin
    return int(match.group(1)), int(match.group(2)), is_local, frontend_origin


def _tenant_base_url(subdomain: str) -> str:
    subdomain = (subdomain or '').strip().rstrip('/')
    if not subdomain:
        return ''
    if subdomain.startswith('http://') or subdomain.startswith('https://'):
        return subdomain.rstrip('/')
    return f'https://{subdomain}'


def _resolve_frontend_url(is_local: bool, frontend_origin: str | None) -> str:
    if frontend_origin:
        return frontend_origin.rstrip('/')
    if is_local:
        return 'http://localhost:8012'
    return 'https://app.niohub.com.br'


def _classify_oauth_error(exc: Exception) -> tuple[str, str]:
    msg = str(exc) or exc.__class__.__name__
    upper = msg.upper()
    if 'INSTAGRAM_APP_ID' in upper or 'INSTAGRAM_APP_SECRET' in upper or 'ADMIN_WEBHOOK_SECRET' in upper:
        return 'config_error', msg
    if 'TENANT RETORNOU' in upper or 'FALHA AO FINALIZAR CANAL' in upper or 'PROVEDOR' in upper and 'SUBDOMAIN' in upper:
        return 'tenant_finalize_error', msg
    if 'INSTAGRAM TOKEN' in upper or 'OAUTH' in upper:
        return 'instagram_api_error', msg
    return 'token_exchange_error', msg


def _render_oauth_popup_result(
    front_url: str,
    provider_id: int,
    *,
    success: bool,
    channel_id: int | None = None,
    error: str | None = None,
    error_detail: str | None = None,
    frontend_origin: str | None = None,
) -> HttpResponse:
    if success:
        query = f'instagram_oauth_success=1&channel_id={channel_id}'
        payload = {
            'type': 'INSTAGRAM_OAUTH_SUCCESS',
            'channel_id': channel_id,
            'provider_id': provider_id,
        }
        title = 'Instagram conectado!'
        message = 'Você pode fechar esta janela.'
    else:
        query = f'instagram_oauth_error={error or "unknown"}'
        payload = {
            'type': 'INSTAGRAM_OAUTH_ERROR',
            'error': error or 'unknown',
            'provider_id': provider_id,
        }
        if error_detail:
            payload['error_detail'] = error_detail[:300]
        title = 'Erro ao conectar Instagram'
        message = 'Você pode fechar esta janela e tentar novamente.'

    target_url = f'{front_url.rstrip("/")}/app/accounts/{provider_id}/canais/configurar?{query}'
    payload_json = json.dumps(payload)
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
      <head><meta charset="utf-8" /><title>{title}</title></head>
      <body style="font-family:sans-serif;text-align:center;padding-top:48px;background:#0f172a;color:#fff;">
        <h2>{title}</h2><p>{message}</p>
        <p id="fallback-link" style="margin-top:24px;display:none;">
          <a href="{target_url}" style="color:#93c5fd;">Continuar para Configurar Canais</a>
        </p>
        <script>
          (function () {{
            var payload = {payload_json};
            var targetUrl = {json.dumps(target_url)};
            var seen = [];
            function notify(target) {{
              if (!target || seen.indexOf(target) >= 0) return;
              seen.push(target);
              try {{
                if (target.closed) return;
                target.postMessage(payload, '*');
              }} catch (e) {{}}
            }}
            function notifyAll() {{
              try {{
                if (!window.opener || window.opener.closed) return;
                notify(window.opener);
                try {{ notify(window.opener.parent); }} catch (e) {{}}
                try {{ if (window.opener.top) notify(window.opener.top); }} catch (e) {{}}
              }} catch (e) {{}}
            }}
            notifyAll();
            setTimeout(notifyAll, 150);
            setTimeout(notifyAll, 500);
            setTimeout(function () {{
              notifyAll();
              try {{ window.close(); }} catch (e) {{}}
            }}, 900);
            setTimeout(function () {{
              var link = document.getElementById('fallback-link');
              if (link) link.style.display = 'block';
              if (!window.closed) {{
                window.location.replace(targetUrl);
              }}
            }}, 2200);
          }})();
        </script>
      </body>
    </html>
    """
    return HttpResponse(html)


def _exchange_code(code: str, redirect_uri: str) -> tuple[str, str, str, int | None]:
    if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
        raise RuntimeError('INSTAGRAM_APP_ID/SECRET não configurados no superadmin.')

    resp = requests.post(
        'https://api.instagram.com/oauth/access_token',
        data={
            'client_id': INSTAGRAM_APP_ID,
            'client_secret': INSTAGRAM_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code': code,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f'Instagram token: HTTP {resp.status_code}: {(resp.text or "")[:300]}'
        )
    payload = resp.json()
    if isinstance(payload.get('data'), list) and payload['data']:
        item = payload['data'][0]
        short_token = item.get('access_token')
        user_id = str(item.get('user_id') or '')
        permissions = item.get('permissions') or ''
    else:
        short_token = payload.get('access_token')
        user_id = str(payload.get('user_id') or '')
        permissions = ''

    long_resp = requests.get(
        'https://graph.instagram.com/access_token',
        params={
            'grant_type': 'ig_exchange_token',
            'client_secret': INSTAGRAM_APP_SECRET,
            'access_token': short_token,
        },
        timeout=30,
    )
    if not long_resp.ok:
        raise RuntimeError(
            f'Instagram long-lived token: HTTP {long_resp.status_code}: {(long_resp.text or "")[:300]}'
        )
    long_data = long_resp.json()
    long_token = long_data.get('access_token') or short_token
    expires_in = long_data.get('expires_in')
    return long_token, user_id, permissions, expires_in


def _fetch_instagram_profile(access_token: str) -> dict:
    try:
        resp = requests.get(
            'https://graph.instagram.com/v21.0/me',
            params={
                'fields': 'user_id,username,name,profile_picture_url',
                'access_token': access_token,
            },
            timeout=20,
        )
        if resp.ok:
            return resp.json()
    except Exception as exc:
        logger.warning('[InstagramOAuth] Falha ao buscar perfil Instagram: %s', exc)
    return {}


def _register_instagram_canal_superadmin(
    provedor,
    *,
    tenant_channel_id: int,
    access_token: str,
    oauth_user_id: str,
    canal_nome: str = 'Instagram',
) -> None:
    """Regista canal Instagram no superadmin após OAuth (não depende do notifier do tenant)."""
    profile = _fetch_instagram_profile(access_token)
    ig_user_id = str(profile.get('user_id') or oauth_user_id or '').strip()
    if not ig_user_id:
        logger.warning(
            '[InstagramOAuth] Sem instagram_user_id para registar canal tenant=%s no superadmin.',
            tenant_channel_id,
        )
        return

    from .webhook_dispatcher import upsert_instagram_canal

    display_name = profile.get('username') or profile.get('name') or canal_nome or 'Instagram'
    canal, created = upsert_instagram_canal(
        provedor,
        instagram_user_id=ig_user_id,
        instagram_username=profile.get('username') or '',
        tenant_canal_id=tenant_channel_id,
        canal_nome=display_name,
        profile_picture_url=profile.get('profile_picture_url') or '',
    )
    logger.info(
        '[InstagramOAuth] Canal superadmin %s (id=%s, ig=%s, tenant_canal=%s)',
        'criado' if created else 'actualizado',
        canal.id,
        ig_user_id,
        tenant_channel_id,
    )


def _finalize_on_tenant(
    subdomain: str,
    channel_id: int,
    access_token: str,
    user_id: str,
    permissions: str,
    expires_in,
    *,
    is_local: bool = False,
) -> None:
    secret = (getattr(settings, 'ADMIN_WEBHOOK_SECRET', None) or '').strip()
    if not secret:
        raise RuntimeError('ADMIN_WEBHOOK_SECRET não configurado no superadmin.')

    tenant_base = _tenant_base_url(subdomain)
    if is_local:
        local_override = (
            (getattr(settings, 'TENANT_WEBHOOK_BASE_URL', None) or '').strip().rstrip('/')
            or (os.environ.get('TENANT_WEBHOOK_BASE_URL') or '').strip().rstrip('/')
        )
        if local_override:
            tenant_base = local_override
    if not tenant_base:
        raise RuntimeError('Provedor sem subdomain configurado no superadmin.')

    url = f'{tenant_base}/api/webhooks/internal/instagram-oauth-finish/'
    resp = requests.post(
        url,
        json={
            'channel_id': channel_id,
            'access_token': access_token,
            'user_id': user_id,
            'permissions': permissions,
            'expires_in': expires_in,
        },
        headers={'X-Admin-Webhook-Secret': secret},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f'Tenant retornou HTTP {resp.status_code}: {(resp.text or "")[:300]}')
    data = resp.json() if resp.content else {}
    if not data.get('success'):
        raise RuntimeError(data.get('error') or 'Falha ao finalizar canal no tenant.')


@csrf_exempt
@require_http_methods(['GET', 'HEAD'])
def instagram_oauth_callback(request):
    """GET /api/auth/instagram/callback/ — hospedado no superadmin (api.niohub.com.br)."""
    state = request.GET.get('state') or ''
    channel_id, provider_id, is_local, frontend_origin = parse_instagram_state(state)
    front_url = _resolve_frontend_url(is_local, frontend_origin)
    fallback_provider = provider_id or 1

    if request.method == 'HEAD':
        return JsonResponse({}, status=200)

    oauth_error = request.GET.get('error')
    if oauth_error:
        return _render_oauth_popup_result(
            front_url,
            fallback_provider,
            success=False,
            error=oauth_error,
            frontend_origin=frontend_origin,
        )

    code = (request.GET.get('code') or '').replace('#_', '').strip()
    if not code or not channel_id or not provider_id:
        return _render_oauth_popup_result(
            front_url,
            fallback_provider,
            success=False,
            error='no_code',
            frontend_origin=frontend_origin,
        )

    redirect_uri = get_central_instagram_redirect_uri(is_local)

    try:
        long_token, user_id, permissions, expires_in = _exchange_code(code, redirect_uri)

        from .models import Provedor

        provedor = Provedor.objects.filter(id=provider_id).first()
        tenant_subdomain = (provedor.subdomain if provedor else '') or ''
        if not is_local and (not provedor or not tenant_subdomain):
            raise RuntimeError(f'Provedor {provider_id} não encontrado ou sem subdomain.')
        if is_local and not tenant_subdomain:
            tenant_subdomain = 'local'

        _finalize_on_tenant(
            tenant_subdomain,
            channel_id,
            long_token,
            user_id,
            permissions,
            expires_in,
            is_local=is_local,
        )

        if provedor:
            _register_instagram_canal_superadmin(
                provedor,
                tenant_channel_id=channel_id,
                access_token=long_token,
                oauth_user_id=user_id,
            )

        logger.info(
            '[InstagramOAuth] Canal %s finalizado no tenant %s (provedor=%s)',
            channel_id,
            provedor.subdomain if provedor else tenant_subdomain,
            provider_id,
        )
        return _render_oauth_popup_result(
            front_url,
            provider_id,
            success=True,
            channel_id=channel_id,
            frontend_origin=frontend_origin,
        )
    except Exception as exc:
        error_code, error_detail = _classify_oauth_error(exc)
        logger.exception(
            '[InstagramOAuth] Erro no callback central (canal=%s, code=%s): %s',
            channel_id,
            error_code,
            exc,
        )
        return _render_oauth_popup_result(
            front_url,
            fallback_provider,
            success=False,
            error=error_code,
            error_detail=error_detail,
            frontend_origin=frontend_origin,
        )
