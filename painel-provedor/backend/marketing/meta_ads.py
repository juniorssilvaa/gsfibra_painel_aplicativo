"""Cliente da API de Marketing da Meta usado pelo Estúdio (criar, editar, pausar e analisar campanhas)."""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GRAPH_VERSION = 'v24.0'
GRAPH = f'https://graph.facebook.com/{GRAPH_VERSION}'
TIMEOUT = 40
WHATSAPP_LINK = 'https://api.whatsapp.com/send'
REQUIRED_SCOPES = (
    'ads_management',
    'ads_read',
    'business_management',
    'pages_show_list',
    'pages_read_engagement',
    'pages_manage_ads',
)
TOKEN_EXPIRED_MSG = 'A conexão com o Facebook expirou ou foi revogada. Clique em "Reconectar Facebook" no Estúdio.'

PERIODOS = {
    'hoje': 'today',
    'ontem': 'yesterday',
    '7d': 'last_7d',
    '14d': 'last_14d',
    '30d': 'last_30d',
    '90d': 'last_90d',
    'maximo': 'maximum',
}

CHAMADAS_SITE = {
    'saiba_mais': 'LEARN_MORE',
    'assinar': 'SUBSCRIBE',
    'cadastre_se': 'SIGN_UP',
    'fale_conosco': 'CONTACT_US',
    'ver_oferta': 'GET_OFFER',
    'comprar': 'SHOP_NOW',
}

GENEROS = {'todos': None, 'homens': [1], 'mulheres': [2]}

UF_ESTADOS = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 'CE': 'Ceará',
    'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 'MA': 'Maranhão', 'MT': 'Mato Grosso',
    'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná',
    'PE': 'Pernambuco', 'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo',
    'SE': 'Sergipe', 'TO': 'Tocantins',
}

ACTION_LABELS = {
    'onsite_conversion.messaging_conversation_started_7d': 'conversas_iniciadas',
    'link_click': 'cliques_no_link',
    'landing_page_view': 'visualizacoes_da_pagina',
    'lead': 'cadastros',
    'post_engagement': 'engajamento',
}

INSIGHT_FIELDS = 'spend,impressions,reach,frequency,clicks,ctr,cpc,cpm,actions,cost_per_action_type'


class MetaAdsError(Exception):
    pass


def _app_credentials() -> Tuple[str, str]:
    app_id = getattr(settings, 'FACEBOOK_APP_ID', None) or '713538217881661'
    secret = getattr(settings, 'FACEBOOK_APP_SECRET', '') or ''
    if not secret:
        raise MetaAdsError('FACEBOOK_APP_SECRET não está configurado no servidor.')
    return str(app_id), secret


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', text).strip().lower()


def _error_text(body: Any, status_code: int) -> str:
    err = (body or {}).get('error') if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return f'A Meta respondeu HTTP {status_code}.'
    if err.get('code') == 190:
        return TOKEN_EXPIRED_MSG
    title = (err.get('error_user_title') or '').strip()
    msg = (err.get('error_user_msg') or err.get('message') or '').strip()
    text = f'{title}: {msg}' if title and msg else (msg or title or f'Erro {err.get("code")}')
    return f'Meta: {text}'


def _encode(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        for k, v in data.items()
        if v is not None
    }


def graph(method: str, path: str, token: str, params: Optional[Dict[str, Any]] = None,
          data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f'{GRAPH}/{path.lstrip("/")}'
    query = _encode({**(params or {}), 'access_token': token})
    try:
        if method == 'GET':
            resp = requests.get(url, params=query, timeout=TIMEOUT)
        else:
            resp = requests.request(method, url, params={'access_token': token}, data=_encode(data or {}), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise MetaAdsError(f'Falha de rede ao falar com a Meta ({exc.__class__.__name__}). Tente novamente.')
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400 or (isinstance(body, dict) and body.get('error')):
        raise MetaAdsError(_error_text(body, resp.status_code))
    return body if isinstance(body, dict) else {'data': body}


# ---------------------------------------------------------------- conexão

def _debug_token(token: str) -> Dict[str, Any]:
    app_id, secret = _app_credentials()
    data = graph('GET', 'debug_token', f'{app_id}|{secret}', {'input_token': token}).get('data') or {}
    if str(data.get('app_id') or '') != app_id or not data.get('is_valid'):
        raise MetaAdsError('O login do Facebook não é válido para o app da NioHub. Tente conectar novamente.')
    return data


def exchange_token(short_token: str) -> Dict[str, Any]:
    """Valida o token do login e troca por um de longa duração."""
    if not short_token:
        raise MetaAdsError('Login do Facebook não retornou o token.')
    _debug_token(short_token)
    app_id, secret = _app_credentials()
    exchanged = graph('GET', 'oauth/access_token', short_token, {
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': secret,
        'fb_exchange_token': short_token,
    })
    token = exchanged.get('access_token') or short_token
    info = _debug_token(token)
    expires_at = None
    if info.get('expires_at'):
        expires_at = datetime.fromtimestamp(int(info['expires_at']), tz=UTC)
    me = graph('GET', 'me', token, {'fields': 'id,name'})
    scopes = list(info.get('scopes') or [])
    return {
        'access_token': token,
        'expires_at': expires_at,
        'scopes': scopes,
        'missing_scopes': [s for s in REQUIRED_SCOPES if s not in scopes],
        'user_id': me.get('id') or '',
        'user_name': me.get('name') or '',
    }


def list_ad_accounts(token: str) -> List[Dict[str, Any]]:
    data = graph('GET', 'me/adaccounts', token, {
        'fields': 'id,name,account_status,currency,business{name}',
        'limit': 100,
    }).get('data') or []
    return [
        {
            'id': a.get('id'),
            'name': a.get('name') or a.get('id'),
            'currency': a.get('currency') or '',
            'active': a.get('account_status') == 1,
            'business': (a.get('business') or {}).get('name') or '',
        }
        for a in data
    ]


def list_pages(token: str) -> List[Dict[str, Any]]:
    data = graph('GET', 'me/accounts', token, {
        'fields': 'id,name,instagram_business_account{id,username}',
        'limit': 100,
    }).get('data') or []
    return [
        {
            'id': p.get('id'),
            'name': p.get('name') or p.get('id'),
            'instagram_user_id': (p.get('instagram_business_account') or {}).get('id') or '',
            'instagram_username': (p.get('instagram_business_account') or {}).get('username') or '',
        }
        for p in data
    ]


# ---------------------------------------------------------------- público

def _split_uf(nome: str) -> Tuple[str, str]:
    match = re.match(r'^(.*?)[\s,/\-]+([A-Za-z]{2})$', (nome or '').strip())
    if match and match.group(2).upper() in UF_ESTADOS:
        return match.group(1).strip(), match.group(2).upper()
    return (nome or '').strip(), ''


COUNTRY_ALIASES = {'brasil': ('BR', 'Brasil'), 'brazil': ('BR', 'Brasil'), 'br': ('BR', 'Brasil')}


def _state_name(region: Optional[str]) -> str:
    return _norm(re.sub(r'\s*\(state\)\s*$', '', region or '', flags=re.I))


def _geo_search(token: str, q: str, types: List[str], country: Optional[str] = 'BR') -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {'type': 'adgeolocation', 'q': q, 'location_types': types, 'limit': 15}
    if country:
        params['country_code'] = country
    return graph('GET', 'search', token, params).get('data') or []


def _suggestions(results: List[Dict[str, Any]]) -> str:
    return ', '.join(f"{r.get('name')} - {r.get('region') or ''}".strip(' -') for r in results[:5]) or 'nenhuma'


def _resolve_country(token: str, nome: str) -> Tuple[str, str]:
    alias = COUNTRY_ALIASES.get(_norm(nome))
    if alias:
        return alias
    results = _geo_search(token, nome, ['country'], country=None)
    match = next((r for r in results if _norm(r.get('name')) == _norm(nome) or str(r.get('key')).upper() == nome.upper()), None)
    if not match:
        raise MetaAdsError(f'País "{nome}" não encontrado na Meta. Parecidos: {_suggestions(results)}.')
    return str(match['key']), match.get('name') or nome


def _resolve_state(token: str, nome: str) -> Dict[str, Any]:
    results = _geo_search(token, nome, ['region'])
    match = next((r for r in results if _norm(r.get('name')) == _norm(nome)), None)
    if not match:
        raise MetaAdsError(f'Estado "{nome}" não encontrado na Meta. Parecidos: {_suggestions(results)}.')
    return match


def resolve_locations(token: str, locais: List[Any]) -> Tuple[Dict[str, Any], List[str]]:
    """País, estados e cidades por nome → geo_locations da Meta. Ambiguidade vira erro com as opções."""
    countries, cities, regions, labels = [], [], [], []
    for item in locais or []:
        if isinstance(item, str):
            item = {'nome': item}
        raw = str(item.get('nome') or '').strip()
        tipo = _norm(item.get('tipo') or '')
        if not raw:
            continue

        if tipo == 'pais' or (not tipo and _norm(raw) in COUNTRY_ALIASES):
            code, label = _resolve_country(token, raw)
            if code not in countries:
                countries.append(code)
                labels.append(f'País inteiro: {label}')
            continue

        sem_prefixo = re.sub(r'^estado\s+(do|da|de)\s+', '', raw, flags=re.I).strip()
        uf_sozinha = raw.upper() if raw.upper() in UF_ESTADOS else ''
        if tipo == 'estado' or uf_sozinha or sem_prefixo != raw:
            region = _resolve_state(token, UF_ESTADOS[uf_sozinha] if uf_sozinha else sem_prefixo)
            regions.append({'key': str(region['key'])})
            labels.append(f"Estado inteiro: {region.get('name')}")
            continue

        nome, uf = _split_uf(raw)
        types = ['city'] if tipo == 'cidade' or uf else ['city', 'region']
        results = _geo_search(token, nome, types)
        exact = [r for r in results if _norm(r.get('name')) == _norm(nome)]
        if uf:
            exact = [r for r in exact if _state_name(r.get('region')) == _norm(UF_ESTADOS[uf])]
        if not exact:
            raise MetaAdsError(f'Local "{raw}" não encontrado na Meta. Parecidos: {_suggestions(results)}.')
        cidades = [r for r in exact if r.get('type') == 'city']
        estados = [r for r in exact if r.get('type') == 'region']
        if cidades and estados:
            raise MetaAdsError(
                f'"{nome}" pode ser o estado inteiro ou só a cidade. Pergunte ao dono e informe tipo "estado" ou "cidade".'
            )
        if len(cidades) > 1:
            opcoes = ', '.join(f"{r.get('name')} - {r.get('region')}" for r in cidades[:6])
            raise MetaAdsError(f'Existe mais de uma cidade chamada "{nome}": {opcoes}. Informe a UF.')
        if estados:
            regions.append({'key': str(estados[0]['key'])})
            labels.append(f"Estado inteiro: {estados[0].get('name')}")
            continue
        chosen = cidades[0]
        entry = {'key': str(chosen['key'])}
        raio = item.get('raio_km')
        estado_nome = re.sub(r'\s*\(state\)\s*$', '', chosen.get('region') or '')
        label = f"{chosen.get('name')} - {estado_nome}"
        if raio:
            raio = max(17, min(80, int(float(raio))))
            entry.update({'radius': raio, 'distance_unit': 'kilometer'})
            label += f' (+{raio} km)'
        cities.append(entry)
        labels.append(label)
    geo: Dict[str, Any] = {}
    if countries:
        geo['countries'] = countries
    if cities:
        geo['cities'] = cities
    if regions:
        geo['regions'] = regions
    return geo, labels


def resolve_points(pontos: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    custom, labels = [], []
    for p in pontos or []:
        try:
            lat, lng = float(p['latitude']), float(p['longitude'])
        except (KeyError, TypeError, ValueError):
            raise MetaAdsError('Cada ponto precisa de latitude e longitude numéricas.')
        raio = max(1, min(80, float(p.get('raio_km') or 3)))
        custom.append({'latitude': lat, 'longitude': lng, 'radius': raio, 'distance_unit': 'kilometer'})
        labels.append(f'Ponto {lat:.5f},{lng:.5f} (raio {raio:g} km)')
    return custom, labels


def resolve_interests(token: str, termos: List[str]) -> List[Dict[str, str]]:
    found = []
    for termo in termos or []:
        termo = str(termo or '').strip()
        if not termo:
            continue
        data = graph('GET', 'search', token, {'type': 'adinterest', 'q': termo, 'limit': 5}).get('data') or []
        if not data:
            raise MetaAdsError(f'Interesse "{termo}" não existe na Meta. Tente outro termo.')
        chosen = next((d for d in data if _norm(d.get('name')) == _norm(termo)), data[0])
        if not any(f['id'] == str(chosen['id']) for f in found):
            found.append({'id': str(chosen['id']), 'name': chosen.get('name') or termo})
    return found


def build_targeting(geo: Dict[str, Any], custom: List[Dict[str, Any]], idade_min: int, idade_max: int,
                    generos: str, interesses: List[Dict[str, str]], has_instagram: bool) -> Dict[str, Any]:
    geo = dict(geo)
    if custom:
        geo['custom_locations'] = custom
    if not geo:
        raise MetaAdsError('Informe pelo menos um país, estado, cidade ou ponto no mapa para segmentar o anúncio.')
    if 'BR' in geo.get('countries', []) and (geo.get('cities') or geo.get('regions') or custom):
        raise MetaAdsError(
            'O Brasil inteiro já inclui as cidades, estados e pontos pedidos. Use só o Brasil ou só os locais específicos.'
        )
    geo['location_types'] = ['home', 'recent']
    targeting: Dict[str, Any] = {
        'geo_locations': geo,
        'age_min': max(18, min(65, int(idade_min or 18))),
        'age_max': max(18, min(65, int(idade_max or 65))),
        'targeting_automation': {'advantage_audience': 0},
    }
    if targeting['age_min'] > targeting['age_max']:
        raise MetaAdsError('A idade mínima não pode ser maior que a máxima.')
    if GENEROS.get(generos or 'todos'):
        targeting['genders'] = GENEROS[generos]
    if interesses:
        targeting['flexible_spec'] = [{'interests': interesses}]
    if not has_instagram:
        targeting['publisher_platforms'] = ['facebook']
    return targeting


# ---------------------------------------------------------------- criação / edição

def _to_minor(valor_reais) -> int:
    try:
        value = round(float(str(valor_reais).replace(',', '.')) * 100)
    except (TypeError, ValueError):
        raise MetaAdsError('Orçamento diário inválido.')
    if value <= 0:
        raise MetaAdsError('O orçamento diário precisa ser maior que zero.')
    return int(value)


def format_money(minor, currency: str = 'BRL') -> str:
    try:
        value = int(minor) / 100
    except (TypeError, ValueError):
        return ''
    text = f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {text}' if (currency or 'BRL') == 'BRL' else f'{currency} {text}'


def parse_day(value: Optional[str], end: bool = False) -> Optional[str]:
    """'AAAA-MM-DD' → ISO no fuso do servidor (início 00:00, fim 23:59). Datas passadas no início = agora."""
    if not value:
        return None
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        raise MetaAdsError(f'Data inválida: {value}. Use AAAA-MM-DD.')
    moment = timezone.make_aware(datetime.combine(day, time(23, 59) if end else time(0, 0)))
    if not end and moment <= timezone.now():
        return None
    if end and moment <= timezone.now():
        raise MetaAdsError('A data de término já passou.')
    return moment.isoformat()


def ad_image_jpeg(data: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert('RGB')
    img.thumbnail((2048, 2048), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=92)
    return out.getvalue()


def upload_image(conn, data: bytes) -> str:
    body = graph('POST', f'{conn.ad_account_id}/adimages', conn.access_token, data={
        'bytes': base64.b64encode(ad_image_jpeg(data)).decode('ascii'),
    })
    images = body.get('images') or {}
    for info in images.values():
        if info.get('hash'):
            return info['hash']
    raise MetaAdsError('A Meta não devolveu o código da imagem enviada.')


def story_spec(conn, criativo: Dict[str, Any], image_hash: str) -> Dict[str, Any]:
    link_data: Dict[str, Any] = {
        'image_hash': image_hash,
        'message': criativo['texto_principal'],
        'name': criativo.get('titulo') or None,
        'description': criativo.get('descricao') or None,
    }
    if criativo['destino'] == 'whatsapp':
        link_data['link'] = WHATSAPP_LINK
        link_data['call_to_action'] = {'type': 'WHATSAPP_MESSAGE', 'value': {'app_destination': 'WHATSAPP'}}
    else:
        link_data['link'] = criativo['link']
        link_data['call_to_action'] = {
            'type': CHAMADAS_SITE.get(criativo.get('chamada') or 'saiba_mais', 'LEARN_MORE'),
            'value': {'link': criativo['link']},
        }
    spec: Dict[str, Any] = {'page_id': conn.page_id, 'link_data': {k: v for k, v in link_data.items() if v}}
    if conn.instagram_user_id:
        spec['instagram_user_id'] = conn.instagram_user_id
    return spec


def create_campaign(conn, payload: Dict[str, Any], image_data: bytes) -> Dict[str, Any]:
    """Cria campanha → conjunto → criativo → anúncio pausados e só ativa a campanha no fim."""
    act = conn.ad_account_id
    token = conn.access_token
    criativo = payload['criativo']
    whatsapp = criativo['destino'] == 'whatsapp'
    image_hash = upload_image(conn, image_data)

    campaign = graph('POST', f'{act}/campaigns', token, data={
        'name': payload['nome'],
        'objective': 'OUTCOME_ENGAGEMENT' if whatsapp else 'OUTCOME_TRAFFIC',
        'status': 'PAUSED',
        'special_ad_categories': [],
        'buying_type': 'AUCTION',
        'daily_budget': payload['orcamento_diario'],
        'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
    })
    campaign_id = campaign['id']
    try:
        adset_data = {
            'name': f"{payload['nome']} - Público",
            'campaign_id': campaign_id,
            'billing_event': 'IMPRESSIONS',
            'optimization_goal': 'CONVERSATIONS' if whatsapp else 'LINK_CLICKS',
            'destination_type': 'WHATSAPP' if whatsapp else 'WEBSITE',
            'targeting': payload['targeting'],
            'start_time': payload.get('inicio'),
            'end_time': payload.get('fim'),
            'status': 'ACTIVE',
        }
        if whatsapp:
            adset_data['promoted_object'] = {'page_id': conn.page_id}
        adset = graph('POST', f'{act}/adsets', token, data=adset_data)
        creative = graph('POST', f'{act}/adcreatives', token, data={
            'name': f"{payload['nome']} - Criativo",
            'object_story_spec': story_spec(conn, criativo, image_hash),
        })
        ad = graph('POST', f'{act}/ads', token, data={
            'name': f"{payload['nome']} - Anúncio",
            'adset_id': adset['id'],
            'creative': {'creative_id': creative['id']},
            'status': 'ACTIVE',
        })
        graph('POST', campaign_id, token, data={'status': 'ACTIVE'})
    except MetaAdsError as exc:
        try:
            graph('POST', campaign_id, token, data={'status': 'DELETED'})
        except MetaAdsError:
            logger.warning('[MetaAds] Não foi possível apagar a campanha incompleta %s', campaign_id)
        raise MetaAdsError(f'{exc} (nada foi publicado; a campanha incompleta foi descartada)')
    return {'campanha_id': campaign_id, 'conjunto_id': adset['id'], 'criativo_id': creative['id'], 'anuncio_id': ad['id']}


def campaign_structure(conn, campaign_id: str) -> Dict[str, Any]:
    data = graph('GET', campaign_id, conn.access_token, {
        'fields': (
            'id,account_id,name,objective,status,effective_status,daily_budget,lifetime_budget,start_time,stop_time,'
            'adsets.limit(20){id,name,status,targeting,start_time,end_time,destination_type},'
            'ads.limit(20){id,name,status,effective_status,creative{id,object_story_spec}}'
        ),
    })
    if str(data.get('account_id') or '') != conn.ad_account_id.replace('act_', ''):
        raise MetaAdsError('Esta campanha não pertence à conta de anúncios conectada.')
    return data


def update_campaign(conn, campaign_id: str, payload: Dict[str, Any], image_data: Optional[bytes]) -> Dict[str, Any]:
    token = conn.access_token
    current = campaign_structure(conn, campaign_id)
    applied = []

    campaign_fields = {}
    if payload.get('nome'):
        campaign_fields['name'] = payload['nome']
    if payload.get('orcamento_diario'):
        campaign_fields['daily_budget'] = payload['orcamento_diario']
    if campaign_fields:
        graph('POST', campaign_id, token, data=campaign_fields)
        applied.append('campanha')

    adsets = (current.get('adsets') or {}).get('data') or []
    for adset in adsets:
        adset_fields = {}
        if payload.get('targeting_patch'):
            targeting = dict(adset.get('targeting') or {})
            targeting.update(payload['targeting_patch'])
            for key in payload.get('targeting_remove') or []:
                targeting.pop(key, None)
            targeting['targeting_automation'] = {'advantage_audience': 0}
            adset_fields['targeting'] = targeting
        if payload.get('fim'):
            adset_fields['end_time'] = payload['fim']
        if adset_fields:
            graph('POST', adset['id'], token, data=adset_fields)
    if adsets and (payload.get('targeting_patch') or payload.get('fim')):
        applied.append('público/datas')

    if payload.get('criativo_patch') or image_data:
        ads = (current.get('ads') or {}).get('data') or []
        if not ads:
            raise MetaAdsError('A campanha não tem anúncio para editar.')
        image_hash = upload_image(conn, image_data) if image_data else None
        for ad in ads:
            spec = ((ad.get('creative') or {}).get('object_story_spec') or {})
            link_data = dict(spec.get('link_data') or {})
            patch = payload.get('criativo_patch') or {}
            for src, dst in (('texto_principal', 'message'), ('titulo', 'name'), ('descricao', 'description')):
                if src in patch:
                    link_data[dst] = patch[src]
            if patch.get('link'):
                link_data['link'] = patch['link']
                cta = dict(link_data.get('call_to_action') or {})
                if cta.get('type') != 'WHATSAPP_MESSAGE':
                    cta['value'] = {'link': patch['link']}
                    link_data['call_to_action'] = cta
            if image_hash:
                link_data['image_hash'] = image_hash
                link_data.pop('picture', None)
                link_data.pop('image_url', None)
            new_spec = {'page_id': spec.get('page_id') or conn.page_id, 'link_data': {k: v for k, v in link_data.items() if v}}
            if spec.get('instagram_user_id') or conn.instagram_user_id:
                new_spec['instagram_user_id'] = spec.get('instagram_user_id') or conn.instagram_user_id
            creative = graph('POST', f'{conn.ad_account_id}/adcreatives', token, data={
                'name': f"{current.get('name')} - Criativo editado",
                'object_story_spec': new_spec,
            })
            graph('POST', ad['id'], token, data={'creative': {'creative_id': creative['id']}})
        applied.append('anúncio')

    if payload.get('status') in ('ACTIVE', 'PAUSED'):
        graph('POST', campaign_id, token, data={'status': payload['status']})
        applied.append('ativada' if payload['status'] == 'ACTIVE' else 'pausada')
    return {'campanha_id': campaign_id, 'alterado': applied}


def set_campaign_status(conn, campaign_id: str, status: str) -> None:
    if status not in ('ACTIVE', 'PAUSED'):
        raise MetaAdsError('Status inválido.')
    campaign_structure(conn, campaign_id)
    graph('POST', campaign_id, conn.access_token, data={'status': status})


def pause_campaign(conn, campaign_id: str) -> None:
    set_campaign_status(conn, campaign_id, 'PAUSED')


# ---------------------------------------------------------------- análise

def _metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ('spend', 'impressions', 'reach', 'clicks'):
        if row.get(key) is not None:
            out[{'spend': 'gasto', 'impressions': 'impressoes', 'reach': 'alcance', 'clicks': 'cliques'}[key]] = float(row[key]) if key == 'spend' else int(float(row[key]))
    for key, label in (('ctr', 'ctr_%'), ('cpc', 'cpc'), ('cpm', 'cpm'), ('frequency', 'frequencia')):
        if row.get(key) is not None:
            out[label] = round(float(row[key]), 2)
    for action in row.get('actions') or []:
        label = ACTION_LABELS.get(action.get('action_type'))
        if label:
            out[label] = int(float(action.get('value') or 0))
    for action in row.get('cost_per_action_type') or []:
        label = ACTION_LABELS.get(action.get('action_type'))
        if label:
            out[f'custo_por_{label}'] = round(float(action.get('value') or 0), 2)
    return out


def _preset(periodo: Optional[str]) -> str:
    return PERIODOS.get(periodo or '30d', 'last_30d')


def list_campaigns(conn, periodo: str = '30d') -> Dict[str, Any]:
    token = conn.access_token
    campaigns = graph('GET', f'{conn.ad_account_id}/campaigns', token, {
        'fields': 'id,name,objective,status,effective_status,daily_budget,lifetime_budget,start_time,stop_time,created_time',
        'limit': 50,
    }).get('data') or []
    insights = graph('GET', f'{conn.ad_account_id}/insights', token, {
        'level': 'campaign',
        'fields': f'campaign_id,{INSIGHT_FIELDS}',
        'date_preset': _preset(periodo),
        'limit': 100,
    }).get('data') or []
    by_id = {row.get('campaign_id'): _metrics(row) for row in insights}
    return {
        'periodo': periodo,
        'moeda': conn.currency or 'BRL',
        'campanhas': [
            {
                'id': c['id'],
                'nome': c.get('name'),
                'objetivo': c.get('objective'),
                'status': c.get('effective_status') or c.get('status'),
                'orcamento_diario': format_money(c.get('daily_budget'), conn.currency) if c.get('daily_budget') else None,
                'inicio': (c.get('start_time') or '')[:10] or None,
                'fim': (c.get('stop_time') or '')[:10] or None,
                'metricas': by_id.get(c['id']) or {},
            }
            for c in campaigns
        ],
    }


HIDDEN_STATUSES = {'DELETED', 'ARCHIVED'}
ACTIVE_FIRST = {'ACTIVE': 0, 'IN_PROCESS': 1, 'WITH_ISSUES': 1, 'PENDING_REVIEW': 1}


def _all(path: str, token: str, params: Dict[str, Any], max_pages: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    after = None
    for _ in range(max_pages):
        page = graph('GET', path, token, {**params, **({'after': after} if after else {})})
        out.extend(page.get('data') or [])
        paging = page.get('paging') or {}
        after = (paging.get('cursors') or {}).get('after')
        if not after or not paging.get('next'):
            break
    return out


def _creative_view(creative: Dict[str, Any]) -> Dict[str, str]:
    spec = creative.get('object_story_spec') or {}
    link = spec.get('link_data') or {}
    video = spec.get('video_data') or {}
    feed = creative.get('asset_feed_spec') or {}
    first = lambda key: next((i.get('text') for i in feed.get(key) or [] if i.get('text')), '')
    cta = link.get('call_to_action') or video.get('call_to_action') or {}
    return {
        'imagem': creative.get('image_url') or link.get('picture') or video.get('image_url') or creative.get('thumbnail_url') or '',
        'titulo': creative.get('title') or link.get('name') or video.get('title') or first('titles'),
        'texto': creative.get('body') or link.get('message') or video.get('message') or first('bodies'),
        'link': link.get('link') or next((u.get('website_url') for u in feed.get('link_urls') or [] if u.get('website_url')), ''),
        'botao': cta.get('type') or next(iter(feed.get('call_to_action_types') or []), ''),
    }


def _ad_problem(ad: Dict[str, Any]) -> str:
    issues = [i.get('error_summary') or i.get('error_message') for i in ad.get('issues_info') or []]
    feedback = (ad.get('ad_review_feedback') or {}).get('global') or {}
    reasons = [f'{k}: {v}' if v else k for k, v in feedback.items()]
    return ' · '.join(t for t in issues + reasons if t)[:500]


def _budget(entity: Dict[str, Any]) -> Tuple[int, int]:
    return int(entity.get('daily_budget') or 0), int(entity.get('lifetime_budget') or 0)


ACCOUNT_BLOCKED = {2: 'Conta de anúncios desativada pela Meta', 100: 'Conta de anúncios em encerramento', 101: 'Conta de anúncios encerrada'}
ACCOUNT_BILLING = {3: 'Pagamento pendente na conta de anúncios', 8: 'Pagamento pendente na conta de anúncios', 9: 'Conta em período de carência de pagamento'}
AD_REVIEW = {'PENDING_REVIEW', 'IN_PROCESS', 'PREAPPROVED'}
AD_PAUSED = {'PAUSED', 'ADSET_PAUSED', 'CAMPAIGN_PAUSED'}


def _meta_time(value: str):
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S%z') if value else None
    except ValueError:
        return None


def _plural(n: int, one: str, many: str) -> str:
    return f'{n} {one if n == 1 else many}'


def _delivery(campaign: Dict[str, Any], ads: List[Dict[str, Any]], account_status) -> Dict[str, str]:
    """Situação real de entrega (o que o Gerenciador chama de "Veiculação"), combinando conta, campanha e anúncios."""
    status = campaign.get('effective_status') or ''
    now = datetime.now(UTC)
    start, stop = _meta_time(campaign.get('start_time')), _meta_time(campaign.get('stop_time'))
    view = lambda code, label, detail='': {'codigo': code, 'rotulo': label, 'detalhe': detail}

    if account_status in ACCOUNT_BLOCKED:
        return view('bloqueada', 'Conta bloqueada', ACCOUNT_BLOCKED[account_status])
    if account_status in ACCOUNT_BILLING or status == 'PENDING_BILLING_INFO':
        return view('pagamento', 'Pagamento pendente', ACCOUNT_BILLING.get(account_status, 'Pagamento pendente na conta de anúncios'))
    if account_status == 7:
        return view('em_analise', 'Em análise', 'A Meta está revisando a conta de anúncios')
    if status == 'PAUSED':
        return view('pausada', 'Pausada', 'Campanha pausada')
    if stop and stop <= now:
        return view('concluida', 'Concluída', f'Terminou em {stop.strftime("%d/%m/%Y")}')
    if not ads:
        return view('sem_anuncios', 'Sem anúncios', 'A campanha não tem anúncios ativos')

    states = [a.get('status') or '' for a in ads]
    active = states.count('ACTIVE')
    review = sum(s in AD_REVIEW for s in states)
    issues = states.count('WITH_ISSUES')
    rejected = states.count('DISAPPROVED')
    paused = sum(s in AD_PAUSED for s in states)
    problem = next((a.get('problema') for a in ads if a.get('problema')), '')
    others = ', '.join(t for t in (
        review and _plural(review, 'anúncio em análise', 'anúncios em análise'),
        rejected and _plural(rejected, 'anúncio reprovado', 'anúncios reprovados'),
        issues and _plural(issues, 'anúncio com problema', 'anúncios com problema'),
    ) if t)

    if start and start > now and (active or review):
        return view('agendada', 'Agendada', f'Começa em {start.strftime("%d/%m/%Y %H:%M")}')
    if active:
        return view('veiculando', 'Veiculando', others)
    if review:
        return view('em_analise', 'Em análise', 'A Meta está revisando o anúncio (normalmente de minutos a 24 horas)')
    if issues:
        return view('com_problema', 'Com problema', problem)
    if rejected:
        return view('reprovada', 'Reprovado', problem)
    if paused:
        return view('pausada', 'Pausada', 'Conjunto de anúncios pausado' if 'ADSET_PAUSED' in states else 'Anúncios pausados')
    return view('outro', status or 'Desconhecido', '')


def ads_overview(conn, periodo: str = '30d') -> Dict[str, Any]:
    """Campanhas da conta com orçamento, anúncios (imagem/texto) e métricas do período, para a tela do Estúdio."""
    token, account, preset = conn.access_token, conn.ad_account_id, _preset(periodo)
    insight = {'fields': INSIGHT_FIELDS, 'date_preset': preset}
    jobs = {
        'campaigns': (f'{account}/campaigns', {
            'fields': 'id,name,objective,effective_status,daily_budget,lifetime_budget,start_time,stop_time,created_time',
            'limit': 100,
        }),
        'adsets': (f'{account}/adsets', {'fields': 'campaign_id,effective_status,daily_budget,lifetime_budget', 'limit': 200}),
        'ads': (f'{account}/ads', {
            'fields': 'id,name,campaign_id,effective_status,created_time,issues_info,ad_review_feedback,'
                      'creative{thumbnail_url,image_url,title,body,object_story_spec,asset_feed_spec}',
            'limit': 100,
        }),
        'ad_insights': (f'{account}/insights', {**insight, 'level': 'ad', 'fields': f'ad_id,{INSIGHT_FIELDS}', 'limit': 200}),
        'campaign_insights': (f'{account}/insights', {
            **insight, 'level': 'campaign', 'fields': f'campaign_id,{INSIGHT_FIELDS}', 'limit': 200,
        }),
        'total': (f'{account}/insights', insight),
    }
    with ThreadPoolExecutor(max_workers=len(jobs) + 1) as pool:
        futures = {key: pool.submit(_all, path, token, params) for key, (path, params) in jobs.items()}
        account_future = pool.submit(graph, 'GET', account, token, {'fields': 'account_status'})
        data = {key: future.result() for key, future in futures.items()}
        try:
            account_status = account_future.result().get('account_status')
        except MetaAdsError:
            account_status = None

    ad_metrics = {r.get('ad_id'): _metrics(r) for r in data['ad_insights']}
    campaign_metrics = {r.get('campaign_id'): _metrics(r) for r in data['campaign_insights']}
    adset_budget: Dict[str, Tuple[int, int]] = {}
    for adset in data['adsets']:
        if adset.get('effective_status') in HIDDEN_STATUSES:
            continue
        daily, lifetime = _budget(adset)
        prev = adset_budget.get(adset.get('campaign_id'), (0, 0))
        adset_budget[adset.get('campaign_id')] = (prev[0] + daily, prev[1] + lifetime)
    ads_by_campaign: Dict[str, List[Dict[str, Any]]] = {}
    for ad in data['ads']:
        if ad.get('effective_status') in HIDDEN_STATUSES:
            continue
        ads_by_campaign.setdefault(ad.get('campaign_id'), []).append({
            'id': ad.get('id'),
            'nome': ad.get('name') or '',
            'status': ad.get('effective_status') or '',
            'problema': _ad_problem(ad),
            **_creative_view(ad.get('creative') or {}),
            'metricas': ad_metrics.get(ad.get('id')) or {},
        })

    campanhas = []
    for c in data['campaigns']:
        status = c.get('effective_status') or ''
        if status in HIDDEN_STATUSES:
            continue
        daily, lifetime = _budget(c)
        nivel = 'campanha'
        if not daily and not lifetime:
            daily, lifetime = adset_budget.get(c['id'], (0, 0))
            nivel = 'conjunto'
        anuncios = ads_by_campaign.get(c['id'], [])
        campanhas.append({
            'id': c['id'],
            'nome': c.get('name') or '',
            'objetivo': c.get('objective') or '',
            'status': status,
            'orcamento': format_money(daily or lifetime, conn.currency) if (daily or lifetime) else None,
            'orcamento_tipo': 'diario' if daily else ('total' if lifetime else None),
            'orcamento_nivel': nivel,
            'inicio': (c.get('start_time') or '')[:10] or None,
            'fim': (c.get('stop_time') or '')[:10] or None,
            'criada_em': c.get('created_time') or '',
            'metricas': campaign_metrics.get(c['id']) or {},
            'veiculacao': _delivery(c, anuncios, account_status),
            'anuncios': anuncios,
        })
    campanhas.sort(key=lambda c: c['criada_em'], reverse=True)
    campanhas.sort(key=lambda c: ACTIVE_FIRST.get(c['status'], 2))
    return {
        'periodo': periodo,
        'moeda': conn.currency or 'BRL',
        'total': _metrics(data['total'][0]) if data['total'] else {},
        'campanhas': campanhas,
    }


def analyze_campaign(conn, campaign_id: str, periodo: str = '30d') -> Dict[str, Any]:
    token = conn.access_token
    current = campaign_structure(conn, campaign_id)
    preset = _preset(periodo)
    total = graph('GET', f'{campaign_id}/insights', token, {'fields': INSIGHT_FIELDS, 'date_preset': preset}).get('data') or []
    por_anuncio = graph('GET', f'{campaign_id}/insights', token, {
        'level': 'ad', 'fields': f'ad_id,ad_name,{INSIGHT_FIELDS}', 'date_preset': preset, 'limit': 50,
    }).get('data') or []
    por_publico = graph('GET', f'{campaign_id}/insights', token, {
        'fields': INSIGHT_FIELDS, 'date_preset': preset, 'breakdowns': 'age,gender', 'limit': 50,
    }).get('data') or []
    por_posicionamento = graph('GET', f'{campaign_id}/insights', token, {
        'fields': INSIGHT_FIELDS, 'date_preset': preset, 'breakdowns': 'publisher_platform', 'limit': 20,
    }).get('data') or []
    adsets = (current.get('adsets') or {}).get('data') or []
    ads = (current.get('ads') or {}).get('data') or []
    return {
        'campanha': {
            'id': current.get('id'),
            'nome': current.get('name'),
            'objetivo': current.get('objective'),
            'status': current.get('effective_status') or current.get('status'),
            'orcamento_diario': format_money(current.get('daily_budget'), conn.currency) if current.get('daily_budget') else None,
        },
        'periodo': periodo,
        'total': _metrics(total[0]) if total else {},
        'publicos': [
            {'conjunto': a.get('name'), 'segmentacao': a.get('targeting'), 'fim': (a.get('end_time') or '')[:10] or None}
            for a in adsets
        ],
        'anuncios': [
            {
                'id': ad.get('id'),
                'status': ad.get('effective_status') or ad.get('status'),
                'texto': (((ad.get('creative') or {}).get('object_story_spec') or {}).get('link_data') or {}).get('message'),
                'titulo': (((ad.get('creative') or {}).get('object_story_spec') or {}).get('link_data') or {}).get('name'),
                'metricas': next((_metrics(r) for r in por_anuncio if r.get('ad_id') == ad.get('id')), {}),
            }
            for ad in ads
        ],
        'por_idade_genero': [
            {'idade': r.get('age'), 'genero': r.get('gender'), **_metrics(r)} for r in por_publico
        ],
        'por_plataforma': [
            {'plataforma': r.get('publisher_platform'), **_metrics(r)} for r in por_posicionamento
        ],
        'moeda': conn.currency or 'BRL',
    }
