"""
Utilitários para envio e leitura de CSAT via WhatsApp Cloud API (lista interativa).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# IDs estáveis para list_reply (máx. 200 chars no id)
CSAT_LIST_ROW_IDS = {
    'csat_1': (1, '😡'),
    'csat_2': (2, '😕'),
    'csat_3': (3, '😐'),
    'csat_4': (4, '🙂'),
    'csat_5': (5, '🤩'),
}

CSAT_LIST_ROWS: List[Dict[str, str]] = [
    {'id': 'csat_1', 'title': '😡 Péssimo', 'description': 'Muito insatisfeito'},
    {'id': 'csat_2', 'title': '😕 Ruim', 'description': 'Insatisfeito'},
    {'id': 'csat_3', 'title': '😐 Regular', 'description': 'Neutro / OK'},
    {'id': 'csat_4', 'title': '🙂 Bom', 'description': 'Satisfeito'},
    {'id': 'csat_5', 'title': '🤩 Excelente', 'description': 'Muito satisfeito'},
]


def build_csat_list_body(contact_name: str, provedor_name: str) -> str:
    nome = (contact_name or 'Cliente').split()[0]
    return (
        f"Olá {nome}! Como foi seu atendimento na {provedor_name}? "
        f"Toque no botão abaixo e escolha uma nota."
    )


def parse_csat_rating(
    message_text: str,
    button_id: Optional[str] = None,
) -> Optional[Tuple[int, str]]:
    """
    Interpreta resposta CSAT (lista interativa, emoji ou texto).
    Retorna (rating_value, emoji) ou None se não for CSAT.
    """
    bid = (button_id or '').strip().lower()
    if bid in CSAT_LIST_ROW_IDS:
        rating, emoji = CSAT_LIST_ROW_IDS[bid]
        return rating, emoji

    # IDs alternativos (hash legado do cloud send)
    for key, (rating, emoji) in CSAT_LIST_ROW_IDS.items():
        if bid == key or bid.endswith(key):
            return rating, emoji

    text = (message_text or '').strip()
    if not text:
        return None

    emoji_map = {v[1]: v[0] for v in CSAT_LIST_ROW_IDS.values()}
    for emoji, rating in emoji_map.items():
        if emoji in text:
            return rating, emoji

    # Texto livre: só nota explícita / curta (evita "bom dia", "ok, quero boleto", etc.)
    lower = text.lower().strip()
    # Remover prefixos comuns de título da lista ("😡 péssimo")
    for emoji in ('😡', '😕', '😐', '🙂', '🤩'):
        if lower.startswith(emoji):
            lower = lower[len(emoji):].strip()
            break
    exact = {
        'péssimo': (1, '😡'), 'pessimo': (1, '😡'),
        'ruim': (2, '😕'),
        'regular': (3, '😐'), 'neutro': (3, '😐'),
        'bom': (4, '🙂'),
        'excelente': (5, '🤩'),
        '1': (1, '😡'), '2': (2, '😕'), '3': (3, '😐'), '4': (4, '🙂'), '5': (5, '🤩'),
        'nota 1': (1, '😡'), 'nota 2': (2, '😕'), 'nota 3': (3, '😐'),
        'nota 4': (4, '🙂'), 'nota 5': (5, '🤩'),
    }
    if lower in exact:
        return exact[lower]

    return None


def send_csat_interactive_list(csat_request) -> bool:
    """
    Envia pesquisa CSAT como lista interativa (API oficial WhatsApp).
    """
    try:
        from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api

        conversation = csat_request.conversation
        contact = csat_request.contact
        provedor = csat_request.provedor
        contact_name = contact.name or 'Cliente'
        provedor_name = provedor.nome or 'nossa equipe'
        body = build_csat_list_body(contact_name, provedor_name)

        success, response = send_via_whatsapp_cloud_api(
            conversation=conversation,
            content=body,
            message_type='interactive',
            rows=CSAT_LIST_ROWS,
            button_text='Avaliar atendimento',
            section_title='Sua nota',
            header='Pesquisa de satisfação',
            footer=provedor_name[:60] if provedor_name else '',
        )
        if success:
            logger.info(
                f"[CSAT] Lista interativa enviada: request={csat_request.id}, "
                f"conversa={conversation.id}"
            )
            return True
        logger.warning(
            f"[CSAT] Falha ao enviar lista interativa request={csat_request.id}: {response}"
        )
        return False
    except Exception as e:
        logger.error(f"[CSAT] Erro ao enviar lista interativa: {e}", exc_info=True)
        return False
