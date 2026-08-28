"""
Funções para gerenciar modelos de mensagem do WhatsApp Business
"""
import requests
import logging
from typing import Dict, List, Optional, Tuple
from core.models import Canal
from integrations.meta_oauth import GRAPH_API_VERSION, PHONE_NUMBERS_API_VERSION
from integrations.whatsapp_cloud_send import translate_whatsapp_error

logger = logging.getLogger(__name__)


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
    parameter_format: str = "positional"
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Cria um novo modelo de mensagem.
    
    Args:
        canal: Objeto Canal com waba_id e token configurados
        name: Nome do modelo (máximo 512 caracteres, alfanuméricos minúsculos e sublinhados)
        category: Categoria do modelo (AUTHENTICATION, MARKETING, UTILITY)
        language: Código do idioma (ex: pt_BR, en_US)
        components: Lista de componentes do modelo
        parameter_format: Formato dos parâmetros ("named" ou "positional")
    
    Returns:
        tuple: (success: bool, template: Optional[Dict], error: Optional[str])
    """
    try:
        if not canal.waba_id:
            return False, None, "waba_id não configurado no canal"
        
        if not canal.token:
            return False, None, "token não configurado no canal"
        
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.waba_id}/message_templates"
        
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        # Limpeza e validação básica dos componentes
        cleaned_components = []
        for comp in components:
            c = comp.copy()
            c_type = c.get('type')
            
            # 1. Limpar HEADER (não suporta formatação ou emojis em alguns casos)
            if c_type == 'HEADER' and c.get('format') == 'TEXT':
                text = c.get('text', '')
                # Remover bold (*), italic (_), strikethrough (~)
                clean_text = text.replace('*', '').replace('_', '').replace('~', '')
                # Remover emojis do HEADER (causam erro 100/2388072 frequentemente)
                import re
                clean_text = ''.join(char for char in clean_text if ord(char) < 0x10000)
                c['text'] = clean_text.strip()
            
            # 2. Validar BODY (Manter emojis, Meta aceita no corpo para Utilidade)
            if c_type == 'BODY':
                # No corpo, emojis são permitidos mesmo em UTILITY
                # Mantemos o texto original, apenas garantindo que as variáveis estão corretas
                pass
            
            # 3. Validar BUTTONS
            if c_type == 'BUTTONS':
                buttons = c.get('buttons', [])
                cleaned_buttons = []
                for btn in buttons:
                    b = btn.copy()
                    # WhatsApp não gosta de espaços no final do texto do botão
                    if 'text' in b:
                        b['text'] = b['text'].strip()
                    
                    # Se for URL, garantir que é uma URL válida e tratar variáveis
                    if b.get('type') == 'URL':
                        btn_url = b.get('url', '')
                        # Se tem variável {{1}} mas não tem example, a Meta rejeita
                        if '{{1}}' in btn_url and not b.get('example'):
                            # Tentar extrair um exemplo da URL ou usar o padrão
                            b['example'] = [btn_url.replace('{{1}}', 'exemplo')]
                    
                    cleaned_buttons.append(b)
                c['buttons'] = cleaned_buttons
            
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
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            template = response.json()
            return True, template, None
        else:
            error_data = response.json() if response.content else {}
            error_info = error_data.get('error', {})
            error_code = error_info.get('code', response.status_code)
            error_subcode = error_info.get('error_subcode')
            error_message = error_info.get('message', f'Erro {response.status_code}')
            error_details = error_info.get('error_data', {}).get('details', '')
            
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            logger.error(f"Erro ao criar modelo: {translated_error}")
            logger.error(f"Payload enviado: {payload}")
            return False, None, translated_error
            
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

