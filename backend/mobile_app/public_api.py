"""APIs públicas consumidas pelo app mobile do cliente."""
import json
import logging
import mimetypes
import re
import time

import requests
from django.db import OperationalError, transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
    MobileAppConfig,
    MobileAppProfile,
    MobileAppUser,
    MobileDevice,
    MobileInAppWarning,
    MobilePlan,
)
from .services import (
    app_user_access_denied,
    provedor_access_denied,
    resolve_provedor_from_provider_token,
    sgp_client_name,
    sgp_contract_id,
    sgp_pppoe_login,
    update_user_activity,
)


def _db_retry(fn, *, attempts=5, delay=0.15):
    """Retry em 'database is locked' (SQLite + ASGI concorrente)."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            last = exc
            if 'locked' not in str(exc).lower() or i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))
    raise last


def _provider_block_payload(provedor, profile=None):
    phone = ''
    color = None
    if profile is not None:
        phone = profile.number or ''
        color = profile.primary_color
    return {
        'error': 'Acesso desativado. Entre em contato com o suporte.',
        'is_active': False,
        'is_blocked': True,
        'provider_blocked': True,
        'user_blocked': False,
        'provider_id': getattr(provedor, 'id', None),
        'provider_name': getattr(provedor, 'nome', None) or '',
        'provider_phone': phone,
        'primary_color': color,
        'active_shortcuts': [],
        'active_tools': {},
        'social_links': [],
    }

logger = logging.getLogger(__name__)

BRANDING_FILES = {'logo': 'logo', 'login-logo': 'login_logo'}


def _public_origin(request) -> str:
    proto = request.META.get('HTTP_X_FORWARDED_PROTO') or request.scheme or 'https'
    host = request.META.get('HTTP_X_FORWARDED_HOST') or request.get_host()
    return f'{proto}://{host}'.rstrip('/')


def _branding_url(request, profile, kind):
    if not getattr(profile, BRANDING_FILES[kind]):
        return None
    version = int(profile.updated_at.timestamp()) if profile.updated_at else 0
    return f'{_public_origin(request)}/v1/branding/{profile.provedor_id}/{kind}/?v={version}'


def _theme_payload(request, profile):
    """Personalização visual do app; cores vazias = o app usa o padrão do build."""
    primary = profile.primary_color or ''
    if primary.upper() == '#0D70B3':
        primary = ''
    return {
        'primary_color': primary,
        'secondary_color': profile.secondary_color or '',
        'login_bg_color': profile.login_bg_color or '',
        'login_button_color': profile.login_button_color or '',
        'login_text_color': profile.login_text_color or '',
        'app_bg_color': profile.app_bg_color or '',
        'card_color': profile.card_color or '',
        'home_logo_position': profile.home_logo_position,
        'logo_url': _branding_url(request, profile, 'logo'),
        'login_logo_url': _branding_url(request, profile, 'login-logo'),
    }


APP_DEFAULT_THEME_KEYS = (
    'primary_color', 'secondary_color', 'login_bg_color', 'login_button_color', 'login_text_color',
    'app_bg_color', 'card_color',
)


def _remember_app_defaults(request, profile):
    """Guarda as cores de fábrica que o app envia (X-App-Default-Theme) para a prévia do painel."""
    raw = request.META.get('HTTP_X_APP_DEFAULT_THEME')
    if not raw:
        return
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return
    if not isinstance(data, dict):
        return
    clean = {}
    for key in APP_DEFAULT_THEME_KEYS:
        value = str(data.get(key) or '').strip().upper()
        if re.fullmatch(r'#[0-9A-F]{6}', value):
            clean[key] = value
    if clean and clean != (profile.app_default_theme or {}):
        # update() não mexe em updated_at, que versiona as URLs dos logos.
        MobileAppProfile.objects.filter(pk=profile.pk).update(app_default_theme=clean)
        profile.app_default_theme = clean


@api_view(['GET'])
@permission_classes([AllowAny])
def public_branding_file(request, provedor_id, kind):
    field = BRANDING_FILES.get(kind)
    if not field:
        raise Http404()
    profile = MobileAppProfile.objects.filter(provedor_id=provedor_id).first()
    image = getattr(profile, field, None) if profile else None
    if not image:
        raise Http404()
    try:
        fh = image.open('rb')
    except Exception:
        raise Http404()
    content_type = mimetypes.guess_type(image.name)[0] or 'application/octet-stream'
    response = FileResponse(fh, content_type=content_type)
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def _require_provedor(request, *, from_body=False):
    token = (
        request.query_params.get('provider_token')
        or (request.data.get('provider_token') if from_body or request.method != 'GET' else None)
        or ''
    )
    if not token and request.method == 'GET':
        token = request.GET.get('provider_token') or ''
    if not token:
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1].strip()
    if not token:
        token = request.META.get('HTTP_X_PROVIDER_TOKEN', '').strip() or ''
    if not token:
        return None, Response({'error': 'provider_token é obrigatório.'}, status=400)
    provedor = resolve_provedor_from_provider_token(token, require_active=False)
    if not provedor:
        return None, Response(_provider_block_payload(None), status=403)
    try:
        profile = provedor.mobile_app
    except MobileAppProfile.DoesNotExist:
        return None, Response(_provider_block_payload(provedor), status=403)
    # GSFibra: sem bloqueio por assinatura / perfil inativo.
    return (provedor, profile), None


@api_view(['GET'])
@permission_classes([AllowAny])
def public_app_config(request):
    """Compatível com GET /api/public/config/ do app_provedor."""
    resolved, err = _require_provedor(request)
    if err:
        # Mantém o contrato antigo: config bloqueada volta 200 com payload.
        if err.status_code in (400, 403):
            provedor = None
            profile = None
            token = (
                request.query_params.get('provider_token')
                or request.GET.get('provider_token')
                or ''
            )
            if not token:
                auth = request.META.get('HTTP_AUTHORIZATION', '')
                if auth.startswith('Bearer '):
                    token = auth.split(' ', 1)[1].strip()
            if not token:
                token = request.META.get('HTTP_X_PROVIDER_TOKEN', '').strip() or ''
            if token:
                provedor = resolve_provedor_from_provider_token(token, require_active=False)
                if provedor:
                    try:
                        profile = provedor.mobile_app
                    except MobileAppProfile.DoesNotExist:
                        profile = None
            return Response(_provider_block_payload(provedor, profile), status=200)
        return err
    provedor, profile = resolved

    cpf = request.query_params.get('cpf')
    user_blocked = False
    if cpf:
        denied_user = app_user_access_denied(provedor, cpf)
        if denied_user:
            return Response({
                'error': denied_user,
                'is_active': False,
                'is_blocked': True,
                'provider_blocked': False,
                'user_blocked': True,
            }, status=403)
        update_user_activity(provedor, cpf)

    _remember_app_defaults(request, profile)
    config, _ = MobileAppConfig.objects.get_or_create(profile=profile)
    theme = _theme_payload(request, profile)

    return Response({
        'provider_id': provedor.id,
        'provider_name': provedor.nome,
        'provider_phone': profile.number or '',
        'support_phone': profile.number or '',
        'primary_color': profile.primary_color,
        'logo_url': theme['logo_url'],
        'theme': theme,
        'active_shortcuts': config.active_shortcuts or [],
        'active_tools': {
            'speed_test': config.tool_speed_test,
            'auto_unlock': config.tool_auto_unlock,
            'faturas': config.tool_faturas,
            'connected_devices': config.tool_connected_devices,
            'wifi': config.tool_wifi,
            'cameras': config.tool_cameras,
        },
        'social_links': config.social_links or [],
        'update_warning_active': config.update_warning_active,
        'is_active': True,
        'is_blocked': False,
        'provider_blocked': False,
        'user_blocked': user_blocked,
        'speed_test_provider': config.speed_test_provider,
        'terms_text': profile.terms_text or '',
        'termos': profile.terms_text or '',
        'privacy_text': getattr(profile, 'privacy_text', '') or '',
        'privacidade': getattr(profile, 'privacy_text', '') or '',
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def public_plans(request):
    resolved, err = _require_provedor(request)
    if err:
        return err
    provedor, _profile = resolved
    plans = MobilePlan.objects.filter(provedor=provedor, is_active=True).order_by('price')
    data = []
    for p in plans:
        data.append({
            'id': str(p.id),
            'name': p.name,
            'type': p.type,
            'download_speed': p.download_speed,
            'upload_speed': p.upload_speed,
            'price': float(p.price),
            'price_display': f'R$ {p.price}'.replace('.', ','),
            'description': p.description,
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_server_time(request):
    now = timezone.localtime()
    return Response({
        'server_time': now.isoformat(),
        'server_date': now.date().isoformat(),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def public_warnings(request):
    resolved, err = _require_provedor(request)
    if err:
        return err
    provedor, _profile = resolved

    cpf = request.query_params.get('cpf')
    contract_id = request.query_params.get('contract_id')
    if cpf:
        denied_user = app_user_access_denied(provedor, cpf)
        if denied_user:
            return Response(
                {'error': denied_user, 'user_blocked': True, 'is_blocked': True},
                status=403,
            )
        update_user_activity(provedor, cpf)

    user = None
    dismissed_ids = []
    if cpf:
        cpf_limpo = re.sub(r'\D', '', str(cpf))
        user = MobileAppUser.objects.filter(provedor=provedor, cpf=cpf_limpo).first()
        if user:
            dismissed_ids = user.dismissed_warnings or []

    warnings = MobileInAppWarning.objects.filter(
        provedor=provedor,
        active=True,
    ).order_by('-sticky', '-created_at')

    filtered = []
    for w in warnings:
        if w.id in dismissed_ids:
            continue
        # Avisos direcionados a CPF (ex.: chat suporte) não usam o corte por
        # user.created_at — o usuário pode ser criado/reativado depois do aviso.
        if user and not w.sticky and not w.target_cpfs and w.created_at < user.created_at:
            continue
        if w.target_cpfs:
            target_cpfs = [c.strip() for c in w.target_cpfs.split(',') if c.strip()]
            if not cpf or cpf not in target_cpfs:
                # também aceita CPF só dígitos
                cpf_digits = re.sub(r'\D', '', str(cpf or ''))
                targets_digits = [re.sub(r'\D', '', t) for t in target_cpfs]
                if not cpf_digits or cpf_digits not in targets_digits:
                    continue
        if w.target_contracts:
            target_contracts = [c.strip() for c in w.target_contracts.split(',') if c.strip()]
            if not contract_id or str(contract_id) not in target_contracts:
                continue
        filtered.append({
            'id': w.id,
            'title': w.title,
            'message': w.message,
            'type': w.type,
            'whatsapp_btn': w.whatsapp_btn,
            'sticky': w.sticky,
            'show_home': w.show_home,
            'created_at': w.created_at,
        })
    return Response(filtered)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_dismiss_warning(request):
    resolved, err = _require_provedor(request, from_body=True)
    if err:
        return err
    provedor, _profile = resolved

    warning_id = request.data.get('warning_id')
    if not warning_id:
        return Response({'error': 'warning_id é obrigatório.'}, status=400)

    warning = MobileInAppWarning.objects.filter(id=warning_id, provedor=provedor).first()
    if not warning:
        return Response({'error': 'Aviso não encontrado.'}, status=404)

    current_cpf = request.data.get('cpf')
    if current_cpf:
        cpf_limpo = re.sub(r'\D', '', str(current_cpf))
        user = MobileAppUser.objects.filter(provedor=provedor, cpf=cpf_limpo).first()
        if user:
            dismissed = list(user.dismissed_warnings or [])
            wid = int(warning.id)
            if wid not in dismissed:
                dismissed.append(wid)
                user.dismissed_warnings = dismissed
                user.save(update_fields=['dismissed_warnings'])

    if (warning.target_cpfs or warning.target_contracts) and current_cpf:
        cpf_limpo = re.sub(r'\D', '', str(current_cpf))
        if warning.target_cpfs:
            cpfs = [c.strip() for c in warning.target_cpfs.split(',') if c.strip()]
            cpfs = [c for c in cpfs if re.sub(r'\D', '', c) != cpf_limpo]
            warning.target_cpfs = ','.join(cpfs)
            warning.save(update_fields=['target_cpfs'])
        remaining_cpfs = [c for c in (warning.target_cpfs or '').split(',') if c.strip()]
        remaining_contracts = [c for c in (warning.target_contracts or '').split(',') if c.strip()]
        if not remaining_cpfs and not remaining_contracts:
            warning.delete()
            return Response({
                'success': True,
                'action': 'deleted',
                'message': 'Aviso removido permanentemente.',
            })
        return Response({
            'success': True,
            'action': 'updated',
            'message': 'CPF removido da lista de alvos.',
        })

    return Response({
        'success': True,
        'action': 'dismissed',
        'message': 'Aviso marcado como lido para este usuário.',
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def register_app_user(request):
    """Registra/atualiza cliente + device após login no SGP (compatível com app_provedor)."""
    try:
        data = request.data
        provider_token = request.query_params.get('provider_token') or data.get('provider_token')
        cpf = data.get('cpf')
        if not provider_token or not cpf:
            return Response({'error': 'provider_token e CPF obrigatórios'}, status=400)

        provedor = resolve_provedor_from_provider_token(provider_token, require_active=False)
        if not provedor:
            return Response(_provider_block_payload(None), status=403)
        try:
            profile = provedor.mobile_app
        except MobileAppProfile.DoesNotExist:
            return Response(_provider_block_payload(provedor), status=403)

        cpf_limpo = re.sub(r'\D', '', str(cpf))
        denied_user = app_user_access_denied(provedor, cpf_limpo)
        if denied_user:
            return Response(
                {'error': denied_user, 'user_blocked': True, 'is_blocked': True},
                status=403,
            )
        name = (data.get('name') or '').strip()
        if name.lower() in ('cliente', 'sem nome', 'unknown'):
            name = ''
        email = data.get('email')
        pppoe_login = data.get('pppoe_login') or data.get('login')

        existing = MobileAppUser.objects.filter(provedor=provedor, cpf=cpf_limpo).first()
        user_defaults = {
            'customer_id': data.get('customer_id') or data.get('external_id') or data.get('contract_id'),
        }
        if email:
            user_defaults['email'] = email
        if name:
            user_defaults['name'] = name[:255]
        if existing is None:
            user_defaults['active'] = True
            if 'name' not in user_defaults:
                user_defaults['name'] = ''
        selected_contract = str(user_defaults.get('customer_id') or '').strip()
        if pppoe_login:
            user_defaults['pppoe_login'] = str(pppoe_login).strip()

        need_sgp_name = not user_defaults.get('name') and not (existing and (existing.name or '').strip())
        need_sgp_login = 'pppoe_login' not in user_defaults
        if (need_sgp_name or need_sgp_login) and profile.sgp_url and profile.sgp_token:
            try:
                erp_type = (getattr(profile, 'erp_type', None) or 'sgp').strip().lower()
                data_sgp = None
                if erp_type == 'receitanet':
                    from .receitanet_adapter import _extract_clientes, _map_cliente_to_contrato
                    from .receitanet_client import ReceitaNetClient

                    rn = ReceitaNetClient(profile.sgp_url, profile.sgp_token)
                    rn_res = rn.consultar_clientes(cpf_cnpj=cpf_limpo)
                    if rn_res.get('ok'):
                        contratos = [
                            _map_cliente_to_contrato(c)
                            for c in _extract_clientes(rn_res.get('data'))
                        ]
                        data_sgp = {'contratos': contratos}
                else:
                    url = f"{profile.sgp_url.rstrip('/')}/api/ura/consultacliente"
                    payload = {
                        'token': profile.sgp_token,
                        'cpf_cnpj': cpf_limpo,
                        'app': profile.sgp_app_name or 'gsfibra',
                    }
                    if need_sgp_name:
                        payload['assinatura_eletronica'] = True
                    resp = requests.post(url, json=payload, timeout=5)
                    if resp.status_code == 200:
                        data_sgp = resp.json()

                if data_sgp:
                    if need_sgp_name:
                        resolved_name = sgp_client_name(data_sgp)
                        if not resolved_name:
                            for c in (data_sgp.get('contratos') or []):
                                if not isinstance(c, dict):
                                    continue
                                if selected_contract and sgp_contract_id(c) != selected_contract:
                                    continue
                                resolved_name = sgp_client_name(c)
                                if resolved_name:
                                    break
                        if not resolved_name and erp_type != 'receitanet':
                            # Fallback assinatura eletrônica (somente SGP)
                            for c in (data_sgp.get('contratos') or []):
                                if not isinstance(c, dict):
                                    continue
                                for doc in (c.get('assinaturaEletronica') or []):
                                    if not isinstance(doc, dict):
                                        continue
                                    for st in (doc.get('status') or []):
                                        if not isinstance(st, dict):
                                            continue
                                        obs = str(st.get('observacao') or '')
                                        m = re.search(r'Assinado Por:\s*(.+)$', obs, re.I)
                                        if m and m.group(1).strip():
                                            resolved_name = m.group(1).strip()[:255]
                                            break
                                    if resolved_name:
                                        break
                                if resolved_name:
                                    break
                        if resolved_name:
                            user_defaults['name'] = resolved_name
                    if need_sgp_login:
                        chosen = ''
                        for c in (data_sgp.get('contratos') or []):
                            if not isinstance(c, dict):
                                continue
                            cid = sgp_contract_id(c)
                            login = sgp_pppoe_login(c)
                            if not login:
                                continue
                            if selected_contract and cid == selected_contract:
                                chosen = login
                                break
                            if not chosen:
                                chosen = login
                        if chosen:
                            user_defaults['pppoe_login'] = chosen[:100]
            except Exception as exc:
                logger.warning('[register_app_user] ERP fetch: %s', exc)

        def _save_user():
            with transaction.atomic():
                return MobileAppUser.objects.update_or_create(
                    provedor=provedor,
                    cpf=cpf_limpo,
                    defaults=user_defaults,
                )

        user, created = _db_retry(_save_user)
        update_user_activity(provedor, cpf_limpo)

        device_platform = data.get('device_platform') or data.get('platform')
        device_model = data.get('device_model') or data.get('model')
        device_os = data.get('device_os') or data.get('os_version')
        device_timestamp = data.get('device_timestamp')
        push_token = data.get('push_token') or data.get('fcm_token')
        app_version = data.get('app_version') or data.get('version')

        if device_platform and device_model:
            if push_token:
                def _cleanup_token():
                    MobileDevice.objects.filter(
                        provedor=provedor,
                        push_token=push_token,
                    ).exclude(user=user).delete()

                try:
                    _db_retry(_cleanup_token)
                except OperationalError:
                    logger.warning('[register_app_user] cleanup push_token locked; seguindo')

            defaults = {
                'os_version': device_os or 'Unknown',
                'active': True,
                'provedor': provedor,
                'last_active': timezone.now(),
            }
            if app_version:
                defaults['app_version'] = str(app_version)[:32]
            if push_token:
                defaults['push_token'] = push_token
            if device_timestamp:
                try:
                    dt = parse_datetime(device_timestamp)
                    if dt:
                        defaults['last_active'] = dt
                except Exception:
                    pass

            def _save_device():
                with transaction.atomic():
                    return MobileDevice.objects.update_or_create(
                        user=user,
                        platform=str(device_platform).lower(),
                        model=device_model,
                        defaults=defaults,
                    )

            _db_retry(_save_device)

        from .services import log_mobile_activity
        log_mobile_activity(
            provedor=provedor,
            user=user,
            event='register' if created else 'login',
            event_label='Registrou o app' if created else 'Login',
            request=request,
            metadata={'created': created},
        )

        return Response({'success': True, 'user_id': user.id, 'created': created})
    except Exception as exc:
        logger.exception('[register_app_user]')
        return Response({'error': str(exc)}, status=500)
