"""Push: registro de device, webhook SGP e envio admin."""
import logging
import re

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import MobileAppUser, MobileDevice
from .push_service import send_push_notification_core
from .services import app_user_access_denied, resolve_provedor_from_provider_token

logger = logging.getLogger(__name__)

# Padrões comuns nas mensagens de cobrança do SGP (contrato no texto, não só "Contrato: 123")
_CONTRACT_MSG_PATTERNS = (
    re.compile(r'(?:Contrato|contrato)\s*:?\s*(\d+)', re.I),
    re.compile(r'do\s+contrato\s+(\d+)', re.I),
    re.compile(r'contrato\s+n[º°.]?\s*(\d+)', re.I),
)


def _extract_contract_from_text(text):
    if not text:
        return None
    for pat in _CONTRACT_MSG_PATTERNS:
        match = pat.search(str(text))
        if match:
            return match.group(1)
    return None


def _merge_sgp_webhook_payload(request):
    """Mescla query string + body (SGP costuma usar GET com msg/to/idcontrato)."""
    data = {}
    if hasattr(request.GET, 'lists'):
        for key, values in request.GET.lists():
            if not values:
                continue
            data[key] = values[-1] if len(values) == 1 else values
    else:
        data.update(request.GET.dict())

    if request.method == 'POST' and request.data:
        if hasattr(request.data, 'dict'):
            data.update(request.data.dict())
        elif isinstance(request.data, dict):
            data.update(request.data)

    nested = data.get('data')
    if isinstance(nested, str):
        try:
            import json
            nested = json.loads(nested)
        except (TypeError, ValueError):
            nested = {}
    if not isinstance(nested, dict):
        nested = {}

    return data, nested


def _resolve_sgp_push_target(data, nested, mensagem):
    """Identifica o cliente alvo sem exigir CPF na URL (contrato no param ou no texto)."""
    raw_customer_id = (
        nested.get('customer_id') or data.get('customer_id')
        or nested.get('customerId') or data.get('customerId')
        or nested.get('cpf') or data.get('cpf')
        or nested.get('cpf_cnpj') or data.get('cpf_cnpj')
        or nested.get('idcliente') or data.get('idcliente')
    )
    contract_id = (
        nested.get('contract_id') or data.get('contract_id')
        or nested.get('contrato_id') or data.get('contrato_id')
        or nested.get('contratoId') or data.get('contratoId')
        or nested.get('idcontrato') or data.get('idcontrato')
        or nested.get('contrato') or data.get('contrato')
        or nested.get('id_contrato') or data.get('id_contrato')
        or nested.get('numero_contrato') or data.get('numero_contrato')
    )
    if not contract_id:
        for text in (
            mensagem,
            nested.get('message_body') or data.get('message_body'),
            nested.get('message') or data.get('message'),
        ):
            contract_id = _extract_contract_from_text(text)
            if contract_id:
                break

    customer_id = raw_customer_id or contract_id
    return customer_id, contract_id


def _first_non_empty(data, device_info, *keys):
    for k in keys:
        v = data.get(k)
        if v:
            return v
        if isinstance(device_info, dict):
            v2 = device_info.get(k)
            if v2:
                return v2
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def register_device(request):
    try:
        from django.db import IntegrityError, transaction

        data = request.data
        provider_token = data.get('provider_token')
        provedor = None

        if provider_token:
            provedor = resolve_provedor_from_provider_token(provider_token, require_active=False)
            if not provedor:
                return Response({
                    'error': 'Token de provedor inválido ou inativo.',
                    'is_blocked': True,
                    'provider_blocked': True,
                }, status=403)
            from .services import provedor_access_denied
            if provedor_access_denied(provedor):
                return Response({
                    'error': 'Acesso desativado. Entre em contato com o suporte.',
                    'is_active': False,
                    'is_blocked': True,
                    'provider_blocked': True,
                    'provider_name': provedor.nome,
                }, status=403)

        user = request.user
        if not provedor and getattr(user, 'is_authenticated', False):
            provedor = getattr(user, 'provedor', None)

        if not provedor:
            return Response({'error': 'provider_token é obrigatório.'}, status=400)

        fcm_token = data.get('fcm_token') or data.get('push_token')
        platform = (data.get('platform') or 'unknown').lower()
        device_info = data.get('device', {}) if isinstance(data.get('device'), dict) else {}

        device_model = _first_non_empty(
            data, device_info, 'model', 'device_model', 'modelo', 'model_name',
        ) or 'Unknown'
        os_version = _first_non_empty(
            data, device_info,
            'os_version', 'android_version', 'version', 'versao', 'versao_android',
        ) or 'Unknown'
        app_version = _first_non_empty(
            data, device_info, 'app_version', 'appVersion', 'versao_app',
        )

        if not fcm_token:
            return Response({'error': 'fcm_token é obrigatório.'}, status=400)

        app_user = None
        user_id = data.get('user_id')
        cpf_recebido = data.get('cpf')
        cpf_limpo = re.sub(r'\D', '', str(cpf_recebido or ''))
        if user_id:
            app_user = MobileAppUser.objects.filter(id=user_id, provedor=provedor).first()
        if not app_user and cpf_limpo:
            app_user, _ = MobileAppUser.objects.get_or_create(
                provedor=provedor,
                cpf=cpf_limpo,
                defaults={
                    'name': (data.get('name') or '').strip()[:255],
                    'active': True,
                    'customer_id': str(
                        data.get('contract_id') or data.get('customer_id') or ''
                    ).strip()[:64] or None,
                },
            )
            if not app_user.active:
                app_user.active = True
                app_user.save(update_fields=['active'])

        # Atualiza nome/contrato se o app enviar (evita ficar "Sem nome")
        if app_user:
            updates = []
            incoming_name = (data.get('name') or '').strip()
            if incoming_name and incoming_name.lower() not in ('cliente', 'sem nome', 'unknown'):
                if not (app_user.name or '').strip() or (app_user.name or '').strip().lower() in (
                    'cliente', 'sem nome', 'unknown',
                ):
                    app_user.name = incoming_name[:255]
                    updates.append('name')
            cid = str(data.get('contract_id') or data.get('customer_id') or '').strip()
            if cid and not (app_user.customer_id or '').strip():
                app_user.customer_id = cid[:64]
                updates.append('customer_id')
            if updates:
                app_user.save(update_fields=updates)

        denied_user = app_user_access_denied(provedor, cpf_limpo or (app_user.cpf if app_user else None))
        if denied_user:
            return Response(
                {'error': denied_user, 'user_blocked': True, 'is_blocked': True},
                status=403,
            )

        if not app_user:
            return Response(
                {'error': 'Usuário (AppUser) não identificado. Envie CPF.'},
                status=400,
            )

        with transaction.atomic():
            # Libera o token de outros registros (evita UNIQUE)
            MobileDevice.objects.filter(push_token=fcm_token).exclude(
                user=app_user, provedor=provedor,
            ).update(push_token=None, active=False)

            existing = (
                MobileDevice.objects.select_for_update()
                .filter(push_token=fcm_token)
                .first()
                or MobileDevice.objects.select_for_update()
                .filter(provedor=provedor, user=app_user)
                .order_by('-last_active', '-id')
                .first()
            )

            if existing:
                existing.provedor = provedor
                existing.user = app_user
                existing.push_token = fcm_token
                existing.active = True
                if device_model != 'Unknown':
                    existing.model = device_model
                if os_version != 'Unknown':
                    existing.os_version = os_version
                if platform != 'unknown':
                    existing.platform = platform
                if app_version:
                    existing.app_version = str(app_version)[:32]
                existing.last_active = timezone.now()
                existing.save()
            else:
                try:
                    with transaction.atomic():
                        MobileDevice.objects.create(
                            provedor=provedor,
                            user=app_user,
                            push_token=fcm_token,
                            platform=platform if platform != 'unknown' else 'android',
                            model=device_model,
                            os_version=os_version,
                            app_version=str(app_version)[:32] if app_version else None,
                            active=True,
                            push_confirmed=False,
                            last_active=timezone.now(),
                        )
                except IntegrityError:
                    existing = (
                        MobileDevice.objects.filter(push_token=fcm_token).first()
                        or MobileDevice.objects.filter(provedor=provedor, user=app_user)
                        .order_by('-id')
                        .first()
                    )
                    if not existing:
                        raise
                    existing.provedor = provedor
                    existing.user = app_user
                    existing.push_token = fcm_token
                    existing.active = True
                    existing.last_active = timezone.now()
                    existing.save()

        return Response({
            'message': 'Dispositivo registrado com sucesso.',
            'provider': provedor.nome,
        })
    except Exception as exc:
        logger.exception('[register_device]')
        return Response({'error': str(exc)}, status=500)


@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def push_webhook(request):
    """Webhook genérico SGP/ISP → push (compatível com /api/webhooks/push/)."""
    try:
        data, nested = _merge_sgp_webhook_payload(request)

        provider_token = data.get('provider_token')
        if not provider_token:
            return Response({'error': 'provider_token obrigatório.'}, status=401)

        provedor = resolve_provedor_from_provider_token(provider_token)
        if not provedor:
            return Response({'error': 'Token inválido ou provedor inativo.'}, status=403)

        provider_id_recebido = data.get('provider_id') or nested.get('provider_id')
        if provider_id_recebido:
            try:
                if int(provider_id_recebido) != provedor.id:
                    return Response({
                        'error': (
                            f'provider_id ({provider_id_recebido}) não corresponde '
                            f'ao provider do token ({provedor.id}).'
                        ),
                    }, status=403)
            except (ValueError, TypeError):
                return Response({'error': 'provider_id inválido.'}, status=400)

        titulo = (
            nested.get('message_title') or nested.get('title') or nested.get('titulo')
            or data.get('message_title') or data.get('title') or data.get('titulo')
            or 'Nova Mensagem'
        )
        mensagem = (
            nested.get('message_body') or nested.get('message') or nested.get('mensagem')
            or nested.get('msg') or data.get('message_body') or data.get('message')
            or data.get('mensagem') or data.get('msg')
        )
        customer_id, contract_id = _resolve_sgp_push_target(data, nested, mensagem)
        link = nested.get('link') or nested.get('url') or data.get('link') or data.get('url')
        tipo = nested.get('type') or data.get('tipo') or 'info'

        if mensagem and 'HTTPSConnectionPool' in str(mensagem):
            import urllib.parse
            if 'msg=' in str(mensagem):
                try:
                    start = str(mensagem).find('msg=') + 4
                    end = str(mensagem).find('&', start)
                    encoded = str(mensagem)[start:] if end == -1 else str(mensagem)[start:end]
                    mensagem = urllib.parse.unquote_plus(encoded)
                    customer_id, contract_id = _resolve_sgp_push_target(data, nested, mensagem)
                except Exception:
                    return Response({'error': 'Erro no gateway de origem.'}, status=400)
            else:
                return Response({'error': 'Mensagem contém stacktrace de erro do SGP.'}, status=400)

        if not customer_id:
            return Response({
                'error': (
                    'Identificador obrigatório (idcontrato/contrato na URL ou no texto da mensagem). '
                    'Notificação NÃO foi enviada para todos.'
                ),
                'hint': (
                    'No SGP, inclua {idcontrato} na URL ou escreva "contrato {idcontrato}" na mensagem.'
                ),
            }, status=400)
        if not mensagem:
            return Response({'error': 'Mensagem obrigatória.'}, status=400)

        logger.info(
            '[push_webhook] provedor=%s target=%s contract=%s to=%s',
            provedor.id, customer_id, contract_id, data.get('to'),
        )

        result = send_push_notification_core(
            provedor_id=provedor.id,
            title=titulo,
            message=mensagem,
            data={'type': tipo, 'url': link, 'click_action': link},
            source='sgp_webhook',
            target_customer_ids=str(customer_id),
        )
        return Response(result)
    except Exception as exc:
        logger.exception('[push_webhook]')
        return Response({'error': str(exc)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_send_push(request):
    """Envio manual pelo Superadmin / admin do provedor."""
    try:
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as dj_tz

        from .models import MobileNotificationTemplate, MobileScheduledNotification

        user = request.user
        data = request.data
        target_provedor_id = None

        is_sa = getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser
        if is_sa:
            target_provedor_id = data.get('provider_id') or data.get('provedor_id')
            if not target_provedor_id:
                return Response({'error': 'Superuser deve especificar provider_id.'}, status=400)
        else:
            if not getattr(user, 'provedor_id', None):
                return Response({'error': 'Usuário sem provedor associado.'}, status=403)
            target_provedor_id = user.provedor_id
            incoming = data.get('provider_id') or data.get('provedor_id')
            if incoming and str(incoming) != str(target_provedor_id):
                return Response({'error': 'Você só pode enviar para seu provedor.'}, status=403)

        title = data.get('title')
        message = data.get('message')
        link = data.get('link') or data.get('image_url') or ''
        notif_type = data.get('type') or 'info'
        if not title or not message:
            return Response({'error': 'Título e Mensagem são obrigatórios.'}, status=400)

        segment_type = data.get('segment_type') or 'all'
        segment_tags = data.get('segment_tags')
        segment_search = data.get('segment_search')
        selected_cpfs = data.get('selected_cpfs') or data.get('customer_id') or data.get('cpf')
        if isinstance(selected_cpfs, list):
            selected_cpfs = ','.join(str(c) for c in selected_cpfs if c)

        if data.get('save_as_template') and data.get('template_name'):
            MobileNotificationTemplate.objects.create(
                provedor_id=int(target_provedor_id),
                name=str(data.get('template_name')).strip()[:255],
                title=title,
                body=message,
                type=notif_type if notif_type in ('info', 'promo', 'warning') else 'info',
                image_url=data.get('image_url') or None,
                created_by=user if getattr(user, 'is_authenticated', False) else None,
            )

        scheduled_raw = data.get('scheduled_at')
        if scheduled_raw:
            from datetime import datetime as _dt

            raw = str(scheduled_raw).strip().replace(' ', 'T')
            # datetime-local: YYYY-MM-DDTHH:MM (sem segundos/timezone)
            scheduled_at = parse_datetime(raw)
            if scheduled_at is None:
                for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'):
                    try:
                        scheduled_at = _dt.strptime(raw[:19], fmt)
                        break
                    except ValueError:
                        continue
            if scheduled_at is None:
                return Response({'error': 'Data de agendamento inválida.'}, status=400)
            if dj_tz.is_naive(scheduled_at):
                scheduled_at = dj_tz.make_aware(scheduled_at, dj_tz.get_current_timezone())
            if scheduled_at <= dj_tz.now():
                return Response(
                    {'error': 'Escolha uma data/hora futura para agendar o envio.'},
                    status=400,
                )
            search_value = segment_search or None
            if segment_type == 'selected' and selected_cpfs:
                search_value = selected_cpfs
            scheduled = MobileScheduledNotification.objects.create(
                provedor_id=int(target_provedor_id),
                title=title,
                body=message,
                type=notif_type if notif_type in ('info', 'promo', 'warning') else 'info',
                image_url=data.get('image_url') or None,
                scheduled_at=scheduled_at,
                status='pending',
                segment_type=segment_type,
                segment_tags=segment_tags or None,
                segment_search=search_value,
                created_by=user if getattr(user, 'is_authenticated', False) else None,
            )
            return Response({
                'status': 'scheduled',
                'id': scheduled.id,
                'scheduled_at': scheduled.scheduled_at,
                'message': 'Notificação agendada com sucesso.',
            })

        if segment_type == 'selected' and not selected_cpfs:
            return Response({
                'status': 'error',
                'message': 'Selecione ao menos um CPF para o segmento “Clientes selecionados”.',
            }, status=400)

        result = send_push_notification_core(
            provedor_id=int(target_provedor_id),
            title=title,
            message=message,
            data={
                'url': link or '',
                'type': notif_type,
                'image_url': data.get('image_url') or '',
            },
            source='admin_panel',
            target_customer_ids=selected_cpfs or None,
            segment_type='all' if segment_type == 'selected' else segment_type,
            segment_tags=segment_tags,
            segment_search=segment_search,
        )

        if result.get('status') == 'skipped':
            debug = result.get('debug') or {}
            msg = 'Nenhum dispositivo encontrado para receber esta mensagem.'
            if debug.get('total', 0) > 0 and debug.get('with_token', 0) == 0:
                msg = (
                    'Existem dispositivos cadastrados, mas nenhum possui Token de Push válido.'
                )
            elif debug.get('total', 0) == 0:
                msg = 'Não há nenhum dispositivo vinculado ao provedor.'
            return Response({'status': 'error', 'message': msg, 'debug': debug})

        if result.get('status') == 'error':
            reason = result.get('reason') or ''
            msg = {
                'firebase_not_initialized': (
                    'Firebase não inicializado no Superadmin. '
                    'Configure FIREBASE_CREDENTIALS ou coloque firebase-credentials.json no backend.'
                ),
                'firebase_admin_missing': 'Pacote firebase-admin ausente no Superadmin.',
            }.get(reason, result.get('message') or f'Falha no envio ({reason or "desconhecido"})')
            return Response({
                'status': 'error',
                'message': msg,
                'reason': reason,
                'sent': 0,
                'failed': 0,
                'success_count': 0,
                'failure_count': 0,
            })

        payload = dict(result)
        payload.setdefault('success_count', payload.get('sent', 0))
        payload.setdefault('failure_count', payload.get('failed', 0))
        return Response(payload)
    except Exception as exc:
        logger.exception('[admin_send_push]')
        return Response({'error': str(exc)}, status=500)
