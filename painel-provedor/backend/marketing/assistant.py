"""IA de tráfego pago do Estúdio: publica, edita, pausa e analisa campanhas na Meta para o dono do provedor."""
from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from django.db import close_old_connections, transaction
from django.utils import timezone

from marketing import meta_ads
from marketing.meta_ads import MetaAdsError
from marketing.models import MarketingAsset, MarketingMessage, MetaAdAction, MetaAdsConnection

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
HISTORY_LIMIT = 40
PENDING_TIMEOUT = timedelta(minutes=10)
ACTION_TTL = timedelta(hours=24)

SYSTEM_PROMPT = """Você é a IA de tráfego pago do provedor de internet {provedor} no Estúdio de Marketing. Você conversa com o dono ou gestor do provedor (nunca com clientes finais) e cuida das campanhas de anúncios dele no Facebook e no Instagram (Meta).

O que você faz:
- Publica campanhas novas na conta de anúncios conectada, com a imagem e os textos que o dono enviar e a segmentação que ele pedir.
- Edita campanhas existentes: nome, orçamento diário, data de término, público (locais, idade, gênero, interesses), textos, imagem e link; ativa e pausa campanhas.
- Analisa os resultados (gasto, alcance, cliques, conversas iniciadas no WhatsApp, custo por resultado, desempenho por idade, gênero e plataforma) e as entradas de clientes que chegaram ao WhatsApp do painel por anúncio, e recomenda melhorias práticas.

Como montar uma campanha nova:
- Destino: pergunte se o anúncio leva para o WhatsApp (Clique para WhatsApp: abre conversa com o número de WhatsApp ligado à Página do Facebook) ou para um site (peça o link completo).
- Imagem: use só imagens que o dono enviou no chat (#id). Se ainda não enviou, peça que anexe pelo clipe, arraste ou cole com Ctrl+V. Você não cria imagens.
- Textos: use exatamente o texto principal, o título e a descrição que o dono escrever. Se ele pedir sugestão, sugira, mas só use depois que ele aprovar. Planos, velocidades, preços e condições só podem vir do que o dono escreveu ou da tool consultar_planos_e_dados; nunca invente números nem promoções.
- Público: precisa de pelo menos um local. Pode ser o país inteiro (anúncio nacional, ex.: Brasil), estados inteiros (ex.: Pará, Ceará), cidades com UF (ex.: Parauapebas - PA) ou pontos no mapa com latitude, longitude e raio. Informe sempre o tipo de cada local (pais, estado ou cidade). Se o dono disser um nome que é estado e cidade ao mesmo tempo (Rio de Janeiro, São Paulo) sem deixar claro, pergunte se é o estado inteiro ou só a cidade. Brasil inteiro não se combina com cidades ou estados do Brasil: use um ou outro. Raio em volta de cidade vai de 17 a 80 km; para áreas menores (bairro, região de cobertura) use pontos com raio a partir de 1 km. Pergunte idade, gênero e interesses se ele não disse; se ele disser que tanto faz, use 18 a 65 anos, todos os gêneros e sem interesses.
- Orçamento diário em reais e, se ele quiser, datas de início e fim. Sem início, começa assim que a Meta aprovar; sem fim, roda até ser pausada.
- Nome da campanha: se o dono não der, sugira um curto e descritivo.

Confirmação (obrigatória, porque envolve o dinheiro do dono):
- Para criar ou editar, chame preparar_campanha ou preparar_edicao. Elas não publicam nada: devolvem um resumo e um acao_id.
- Mostre o resumo completo ao dono com os valores exatos que a tool devolveu (nome, destino, textos, imagem #id, locais, idade, gênero, interesses, orçamento diário, datas, Página e Instagram) e pergunte se pode publicar. Pare aí e espere a resposta. Abaixo da sua mensagem aparece um botão para ele publicar com um clique.
- Quando o dono responder concordando com o resumo (ex.: "pode publicar", "pode criar", "sim"), chame confirmar_acao com o acao_id da ação aguardando confirmação. Nunca prepare a mesma campanha de novo só porque ele concordou: preparar de novo só quando ele pedir mudanças (a ação antiga é descartada sozinha).
- Pausar é imediato: use pausar_campanha quando o dono pedir. Ativar uma campanha pausada é uma edição e precisa de confirmação.
- Depois de confirmar, avise que a Meta ainda revisa o anúncio antes de veicular (normalmente de minutos a 24 horas).

Regras gerais:
- Só diga que publicou, editou ou pausou algo se a tool retornou ok nesta resposta. Se retornar erro, explique o erro exatamente como veio e o que o dono pode fazer; não invente erros nem finja sucesso.
- Se o Facebook não estiver conectado, ou faltar escolher a conta de anúncios e a Página, explique que ele precisa usar o botão no topo do Estúdio antes.
- Em análises, entregue conclusões e recomendações práticas baseadas só nos números retornados (o que está funcionando, o que está caro, onde cortar ou investir), não uma lista crua.
- Não peça ao dono IDs técnicos; para campanhas existentes, consulte listar_campanhas e identifique pelo nome.
- Responda em português do Brasil, de forma direta, em texto simples: o chat não formata markdown, então não use **, #, tabelas nem links em colchetes; use listas com hífen quando ajudar."""

_PUBLICO_PROPS: Dict[str, Any] = {
    'locais': {
        'type': 'array',
        'description': (
            'Locais do público: país inteiro (tipo "pais", ex.: Brasil), estado inteiro (tipo "estado", nome ou UF, '
            'ex.: Pará ou PA) ou cidade (tipo "cidade", com UF: "Parauapebas - PA", raio opcional de 17 a 80 km).'
        ),
        'items': {
            'type': 'object',
            'properties': {
                'tipo': {'type': 'string', 'enum': ['pais', 'estado', 'cidade']},
                'nome': {'type': 'string'},
                'raio_km': {'type': 'number'},
            },
            'required': ['tipo', 'nome'],
        },
    },
    'pontos': {
        'type': 'array',
        'description': 'Pontos no mapa (latitude, longitude) com raio em km (1 a 80), para bairros ou áreas de cobertura.',
        'items': {
            'type': 'object',
            'properties': {
                'latitude': {'type': 'number'},
                'longitude': {'type': 'number'},
                'raio_km': {'type': 'number'},
            },
            'required': ['latitude', 'longitude'],
        },
    },
    'idade_min': {'type': 'integer', 'description': '18 a 65.'},
    'idade_max': {'type': 'integer', 'description': '18 a 65 (65 = 65 ou mais).'},
    'generos': {'type': 'string', 'enum': ['todos', 'homens', 'mulheres']},
    'interesses': {
        'type': 'array', 'items': {'type': 'string'},
        'description': 'Interesses do público em português (ex.: "Jogos online", "Netflix"). Lista vazia remove os interesses.',
    },
}

_CRIATIVO_PROPS: Dict[str, Any] = {
    'imagem_id': {'type': 'integer', 'description': 'Imagem enviada pelo dono no chat (#id).'},
    'texto_principal': {'type': 'string', 'description': 'Texto principal do anúncio, exatamente como o dono aprovou.'},
    'titulo': {'type': 'string', 'description': 'Título curto do anúncio.'},
    'descricao': {'type': 'string', 'description': 'Descrição (linha abaixo do título).'},
    'link': {'type': 'string', 'description': 'Link do site (só destino site).'},
}

TOOLS: List[Dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'consultar_planos_e_dados',
            'description': 'Lista os planos ativos (nome, velocidades, preço, descrição) e os dados comerciais do provedor.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'preparar_campanha',
            'description': (
                'Valida e monta uma campanha NOVA (campanha, público e anúncio) sem publicar. Devolve o resumo e o '
                'acao_id para o dono confirmar.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'nome': {'type': 'string'},
                    'destino': {'type': 'string', 'enum': ['whatsapp', 'site']},
                    'chamada': {'type': 'string', 'enum': sorted(meta_ads.CHAMADAS_SITE), 'description': 'Botão do anúncio (só destino site).'},
                    'orcamento_diario': {'type': 'number', 'description': 'Valor por dia em reais.'},
                    'data_inicio': {'type': 'string', 'description': 'AAAA-MM-DD (opcional).'},
                    'data_fim': {'type': 'string', 'description': 'AAAA-MM-DD (opcional).'},
                    **_CRIATIVO_PROPS,
                    **_PUBLICO_PROPS,
                },
                'required': ['nome', 'destino', 'orcamento_diario', 'imagem_id', 'texto_principal'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'preparar_edicao',
            'description': (
                'Valida e monta uma edição de campanha existente sem aplicar. Envie só o que muda. Devolve o resumo e '
                'o acao_id para o dono confirmar.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'campanha_id': {'type': 'string'},
                    'nome': {'type': 'string'},
                    'orcamento_diario': {'type': 'number', 'description': 'Novo valor por dia em reais.'},
                    'data_fim': {'type': 'string', 'description': 'Nova data de término AAAA-MM-DD.'},
                    'status': {'type': 'string', 'enum': ['ativar', 'pausar']},
                    **_CRIATIVO_PROPS,
                    **_PUBLICO_PROPS,
                },
                'required': ['campanha_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'confirmar_acao',
            'description': 'Executa na Meta uma ação preparada, SOMENTE depois que o dono respondeu concordando com o resumo.',
            'parameters': {
                'type': 'object',
                'properties': {'acao_id': {'type': 'integer'}},
                'required': ['acao_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'cancelar_acao',
            'description': 'Descarta uma ação preparada que o dono não quer mais.',
            'parameters': {
                'type': 'object',
                'properties': {'acao_id': {'type': 'integer'}},
                'required': ['acao_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'pausar_campanha',
            'description': 'Pausa uma campanha na hora (para de gastar).',
            'parameters': {
                'type': 'object',
                'properties': {'campanha_id': {'type': 'string'}},
                'required': ['campanha_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'listar_campanhas',
            'description': 'Campanhas da conta de anúncios com status, orçamento e métricas do período.',
            'parameters': {
                'type': 'object',
                'properties': {'periodo': {'type': 'string', 'enum': sorted(meta_ads.PERIODOS)}},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'analisar_campanha',
            'description': 'Detalhes de uma campanha: público, anúncios e métricas no total, por anúncio, por idade/gênero e por plataforma.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'campanha_id': {'type': 'string'},
                    'periodo': {'type': 'string', 'enum': sorted(meta_ads.PERIODOS)},
                },
                'required': ['campanha_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'relatorio_anuncios',
            'description': 'Entradas de clientes no WhatsApp do painel por anúncio Clique para WhatsApp: entradas, contatos e contatos novos.',
            'parameters': {
                'type': 'object',
                'properties': {'dias': {'type': 'integer', 'enum': [7, 30, 90]}},
                'required': ['dias'],
            },
        },
    },
]


class ToolError(Exception):
    pass


def _format_price(preco) -> str:
    try:
        value = Decimal(preco or 0)
    except (InvalidOperation, TypeError):
        return ''
    if value <= 0:
        return ''
    text = f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {text}/mês'


def _format_speed(value) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return f'{text} MEGA' if text.isdigit() else text.upper()


def _provider_data(provedor) -> Dict[str, Any]:
    from core.models import Plano

    planos = [
        {
            'nome': p.nome,
            'download': _format_speed(p.velocidade_download),
            'upload': _format_speed(p.velocidade_upload),
            'preco': _format_price(p.preco),
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


def _connection(provedor) -> MetaAdsConnection:
    conn = MetaAdsConnection.objects.filter(provedor=provedor).first()
    if not conn or not conn.access_token:
        raise ToolError('O Facebook não está conectado. Peça ao dono para clicar em "Conectar Facebook" no topo do Estúdio.')
    if conn.token_expires_at and conn.token_expires_at <= timezone.now():
        raise ToolError(meta_ads.TOKEN_EXPIRED_MSG)
    if not conn.ready:
        raise ToolError('Falta escolher a conta de anúncios e a Página do Facebook no topo do Estúdio.')
    return conn


def _image(provedor, imagem_id) -> MarketingAsset:
    asset = MarketingAsset.objects.filter(provedor=provedor, pk=imagem_id or 0, kind='reference').only('id', 'original_name', 'width', 'height').first()
    if not asset:
        raise ToolError(f'Imagem #{imagem_id} não encontrada. Use uma imagem que o dono enviou no chat.')
    return asset


def _image_label(asset: MarketingAsset) -> str:
    return f'#{asset.id} ({asset.original_name or "imagem"}, {asset.width}x{asset.height})'


def _text(args, key, limit) -> str:
    return str(args.get(key) or '').strip()[:limit]


def _site_link(args) -> str:
    link = _text(args, 'link', 1000)
    if not link.lower().startswith(('http://', 'https://')):
        raise ToolError('Para destino site, informe o link completo começando com https://.')
    return link


def _publico(conn, args, *, required: bool):
    """Resolve locais/pontos/idade/gênero/interesses na Meta. Retorna (targeting_patch, remover, resumo)."""
    token = conn.access_token
    patch: Dict[str, Any] = {}
    remove: List[str] = []
    resumo: Dict[str, Any] = {}
    if args.get('locais') or args.get('pontos') or required:
        geo, labels = meta_ads.resolve_locations(token, args.get('locais') or [])
        custom, plabels = meta_ads.resolve_points(args.get('pontos') or [])
        base = meta_ads.build_targeting(geo, custom, 18, 65, 'todos', [], bool(conn.instagram_user_id))
        patch['geo_locations'] = base['geo_locations']
        if 'publisher_platforms' in base:
            patch['publisher_platforms'] = base['publisher_platforms']
        resumo['locais'] = labels + plabels
    if args.get('idade_min') is not None or args.get('idade_max') is not None or required:
        idade_min = max(18, min(65, int(args.get('idade_min') or 18)))
        idade_max = max(18, min(65, int(args.get('idade_max') or 65)))
        if idade_min > idade_max:
            raise ToolError('A idade mínima não pode ser maior que a máxima.')
        patch.update({'age_min': idade_min, 'age_max': idade_max})
        resumo['idade'] = f'{idade_min} a {idade_max}{"+" if idade_max == 65 else ""} anos'
    if args.get('generos') or required:
        generos = args.get('generos') or 'todos'
        if meta_ads.GENEROS.get(generos):
            patch['genders'] = meta_ads.GENEROS[generos]
        else:
            remove.append('genders')
        resumo['generos'] = generos
    if 'interesses' in args or required:
        interesses = meta_ads.resolve_interests(token, args.get('interesses') or [])
        if interesses:
            patch['flexible_spec'] = [{'interests': interesses}]
        else:
            remove.append('flexible_spec')
        resumo['interesses'] = [i['name'] for i in interesses] or 'sem interesses (público amplo nos locais)'
    return patch, remove, resumo


def _identidade(conn) -> Dict[str, str]:
    return {
        'conta_de_anuncios': conn.ad_account_name or conn.ad_account_id,
        'pagina': conn.page_name or conn.page_id,
        'instagram': f'@{conn.instagram_username}' if conn.instagram_user_id else 'sem Instagram ligado à Página (anúncio só no Facebook)',
    }


def _preparar_campanha(args, *, provedor, thread, user, message) -> Dict[str, Any]:
    conn = _connection(provedor)
    nome = _text(args, 'nome', 200)
    destino = args.get('destino')
    texto = _text(args, 'texto_principal', 2000)
    if not nome or destino not in ('whatsapp', 'site') or not texto:
        raise ToolError('Informe nome, destino (whatsapp ou site) e o texto principal do anúncio.')
    asset = _image(provedor, args.get('imagem_id'))
    criativo = {
        'destino': destino,
        'texto_principal': texto,
        'titulo': _text(args, 'titulo', 255),
        'descricao': _text(args, 'descricao', 255),
    }
    if destino == 'site':
        criativo['link'] = _site_link(args)
        criativo['chamada'] = args.get('chamada') if args.get('chamada') in meta_ads.CHAMADAS_SITE else 'saiba_mais'
    orcamento = meta_ads._to_minor(args.get('orcamento_diario'))
    inicio = meta_ads.parse_day(args.get('data_inicio'))
    fim = meta_ads.parse_day(args.get('data_fim'), end=True)
    patch, _, publico = _publico(conn, args, required=True)
    targeting = {**patch, 'targeting_automation': {'advantage_audience': 0}}

    payload = {
        'nome': nome,
        'orcamento_diario': orcamento,
        'inicio': inicio,
        'fim': fim,
        'targeting': targeting,
        'imagem_id': asset.id,
        'criativo': criativo,
    }
    resumo = {
        'nome': nome,
        'destino': 'WhatsApp (Clique para WhatsApp)' if destino == 'whatsapp' else f'Site: {criativo["link"]}',
        'imagem': _image_label(asset),
        'texto_principal': texto,
        'titulo': criativo['titulo'] or None,
        'descricao': criativo['descricao'] or None,
        'botao': criativo.get('chamada') or 'Enviar mensagem no WhatsApp',
        'publico': publico,
        'orcamento_diario': meta_ads.format_money(orcamento, conn.currency),
        'inicio': (args.get('data_inicio') or 'assim que a Meta aprovar'),
        'fim': (args.get('data_fim') or 'sem data de término (roda até pausar)'),
        **_identidade(conn),
    }
    cancel_pending_actions(thread, 'Substituída por um resumo mais novo')
    action = MetaAdAction.objects.create(
        provedor=provedor, thread=thread, message=message, kind='create',
        payload=payload, resumo=resumo, created_by=user,
    )
    return {
        'ok': True,
        'acao_id': action.id,
        'resumo': resumo,
        'proximo_passo': (
            'Mostre este resumo ao dono (use exatamente os valores daqui) e pergunte se pode publicar. Ele pode '
            'clicar em "Publicar na Meta" abaixo da sua mensagem ou responder concordando; nesse caso chame '
            f'confirmar_acao com acao_id {action.id}.'
        ),
    }


def _preparar_edicao(args, *, provedor, thread, user, message) -> Dict[str, Any]:
    conn = _connection(provedor)
    campaign_id = _text(args, 'campanha_id', 64)
    if not campaign_id:
        raise ToolError('Informe a campanha a editar.')
    current = meta_ads.campaign_structure(conn, campaign_id)
    payload: Dict[str, Any] = {}
    mudancas: Dict[str, Any] = {}

    if _text(args, 'nome', 200):
        payload['nome'] = mudancas['nome'] = _text(args, 'nome', 200)
    if args.get('orcamento_diario') is not None:
        payload['orcamento_diario'] = meta_ads._to_minor(args['orcamento_diario'])
        mudancas['orcamento_diario'] = meta_ads.format_money(payload['orcamento_diario'], conn.currency)
    if args.get('data_fim'):
        payload['fim'] = meta_ads.parse_day(args['data_fim'], end=True)
        mudancas['fim'] = args['data_fim']
    if args.get('status') in ('ativar', 'pausar'):
        payload['status'] = 'ACTIVE' if args['status'] == 'ativar' else 'PAUSED'
        mudancas['status'] = args['status']

    patch, remove, publico = _publico(conn, args, required=False)
    if patch or remove:
        payload['targeting_patch'] = patch
        payload['targeting_remove'] = remove
        mudancas['publico'] = publico

    criativo_patch = {}
    for key, limit in (('texto_principal', 2000), ('titulo', 255), ('descricao', 255)):
        if key in args:
            criativo_patch[key] = _text(args, key, limit)
    if args.get('link'):
        criativo_patch['link'] = _site_link(args)
    if criativo_patch:
        payload['criativo_patch'] = criativo_patch
        mudancas.update(criativo_patch)
    if args.get('imagem_id'):
        asset = _image(provedor, args['imagem_id'])
        payload['imagem_id'] = asset.id
        mudancas['imagem'] = _image_label(asset)

    if not mudancas:
        raise ToolError('Nenhuma mudança informada para a campanha.')
    resumo = {
        'campanha': current.get('name'),
        'status_atual': current.get('effective_status') or current.get('status'),
        'orcamento_atual': meta_ads.format_money(current.get('daily_budget'), conn.currency) if current.get('daily_budget') else None,
        'mudancas': mudancas,
    }
    cancel_pending_actions(thread, 'Substituída por um resumo mais novo')
    action = MetaAdAction.objects.create(
        provedor=provedor, thread=thread, message=message, kind='update', campaign_id=campaign_id,
        payload=payload, resumo=resumo, created_by=user,
    )
    return {
        'ok': True,
        'acao_id': action.id,
        'resumo': resumo,
        'proximo_passo': (
            'Mostre as mudanças ao dono (use exatamente os valores daqui) e pergunte se pode aplicar. Ele pode '
            'clicar em "Aplicar na Meta" abaixo da sua mensagem ou responder concordando; nesse caso chame '
            f'confirmar_acao com acao_id {action.id}.'
        ),
    }


def _confirmar(args, *, provedor, thread, message) -> Dict[str, Any]:
    action = MetaAdAction.objects.filter(provedor=provedor, thread=thread, pk=args.get('acao_id') or 0).first()
    if not action:
        raise ToolError('Ação não encontrada nesta conversa.')
    answered = thread.messages.filter(role='user', pk__gt=action.message_id or 0).exists()
    if action.message_id == message.id or not answered:
        raise ToolError('O dono ainda não respondeu ao resumo. Mostre o resumo e espere ele confirmar.')
    return execute_action(action)


def cancel_pending_actions(thread, reason: str = '') -> int:
    return thread.ad_actions.filter(status='pending').update(status='cancelled', error=reason)


def execute_action(action: MetaAdAction) -> Dict[str, Any]:
    """Executa na Meta uma ação que o dono confirmou (pelo chat ou pelo botão). Roda no máximo uma vez."""
    provedor = action.provedor
    if action.status != 'pending':
        raise ToolError(f'Esta ação já está como "{action.get_status_display()}".')
    if action.created_at < timezone.now() - ACTION_TTL:
        MetaAdAction.objects.filter(pk=action.pk, status='pending').update(status='cancelled', error='Expirada')
        raise ToolError('Esta ação expirou (mais de 24 horas). Prepare de novo.')
    if action.thread_id and MetaAdAction.objects.filter(thread_id=action.thread_id, status='pending', pk__gt=action.pk).exists():
        raise ToolError('Este resumo foi substituído por um mais novo nesta conversa. Confirme o mais recente.')
    conn = _connection(provedor)
    if not MetaAdAction.objects.filter(pk=action.pk, status='pending').update(status='running'):
        raise ToolError('Esta ação já está sendo executada.')

    try:
        image = None
        if action.payload.get('imagem_id'):
            asset = MarketingAsset.objects.filter(provedor=provedor, pk=action.payload['imagem_id']).only('image').first()
            if not asset:
                raise MetaAdsError('A imagem escolhida foi apagada. Envie a imagem de novo.')
            image = bytes(asset.image)
        if action.kind == 'create':
            result = meta_ads.create_campaign(conn, action.payload, image)
        else:
            result = meta_ads.update_campaign(conn, action.campaign_id, action.payload, image)
    except MetaAdsError as exc:
        MetaAdAction.objects.filter(pk=action.pk).update(status='error', error=str(exc)[:2000])
        return {'ok': False, 'erro': str(exc)}
    except Exception as exc:
        logger.exception('[MetaAds] Falha ao executar ação %s', action.pk)
        MetaAdAction.objects.filter(pk=action.pk).update(status='error', error=str(exc)[:2000])
        return {'ok': False, 'erro': f'Falha inesperada: {str(exc)[:300]}'}

    MetaAdAction.objects.filter(pk=action.pk).update(
        status='applied', result=result, applied_at=timezone.now(),
        campaign_id=result.get('campanha_id') or action.campaign_id,
    )
    return {
        'ok': True,
        'resultado': result,
        'observacao': 'Publicado na Meta. O anúncio passa pela revisão da Meta antes de começar a veicular.',
    }


def _run_tool(name: str, args: Dict[str, Any], *, provedor, thread, user, message) -> Dict[str, Any]:
    try:
        if name == 'consultar_planos_e_dados':
            return _provider_data(provedor)
        if name == 'relatorio_anuncios':
            return _ads_report(provedor, args.get('dias'))
        if name == 'preparar_campanha':
            return _preparar_campanha(args, provedor=provedor, thread=thread, user=user, message=message)
        if name == 'preparar_edicao':
            return _preparar_edicao(args, provedor=provedor, thread=thread, user=user, message=message)
        if name == 'confirmar_acao':
            return _confirmar(args, provedor=provedor, thread=thread, message=message)
        if name == 'cancelar_acao':
            done = MetaAdAction.objects.filter(
                provedor=provedor, thread=thread, pk=args.get('acao_id') or 0, status='pending'
            ).update(status='cancelled')
            return {'ok': bool(done)} if done else {'ok': False, 'erro': 'Nenhuma ação pendente com esse número.'}
        if name == 'pausar_campanha':
            meta_ads.pause_campaign(_connection(provedor), _text(args, 'campanha_id', 64))
            return {'ok': True, 'status': 'pausada'}
        if name == 'listar_campanhas':
            return meta_ads.list_campaigns(_connection(provedor), args.get('periodo') or '30d')
        if name == 'analisar_campanha':
            return meta_ads.analyze_campaign(_connection(provedor), _text(args, 'campanha_id', 64), args.get('periodo') or '30d')
    except (ToolError, MetaAdsError) as exc:
        return {'ok': False, 'erro': str(exc)}
    return {'ok': False, 'erro': f'Tool desconhecida: {name}'}


def _context_message(provedor, thread) -> Dict[str, str]:
    lines = [f'Hoje é {timezone.localdate().strftime("%d/%m/%Y")}.']
    conn = MetaAdsConnection.objects.filter(provedor=provedor).first()
    if not conn or not conn.access_token:
        lines.append('Facebook NÃO conectado: o dono precisa clicar em "Conectar Facebook" no topo do Estúdio antes de qualquer campanha.')
    elif conn.token_expires_at and conn.token_expires_at <= timezone.now():
        lines.append('A conexão com o Facebook expirou: o dono precisa clicar em "Reconectar Facebook" no topo do Estúdio.')
    elif not conn.ready:
        lines.append('Facebook conectado, mas falta escolher a conta de anúncios e a Página no topo do Estúdio.')
    else:
        ident = _identidade(conn)
        lines.append(
            f"Conta de anúncios: {ident['conta_de_anuncios']} (moeda {conn.currency or 'BRL'}). "
            f"Página: {ident['pagina']}. Instagram: {ident['instagram']}."
        )
    limit = timezone.now() - ACTION_TTL
    pending = thread.ad_actions.filter(status='pending', created_at__gte=limit).order_by('-id').first()
    if pending:
        lines.append(
            f'AÇÃO PREPARADA AGUARDANDO O DONO: acao_id {pending.id} ({pending.get_kind_display()}): '
            f'{json.dumps(pending.resumo, ensure_ascii=False)}\n'
            f'Se a última mensagem do dono aprova esse resumo (ex.: "pode publicar", "pode criar", "sim", "ok", '
            f'"está certo"), chame confirmar_acao com acao_id {pending.id} AGORA. Não chame preparar_campanha nem '
            'preparar_edicao de novo e não repita o resumo. Só prepare de novo se ele pedir alguma mudança.'
        )
    recent = list(thread.ad_actions.exclude(status='pending').order_by('-id')[:5])
    if recent:
        lines.append('Últimas ações desta conversa:')
        for a in recent:
            detail = a.result if a.status == 'applied' else (a.error or '')
            lines.append(f'- acao_id {a.id} ({a.get_kind_display()}): {a.get_status_display()} {json.dumps(detail, ensure_ascii=False) if detail else ""}'.rstrip())
    return {'role': 'system', 'content': '\n'.join(lines)}


def _history(thread, provedor, exclude_id: int) -> List[Dict[str, Any]]:
    rows = list(
        thread.messages.filter(status='done').exclude(pk=exclude_id).order_by('-id')[:HISTORY_LIMIT]
    )[::-1]
    image_ids = {aid for row in rows if row.role == 'user' for aid in (row.asset_ids or [])}
    images = {
        a.id: _image_label(a)
        for a in MarketingAsset.objects.filter(provedor=provedor, pk__in=image_ids).only('id', 'original_name', 'width', 'height')
    }
    out = []
    for row in rows:
        text = row.content or ''
        if row.role == 'user':
            labels = [images[aid] for aid in (row.asset_ids or []) if aid in images]
            if labels:
                text = f'{text}\n[Imagens enviadas pelo dono: {", ".join(labels)}]'.strip()
        if text:
            out.append({'role': row.role, 'content': text})
    return out


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
    try:
        client = get_provider_client(provedor)
        if not client.available:
            raise RuntimeError(OPENAI_KEY_MISSING_MSG)
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT.format(provedor=provedor.nome)}]
        messages += _history(thread, provedor, pending.id)
        messages.append(_context_message(provedor, thread))

        final_text = ''
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat_completions_create(messages, tools=TOOLS, tool_choice='auto')
            msg = resp.choices[0].message
            tool_calls = getattr(msg, 'tool_calls', None) or []
            if not tool_calls:
                final_text = (msg.content or '').strip()
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
                    provedor=provedor, thread=thread, user=user, message=pending,
                )
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': json.dumps(result, ensure_ascii=False, default=str),
                })
        final_text = final_text.replace('**', '')
        pending.content = final_text or 'Não consegui concluir o pedido. Pode reformular?'
        pending.status = 'done'
    except Exception as exc:
        logger.exception('[Marketing] Falha no turno da IA (mensagem %s)', message_id)
        pending.content = f'Não consegui responder agora: {str(exc)[:300]}'
        pending.status = 'error'
    pending.save(update_fields=['content', 'status'])
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
    """Turno perdido (processo reiniciado no meio da resposta) não pode travar a conversa."""
    limit = timezone.now() - PENDING_TIMEOUT
    thread.messages.filter(status='pending', created_at__lt=limit).update(
        status='error', content='A resposta demorou demais e foi interrompida. Envie o pedido novamente.'
    )
