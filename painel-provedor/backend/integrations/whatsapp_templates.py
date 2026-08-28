"""
Funções para gerenciar modelos de mensagem do WhatsApp Business
"""
import re
import requests
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
from core.models import Canal
from integrations.meta_oauth import GRAPH_API_VERSION, PHONE_NUMBERS_API_VERSION
from integrations.whatsapp_cloud_send import translate_whatsapp_error

logger = logging.getLogger(__name__)

_VAR_PLACEHOLDER_RE = re.compile(r'\{\{(\d+)\}\}')
# Meta: texto fixo na criação de template ORDER_DETAILS (contas BR).
META_ORDER_DETAILS_BUTTON_TEXT = 'Copy Pix code'
_MIN_TRAILING_CHARS_AFTER_LAST_VAR = 8
_DEFAULT_TRAIL_OUT = 'Para sua comodidade, anexamos uma cópia da sua fatura.'
_META_TEMPLATE_NAME_MAX_LEN = 512
# Domínios de placeholder que a Meta costuma bloquear na revisão (erro 368).
_META_FLAGGED_URL_HOSTS = (
    'exemplo.com',
    'example.org',
    'seudominio.com',
    'seudominio.com.br',
    'teste.com',
    'dominio.com.br',
)
_META_URL_EXAMPLE_SUFFIX = 'sample-receipt-12345'


def _host_is_flagged_for_meta(host: str) -> bool:
    host = (host or '').lower()
    return any(host == h or host.endswith(f'.{h}') for h in _META_FLAGGED_URL_HOSTS)


def sanitize_template_button_url(url: str) -> str:
    """Substitui domínios de exemplo que a Meta rejeita (código 368) e normaliza {{1}}."""
    raw = (url or '').strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw if '://' in raw else f'https://{raw}')
        if parsed.hostname and _host_is_flagged_for_meta(parsed.hostname):
            parsed = parsed._replace(netloc='www.example.com')
            raw = urlunparse(parsed)
    except Exception:
        pass
    raw = (
        raw.replace('://exemplo.com', '://www.example.com')
        .replace('://www.exemplo.com', '://www.example.com')
        .replace('://seudominio.com.br', '://www.example.com')
        .replace('://seudominio.com', '://www.example.com')
    )
    # Meta: variável do botão URL deve ser o último token — cortar qualquer coisa após {{1}}
    raw = re.sub(r'\{\{\s*1\s*\}\}', '{{1}}', raw)
    idx = raw.find('{{1}}')
    if idx >= 0:
        raw = raw[: idx + len('{{1}}')]
    return raw


def build_url_button_example_urls(url: str) -> List[str]:
    base = sanitize_template_button_url(url)
    if '{{1}}' in base:
        sample = base.replace('{{1}}', 'e988ed73-c16e-4c3f-96ad-3db2e10d9631')
        return [sample]
    return [base]


def finalize_template_name_for_canal(name: str, canal: Canal) -> str:
    """
    Anexa sufixo _p{provedor_id} ao nome do template quando o canal tem provedor,
    para identificar o provedor no gerenciador da Meta (vários provedores / mesmo WABA).
    """
    base = (name or '').strip()
    pid = getattr(canal, 'provedor_id', None)
    if pid is None:
        return base
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return base
    suffix = f'_p{pid_int}'
    if base.endswith(suffix):
        return base
    combined = f'{base}{suffix}'
    if len(combined) > _META_TEMPLATE_NAME_MAX_LEN:
        room = _META_TEMPLATE_NAME_MAX_LEN - len(suffix)
        base = base[: max(0, room)].rstrip('_')
        combined = f'{base}{suffix}'
    return combined


def normalize_body_text_for_meta(text: str) -> Tuple[str, List[str]]:
    """
    Ajusta o corpo do template às regras da Meta (Leading/Trailing Params, 2388299).
    Retorna (texto_normalizado, avisos em português).
    """
    warnings: List[str] = []
    text = (text or '').strip()
    if not text:
        return text, warnings

    matches = list(_VAR_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return text, warnings

    first = matches[0]
    prefix = text[: first.start()].strip()

    # Só altera se a variável for o primeiro caractere (modelos "Olá, {{1}}." são aceitos).
    if first.start() == 0 or not prefix:
        text = f'Olá, {text[first.start():].lstrip()}'
        warnings.append('Saudação adicionada antes da primeira variável.')
        matches = list(_VAR_PLACEHOLDER_RE.finditer(text))

    last = matches[-1]
    suffix = text[last.end() :].strip()
    meaningful_suffix = re.sub(r'^[\s.,;:!?\-—]+|[\s.,;:!?\-—]+$', '', suffix)
    if not meaningful_suffix or len(meaningful_suffix) < _MIN_TRAILING_CHARS_AFTER_LAST_VAR:
        text = f'{text[: last.end()].rstrip()}. {_DEFAULT_TRAIL_OUT}'
        warnings.append(
            'Texto final adicionado após a última variável (exigência da Meta).'
        )

    return text.strip(), warnings


def normalize_template_buttons_for_meta(buttons: List[Dict]) -> List[Dict]:
    """
    Na criação de template (POST message_templates), a Meta aceita ORDER_DETAILS
    com apenas texto — não PAYMENT_REQUEST nem payment_setting (isso é no envio).
    Apenas um botão ORDER_DETAILS por template (padrão das contas BR).
    """
    if not buttons:
        return buttons

    order_labels: List[str] = []
    cleaned: List[Dict] = []

    for btn in buttons:
        btype = (btn.get('type') or '').upper()
        if btype in ('PAYMENT_REQUEST', 'ORDER_DETAILS'):
            label = (btn.get('text') or '').strip()
            if label:
                order_labels.append(label)
            continue
        b = {k: v for k, v in btn.items() if k != 'payment_setting'}
        cleaned.append(b)

    if order_labels:
        if len(order_labels) > 1:
            logger.info(
                '[whatsapp_templates] Vários botões de pagamento no formulário; '
                'template Meta usa um único ORDER_DETAILS (%s). Boleto no envio.',
                META_ORDER_DETAILS_BUTTON_TEXT,
            )
        cleaned.append({
            'type': 'ORDER_DETAILS',
            'text': META_ORDER_DETAILS_BUTTON_TEXT,
        })

    return cleaned


def upload_media_to_meta(canal: Canal, file_obj) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Faz o upload de um arquivo para a Meta e retorna o h_handle.
    Documentação: https://developers.facebook.com/docs/graph-api/guides/upload-api/
    """
    try:
        API_VERSION = "v24.0" # Sincronizado com meta_oauth
        from integrations.meta_oauth import META_APP_ID
        
        # 1. Iniciar Sessão de Upload
        url_session = f"https://graph.facebook.com/{API_VERSION}/{META_APP_ID}/uploads"
        params = {
            "file_length": file_obj.size,
            "file_type": file_obj.content_type,
            "access_token": canal.token
        }
        
        resp_session = requests.post(url_session, params=params)
        if not resp_session.ok:
            logger.error(f"Erro ao iniciar sessão de upload: {resp_session.text}")
            return False, None, f"Erro ao iniciar sessão de upload: {resp_session.text}"
        
        session_id = resp_session.json().get('id')
        
        # 2. Upload do Binário
        url_upload = f"https://graph.facebook.com/{API_VERSION}/{session_id}"
        headers = {
            "Authorization": f"OAuth {canal.token}",
            "file_offset": "0"
        }
        
        # Ler conteúdo do arquivo
        file_obj.seek(0)
        file_content = file_obj.read()
        
        resp_upload = requests.post(url_upload, headers=headers, data=file_content)
        if not resp_upload.ok:
            logger.error(f"Erro no upload do binário: {resp_upload.text}")
            return False, None, f"Erro no upload do binário: {resp_upload.text}"
            
        h_handle = resp_upload.json().get('h')
        return True, h_handle, None
        
    except Exception as e:
        logger.exception("Exceção no upload de mídia")
        return False, None, str(e)



def list_message_templates(canal: Canal, limit: int = 50) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
    """
    Lista todos os modelos de mensagem de uma conta WhatsApp Business.
    
    Args:
        canal: Objeto Canal com waba_id e token configurados
        limit: Número máximo de modelos a retornar (padrão: 50)
    
    Returns:
        tuple: (success: bool, templates: Optional[List[Dict]], error: Optional[str])
    """
    try:
        if not canal.waba_id:
            return False, None, "waba_id não configurado no canal"
        
        if not canal.token:
            return False, None, "token não configurado no canal"
        
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.waba_id}/message_templates"
        
        headers = {
            "Authorization": f"Bearer {canal.token}"
        }
        
        # Campos solicitados conforme documentação da Meta
        params = {
            "fields": "language,name,rejected_reason,status,category,sub_category,last_updated_time,components,quality_score",
            "limit": limit
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            templates = data.get('data', [])
            return True, templates, None
        else:
            error_data = response.json() if response.content else {}
            logger.error(f"Erro ao listar modelos: {response.text}")
            error_info = error_data.get('error', {})
            error_code = error_info.get('code')
            error_subcode = error_info.get('error_subcode')
            error_message = error_info.get('message', f'Erro {response.status_code}')
            error_details = error_info.get('error_data', {}).get('details', '')
            
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            logger.error(f"Erro ao listar modelos: {translated_error}")
            return False, None, translated_error
            
    except Exception as e:
        logger.exception("Exceção ao listar modelos")
        return False, None, str(e)


def get_template(canal: Canal, template_id: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Obtém detalhes de um modelo específico.
    
    Args:
        canal: Objeto Canal com token configurado
        template_id: ID do modelo
    
    Returns:
        tuple: (success: bool, template: Optional[Dict], error: Optional[str])
    """
    try:
        if not canal.token:
            return False, None, "token não configurado no canal"
        
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{template_id}"
        
        headers = {
            "Authorization": f"Bearer {canal.token}"
        }
        
        params = {
            "fields": "id,name,category,language,status,components"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            template = response.json()
            return True, template, None
        else:
            error_data = response.json() if response.content else {}
            logger.error(f"Erro ao obter modelo: {response.text}")
            error_info = error_data.get('error', {})
            error_code = error_info.get('code')
            error_subcode = error_info.get('error_subcode')
            error_message = error_info.get('message', f'Erro {response.status_code}')
            error_details = error_info.get('error_data', {}).get('details', '')
            
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            logger.error(f"Erro ao obter modelo: {translated_error}")
            return False, None, translated_error
            
    except Exception as e:
        logger.exception("Exceção ao obter modelo")
        return False, None, str(e)


def create_message_template(
    canal: Canal,
    name: str,
    category: str,
    language: str,
    components: List[Dict],
    parameter_format: str = "positional",
    media_file = None
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Cria um novo modelo de mensagem.
    
    Args:
        canal: Objeto Canal com waba_id e token configurados
        name: Nome base do modelo; com provedor no canal, o envio usa nome_sufixo _p{provedor_id}
        category: Categoria do modelo (AUTHENTICATION, MARKETING, UTILITY)
        language: Código do idioma (ex: pt_BR, en_US)
        components: Lista de componentes do modelo
        parameter_format: Formato dos parâmetros ("named" ou "positional")
    
    Returns:
        tuple: (success: bool, template: Optional[Dict], error: Optional[str])
    """
    try:
        # 1. Limpar nome do template (apenas minúsculas e números, sem acentos ou espaços)
        # O processamento acima é a lógica esperada no frontend.
        
        if not canal.waba_id:
            return False, None, "waba_id não configurado no canal"
        
        if not canal.token:
            return False, None, "token não configurado no canal"

        name = finalize_template_name_for_canal(name, canal)

        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.waba_id}/message_templates"
        
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        # Limpeza e validação básica dos componentes
        cleaned_components = []
        
        # Se houver arquivo, fazer upload e injetar o handle no componente HEADER
        media_handle = None
        if media_file:
            success_up, handle, err_up = upload_media_to_meta(canal, media_file)
            if success_up:
                media_handle = handle
            else:
                logger.error(f"Falha ao processar upload de mídia para template: {err_up}")

        for comp in components:
            c = comp.copy()
            c_type = c.get('type')
            header_fmt = str(c.get('format') or '').upper()

            # Normalizar chaves do "example" (evita quebras de linha/espacos, ex: "\nbody_text")
            example = c.get('example')
            if isinstance(example, dict) and example:
                normalized_example = {}
                for k, v in example.items():
                    if not isinstance(k, str):
                        continue
                    ks = k.strip()
                    if not ks:
                        continue
                    normalized_example[ks] = v

                # Compatibilidade: se veio com key errada (ex: "\nbody_text"), corrigir
                if 'body_text' not in normalized_example:
                    for k in list(normalized_example.keys()):
                        if isinstance(k, str) and 'body_text' in k:
                            normalized_example['body_text'] = normalized_example.pop(k)
                            break

                c['example'] = normalized_example

            # Cabeçalho de mídia exige upload de exemplo (handle Meta), não URL pública
            if c_type == 'HEADER' and header_fmt in ('IMAGE', 'VIDEO', 'DOCUMENT'):
                if media_handle:
                    c['example'] = {'header_handle': [media_handle]}
                else:
                    c.pop('example', None)
                    label = 'PDF' if header_fmt == 'DOCUMENT' else header_fmt.lower()
                    return (
                        False,
                        None,
                        f'Para cabeçalho {label}, envie um arquivo de exemplo '
                        f'({label}) no formulário antes de criar o template.',
                    )
            
            # 1. Limpar HEADER (não suporta formatação ou emojis em alguns casos)
            if c_type == 'HEADER' and c.get('format') == 'TEXT':
                text = c.get('text', '')
                # Remover bold (*), italic (_), strikethrough (~)
                clean_text = text.replace('*', '').replace('_', '').replace('~', '')
                # Remover emojis do HEADER (causam erro 100/2388072 frequentemente)
                import re
                clean_text = ''.join(char for char in clean_text if ord(char) < 0x10000)
                c['text'] = clean_text.strip()
            
            # 2. BODY — normalizar posição das variáveis (Meta não aceita no início/fim)
            if c_type == 'BODY':
                body_text = (c.get('text') or '').strip()
                if body_text:
                    normalized, norm_warnings = normalize_body_text_for_meta(body_text)
                    if normalized != body_text:
                        c['text'] = normalized
                        for w in norm_warnings:
                            logger.info('[whatsapp_templates] BODY normalizado: %s', w)

                    # 2b. BODY — renumerar variáveis para sequência iniciando em {{1}}
                    # (Meta exige {{1}}, {{2}}, {{3}}... sem buracos no BODY)
                    current_text = (c.get('text') or '').strip()
                    matches = list(_VAR_PLACEHOLDER_RE.finditer(current_text))
                    if matches:
                        unique_nums = []
                        for m in matches:
                            try:
                                unique_nums.append(int(m.group(1)))
                            except Exception:
                                continue
                        unique_nums = sorted(set(unique_nums))
                        if unique_nums and unique_nums != list(range(1, len(unique_nums) + 1)):
                            mapping = {old: i + 1 for i, old in enumerate(unique_nums)}
                            # Usar regex com função para evitar colisões (ex: {{6}}->{{5}} e depois {{5}}->{{4}})
                            def _renumber_var(match):
                                try:
                                    old = int(match.group(1))
                                except Exception:
                                    return match.group(0)
                                new = mapping.get(old, old)
                                return f'{{{{{new}}}}}'

                            new_text = _VAR_PLACEHOLDER_RE.sub(_renumber_var, current_text)
                            c['text'] = new_text
                            logger.info(
                                '[whatsapp_templates] BODY renumerado: %s -> %s',
                                unique_nums,
                                list(range(1, len(unique_nums) + 1)),
                            )
            
            # 3. BUTTONS — ORDER_DETAILS na criação (não PAYMENT_REQUEST)
            if c_type == 'BUTTONS':
                buttons = c.get('buttons', [])
                cleaned_buttons = []
                for btn in buttons:
                    b = btn.copy()
                    # Remover chaves internas do Niohub (não fazem parte do payload da Meta)
                    for k in list(b.keys()):
                        if isinstance(k, str) and k.startswith('_niohub_'):
                            b.pop(k, None)
                    if 'text' in b:
                        b['text'] = b['text'].strip()
                    if b.get('type') == 'URL':
                        raw_url = b.get('url', '')
                        btn_url = sanitize_template_button_url(raw_url)
                        if btn_url != raw_url:
                            logger.info(
                                '[whatsapp_templates] URL do botão ajustada para revisão Meta: %s -> %s',
                                raw_url,
                                btn_url,
                            )
                        b['url'] = btn_url
                        # Respeitar exemplo enviado pela UI quando houver (permite URL de amostra customizada)
                        if b.get('example'):
                            b['example'] = [
                                sanitize_template_button_url(str(ex))
                                for ex in b['example']
                            ]
                        elif '{{1}}' in btn_url:
                            b['example'] = build_url_button_example_urls(btn_url)
                    cleaned_buttons.append(b)
                c['buttons'] = normalize_template_buttons_for_meta(cleaned_buttons)
            
            cleaned_components.append(c)

        payload = {
            "name": name,
            "category": category,
            "language": language,
            "components": cleaned_components
        }
        
        # parameter_format não é um campo oficial do POST de criação de template na Meta,
        # mas pode ser necessário para o nosso controle interno ou se a API Cloud mudar.
        # Por via de dúvida, vamos remover do payload enviado à Meta se não for AUTHENTICATION.
        # Na verdade, a documentação oficial da Meta não lista esse campo no POST de criação.
        
        # Log do payload para debug
        logger.info(f"Criando modelo '{name}' (Categoria: {category})")
        logger.info('[whatsapp_templates] Payload Meta: %s', payload)
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            template = response.json()
            logger.info(
                "[whatsapp_templates] Modelo criado (status inicial Meta): id=%s status=%s",
                template.get('id'),
                template.get('status'),
            )
            return True, template, None
        else:
            error_data = response.json() if response.content else {}
            error_info = error_data.get('error', {})
            error_code = error_info.get('code', response.status_code)
            error_subcode = error_info.get('error_subcode')
            error_message = error_info.get('message', f'Erro {response.status_code}')
            error_user_msg = error_info.get('error_user_msg', '')
            error_details = error_info.get('error_data', {}).get('details', '')
            
            # Mapeamento de subcodes de erro de template da Meta para mensagens claras em português
            TEMPLATE_ERROR_MAP = {
                2388299: (
                    "A variável {{1}} está muito próxima do início da mensagem. "
                    "A Meta exige texto suficiente antes da primeira variável. "
                    "Exemplo correto: 'Seu pagamento está próximo do vencimento. Titular: {{1}}, Valor: {{2}}, Vencimento: {{3}}.' — "
                    "Reescreva o texto para que haja pelo menos uma frase completa antes de {{1}}."
                ),
                2388053: "Nome do template inválido. Use apenas letras minúsculas, números e underscores (ex: aviso_pagamento).",
                2388057: "Categoria inválida. Use UTILITY, MARKETING ou AUTHENTICATION.",
                2388076: "O template com este nome já existe. Escolha um nome diferente.",
                2388072: "O cabeçalho (HEADER) contém caracteres ou formatação inválida (evite emojis e negrito no cabeçalho).",
                2388094: "As variáveis no corpo devem ser numeradas sequencialmente: {{1}}, {{2}}, {{3}}...",
                2388076: "Já existe um template com este nome. Escolha um nome diferente.",
                2388060: "O texto do corpo da mensagem está vazio ou inválido.",
                2388052: "Tipo de botão inválido. Use QUICK_REPLY ou URL.",
                2388087: "O número de variáveis nos exemplos não corresponde às variáveis no texto do template.",
                2388128: (
                    "O botão ORDER_DETAILS deve usar exatamente o texto "
                    f"«{META_ORDER_DETAILS_BUTTON_TEXT}» (exigência da Meta). "
                    "PIX e boleto são configurados no envio da mensagem."
                ),
                2388023: (
                    "A Meta ainda está excluindo uma versão anterior deste template em português (pt_BR). "
                    "Aguarde cerca de 1 minuto e envie de novo, ou use outro nome de template "
                    "(ex.: pagamento_vencimento_v2)."
                ),
                2388273: (
                    "Cabeçalho com documento/imagem/vídeo precisa de arquivo de exemplo. "
                    "Selecione um PDF (documento) ou mídia no formulário e envie novamente."
                ),
                1346003: (
                    "A Meta bloqueou o conteúdo do template (URL ou texto considerado abusivo/spam). "
                    "Use o domínio real do seu provedor no botão de link (evite exemplo.com) e tente outro nome de template."
                ),
            }

            if error_code == 368:
                friendly_error = TEMPLATE_ERROR_MAP.get(
                    1346003,
                    (
                        "A Meta bloqueou o conteúdo na revisão. Troque a URL do botão pelo domínio "
                        "real do seu sistema (recibo/boleto) e evite domínios de exemplo."
                    ),
                )
            elif error_subcode in TEMPLATE_ERROR_MAP:
                friendly_error = TEMPLATE_ERROR_MAP[error_subcode]
            else:
                from integrations.whatsapp_cloud_send import translate_whatsapp_error
                friendly_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
                if error_user_msg:
                    friendly_error = f"{friendly_error} — {error_user_msg}"

            logger.error(f"Erro ao criar modelo: {friendly_error}")
            logger.error(f"Resposta bruta da Meta: {response.text}")
            logger.error(f"Payload enviado: {payload}")
            return False, None, friendly_error
            
    except Exception as e:
        logger.exception("Exceção ao criar modelo")
        return False, None, str(e)


def delete_message_template(canal: Canal, template_id: str) -> Tuple[bool, Optional[str]]:
    """
    Deleta um modelo de mensagem.
    
    Args:
        canal: Objeto Canal com token configurado
        template_id: ID do modelo (formato: {name}:{language})
    
    Returns:
        tuple: (success: bool, error: Optional[str])
    """
    try:
        if not canal.token:
            return False, "token não configurado no canal"
        
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{template_id}"
        
        headers = {
            "Authorization": f"Bearer {canal.token}"
        }
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code == 200:
            return True, None
        else:
            error_data = response.json() if response.content else {}
            error_info = error_data.get('error', {})
            error_code = error_info.get('code')
            error_subcode = error_info.get('error_subcode')
            error_message = error_info.get('message', f'Erro {response.status_code}')
            error_details = error_info.get('error_data', {}).get('details', '')
            
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            logger.error(f"Erro ao deletar modelo: {translated_error}")
            return False, translated_error
            
    except Exception as e:
        logger.exception("Exceção ao deletar modelo")
        return False, str(e)

