"""Envio central de push FCM (legado app_provedor/api/push_service.py)."""
import logging
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .firebase_config import initialize_firebase
from .models import (
    MobileAppUser,
    MobileDevice,
    MobileInAppWarning,
    MobileNotificationLog,
)

logger = logging.getLogger(__name__)

_firebase_app = initialize_firebase()


def send_push_notification_core(
    provedor_id,
    title,
    message,
    data=None,
    source='system',
    target_customer_ids=None,
    segment_type='all',
    segment_tags=None,
    segment_search=None,
):
    global _firebase_app
    if not provedor_id:
        raise ValueError('provedor_id é obrigatório para envio de push.')

    def _expand_target_ids(raw_ids):
        if not raw_ids:
            return []
        ids = [raw_ids] if isinstance(raw_ids, str) else list(raw_ids)
        expanded = []
        for item in ids:
            if item is None:
                continue
            parts = [p.strip() for p in str(item).split(',') if p.strip()]
            expanded.extend(parts or [str(item)])
        return expanded

    def _create_in_app_warning_for_targets(cpf_list, *, title_text=title, message_text=message):
        """Garante aviso no sino do app mesmo se o FCM falhar."""
        try:
            target_cpfs_str = None
            is_broadcast = (
                segment_type == 'all'
                and not target_customer_ids
                and not segment_tags
                and not segment_search
            )
            if not is_broadcast:
                cleaned = []
                for c in cpf_list or []:
                    digits = re.sub(r'\D', '', str(c or ''))
                    if digits and digits not in cleaned:
                        cleaned.append(digits)
                if cleaned:
                    target_cpfs_str = ','.join(cleaned)
            warning_type = str((data or {}).get('type') or 'info')[:20]
            if source == 'support_chat':
                warning_type = 'support_chat'
            # Aviso in-app: corpo = mensagem; título = atendente ou texto (sem provedor)
            warn_title = title_text
            warn_message = message_text or title_text
            if not message_text and title_text:
                warn_title = 'Atendimento'
                warn_message = title_text
            if is_broadcast or target_cpfs_str:
                MobileInAppWarning.objects.create(
                    provedor_id=provedor_id,
                    title=warn_title,
                    message=warn_message,
                    type=warning_type,
                    target_cpfs=target_cpfs_str,
                    active=True,
                    sticky=False,
                    show_home=False,
                )
                limit_date = timezone.now() - timedelta(days=30)
                MobileInAppWarning.objects.filter(
                    provedor_id=provedor_id,
                    created_at__lt=limit_date,
                ).exclude(target_cpfs__isnull=True).exclude(target_cpfs='').delete()
        except Exception as exc:
            logger.error('[mobile_app] InAppWarning create error: %s', exc)

    if not _firebase_app:
        _firebase_app = initialize_firebase()
    if not _firebase_app:
        if target_customer_ids:
            _create_in_app_warning_for_targets(_expand_target_ids(target_customer_ids))
        return {'status': 'error', 'reason': 'firebase_not_initialized'}

    try:
        from firebase_admin import messaging
    except ImportError:
        if target_customer_ids:
            _create_in_app_warning_for_targets(_expand_target_ids(target_customer_ids))
        return {'status': 'error', 'reason': 'firebase_admin_missing'}

    query = (
        MobileDevice.objects.filter(provedor_id=provedor_id, active=True)
        .exclude(push_token__isnull=True)
        .exclude(push_token='')
    )

    if target_customer_ids:
        ids = [target_customer_ids] if isinstance(target_customer_ids, str) else list(target_customer_ids)
        # Aceita lista de CPFs separados por vírgula
        expanded = []
        for item in ids:
            if item is None:
                continue
            parts = [p.strip() for p in str(item).split(',') if p.strip()]
            expanded.extend(parts or [str(item)])
        ids_digits = {re.sub(r'\D', '', str(x)) for x in expanded if re.sub(r'\D', '', str(x))}
        if not ids_digits:
            query = query.none()
        else:
            # Match por CPF só com dígitos (evita falha com máscara / zeros)
            user_ids = []
            for uid, cpf in (
                MobileAppUser.objects.filter(provedor_id=provedor_id)
                .values_list('id', 'cpf')
            ):
                if re.sub(r'\D', '', str(cpf or '')) in ids_digits:
                    user_ids.append(uid)
            ext_ids = list(ids_digits) + list(expanded)
            query = query.filter(
                Q(user_id__in=user_ids)
                | Q(user__cpf__in=ext_ids)
                | Q(user__external_id__in=ext_ids)
                | Q(user__customer_id__in=ext_ids)
            )

    if segment_type == 'active':
        query = query.filter(user__active=True)
    elif segment_type == 'inactive':
        query = query.filter(user__active=False)
    elif segment_type == 'selected' and target_customer_ids:
        query = query.filter(user__active=True)
    elif segment_type != 'inactive':
        query = query.filter(Q(user__isnull=True) | Q(user__active=True))
    elif segment_type == 'tags' and segment_tags:
        tags_list = [t.strip() for t in str(segment_tags).split(',') if t.strip()]
        if tags_list:
            tags_q = Q()
            for tag in tags_list:
                tags_q |= Q(user__tags__icontains=tag)
            query = query.filter(tags_q)

    if segment_search:
        text = str(segment_search).strip()
        if text:
            digits = re.sub(r'\D', '', text)
            search_q = Q(user__name__icontains=text) | Q(user__email__icontains=text)
            if digits:
                search_q |= (
                    Q(user__cpf__icontains=digits)
                    | Q(user__customer_id__icontains=digits)
                    | Q(user__external_id__icontains=digits)
                )
            else:
                search_q |= Q(user__customer_id__icontains=text) | Q(user__external_id__icontains=text)
            query = query.filter(search_q)

    devices = query.select_related('user')
    device_rows = list(
        devices.values(
            'push_token',
            'user_id',
            'user__name',
            'user__cpf',
            'user__pppoe_login',
            'user__customer_id',
            'platform',
            'model',
        )
    )
    # Um registro por token (último device ganha)
    token_info = {}
    for row in device_rows:
        tok = row.get('push_token')
        if tok:
            token_info[tok] = row

    tokens = list(token_info.keys())

    if not tokens:
        total = MobileDevice.objects.filter(provedor_id=provedor_id).count()
        active = MobileDevice.objects.filter(provedor_id=provedor_id, active=True).count()
        with_token = (
            MobileDevice.objects.filter(provedor_id=provedor_id)
            .exclude(push_token__isnull=True)
            .exclude(push_token='')
            .count()
        )
        # Mesmo sem device: cria aviso no sino para o CPF alvo (chat suporte)
        if target_customer_ids:
            _create_in_app_warning_for_targets(_expand_target_ids(target_customer_ids))
        return {
            'status': 'skipped',
            'reason': 'no_devices_found',
            'debug': {'total': total, 'active': active, 'with_token': with_token},
        }

    success_count = 0
    failure_count = 0
    batch_size = 500
    token_status = {}  # token -> 'enviado' | 'falha'

    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i + batch_size]
        try:
            formatted_data = {}
            for k, v in (data or {}).items():
                key = str(k)
                # Chaves reservadas pelo FCM (Invalid data payload key)
                if key in ('from', 'message_type') or key.startswith('google.') or key.startswith('gcm.'):
                    if key == 'message_type':
                        key = 'msg_type'
                    else:
                        continue
                formatted_data[key] = str(v)
            message_payload = messaging.MulticastMessage(
                tokens=batch_tokens,
                notification=messaging.Notification(title=title, body=message),
                data=formatted_data,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        channel_id='high_importance_channel',
                        sound='default',
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(alert=messaging.ApsAlert(title=title, body=message), sound='default'),
                    ),
                ),
            )
            if hasattr(messaging, 'send_each_for_multicast'):
                response = messaging.send_each_for_multicast(message_payload)
            else:
                response = messaging.send_multicast(message_payload)
            success_count += response.success_count
            failure_count += response.failure_count

            if response.responses:
                for idx, resp in enumerate(response.responses):
                    token = batch_tokens[idx] if idx < len(batch_tokens) else None
                    if not token:
                        continue
                    if resp.success:
                        token_status[token] = 'enviado'
                        try:
                            MobileDevice.objects.filter(push_token=token).update(
                                push_confirmed=True,
                                push_confirmed_at=timezone.now(),
                            )
                        except Exception:
                            pass
                    else:
                        token_status[token] = 'falha'
                        error_message = str(resp.exception) if resp.exception else ''
                        error_str = error_message.lower()
                        logger.warning(
                            '[mobile_app] FCM fail token_tail=%s err=%s',
                            token[-12:] if token else '',
                            error_message[:300],
                        )
                        # Só invalida token claramente morto (não limpa em erro transitório)
                        hard_invalid = any(
                            term in error_str
                            for term in (
                                'unregistered',
                                'registration-token-not-registered',
                                'invalid-registration-token',
                                'invalid argument',
                            )
                        )
                        if hard_invalid:
                            try:
                                MobileDevice.objects.filter(push_token=token).update(
                                    active=False,
                                    push_token=None,
                                )
                            except Exception:
                                pass
        except Exception as exc:
            logger.error('[mobile_app] FCM batch error: %s', exc, exc_info=True)
            failure_count += len(batch_tokens)
            for token in batch_tokens:
                token_status[token] = 'falha'

    # Destinatários agregados por CPF/usuário (melhor status: enviado se algum token ok)
    recipients_by_key = {}
    for token, info in token_info.items():
        status = token_status.get(token, 'falha')
        key = info.get('user__cpf') or info.get('user_id') or token[-8:]
        login = ''
        if info.get('user__pppoe_login'):
            login = str(info['user__pppoe_login']).split(',')[0].strip()
        name = (info.get('user__name') or '').strip() or login or info.get('user__cpf') or 'Cliente'
        existing = recipients_by_key.get(key)
        if not existing:
            recipients_by_key[key] = {
                'name': name,
                'cpf': info.get('user__cpf') or '',
                'login': login,
                'customer_id': info.get('user__customer_id') or '',
                'status': status,
                'platform': info.get('platform') or '',
                'model': info.get('model') or '',
            }
        elif status == 'enviado':
            existing['status'] = 'enviado'

    recipients_list = list(recipients_by_key.values())[:500]

    try:
        payload_data = data or {}
        MobileNotificationLog.objects.create(
            provedor_id=provedor_id,
            source=source,
            title=title,
            body=message,
            recipients_count=len(tokens),
            success_count=success_count,
            failure_count=failure_count,
            notif_type=str(payload_data.get('type') or 'info')[:20],
            link=(payload_data.get('url') or payload_data.get('link') or None),
            image_url=(payload_data.get('image_url') or None) or None,
            segment_type=segment_type or 'all',
            recipients=recipients_list,
            metadata={
                'segment_tags': segment_tags,
                'segment_search': segment_search,
                'target_customer_ids': (
                    str(target_customer_ids)[:500] if target_customer_ids else None
                ),
                'unique_clients': len(recipients_list),
            },
        )
    except Exception:
        logger.exception('[mobile_app] falha ao gravar log de notificação')

    try:
        if source != 'in_app_warning_system':
            target_cpfs_list = [
                c for c in (row.get('user__cpf') for row in device_rows) if c
            ]
            # dedupe preserving order
            seen = set()
            ordered = []
            for c in target_cpfs_list:
                if c not in seen:
                    seen.add(c)
                    ordered.append(c)
            if not ordered and target_customer_ids:
                ids = [target_customer_ids] if isinstance(target_customer_ids, str) else list(target_customer_ids)
                for item in ids:
                    if item is None:
                        continue
                    parts = [p.strip() for p in str(item).split(',') if p.strip()]
                    ordered.extend(parts or [str(item)])
            _create_in_app_warning_for_targets(ordered)
    except Exception as exc:
        logger.error('[mobile_app] InAppWarning create error: %s', exc)

    return {
        'status': 'completed',
        'provider_id': provedor_id,
        'provedor_id': provedor_id,
        'sent': success_count,
        'failed': failure_count,
        'success_count': success_count,
        'failure_count': failure_count,
    }


def process_due_scheduled_notifications(limit=50):
    """
    Envia notificações agendadas com scheduled_at <= agora (legado process_notifications).
    Chamado pelo loop ASGI periódico do superadmin.
    """
    from .models import MobileScheduledNotification

    now = timezone.now()
    due = list(
        MobileScheduledNotification.objects.filter(
            status='pending',
            scheduled_at__lte=now,
        ).order_by('scheduled_at')[:limit]
    )
    if not due:
        return {'processed': 0, 'checked': 0}

    processed = 0
    for notification in due:
        try:
            data = {'type': notification.type or 'info'}
            if notification.image_url:
                data['image_url'] = notification.image_url
                data['image'] = notification.image_url

            segment_type = notification.segment_type or 'all'
            segment_search = notification.segment_search
            target_customer_ids = None
            # CPFs de "clientes selecionados" são persistidos em segment_search
            if segment_type == 'selected' and segment_search:
                target_customer_ids = segment_search
                segment_type_for_send = 'all'
                segment_search = None
            else:
                segment_type_for_send = segment_type

            result = send_push_notification_core(
                provedor_id=notification.provedor_id,
                title=notification.title,
                message=notification.body,
                data=data,
                source='scheduled_task',
                target_customer_ids=target_customer_ids,
                segment_type=segment_type_for_send,
                segment_tags=notification.segment_tags,
                segment_search=segment_search,
            )

            sent = result.get('sent', result.get('success_count', 0)) or 0
            failed = result.get('failed', result.get('failure_count', 0)) or 0

            if result.get('status') in ('completed', 'skipped'):
                notification.status = 'sent'
                notification.sent_at = timezone.now()
                notification.sent_count = sent
                notification.failed_count = failed
                if result.get('reason'):
                    notification.error_message = (
                        f"Status: {result.get('status')}, Motivo: {result.get('reason')}"
                    )
            else:
                notification.status = 'failed'
                notification.error_message = f'Erro no retorno do serviço: {result}'

            notification.save()
            processed += 1
            logger.info(
                '[mobile_app] scheduled #%s sent=%s failed=%s status=%s',
                notification.id,
                sent,
                failed,
                notification.status,
            )
        except Exception as exc:
            logger.exception(
                '[mobile_app] erro ao processar agendada #%s: %s',
                getattr(notification, 'id', '?'),
                exc,
            )
            try:
                notification.status = 'failed'
                notification.error_message = str(exc)
                notification.save(update_fields=['status', 'error_message'])
            except Exception:
                pass

    return {'processed': processed, 'checked': len(due)}
