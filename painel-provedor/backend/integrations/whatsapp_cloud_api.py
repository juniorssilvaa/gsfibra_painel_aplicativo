"""
Serviço para integração com WhatsApp Cloud API (Coexistence)
"""
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WhatsAppCloudAPIService:
    """
    Serviço para enviar mensagens via WhatsApp Cloud API
    """
    
    BASE_URL = "https://graph.facebook.com/v21.0"
    
    def __init__(self, phone_number_id: str, access_token: str):
        """
        Inicializa o serviço com credenciais do Cloud API
        
        Args:
            phone_number_id: ID do número de telefone do WhatsApp Business
            access_token: Token de acesso do Cloud API
        """
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.base_url = f"{self.BASE_URL}/{phone_number_id}"
    
    def send_text_message(self, to: str, message: str, reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Envia uma mensagem de texto via Cloud API
        
        Args:
            to: Número do destinatário (formato: 5511999999999)
            message: Texto da mensagem
            reply_to_message_id: ID da mensagem para responder (opcional)
        
        Returns:
            Dict com resultado do envio
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        # Adicionar contexto de resposta se fornecido
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Mensagem enviada via Cloud API para {to}: {result.get('messages', [{}])[0].get('id')}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "data": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar mensagem via Cloud API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_image_message(
        self, 
        to: str, 
        image_url: str, 
        caption: Optional[str] = None,
        reply_to_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envia uma mensagem de imagem via Cloud API
        
        Args:
            to: Número do destinatário
            image_url: URL da imagem
            caption: Legenda da imagem (opcional)
            reply_to_message_id: ID da mensagem para responder (opcional)
        
        Returns:
            Dict com resultado do envio
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        
        if caption:
            payload["image"]["caption"] = caption
        
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Imagem enviada via Cloud API para {to}: {result.get('messages', [{}])[0].get('id')}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "data": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar imagem via Cloud API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_audio_message(
        self, 
        to: str, 
        audio_url: str,
        reply_to_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envia uma mensagem de áudio via Cloud API
        
        Args:
            to: Número do destinatário
            audio_url: URL do áudio
            reply_to_message_id: ID da mensagem para responder (opcional)
        
        Returns:
            Dict com resultado do envio
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": {
                "link": audio_url
            }
        }
        
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Áudio enviado via Cloud API para {to}: {result.get('messages', [{}])[0].get('id')}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "data": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar áudio via Cloud API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_video_message(
        self, 
        to: str, 
        video_url: str, 
        caption: Optional[str] = None,
        reply_to_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envia uma mensagem de vídeo via Cloud API
        
        Args:
            to: Número do destinatário
            video_url: URL do vídeo
            caption: Legenda do vídeo (opcional)
            reply_to_message_id: ID da mensagem para responder (opcional)
        
        Returns:
            Dict com resultado do envio
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "video",
            "video": {
                "link": video_url
            }
        }
        
        if caption:
            payload["video"]["caption"] = caption
        
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Vídeo enviado via Cloud API para {to}: {result.get('messages', [{}])[0].get('id')}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "data": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar vídeo via Cloud API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_document_message(
        self, 
        to: str, 
        document_url: str, 
        filename: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envia uma mensagem de documento via Cloud API
        
        Args:
            to: Número do destinatário
            document_url: URL do documento
            filename: Nome do arquivo
            caption: Legenda do documento (opcional)
            reply_to_message_id: ID da mensagem para responder (opcional)
        
        Returns:
            Dict com resultado do envio
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {
                "link": document_url,
                "filename": filename
            }
        }
        
        if caption:
            payload["document"]["caption"] = caption
        
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Documento enviado via Cloud API para {to}: {result.get('messages', [{}])[0].get('id')}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "data": result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro ao enviar documento via Cloud API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

