"""
Função para enviar mensagens via WhatsApp Cloud API (Oficial)
"""
import requests
import logging
import json
import os
import uuid
import re
from typing import Tuple, Optional, List, Dict, Any
from core.models import Canal
from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
from django.conf import settings

logger = logging.getLogger(__name__)

def translate_whatsapp_error(error_code: int, error_subcode: Optional[int] = None, error_message: str = "", details: str = "") -> str:
    """
    Traduz códigos de erro da API do WhatsApp para português.
    Baseado em: https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes
    
    Args:
        error_code: Código de erro principal
        error_subcode: Subcódigo de erro (opcional)
        error_message: Mensagem de erro original (opcional)
        details: Detalhes adicionais do erro (opcional)
    
    Returns:
        str: Mensagem de erro traduzida em português
    """
    # Erros comuns da API do WhatsApp
    error_translations = {
        # Erros de autenticação e permissão
        0: "Erro desconhecido na API do WhatsApp.",
        1: "Erro interno no servidor do Facebook/WhatsApp. Tente novamente mais tarde.",
        2: "Serviço temporariamente indisponível. Tente novamente em alguns minutos.",
        3: "Recurso não encontrado ou indisponível.",
        190: "Token de acesso expirado ou inválido. Por favor, reconecte o canal WhatsApp.",
        10: "Permissão negada. Verifique se o token tem as permissões necessárias para enviar mensagens.",
        200: "Permissão negada. O token não possui acesso a este recurso ou número de telefone.",
        
        # Erros de rate limiting
        4: "Limite de requisições excedido. O WhatsApp restringiu o envio temporariamente por excesso de velocidade.",
        17: "Muitas requisições ao servidor. Por favor, aguarde antes de tentar novamente.",
        32: "Limite de envio da conta excedido. Verifique seu nível de mensagens (Tiering) no painel da Meta.",
        80007: "Limite de taxa atingido. O número de mensagens enviadas ultrapassa a capacidade atual.",
        
        # Erros de mensagens (Janela de 24h e Destinatário)
        131000: "Número de telefone inválido. Verifique se o número está correto e no formato internacional.",
        131005: "Não foi possível enviar para este número. O destinatário pode não ter WhatsApp.",
        131008: "Mensagem muito longa. Reduza o texto e tente novamente.",
        131009: "A janela de atendimento (24h) está fechada. Este cliente não responde há mais de 24h. Use um Modelo de Mensagem (Template) para retomar o contato.",
        131010: "O destinatário não possui uma conta de WhatsApp ativa.",
        131016: "A mensagem não pôde ser entregue. O número pode estar bloqueado ou indisponível.",
        131021: "O destinatário não pode receber mensagens no momento. Pode ser devido a restrições de privacidade ou bloqueio.",
        131026: "Falha na entrega da mensagem. Tente reenviar mais tarde.",
        131042: "Erro no processamento da mensagem pelo servidor do WhatsApp.",
        131047: "Janela de 24 horas encerrada. Para enviar mensagens após este período, é obrigatório o uso de um Modelo de Mensagem (Template) aprovado.",
        131051: "Tipo de mensagem não suportado pelo destinatário.",
        131052: "Mídia inválida ou formato não suportado. Verifique o arquivo antes de enviar.",
        131053: "Mídia muito grande. O WhatsApp limita o tamanho de arquivos dependendo do tipo.",
        131057: "Falha ao processar o arquivo de mídia. Tente novamente.",
        
        # Erros de template
        132000: "Modelo de mensagem (Template) não encontrado nas configurações.",
        132001: "O Template selecionado ainda não foi aprovado pela Meta.",
        132007: "Erro no formato do Template. Verifique os parâmetros e variáveis.",
        132012: "Número de parâmetros no Template não coincide com o esperado.",
        132015: "Template desativado ou pausado por baixa qualidade.",
        
        # Erros de mídia
        133000: "Falha geral no processamento de mídia.",
        133004: "O arquivo enviado não corresponde ao tipo de mídia declarado.",
        133010: "URL da mídia está inacessível ou inválida.",
        
        # Erros de pagamento e conta
        135000: "Problema com a conta de anúncios ou método de pagamento da Meta Business.",
    }
    
    # Adicionar traduções em massa para faixas se necessário (opcional)
    # Por enquanto os principais já estão no dicionário
    
    # Determinar a mensagem base
    translated_msg = ""
    if error_code in error_translations:
        translated_msg = error_translations[error_code]
    elif error_subcode and error_subcode in error_translations:
        translated_msg = error_translations[error_subcode]
    elif 131000 <= error_code <= 131999:
        translated_msg = "Erro na entrega: O número de destino é inválido ou a janela de 24h está fechada."
    elif 132000 <= error_code <= 132999:
        translated_msg = "Erro no Modelo de Mensagem: Verifique se o template está aprovado e configurado corretamente."
    elif 133000 <= error_code <= 133999:
        translated_msg = "Erro de Mídia: O arquivo enviado possui problemas ou o formato não é aceito."
    else:
        translated_msg = error_message or "Erro durante o processamento da requisição no WhatsApp."

    # Adicionar detalhes se existirem e não estiverem inclusos na mensagem original
    final_msg = translated_msg
    if details and details not in final_msg:
        # Se os detalhes forem técnicos em inglês, podemos tentar simplificar ou apenas anexar
        final_msg = f"{translated_msg} ({details})"
    
    # Se ainda assim não tiver código na mensagem, adicionar para referência técnica
    if str(error_code) not in final_msg:
        final_msg = f"{final_msg} (Código: {error_code})"
        
    return final_msg



def upload_media_to_whatsapp(canal: Canal, file_path: str, media_type: str, mime_type: str) -> Tuple[bool, Optional[str]]:
    """
    Faz upload de mídia para a API do WhatsApp e retorna o media_id.
    
    Args:
        canal: Objeto Canal com token configurado
        file_path: Caminho local do arquivo
        media_type: Tipo de mídia (image, video, audio, document)
        mime_type: Tipo MIME do arquivo (ex: image/jpeg, video/mp4)
    
    Returns:
        tuple: (success: bool, media_id: Optional[str])
    """
    try:
        if not os.path.exists(file_path):
            return False, f"Arquivo não encontrado: {file_path}"
        
        # Endpoint para upload de mídia
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/media"
        
        # Ler o arquivo
        with open(file_path, 'rb') as file:
            files = {
                'file': (os.path.basename(file_path), file, mime_type),
            }
            
            data = {
                'messaging_product': 'whatsapp',
                'type': media_type  # Tipo básico: image, video, audio, document
            }
            
            headers = {
                "Authorization": f"Bearer {canal.token}"
            }
            
            response = requests.post(url, files=files, data=data, headers=headers, timeout=60)
            
            if response.status_code == 200:
                response_data = response.json()
                media_id = response_data.get('id')
                if media_id:
                    logger.info(f"Mídia enviada com sucesso. Media ID: {media_id}")
                    return True, media_id
                else:
                    return False, "Media ID não retornado na resposta"
            else:
                error_msg = response.text
                logger.error(f"Erro ao fazer upload de mídia: {response.status_code} - {error_msg}")
                return False, error_msg
    
    except Exception as e:
        logger.error(f"Exceção ao fazer upload de mídia: {str(e)}")
        return False, str(e)


def send_via_whatsapp_cloud_api(
    conversation,
    content: str,
    message_type: str = 'text',
    file_url: Optional[str] = None,
    file_path: Optional[str] = None,
    file_name: Optional[str] = None,
    mime_type: Optional[str] = None,
    is_voice_message: Optional[bool] = None,
    reply_to_message_id: Optional[str] = None,
    buttons: Optional[List[Dict]] = None,
    order_details: Optional[Dict] = None,
    **kwargs
) -> Tuple[bool, Optional[str]]:
    """
    Envia mensagem via WhatsApp Cloud API (Oficial).
    
    Args:
        conversation: Objeto Conversation
        content: Conteúdo da mensagem
        message_type: Tipo da mensagem ('text', 'image', 'audio', 'video', 'document')
        file_url: URL do arquivo (para tipos de mídia)
        reply_to_message_id: ID da mensagem a responder (opcional)
    
    Returns:
        tuple: (success: bool, response: str ou dict)
    """
    try:
        provedor = conversation.inbox.provedor
        
        # Buscar instancia do canal vinculada a este inbox
        canal = conversation.inbox.get_canal_instance()
        
        if not canal:
            return False, "Canal WhatsApp Oficial não encontrado"
        
        if not canal.token:
            return False, "Token do canal não configurado"
        
        if not canal.phone_number_id:
            return False, "Phone Number ID não configurado"
        
        # Obter número do destinatário do contato
        contact = conversation.contact
        recipient_number = conversation.contact.phone.replace('@s.whatsapp.net', '').replace('@c.us', '')
        
        # Garantir formato com '+' para Meta Cloud API (conforme testes manuais do usuário)
        if not recipient_number.startswith('+'):
            if not recipient_number.startswith('55') and len(recipient_number) <= 11:
                recipient_number = '55' + recipient_number
            recipient_number = '+' + recipient_number
        
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_number
        }
        
        # Adicionar reply_to se fornecido
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        # Montar payload específico por tipo
        if message_type == 'text':
            payload["type"] = "text"
            payload["text"] = {
                "preview_url": False,
                "body": content
            }
        elif message_type == 'image':
            payload["type"] = "image"
            image_data = {}
            
            # Priorizar upload de mídia (recomendado pela Meta)
            if file_path and os.path.exists(file_path):
                # Fazer upload e obter media_id
                upload_success, media_id = upload_media_to_whatsapp(canal, file_path, 'image', mime_type or 'image/jpeg')
                if upload_success and media_id:
                    image_data["id"] = media_id
                else:
                    # Fallback para link se upload falhar
                    if file_url:
                        image_data["link"] = file_url
                    else:
                        return False, f"Erro ao fazer upload de mídia: {media_id}"
            elif file_url:
                # Usar link como fallback (não recomendado)
                image_data["link"] = file_url
            else:
                return False, "file_path ou file_url é obrigatório para imagens"
            
            if content:
                image_data["caption"] = content
            
            payload["image"] = image_data
            
        elif message_type == 'audio' or message_type == 'ptt':
            payload["type"] = "audio"
            audio_data = {}
            
            # Verificar formato do arquivo - Meta aceita apenas: MP3, OGG, AAC, AMR, M4A
            if file_path:
                file_ext = os.path.splitext(file_path)[1].lower()
            elif file_name:
                file_ext = os.path.splitext(file_name)[1].lower()
            else:
                file_ext = None
            
            # Formatos suportados pela Meta
            supported_formats = ['.mp3', '.ogg', '.aac', '.amr', '.m4a']
            if file_ext and file_ext not in supported_formats:
                # Arquivo não suportado - tentar usar como link ou retornar erro
                logger.warning(f"Formato de áudio não suportado pela Meta: {file_ext}. Formatos aceitos: {supported_formats}")
                if file_url:
                    # Tentar usar link como fallback (pode não funcionar)
                    audio_data["link"] = file_url
                    logger.warning(f"Usando link como fallback para formato não suportado: {file_ext}")
                else:
                    return False, f"Formato de áudio não suportado: {file_ext}. Formatos aceitos: MP3, OGG, AAC, AMR, M4A"
            
            # Detectar se é mensagem de voz (arquivo .ogg) ou áudio básico
            # Mensagens de voz devem ser arquivos .ogg codificados com codec OPUS
            if is_voice_message is None:
                # Auto-detectar baseado na extensão do arquivo
                if file_ext:
                    is_voice_message = (file_ext == '.ogg') or (message_type == 'ptt')
                else:
                    is_voice_message = (message_type == 'ptt')
            
            if file_path and os.path.exists(file_path):
                # Determinar MIME type correto para áudio
                detected_mime = mime_type or 'audio/mpeg'
                if not mime_type:
                    mime_map = {
                        '.mp3': 'audio/mpeg',
                        '.ogg': 'audio/ogg',
                        '.aac': 'audio/aac',
                        '.amr': 'audio/amr',
                        '.m4a': 'audio/mp4'
                    }
                    detected_mime = mime_map.get(file_ext, 'audio/mpeg')
                
                logger.info(f"[WhatsAppCloud] Fazendo upload de áudio: formato={file_ext}, mime={detected_mime}, voice={is_voice_message}")
                upload_success, media_id = upload_media_to_whatsapp(canal, file_path, 'audio', detected_mime)
                if upload_success and media_id:
                    audio_data["id"] = media_id
                    logger.info(f"[WhatsAppCloud] Upload de áudio bem-sucedido: media_id={media_id}")
                elif file_url:
                    audio_data["link"] = file_url
                    logger.warning(f"[WhatsAppCloud] Upload falhou, usando link como fallback")
                else:
                    error_msg = f"Erro ao fazer upload de mídia: {media_id}"
                    logger.error(f"[WhatsAppCloud] {error_msg}")
                    return False, error_msg
            elif file_url:
                audio_data["link"] = file_url
                logger.info(f"[WhatsAppCloud] Usando link para áudio: {file_url}")
            else:
                return False, "file_path ou file_url é obrigatório para áudio"
            
            # Adicionar campo "voice" se for mensagem de voz
            # Mensagens de voz são arquivos .ogg codificados com codec OPUS
            if is_voice_message:
                audio_data["voice"] = True
                logger.info(f"[WhatsAppCloud] Áudio configurado como mensagem de voz")
            
            payload["audio"] = audio_data
            
        elif message_type == 'video':
            payload["type"] = "video"
            video_data = {}
            
            # Verificar formato do arquivo - Meta aceita apenas: MP4 e 3GP
            if file_path:
                file_ext = os.path.splitext(file_path)[1].lower()
            elif file_name:
                file_ext = os.path.splitext(file_name)[1].lower()
            else:
                file_ext = None
            
            # Formatos suportados pela Meta para vídeo
            supported_formats = ['.mp4', '.3gp']
            if file_ext and file_ext not in supported_formats:
                logger.warning(f"Formato de vídeo não suportado pela Meta: {file_ext}. Formatos aceitos: {supported_formats}")
                if file_url:
                    # Tentar usar link como fallback (pode não funcionar)
                    video_data["link"] = file_url
                    logger.warning(f"Usando link como fallback para formato não suportado: {file_ext}")
                else:
                    return False, f"Formato de vídeo não suportado: {file_ext}. Formatos aceitos: MP4, 3GP. A Meta requer codec H.264 para vídeo e AAC para áudio."
            
            if file_path and os.path.exists(file_path):
                # Determinar MIME type correto para vídeo
                detected_mime = mime_type or 'video/mp4'
                if not mime_type:
                    mime_map = {
                        '.mp4': 'video/mp4',
                        '.3gp': 'video/3gpp'
                    }
                    detected_mime = mime_map.get(file_ext, 'video/mp4')
                
                logger.info(f"[WhatsAppCloud] Fazendo upload de vídeo: formato={file_ext}, mime={detected_mime}")
                upload_success, media_id = upload_media_to_whatsapp(canal, file_path, 'video', detected_mime)
                if upload_success and media_id:
                    video_data["id"] = media_id
                    logger.info(f"[WhatsAppCloud] Upload de vídeo bem-sucedido: media_id={media_id}")
                elif file_url:
                    video_data["link"] = file_url
                    logger.warning(f"[WhatsAppCloud] Upload falhou, usando link como fallback")
                else:
                    error_msg = f"Erro ao fazer upload de mídia: {media_id}"
                    logger.error(f"[WhatsAppCloud] {error_msg}")
                    return False, error_msg
            elif file_url:
                video_data["link"] = file_url
                logger.info(f"[WhatsAppCloud] Usando link para vídeo: {file_url}")
            else:
                return False, "file_path ou file_url é obrigatório para vídeo"
            
            if content:
                video_data["caption"] = content
            
            payload["video"] = video_data
            
        elif message_type == 'document':
            payload["type"] = "document"
            document_data = {}
            
            if file_path and os.path.exists(file_path):
                upload_success, media_id = upload_media_to_whatsapp(canal, file_path, 'document', mime_type or 'application/pdf')
                if upload_success and media_id:
                    document_data["id"] = media_id
                elif file_url:
                    document_data["link"] = file_url
                else:
                    return False, f"Erro ao fazer upload de mídia: {media_id}"
            elif file_url:
                document_data["link"] = file_url
            else:
                return False, "file_path ou file_url é obrigatório para documento"
            
            # Adicionar filename se fornecido (importante para WhatsApp exibir ícone correto)
            if file_name:
                document_data["filename"] = file_name
            elif file_path:
                # Extrair nome do arquivo do caminho se não fornecido
                document_data["filename"] = os.path.basename(file_path)
            
            # Adicionar caption se fornecido
            if content:
                document_data["caption"] = content
            
            payload["document"] = document_data
        elif message_type == 'order_details' or (message_type == 'interactive' and order_details):
            payload["type"] = "interactive"
            
            # Garantir que payment_settings de PIX contenha os campos obrigatórios 'key' e 'key_type'
            # Se order_details vier incompleto, tentar montar a partir dos campos básicos (Simplificação solicitada pelo usuário)
            if order_details and "payment_settings" not in order_details:
                # Caso o frontend mande apenas campos básicos
                fatura_id = order_details.get("invoice_id")
                valor = order_details.get("amount") or 0
                pix_code = order_details.get("pix_code")
                
                if fatura_id and pix_code:
                    valor_centavos = int(float(valor) * 100)
                    key, key_type = _extract_pix_info_from_code(pix_code)
                    
                    order_details = {
                        "reference_id": f"fat_{fatura_id}",
                        "type": "digital-goods",
                        "payment_type": "br",
                        "payment_settings": [{
                            "type": "pix_dynamic_code",
                            "pix_dynamic_code": {
                                "code": pix_code,
                                "merchant_name": "NIO NET",
                                "key": key,
                                "key_type": key_type
                            }
                        }],
                        "currency": "BRL",
                        "total_amount": {"value": valor_centavos, "offset": 100},
                        "order": {
                            "status": "pending",
                            "items": [{
                                "name": f"Fatura {fatura_id}",
                                "amount": {"value": valor_centavos, "offset": 100},
                                "quantity": 1
                            }],
                            "subtotal": {"value": valor_centavos, "offset": 100}
                        }
                    }

            # Caso ainda venha o objeto completo do frontend, apenas validamos a chave PIX
            elif order_details and "payment_settings" in order_details:
                for setting in order_details.get("payment_settings", []):
                    if setting.get("type") == "pix_dynamic_code":
                        pix_info = setting.get("pix_dynamic_code", {})
                        pix_code = pix_info.get("code")
                        if pix_code and (not pix_info.get("key") or not pix_info.get("key_type")):
                            key, key_type = _extract_pix_info_from_code(pix_code)
                            pix_info["key"] = key
                            pix_info["key_type"] = key_type
                            setting["pix_dynamic_code"] = pix_info

            payload["interactive"] = {
                "type": "order_details",
                "body": {
                    "text": content
                },
                "action": {
                    "name": "review_and_pay",
                    "parameters": order_details
                }
            }
            
            # Adicionar rodapé se disponível
            footer_text = kwargs.get('footer')
            if footer_text:
                payload["interactive"]["footer"] = {"text": footer_text}

        elif message_type == 'interactive' and (buttons or kwargs.get('rows')):
            payload["type"] = "interactive"
            
            # Extrair metadados para interativos
            header_text = kwargs.get('header')
            footer_text = kwargs.get('footer')
            rows = kwargs.get('rows')
            button_text = kwargs.get('button_text', 'Ver Opções')
            section_title = kwargs.get('section_title', 'Selecione uma opção')
            
            interactive_payload: Dict[str, Any] = {}
            
            body_text = str(content)[:1024]
            header_val = str(header_text)[:60] if header_text else None
            footer_val = str(footer_text)[:1024] if footer_text else ""
            
            if rows:
                # WhatsApp List Message
                sections_payload: List[Dict[str, Any]] = []
                rows_payload: List[Dict[str, Any]] = []
                for row in rows[:10]: # WhatsApp permite no máximo 10 linhas
                    rows_payload.append({
                        "id": str(row.get('id', str(hash(row.get('title', ''))))),
                        "title": str(row.get('title', 'Opção'))[:24], # Máximo 24 caracteres
                        "description": str(row.get('description', ''))[:72] # Máximo 72 caracteres
                    })
                
                sections_payload.append({
                    "title": str(section_title)[:24], # Máximo 24 caracteres
                    "rows": rows_payload
                })
                
                interactive_payload = {
                    "type": "list",
                    "body": {
                        "text": body_text
                    },
                    "footer": {
                        "text": footer_val
                    },
                    "action": {
                        "button": str(button_text)[:20], # Texto do botão que abre a lista
                        "sections": sections_payload
                    }
                }

                if header_val:
                    interactive_payload["header"] = {
                        "type": "text",
                        "text": header_val
                    }
            else:
                # WhatsApp Reply Buttons
                buttons_payload: List[Dict[str, Any]] = []
                safe_buttons = buttons or []
                
                # Botões Interativos (Reply Buttons ou Copy Code) - Máximo 3
                for btn in safe_buttons[:3]:
                    btn_type = btn.get('type', 'reply')
                    
                    if btn_type == 'copy_code':
                        buttons_payload.append({
                            "type": "copy_code",
                            "copy_code": {
                                "text": str(btn.get('copy_code', btn.get('id', '')))
                            }
                        })
                    else:
                        buttons_payload.append({
                            "type": "reply",
                            "reply": {
                                "id": str(btn.get('id', str(hash(btn.get('title', ''))))),
                                "title": str(btn.get('title', 'Botão'))[:20]
                            }
                        })
                
                interactive_payload = {
                    "type": "button",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "buttons": buttons_payload
                    }
                }
                
                # Adicionar Header e Footer se fornecidos
                if header_text:
                    interactive_payload["header"] = {
                        "type": "text",
                        "text": str(header_text)[:60]
                    }
                
                if footer_text:
                    interactive_payload["footer"] = {
                        "text": str(footer_text)[:1024]
                    }
            
            payload["interactive"] = interactive_payload
        else:
            # Fallback para texto
            payload["type"] = "text"
            payload["text"] = {
                "preview_url": False,
                "body": content
            }
        
        # Remover campos None do payload
        def remove_none(obj):
            if isinstance(obj, dict):
                return {k: remove_none(v) for k, v in obj.items() if v is not None}
            return obj
        
        payload = remove_none(payload)
        
        # Fazer requisição para API da Meta
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"[WhatsAppCloud] Enviando mensagem: type={message_type}, to={recipient_number}")
        logger.debug(f"[WhatsAppCloud] Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"[WhatsAppCloud] Mensagem enviada com sucesso")
            return True, json.dumps(response_data)
        else:
            # Tentar extrair informações do erro
            error_data = {}
            try:
                error_data = response.json().get('error', {})
            except:
                error_data = {}
            
            error_code = error_data.get('code', response.status_code)
            error_subcode = error_data.get('error_subcode')
            error_message = error_data.get('message', response.text)
            error_details = error_data.get('error_data', {}).get('details', '')
            
            # Traduzir o erro para português
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            
            # Retornar erro em formato JSON para incluir código e mensagem
            error_response = {
                'error_code': error_code,
                'error_message': translated_error,
                'original_message': error_message,
                'details': error_details
            }
            
            logger.error(f"[WhatsAppCloud] Erro ao enviar mensagem: HTTP {response.status_code} - Código: {error_code} - {translated_error}")
            return False, json.dumps(error_response)
    
    except Exception as e:
        return False, str(e)


def send_reaction(
    conversation,
    target_message_id: str,
    emoji: str
) -> Tuple[bool, Optional[str]]:
    """
    Envia uma reação (emoji) para uma mensagem recebida via WhatsApp Cloud API.
    
    De acordo com a documentação da Meta:
    - Apenas um webhook de mensagem enviada (com status "sent") será disparado
    - Não haverá webhooks de mensagens entregues e lidas
    - Se a mensagem tiver mais de 30 dias, não corresponder a nenhuma mensagem na conversa,
      tiver sido excluída ou já for uma mensagem de reação, a reação não será entregue
      e você receberá um webhook com código de erro 131009.
    
    Args:
        conversation: Objeto Conversation
        target_message_id: ID da mensagem do WhatsApp (wamid.HBgL...) que será reagida
        emoji: Emoji a ser aplicado (pode ser o próprio emoji ou sequência Unicode)
    
    Returns:
        tuple: (success: bool, response: str ou dict)
    """
    try:
        provedor = conversation.inbox.provedor
        
        # Buscar instancia do canal vinculada a este inbox
        canal = conversation.inbox.get_canal_instance()
        
        if not canal:
            return False, "Canal WhatsApp Oficial não encontrado"
        
        if not canal.token:
            return False, "Token do canal não configurado"
        
        if not canal.phone_number_id:
            return False, "Phone Number ID não configurado"
        
        # Obter número do destinatário do contato
        contact = conversation.contact
        recipient_number = contact.phone
        
        # Remover caracteres não numéricos
        recipient_number = ''.join(filter(str.isdigit, recipient_number))
        
        # Garantir que comece com código do país (se não tiver, assumir Brasil 55)
        if not recipient_number.startswith('55') and len(recipient_number) <= 11:
            recipient_number = '55' + recipient_number
        
        # Montar payload para reação
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_number,
            "type": "reaction",
            "reaction": {
                "message_id": target_message_id,
                "emoji": emoji
            }
        }
        
        # Fazer requisição para API da Meta
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"[WhatsAppCloud] Enviando reação: emoji={emoji}, message_id={target_message_id}, to={recipient_number}")
        logger.debug(f"[WhatsAppCloud] Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"[WhatsAppCloud] Reação enviada com sucesso")
            return True, json.dumps(response_data)
        else:
            error_msg = response.text
            logger.error(f"[WhatsAppCloud] Erro ao enviar reação: HTTP {response.status_code} - {error_msg}")
            return False, error_msg
    
    except Exception as e:
        logger.error(f"[WhatsAppCloud] Exceção ao enviar reação: {str(e)}")
        return False, str(e)


def send_typing_indicator(canal: Canal, message_id: str) -> Tuple[bool, Optional[str]]:
    """
    Envia indicador de digitação (typing indicator) via API da Meta (WhatsApp).
    
    O indicador de digitação informa ao usuário que você está digitando uma resposta.
    O indicador será removido automaticamente quando você enviar uma mensagem ou após 25 segundos.
    
    IMPORTANTE: Apenas envie o indicador se você realmente for responder em breve.
    
    Args:
        canal: Objeto Canal com phone_number_id e token
        message_id: ID da mensagem do WhatsApp (wamid) que foi recebida
        
    Returns:
        Tuple[bool, Optional[str]]: (sucesso, mensagem_erro)
    """
    if not canal or not canal.phone_number_id or not canal.token:
        return False, "Canal, phone_number_id ou token não configurado"
    
    if not message_id:
        return False, "message_id não fornecido"
    
    try:
        # Preparar payload para API da Meta
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {
                "type": "text"
            }
        }
        
        # Fazer requisição para API da Meta
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                logger.info(f"[WhatsAppTypingIndicator] Indicador de digitação enviado para mensagem {message_id}")
                return True, None
            else:
                error_msg = result.get("error", {}).get("message", "Erro desconhecido")
                logger.warning(f"[WhatsAppTypingIndicator] Erro ao enviar indicador: {error_msg}")
                return False, error_msg
        else:
            error_data = response.json() if response.content else {}
            error_info = error_data.get("error", {})
            error_code = error_info.get("code")
            error_message = error_info.get("message", "Erro desconhecido")
            error_type = error_info.get("type", "Unknown")
            error_details = error_info.get("error_data", {}).get("details", "")
            
            translated_error = translate_whatsapp_error(error_code, error_message=error_message, details=error_details)
            logger.warning(
                f"[WhatsAppTypingIndicator] Falha ao enviar indicador (HTTP {response.status_code}): "
                f"{translated_error} (code: {error_code}, type: {error_type})"
            )
            return False, translated_error
            
    except requests.exceptions.Timeout:
        error_msg = "Timeout ao enviar indicador de digitação"
        logger.error(f"[WhatsAppTypingIndicator] {error_msg}")
        return False, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Erro de conexão ao enviar indicador: {str(e)}"
        logger.error(f"[WhatsAppTypingIndicator] {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Erro inesperado ao enviar indicador: {str(e)}"
        logger.error(f"[WhatsAppTypingIndicator] {error_msg}", exc_info=True)
        return False, error_msg


def mark_message_as_read(conversation, message_id: str) -> Tuple[bool, Optional[str]]:
    """
    Marca uma mensagem como lida na API da Meta (WhatsApp).
    
    De acordo com a documentação da Meta:
    - Marca a mensagem especificada como lida
    - Todas as mensagens anteriores no thread também são marcadas como lidas
    - Boa prática: marcar mensagens recebidas como lidas até 30 dias após a data de recebimento
    
    Args:
        conversation: Objeto Conversation
        message_id: ID da mensagem do WhatsApp (wamid.HBgL...) que foi recebida via webhook
    
    Returns:
        tuple: (success: bool, error_message: Optional[str])
    """
    try:
        provedor = conversation.inbox.provedor
        
        # Buscar instancia do canal vinculada a este inbox
        canal = conversation.inbox.get_canal_instance()
        
        if not canal:
            return False, "Canal WhatsApp Oficial não encontrado"
        
        if not canal.token:
            return False, "Token do canal não configurado"
        
        if not canal.phone_number_id:
            return False, "Phone Number ID não configurado"
        
        # Montar payload para marcar como lida
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        # Fazer requisição para API da Meta
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("success", False):
                logger.info(f"Mensagem {message_id} marcada como lida com sucesso")
                return True, None
            else:
                error_msg = response_data.get("error", {}).get("message", "Erro desconhecido")
                logger.warning(f"Erro ao marcar mensagem como lida: {error_msg}")
                return False, error_msg
        else:
            error_msg = response.text
            logger.error(f"Erro HTTP {response.status_code} ao marcar mensagem como lida: {error_msg}")
            return False, error_msg
    
    except Exception as e:
        logger.error(f"Exceção ao marcar mensagem como lida: {str(e)}")
        return False, str(e)


def send_template_message(
    canal: Any,
    recipient_number: str,
    template_name: str,
    template_language: str,
    template_components: Optional[List[Dict]] = None
) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Envia uma mensagem de template via WhatsApp Cloud API.
    Usado para iniciar conversas quando a janela de atendimento está fechada.
    
    Args:
        canal: Objeto Canal (ou objeto com atributos token, phone_number_id e opcionalmente waba_id)
        recipient_number: Número do destinatário (formato internacional, ex: 5511999999999)
        template_name: Nome do template aprovado
        template_language: Código do idioma do template (ex: pt_BR, en_US)
        template_components: Lista de componentes com parâmetros (opcional)
    
    Returns:
        tuple: (success: bool, error_message: Optional[str], response_data: Optional[Dict])
    """
    try:
        if not canal.token:
            return False, "Token do canal não configurado", None
        
        if not canal.phone_number_id:
            return False, "Phone Number ID não configurado", None
        
        # Manter apenas números e o sinal de '+' no início
        has_plus = recipient_number.startswith('+')
        recipient_number = ''.join(filter(lambda x: x.isdigit() or x == '+', recipient_number))
        
        # Se tinha '+' mas foi filtrado ou se não começa com '+', garantir formato correto
        if not recipient_number.startswith('+'):
            # Garantir que comece com código do país (se não tiver, assumir Brasil 55)
            if not recipient_number.startswith('55') and len(recipient_number) <= 11:
                recipient_number = '55' + recipient_number
            recipient_number = '+' + recipient_number
        
        # IMPORTANTE: A API da Meta aceita o formato original (pt_BR com underscore)
        # Não precisamos converter, usar o formato que vem da API de listagem
        language_code = template_language if template_language else 'pt_BR'
        
        # Log adicional para debug
        logger.info(f"[WhatsAppCloud] Idioma usado: {language_code}")
        
        # Montar payload
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        # Adicionar componentes se fornecidos
        if template_components:
            payload["template"]["components"] = template_components
        
        # Log do payload completo para debug
        logger.info(f"[WhatsAppCloud] Payload completo: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        # Fazer requisição
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {canal.token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"[WhatsAppCloud] Enviando template: name={template_name}, language={template_language} -> {language_code}, to={recipient_number}")
        logger.info(f"[WhatsAppCloud] Phone Number ID: {canal.phone_number_id}, WABA ID: {canal.waba_id}")
        logger.debug(f"[WhatsAppCloud] Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        logger.info(f"[WhatsAppCloud] Resposta da API: Status {response.status_code}")
        if response.status_code != 200:
            logger.error(f"[WhatsAppCloud] Resposta completa: {response.text}")
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"[WhatsAppCloud] Template enviado com sucesso")
            return True, None, response_data
        else:
            # Tentar extrair informações do erro
            error_data = {}
            try:
                error_data = response.json().get('error', {})
            except:
                error_data = {}
            
            error_code = error_data.get('code', response.status_code)
            error_subcode = error_data.get('error_subcode')
            error_message = error_data.get('message', response.text)
            error_details = error_data.get('error_data', {}).get('details', '')
            
            # Traduzir o erro para português
            translated_error = translate_whatsapp_error(error_code, error_subcode, error_message, error_details)
            
            logger.error(f"[WhatsAppCloud] Erro ao enviar template: HTTP {response.status_code} - Código: {error_code} - {translated_error}")
            return False, translated_error, None
    
    except Exception as e:
        logger.exception(f"[WhatsAppCloud] Exceção ao enviar template: {str(e)}")
        return False, str(e), None


def _normalize_whatsapp_to_number(recipient_number: str) -> str:
    recipient_number = "".join(c for c in recipient_number if c.isdigit() or c == "+")
    if not recipient_number.startswith("+"):
        if not recipient_number.startswith("55") and len(recipient_number) <= 11:
            recipient_number = "55" + recipient_number
        recipient_number = "+" + recipient_number
    return recipient_number


def send_interactive_order_details_raw(
    phone_number_id: str,
    access_token: str,
    recipient_number: str,
    body_text: str,
    order_parameters: Dict[str, Any],
    document_link: Optional[str] = None,
    document_filename: str = "Fatura.pdf",
    footer_text: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Envia mensagem interativa order_details (PIX / revisar e pagar) via Cloud API,
    sem conversa/canal no banco — usado pelo canal de cobrança do superadmin.
    """
    try:
        to = _normalize_whatsapp_to_number(recipient_number)

        def remove_none(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: remove_none(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [remove_none(x) for x in obj]
            return obj

        interactive: Dict[str, Any] = {
            "type": "order_details",
            "body": {"text": str(body_text)[:1024]},
            "action": {
                "name": "review_and_pay",
                "parameters": order_parameters,
            },
        }
        if document_link:
            interactive["header"] = {
                "type": "document",
                "document": {
                    "link": document_link,
                    "filename": (document_filename or "Fatura.pdf")[:240],
                },
            }
        if footer_text:
            interactive["footer"] = {"text": str(footer_text)[:60]}

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        payload = remove_none(payload)

        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        logger.info(
            "[WhatsAppCloud] order_details interativo | to=%s doc=%s",
            to,
            "sim" if document_link else "não",
        )
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            return True, None, response.json()
        err_data: Dict[str, Any] = {}
        try:
            err_data = response.json().get("error", {}) or {}
        except Exception:
            pass
        translated = translate_whatsapp_error(
            err_data.get("code", response.status_code),
            err_data.get("error_subcode"),
            err_data.get("message", response.text),
            (err_data.get("error_data") or {}).get("details", ""),
        )
        logger.error("[WhatsAppCloud] order_details falhou: %s", response.text[:800])
        return False, translated, None
    except Exception as e:
        logger.exception("[WhatsAppCloud] exceção em order_details: %s", e)
        return False, str(e), None


def _extract_pix_info_from_code(pix_code: str) -> Tuple[str, str]:
    """
    Extrai chave e tipo de chave de um código PIX (EMV ou chave direta).
    Lógica robusta para garantir parâmetros obrigatórios da Meta API.
    """
    if not pix_code:
        return "", "EVP"

    # 1. Se for QR Code EMV
    if pix_code.startswith('000201'):
        try:
            # CPF (11 dígitos seguidos)
            for match in re.finditer(r'\b\d{11}\b', pix_code):
                if match.start() > 10 and len(set(match.group())) > 1:
                    return match.group(), "CPF"
            # CNPJ (14 dígitos seguidos)
            for match in re.finditer(r'\b\d{14}\b', pix_code):
                if match.start() > 10 and len(set(match.group())) > 1:
                    return match.group(), "CNPJ"
            # Email
            email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', pix_code)
            if email:
                return email.group(), "EMAIL"
            # Telefone
            for pattern in [r'\+55\d{10,11}', r'\b55\d{10,11}\b']:
                for m in re.finditer(pattern, pix_code):
                    if m.start() > 10 and not m.group().startswith('0002'):
                        return m.group().lstrip('+'), "PHONE"
            
            # Fallback EVP determinístico baseado em hash
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, pix_code[:50])), "EVP"
        except:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, pix_code[:50])), "EVP"

    # 2. Se for chave direta
    if len(pix_code) == 11 and pix_code.isdigit():
        return pix_code, "CPF"
    elif len(pix_code) == 14 and pix_code.isdigit():
        return pix_code, "CNPJ"
    elif '@' in pix_code:
        return pix_code, "EMAIL"
    elif pix_code.startswith('+55') or (pix_code.startswith('55') and len(pix_code) >= 12):
        return pix_code.lstrip('+'), "PHONE"
    elif '-' in pix_code and len(pix_code) == 36:
        return pix_code, "EVP"
    
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, pix_code[:50])), "EVP"
