"""Push FCM para o app CHAT-NIOHUB (atendentes)."""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

_firebase_app = None


def initialize_firebase():
    global _firebase_app
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning('[AgentPush] firebase-admin não instalado')
        return None

    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app

    cred_path = (os.environ.get('FIREBASE_CREDENTIALS') or '').strip()
    if cred_path and not os.path.exists(cred_path):
        logger.warning('[AgentPush] FIREBASE_CREDENTIALS não existe: %s', cred_path)
        cred_path = ''

    if not cred_path:
        from django.conf import settings
        base_dir = getattr(settings, 'BASE_DIR', None)
        candidates = [
            'firebase-credentials.json',
            'firebase_credentials.json',
            'service_account_key.json',
        ]
        if base_dir:
            candidates.extend([
                str(base_dir / 'firebase-credentials.json'),
                str(base_dir / 'firebase_credentials.json'),
                str(base_dir / 'service_account_key.json'),
            ])
        candidates.extend([
            '/opt/app_provedor/firebase-credentials.json',
            '/opt/app_provedor/backend/firebase-credentials.json',
        ])
        for p in candidates:
            if os.path.exists(p):
                cred_path = p
                break

    if not cred_path or not os.path.exists(cred_path):
        logger.warning('[AgentPush] Credenciais Firebase não encontradas')
        return None

    try:
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info('[AgentPush] Firebase OK: %s', cred_path)
        return _firebase_app
    except Exception as exc:
        logger.error('[AgentPush] Firebase init falhou: %s', exc)
        return None


def register_agent_device(
    *,
    user,
    token: str,
    platform: str = '',
    device_name: str = '',
):
    from core.models import AgentPushDevice

    token = (token or '').strip()
    if not token:
        raise ValueError('token é obrigatório')

    # Um token pertence a um único usuário — reassocia se necessário.
    AgentPushDevice.objects.filter(token=token).exclude(user=user).delete()

    device, _created = AgentPushDevice.objects.update_or_create(
        token=token,
        defaults={
            'user': user,
            'platform': (platform or '')[:20],
            'device_name': (device_name or '')[:120],
            'active': True,
        },
    )
    return device


def deactivate_agent_device(*, user, token: str = '') -> int:
    from core.models import AgentPushDevice

    qs = AgentPushDevice.objects.filter(user=user, active=True)
    if token:
        qs = qs.filter(token=token.strip())
    return qs.update(active=False)


def _tokens_for_users(user_ids: Sequence[int]) -> List[str]:
    from core.models import AgentPushDevice

    if not user_ids:
        return []
    return list(
        AgentPushDevice.objects.filter(
            user_id__in=list(user_ids),
            active=True,
        )
        .exclude(token='')
        .values_list('token', flat=True)
    )


def send_push_to_users(
    user_ids: Iterable[int],
    *,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict[str, Any]:
    ids = [int(u) for u in user_ids if u]
    tokens = _tokens_for_users(ids)
    if not tokens:
        return {'sent': False, 'reason': 'sem_devices', 'success': 0, 'failure': 0}

    app = initialize_firebase()
    if not app:
        return {'sent': False, 'reason': 'firebase_not_initialized', 'success': 0, 'failure': 0}

    try:
        from firebase_admin import messaging
    except ImportError:
        return {'sent': False, 'reason': 'firebase_admin_missing', 'success': 0, 'failure': 0}

    payload_data = {str(k): str(v) for k, v in (data or {}).items() if v is not None}
    success = 0
    failure = 0
    invalid_tokens: List[str] = []

    # Envia em lotes de até 500 (limite multicast FCM).
    batch_size = 500
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        message = messaging.MulticastMessage(
            tokens=batch,
            notification=messaging.Notification(title=title, body=body),
            data=payload_data,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='niohub_agent_alerts',
                    sound='default',
                    color='#EA580C',
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound='default',
                        badge=1,
                    ),
                ),
            ),
        )
        try:
            if hasattr(messaging, 'send_each_for_multicast'):
                response = messaging.send_each_for_multicast(message)
            else:
                response = messaging.send_multicast(message)
            success += int(getattr(response, 'success_count', 0) or 0)
            failure += int(getattr(response, 'failure_count', 0) or 0)
            responses = getattr(response, 'responses', None) or []
            for idx, resp in enumerate(responses):
                if getattr(resp, 'success', False):
                    continue
                exc = getattr(resp, 'exception', None)
                code = ''
                if exc is not None:
                    code = getattr(exc, 'code', '') or str(exc)
                if 'registration-token-not-registered' in str(code).lower() or \
                   'invalid-registration-token' in str(code).lower():
                    invalid_tokens.append(batch[idx])
        except Exception as exc:
            logger.error('[AgentPush] Falha no envio multicast: %s', exc)
            failure += len(batch)

    if invalid_tokens:
        from core.models import AgentPushDevice
        AgentPushDevice.objects.filter(token__in=invalid_tokens).update(active=False)

    logger.info(
        '[AgentPush] Enviado users=%s success=%s failure=%s',
        len(ids), success, failure,
    )
    return {
        'sent': success > 0,
        'reason': 'ok' if success else 'envio_falhou',
        'success': success,
        'failure': failure,
    }


def notify_agents_push(
    *,
    user_ids: Sequence[int],
    title: str,
    body: str,
    conversation_id: Optional[int] = None,
    event_type: str = 'waiting',
) -> dict[str, Any]:
    data = {
        'type': event_type,
        'conversation_id': conversation_id or '',
        'click_action': 'FLUTTER_NOTIFICATION_CLICK',
    }
    return send_push_to_users(user_ids, title=title, body=body, data=data)
