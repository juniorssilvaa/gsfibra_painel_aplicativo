"""
Persistência e leitura de imagens da galeria do provedor (chatbot).

Os arquivos em MEDIA_ROOT podem sumir após deploy/restart do container;
o conteúdo em arquivo_db (PostgreSQL) permanece e é a fonte principal.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from typing import Callable, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

BytesAndMime = Tuple[Optional[bytes], Optional[str]]


def get_provider_gallery_bytes(img) -> BytesAndMime:
    """Retorna (bytes, mime_type) ou (None, None) se indisponível."""
    if img is None:
        return None, None

    raw = img.arquivo_db
    if raw:
        data = bytes(raw) if not isinstance(raw, (bytes, bytearray)) else raw
        if data:
            mime = (img.mime_type or '').strip() or 'image/png'
            return data, mime

    try:
        if img.imagem and img.imagem.name:
            with img.imagem.open('rb') as f:
                data = f.read()
            if data:
                mime = mimetypes.guess_type(img.imagem.name)[0] or 'image/png'
                img.arquivo_db = data
                img.mime_type = mime
                img.save(update_fields=['arquivo_db', 'mime_type', 'updated_at'])
                logger.info(
                    '[ProviderGallery] Backfill arquivo_db id=%s (%s bytes)',
                    img.id,
                    len(data),
                )
                return data, mime
    except Exception as exc:
        logger.warning('[ProviderGallery] Falha ao ler disco id=%s: %s', img.id, exc)

    return None, None


def persist_gallery_image_bytes(instance) -> bool:
    """Grava bytes da ImageField em arquivo_db (chamar após upload)."""
    if not instance or not instance.imagem:
        return False
    try:
        with instance.imagem.open('rb') as f:
            data = f.read()
        if not data:
            logger.warning('[ProviderGallery] Upload vazio id=%s', getattr(instance, 'id', '?'))
            return False
        mime = mimetypes.guess_type(instance.imagem.name)[0] or 'image/png'
        instance.arquivo_db = data
        instance.mime_type = mime
        instance.save(update_fields=['arquivo_db', 'mime_type', 'updated_at'])
        logger.info(
            "[ProviderGallery] Persistido no banco '%s' id=%s (%s bytes)",
            instance.nome,
            instance.id,
            len(data),
        )
        return True
    except Exception as exc:
        logger.error(
            '[ProviderGallery] Erro ao persistir bytes id=%s: %s',
            getattr(instance, 'id', '?'),
            exc,
            exc_info=True,
        )
        return False


def gallery_image_temp_file(img) -> Tuple[Optional[str], Optional[Callable[[], None]]]:
    """
    Caminho temporário legível para envio WhatsApp (Cloud API exige arquivo local).
    Retorna (path, cleanup) ou (None, None).
    """
    data, mime = get_provider_gallery_bytes(img)
    if not data:
        return None, None

    ext = mimetypes.guess_extension(mime or 'image/png') or '.png'
    fd, path = tempfile.mkstemp(suffix=ext, prefix=f'gallery_{img.id}_')
    try:
        os.write(fd, data)
    finally:
        os.close(fd)

    def _cleanup():
        try:
            os.unlink(path)
        except OSError:
            pass

    return path, _cleanup


def copy_gallery_bytes_to_conversation_media(conv, gallery_image) -> str:
    """Copia bytes da galeria para media/messages/<conv_id>/ (painel)."""
    fallback = f'/api/media/provider-gallery/{gallery_image.id}/'
    data, _mime = get_provider_gallery_bytes(gallery_image)
    if not data:
        return fallback

    raw_name = os.path.basename(gallery_image.imagem.name if gallery_image.imagem else 'image.jpg')
    safe_name = raw_name.replace('/', '_').replace('\\', '_') or 'image.jpg'
    dest_name = f'gallery_{gallery_image.id}_{safe_name}'
    dest_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conv.id))
    dest_path = os.path.join(dest_dir, dest_name)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, 'wb') as out:
            out.write(data)
    except Exception as exc:
        logger.warning(
            '[ProviderGallery] Falha ao copiar para conversa %s: %s',
            conv.id,
            exc,
        )
        return fallback
    return f'/api/media/messages/{conv.id}/{dest_name}'
