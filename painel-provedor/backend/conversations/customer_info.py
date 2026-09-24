"""Resumo do cliente de uma conversa (contato + dados do ERP/SGP) para o app do atendente."""
import logging
import re
from datetime import date, datetime

from django.core.cache import cache

logger = logging.getLogger(__name__)

_CONTACT_DOC_KEYS = ('cpf_cnpj', 'document', 'sgp_document', 'app_cpf', 'cpf', 'cnpj')
_STATE_DOC_KEYS = ('cpf_cnpj', 'cpfcnpj', 'cpf', 'cnpj', 'document')
_DATE_KEY_HINTS = ('datacadastro', 'data_cadastro', 'dtcadastro', 'cadastro', 'dataativacao',
                   'data_ativacao', 'ativacao', 'datacriacao', 'data_criacao', 'datainicio',
                   'data_inicio', 'datahabilitacao', 'habilitacao')
_CACHE_SECONDS = 300


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def _valid_doc(value):
    d = _digits(value)
    return d if len(d) in (11, 14) else None


def find_document(conversation):
    """CPF/CNPJ já informado pelo cliente (contato, conversa ou memória da IA/chatbot)."""
    contact_attrs = (conversation.contact.additional_attributes or {}) if conversation.contact_id else {}
    for key in _CONTACT_DOC_KEYS:
        doc = _valid_doc(contact_attrs.get(key))
        if doc:
            return doc

    conv_attrs = conversation.additional_attributes or {}
    for key in _STATE_DOC_KEYS:
        doc = _valid_doc(conv_attrs.get(key))
        if doc:
            return doc

    memory = conv_attrs.get('chatbot_memory')
    state = memory.get('state') if isinstance(memory, dict) else None
    if isinstance(state, dict):
        for source in (state, state.get('flow_context') or {}):
            if not isinstance(source, dict):
                continue
            for key in _STATE_DOC_KEYS:
                doc = _valid_doc(source.get(key))
                if doc:
                    return doc
    return None


def format_document(doc):
    if not doc:
        return None
    if len(doc) == 11:
        return f'{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}'
    return f'{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}'


def _find_date(data):
    if not isinstance(data, dict):
        return None
    for key, value in data.items():
        low = str(key).lower()
        if value and any(h in low for h in _DATE_KEY_HINTS) and not isinstance(value, (dict, list)):
            return str(value)
    return None


def _parse_date(value):
    s = str(value or '').strip()[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value or '').replace('R$', '').strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _financial_summary(faturas_resp, contratos):
    faturas = []
    if isinstance(faturas_resp, dict):
        faturas = faturas_resp.get('links') or faturas_resp.get('faturas') or []
    elif isinstance(faturas_resp, list):
        faturas = faturas_resp
    faturas = [f for f in faturas if isinstance(f, dict)]

    today = date.today()
    vencidas = 0
    total = 0.0
    for f in faturas:
        venc = _parse_date(f.get('vencimento') or f.get('vencimento_br') or f.get('data_vencimento'))
        if venc and venc < today:
            vencidas += 1
        total += _to_float(f.get('valor') or f.get('valor_corrigido') or 0)

    suspenso = any(
        str(c.get('status') or '').lower().startswith('suspens') for c in contratos
    )
    if suspenso:
        status, label = 'suspenso', 'Contrato suspenso'
    elif vencidas:
        status, label = 'em_atraso', f'Em atraso ({vencidas} fatura{"s" if vencidas > 1 else ""})'
    elif faturas:
        status, label = 'em_aberto', f'Fatura em aberto ({len(faturas)})'
    else:
        status, label = 'em_dia', 'Em dia'

    return {
        'status': status,
        'label': label,
        'faturas_abertas': len(faturas),
        'faturas_vencidas': vencidas,
        'valor_aberto': round(total, 2),
    }


def _erp_lookup(provedor, doc):
    from core.sgp_client import SGPClient
    from core.sgp_contract_utils import get_contrato_id, get_plano_nome

    integ = provedor.integracoes_externas or {}
    sgp_cfg = integ.get('sgp') if isinstance(integ.get('sgp'), dict) else {}
    url = sgp_cfg.get('sgp_url') or integ.get('sgp_url')
    token = sgp_cfg.get('sgp_token') or integ.get('sgp_token')
    app = sgp_cfg.get('sgp_app') or integ.get('sgp_app')
    if not (url and token and app):
        return {'configured': False}

    cache_key = f'customer_info_erp:{provedor.id}:{doc}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    client = SGPClient(base_url=url, token=token, app_name=app)
    try:
        resp = client.consultar_cliente(doc) or {}
    except Exception as exc:
        logger.warning('[customer_info] SGP consultar_cliente falhou provedor=%s: %s', provedor.id, exc)
        return {'configured': True, 'found': False, 'error': 'Não foi possível consultar o ERP.'}

    raw_contratos = [c for c in (resp.get('contratos') or []) if isinstance(c, dict)]
    contratos = []
    for c in raw_contratos:
        contratos.append({
            'id': get_contrato_id(c),
            'plano': get_plano_nome(c),
            'status': c.get('contratoStatusDisplay') or c.get('status') or '',
            'data_cadastro': _find_date(c),
        })

    nome = resp.get('razaoSocial') or resp.get('nome') or resp.get('nomeCliente')
    if not nome and raw_contratos:
        nome = raw_contratos[0].get('razaoSocial') or raw_contratos[0].get('nome')

    if not nome and not contratos:
        result = {'configured': True, 'found': False}
        cache.set(cache_key, result, _CACHE_SECONDS)
        return result

    try:
        faturas = client.listar_faturas_v2(cpf_cnpj=doc)
    except Exception as exc:
        logger.warning('[customer_info] SGP faturas falhou provedor=%s: %s', provedor.id, exc)
        faturas = {}

    data_cadastro = _find_date(resp) or next(
        (c['data_cadastro'] for c in contratos if c['data_cadastro']), None
    )
    result = {
        'configured': True,
        'found': True,
        'nome': nome,
        'data_cadastro': data_cadastro,
        'contratos': contratos,
        'financeiro': _financial_summary(faturas, contratos),
    }
    cache.set(cache_key, result, _CACHE_SECONDS)
    return result


def build_customer_info(conversation):
    contact = conversation.contact
    inbox = conversation.inbox
    doc = find_document(conversation)

    channel = None
    if inbox is not None:
        channel = getattr(inbox, 'custom_name', None) or getattr(inbox, 'name', None) \
            or getattr(inbox, 'channel_type', None)
    channel = channel or getattr(conversation, 'channel_type', None)

    info = {
        'conversation_id': conversation.id,
        'name': getattr(contact, 'name', None),
        'phone': getattr(contact, 'phone', None),
        'email': getattr(contact, 'email', None),
        'avatar': getattr(contact, 'avatar', None),
        'channel': channel,
        'channel_type': getattr(inbox, 'channel_type', None) if inbox is not None else None,
        'cpf_cnpj': format_document(doc),
        'erp': None,
    }

    provedor = getattr(inbox, 'provedor', None) if inbox is not None else None
    if doc and provedor is not None:
        info['erp'] = _erp_lookup(provedor, doc)
    return info
