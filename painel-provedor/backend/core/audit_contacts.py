"""
Resolução de contato/conversa para a auditoria (conversas encerradas no Supabase).

As tabelas `conversations` e `contacts` do Supabase usam `id` global, mas cada tenant tem
sua própria sequência — IDs colidem entre provedores (conversa não gravada / contato
sobrescrito). `mensagens` guarda provedor_id + contact_id corretos, e o Contact local
não é removido na migração, então essas são as fontes confiáveis.
"""
import logging
import re

import requests

logger = logging.getLogger(__name__)

_CLOSED_BY_NAME_RE = re.compile(r'encerrada manualmente por\s+(.+?)\s+com\s', re.IGNORECASE)
_HUMAN_CLOSE_ACTIONS = ('conversation_closed_manual', 'conversation_closed_agent')

IN_CHUNK = 200
PAGE_SIZE = 1000


def supabase_get_in(url, headers, column, values, select, extra_params=None, timeout=10):
    values = [v for v in values if v is not None]
    rows = []
    for i in range(0, len(values), IN_CHUNK):
        chunk = ','.join(str(v) for v in values[i:i + IN_CHUNK])
        base = {column: f'in.({chunk})', 'select': select, **(extra_params or {})}
        offset = 0
        while True:
            try:
                response = requests.get(
                    url, headers=headers, params={**base, 'limit': PAGE_SIZE, 'offset': offset}, timeout=timeout,
                )
            except Exception as exc:
                logger.warning('[AUDIT] Falha ao buscar %s: %s', url, exc)
                break
            if response.status_code != 200:
                break
            batch = response.json()
            if not isinstance(batch, list):
                break
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            offset += len(batch)
    return rows


def conversations_from_messages(supabase_url, headers, provedor_id, conversation_ids, messages_table='mensagens'):
    """{conversation_id: {id, contact_id, created_at}} a partir de `mensagens` do provedor."""
    result = {}
    if not provedor_id or not conversation_ids:
        return result
    for row in supabase_get_in(
        f'{supabase_url}/rest/v1/{messages_table}', headers, 'conversation_id', list(conversation_ids),
        'conversation_id,contact_id,created_at',
        {'provedor_id': f'eq.{provedor_id}', 'order': 'created_at.asc'},
    ):
        cid = row.get('conversation_id')
        if cid is None:
            continue
        entry = result.setdefault(cid, {'id': cid, 'contact_id': None, 'created_at': row.get('created_at')})
        if not entry['contact_id'] and row.get('contact_id'):
            entry['contact_id'] = row['contact_id']
    return result


def resolve_contacts(supabase_url, headers, provedor_id, contact_ids):
    """{contact_id: {id, name, phone, avatar}} — Contact local do provedor, depois Supabase escopado."""
    contact_ids = {int(c) for c in contact_ids if c}
    result = {}
    if not contact_ids:
        return result
    try:
        from conversations.models import Contact
        qs = Contact.objects.filter(id__in=contact_ids)
        if provedor_id:
            qs = qs.filter(provedor_id=provedor_id)
        for c in qs.only('id', 'name', 'phone', 'avatar'):
            result[c.id] = {'id': c.id, 'name': c.name, 'phone': c.phone, 'avatar': getattr(c, 'avatar', None) or None}
    except Exception as exc:
        logger.warning('[AUDIT] Falha ao buscar contatos locais: %s', exc)

    missing = contact_ids - set(result)
    if missing and supabase_url:
        extra = {'provedor_id': f'eq.{provedor_id}'} if provedor_id else None
        for row in supabase_get_in(
            f'{supabase_url}/rest/v1/contacts', headers, 'id', list(missing), 'id,name,phone,avatar', extra,
        ):
            if row.get('id') is not None:
                result.setdefault(row['id'], row)
    return result


def resolve_closed_by(action, details, user_name=None, user_id=None, conv_attrs=None):
    """(tipo, nome) de quem encerrou: tipo em agent | ai | chatbot | system."""
    details = details if isinstance(details, dict) else {}
    text = details.get('details') if isinstance(details.get('details'), str) else ''
    attrs = conv_attrs if isinstance(conv_attrs, dict) else {}
    closure_source = str(attrs.get('closure_source') or '')

    if action in _HUMAN_CLOSE_ACTIONS:
        if user_name:
            return 'agent', user_name
        match = _CLOSED_BY_NAME_RE.search(text)
        if match:
            return 'agent', match.group(1).strip()

    if closure_source.startswith('chatbot'):
        return 'chatbot', 'Chatbot'
    if action == 'conversation_closed_ai' or closure_source.startswith('ia_'):
        return 'ai', 'IA'
    if action == 'conversation_closed_timeout':
        return 'ai', 'IA (inatividade)'
    if user_name:
        return 'agent', user_name
    if user_id is not None:
        return 'agent', 'Atendente'
    if attrs.get('encerrado_por') == 'ai' or attrs.get('resolucao_automacao'):
        return 'ai', 'IA'
    return 'system', 'Sistema'
