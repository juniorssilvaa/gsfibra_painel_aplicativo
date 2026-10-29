"""
Status de conexão do WhatsApp Oficial (Cloud API).

Mantém token/phone_number_id ao desconectar para o provedor poder
reconectar no mesmo canal (mesmo ID) via Embedded Signup.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)

# Erros Graph que indicam token/sessão inválidos → canal precisa reconectar
AUTH_DISCONNECT_CODES = frozenset({
    190,   # Access token expired / invalid
    102,   # API Session
    463,   # Session expired (legacy)
    467,   # Invalid access token
})


def is_graph_auth_error(error_code: Any, error_message: str = '', error_type: str = '') -> bool:
    """True se a Graph recusou por token/sessão (não por parâmetro de mensagem)."""
    try:
        code = int(error_code)
    except (TypeError, ValueError):
        code = None
    if code in AUTH_DISCONNECT_CODES:
        return True
    msg = (error_message or '').lower()
    etype = (error_type or '').lower()
    if 'authorization error' in msg or 'access token' in msg or 'session has expired' in msg or 'invalid oauth' in msg:
        return True
    # Código 100 é genérico (Invalid parameter); só é auth se a Meta classificar como OAuth
    if code == 100 and etype == 'oauthexception':
        return True
    return False

DISCONNECT_ACCOUNT_EVENTS = frozenset({
    'PARTNER_APP_UNINSTALLED',
    'PARTNER_REMOVED',
    'ACCOUNT_DELETED',
    'ACCOUNT_VIOLATION',
    'DISABLED_UPDATE',
    'ACCOUNT_RESTRICTION',
})


def find_whatsapp_oficial_canal(
    *,
    waba_id: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    canal_id: Optional[int] = None,
):
    """Localiza canal oficial sem exigir ativo=True (desconectado ainda precisa ser achado)."""
    from core.models import Canal

    qs = Canal.objects.filter(tipo='whatsapp_oficial')
    if canal_id:
        return qs.filter(id=canal_id).first()
    if phone_number_id:
        canal = qs.filter(phone_number_id=str(phone_number_id)).first()
        if canal:
            return canal
    if waba_id:
        return qs.filter(waba_id=str(waba_id)).order_by('-ativo', '-id').first()
    return None


def _notify_painel(canal, *, status_anterior: str, motivo: str, evento: Optional[str] = None) -> None:
    provedor = getattr(canal, 'provedor', None)
    if not provedor:
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    payload = {
        'type': 'channel_status_update',
        'data': {
            'canal_id': canal.id,
            'canal_tipo': canal.tipo,
            'waba_id': canal.waba_id,
            'phone_number_id': canal.phone_number_id,
            'status_anterior': status_anterior,
            'status_novo': canal.status,
            'ativo': canal.ativo,
            'motivo': motivo,
            'evento_meta': evento,
            'timestamp': timezone.now().isoformat(),
        },
    }
    try:
        async_to_sync(channel_layer.group_send)(f'painel_{provedor.id}', payload)
    except Exception:
        logger.debug('[WA Oficial Status] Falha WS painel_%s', provedor.id, exc_info=True)


def mark_whatsapp_oficial_disconnected(
    canal,
    *,
    reason: str = 'disconnected',
    event: Optional[str] = None,
    status: str = 'disconnected',
) -> bool:
    """
    Marca canal como desconectado mantendo credenciais (para reconectar no mesmo ID).
    Retorna True se houve mudança.
    """
    if not canal or getattr(canal, 'tipo', None) != 'whatsapp_oficial':
        return False

    old_status = (canal.status or '').strip() or 'connected'
    old_ativo = bool(canal.ativo)
    new_status = (status or 'disconnected').strip() or 'disconnected'

    if old_status == new_status and not old_ativo:
        return False

    extras = dict(canal.dados_extras or {})
    extras['disconnect_reason'] = reason
    extras['disconnect_at'] = timezone.now().isoformat()
    if event:
        extras['disconnect_event'] = event
    # Força re-subscribe no próximo Embedded Signup
    extras['app_subscribed'] = False

    canal.status = new_status
    canal.ativo = False
    canal.dados_extras = extras
    canal.save(update_fields=['status', 'ativo', 'dados_extras', 'updated_at'])

    logger.warning(
        '[WA Oficial Status] Canal %s desconectado (status=%s→%s ativo=%s→False motivo=%s evento=%s)',
        canal.id,
        old_status,
        new_status,
        old_ativo,
        reason,
        event,
    )
    _notify_painel(canal, status_anterior=old_status, motivo=reason, evento=event)
    return True


def mark_whatsapp_oficial_connected(canal, *, reason: str = 'connected') -> bool:
    if not canal or getattr(canal, 'tipo', None) != 'whatsapp_oficial':
        return False
    if not canal.token or not canal.phone_number_id:
        return False

    old_status = (canal.status or '').strip()
    if canal.ativo and old_status == 'connected':
        return False

    extras = dict(canal.dados_extras or {})
    extras.pop('disconnect_reason', None)
    extras.pop('disconnect_event', None)
    extras['last_verified_at'] = timezone.now().isoformat()

    canal.status = 'connected'
    canal.ativo = True
    canal.dados_extras = extras
    canal.save(update_fields=['status', 'ativo', 'dados_extras', 'updated_at'])

    logger.info('[WA Oficial Status] Canal %s marcado conectado (%s)', canal.id, reason)
    _notify_painel(canal, status_anterior=old_status or 'disconnected', motivo=reason)
    return True


def maybe_disconnect_on_graph_error(
    canal,
    error_code: Any,
    error_message: str = '',
    error_type: str = '',
) -> bool:
    """Se o erro Graph indicar auth inválida, marca desconectado."""
    if not is_graph_auth_error(error_code, error_message, error_type):
        return False
    return mark_whatsapp_oficial_disconnected(
        canal,
        reason=f'graph_error_{error_code}',
        event=str(error_code),
        status='expired' if str(error_code) in ('190', '100') else 'disconnected',
    )


def verify_whatsapp_oficial_connection(canal) -> Dict[str, Any]:
    """
    Consulta a Graph API (phone_number_id) para saber se o token ainda vale.
    Atualiza status no banco conforme o resultado.
    """
    if not canal or canal.tipo != 'whatsapp_oficial':
        return {'ok': False, 'connected': False, 'error': 'not_whatsapp_oficial'}

    if not canal.token or not canal.phone_number_id:
        mark_whatsapp_oficial_disconnected(canal, reason='missing_credentials')
        return {'ok': True, 'connected': False, 'status': 'disconnected', 'reason': 'missing_credentials'}

    url = f'https://graph.facebook.com/v21.0/{canal.phone_number_id}'
    try:
        resp = requests.get(
            url,
            params={'fields': 'display_phone_number,verified_name,quality_rating'},
            headers={'Authorization': f'Bearer {canal.token}'},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning('[WA Oficial Status] Falha de rede ao verificar canal %s: %s', canal.id, exc)
        return {
            'ok': False,
            'connected': bool(canal.ativo and (canal.status or '') == 'connected'),
            'error': 'network_error',
            'detail': str(exc),
            'status': canal.status,
        }

    if resp.status_code == 200:
        mark_whatsapp_oficial_connected(canal, reason='graph_verify_ok')
        data = {}
        try:
            data = resp.json() or {}
        except Exception:
            pass
        return {
            'ok': True,
            'connected': True,
            'status': 'connected',
            'display_phone_number': data.get('display_phone_number'),
            'verified_name': data.get('verified_name'),
        }

    error = {}
    try:
        error = (resp.json() or {}).get('error') or {}
    except Exception:
        pass
    code = error.get('code', resp.status_code)
    message = error.get('message') or resp.text[:200]
    maybe_disconnect_on_graph_error(canal, code, message)
    # Se não for auth mas falhou (ex. 404 phone), ainda marcar desconectado
    if canal.ativo or (canal.status or '') == 'connected':
        mark_whatsapp_oficial_disconnected(
            canal,
            reason=f'verify_http_{resp.status_code}',
            event=str(code),
        )
    return {
        'ok': True,
        'connected': False,
        'status': canal.status,
        'error_code': code,
        'error_message': message,
    }
