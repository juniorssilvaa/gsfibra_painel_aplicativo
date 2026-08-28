"""Perfil de clientes Instagram (IGSID) via User Profile API."""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_IG_VERSION = 'v21.0'
PROFILE_FIELDS = 'name,username,profile_pic'
# Django URLField default — URLs da Meta frequentemente excedem 200 chars
CONTACT_AVATAR_MAX_LEN = 200


def fetch_instagram_customer_profile(access_token: str, igsid: str) -> dict:
    """
    Busca nome/username do cliente que enviou DM.

    Docs: https://developers.facebook.com/docs/messenger-platform/instagram/features/user-profile/
    Requer que o cliente já tenha interagido (ex.: enviado mensagem).
    """
    if not access_token or not igsid:
        return {}

    urls = (
        f'https://graph.instagram.com/{GRAPH_IG_VERSION}/{igsid}',
        f'https://graph.facebook.com/{GRAPH_IG_VERSION}/{igsid}',
    )

    for url in urls:
        try:
            response = requests.get(
                url,
                params={'fields': PROFILE_FIELDS, 'access_token': access_token},
                timeout=15,
            )
            if response.ok:
                data = response.json()
                if isinstance(data, dict) and not data.get('error'):
                    return data
            logger.debug(
                '[InstagramProfile] Falha %s status=%s body=%s',
                url,
                response.status_code,
                (response.text or '')[:300],
            )
        except Exception as exc:
            logger.debug('[InstagramProfile] Erro em %s: %s', url, exc)

    return {}


def build_instagram_contact_display_name(profile: dict, sender_id: str) -> str:
    name = (profile.get('name') or '').strip()
    username = (profile.get('username') or '').strip()

    if name and username:
        return f'{name} (@{username})'
    if name:
        return name
    if username:
        return f'@{username}'
    return f'Instagram {sender_id}'


def enrich_instagram_contact(contact, canal, sender_id: str) -> None:
    """Atualiza contato com nome, @username e foto quando disponível."""
    extras = dict(contact.additional_attributes or {})
    sender_id = str(sender_id)

    needs_profile = (
        not extras.get('instagram_username')
        or not contact.name
        or contact.name == sender_id
        or contact.name.startswith('Instagram ')
    )
    if not needs_profile:
        return

    if not canal or not canal.token:
        return

    profile = fetch_instagram_customer_profile(canal.token, sender_id)
    if not profile:
        return

    username = (profile.get('username') or '').strip()
    profile_pic = profile.get('profile_pic') or profile.get('profile_picture_url')

    contact.name = build_instagram_contact_display_name(profile, sender_id)

    if username:
        extras['instagram_username'] = username
    extras['instagram_scoped_id'] = sender_id

    update_fields = ['name', 'additional_attributes', 'updated_at']
    contact.additional_attributes = extras

    if profile_pic:
        profile_pic = str(profile_pic).strip()
        if len(profile_pic) <= CONTACT_AVATAR_MAX_LEN:
            contact.avatar = profile_pic
            update_fields.append('avatar')
        else:
            extras['instagram_profile_pic'] = profile_pic
            contact.additional_attributes = extras

    try:
        contact.save(update_fields=update_fields)
    except Exception as exc:
        logger.warning(
            '[InstagramProfile] Falha ao salvar contato %s (avatar/name): %s',
            contact.id,
            exc,
        )
        if 'avatar' in update_fields:
            contact.avatar = None
            extras.pop('instagram_profile_pic', None)
            contact.additional_attributes = extras
            safe_fields = [f for f in update_fields if f != 'avatar']
            try:
                contact.save(update_fields=safe_fields)
            except Exception:
                logger.exception(
                    '[InstagramProfile] Falha ao salvar contato %s após remover avatar',
                    contact.id,
                )
                return
        else:
            return

    logger.info(
        '[InstagramProfile] Contato %s atualizado: name=%s username=%s',
        contact.id,
        contact.name,
        username or '-',
    )
