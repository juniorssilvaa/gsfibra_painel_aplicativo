"""Envio de mensagens via Instagram Messaging API (Instagram Login)."""
import logging
from typing import Optional, Tuple

from integrations.instagram_media import build_instagram_public_url

logger = logging.getLogger(__name__)

GRAPH_IG_VERSION = 'v25.0'


def _resolve_canal(canal) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not canal or not canal.token:
        return None, None, 'Canal Instagram sem token'
    ig_user_id = (canal.dados_extras or {}).get('instagram_user_id')
    if not ig_user_id:
        return None, None, 'Canal Instagram sem instagram_user_id'
    return str(ig_user_id), canal.token, None


def _post_messages(canal, payload: dict) -> Tuple[bool, Optional[dict], Optional[str]]:
    ig_user_id, token, err = _resolve_canal(canal)
    if err:
        return False, None, err

    url = f'https://graph.instagram.com/{GRAPH_IG_VERSION}/{ig_user_id}/messages'
    try:
        import requests

        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=60,
        )
        data = response.json() if response.content else {}

        if response.ok:
            return True, data, None

        err_obj = data.get('error') or {}
        error_msg = err_obj.get('message') or response.text or f'HTTP {response.status_code}'
        logger.warning(
            '[InstagramSend] Falha envio: %s (subcode=%s)',
            error_msg,
            err_obj.get('error_subcode'),
        )
        return False, data, error_msg
    except Exception as exc:
        logger.exception('[InstagramSend] Erro ao enviar mensagem')
        return False, None, str(exc)


def map_media_type_to_instagram(media_type: str, mime_type: str = '') -> str:
    mt = (media_type or '').lower()
    if mt in ('image', 'photo'):
        return 'image'
    if mt == 'video':
        return 'video'
    if mt in ('audio', 'ptt', 'myaudio', 'voice'):
        return 'audio'
    if mt in ('document', 'file', 'pdf'):
        return 'file'
    if mt == 'sticker':
        return 'like_heart'

    mime = (mime_type or '').lower()
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    if mime == 'application/pdf':
        return 'file'
    return 'file'


def send_instagram_text(
    canal,
    recipient_igsid: str,
    text: str,
    reply_to_mid: Optional[str] = None,
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    POST https://graph.instagram.com/{IG_ID}/messages
    Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api
    """
    if not recipient_igsid or not text:
        return False, None, 'Destinatário ou texto ausente'

    text = text.replace('*', '').strip()
    if not text:
        return False, None, 'Texto vazio após formatação'

    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'message': {'text': text[:1000]},
    }
    if reply_to_mid:
        payload['reply_to'] = {'mid': str(reply_to_mid)}
        logger.info('[InstagramSend] Enviando reply para mid=%s', reply_to_mid)
        ok, data, err = _post_messages(canal, payload)
        # subcode 2534002 = Invalid parameter (reply_to inválido/expirado)
        if not ok and err and 'invalid parameter' in err.lower():
            logger.warning(
                '[InstagramSend] reply_to rejeitado (%s); reenviando sem reply',
                err,
            )
            payload.pop('reply_to', None)
            return _post_messages(canal, payload)
        return ok, data, err

    return _post_messages(canal, payload)


def send_instagram_sticker(canal, recipient_igsid: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'message': {'attachment': {'type': 'like_heart'}},
    }
    return _post_messages(canal, payload)


def send_instagram_media(
    canal,
    recipient_igsid: str,
    media_type: str,
    media_url: str,
    caption: Optional[str] = None,
    mime_type: str = '',
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Envia imagem, áudio, vídeo ou PDF via URL pública.
    Legenda (caption) é enviada como mensagem de texto separada — a API não suporta caption em anexo.
    """
    if not recipient_igsid or not media_url:
        return False, None, 'Destinatário ou URL de mídia ausente'

    ig_type = map_media_type_to_instagram(media_type, mime_type)
    if ig_type == 'like_heart':
        return send_instagram_sticker(canal, recipient_igsid)

    public_url = build_instagram_public_url(media_url)
    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'message': {
            'attachment': {
                'type': ig_type,
                'payload': {'url': public_url},
            }
        },
    }
    ok, data, err = _post_messages(canal, payload)
    if not ok:
        return ok, data, err

    if caption and caption.strip():
        caption_clean = caption.replace('*', '').strip()
        if caption_clean:
            ok_text, data_text, err_text = send_instagram_text(canal, recipient_igsid, caption_clean)
            if not ok_text:
                logger.warning('[InstagramSend] Mídia enviada, mas legenda falhou: %s', err_text)
            elif isinstance(data, dict) and isinstance(data_text, dict):
                data['caption_message_id'] = data_text.get('message_id')

    return ok, data, err


def send_instagram_reaction(
    canal,
    recipient_igsid: str,
    message_id: str,
    reaction: str = 'love',
) -> Tuple[bool, Optional[dict], Optional[str]]:
    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'sender_action': 'react',
        'payload': {
            'message_id': str(message_id),
            'reaction': reaction or 'love',
        },
    }
    return _post_messages(canal, payload)


def send_instagram_unreact(
    canal,
    recipient_igsid: str,
    message_id: str,
) -> Tuple[bool, Optional[dict], Optional[str]]:
    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'sender_action': 'unreact',
        'payload': {'message_id': str(message_id)},
    }
    return _post_messages(canal, payload)


def build_instagram_template_buttons(
    msg_btns=None,
    msg_rows=None,
    body_text: str = '',
) -> Tuple[str, list]:
    """Converte botões/rows do chatbot para template button da API Instagram (máx. 3)."""
    items = []
    if msg_btns:
        items.extend(msg_btns if isinstance(msg_btns, list) else [])
    if msg_rows:
        items.extend(msg_rows if isinstance(msg_rows, list) else [])

    ig_buttons = []
    overflow = []

    for idx, btn in enumerate(items):
        title = str(btn.get('title') or btn.get('label') or f'Opção {idx + 1}').strip()
        if idx < 3:
            btn_id = str(btn.get('id') or f'btn_{idx}')
            url = btn.get('url') or btn.get('web_url') or btn.get('link')
            if url and str(url).startswith('http'):
                ig_buttons.append({
                    'type': 'web_url',
                    'url': str(url)[:1000],
                    'title': title[:20],
                })
            else:
                ig_buttons.append({
                    'type': 'postback',
                    'payload': btn_id[:1000],
                    'title': title[:20],
                })
        else:
            overflow.append(f'• {title}')

    text = (body_text or 'Escolha uma opção:').strip()
    if overflow:
        suffix = '\n'.join(overflow)
        text = f'{text}\n\n{suffix}' if text else suffix
    text = (text or 'Escolha uma opção:')[:640]
    return text, ig_buttons


def send_instagram_button_template(
    canal,
    recipient_igsid: str,
    text: str,
    msg_btns=None,
    msg_rows=None,
) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Template button — docs Instagram Login API.
    https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api
    """
    if not recipient_igsid:
        return False, None, 'Destinatário ausente'

    body, buttons = build_instagram_template_buttons(msg_btns, msg_rows, text)
    if not buttons:
        return send_instagram_text(canal, recipient_igsid, body)

    payload = {
        'recipient': {'id': str(recipient_igsid)},
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'button',
                    'text': body.replace('*', '').strip()[:640],
                    'buttons': buttons,
                },
            }
        },
    }
    logger.info('[InstagramSend] Enviando template button (%s botões)', len(buttons))
    return _post_messages(canal, payload)
