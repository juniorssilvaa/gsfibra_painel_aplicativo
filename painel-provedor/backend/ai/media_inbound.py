"""
Áudio/imagem/vídeo/documento inbound → texto para a IA.

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
DOCUMENT_TYPES = frozenset({'document'})
MEDIA_AI_TYPES = AUDIO_TYPES | IMAGE_TYPES | VIDEO_TYPES | DOCUMENT_TYPES

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
    '.pdf': 'application/pdf',
}

# Sinais fortes de comprovante / pagamento (PT-BR + bancos comuns)
_PAYMENT_HINTS = (
    'comprovante',
    'pagamento',
    'pagseguro',
    'mercado pago',
    'mercadopago',
    'pix',
    'transferência',
    'transferencia',
    'ted',
    'doc ',
    'recibo',
    'pago',
    'boleto',
    'depósito',
    'deposito',
    'chave pix',
    'valor:',
    'valor r$',
    'r$ ',
    'nubank',
    'inter ',
    'itau',
    'itaú',
    'bradesco',
    'santander',
    'caixa econômica',
    'caixa economica',
    'banco do brasil',
    'sicoob',
    'sicredi',
    'c6 bank',
    'picpay',
    'stone',
    'asaas',
    'baixa',
)

COMPROVANTE_DIRECTIVE = (
    '[OBRIGATÓRIO — COMPROVANTE DE PAGAMENTO] '
    'Na PRIMEIRA resposta, chame APENAS transferir_conversa com equipe_nome=FINANCEIRO '
    '(ou o nome exato da equipe financeira nas regras do provedor). '
    'NÃO chame consultar_horario_atendimento nem outras tools antes da transferência. '
    'Não peça CPF, não faça perguntas e não espere confirmação. '
    'Na resposta ao cliente: NÃO diga que está transferindo para o FINANCEIRO/setor. '
    'Confirme de forma simples que o comprovante será encaminhado para ser '
    'ADICIONADO AO SISTEMA e realizar a BAIXA DO PAGAMENTO. '
    'Se o retorno da transferência indicar fora do horário, informe quando o atendimento '
    'humano retoma, sem citar o setor financeiro.'
)

COMPROVANTE_DIRECTIVE_NO_HOURS = (
    '[OBRIGATÓRIO — COMPROVANTE DE PAGAMENTO] '
    'Na PRIMEIRA resposta, chame APENAS transferir_conversa com equipe_nome=FINANCEIRO '
    '(ou o nome exato da equipe financeira nas regras do provedor). '
    'NÃO chame consultar_horario_atendimento nem outras tools antes da transferência. '
    'Não peça CPF, não faça perguntas e não espere confirmação. '
    'Na resposta ao cliente: NÃO diga que está transferindo para o FINANCEIRO/setor '
    'nem informe horário de atendimento, feriado ou próximo horário. '
    'Confirme de forma simples que o comprovante será encaminhado para ser '
    'ADICIONADO AO SISTEMA e realizar a BAIXA DO PAGAMENTO. '
    'Após "Obrigada!" (ou a frase do provedor na base de conhecimento), ENCERRAR a resposta. '
    'NÃO envie segunda mensagem com horário. NÃO use despedida/emoji extras além do que '
    'as regras do provedor pedirem para comprovante.'
)


def provider_informs_hours_after_comprovante(provedor) -> bool:
    """True se o provedor optou por informar horário após transferir comprovante."""
    return bool(getattr(provedor, 'ai_inform_hours_after_comprovante_transfer', False))


def comprovante_directive_for_provedor(provedor) -> str:
    if provider_informs_hours_after_comprovante(provedor):
        return COMPROVANTE_DIRECTIVE
    return COMPROVANTE_DIRECTIVE_NO_HOURS


UNREADABLE_DOC_DIRECTIVE = (
    '[OBRIGATÓRIO — DOCUMENTO ILEGÍVEL] '
    'Não foi possível ler ou interpretar o arquivo enviado. '
    'Se as regras do provedor pedirem transferência nesses casos, chame IMEDIATAMENTE '
    'transferir_conversa para FINANCEIRO. Na resposta ao cliente: NÃO anuncie a '
    'transferência para o setor; confirme de forma simples o encaminhamento para '
    'inclusão no sistema / tratamento do documento.'
)


def provider_kb_requires_comprovante_transfer(provedor) -> bool:
    """
    True se a base de conhecimento (dados_adicionais) do provedor pede
    transferir/encaminhar comprovante(s) para o financeiro.
    Sem essa regra, não forçamos transferência automática.
    """
    kb = (getattr(provedor, 'dados_adicionais', None) or '').strip().lower()
    if not kb:
        return False
    if 'comprovante' not in kb:
        return False
    if not any(x in kb for x in ('financeiro', 'financ', 'cobrança', 'cobranca', 'faturamento')):
        return False
    return any(
        x in kb
        for x in (
            'transfer',
            'encaminh',
            'imediat',
            'passar para',
            'enviar para',
            'direcion',
        )
    )


def looks_like_payment_receipt(text: str) -> bool:
    """Heurística leve: texto de visão/PDF/legenda parece comprovante de pagamento."""
    raw = (text or '').strip().lower()
    if not raw:
        return False
    hits = sum(1 for h in _PAYMENT_HINTS if h in raw)
    if 'comprovante' in raw and hits >= 1:
        return True
    if ('pix' in raw or 'transfer' in raw) and hits >= 2:
        return True
    return hits >= 3


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


def _extract_pdf_text(file_path: str, max_pages: int = 10) -> str:
    try:
        import pdfplumber

        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = (page.extract_text() or '').strip()
                if page_text:
                    parts.append(page_text)
        return '\n\n'.join(parts).strip()
    except Exception:
        logger.exception('[media_inbound] Falha ao extrair texto do PDF %s', file_path)
        return ''


def _append_directive(parts: list, extra: Dict[str, Any], directive: str, flag: str) -> None:
    parts.append(directive)
    extra[flag] = True
    extra['ai_mandatory_directive'] = directive


def enrich_inbound_media_for_ai(
    provedor,
    message_type: str,
    file_path: Optional[str],
    caption: str = '',
    file_name: str = '',
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Gera o texto que a IA deve receber + attrs extras (transcription / image_description).
    Não inventa conteúdo: se a transcrição/visão falhar, devolve só a legenda.

    Diretiva / transferência forçada de comprovante só ocorre se a base de
    conhecimento do provedor exigir (dados_adicionais).
    """
    mt = (message_type or '').strip().lower()
    caption_clean = (caption or '').strip()
    if caption_clean in ('[Mídia]', '[midia]', '[media]'):
        caption_clean = ''

    kb_force = provider_kb_requires_comprovante_transfer(provedor)
    extra: Dict[str, Any] = {
        'kb_requires_comprovante_transfer': kb_force,
    }
    parts = []
    if caption_clean:
        parts.append(caption_clean)

    name_hint = (file_name or '').strip()
    if name_hint and looks_like_payment_receipt(name_hint):
        parts.append(f'Nome do arquivo: {name_hint}')

    def _mark_receipt(reason: str = '') -> None:
        extra['payment_receipt_detected'] = True
        if reason:
            extra['payment_receipt_reason'] = reason
        if kb_force:
            _append_directive(
                parts,
                extra,
                comprovante_directive_for_provedor(provedor),
                'comprovante_kb_directive',
            )
            logger.info(
                '[media_inbound] Comprovante + regra KB → diretiva para a IA provedor=%s',
                getattr(provedor, 'id', None),
            )
        else:
            logger.info(
                '[media_inbound] Comprovante detectado, mas provedor=%s sem regra KB de transferência',
                getattr(provedor, 'id', None),
            )

    def _mark_unreadable() -> None:
        if kb_force:
            _append_directive(parts, extra, UNREADABLE_DOC_DIRECTIVE, 'comprovante_kb_directive')
            extra['unreadable_media'] = True
        else:
            extra['unreadable_media'] = True

    if not file_path:
        text = '\n'.join(parts) if parts else None
        if text and looks_like_payment_receipt(text):
            _mark_receipt('caption_or_name')
            text = '\n'.join(parts).strip()
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
            if looks_like_payment_receipt(description) or looks_like_payment_receipt(caption_clean):
                _mark_receipt('image_description')
        else:
            extra['image_description_error'] = True
            parts.append('Cliente enviou uma imagem, mas não foi possível interpretá-la.')
            blob = f'{caption_clean} {name_hint}'.strip()
            if looks_like_payment_receipt(blob):
                _mark_receipt('image_unreadable_hint')
    elif mt in DOCUMENT_TYPES:
        ext = os.path.splitext(file_path or '')[1].lower()
        is_pdf = ext == '.pdf' or (name_hint or '').lower().endswith('.pdf')
        parts.append(
            f'Cliente enviou um documento'
            + (f' ({name_hint})' if name_hint else '')
            + '.'
        )
        if is_pdf:
            pdf_text = _extract_pdf_text(file_path)
            if pdf_text:
                extra['pdf_text'] = pdf_text[:8000]
                extra['pdf_text_source'] = 'pdfplumber'
                summary = pdf_text[:2500]
                parts.append(f'Conteúdo extraído do PDF:\n{summary}')
                logger.info(
                    '[media_inbound] PDF ok provedor=%s chars=%s',
                    getattr(provedor, 'id', None),
                    len(pdf_text),
                )
                blob = f'{pdf_text} {caption_clean} {name_hint}'
                if looks_like_payment_receipt(blob):
                    _mark_receipt('pdf_text')
            else:
                extra['pdf_text_error'] = True
                parts.append('Não foi possível extrair texto legível do PDF.')
                blob = f'{caption_clean} {name_hint}'
                if looks_like_payment_receipt(blob):
                    _mark_receipt('pdf_unreadable_hint')
                else:
                    _mark_unreadable()
        else:
            blob = f'{caption_clean} {name_hint}'
            if looks_like_payment_receipt(blob):
                _mark_receipt('document_name')
            else:
                _mark_unreadable()

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
