"""Download e utilitários de mídia para Instagram Messaging."""
import logging
import mimetypes
import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ATTACHMENT_EXT = {
    'image': '.jpg',
    'video': '.mp4',
    'audio': '.m4a',
    'file': '.pdf',
    'share': '.txt',
    'ig_reel': '.txt',
    'story_mention': '.txt',
    'template': '.txt',
}


def build_instagram_public_url(relative_url: str) -> str:
    """URL absoluta HTTPS para a Meta buscar mídia no envio."""
    if not relative_url:
        raise ValueError('URL de mídia ausente')
    if relative_url.startswith('http://') or relative_url.startswith('https://'):
        return relative_url
    backend = (getattr(settings, 'BACKEND_URL', None) or '').rstrip('/')
    if not backend:
        from integrations.meta_oauth import get_backend_url
        backend = get_backend_url().rstrip('/')
    if not backend:
        raise ValueError('URL do tenant não configurada (SUBDOMAIN/BACKEND_URL) — necessário para mídia Instagram')
    path = relative_url if relative_url.startswith('/') else f'/{relative_url}'
    return f'{backend}{path}'


def _guess_ext(content_type: str, attachment_type: str, url: str) -> str:
    mime = (content_type or '').split(';')[0].strip().lower()
    if mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            return guessed
    parsed = urlparse(url or '')
    _, ext = os.path.splitext(parsed.path)
    if ext and len(ext) <= 6:
        return ext
    return ATTACHMENT_EXT.get(attachment_type, '.bin')


def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w.\-]', '_', name)[:180]


def download_instagram_attachment(
    conversation_id: int,
    url: str,
    attachment_type: str,
    mid: Optional[str] = None,
) -> Tuple[Optional[str], Optional[dict]]:
    """Baixa mídia do CDN Instagram e salva em media/messages/<conversation_id>/."""
    if not url:
        return None, None

    try:
        response = requests.get(url, timeout=60)
        if not response.ok:
            logger.warning('[InstagramMedia] Download falhou HTTP %s url=%s', response.status_code, url[:120])
            return None, None

        content_type = response.headers.get('Content-Type', '')
        ext = _guess_ext(content_type, attachment_type, url)
        base = _safe_filename(f'ig_{mid or "media"}')
        filename = base if base.lower().endswith(ext) else f'{base}{ext}'

        media_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conversation_id))
        os.makedirs(media_dir, exist_ok=True)
        file_path = os.path.join(media_dir, filename)
        with open(file_path, 'wb') as handle:
            handle.write(response.content)

        local_url = f'/api/media/messages/{conversation_id}/{filename}/'.replace('\\', '/')
        meta = {
            'mime_type': content_type.split(';')[0].strip() if content_type else None,
            'file_size': len(response.content),
            'instagram_source_url': url,
            'local_file_url': local_url,
        }
        return local_url, meta
    except Exception as exc:
        logger.warning('[InstagramMedia] Erro ao baixar mídia: %s', exc)
        return None, None


def map_inbound_attachment_type(raw_type: str) -> str:
    """Normaliza tipo de anexo do webhook para message_type interno."""
    t = (raw_type or 'attachment').lower()
    mapping = {
        'image': 'image',
        'video': 'video',
        'audio': 'audio',
        'file': 'document',
        'share': 'share',
        'ig_reel': 'video',
        'story_mention': 'share',
        'like_heart': 'sticker',
        'template': 'template',
        'location': 'location',
        'fallback': 'attachment',
    }
    return mapping.get(t, t if t in ('image', 'video', 'audio', 'document', 'sticker') else 'attachment')


def find_ffmpeg_path() -> Optional[str]:
    import shutil
    import subprocess

    ffmpeg_path = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
    if not ffmpeg_path and os.name == 'nt':
        for path in (
            r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
        ):
            if os.path.exists(path):
                return path
    if not ffmpeg_path:
        try:
            test = subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            if test.returncode == 0:
                return 'ffmpeg'
        except Exception:
            pass
    return ffmpeg_path


def convert_audio_for_instagram(input_path: str, media_dir: str, base_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Instagram Login aceita áudio em wav/mp4/aac — na prática .m4a é rejeitado (2534080).
    Converte webm/ogg/etc. para .mp4 (AAC).
    Retorna (final_file_path, final_filename) ou (None, None) se falhar.
    """
    import subprocess

    ext = os.path.splitext(input_path)[1].lower()
    if ext in ('.wav', '.mp4', '.aac'):
        return input_path, os.path.basename(input_path)

    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        logger.error('[InstagramMedia] ffmpeg não encontrado para converter áudio')
        return None, None

    converted_filename = f'{base_name}.mp4'
    converted_path = os.path.join(media_dir, converted_filename)
    cmd = [
        ffmpeg_path, '-i', input_path,
        '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart',
        '-y', converted_path,
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode == 0 and os.path.exists(converted_path):
            logger.info('[InstagramMedia] Áudio convertido para %s', converted_filename)
            return converted_path, converted_filename
        logger.warning(
            '[InstagramMedia] Falha na conversão de áudio: %s',
            result.stderr.decode('utf-8', errors='ignore')[:300],
        )
    except Exception as exc:
        logger.warning('[InstagramMedia] Erro ao converter áudio: %s', exc)
    return None, None
