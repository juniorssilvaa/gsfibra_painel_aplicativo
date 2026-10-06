"""Criação de artes do Estúdio: dados do cadastro, geração da imagem e textos."""
from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from PIL import Image

from core.models import Plano
from marketing import composer, image_engine, mockup
from marketing.models import MarketingAsset

TEXT_MODES = ('sistema', 'ia')
MAX_REFERENCES = 4
DIRECTION_PREFIX = 'Direção de arte: '
NO_TEXT_RULE = (
    'REGRA ABSOLUTA: a imagem não pode conter nenhum texto. Nada de palavras, letras, números, slogans, títulos, '
    'placas, letreiros, marcas d\'água ou logotipos, em nenhum idioma. Os textos serão aplicados depois por outro sistema.'
)


class CreativeError(Exception):
    pass


def format_price(preco) -> str:
    try:
        value = Decimal(preco or 0)
    except (InvalidOperation, TypeError):
        return ''
    if value <= 0:
        return ''
    text = f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {text}/mês'


def format_speed(value) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return f'{text} MEGA' if text.isdigit() else text.upper()


def plan_texts(plano: Plano) -> Dict[str, str]:
    return {
        'titulo': plano.nome,
        'destaque': format_speed(plano.velocidade_download),
        'preco': format_price(plano.preco),
    }


def _asset(provedor, asset_id, kind: Optional[str] = None) -> Optional[MarketingAsset]:
    if not asset_id:
        return None
    qs = MarketingAsset.objects.filter(provedor=provedor, pk=asset_id)
    if kind:
        qs = qs.filter(kind=kind)
    item = qs.first()
    if not item:
        raise CreativeError(f'Imagem #{asset_id} não encontrada neste provedor.')
    return item


def _phone_area_prompt(formato: str, modo_texto: str) -> str:
    if mockup.side_layout(formato):
        area = 'Deixe a metade direita da imagem com fundo limpo, sem objetos, pessoas nem textos'
        texts = (
            'Deixe a metade esquerda com fundo simples e escuro, porque os textos serão aplicados ali.'
            if modo_texto == 'sistema' else 'Coloque todos os textos na metade esquerda.'
        )
    elif modo_texto == 'sistema':
        area = 'Deixe a parte central da imagem com fundo limpo, sem objetos, pessoas nem textos'
        texts = 'Deixe também o terço inferior com fundo simples e escuro para os textos.'
    else:
        area = 'Deixe livre a faixa entre 28% e 78% da altura, com fundo limpo, sem objetos, pessoas nem textos'
        texts = 'Coloque os textos acima e abaixo dessa faixa.'
    return (
        f'{area}: celulares com as telas reais do aplicativo serão inseridos ali depois. '
        f'Não desenhe celulares, smartphones nem telas de aplicativo. {texts}'
    )


def direction_from_prompt(prompt: str) -> str:
    for line in (prompt or '').splitlines():
        if line.startswith(DIRECTION_PREFIX):
            return line[len(DIRECTION_PREFIX):].strip()
    return ''


def build_prompt(descricao_visual: str, formato: str, modo_texto: str, textos: Dict[str, str], *,
                 has_base: bool, has_logo_ref: bool, has_style_refs: bool, has_telas: bool = False,
                 alteracoes: str = '') -> str:
    label = image_engine.FORMAT_LABELS[formato]
    no_text = modo_texto == 'sistema'
    if has_base:
        parts = [
            'Edite a primeira imagem enviada: é uma arte de anúncio já feita e aprovada pelo dono. Não crie uma arte nova.',
            f'Alterações pedidas: {(alteracoes or descricao_visual).strip()}',
            'Todo o resto deve continuar idêntico à primeira imagem: composição, enquadramento, fundo, cores, '
            'iluminação e elementos' + ('' if no_text else ', tipografia e textos') + ' que não foram citados nas alterações.',
            f'Formato {label}.',
        ]
        if no_text:
            parts.insert(1, NO_TEXT_RULE)
    elif no_text:
        parts = [
            f'Imagem de fundo para um anúncio de um provedor de internet, formato {label}.',
            NO_TEXT_RULE,
            f'{DIRECTION_PREFIX}{descricao_visual.strip()}',
        ]
    else:
        parts = [
            f'Arte publicitária profissional para anúncio de um provedor de internet, formato {label}.',
            f'{DIRECTION_PREFIX}{descricao_visual.strip()}',
        ]
    order = []
    if has_logo_ref:
        order.append('há uma imagem com o logotipo do provedor: inclua-o sem distorcer cores nem formas')
    if has_style_refs and has_base:
        order.append('as demais imagens são referências enviadas pelo dono só para guiar as alterações pedidas')
    elif has_style_refs:
        order.append(
            'as demais imagens são exemplos de estilo enviados pelo dono: siga layout, paleta, tipografia e clima, '
            'mas crie uma arte nova, sem copiar textos, preços, logotipos ou marcas que apareçam nelas'
        )
    if order:
        parts.append('Imagens enviadas: ' + '; '.join(order) + '.')
    if has_telas:
        parts.append(_phone_area_prompt(formato, modo_texto))
    if no_text and not has_telas:
        parts.append(
            'Deixe o terço inferior com fundo mais simples e escuro, sem elementos importantes, '
            'porque os textos serão aplicados depois.'
        )
    if no_text:
        parts.append('Lembrete final: a imagem deve sair com zero texto, zero letras e zero números.')
    else:
        lines = [textos[k] for k in ('titulo', 'destaque', 'preco', 'chamada', 'rodape') if textos.get(k)]
        if lines:
            quoted = '; '.join(f'"{line}"' for line in lines)
            parts.append(
                'Escreva na arte exatamente estes textos em português do Brasil, com grafia e números idênticos, '
                f'legíveis e com bom contraste: {quoted}. Não acrescente nenhum outro texto, preço ou número.'
            )
        else:
            parts.append('Não escreva preços nem números que não tenham sido informados.')
    return '\n'.join(parts)


def create_creative(
    *,
    provedor,
    thread,
    user,
    descricao_visual: str = '',
    formato: str = 'quadrado',
    modo_texto: str = 'sistema',
    plano_id=None,
    titulo: Optional[str] = None,
    destaque: Optional[str] = None,
    chamada: Optional[str] = None,
    rodape: Optional[str] = None,
    cor_destaque: Optional[str] = None,
    referencias: Optional[List[int]] = None,
    logo_id=None,
    arte_base_id=None,
    apenas_textos: bool = False,
    telas: Optional[List[int]] = None,
    alteracoes: Optional[str] = None,
) -> Tuple[MarketingAsset, Dict[str, str]]:
    """Em ajustes (arte_base_id), None herda da arte base; '' remove o texto, logo_id=0 remove a logo e
    telas=[] remove os celulares. alteracoes descreve só o que muda na imagem; o resto é preservado."""
    if modo_texto not in TEXT_MODES:
        raise CreativeError('modo_texto deve ser "sistema" ou "ia".')
    base = _asset(provedor, arte_base_id, 'creative')
    alteracoes = (alteracoes or '').strip()
    new_direction = (descricao_visual or '').strip()
    if base and not apenas_textos and not alteracoes and not new_direction:
        if base.base_image and formato in (base.formato, '', None):
            apenas_textos = True
        else:
            raise CreativeError(
                f'Para editar a imagem da arte #{base.id}, informe em alteracoes o que deve mudar, nas palavras do dono.'
            )
    if apenas_textos and base:
        formato = base.formato or formato
    if formato not in image_engine.FORMATS:
        raise CreativeError('formato deve ser quadrado, story ou paisagem.')

    inherited = dict(base.textos or {}) if base else {}
    direction = new_direction or inherited.get('descricao_visual') or (direction_from_prompt(base.prompt) if base else '')

    def pick(key, value):
        return inherited.get(key) if value is None else value

    informed = {
        'titulo': pick('titulo', titulo),
        'destaque': pick('destaque', destaque),
        'chamada': pick('chamada', chamada),
        'rodape': pick('rodape', rodape),
        'cor_destaque': pick('cor_destaque', cor_destaque),
        'descricao_visual': direction,
    }
    if plano_id is None and base:
        plano_id = base.plano_id

    plano = None
    if plano_id:
        plano = Plano.objects.filter(provedor=provedor, pk=plano_id, ativo=True).first()
        if not plano:
            raise CreativeError(f'Plano #{plano_id} não encontrado ou inativo neste provedor.')

    textos = {
        'titulo': informed['titulo'], 'destaque': informed['destaque'], 'preco': '',
        'chamada': informed['chamada'], 'rodape': informed['rodape'],
    }
    if plano:
        from_plan = plan_texts(plano)
        textos['titulo'] = informed['titulo'] or from_plan['titulo']
        textos['destaque'] = from_plan['destaque'] or informed['destaque']
        textos['preco'] = from_plan['preco']
    textos = {k: str(v or '').strip() for k, v in textos.items()}

    if logo_id is None:
        try:
            logo = _asset(provedor, inherited.get('logo_id'))
        except CreativeError:
            logo = None
    else:
        logo = _asset(provedor, logo_id)
    informed['logo_id'] = logo.id if logo else None
    cor_destaque = informed['cor_destaque']

    tela_ids = [int(t) for t in ((inherited.get('telas') or []) if telas is None else telas) if t]
    if len(tela_ids) > mockup.MAX_SCREENS:
        raise CreativeError(f'Use no máximo {mockup.MAX_SCREENS} telas por arte.')
    screens = [_asset(provedor, tid) for tid in tela_ids]
    informed['telas'] = tela_ids
    skip = set(tela_ids) | {informed['logo_id']}
    refs = [_asset(provedor, rid) for rid in (referencias or [])[:MAX_REFERENCES] if rid and rid not in skip]

    if apenas_textos:
        if not base or not base.base_image:
            raise CreativeError(
                'Só dá para reaplicar sem gerar imagem nova numa arte do modo sistema ou que já tenha telas do app.'
            )
        modo_texto = base.modo_texto or modo_texto
        art = Image.open(io.BytesIO(bytes(base.base_image))).convert('RGB')
        engine = base.engine
        prompt = base.prompt
    else:
        if not base and not direction:
            raise CreativeError('Informe a direção de arte (descricao_visual).')
        ref_bytes = []
        if base:
            ref_bytes.append(bytes(base.base_image or base.image))
        logo_as_ref = modo_texto == 'ia' and logo is not None
        if logo_as_ref:
            ref_bytes.append(bytes(logo.image))
        ref_bytes += [bytes(r.image) for r in refs]
        prompt = build_prompt(
            direction, formato, modo_texto, textos,
            has_base=base is not None, has_logo_ref=logo_as_ref, has_style_refs=bool(refs),
            has_telas=bool(screens), alteracoes=alteracoes or new_direction,
        )
        art, engine = image_engine.generate_image(
            provedor, prompt, formato, ref_bytes, quality='high' if modo_texto == 'ia' else 'medium',
            edit=base is not None,
        )

    screen_bytes = [bytes(s.image) for s in screens]
    if modo_texto == 'sistema':
        final = composer.compose(
            art, cor_destaque=cor_destaque, logo_bytes=bytes(logo.image) if logo else None,
            telas=screen_bytes, formato=formato, **textos,
        )
        base_bytes = image_engine.to_jpeg_bytes(art)
    elif screen_bytes:
        box = mockup.box_from_fractions(art.size, mockup.IA_PHONE_BOXES[formato])
        final = mockup.place_phones(art, screen_bytes, box).convert('RGB')
        base_bytes = image_engine.to_jpeg_bytes(art)
    else:
        final = art
        base_bytes = None

    asset = MarketingAsset.objects.create(
        provedor=provedor,
        thread=thread,
        kind='creative',
        image=image_engine.to_jpeg_bytes(final),
        base_image=base_bytes,
        mime_type='image/jpeg',
        width=final.width,
        height=final.height,
        formato=formato,
        modo_texto=modo_texto,
        prompt=prompt,
        textos=informed,
        plano=plano,
        parent=base,
        engine=engine,
        created_by=user,
    )
    return asset, textos
