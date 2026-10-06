"""Geração de imagem com a chave do provedor (OpenAI gpt-image-1 ou Gemini) e ajuste aos formatos de anúncio."""
from __future__ import annotations

import base64
import io
from typing import Dict, List, Optional, Tuple

from PIL import Image

from ai.providers.config import get_provedor_ai_provider, get_provedor_openai_api_key

FORMATS: Dict[str, Tuple[int, int]] = {
    'quadrado': (1080, 1080),
    'story': (1080, 1920),
    'paisagem': (1200, 628),
}
FORMAT_LABELS = {
    'quadrado': 'quadrado 1:1 (feed)',
    'story': 'vertical 9:16 (stories e reels)',
    'paisagem': 'horizontal 1,91:1 (feed paisagem)',
}
IMAGE_PROVIDERS = ('openai', 'gemini')
OPENAI_IMAGE_MODEL = 'gpt-image-1'
GEMINI_IMAGE_MODEL = 'gemini-2.5-flash-image'
_OPENAI_SIZES = {'quadrado': '1024x1024', 'story': '1024x1536', 'paisagem': '1536x1024'}
_GEMINI_RATIOS = {'quadrado': '1:1', 'story': '9:16', 'paisagem': '16:9'}
IMAGE_TIMEOUT_SECONDS = 240
OPENAI_VISION_MODEL = 'gpt-4o-mini'
GEMINI_VISION_MODEL = 'gemini-2.5-flash'
VISION_TIMEOUT_SECONDS = 60
DESCRIBE_PROMPT = (
    'Esta imagem foi enviada pelo dono de um provedor de internet como referência para criar artes de anúncio. '
    'Descreva em português, em até 120 palavras, o que um diretor de arte precisa saber para criar algo no mesmo estilo: '
    'tipo de imagem (logotipo, anúncio pronto, foto, print de tela), layout e composição, cores principais com '
    'hex aproximado, tipografia, elementos visuais, clima, e os textos visíveis transcritos entre aspas. '
    'Responda só com a descrição, sem introdução.'
)
COMPETITOR_PROMPT = (
    'Esta é uma postagem do Instagram de um concorrente (provedor de internet). Em até 110 palavras, em português, '
    'descreva para um analista de marketing: oferta ou mensagem principal, gancho do título, textos visíveis entre '
    'aspas (preços e velocidades exatamente como aparecem), layout, cores principais com hex aproximado, uso de '
    'pessoas ou produtos, e a chamada para ação. Responda só com a descrição, sem introdução.'
)

ENGINE_MISSING_MSG = (
    'Nenhuma chave capaz de gerar imagens. O agente de IA do provedor usa um modelo sem geração de imagem: '
    'cadastre uma chave OpenAI ou Gemini para imagens no Estúdio de Marketing.'
)


KEY_REJECTED_MSG = 'A chave da {provider} foi recusada (inválida, revogada ou sem saldo). {where}'
_KEY_LOCATION = {
    'principal': 'Confira a chave em Integrações > Agente de IA.',
    'extra': 'Troque em "Trocar chave de imagem" no topo do Estúdio de Marketing.',
}
OPENAI_ORG_VERIFY_MSG = (
    'A OpenAI exige verificar a organização para usar o gpt-image-1. Verifique em '
    'platform.openai.com/settings/organization/general e tente de novo em alguns minutos.'
)
_KEY_PREFIXES = {'openai': ('sk-',), 'gemini': ('AIza',)}
_PROVIDER_NAMES = {'openai': 'OpenAI', 'gemini': 'Gemini'}


class ImageEngineUnavailable(Exception):
    pass


def is_auth_error(exc: Exception) -> bool:
    status_code = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    if status_code in (401, 403) and 'organization' not in str(exc).lower():
        return True
    text = str(exc)
    return 'invalid_api_key' in text or 'API key not valid' in text or 'API_KEY_INVALID' in text


def friendly_error(exc: Exception, provider: str = '', source: str = 'principal') -> str:
    text = str(exc)
    if 'organization' in text.lower() and 'verif' in text.lower():
        return OPENAI_ORG_VERIFY_MSG
    if is_auth_error(exc):
        return KEY_REJECTED_MSG.format(
            provider=_PROVIDER_NAMES.get(provider, 'API'), where=_KEY_LOCATION.get(source, _KEY_LOCATION['principal'])
        )
    return f'Falha no serviço de imagem: {text[:300]}'


def validate_api_key(provider: str, api_key: str) -> None:
    """Confere formato e testa a chave numa chamada gratuita. Levanta ValueError com mensagem para o dono."""
    name = _PROVIDER_NAMES[provider]
    if not api_key or any(ch.isspace() for ch in api_key) or not api_key.startswith(_KEY_PREFIXES[provider]):
        prefix = ' ou '.join(f'"{p}"' for p in _KEY_PREFIXES[provider])
        raise ValueError(f'Isso não parece uma chave {name}: ela deve começar com {prefix} e não ter espaços.')
    try:
        if provider == 'gemini':
            from google import genai

            genai.Client(api_key=api_key).models.get(model=GEMINI_IMAGE_MODEL)
        else:
            from openai import OpenAI

            OpenAI(api_key=api_key, timeout=VISION_TIMEOUT_SECONDS).models.list()
    except Exception as exc:
        if is_auth_error(exc):
            raise ValueError(f'A {name} recusou essa chave. Confira se copiou a chave inteira e se ela está ativa.')
        raise ValueError(f'Não foi possível validar a chave na {name}: {str(exc)[:200]}')


def resolve_image_engine(provedor) -> Tuple[str, str, str]:
    """(provider, api_key, origem). Usa a chave do agente de IA (Integrações); a chave extra só entra quando o
    agente usa um provedor sem geração de imagem (DeepSeek) ou está sem chave."""
    main = get_provedor_ai_provider(provedor)
    main_key = get_provedor_openai_api_key(provedor)
    if main in IMAGE_PROVIDERS and main_key:
        return main, main_key, 'principal'
    ext = provedor.integracoes_externas or {}
    extra_provider = (ext.get('image_provider') or '').strip().lower()
    extra_key = (ext.get('image_api_key') or '').strip()
    if extra_key and extra_provider in IMAGE_PROVIDERS:
        return extra_provider, extra_key, 'extra'
    raise ImageEngineUnavailable(ENGINE_MISSING_MSG)


def agent_key_supports_images(provedor) -> bool:
    return get_provedor_ai_provider(provedor) in IMAGE_PROVIDERS and bool(get_provedor_openai_api_key(provedor))


def image_engine_status(provedor) -> Dict[str, object]:
    ext = provedor.integracoes_externas or {}
    status = {
        'ai_provider': get_provedor_ai_provider(provedor),
        'extra_provider': (ext.get('image_provider') or '').strip().lower() or None,
        'has_extra_key': bool((ext.get('image_api_key') or '').strip()),
        'agent_key_supports_images': agent_key_supports_images(provedor),
    }
    try:
        provider, _, origem = resolve_image_engine(provedor)
        status.update({'available': True, 'provider': provider, 'source': origem})
    except ImageEngineUnavailable as exc:
        status.update({'available': False, 'provider': None, 'source': None, 'message': str(exc)})
    return status


def fit_to_format(raw: bytes, formato: str) -> Image.Image:
    """Recorta no centro para a proporção do formato e redimensiona ao tamanho do anúncio."""
    target_w, target_h = FORMATS[formato]
    img = Image.open(io.BytesIO(raw)).convert('RGB')
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    if src_w / src_h > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)


def _generate_openai(api_key: str, prompt: str, formato: str, references: List[bytes], quality: str,
                     edit: bool = False) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=IMAGE_TIMEOUT_SECONDS)
    common = {'model': OPENAI_IMAGE_MODEL, 'prompt': prompt, 'size': _OPENAI_SIZES[formato], 'quality': quality}
    if references:
        files = [(f'referencia_{i}.png', data, 'image/png') for i, data in enumerate(references, start=1)]
        extra = {'input_fidelity': 'high'} if edit else {}
        resp = client.images.edit(image=files, **common, **extra)
    else:
        resp = client.images.generate(**common)
    return base64.b64decode(resp.data[0].b64_json)


def _generate_gemini(api_key: str, prompt: str, formato: str, references: List[bytes]) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    parts = [types.Part.from_bytes(data=data, mime_type='image/png') for data in references]
    parts.append(types.Part.from_text(text=prompt))
    resp = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=[types.Content(role='user', parts=parts)],
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE'],
            image_config=types.ImageConfig(aspect_ratio=_GEMINI_RATIOS[formato]),
        ),
    )
    for candidate in getattr(resp, 'candidates', None) or []:
        for part in getattr(getattr(candidate, 'content', None), 'parts', None) or []:
            inline = getattr(part, 'inline_data', None)
            if inline and getattr(inline, 'data', None):
                return inline.data
    raise RuntimeError('O Gemini não retornou imagem (pode ter recusado o pedido pela política de conteúdo).')


def reference_png(data: bytes, max_side: int = 1536) -> bytes:
    img = Image.open(io.BytesIO(data))
    img = img.convert('RGBA') if img.mode in ('RGBA', 'LA', 'P') else img.convert('RGB')
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    return to_png_bytes(img)


def describe_image(provedor, data: bytes, prompt: str = DESCRIBE_PROMPT) -> str:
    provider, api_key, _ = resolve_image_engine(provedor)
    png = reference_png(data, max_side=1024)
    if provider == 'gemini':
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[types.Part.from_bytes(data=png, mime_type='image/png'), prompt],
        )
        return (getattr(resp, 'text', None) or '').strip()

    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=VISION_TIMEOUT_SECONDS)
    b64 = base64.b64encode(png).decode('ascii')
    resp = client.chat.completions.create(
        model=OPENAI_VISION_MODEL,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
            ],
        }],
        max_tokens=400,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or '').strip()


def generate_image(provedor, prompt: str, formato: str, references: Optional[List[bytes]] = None,
                   quality: str = 'medium', edit: bool = False) -> Tuple[Image.Image, str]:
    """edit=True: a primeira referência é a arte a ser editada e deve ser preservada ao máximo."""
    provider, api_key, _ = resolve_image_engine(provedor)
    refs = [reference_png(data) for data in (references or [])]
    if provider == 'gemini':
        raw = _generate_gemini(api_key, prompt, formato, refs)
        label = f'gemini:{GEMINI_IMAGE_MODEL}'
    else:
        raw = _generate_openai(api_key, prompt, formato, refs, quality, edit=edit)
        label = f'openai:{OPENAI_IMAGE_MODEL}'
    return fit_to_format(raw, formato), label


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def to_jpeg_bytes(img: Image.Image, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()
