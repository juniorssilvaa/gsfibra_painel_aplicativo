"""Nome de exibição do chatbot nas mensagens automáticas (todos os canais)."""

from __future__ import annotations

import re
from typing import Optional, Tuple


def get_chatbot_display_name(provedor) -> str:
    return str(getattr(provedor, 'chatbot_name', None) or '').strip()


def strip_whatsapp_asterisks(text: str) -> str:
    """
    Remove marcação *negrito* do WhatsApp — no Telegram (texto puro) os *
    aparecem literais.
    """
    if not text:
        return text or ''
    # Pares *texto* → texto
    out = re.sub(r'\*([^*\n]+)\*', r'\1', text)
    # Asteriscos restantes
    return out.replace('*', '')


def prepend_chatbot_name(
    provedor,
    text: str,
    *,
    markdown: bool = True,
) -> Tuple[str, Optional[str]]:
    """
    Prefixa o conteúdo com o nome do chatbot para aparecer no topo da mensagem.
    WhatsApp: *Nome*\\n\\n...
    Telegram (markdown=False): Nome\\n\\n...
    Retorna (texto, nome|None).
    """
    name = get_chatbot_display_name(provedor)
    body = text if text is not None else ''
    if not name:
        return body, None

    stripped = body.lstrip()
    plain_prefix = name
    md_prefix = f'*{name}*'

    # Evitar duplicar se já começa com o nome
    if (
        stripped.startswith(md_prefix)
        or stripped.startswith(plain_prefix + '\n')
        or stripped.startswith(plain_prefix + ':')
    ):
        return body, name

    if not stripped:
        return (md_prefix if markdown else plain_prefix), name

    if markdown:
        return f'{md_prefix}\n\n{body}', name
    return f'{plain_prefix}\n\n{body}', name
