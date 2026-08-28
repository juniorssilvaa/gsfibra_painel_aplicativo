"""
Áudio/imagem/vídeo inbound → texto para a IA.

Usa a mesma chave de Integrações → Agente de IA (openai_api_key / ai_api_key).
OpenAI: Whisper (whisper-1). Gemini: generate_content com o arquivo.
"""
from __future__ import annotations

import logging
import mimetypes
import os
from typing import Any, Dict, Optional, Tuple

from django.conf import settings

from ai.providers.config import (
    get_provedor_ai_model,
    get_provedor_ai_provider,
    get_provedor_openai_api_key,
)

logger = logging.getLogger(__name__)

AUDIO_TYPES = frozenset({'audio', 'ptt', 'voice', 'myaudio'})
IMAGE_TYPES = frozenset({'image'})
VIDEO_TYPES = frozenset({'video'})
MEDIA_AI_TYPES = AUDIO_TYPES | IMAGE_TYPES | VIDEO_TYPES

_MIME_BY_EXT = {
    '.ogg': 'audio/ogg',
    '.oga': 'audio/ogg',
    '.opus': 'audio/ogg',
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


def resolve_media_file_path(file_url: Optional[str], conversation_id: Optional[int] = None) -> Optional[str]:
    """Converte file_url do chat (/api/media/messages/<id>/<file>/) em caminho local."""
    if not file_url:
        return None
    raw = str(file_url).strip()
    if os.path.isfile(raw):
        return raw

    parts = [p for p in raw.replace('\\', '/').strip('/').split('/') if p]
    try:
        idx = parts.index('messages')
        conv = parts[idx + 1]
        name = parts[idx + 2]
    except (ValueError, IndexError):
        if conversation_id and parts:
            conv = str(conversation_id)
            name = parts[-1]
        else:
            return None

    path = os.path.join(str(settings.MEDIA_ROOT), 'messages', str(conv), name)
    if os.path.isfile(path):
        return path
    return None


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path or '')[1].lower()
    if ext in _MIME_BY_EXT:
        return _MIME_BY_EXT[ext]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or 'application/octet-stream'


def transcribe_audio_file(provedor, file_path: str) -> Optional[str]:
    """Transcreve áudio/vídeo com a chave da IA do provedor. Retorna só o texto falado."""
    if not file_path or not os.path.isfile(file_path):
        return None
    key = get_provedor_openai_api_key(provedor)
    if not key:
        logger.warning(
            '[media_inbound] Sem chave de IA no provedor %s — não transcreve.',
            getattr(provedor, 'id', None),
        )
        return None

    provider = get_provedor_ai_provider(provedor)
    try:
        if provider == 'openai':
            return _transcribe_openai(key, file_path)
        if provider == 'gemini':
            return _transcribe_gemini(key, get_provedor_ai_model(provedor), file_path)
        logger.warning(
            '[media_inbound] Provedor de IA %s não transcreve áudio (só OpenAI/Gemini).',
            provider,
        )
        return None
    except Exception:
        logger.exception('[media_inbound] Falha ao transcrever %s', file_path)
        return None


def describe_image_file(provedor, file_path: str) -> Optional[str]:
    """Descreve a imagem com o mesmo modelo/chave da IA (visão)."""
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        from ai.service import openai_service

        result = openai_service.analyze_image_with_ai(file_path, provedor)
        if result.get('success'):
            text = (result.get('resposta') or '').strip()
            return text or None
        logger.warning('[media_inbound] Visão falhou: %s', result.get('erro'))
        return None
    except Exception:
        logger.exception('[media_inbound] Falha ao analisar imagem %s', file_path)
        return None


def enrich_inbound_media_for_ai(
    provedor,
    message_type: str,
    file_path: Optional[str],
    caption: str = '',
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Gera o texto que a IA deve receber + attrs extras (transcription / image_description).
    Não inventa conteúdo: se a transcrição/visão falhar, devolve só a legenda.
    """
    mt = (message_type or '').strip().lower()
    caption_clean = (caption or '').strip()
    if caption_clean in ('[Mídia]', '[midia]', '[media]'):
        caption_clean = ''

    extra: Dict[str, Any] = {}
    parts = []
    if caption_clean:
        parts.append(caption_clean)

    if not file_path:
        text = '\n'.join(parts) if parts else None
        return text, extra

    if mt in AUDIO_TYPES or mt in VIDEO_TYPES:
        kind = 'vídeo' if mt in VIDEO_TYPES else 'áudio'
        transcribed = transcribe_audio_file(provedor, file_path)
        if transcribed:
            extra['transcription'] = transcribed
            extra['transcription_source'] = 'provider_ai_key'
            parts.append(f'Transcrição do {kind} enviado pelo cliente: {transcribed}')
            logger.info(
                '[media_inbound] Transcrição ok provedor=%s tipo=%s chars=%s',
                getattr(provedor, 'id', None),
                mt,
                len(transcribed),
            )
        else:
            extra['transcription_error'] = True
    elif mt in IMAGE_TYPES:
        description = describe_image_file(provedor, file_path)
        if description:
            extra['image_description'] = description
            extra['image_description_source'] = 'provider_ai_key'
            parts.append(f'Cliente enviou uma imagem. Descrição: {description}')
            logger.info(
                '[media_inbound] Visão ok provedor=%s chars=%s',
                getattr(provedor, 'id', None),
                len(description),
            )
        else:
            extra['image_description_error'] = True

    text = '\n'.join(parts).strip() if parts else None
    return text, extra


def _transcribe_openai(api_key: str, file_path: str) -> Optional[str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with open(file_path, 'rb') as handle:
        result = client.audio.transcriptions.create(
            model='whisper-1',
            file=handle,
            language='pt',
        )
    text = (getattr(result, 'text', None) or '').strip()
    return text or None


def _transcribe_gemini(api_key: str, model: str, file_path: str) -> Optional[str]:
    from google import genai
    from google.genai import types

    with open(file_path, 'rb') as handle:
        data = handle.read()
    if not data:
        return None

    mime = _guess_mime(file_path)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model or 'gemini-2.0-flash',
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime),
            'Transcreva fielmente o áudio em português do Brasil. '
            'Responda apenas com o texto falado, sem comentários nem aspas.',
        ],
    )
    text = (getattr(response, 'text', None) or '').strip()
    return text or None
