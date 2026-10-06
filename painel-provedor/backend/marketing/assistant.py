"""IA de marketing do Estúdio: conversa com o dono do provedor, cria artes e analisa anúncios."""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import timedelta
from typing import Any, Dict, List

from django.db import close_old_connections, transaction
from django.utils import timezone

from marketing import image_engine
from marketing.models import MarketingAsset, MarketingMessage

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
HISTORY_LIMIT = 40
MAX_DESCRIBE_PER_TURN = 4
MAX_INSTAGRAM_IMAGES = 6
_ANNOTATION_RE = re.compile(r'\n*\[(?:Outras )?Artes? criadas?:[^\]]*\]', re.IGNORECASE)
PENDING_TIMEOUT = timedelta(minutes=10)

SYSTEM_PROMPT = """Você é a IA de marketing do provedor de internet {provedor}. Você conversa com o dono ou gestor do provedor (nunca com clientes finais) no Estúdio de Marketing.

O que você faz:
- Cria e ajusta artes para anúncios do Facebook e Instagram com a tool gerar_arte, seguindo a direção de arte que o dono pedir.
- Escreve textos de anúncio (texto principal, título, descrição, chamada) quando ele pedir.
- Analisa as entradas de clientes por anúncio com a tool relatorio_anuncios e sugere melhorias baseadas nesses números.
- Analisa perfis de concorrentes no Instagram com a tool analisar_instagram quando o dono pedir (usuário ou link): compare engajamento (curtidas e comentários por post), ofertas e preços divulgados, ganchos, estilo visual, formatos e frequência; aponte o que funciona melhor para eles e proponha como o provedor pode fazer melhor com a identidade dele. Baseie-se só nos dados retornados e nunca copie textos, preços ou marca do concorrente. Se a tool retornar erro, explique e sugira colar prints das postagens.

Regras:
- Planos, velocidades, preços, taxas e condições só podem vir da tool consultar_planos_e_dados ou do que o dono escrever. Nunca invente números, promoções nem condições.
- Modo de texto da arte: "sistema" (a IA de imagem desenha só a arte e o sistema escreve por cima os textos exatos; preço e velocidade nunca saem errados) ou "ia" (a IA de imagem desenha tudo, inclusive os textos; pode errar letras ou números e o dono precisa revisar). Se o dono ainda não escolheu nesta conversa, explique as duas opções em poucas palavras e pergunte antes de gerar. Depois da escolha, mantenha-a até ele mudar.
- Formatos: quadrado (feed), story (9:16) e paisagem. Se ele não disser, pergunte junto com o modo; se disser que tanto faz, use quadrado.
- Ajustar é editar a arte existente, não criar outra. Quando o dono pedir mudança numa arte existente (citando o número ou falando da última arte), chame gerar_arte com arte_base_id e escreva em alteracoes só o que muda, nas palavras dele (ex.: "trocar o fundo para azul", "colocar as telas nos celulares"). Não envie descricao_visual em ajustes: a direção de arte original é mantida e a IA de imagem preserva todo o resto. Mantenha formato e modo da arte base, salvo pedido contrário.
- Se a mudança for só em textos, cor do preço, logo ou telas de uma arte que permite (modo sistema ou arte que já tem telas), use apenas_textos=true: não gera imagem nova e não tem custo de geração.
- Textos da arte (título, destaque, chamada, rodapé) sempre vão nos campos titulo, destaque, chamada e rodape, nunca dentro de alteracoes ou descricao_visual; no modo sistema, só esses campos aparecem escritos na arte.
- Nunca peça ao dono nomes de campos internos (descricao_visual, alteracoes, arte_base_id, modo_texto). Se faltar informação, pergunte em linguagem simples.
- Imagens anexadas ou coladas (prints) pelo dono aparecem no histórico como #id, com uma descrição do que a imagem mostra. Use essas descrições para entender o que ele quer: logotipo vai em logo_id; artes de exemplo vão em referencias e guiam a descricao_visual; prints de telas do app que devem aparecer na arte vão em telas. Se não estiver claro qual é o papel da imagem, pergunte.
- telas (até 3): o sistema coloca os prints exatamente como são dentro de celulares desenhados na arte (quadrado e paisagem: celulares à direita e textos à esquerda; story: celulares no meio). A IA de imagem só cria o fundo, então descreva na descricao_visual apenas o cenário e o clima, sem celulares. Sempre que o dono quiser mostrar o app ou telas reais, use telas, nunca referencias. Para trocar só as telas de uma arte que já tem telas, use arte_base_id + telas + apenas_textos=true.
- Exemplos podem ser anúncios de outras empresas: aproveite layout, cores e clima, mas nunca copie textos, preços, nomes ou marcas deles.
- Em artes novas, descricao_visual é uma direção de arte detalhada: cena, estilo, cores, iluminação e composição, fiel ao pedido do dono, e sempre com o tema do anúncio (ex.: aplicativo do provedor no celular, Wi-Fi em casa, fibra óptica, família conectada). No modo sistema, descreva só a cena e o fundo: não mencione textos, títulos, tipografia nem legibilidade, porque os textos são aplicados pelo sistema e a IA de imagem não pode escrever nada.
- Quando já souber o que fazer (formato e modo definidos, pedido claro), chame gerar_arte nesta mesma resposta. Nunca responda "aguarde", "vou preparar" ou "já volto": você só trabalha enquanto responde, e o dono só recebe a arte se a tool for chamada agora.
- Só diga que criou ou ajustou uma arte se gerar_arte retornou ok nesta resposta, e cite o arte_id retornado. Imagens enviadas pelo dono não são artes criadas por você.
- Depois de gerar, diga em poucas linhas o que foi feito e pergunte se ele quer ajustes. Não repita perguntas já respondidas.
- Se uma tool retornar erro, explique ao dono exatamente o erro retornado; não finja que a arte foi criada e não invente erros.
- Em análises, entregue conclusões e recomendações práticas (o que funciona, por quê, o que fazer), não uma lista crua dos dados.
- Responda em português do Brasil, de forma direta, em texto simples: o chat não formata markdown, então não use **, #, tabelas nem links em colchetes; use listas com hífen quando ajudar."""

TOOLS: List[Dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'consultar_planos_e_dados',
            'description': 'Lista os planos ativos (id, nome, velocidades, preço, descrição) e os dados comerciais do provedor.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'gerar_arte',
            'description': (
                'Cria uma arte de anúncio (ou uma nova versão de uma arte existente). Com plano_id, o preço e a '
                'velocidade vêm do cadastro do plano. Leva de 20 a 60 segundos. Em ajustes (arte_base_id), campos '
                'omitidos são mantidos da arte base: envie só o que muda, "" para remover um texto, logo_id=0 '
                'para remover a logo e telas=[] para remover os celulares.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'descricao_visual': {'type': 'string', 'description': 'Direção de arte detalhada para uma arte NOVA. Em ajustes (arte_base_id), não envie: use alteracoes.'},
                    'alteracoes': {'type': 'string', 'description': 'Em ajustes (arte_base_id): só as mudanças VISUAIS da imagem (fundo, cores, elementos), nas palavras do dono. Textos não entram aqui: vão em titulo, destaque, chamada e rodape.'},
                    'formato': {'type': 'string', 'enum': ['quadrado', 'story', 'paisagem']},
                    'modo_texto': {'type': 'string', 'enum': ['sistema', 'ia']},
                    'plano_id': {'type': 'integer', 'description': 'Plano divulgado (opcional).'},
                    'titulo': {'type': 'string', 'description': 'Título; sem plano_id ou para trocar o nome do plano.'},
                    'destaque': {'type': 'string', 'description': 'Frase de destaque quando não houver plano (com plano, a velocidade é usada).'},
                    'chamada': {'type': 'string', 'description': 'Chamada para ação, por exemplo "Chame no WhatsApp".'},
                    'rodape': {'type': 'string', 'description': 'Rodapé: telefone, site, cidade ou condição informada pelo dono.'},
                    'cor_destaque': {'type': 'string', 'description': 'Cor do preço em hexadecimal (#RRGGBB), modo sistema.'},
                    'logo_id': {'type': 'integer', 'description': 'Imagem anexada (#id) com a logo do provedor.'},
                    'referencias': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'Imagens anexadas (#id) usadas como inspiração.'},
                    'arte_base_id': {'type': 'integer', 'description': 'Arte existente (#id) a ser ajustada.'},
                    'telas': {
                        'type': 'array', 'items': {'type': 'integer'},
                        'description': 'Prints de telas do app (#id, até 3, o primeiro fica em destaque) colados sem alteração dentro de celulares na arte.',
                    },
                    'apenas_textos': {'type': 'boolean', 'description': 'Reaplica textos/logo/cor/telas sem gerar imagem nova (arte do modo sistema ou que já tem telas).'},
                },
                'required': ['formato', 'modo_texto'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'relatorio_anuncios',
            'description': 'Entradas de clientes por anúncio Clique para WhatsApp: entradas, contatos e contatos novos por anúncio.',
            'parameters': {
                'type': 'object',
                'properties': {'dias': {'type': 'integer', 'enum': [7, 30, 90]}},
                'required': ['dias'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'analisar_instagram',
            'description': (
                'Busca pela API oficial da Meta um perfil profissional público do Instagram (concorrente ou referência): '
                'seguidores, bio e as últimas postagens com legenda, curtidas, comentários e data. As imagens são salvas '
                'no chat (#id) com uma análise visual de cada uma. Só funciona com contas comerciais ou de criador.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'usuario': {'type': 'string', 'description': 'Usuário (@nome) ou link do perfil no Instagram.'},
                    'quantidade': {'type': 'integer', 'description': 'Quantas postagens recentes ler (1 a 12, padrão 9).'},
                },
                'required': ['usuario'],
            },
        },
    },
]


def _provider_data(provedor) -> Dict[str, Any]:
    from core.models import Plano
    from marketing.creatives import format_price, format_speed

    planos = [
        {
            'id': p.id,
            'nome': p.nome,
            'download': format_speed(p.velocidade_download),
            'upload': format_speed(p.velocidade_upload),
            'preco': format_price(p.preco),
            'descricao': p.descricao,
        }
        for p in Plano.objects.filter(provedor=provedor, ativo=True).order_by('ordem', 'nome')
    ]
    dados = {
        'nome': provedor.nome,
        'site': provedor.site_oficial,
        'email': provedor.email_contato,
        'endereco': provedor.endereco,
        'redes_sociais': provedor.redes_sociais,
        'taxa_adesao': provedor.taxa_adesao,
        'prazo_instalacao': provedor.prazo_instalacao,
        'tipo_conexao': provedor.tipo_conexao,
    }
    return {'planos': planos, 'provedor': {k: v for k, v in dados.items() if v}}


def _ads_report(provedor, dias) -> Dict[str, Any]:
    from conversations.ad_referral import REPORT_DAYS, ad_referral_report

    dias = dias if dias in REPORT_DAYS else 30
    report = ad_referral_report(provedor.id, dias)
    report['ads'] = [
        {k: ad[k] for k in ('source_id', 'source_type', 'headline', 'body', 'entries', 'contacts', 'new_contacts', 'last_entry_at')}
        for ad in report['ads'][:20]
    ]
    return report


def _save_instagram_post(provedor, thread, user, username: str, item: Dict[str, Any], data: bytes):
    from PIL import Image
    import io

    permalink = item.get('permalink') or ''
    existing = MarketingAsset.objects.filter(
        provedor=provedor, thread=thread, kind='reference', textos__permalink=permalink
    ).first() if permalink else None
    if existing:
        return existing, False
    try:
        png = image_engine.reference_png(data)
        width, height = Image.open(io.BytesIO(png)).size
    except Exception:
        return None, False
    day = (item.get('timestamp') or '')[:10]
    asset = MarketingAsset.objects.create(
        provedor=provedor, thread=thread, kind='reference', image=png, mime_type='image/png',
        width=width, height=height, original_name=f'@{username} {day}'.strip(), created_by=user,
        textos={
            'fonte': 'instagram', 'usuario': username, 'permalink': permalink, 'data': day,
            'curtidas': item.get('like_count'), 'comentarios': item.get('comments_count'),
        },
    )
    return asset, True


def _instagram_analysis(provedor, thread, user, args: Dict[str, Any], created: List[int]) -> Dict[str, Any]:
    from marketing import instagram_discovery as igd

    try:
        profile = igd.fetch_profile(args.get('usuario') or '', args.get('quantidade') or 9)
    except igd.DiscoveryError as exc:
        return {'ok': False, 'erro': str(exc)}

    username = profile.get('username') or ''
    can_describe = True
    posts = []
    saved = 0
    for item in profile['media']:
        post = {
            'tipo': item.get('media_product_type') or item.get('media_type'),
            'data': (item.get('timestamp') or '')[:10],
            'curtidas': item.get('like_count'),
            'comentarios': item.get('comments_count'),
            'legenda': (item.get('caption') or '')[:500],
            'link': item.get('permalink'),
        }
        is_image = item.get('media_type') in ('IMAGE', 'CAROUSEL_ALBUM')
        if is_image and saved < MAX_INSTAGRAM_IMAGES and item.get('media_url'):
            data = igd.download_media(item['media_url'])
            asset, is_new = _save_instagram_post(provedor, thread, user, username, item, data) if data else (None, False)
            if asset:
                saved += 1
                post['imagem_id'] = asset.id
                if is_new and can_describe:
                    try:
                        asset.descricao = image_engine.describe_image(provedor, data, image_engine.COMPETITOR_PROMPT)[:2000]
                        asset.save(update_fields=['descricao'])
                    except image_engine.ImageEngineUnavailable:
                        can_describe = False
                    except Exception as exc:
                        can_describe = not image_engine.is_auth_error(exc)
                        logger.warning('[Marketing] Falha ao analisar post de @%s', username, exc_info=True)
                post['analise_visual'] = asset.descricao or None
                created.append(asset.id)
        posts.append(post)

    likes = [p['curtidas'] for p in posts if isinstance(p.get('curtidas'), int)]
    comments = [p['comentarios'] for p in posts if isinstance(p.get('comentarios'), int)]
    return {
        'ok': True,
        'perfil': {k: profile.get(k) for k in ('username', 'name', 'biography', 'website', 'followers_count', 'media_count')},
        'posts_analisados': len(posts),
        'media_curtidas': round(sum(likes) / len(likes), 1) if likes else None,
        'media_comentarios': round(sum(comments) / len(comments), 1) if comments else None,
        'posts': posts,
        'observacao': 'Imagens com imagem_id foram salvas no chat e o dono já as vê. Curtidas ocultas pelo perfil vêm vazias.',
    }


def _run_tool(name: str, args: Dict[str, Any], *, provedor, thread, user, created: List[int]) -> Dict[str, Any]:
    from marketing.creatives import CreativeError, create_creative
    from marketing.image_engine import ImageEngineUnavailable

    if name == 'consultar_planos_e_dados':
        return _provider_data(provedor)
    if name == 'relatorio_anuncios':
        return _ads_report(provedor, args.get('dias'))
    if name == 'analisar_instagram':
        return _instagram_analysis(provedor, thread, user, args, created)
    if name == 'gerar_arte':
        allowed = {
            'descricao_visual', 'formato', 'modo_texto', 'plano_id', 'titulo', 'destaque', 'chamada', 'rodape',
            'cor_destaque', 'logo_id', 'referencias', 'arte_base_id', 'apenas_textos', 'telas', 'alteracoes',
        }
        try:
            asset, textos = create_creative(
                provedor=provedor, thread=thread, user=user, **{k: v for k, v in args.items() if k in allowed}
            )
        except (CreativeError, ImageEngineUnavailable) as exc:
            return {'ok': False, 'erro': str(exc)}
        except Exception as exc:
            logger.exception('[Marketing] Falha ao gerar arte (provedor %s)', provedor.id)
            return {'ok': False, 'erro': image_engine.friendly_error(exc, *_engine_source(provedor))}
        created.append(asset.id)
        return {
            'ok': True,
            'arte_id': asset.id,
            'formato': asset.formato,
            'modo_texto': asset.modo_texto,
            'telas': (asset.textos or {}).get('telas') or None,
            'textos_aplicados': {k: v for k, v in textos.items() if v} if asset.modo_texto == 'sistema' else None,
            'textos_pedidos_a_ia': {k: v for k, v in textos.items() if v} if asset.modo_texto == 'ia' else None,
        }
    return {'ok': False, 'erro': f'Tool desconhecida: {name}'}


def _describe_assets(ids: List[int], provedor) -> str:
    if not ids:
        return ''
    items = MarketingAsset.objects.filter(provedor=provedor, pk__in=ids).select_related('plano')
    labels = []
    for item in items:
        if item.kind == 'reference':
            label = f'#{item.id} ({item.original_name or "imagem"})'
            if item.descricao:
                label += f': {item.descricao}'
            labels.append(label)
        else:
            plano = f", plano '{item.plano.nome}'" if item.plano else ''
            labels.append(f'#{item.id} ({item.formato}, modo {item.modo_texto}{plano})')
    return '\n'.join(labels)


def _engine_source(provedor):
    try:
        provider, _, source = image_engine.resolve_image_engine(provedor)
        return provider, source
    except image_engine.ImageEngineUnavailable:
        return '', 'principal'


def _describe_new_references(thread, provedor) -> None:
    ids = set()
    for asset_ids in thread.messages.filter(role='user').values_list('asset_ids', flat=True):
        ids.update(asset_ids or [])
    if not ids:
        return
    pending = MarketingAsset.objects.filter(
        provedor=provedor, pk__in=ids, kind='reference', descricao=''
    ).order_by('-id')[:MAX_DESCRIBE_PER_TURN]
    for asset in pending:
        try:
            text = image_engine.describe_image(provedor, bytes(asset.image))
        except image_engine.ImageEngineUnavailable:
            return
        except Exception as exc:
            if image_engine.is_auth_error(exc):
                logger.warning('[Marketing] Chave de imagem recusada ao descrever referências (provedor %s)', provedor.id)
                return
            logger.warning('[Marketing] Não foi possível descrever a referência %s', asset.id, exc_info=True)
            continue
        if text:
            asset.descricao = text[:2000]
            asset.save(update_fields=['descricao'])


def _history(thread, provedor, exclude_id: int) -> List[Dict[str, Any]]:
    rows = list(
        thread.messages.filter(status='done').exclude(pk=exclude_id).order_by('-id')[:HISTORY_LIMIT]
    )[::-1]
    out = []
    for row in rows:
        if row.role == 'assistant':
            out += _past_creations(row, provedor)
            text = _strip_annotations(row.content or '')
        else:
            text = row.content or ''
            described = _describe_assets(row.asset_ids or [], provedor)
            if described:
                text = f'{text}\n[Imagens anexadas pelo dono:\n{described}]'.strip()
        if text:
            out.append({'role': row.role, 'content': text})
    return out


def _strip_annotations(text: str) -> str:
    return _ANNOTATION_RE.sub('', text).strip()


def _past_creations(row, provedor) -> List[Dict[str, Any]]:
    """Artes criadas e posts de Instagram baixados numa resposta anterior viram o par tool_call/resultado
    que de fato aconteceu."""
    assets = list(
        MarketingAsset.objects.filter(provedor=provedor, pk__in=row.asset_ids or []).select_related('plano').order_by('id')
    )
    if not assets:
        return []
    calls, results = [], []
    instagram = {}
    for asset in assets:
        source = asset.textos or {}
        if asset.kind == 'reference':
            if source.get('fonte') == 'instagram':
                instagram.setdefault(source.get('usuario') or '', []).append({
                    'imagem_id': asset.id, 'data': source.get('data'), 'curtidas': source.get('curtidas'),
                    'comentarios': source.get('comentarios'), 'analise_visual': asset.descricao,
                })
            continue
        call_id = f'hist_{row.id}_{asset.id}'
        args = {'formato': asset.formato, 'modo_texto': asset.modo_texto}
        if asset.parent_id:
            args['arte_base_id'] = asset.parent_id
        if asset.plano_id:
            args['plano_id'] = asset.plano_id
        if (asset.textos or {}).get('telas'):
            args['telas'] = asset.textos['telas']
        calls.append({
            'id': call_id,
            'type': 'function',
            'function': {'name': 'gerar_arte', 'arguments': json.dumps(args, ensure_ascii=False)},
        })
        results.append({
            'role': 'tool',
            'tool_call_id': call_id,
            'content': json.dumps({'ok': True, 'arte_id': asset.id, **args}, ensure_ascii=False),
        })
    for usuario, imagens in instagram.items():
        call_id = f'hist_{row.id}_ig_{imagens[0]["imagem_id"]}'
        calls.append({
            'id': call_id,
            'type': 'function',
            'function': {'name': 'analisar_instagram', 'arguments': json.dumps({'usuario': usuario}, ensure_ascii=False)},
        })
        results.append({
            'role': 'tool',
            'tool_call_id': call_id,
            'content': json.dumps({'ok': True, 'usuario': usuario, 'imagens_salvas': imagens}, ensure_ascii=False),
        })
    if not calls:
        return []
    return [{'role': 'assistant', 'content': None, 'tool_calls': calls}, *results]


def run_turn(message_id: int) -> None:
    from ai.providers import OPENAI_KEY_MISSING_MSG, get_provider_client

    pending = MarketingMessage.objects.select_related('thread__provedor', 'thread__created_by').filter(
        pk=message_id, status='pending'
    ).first()
    if not pending:
        return
    thread = pending.thread
    provedor = thread.provedor
    user = thread.created_by
    created: List[int] = []
    try:
        client = get_provider_client(provedor)
        if not client.available:
            raise RuntimeError(OPENAI_KEY_MISSING_MSG)
        _describe_new_references(thread, provedor)
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT.format(provedor=provedor.nome)}]
        messages += _history(thread, provedor, pending.id)

        final_text = ''
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat_completions_create(messages, tools=TOOLS, tool_choice='auto')
            msg = resp.choices[0].message
            tool_calls = getattr(msg, 'tool_calls', None) or []
            if not tool_calls:
                final_text = _strip_annotations(msg.content or '')
                break
            messages.append({
                'role': 'assistant',
                'content': msg.content or None,
                'tool_calls': [
                    {
                        'id': tc.id,
                        'type': 'function',
                        'function': {'name': tc.function.name, 'arguments': tc.function.arguments or '{}'},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or '{}')
                except json.JSONDecodeError:
                    args = {}
                result = _run_tool(
                    tc.function.name, args if isinstance(args, dict) else {},
                    provedor=provedor, thread=thread, user=user, created=created,
                )
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': json.dumps(result, ensure_ascii=False, default=str),
                })
        if not final_text:
            final_text = 'Arte criada.' if created else 'Não consegui concluir o pedido. Pode reformular?'
        pending.content = final_text
        pending.status = 'done'
    except Exception as exc:
        logger.exception('[Marketing] Falha no turno da IA (mensagem %s)', message_id)
        pending.content = f'Não consegui responder agora: {str(exc)[:300]}'
        pending.status = 'error'
    pending.asset_ids = created
    pending.save(update_fields=['content', 'status', 'asset_ids'])
    type(thread).objects.filter(pk=thread.pk).update(updated_at=timezone.now())


def _run_safe(message_id: int) -> None:
    try:
        run_turn(message_id)
    finally:
        close_old_connections()


def start_turn(message_id: int) -> None:
    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_safe, args=(message_id,), name='niochat-marketing', daemon=True
        ).start()
    )


def expire_stale_pending(thread) -> None:
    """Turno perdido (processo reiniciado no meio da geração) não pode travar a conversa."""
    limit = timezone.now() - PENDING_TIMEOUT
    thread.messages.filter(status='pending', created_at__lt=limit).update(
        status='error', content='A resposta demorou demais e foi interrompida. Envie o pedido novamente.'
    )
