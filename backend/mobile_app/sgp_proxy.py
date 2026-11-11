"""Proxy SGP para o app mobile (compatível com app_provedor /api/sgp/<endpoint>)."""
import logging
import re

import requests
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import MobileAppUser
from .services import (
    app_user_access_denied_from_payload,
    provedor_access_denied,
    resolve_provedor_from_provider_token,
    sgp_contract_id,
    sgp_pppoe_login,
)

logger = logging.getLogger(__name__)

ENDPOINT_MAP = {
    'cliente/consulta': 'api/ura/consultacliente',
    'faturas': 'api/ura/faturas',
    'ura/titulos': 'api/ura/titulos',
    'central/contratos': 'api/central/contratos',
    'ura/consultacliente': 'api/ura/consultacliente',
    'central/extratouso': 'api/central/extratouso',
    'central/chamado': 'api/central/chamado',
    'central/chamado/list': 'api/central/chamado/list',
    'ura/chamado': 'api/ura/chamado',
    'ura/liberacaopromessa': 'api/ura/liberacaopromessa',
    'wifi/config': 'api/wifi/config',
    'central/notafiscal/list': 'api/central/notafiscal/list',
    'ura/notafiscal': 'api/central/notafiscal/list',
    'ura/verificaacesso': 'api/ura/verificaacesso',
}

FORCE_FORM_MARKERS = (
    'api/ura/titulos',
    'api/central/extratouso',
    'api/central/chamado',
    'api/ura/chamado',
    'api/ura/liberacaopromessa',
    'api/ura/consultacliente',
    'api/central/notafiscal/list',
)


def _resolve_provedor(request):
    provider_token = request.query_params.get('provider_token') or request.data.get('provider_token')
    if not provider_token:
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if auth.startswith('Bearer '):
            provider_token = auth.split(' ', 1)[1].strip()
    if not provider_token:
        provider_token = request.META.get('HTTP_X_PROVIDER_TOKEN', '').strip() or None
    if not provider_token:
        return None
    token = str(provider_token).strip()
    # App às vezes envia a URL da API por engano no lugar do sk_live_*
    if token.startswith('http://') or token.startswith('https://') or '/v1' in token:
        logger.warning('SGP proxy: provider_token inválido (parece URL): %s', token[:80])
        return None
    return resolve_provedor_from_provider_token(token, require_active=False)


def _sync_app_user_from_contratos(provedor, payload, resp_json):
    """Atualiza PPPoE/customer_id no MobileAppUser a partir da lista de contratos."""
    if not isinstance(resp_json, dict):
        return

    contracts_list = []
    if isinstance(resp_json.get('contratos'), list):
        contracts_list = resp_json['contratos']
    elif isinstance(resp_json, list) and resp_json and (
        'contrato' in resp_json[0] or 'servico_login' in resp_json[0]
    ):
        contracts_list = resp_json

    payload_contrato = str(
        (payload or {}).get('contrato')
        or (payload or {}).get('contract_id')
        or (payload or {}).get('contratoId')
        or (payload or {}).get('idcontrato')
        or ''
    ).strip()

    for c in contracts_list:
        if not isinstance(c, dict):
            continue
        cpf_raw = c.get('cpfCnpj') or c.get('cpf_cnpj')
        if not cpf_raw:
            continue
        cpf = re.sub(r'\D', '', str(cpf_raw))
        user = MobileAppUser.objects.filter(provedor=provedor, cpf=cpf).first()
        if not user:
            continue

        contract_id = sgp_contract_id(c)
        pppoe = sgp_pppoe_login(c)
        wanted = payload_contrato or str(user.customer_id or '').strip()
        if wanted and contract_id and contract_id != wanted:
            continue

        update_fields = {}
        if pppoe and pppoe != (user.pppoe_login or ''):
            update_fields['pppoe_login'] = pppoe[:100]
        if contract_id and contract_id != str(user.customer_id or ''):
            if wanted:
                if contract_id == wanted:
                    update_fields['customer_id'] = contract_id
            elif not user.customer_id:
                update_fields['customer_id'] = contract_id
        if update_fields:
            MobileAppUser.objects.filter(pk=user.pk).update(**update_fields)


@csrf_exempt
@api_view(['POST', 'GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def proxy_sgp_request(request, endpoint):
    try:
        provedor = _resolve_provedor(request)
        if not provedor:
            return Response({
                'error': 'Provedor não identificado. Envie provider_token.',
                'is_active': False,
                'is_blocked': True,
                'provider_blocked': True,
            }, status=403)

        try:
            profile = provedor.mobile_app
        except Exception:
            return Response({
                'error': 'App não habilitado para este provedor',
                'is_active': False,
                'is_blocked': True,
                'provider_blocked': True,
                'provider_name': provedor.nome,
            }, status=403)

        if provedor_access_denied(provedor) or not profile.is_active:
            return Response({
                'error': 'Acesso desativado. Entre em contato com o suporte.',
                'is_active': False,
                'is_blocked': True,
                'provider_blocked': True,
                'user_blocked': False,
                'provider_name': provedor.nome,
            }, status=403)

        if not profile.sgp_token or not profile.sgp_url:
            return Response(
                {'error': f'Provedor {provedor.nome} sem credenciais do ERP configuradas no painel.'},
                status=400,
            )

        sgp_token = str(profile.sgp_token).strip()
        if sgp_token.startswith('sk_live_') or sgp_token.startswith('sk_test_'):
            logger.warning(
                'SGP proxy: sgp_token do perfil parece token Niohub (sk_live), não o token do ERP. provedor=%s',
                provedor.id,
            )
            return Response({
                'error': (
                    'Token do ERP inválido no painel. Em Integração ERP, use o token da API '
                    '(SGP ou ReceitaNet Central Digital — não o sk_live_ do aplicativo).'
                ),
            }, status=400)

        if request.method == 'POST':
            payload = request.data.copy() if isinstance(request.data, dict) else request.data.dict()
        else:
            payload = request.query_params.dict().copy()

        denied_user = app_user_access_denied_from_payload(provedor, payload)
        if denied_user:
            return Response(
                {'error': denied_user, 'user_blocked': True, 'is_blocked': True},
                status=403,
            )

        erp_type = (getattr(profile, 'erp_type', None) or 'sgp').strip().lower()
        if erp_type == 'receitanet':
            from .receitanet_adapter import handle_receitanet_proxy

            resp = handle_receitanet_proxy(request, endpoint, profile)
            _sync_app_user_from_contratos(provedor, payload, getattr(resp, 'data', None))
            return resp

        payload['token'] = sgp_token
        payload['app'] = profile.sgp_app_name or 'gsfibra'
        payload.pop('provider_id', None)
        payload.pop('provider_token', None)

        clean = endpoint.lstrip('/').rstrip('/')
        if endpoint.startswith('central/contratos'):
            final_endpoint = 'api/ura/consultacliente'
        else:
            final_endpoint = ENDPOINT_MAP.get(clean, clean)

        base_domain = (
            profile.sgp_url.split('/api/')[0]
            if '/api/' in profile.sgp_url
            else profile.sgp_url.rstrip('/')
        )
        # SGP URA responde em HTTPS; HTTP no nginx costuma devolver 404
        if base_domain.lower().startswith('http://'):
            base_domain = 'https://' + base_domain[7:]
        target_url = f"{base_domain}/{final_endpoint}"
        if not target_url.endswith('/'):
            target_url += '/'

        if 'cpf_cnpj' in payload:
            payload['cpfcnpj'] = re.sub(r'[^0-9]', '', str(payload.pop('cpf_cnpj')))
        if 'cpfcnpj' in payload:
            payload['cpfcnpj'] = re.sub(r'[^0-9]', '', str(payload['cpfcnpj']))

        logger.info('SGP proxy %s %s -> %s provedor=%s', request.method, endpoint, target_url, provedor.id)

        if request.method == 'GET':
            upstream = requests.get(target_url, params=payload, timeout=30)
        else:
            content_type = request.content_type or ''
            force_form = any(m in target_url for m in FORCE_FORM_MARKERS)
            if 'application/json' in content_type and not force_form:
                upstream = requests.post(target_url, json=payload, timeout=30)
            else:
                upstream = requests.post(target_url, data=payload, timeout=30)

        logger.info(
            'SGP upstream %s %s status=%s bytes=%s provedor=%s',
            request.method,
            target_url,
            upstream.status_code,
            len(upstream.content or b''),
            provedor.id,
        )

        try:
            resp_json = upstream.json()
        except Exception:
            snippet = (upstream.text or '')[:240]
            logger.warning('SGP upstream non-JSON status=%s body=%s', upstream.status_code, snippet)
            if upstream.status_code in (401, 403):
                return Response({
                    'error': 'SGP recusou a consulta. Verifique URL, token e nome do app no painel (Integração ERP).',
                    'sgp_status': upstream.status_code,
                }, status=400)
            return Response(upstream.content, status=upstream.status_code)

        if upstream.status_code in (401, 403):
            logger.warning(
                'SGP recusou %s status=%s body=%s provedor=%s',
                target_url,
                upstream.status_code,
                str(resp_json)[:300],
                provedor.id,
            )
            sgp_msg = None
            if isinstance(resp_json, dict):
                sgp_msg = resp_json.get('msg') or resp_json.get('message') or resp_json.get('error') or resp_json.get('detail')
            return Response({
                'error': sgp_msg or (
                    'SGP recusou a consulta. Verifique token e nome do app no painel (Integração ERP).'
                ),
                'sgp_status': upstream.status_code,
            }, status=400)

        if isinstance(resp_json, dict):
            for key in ('titulos', 'links'):
                items = resp_json.get(key) or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and 'codigoPix' in item and 'codigopix' not in item:
                            item['codigopix'] = item['codigoPix']

            _sync_app_user_from_contratos(provedor, payload, resp_json)

        return Response(resp_json, status=upstream.status_code)
    except Exception as exc:
        logger.exception('ERRO PROXY SGP: %s', exc)
        return Response({'error': str(exc)}, status=500)
