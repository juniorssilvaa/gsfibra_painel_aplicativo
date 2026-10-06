"""Cartão de contato compartilhado no WhatsApp → texto legível para o painel e para a IA."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

PREFIX = '[Contato compartilhado]'


def _from_vcard(vcard: str) -> Tuple[str, List[str]]:
    name = ''
    phones: List[str] = []
    for line in str(vcard or '').splitlines():
        key, _, value = line.partition(':')
        key_upper = key.upper()
        if key_upper.startswith('FN') and value.strip():
            name = value.strip()
        elif key_upper.startswith('TEL') and value.strip():
            phones.append(value.strip())
        elif 'WAID=' in key_upper and not value.strip():
            waid = re.search(r'waid=(\d+)', key, re.IGNORECASE)
            if waid:
                phones.append(f'+{waid.group(1)}')
    return name, phones


def _describe(item: Dict[str, Any]) -> str:
    vcard_name, phones = _from_vcard(item.get('vcard') or '')
    raw_name = item.get('name')
    if isinstance(raw_name, dict):
        raw_name = raw_name.get('formatted_name') or raw_name.get('first_name')
    name = item.get('displayName') or item.get('display_name') or raw_name or vcard_name
    for phone in item.get('phones') or []:
        if isinstance(phone, dict) and phone.get('phone'):
            phones.append(str(phone['phone']))
    phones = list(dict.fromkeys(p for p in phones if p))
    name = str(name or '').strip()
    if name and phones:
        return f'{name}: {", ".join(phones)}'
    return name or ', '.join(phones)


def shared_contact_text(payload: Any, fallback_name: str = '') -> str:
    """Texto do(s) contato(s) compartilhado(s); vazio se o payload não for um cartão de contato."""
    if not isinstance(payload, dict):
        return ''
    items = payload.get('contacts') if isinstance(payload.get('contacts'), list) else [payload]
    described = [d for d in (_describe(i) for i in items if isinstance(i, dict)) if d]
    if not described and fallback_name:
        described = [str(fallback_name).strip()]
    if not described:
        return ''
    return f'{PREFIX} ' + '; '.join(described)
