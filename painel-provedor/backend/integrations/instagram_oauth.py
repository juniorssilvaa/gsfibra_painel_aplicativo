"""
Instagram Business Login OAuth.

Documentação: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login
"""
import base64
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Canal
from integrations.meta_oauth import get_backend_url, get_frontend_url, get_local_frontend_url

logger = logging.getLogger(__name__)

META_APP_ID = getattr(settings, 'FACEBOOK_APP_ID', None) or '713538217881661'
INSTAGRAM_APP_ID = (getattr(settings, 'INSTAGRAM_APP_ID', None) or '').strip()
INSTAGRAM_APP_SECRET = (getattr(settings, 'INSTAGRAM_APP_SECRET', None) or '').strip()

INSTAGRAM_SCOPES = [
    'instagram_business_basic',
    'instagram_business_manage_messages',
    'instagram_business_manage_comments',
]


def validate_instagram_oauth_config() -> None:
    """
    Instagram Business Login usa credenciais próprias (Instagram App ID/Secret),
    diferentes do Facebook App ID usado no WhatsApp/Meta Login.
    """
    if not INSTAGRAM_APP_ID:
        raise RuntimeError(
            'INSTAGRAM_APP_ID não configurado. '
            'No Meta App Dashboard: Instagram → API setup with Instagram login → '
            'Set up Instagram business login → Business login settings → Instagram App ID.'
        )
    if INSTAGRAM_APP_ID == META_APP_ID:
        raise RuntimeError(
            'INSTAGRAM_APP_ID não pode ser o mesmo Facebook App ID. '
            'Use o Instagram App ID exibido em Business login settings no painel da Meta.'
        )
    if not INSTAGRAM_APP_SECRET:
        raise RuntimeError(
            'INSTAGRAM_APP_SECRET não configurado. '
            'Use o Instagram App Secret em Business login settings (não o App Secret geral do Facebook).'
        )


def get_instagram_redirect_uri(
    request=None,
    frontend_origin: str | None = None,
    is_local: bool = False,
) -> str:
    """
    Callback OAuth centralizado em api.niohub.com.br (mesmo padrão do WhatsApp).
    O frontend_origin fica no state apenas para redirecionar o popup de volta ao tenant.
    """
    from integrations.meta_oauth import get_central_oauth_api_url

    base = get_central_oauth_api_url(is_local)
    return f"{base.rstrip('/')}/api/auth/instagram/callback/"


def _b64url_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode('utf-8')).decode('ascii').rstrip('=')


def _b64url_decode(value: str) -> str:
    pad = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad).decode('utf-8')


def is_allowed_frontend_origin(origin: str) -> bool:
    if not origin:
        return False
    normalized = origin.rstrip('/')
    allowed = {
        'http://localhost:8012',
        'http://127.0.0.1:8012',
        'https://chat-local.niohub.com.br',
        'https://chat.niohub.com.br',
        get_frontend_url().rstrip('/'),
        get_local_frontend_url().rstrip('/'),
    }
    for item in getattr(settings, 'CORS_ALLOWED_ORIGINS', []) or []:
        if item:
            allowed.add(str(item).rstrip('/'))
    if normalized in allowed:
        return True
    try:
        from urllib.parse import urlparse

        host = (urlparse(normalized).netloc or '').lower()
        if host.endswith('.niohub.com.br'):
            return True
    except Exception:
        pass
    return False


def build_instagram_oauth_state(
    channel_id: int,
    provider_id: int,
    frontend_origin: str | None = None,
    local_dev: bool = False,
) -> str:
    state = f'instagram_c{channel_id}_p{provider_id}'
    if frontend_origin and is_allowed_frontend_origin(frontend_origin):
        state += f'_r{_b64url_encode(frontend_origin.rstrip("/"))}'
    if local_dev:
        state += '_local'
    return state


def build_instagram_oauth_url(
    channel_id: int,
    provider_id: int,
    frontend_origin: str | None = None,
    local_dev: bool = False,
    request=None,
) -> str:
    validate_instagram_oauth_config()
    origin = frontend_origin
    if not origin and local_dev:
        origin = get_local_frontend_url()
    params = {
        'client_id': INSTAGRAM_APP_ID,
        'redirect_uri': get_instagram_redirect_uri(request, origin, local_dev),
        'response_type': 'code',
        'scope': ','.join(INSTAGRAM_SCOPES),
        'state': build_instagram_oauth_state(channel_id, provider_id, origin, local_dev),
        'enable_fb_login': 'true',
    }
    return f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"


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


def resolve_instagram_frontend_url(is_local: bool = False, frontend_origin: str | None = None) -> str:
    if frontend_origin and is_allowed_frontend_origin(frontend_origin):
        return frontend_origin.rstrip('/')
    if is_local:
        return get_local_frontend_url()
    return get_frontend_url()


def render_instagram_oauth_result(
    front_url: str,
    provider_id: int,
    *,
    success: bool,
    channel_id: int | None = None,
    error: str | None = None,
) -> HttpResponse:
    """Fecha popup e avisa a aba pai; fallback redireciona no mesmo domínio de origem."""
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
        title = 'Erro ao conectar Instagram'
        message = 'Você pode fechar esta janela e tentar novamente.'

    target_url = f'{front_url.rstrip("/")}/app/accounts/{provider_id}/canais/configurar?{query}'
    payload_json = json.dumps(payload)

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8" />
        <title>{title}</title>
      </head>
      <body style="font-family: sans-serif; text-align: center; padding-top: 48px; background: #0f172a; color: #fff;">
        <h2>{title}</h2>
        <p>{message}</p>
        <p id="fallback-link" style="margin-top: 24px; display: none;">
          <a href="{target_url}" style="color: #93c5fd;">Continuar para Configurar Canais</a>
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


def exchange_code_for_short_token(code: str, redirect_uri: str):
    validate_instagram_oauth_config()

    response = requests.post(
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
    if not response.ok:
        logger.error(
            '[InstagramOAuth] Token exchange failed: HTTP %s redirect_uri=%s body=%s',
            response.status_code,
            redirect_uri,
            (response.text or '')[:500],
        )
        response.raise_for_status()
    payload = response.json()

    if isinstance(payload.get('data'), list) and payload['data']:
        item = payload['data'][0]
        return (
            item.get('access_token'),
            str(item.get('user_id') or ''),
            item.get('permissions') or '',
        )

    return (
        payload.get('access_token'),
        str(payload.get('user_id') or ''),
        '',
    )


def exchange_long_lived_token(short_token: str) -> dict:
    response = requests.get(
        'https://graph.instagram.com/access_token',
        params={
            'grant_type': 'ig_exchange_token',
            'client_secret': INSTAGRAM_APP_SECRET,
            'access_token': short_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_instagram_profile(access_token: str) -> dict:
    try:
        response = requests.get(
            'https://graph.instagram.com/v21.0/me',
            params={
                'fields': 'user_id,username,name,profile_picture_url',
                'access_token': access_token,
            },
            timeout=20,
        )
        if response.ok:
            return response.json()
    except Exception as exc:
        logger.warning('Falha ao buscar perfil Instagram: %s', exc)
    return {}


def finalize_instagram_channel(canal: Canal, access_token: str, user_id: str, permissions: str, expires_in=None):
    profile = fetch_instagram_profile(access_token)
    resolved_user_id = str(profile.get('user_id') or user_id or '').strip()
    dados = dict(canal.dados_extras or {})
    dados.update({
        'instagram_user_id': resolved_user_id,
        'instagram_username': profile.get('username'),
        'instagram_name': profile.get('name'),
        'permissions': permissions,
        'profile_picture_url': profile.get('profile_picture_url'),
        'oauth_provider': 'instagram_business_login',
    })
    if expires_in:
        dados['token_expires_at'] = (
            datetime.utcnow() + timedelta(seconds=int(expires_in))
        ).isoformat() + 'Z'

    canal.token = access_token
    canal.status = 'connected'
    canal.dados_extras = dados
    canal.save(update_fields=['token', 'status', 'dados_extras', 'updated_at'])

    from conversations.models import Inbox

    Inbox.objects.get_or_create(
        name=f'Instagram - {canal.nome}',
        channel_type='instagram',
        provedor=canal.provedor,
        channel_id=str(canal.id),
        defaults={
            'additional_attributes': {
                'canal_id': canal.id,
                'instagram_user_id': dados.get('instagram_user_id'),
            }
        },
    )

    try:
        from integrations.superadmin_notifier import notify_superadmin_async
        notify_superadmin_async(canal)
    except Exception as exc:
        logger.warning('Falha ao notificar superadmin sobre canal Instagram %s: %s', canal.id, exc)


@csrf_exempt
@require_http_methods(['POST'])
def instagram_oauth_finish_internal(request):
    """
    Finaliza canal Instagram no tenant após OAuth centralizado (api.niohub.com.br).
    Chamado pelo superadmin com X-Admin-Webhook-Secret.
    """
    expected = (getattr(settings, 'ADMIN_WEBHOOK_SECRET', None) or '').strip()
    provided = (request.headers.get('X-Admin-Webhook-Secret') or '').strip()
    if not expected or provided != expected:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    channel_id = data.get('channel_id')
    access_token = (data.get('access_token') or '').strip()
    user_id = str(data.get('user_id') or '')
    permissions = data.get('permissions') or ''
    expires_in = data.get('expires_in')

    if not channel_id or not access_token:
        return JsonResponse(
            {'success': False, 'error': 'channel_id e access_token são obrigatórios'},
            status=400,
        )

    try:
        canal = Canal.objects.select_related('provedor').get(pk=channel_id, tipo='instagram')
        finalize_instagram_channel(canal, access_token, user_id, permissions, expires_in)
        return JsonResponse({'success': True, 'channel_id': canal.id})
    except Canal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Canal não encontrado'}, status=404)
    except Exception as exc:
        logger.exception('[InstagramOAuth] Erro ao finalizar canal interno %s', channel_id)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
@require_http_methods(['GET', 'HEAD'])
def instagram_callback(request):
    state = request.GET.get('state') or ''
    channel_id, provider_id, is_local, frontend_origin = parse_instagram_state(state)
    front_url = resolve_instagram_frontend_url(is_local, frontend_origin)
    fallback_provider = provider_id or 1

    if request.method == 'HEAD':
        return JsonResponse({}, status=200)

    oauth_error = request.GET.get('error')
    if oauth_error:
        return render_instagram_oauth_result(
            front_url,
            fallback_provider,
            success=False,
            error=oauth_error,
        )

    code = (request.GET.get('code') or '').replace('#_', '').strip()
    if not code or not channel_id:
        return render_instagram_oauth_result(
            front_url,
            fallback_provider,
            success=False,
            error='no_code',
        )

    redirect_uri = get_instagram_redirect_uri(
        frontend_origin=frontend_origin,
        is_local=is_local,
    )

    try:
        short_token, user_id, permissions = exchange_code_for_short_token(code, redirect_uri)
        long_data = exchange_long_lived_token(short_token)
        long_token = long_data.get('access_token') or short_token
        expires_in = long_data.get('expires_in')

        canal = Canal.objects.select_related('provedor').get(pk=channel_id, tipo='instagram')
        finalize_instagram_channel(canal, long_token, user_id, permissions, expires_in)

        pid = canal.provedor_id or fallback_provider
        return render_instagram_oauth_result(
            front_url,
            pid,
            success=True,
            channel_id=canal.id,
        )
    except Exception as exc:
        logger.exception(
            'Erro no callback OAuth do Instagram (canal=%s, is_local=%s, redirect_uri=%s): %s',
            channel_id,
            is_local,
            redirect_uri,
            exc,
        )
        return render_instagram_oauth_result(
            front_url,
            fallback_provider,
            success=False,
            error='token_exchange_error',
        )
