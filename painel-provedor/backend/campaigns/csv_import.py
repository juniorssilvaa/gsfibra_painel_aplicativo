"""Leitura do CSV de destinatários da campanha (só nome e telefone).

Aceita planilhas simples (nome;telefone;...) e o export do Google Contatos / celular
(First Name, Last Name, Phone 1 - Value, ...), igual à importação da tela de Contatos.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Dict, List, Optional, Tuple

from campaigns.service import fold_key
from core.phone_utils import digits_only, is_valid_whatsapp_phone, looks_like_brazilian_local, normalize_whatsapp_phone

NAME_KEYS = (
    'nome', 'name', 'cliente', 'nome_do_cliente', 'nome_cliente', 'razao_social', 'contato', 'full_name',
    'display_name', 'nome_completo',
)
FIRST_KEYS = ('first_name', 'given_name', 'primeiro_nome')
MIDDLE_KEYS = ('middle_name', 'additional_name', 'nome_do_meio')
LAST_KEYS = ('last_name', 'family_name', 'sobrenome')
FALLBACK_NAME_KEYS = ('nickname', 'apelido', 'file_as', 'organization_name', 'organization_1_name', 'empresa')
PHONE_KEYS = (
    'telefone', 'phone', 'celular', 'whatsapp', 'whats_app', 'fone', 'numero', 'numero_telefone',
    'telefone_celular', 'tel', 'mobile', 'cell', 'cellphone', 'msisdn', 'mobile_phone',
)
GOOGLE_PHONE = re.compile(r'^phone_\d+_value$')
MOJIBAKE = re.compile('[ÃÂâð][\u0080-\u00bf\u0152-\u2122]')
MAX_ROWS = 20000


def _decode(raw: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError('Não foi possível ler o arquivo (codificação inválida).')


def _mojibake_bytes(s: str) -> bytes:
    out = bytearray()
    for ch in s:
        try:
            out += ch.encode('cp1252')
        except UnicodeEncodeError:
            if ord(ch) <= 255:
                out.append(ord(ch))
    return bytes(out)


def fix_text(value) -> str:
    """Limpa a célula e conserta acentos quebrados por Excel (ex.: 'PerfuraÃ§Ã£o' -> 'Perfuração')."""
    s = re.sub(r'\s+', ' ', str(value or '')).strip()
    if s and MOJIBAKE.search(s):
        # Emojis podem perder bytes no Excel; os pedaços irrecuperáveis são descartados.
        fixed = _mojibake_bytes(s).decode('utf-8', errors='replace').replace('\ufffd', '').strip()
        if fixed and len(MOJIBAKE.findall(fixed)) < len(MOJIBAKE.findall(s)):
            return re.sub(r'\s+', ' ', fixed)
    return s


def _phone_digits(value: str) -> str:
    s = str(value or '').strip().replace('@s.whatsapp.net', '').replace('@lid', '')
    if re.match(r'^\d+[,.]\d+[eE]\+\d+$', s):
        try:
            s = str(int(float(s.replace(',', '.'))))
        except ValueError:
            pass
    if not s.startswith('+'):
        d = digits_only(s)
        if d.startswith('0'):
            d = d.lstrip('0')
            if len(d) in (12, 13) and looks_like_brazilian_local(d[2:]):
                d = d[2:]
            s = d
    return normalize_whatsapp_phone(s)


def _first_valid_phone(values) -> str:
    for value in values:
        for part in str(value or '').split(':::'):
            phone = _phone_digits(part)
            if is_valid_whatsapp_phone(phone):
                return phone
    return ''


def _col(folded: Dict[str, str], keys) -> Optional[str]:
    return next((folded[k] for k in keys if k in folded), None)


def parse_recipients_csv(raw: bytes) -> Tuple[List[Dict], Dict]:
    """Retorna (destinatários, resumo). Cada destinatário: {nome, telefone, dados}."""
    text = _decode(raw)
    sample = text[:8192]
    counts = {d: sample.count(d) for d in (';', ',', '\t')}
    delimiter = max(counts, key=counts.get) if any(counts.values()) else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [h for h in (reader.fieldnames or []) if h]
    if not headers:
        raise ValueError('O CSV precisa ter uma linha de cabeçalho (ex.: nome;telefone).')

    folded = {}
    for h in headers:
        folded.setdefault(fold_key(fix_text(h)), h)
    rows = list(reader)[:MAX_ROWS]

    name_col = _col(folded, NAME_KEYS)
    name_parts = [c for c in (_col(folded, FIRST_KEYS), _col(folded, MIDDLE_KEYS), _col(folded, LAST_KEYS)) if c]
    fallback_name_cols = [folded[k] for k in FALLBACK_NAME_KEYS if k in folded]

    phone_cols = [c for c in [_col(folded, PHONE_KEYS)] if c]
    phone_cols += [h for k, h in folded.items() if GOOGLE_PHONE.match(k) and h not in phone_cols]
    if not phone_cols:
        for h in headers:
            if any(is_valid_whatsapp_phone(_phone_digits(row.get(h))) for row in rows[:5]):
                phone_cols = [h]
                break
    if not phone_cols:
        raise ValueError('Não encontrei a coluna de telefone no CSV (use o cabeçalho "telefone").')

    recipients, seen, invalid = [], set(), 0
    for row in rows:
        phone = _first_valid_phone(row.get(c) for c in phone_cols)
        if not phone:
            invalid += 1
            continue
        if phone in seen:
            continue
        seen.add(phone)

        nome = fix_text(row.get(name_col)) if name_col else ''
        if not nome:
            nome = ' '.join(p for p in (fix_text(row.get(c)) for c in name_parts) if p)
        if not nome:
            nome = next((v for v in (fix_text(row.get(c)) for c in fallback_name_cols) if v), '')

        recipients.append({'nome': nome[:255], 'telefone': phone, 'dados': {}})

    return recipients, {'linhas': len(rows), 'invalidos': invalid}
