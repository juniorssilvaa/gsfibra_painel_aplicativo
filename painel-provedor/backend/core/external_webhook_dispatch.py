"""
Token e JSON para sistemas externos (SGP, etc.) enviarem disparos de cobrança ao Niohub.
"""
import json
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from django.conf import settings

INBOUND_WEBHOOK_PATH = '/api/webhooks/inbound/'
TOKEN_PREFIX = 'sk_live_'
_META_VAR_RE = re.compile(r'\{\{(\d+)\}\}')

# Lista oficial SGP (documentação / UI / JSON de disparo).
EXTERNAL_BILLING_VARIABLES = [
    ('idcontrato', 'Id do contrato'),
    ('idcliente', 'Id do cliente'),
    ('cliente', 'Nome do cliente'),
    ('cliente1', 'Primeiro nome do cliente'),
    ('cliente2', 'Segundo nome do cliente'),
    ('provedor', 'Nome do provedor'),
    ('vencimento', 'Data de vencimento atualizada (boleto atrasado)'),
    ('vencimento_original', 'Data de vencimento original'),
    ('titulo', 'Número do título'),
    ('valor', 'Valor do título'),
    ('valor_desc', 'Valor do título com desconto/juros/mora'),
    ('link', 'Link público para pagamento do título'),
    ('link_pix', 'Link público para pagamento via PIX'),
    ('data_aviso', 'Data de envio do aviso / data do pagamento recebido'),
    ('link_cobranca', 'Link público da cobrança para pagamento do título'),
    ('link_contato_email_inscricoes', 'Link para o cliente gerenciar recebimento de cobranças (e-mail)'),
    ('link_contato_sms_inscricoes', 'Link para o cliente gerenciar recebimento de cobranças (SMS)'),
    ('linhadigitavel', 'Linha digitável do boleto'),
    ('link_pix_html', 'Link público interativo para pagamento via PIX'),
    ('codigopix', 'Código PIX copia e cola'),
    ('celular', 'Telefone celular do cliente (enviado pelo SGP em to)'),
]

SGP_BILLING_VARIABLES = EXTERNAL_BILLING_VARIABLES

SGP_VARIABLE_KEYS = frozenset(k for k, _ in EXTERNAL_BILLING_VARIABLES)

# Chave no JSON de disparo → aliases que o SGP pode enviar no payload (sem misturar pares distintos).
SGP_PAYLOAD_ALIASES: Dict[str, Tuple[str, ...]] = {
    'idcontrato': ('contrato', 'id_contrato', 'numero_contrato'),
    'idcliente': ('id_cliente', 'cliente_id'),
    'cliente': ('nome', 'nome_cliente', 'customer_name'),
    'cliente1': ('cliente', 'nome', 'nome_cliente'),
    'cliente2': ('cliente2_nome', 'segundo_nome'),
    'provedor': ('nome_provedor', 'razao_social'),
    # vencimento ≠ vencimento_original (datas diferentes no SGP)
    'vencimento': ('vencimento_br', 'data_vencimento', 'data_vencimento_atualizada'),
    'vencimento_original': ('vencimento_original_br', 'data_vencimento_original'),
    'titulo': ('titulo_doc', 'numero_titulo', 'num_titulo', 'fatura_id'),
    'valor': ('valor_titulo', 'valor_boleto'),
    'valor_desc': ('valor_com_desconto', 'valor_atualizado'),
    'link': ('documento_url', 'url_boleto', 'url_pagamento'),
    'link_pix': ('linkpix', 'url_pix'),
    'data_aviso': ('data_envio', 'data_aviso_envio'),
    'link_cobranca': ('link_cobranca_url',),
    'link_contato_email_inscricoes': ('link_email_inscricoes',),
    'link_contato_sms_inscricoes': ('link_sms_inscricoes',),
    'linhadigitavel': (
        'linha_digitavel', 'linha_digitavel_boleto', 'codigo_barras', 'codigobarras',
        'digitable_line',
    ),
    'link_pix_html': ('link_pix_interativo',),
    'codigopix': ('codigo_pix', 'pix', 'codigoPix'),
    'codigo_pix': ('codigopix', 'pix', 'codigo_pix', 'codigoPix'),
    'documento_url': ('link', 'link_cobranca', 'link_pix_html', 'documento', 'url_boleto'),
    'button_url': (
        'url_botao', 'button_param', 'url_param', 'validacao_id', 'link_validacao',
        'id_validacao', 'parametro_botao',
    ),
    'celular': ('to', 'telefone', 'phone', 'numero', 'whatsapp'),
}

# Chave SGP por tipo de slot — só pelo texto ao redor de {{n}}, nunca pelo número N.
# {{2}} ou {{3}} não significam data/valor por si só.
SGP_KEY_BY_SLOT: Dict[str, str] = {
    'name': 'cliente1',
    'date_original': 'vencimento_original',
    'date_updated': 'vencimento',
    'date': 'vencimento',
    'money': 'valor',
    'title': 'titulo',
    'provider': 'provedor',
}

# Mantido vazio de propósito: mapeamento por posição (var_2→valor, var_3→data) foi removido.
SGP_VAR_INDEX_FALLBACK: Dict[str, Tuple[str, ...]] = {}


def _strip_accents_simple(text: str) -> str:
    import unicodedata
    norm = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in norm if not unicodedata.combining(c))


def classify_meta_var_slot(body_text: str, var_index: int) -> str:
    """
    Infere o tipo semântico de {{n}} só pelo texto imediatamente ao redor.
    O número N nunca define o tipo ({{2}}/{{3}} não são “sempre data”).

    O contexto é o segmento entre a variável anterior e a próxima (na mesma linha),
    para um rótulo não contaminar outro {{n}} na mesma frase.
    """
    marker = f'{{{{{var_index}}}}}'
    text = body_text or ''
    pos = text.find(marker)
    if pos < 0:
        return 'generic'

    line_start = text.rfind('\n', 0, pos) + 1
    line_end = text.find('\n', pos)
    if line_end < 0:
        line_end = len(text)

    # Início do segmento: após o {{n}} anterior na mesma linha (senão início da linha)
    seg_start = line_start
    for m in _META_VAR_RE.finditer(text[line_start:pos]):
        seg_start = line_start + m.end()

    # Fim do segmento: antes do próximo {{n}} na mesma linha (senão fim da linha)
    seg_end = line_end
    m_next = _META_VAR_RE.search(text[pos + len(marker):line_end])
    if m_next:
        seg_end = pos + len(marker) + m_next.start()

    # Só o texto ANTES de {{n}} (rótulo). Ignora o que vem depois para não
    # misturar “fatura {{2}} no valor de {{3}}” — cada slot usa seu próprio prefixo.
    before = _strip_accents_simple(text[seg_start:pos]).lower().strip()
    after = _strip_accents_simple(text[pos + len(marker):seg_end]).lower().strip()

    _DATE = (
        r'vence\s+hoje|vence\s+em|pagamento\s+ate|valido\s+para\s+pagamento\s+ate|'
        r'vencimento|venceu|venc\.|data\s+de\s+vencimento'
    )
    _DATE_ORIGINAL = r'vencimento\s+original|venc\.?\s*original|original\s+em|data\s+original'
    _DATE_UPDATED = (
        r'vencimento\s+atualizado|atualizado\s+para|novo\s+vencimento|'
        r'vencimento\s+do\s+boleto|boleto\s+com\s+o\s+vencimento'
    )

    if re.search(_DATE_ORIGINAL, before):
        return 'date_original'
    if re.search(_DATE_UPDATED, before):
        return 'date_updated'
    if re.search(_DATE, before):
        return 'date'
    if re.search(r'valor\s+original|(?<![a-z])valor(?![a-z])|r\$|amount|total|no\s+valor\s+de', before):
        return 'money'
    # R$ logo após {{n}} (ex.: {{3}} ) — reforço mínimo, sem ler a frase seguinte
    if re.match(r'^[\s]*r\$', after):
        return 'money'
    if re.search(r'ol[aá]|sr\(|sra|(?<![a-z])nome(?![a-z])|cliente|prezado', before):
        return 'name'
    if re.search(r'titulo|fatura|contrato|referencia|charge|documento', before):
        return 'title'
    if re.search(r'provedor|equipe\s+d[ao]', before):
        return 'provider'
    return 'generic'


def infer_sgp_key_for_meta_var(body_text: str, var_index: int) -> Optional[str]:
    """
    Chave SGP recomendada para {{n}} só pelo contexto do template.
    Retorna None se o texto ao redor não indicar o tipo (não chuta pelo número N).
    """
    slot = classify_meta_var_slot(body_text, var_index)
    return SGP_KEY_BY_SLOT.get(slot)


def get_payload_sgp_value(payload: Dict[str, Any], sgp_key: str) -> Any:
    """Lê variável SGP do payload (chave exata, minúscula ou alias). Não interpreta var_N por posição."""
    if not payload or not sgp_key:
        return None
    key_map = {str(k).lower(): k for k in payload.keys() if k is not None}
    candidates: List[str] = [sgp_key]
    # Aliases semânticos (vencimento_original → data_vencimento_original), nunca var_2→valor
    if not str(sgp_key).startswith('var_'):
        candidates.extend(SGP_PAYLOAD_ALIASES.get(sgp_key, ()))
    seen = set()
    for candidate in candidates:
        c = str(candidate).lower()
        if c in seen:
            continue
        seen.add(c)
        actual = key_map.get(c)
        if actual is None:
            continue
        val = payload.get(actual)
        if val is not None and str(val).strip() != '' and '{' not in str(val):
            return val
    return None


def list_sgp_variable_catalog() -> List[Dict[str, str]]:
    """Catálogo completo de variáveis SGP para UI e documentação de disparo."""
    return [{'key': k, 'label': label} for k, label in EXTERNAL_BILLING_VARIABLES]


def add_order_details_technical_fields(
    mensagem_config: Dict[str, Any],
    mapped_keys: set,
) -> None:
    """
    Campos extras só para PIX/boleto/PDF (order_details), quando não estão no corpo do template.
    O provedor escolhe as variáveis do texto em {mensagem}; aqui não listamos todas as do SGP.
    """
    if 'codigopix' not in mapped_keys and 'codigo_pix' not in mensagem_config:
        mensagem_config['codigo_pix'] = '{codigopix}'
    if 'titulo' not in mapped_keys:
        mensagem_config['titulo'] = '{titulo}'
    if 'linhadigitavel' not in mapped_keys:
        mensagem_config['linhadigitavel'] = '{linhadigitavel}'
    if 'valor' not in mapped_keys:
        mensagem_config['valor'] = '{valor}'


def _generate_token() -> str:
    return f'{TOKEN_PREFIX}{secrets.token_urlsafe(32)}'


def get_provedor_webhook_token(provedor) -> Optional[str]:
    token = (getattr(provedor, 'sgp_webhook_token', None) or '').strip()
    return token or None


def generate_provedor_webhook_token(provedor) -> str:
    from core.models import Provedor

    for _ in range(12):
        candidate = _generate_token()
        if not Provedor.objects.filter(sgp_webhook_token=candidate).exclude(pk=provedor.pk).exists():
            provedor.sgp_webhook_token = candidate
            provedor.save(update_fields=['sgp_webhook_token', 'updated_at'])
            return candidate
    raise RuntimeError('Não foi possível gerar token único para webhook de disparos')


def inbound_webhook_base_url(request=None) -> str:
    if request is not None:
        return request.build_absolute_uri(INBOUND_WEBHOOK_PATH)
    base = (
        getattr(settings, 'APP_BASE_URL', None)
        or getattr(settings, 'API_BASE_URL', None)
        or ''
    ).rstrip('/')
    if base:
        return f'{base}{INBOUND_WEBHOOK_PATH}'
    return INBOUND_WEBHOOK_PATH


def extract_meta_var_indices(text: str) -> List[int]:
    """Índices {{n}} na ordem de aparição (sem repetir)."""
    ordered: List[int] = []
    seen = set()
    for m in _META_VAR_RE.finditer(text or ''):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def meta_index_to_sgp_key(index: int, body_text: Optional[str] = None) -> str:
    """Cada {{n}} do template Meta corresponde a {var_n} no JSON do SGP."""
    if body_text:
        return build_meta_to_sgp_map(body_text).get(index, f'var_{index}')
    return f'var_{index}'


def build_meta_to_sgp_map(body_text: str) -> Dict[int, str]:
    """
    Mapeia {{1}}, {{2}}… do template Meta para var_1, var_2… no SGP.
    O provedor associa cada var_N às variáveis internas do SGP no modelo de cobrança.
    """
    return {n: f'var_{n}' for n in extract_meta_var_indices(body_text or '')}


def convert_meta_body_to_sgp(body_text: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Mantém o corpo do template Meta ({{1}}, {{2}}…) no JSON exportado.
    O provedor edita o JSON no SGP e associa às variáveis internas dele.
    """
    if not (body_text or '').strip():
        return '', []

    mapping: List[Dict[str, str]] = []
    for n in extract_meta_var_indices(body_text):
        meta_ph = f'{{{{{n}}}}}'
        mapping.append({
            'meta': meta_ph,
            'sgp': meta_ph,
            'sgp_key': str(n),
        })
    return body_text.strip(), mapping


def _body_text_from_template(template: Dict[str, Any]) -> str:
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() == 'BODY':
            return (comp.get('text') or '').strip()
    return ''


_PROVEDOR_PLACEHOLDER_NOME_RE = re.compile(r'^Provedor\s+\d+\s*$', re.I)


def _footer_text_from_template(template: Optional[Dict[str, Any]]) -> str:
    """Texto do rodapé definido no template aprovado na Meta (ex.: JTNET)."""
    if not template:
        return ''
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() == 'FOOTER':
            return (comp.get('text') or '').strip()
    return ''


def resolve_merchant_display_name(
    provedor,
    template_def: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Nome exibido no rodapé / merchant_name do PIX.
    Prioriza o rodapé do template Meta; depois o Nome do Provedor (`nome`);
    em seguida `company` (Asaas). Evita placeholder «Provedor 7» do cadastro automático.
    """
    footer = _footer_text_from_template(template_def)
    if footer:
        return footer[:60]
    if provedor:
        for attr in ('nome', 'company'):
            val = (getattr(provedor, attr, None) or '').strip()
            if val and not _PROVEDOR_PLACEHOLDER_NOME_RE.match(val):
                return val[:60]
    return 'Nio Chat'


def template_has_document_header(template: Dict[str, Any]) -> bool:
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() == 'HEADER':
            if str(comp.get('format', '')).upper() == 'DOCUMENT':
                return True
    return False


def template_has_order_details_button(template: Dict[str, Any]) -> bool:
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() != 'BUTTONS':
            continue
        for btn in comp.get('buttons') or []:
            if str(btn.get('type', '')).upper() in ('ORDER_DETAILS', 'PAYMENT_REQUEST'):
                return True
    return False


def template_has_url_button_txt_mode(template: Dict[str, Any]) -> bool:
    """
    Detecta se o template (enviado pela UI) marcou o modo TXT (?txt=1) para botão URL.
    Esse campo é interno do Niohub e não é enviado à Meta (é removido no create_message_template).
    """
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() != 'BUTTONS':
            continue
        for btn in comp.get('buttons') or []:
            if str(btn.get('type', '')).upper() == 'URL' and bool(btn.get('_niohub_txt_mode')):
                return True
    return False


def template_dynamic_url_buttons(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Botões URL do template que usam variável dinâmica {{1}} (ou têm example da Meta)."""
    out: List[Dict[str, Any]] = []
    for comp in template.get('components') or []:
        if str(comp.get('type', '')).upper() != 'BUTTONS':
            continue
        for btn in comp.get('buttons') or []:
            if str(btn.get('type', '')).upper() != 'URL':
                continue
            url = str(btn.get('url') or '')
            has_var = bool(re.search(r'\{\{\s*1\s*\}\}', url))
            has_example = bool(btn.get('example'))
            # Meta: botão dinâmico traz {{1}} e/ou example na listagem
            if has_var or has_example:
                out.append(btn)
    return out


def template_has_dynamic_url_button(template: Dict[str, Any]) -> bool:
    return bool(template_dynamic_url_buttons(template))


def build_external_dispatch_config(
    provedor,
    canal,
    template: Dict[str, Any],
    request=None,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, List[Dict[str, str]]]:
    """
    Retorna dois JSONs separados (como o SGP exige):
    - gateway_config: conexão Niohub (campo Config do gateway HTTP Genérico / Genérica)
    - mensagem_config: texto e variáveis da mensagem de cobrança no SGP
    """
    token = get_provedor_webhook_token(provedor)
    if not token:
        raise ValueError(
            'Token de webhook não configurado. Gere o token em Integrações antes de exportar o código.'
        )

    query = urlencode({
        'provider_id': str(provedor.id),
        'provider_token': token,
        'canal_id': str(canal.id),
    })
    webhook_url = f'{inbound_webhook_base_url(request)}?{query}'

    # 1) Gateway — só comunicação com o Niohub (sem corpo da mensagem)
    gateway_config: Dict[str, Any] = {
        'url': webhook_url,
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/json',
        },
    }

    body_text = _body_text_from_template(template)
    mensagem_sgp, var_mapping = convert_meta_body_to_sgp(body_text)

    if not mensagem_sgp:
        raise ValueError('Template sem corpo (BODY) ou sem texto para mapear variáveis.')

    # 2) Mensagem — o que o provedor cola no modelo de cobrança do SGP
    # (telefone/celular não entra: o SGP já envia o número do cliente no disparo)
    mensagem_config: Dict[str, Any] = {
        'mensagem': mensagem_sgp,
        '_niohub_template': {
            'template_name': template.get('name') or '',
            'template_language': template.get('language') or 'pt_BR',
            'canal_id': canal.id,
        },
    }

    if template_has_url_button_txt_mode(template):
        mensagem_config['_niohub_template']['url_txt_mode'] = True

    if template_has_document_header(template):
        mensagem_config['documento_url'] = '{link}'

    # Botão URL dinâmico ({{1}} no final da URL do template Meta)
    if template_has_dynamic_url_button(template):
        # SGP substitui o placeholder pelo ID/sufixo ou pela URL completa
        mensagem_config['button_url'] = '{button_url}'

    mapped_keys = {m['sgp_key'] for m in var_mapping}
    if template_has_order_details_button(template):
        add_order_details_technical_fields(mensagem_config, mapped_keys)

    return gateway_config, mensagem_config, token, var_mapping


build_sgp_dispatch_config = build_external_dispatch_config


def config_to_json_string(config: Dict[str, Any]) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False)


def dispatch_config_hints(template: Dict[str, Any], var_mapping: List[Dict[str, str]]) -> List[str]:
    hints = [
        'No SGP são dois passos: (1) cole o JSON do Gateway na configuração do gateway HTTP Genérico; '
        '(2) cole o JSON da Mensagem no modelo de cobrança do SGP e substitua os placeholders pelas '
        'variáveis internas do SGP (ex.: {cliente1}, {valor}, {codigopix}).',
        'O JSON da mensagem mantém {{1}}, {{2}}… iguais ao template Meta (sem var_N nem datas extras). '
        'No disparo, o Niohub preenche cada {{n}} pelo rótulo do BODY Meta e pelos campos que o SGP enviar '
        '(cliente, vencimento, vencimento_original, valor…), sem associar o número {{2}}/{{3}} a um tipo fixo.',
        'O webhook aceita GET e POST. Prefira POST: o SGP envia o JSON no body (telefone em to). '
        'Sem template no _niohub_template: envia texto livre. Com codigopix: cobrança interativa.',
    ]
    if var_mapping:
        nums = ', '.join(m['meta'] for m in var_mapping)
        hints.append(f'Variáveis do corpo do template Meta: {nums}.')
    if template_has_document_header(template):
        hints.append(
            'PDF no cabeçalho: inclua documento_url (ou link) no JSON — no SGP use a variável da URL do boleto. '
            'O Niohub acrescenta /.pdf na URL para a Meta quando necessário.'
        )
    if template_has_dynamic_url_button(template):
        hints.append(
            'Botão com URL dinâmica: o campo button_url no JSON alimenta o {{1}} do botão do template. '
            'No SGP, use o ID/sufixo (ex.: uuid ou uuid/print/assinado) ou a URL completa; '
            'o Niohub remove a parte fixa da URL do template e envia o restante à Meta. '
            'A URL fixa do template na Meta precisa ser o prefixo real do link (não use /s/ se o '
            'documento está em /public/...). Aliases: url_botao, button_param, validacao_id, link_validacao.'
        )
    if template_has_order_details_button(template):
        hints.append(
            'Botão pagar: no JSON há exemplos codigo_pix, valor, titulo, linhadigitavel — '
            'troque no SGP pelas variáveis internas equivalentes.'
        )
    hints.append(
        'Catálogo abaixo: referência de nomes que o SGP costuma usar; '
        'você escolhe quais incluir no seu JSON de disparo.'
    )
    return hints


def resolve_provedor_from_webhook(provider_id: Optional[str], provider_token: Optional[str]):
    from core.models import Provedor

    if not provider_token:
        return None, 'provider_token ausente'
    try:
        provedor = Provedor.objects.get(sgp_webhook_token=provider_token, is_active=True)
    except Provedor.DoesNotExist:
        return None, 'Token inválido ou provedor inativo'

    if provider_id is not None and str(provider_id).strip() != '':
        if str(provedor.id) != str(provider_id).strip():
            return None, 'provider_id não corresponde ao token'

    return provedor, None
