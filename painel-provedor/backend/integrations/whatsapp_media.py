"""Conversão e validação de áudio para WhatsApp (Cloud API e Uazapi)."""
import logging
import os
import subprocess
from typing import Optional, Tuple

from integrations.instagram_media import find_ffmpeg_path

logger = logging.getLogger(__name__)

WHATSAPP_AUDIO_EXTENSIONS = frozenset({'.mp3', '.ogg', '.aac', '.amr', '.m4a'})
VOICE_MEDIA_TYPES = frozenset({'ptt', 'myaudio'})

# Meta: "audio/ogg base não é compatível; somente codecs OPUS; somente mono".
# iOS rejeita voz com MIME sem codecs=opus e OGG com sample rate / timestamps ruins.
AUDIO_OGG_OPUS_MIME = 'audio/ogg; codecs=opus'


def is_whatsapp_voice_message(media_type: str) -> bool:
    """Somente gravações PTT/myaudio são mensagem de voz no WhatsApp."""
    return (media_type or '').lower() in VOICE_MEDIA_TYPES


def _validate_audio_output(path: str, min_bytes: int = 256) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size < min_bytes:
        logger.warning('[WhatsAppMedia] Arquivo de áudio muito pequeno (%s bytes): %s', size, path)
        return False
    return True


def convert_audio_for_whatsapp(
    input_path: str,
    media_dir: str,
    base_name: str,
    *,
    as_voice: bool,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Converte áudio para formato aceito pela Meta WhatsApp Cloud API.

    - PTT / mensagem de voz: OGG + codec OPUS mono (compatível com iOS)
    - Áudio comum: MP3

    Retorna (file_path, filename, mime_type) ou (None, None, None).
    """
    ext = os.path.splitext(input_path)[1].lower()

    # Mensagem de voz: sempre reencoda para OGG/OPUS iOS-safe (não confiar em .ogg
    # já existente — pode ser Vorbis, estereo, 48kHz com timestamps negativos, etc.).
    if not as_voice and ext == '.mp3':
        if _validate_audio_output(input_path):
            return input_path, os.path.basename(input_path), 'audio/mpeg'

    if ext in WHATSAPP_AUDIO_EXTENSIONS and not as_voice and ext != '.mp3':
        # .aac, .amr, .m4a já suportados — manter sem reconverter
        mime_map = {
            '.ogg': AUDIO_OGG_OPUS_MIME,
            '.aac': 'audio/aac',
            '.amr': 'audio/amr',
            '.m4a': 'audio/mp4',
        }
        if _validate_audio_output(input_path):
            return input_path, os.path.basename(input_path), mime_map.get(ext, 'audio/mpeg')

    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        logger.error('[WhatsAppMedia] ffmpeg não encontrado para converter áudio')
        return None, None, None

    if as_voice:
        # Evita sobrescrever o arquivo de entrada (ffmpeg não consegue ler+escrever no mesmo path).
        converted_filename = f'{base_name}_wa.ogg'
        converted_path = os.path.join(media_dir, converted_filename)
        # iOS WhatsApp: OPUS mono 16 kHz + timestamps zerados + MIME codecs=opus.
        # 48 kHz / metadata com time_start negativo → "Este áudio não está mais disponível".
        cmd = [
            ffmpeg_path,
            '-i', input_path,
            '-vn',
            '-af', 'asetpts=PTS-STARTPTS',
            '-c:a', 'libopus',
            '-b:a', '24k',
            '-ac', '1',
            '-ar', '16000',
            '-application', 'voip',
            '-frame_duration', '20',
            '-avoid_negative_ts', 'make_zero',
            '-f', 'ogg',
            '-y', converted_path,
        ]
        mime = AUDIO_OGG_OPUS_MIME
    else:
        converted_filename = f'{base_name}_wa.mp3' if ext == '.mp3' else f'{base_name}.mp3'
        converted_path = os.path.join(media_dir, converted_filename)
        cmd = [
            ffmpeg_path, '-i', input_path,
            '-vn',
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-ac', '1',
            '-y', converted_path,
        ]
        mime = 'audio/mpeg'

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode == 0 and _validate_audio_output(converted_path):
            logger.info(
                '[WhatsAppMedia] Áudio convertido para %s (voice=%s mime=%s)',
                converted_filename,
                as_voice,
                mime,
            )
            return converted_path, converted_filename, mime
        logger.warning(
            '[WhatsAppMedia] Falha na conversão de áudio: %s',
            result.stderr.decode('utf-8', errors='ignore')[:400],
        )
    except subprocess.TimeoutExpired:
        logger.error('[WhatsAppMedia] Timeout ao converter áudio')
    except Exception as exc:
        logger.warning('[WhatsAppMedia] Erro ao converter áudio: %s', exc)
    return None, None, None


def ensure_whatsapp_audio_format(
    file_path: str,
    filename: str,
    media_dir: str,
    media_type: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Garante que o áudio está em formato reproduzível no WhatsApp do cliente.
    Converte webm, wav e demais formatos não suportados.
    Mensagens de voz (ptt/myaudio) sempre passam por reencode OGG/OPUS iOS-safe.
    """
    ext = os.path.splitext(filename)[1].lower()
    as_voice = is_whatsapp_voice_message(media_type)
    base_name = os.path.splitext(filename)[0]

    # Voz: sempre normalizar via FFmpeg (mesmo se já for .ogg).
    if as_voice:
        return convert_audio_for_whatsapp(file_path, media_dir, base_name, as_voice=True)

    if ext in WHATSAPP_AUDIO_EXTENSIONS:
        if ext == '.ogg':
            # OGG genérico anexado como áudio comum — converter para MP3
            return convert_audio_for_whatsapp(file_path, media_dir, base_name, as_voice=False)
        mime_map = {
            '.mp3': 'audio/mpeg',
            '.aac': 'audio/aac',
            '.amr': 'audio/amr',
            '.m4a': 'audio/mp4',
        }
        if _validate_audio_output(file_path):
            return file_path, filename, mime_map.get(ext, 'audio/mpeg')

    return convert_audio_for_whatsapp(file_path, media_dir, base_name, as_voice=False)
