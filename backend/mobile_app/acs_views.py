"""
Wi-Fi do app mobile via ACS (mesmo cliente do atendimento/chatbot).

Compatível com o backend antigo do app:
  GET/POST /v1/wifi/config/?contrato=
  GET      /v1/wifi/hosts/?contrato=
"""
from __future__ import annotations

import logging
import re

import requests
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .acs_client import ACSClient, ACSError
from .models import MobileAppUser
from .public_api import _require_provedor
from .services import log_mobile_activity, sgp_contract_id, sgp_pppoe_login

logger = logging.getLogger(__name__)


def _find_app_user(provedor, contrato, cpf=None):
    qs = MobileAppUser.objects.filter(provedor=provedor)
    contrato = str(contrato or '').strip()
    if contrato:
        user = qs.filter(customer_id=contrato).first() or qs.filter(customer_id__iexact=contrato).first()
        if user:
            return user
    cpf_limpo = re.sub(r'\D', '', str(cpf or ''))
    if cpf_limpo:
        return qs.filter(cpf=cpf_limpo).first()
    return None


def _sgp_login_for_contract(profile, cpf, contrato):
    if not profile or not getattr(profile, 'sgp_url', None) or not getattr(profile, 'sgp_token', None):
        return ''
    if not cpf or not contrato:
        return ''
    try:
        erp_type = (getattr(profile, 'erp_type', None) or 'sgp').strip().lower()
        wanted = str(contrato).strip()
        if erp_type == 'receitanet':
            from .receitanet_adapter import _extract_clientes, _map_cliente_to_contrato
            from .receitanet_client import ReceitaNetClient

            rn = ReceitaNetClient(profile.sgp_url, profile.sgp_token)
            rn_res = rn.consultar_clientes(cpf_cnpj=re.sub(r'\D', '', str(cpf)))
            if not rn_res.get('ok'):
                return ''
            contratos = [_map_cliente_to_contrato(c) for c in _extract_clientes(rn_res.get('data'))]
            for item in contratos:
                if sgp_contract_id(item) != wanted:
                    continue
                return sgp_pppoe_login(item)
            return ''

        base = (
            profile.sgp_url.split('/api/')[0]
            if '/api/' in profile.sgp_url
            else profile.sgp_url.rstrip('/')
        )
        if base.lower().startswith('http://'):
            base = 'https://' + base[7:]
        url = f'{base}/api/ura/consultacliente/'
        payload = {
            'token': profile.sgp_token,
            'cpfcnpj': re.sub(r'\D', '', str(cpf)),
            'app': profile.sgp_app_name or 'gsfibra',
        }
        resp = requests.post(url, data=payload, timeout=8)
        if resp.status_code != 200:
            return ''
        data = resp.json()
        contratos = data.get('contratos') if isinstance(data, dict) else data
        if not isinstance(contratos, list):
            return ''
        for item in contratos:
            if not isinstance(item, dict):
                continue
            if sgp_contract_id(item) != wanted:
                continue
            return sgp_pppoe_login(item)
    except Exception as exc:
        logger.warning('ACS: falha ao resolver login ERP contrato=%s: %s', contrato, exc)
    return ''


def _login_for_contract(app_user, profile, contrato):
    matched = _sgp_login_for_contract(profile, app_user.cpf, contrato)
    if matched:
        if (app_user.pppoe_login or '') != matched:
            app_user.pppoe_login = matched[:100]
            app_user.save(update_fields=['pppoe_login'])
        return matched
    stored = [p.strip() for p in str(app_user.pppoe_login or '').split(',') if p.strip()]
    return stored[0] if stored else ''


def _fetch_wifi(client: ACSClient, login: str, device_id: str) -> dict:
    if login and device_id:
        try:
            return client.get_wifi_by_login(login)
        except ACSError:
            return client.get_wifi_by_device_id(device_id)
    if login:
        return client.get_wifi_by_login(login)
    return client.get_wifi_by_device_id(device_id)


def _apply_wifi(client: ACSClient, login: str, device_id: str, **changes) -> dict:
    if login and device_id:
        try:
            return client.set_wifi_by_login(login, **changes)
        except ACSError:
            return client.set_wifi_by_device_id(device_id, **changes)
    if login:
        return client.set_wifi_by_login(login, **changes)
    return client.set_wifi_by_device_id(device_id, **changes)


def _clean_secret(val):
    if val is None:
        return ''
    s = str(val).strip()
    if not s:
        return ''
    if s.lower() in (
        'não informado',
        'nao informado',
        'n/a',
        'na',
        '-',
        '--',
        '***',
        'not informed',
        'unknown',
    ):
        return ''
    return s


def _format_uptime(raw):
    if raw is None or raw == '':
        return 'N/A'
    if isinstance(raw, str) and not str(raw).strip().isdigit():
        return raw.strip() or 'N/A'
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f'{days}d {hours}h {minutes}m'


def _host_active(item):
    status = str(item.get('status') or item.get('active') or '').strip().lower()
    if status in ('1', 'true', 'online', 'connected', 'active', 'sim'):
        return True
    if status in ('0', 'false', 'offline', 'disconnected', 'inactive'):
        return False
    return True


def _map_hosts(raw_hosts):
    out = []
    if not isinstance(raw_hosts, list):
        return out
    for item in raw_hosts:
        if not isinstance(item, dict):
            continue
        mac = item.get('mac') or item.get('MACAddress') or ''
        ip = item.get('ip') or item.get('IPAddress') or ''
        hostname = item.get('hostname') or item.get('HostName') or 'Dispositivo sem nome'
        if not mac and not ip:
            continue
        out.append({
            'hostname': hostname or 'Dispositivo sem nome',
            'ip': ip or '0.0.0.0',
            'mac': mac or '00:00:00:00:00:00',
            'active': _host_active(item),
            'lease_time': item.get('lease_time') or item.get('leaseTimeRemaining') or 0,
            'interface': item.get('interface') or '',
            'status': item.get('status') or '',
        })
    return out


def _snapshot_fields(data):
    d = data if isinstance(data, dict) else {}
    inner = d
    for key in ('data', 'wifi', 'result', 'body'):
        nested = d.get(key)
        if isinstance(nested, dict):
            inner = {**d, **nested}
            break
    ssid_2g = (
        inner.get('wifi_ssid')
        or inner.get('ssid_24')
        or inner.get('ssid_2g')
        or inner.get('ssid')
        or ''
    )
    ssid_5g = (
        inner.get('wifi_ssid_5g')
        or inner.get('ssid_5')
        or inner.get('ssid_5g')
        or inner.get('ssid_5ghz')
        or ''
    )
    pass_2g = _clean_secret(
        inner.get('wifi_pass_24')
        or inner.get('pass_24')
        or inner.get('password_2g')
        or inner.get('wifi_password')
        or inner.get('password')
    )
    pass_5g = _clean_secret(
        inner.get('wifi_pass_5g')
        or inner.get('pass_5')
        or inner.get('password_5g')
        or inner.get('wifi_password_5g')
    )
    hosts = _map_hosts(inner.get('hosts') or inner.get('lan_hosts') or inner.get('connected_devices'))
    uptime_raw = inner.get('uptime') or inner.get('wan_up_time') or inner.get('sys_up_time')
    return {
        'ssid_2g': ssid_2g or None,
        'password_2g': pass_2g or None,
        'ssid_5g': ssid_5g or None,
        'password_5g': pass_5g or None,
        'serial': ('' if inner.get('serial') is None else str(inner.get('serial')).strip()) or None,
        'manufacturer': inner.get('manufacturer') or inner.get('vendor') or 'Desconhecido',
        'model': inner.get('product_class') or inner.get('model') or inner.get('model_name') or 'Desconhecido',
        'device_id': inner.get('device_id') or None,
        'ip': inner.get('wan_ip') or inner.get('external_ip') or inner.get('ip') or '0.0.0.0',
        'uptime': _format_uptime(uptime_raw),
        'uptime_raw': uptime_raw,
        'is_online': inner.get('is_online'),
        'hosts': hosts,
        'pppoe_user': inner.get('pppoe_user') or inner.get('pppoe') or None,
    }


def _app_wifi_payload(fields, *, cached_user=None, mensagem=None, online=True):
    user = cached_user
    ssid = fields.get('ssid_2g') or (user.wifi_ssid_2g if user else None)
    password = fields.get('password_2g') or (user.wifi_password_2g if user else None)
    ssid_5 = fields.get('ssid_5g') or (user.wifi_ssid_5g if user else None)
    password_5 = fields.get('password_5g') or (user.wifi_password_5g if user else None)
    hosts = fields.get('hosts') or []
    status = 'Online' if online else 'Sem conexão com modem'
    payload = {
        'ssid': ssid,
        'password': password,
        'ssid_5ghz': ssid_5,
        'password_5ghz': password_5,
        'wifi_ssid': ssid,
        'wifi_password': password,
        'wifi_ssid_5ghz': ssid_5,
        'wifi_ssid_5g': ssid_5,
        'wifi_password_5ghz': password_5,
        'serial': fields.get('serial'),
        'model': fields.get('serial') or fields.get('model') or (user.modem_model if user else 'Desconhecido'),
        'product_class': fields.get('model'),
        'manufacturer': fields.get('manufacturer') or (user.modem_manufacturer if user else 'Desconhecido'),
        'wan_up_time': fields.get('uptime') or 'N/A',
        'uptime_raw': fields.get('uptime_raw') or (
            user.modem_uptime_seconds if user and user.modem_uptime_seconds is not None else None
        ),
        'sys_up_time': fields.get('uptime_raw') or (
            user.modem_uptime_seconds if user and user.modem_uptime_seconds is not None else None
        ),
        'ip': fields.get('ip') or (user.modem_external_ip if user else '0.0.0.0'),
        'wan_ip': fields.get('ip'),
        'status': status,
        'connected_count': len(hosts),
        'connected_devices': hosts,
        'erro': False,
    }
    if mensagem:
        payload['mensagem'] = mensagem
    return payload


def _persist_snapshot(app_user, fields, login=None):
    update_fields = []
    if fields.get('password_2g') or fields.get('ssid_2g'):
        if fields.get('ssid_2g'):
            app_user.wifi_ssid_2g = fields['ssid_2g']
            update_fields.append('wifi_ssid_2g')
        if fields.get('password_2g'):
            app_user.wifi_password_2g = fields['password_2g']
            update_fields.append('wifi_password_2g')
    if fields.get('password_5g') or fields.get('ssid_5g'):
        if fields.get('ssid_5g'):
            app_user.wifi_ssid_5g = fields['ssid_5g']
            update_fields.append('wifi_ssid_5g')
        if fields.get('password_5g'):
            app_user.wifi_password_5g = fields['password_5g']
            update_fields.append('wifi_password_5g')
    if fields.get('device_id') and fields['device_id'] != app_user.genieacs_device_id:
        app_user.genieacs_device_id = str(fields['device_id'])[:255]
        update_fields.append('genieacs_device_id')
    real_login = fields.get('pppoe_user') or login
    if real_login and (app_user.pppoe_login or '') != real_login:
        app_user.pppoe_login = str(real_login)[:100]
        update_fields.append('pppoe_login')
    if fields.get('model'):
        app_user.modem_model = str(fields['model'])[:255]
        update_fields.append('modem_model')
    if fields.get('manufacturer'):
        app_user.modem_manufacturer = str(fields['manufacturer'])[:255]
        update_fields.append('modem_manufacturer')
    if fields.get('ip') and fields['ip'] != '0.0.0.0':
        app_user.modem_external_ip = str(fields['ip'])[:64]
        update_fields.append('modem_external_ip')
    raw_uptime = fields.get('uptime_raw')
    if raw_uptime is not None:
        try:
            app_user.modem_uptime_seconds = int(raw_uptime)
            update_fields.append('modem_uptime_seconds')
        except (TypeError, ValueError):
            pass
    app_user.modem_last_sync_at = timezone.now()
    update_fields.append('modem_last_sync_at')
    if update_fields:
        app_user.save(update_fields=list(set(update_fields)))


def _acs_error_status(exc: ACSError):
    code = exc.status_code or 502
    if code == 404:
        return 404
    if code < 400 or code == 200:
        return 502
    if code >= 500:
        return 502
    return code


def _cached_or_error(app_user, exc: ACSError):
    msg = str(exc) or 'Falha ao ler configurações do modem.'
    has_cache = any([
        app_user.wifi_ssid_2g,
        app_user.wifi_password_2g,
        app_user.wifi_ssid_5g,
        app_user.wifi_password_5g,
    ])
    if not has_cache:
        return Response({'erro': True, 'mensagem': msg}, status=_acs_error_status(exc))
    uptime_str = 'N/A'
    if app_user.modem_uptime_seconds is not None:
        uptime_str = _format_uptime(app_user.modem_uptime_seconds)
    return Response(_app_wifi_payload(
        {
            'ssid_2g': app_user.wifi_ssid_2g,
            'password_2g': app_user.wifi_password_2g,
            'ssid_5g': app_user.wifi_ssid_5g,
            'password_5g': app_user.wifi_password_5g,
            'serial': None,
            'model': app_user.modem_model or 'Desconhecido',
            'manufacturer': app_user.modem_manufacturer or 'Desconhecido',
            'ip': app_user.modem_external_ip or '0.0.0.0',
            'uptime': uptime_str,
            'uptime_raw': app_user.modem_uptime_seconds,
            'hosts': [],
        },
        cached_user=app_user,
        mensagem=msg,
        online=False,
    ))


@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def wifi_config_api(request):
    resolved, err = _require_provedor(request, from_body=True)
    if err:
        return err
    provedor, profile = resolved

    contrato = (
        request.query_params.get('contrato')
        or request.data.get('contrato')
        or request.GET.get('contrato')
    )
    if not contrato:
        return Response({'erro': True, 'mensagem': 'Contrato não informado.'}, status=400)

    cpf = (
        request.query_params.get('cpf')
        or request.data.get('cpf')
        or request.data.get('cpf_cnpj')
    )
    app_user = _find_app_user(provedor, contrato, cpf=cpf)
    if not app_user:
        return Response(
            {'erro': True, 'mensagem': 'Contrato não encontrado ou sem login PPPoE vinculado.'},
            status=404,
        )

    login = _login_for_contract(app_user, profile, contrato)
    device_id = (app_user.genieacs_device_id or '').strip()
    if not login and not device_id:
        return Response(
            {'erro': True, 'mensagem': 'Contrato não encontrado ou sem login PPPoE vinculado.'},
            status=404,
        )

    client = ACSClient.from_mobile_profile(profile, provedor=provedor)
    if not client:
        return Response(
            {'erro': True, 'mensagem': 'Integração ACS não configurada (URL/token).'},
            status=404,
        )

    if request.method == 'GET':
        try:
            snapshot = _fetch_wifi(client, login, device_id)
        except ACSError as exc:
            logger.warning(
                '[ACS app] wifi GET falhou provedor=%s contrato=%s login=%s: %s',
                provedor.id, contrato, login or '-', exc,
            )
            return _cached_or_error(app_user, exc)

        fields = _snapshot_fields(snapshot)
        _persist_snapshot(app_user, fields, login=login)
        return Response(_app_wifi_payload(fields, cached_user=app_user, online=True))

    novo_ssid = request.data.get('novo_ssid') or request.data.get('ssid_24')
    nova_senha = request.data.get('nova_senha') or request.data.get('pass_24')
    novo_ssid_5g = request.data.get('novo_ssid_5ghz') or request.data.get('ssid_5')
    nova_senha_5g = request.data.get('nova_senha_5ghz') or request.data.get('pass_5')

    if not any([novo_ssid, nova_senha, novo_ssid_5g, nova_senha_5g]):
        return Response({'erro': True, 'mensagem': 'Nenhum parâmetro de alteração enviado.'}, status=400)

    changes = {}
    if novo_ssid:
        changes['ssid_24'] = str(novo_ssid)
    if nova_senha:
        changes['pass_24'] = str(nova_senha)
    if novo_ssid_5g:
        changes['ssid_5'] = str(novo_ssid_5g)
    if nova_senha_5g:
        changes['pass_5'] = str(nova_senha_5g)
    has_24 = 'ssid_24' in changes or 'pass_24' in changes
    has_5 = 'ssid_5' in changes or 'pass_5' in changes
    if has_24 and has_5:
        changes['band'] = 'both'
    elif has_5:
        changes['band'] = '5'
    else:
        changes['band'] = '24'

    try:
        result = _apply_wifi(client, login, device_id, **changes)
    except ACSError as exc:
        logger.warning(
            '[ACS app] wifi POST falhou provedor=%s contrato=%s login=%s: %s',
            provedor.id, contrato, login or '-', exc,
        )
        msg = str(exc) or 'Falha ao aplicar configurações no modem via ACS.'
        return Response({'erro': True, 'mensagem': msg}, status=_acs_error_status(exc))

    if novo_ssid:
        app_user.wifi_ssid_2g = str(novo_ssid)[:100]
    if nova_senha:
        app_user.wifi_password_2g = str(nova_senha)[:100]
    if novo_ssid_5g:
        app_user.wifi_ssid_5g = str(novo_ssid_5g)[:100]
    if nova_senha_5g:
        app_user.wifi_password_5g = str(nova_senha_5g)[:100]
    app_user.save()

    event = 'wifi_password_changed' if (nova_senha or nova_senha_5g) else 'wifi_ssid_changed'
    log_mobile_activity(
        provedor=provedor,
        event=event,
        user=app_user,
        request=request,
        metadata={'contrato': str(contrato), 'band': changes.get('band')},
    )

    acs_msg = ''
    if isinstance(result, dict):
        acs_msg = result.get('message') or ''
    return Response({
        'erro': False,
        'mensagem': acs_msg or 'Configuração Wi-Fi enviada com sucesso! Aguarde alguns instantes.',
    })


@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def lan_hosts_api(request):
    resolved, err = _require_provedor(request)
    if err:
        return err
    provedor, profile = resolved

    contrato = request.query_params.get('contrato') or request.GET.get('contrato')
    if not contrato:
        return Response({'erro': True, 'mensagem': 'Contrato não informado.'}, status=400)

    cpf = request.query_params.get('cpf') or request.GET.get('cpf')
    app_user = _find_app_user(provedor, contrato, cpf=cpf)
    if not app_user:
        return Response(
            {'erro': True, 'mensagem': 'Contrato não encontrado ou sem login PPPoE vinculado.'},
            status=404,
        )

    login = _login_for_contract(app_user, profile, contrato)
    device_id = (app_user.genieacs_device_id or '').strip()
    if not login and not device_id:
        return Response(
            {'erro': True, 'mensagem': 'Contrato não encontrado ou sem login PPPoE vinculado.'},
            status=404,
        )

    client = ACSClient.from_mobile_profile(profile, provedor=provedor)
    if not client:
        return Response(
            {'erro': True, 'mensagem': 'Integração ACS não configurada (URL/token).'},
            status=404,
        )

    try:
        snapshot = _fetch_wifi(client, login, device_id)
    except ACSError as exc:
        logger.warning(
            '[ACS app] hosts GET falhou provedor=%s contrato=%s login=%s: %s',
            provedor.id, contrato, login or '-', exc,
        )
        msg = str(exc) or 'Modem não encontrado ou API indisponível.'
        return Response({'erro': True, 'mensagem': msg}, status=_acs_error_status(exc))

    fields = _snapshot_fields(snapshot)
    _persist_snapshot(app_user, fields, login=login)
    hosts = fields.get('hosts') or []
    return Response({
        'devices': hosts,
        'count': len(hosts),
        'status': 'success',
        'erro': False,
    })
