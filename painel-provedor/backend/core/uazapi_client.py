import requests
import logging

logger = logging.getLogger(__name__)

class UazapiClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token

    def connect_instance(self, phone=None, instance_name=None):
        """
        Conecta uma instância ao WhatsApp
        Se phone=None, gera QR code
        Se phone=string, gera código de pareamento
        Se instance_name for fornecido, usa como nome da instância
        """
        url = f"{self.base_url}/instance/connect"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "token": self.token  # Formato correto da Uazapi
        }
        
        # Se não passar phone, gera QR code
        # Se passar phone, gera código de pareamento
        data = {}
        if phone:
            data["phone"] = phone
        if instance_name:
            data["instance"] = instance_name
        
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            
            # Verificar se a resposta é válida
            if resp.status_code >= 400:
                # Se erro, retornar dict com erro
                try:
                    error_data = resp.json()
                    return error_data
                except:
                    return {
                        'error': f'HTTP {resp.status_code}',
                        'message': resp.text[:200] if resp.text else 'Erro desconhecido'
                    }
            
            # Tentar parsear JSON
            try:
                return resp.json()
            except ValueError:
                # Se não for JSON válido, retornar erro
                return {
                    'error': 'Resposta inválida da API',
                    'message': resp.text[:200] if resp.text else 'Resposta não é JSON válido'
                }
        except requests.exceptions.RequestException as e:
            return {
                'error': 'Erro na requisição',
                'message': str(e)
            }

    def get_instance_status(self, instance_id):
        """
        Verifica o status de uma instância específica
        Retorna informações completas da instância incluindo:
        - Estado da conexão (disconnected, connecting, connected)
        - QR code atualizado (se em processo de conexão)
        - Código de pareamento (se disponível)
        - Informações da última desconexão
        """
        url = f"{self.base_url}/instance/status?instance={instance_id}"
        headers = {
            "Accept": "application/json",
            "token": self.token
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    
    def get_instance_info(self, instance_id):
        """
        Busca informações completas da instância incluindo:
        - Foto de perfil (profilePicUrl)
        - Nome do perfil (profileName)
        - Status da conexão
        - Informações detalhadas da instância conectada
        
        Este é o endpoint correto para buscar foto de perfil e informações da instância
        """
        url = f"{self.base_url}/instance/info/{instance_id}"
        headers = {
            "Accept": "application/json",
            "token": self.token
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    
    def get_server_status(self):
        """Verifica se o token funciona com o endpoint /status"""
        url = f"{self.base_url}/status"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}"  # Para /status usa Authorization
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json() 

    def delete_instance(self, instance_id):
        """
        Deleta uma instância específica na Uazapi
        """
        url = f"{self.base_url}/instance/{instance_id}"
        headers = {
            "Accept": "application/json",
            "token": self.token
        }
        resp = requests.delete(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json() 

    def disconnect_instance(self, instance_id):
        """
        Desconecta uma instância específica na Uazapi
        Endpoint: POST /instance/disconnect?instance={instance_id}
        """
        url = f"{self.base_url}/instance/disconnect?instance={instance_id}"
        headers = {
            "Accept": "application/json",
            "token": self.token
        }
        
        try:
            resp = requests.post(url, headers=headers, timeout=10)
            
            # Verificar se a resposta é válida
            if resp.status_code >= 400:
                # Se erro, retornar dict com erro
                try:
                    error_data = resp.json()
                    return error_data
                except:
                    return {
                        'error': f'HTTP {resp.status_code}',
                        'message': resp.text[:200] if resp.text else 'Erro desconhecido'
                    }
            
            # Tentar parsear JSON
            try:
                return resp.json()
            except ValueError:
                # Se não for JSON válido, retornar sucesso mesmo sem JSON
                return {
                    'success': True,
                    'message': 'Instância desconectada com sucesso'
                }
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Erro de conexão: {str(e)}',
                'message': 'Não foi possível conectar à API Uazapi'
            }
        except Exception as e:
            return {
                'error': f'Erro inesperado: {str(e)}',
                'message': 'Erro ao desconectar instância'
            } 

    def get_contact_info(self, instance_id, phone):
        """
        Busca informações de um contato específico incluindo foto do perfil
        Usa o endpoint /chat/details conforme documentação da Uazapi
        """
        url = f"{self.base_url}/chat/details"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "token": self.token
        }
        
        data = {
            "instance": instance_id,
            "number": phone.replace('@s.whatsapp.net', '').replace('@c.us', ''),
            "preview": False  # Retorna imagem em tamanho full (melhor qualidade)
        }
        
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                result = resp.json()
                return result
            else:
                return None
                
        except Exception as e:
            return None
    
    def enviar_mensagem(self, numero: str, texto: str, instance_id: str = None, delay: int = None) -> bool:
        """
        Envia mensagem de texto via WhatsApp com suporte a delay
        
        Args:
            numero: Número do WhatsApp (com ou sem @s.whatsapp.net)
            texto: Texto da mensagem
            instance_id: ID da instância (opcional)
            delay: Delay em milissegundos para mostrar "digitando" antes de enviar (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            url = f"{self.base_url}/send/text"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            
            data = {
                "number": numero_limpo,
                "text": texto
            }
            
            if instance_id:
                data["instance"] = instance_id
            
            # Adicionar delay se fornecido (para mostrar "digitando" no WhatsApp)
            if delay is not None:
                data["delay"] = delay
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                # Para Uazapi, status 200 já indica sucesso
                # A resposta contém dados da mensagem se enviada com sucesso
                result = resp.json()
                return bool(result.get('id'))  # Se tem ID da mensagem, foi enviada
            else:
                return False
                
        except Exception as e:
            return False
    
    def enviar_imagem(self, numero: str, imagem_bytes: bytes, legenda: str = "", instance_id: str = None, reply_id: str = None) -> bool:
        """
        Envia imagem via WhatsApp usando ev conforme documentação
        
        Args:
            numero: Número do WhatsApp
            imagem_bytes: Bytes da imagem
            legenda: Legenda da imagem (opcional)
            instance_id: ID da instância (opcional)
            reply_id: ID da mensagem para responder (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            # Converter para base64 conforme documentação
            import base64
            imagem_base64 = base64.b64encode(imagem_bytes).decode('utf-8')
            
            # Usar endpoint /send/media conforme documentação
            url = f"{self.base_url}/send/media"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json", 
                "token": self.token
            }
            
            # Formato conforme documentação /send/media
            data = {
                "number": numero_limpo,
                "type": "image",
                "file": f"data:image/png;base64,{imagem_base64}",
                "readchat": True
            }
            
            # Só adicionar text/caption se houver legenda
            if legenda:
                data["text"] = legenda
            
            # Adicionar reply_id se fornecido (para responder mensagens)
            if reply_id:
                data["replyid"] = reply_id
            
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                return bool(result.get('id'))  # Se tem ID da mensagem, foi enviada
            else:
                return False
                
        except Exception as e:
            return False
    
    def enviar_audio(self, numero: str, audio_bytes: bytes, audio_type: str = "ptt", legenda: str = "", instance_id: str = None, reply_id: str = None) -> bool:
        """
        Envia áudio via WhatsApp usando /send/media conforme documentação Uazapi
        
        Args:
            numero: Número do WhatsApp
            audio_bytes: Bytes do áudio
            audio_type: Tipo de áudio (ptt, audio, myaudio)
            legenda: Legenda do áudio (opcional)
            instance_id: ID da instância (opcional)
            reply_id: ID da mensagem para responder (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            # Converter para base64 conforme documentação
            import base64
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Usar endpoint /send/media conforme documentação
            url = f"{self.base_url}/send/media"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json", 
                "token": self.token
            }
            
            # Detectar MIME type baseado no conteúdo do arquivo
            mime_type = "audio/mp3"  # Default
            if audio_bytes.startswith(b'\x1a\x45\xdf\xa3'):  # WebM signature
                mime_type = "audio/webm"
            elif audio_bytes.startswith(b'ID3') or audio_bytes[1:4] == b'ID3':  # MP3
                mime_type = "audio/mp3"
            elif audio_bytes.startswith(b'OggS'):  # OGG
                mime_type = "audio/ogg"
            
            # Formato conforme documentação /send/media para áudio
            data = {
                "number": numero_limpo,
                "type": audio_type,  # ptt, audio, myaudio
                "file": f"data:{mime_type};base64,{audio_base64}",
                "readchat": True
            }
            
            # Para PTT, não adicionar legenda (mensagem de voz)
            if legenda and audio_type != "ptt":
                data["text"] = legenda
            
            # Adicionar reply_id se fornecido (para responder mensagens)
            if reply_id:
                data["replyid"] = reply_id
            
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                return bool(result.get('id'))  # Se tem ID da mensagem, foi enviada
            else:
                return False
                
        except Exception as e:
            return False

    def enviar_documento(self, numero: str, documento_url: str, nome_arquivo: str = "boleto.pdf", legenda: str = "", instance_id: str = None, reply_id: str = None, track_id: str = None, track_source: str = None) -> bool:
        """
        Envia documento (PDF do boleto) via WhatsApp usando /send/media
        
        Args:
            numero: Número do WhatsApp
            documento_url: URL do documento (PDF do boleto) ou base64
            nome_arquivo: Nome do arquivo (obrigatório para documentos)
            legenda: Legenda do documento (opcional)
            instance_id: ID da instância (opcional)
            reply_id: ID da mensagem para responder (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            # Usar endpoint /send/media conforme documentação
            url = f"{self.base_url}/send/media"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json", 
                "token": self.token
            }
            
            # Formato conforme documentação /send/media para documentos
            data = {
                "number": numero_limpo,
                "type": "document",
                "file": documento_url,
                "docName": nome_arquivo,  # Campo obrigatório para documentos conforme documentação
                "readchat": True
            }
            
            # Só adicionar text/caption se houver legenda
            if legenda:
                data["text"] = legenda
            
            # Adicionar reply_id se fornecido (conforme documentação)
            if reply_id:
                data["replyid"] = reply_id
            
            # Adicionar track_id e track_source se fornecidos (para rastreamento)
            if track_id:
                data["track_id"] = track_id
            if track_source:
                data["track_source"] = track_source
            
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                return bool(result.get('id'))  # Se tem ID da mensagem, foi enviada
            else:
                return False
                
        except Exception as e:
            return False
    
    def enviar_menu(self, numero: str, tipo: str, texto: str, choices: list, footer_text: str = "", instance_id: str = None) -> bool:
        """
        Envia menu interativo com botões via WhatsApp
        
        Args:
            numero: Número do WhatsApp
            tipo: Tipo do menu ('button' ou 'list')
            texto: Texto principal
            choices: Lista de opções no formato ['Texto|valor', 'Texto2|valor2']
            footer_text: Texto do rodapé (opcional)
            instance_id: ID da instância (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            url = f"{self.base_url}/send/menu"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            
            # Usar formato da documentação Uazapi para /send/menu
            data = {
                "number": numero_limpo,
                "type": tipo,
                "text": texto,
                "choices": choices,
                "readchat": True  # Adicionar para garantir que a mensagem seja lida
            }
            
            if footer_text:
                data["footerText"] = footer_text
            
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                # Para Uazapi, status 200 já indica sucesso
                # A resposta contém dados da mensagem se enviada com sucesso
                result = resp.json()
                return bool(result.get('id'))  # Se tem ID da mensagem, foi enviada
            else:
                return False
                
        except Exception as e:
            return False 

    def enviar_carousel(self, numero: str, texto: str, choices: list, instance_id: str = None) -> bool:
        """
        Envia carrossel interativo via WhatsApp
        
        Args:
            numero: Número do WhatsApp
            texto: Texto principal
            choices: Lista de opções no formato do carrossel
            instance_id: ID da instância (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            url = f"{self.base_url}/send/carousel"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            
            data = {
                "number": numero_limpo,
                "text": texto,
                "choices": choices,
                "readchat": True
            }
            
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                return bool(result.get('id'))
            else:
                return False
                
        except Exception as e:
            return False

    def download_message(self, message_id: str, instance_id: str = None,
                          return_base64: bool = False,
                          generate_mp3: bool = True,
                          return_link: bool = True,
                          transcribe: bool = False,
                          openai_apikey: str = None) -> dict:
        """Chama /message/download para obter mídia/transcrição.

        Retorna dict com possíveis chaves: fileURL, mimetype, base64Data, transcription.
        """
        try:
            url = f"{self.base_url}/message/download"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            data = {
                "id": message_id,
                "return_base64": return_base64,
                "generate_mp3": generate_mp3,
                "return_link": return_link,
                "transcribe": transcribe
            }
            if instance_id:
                data["instance"] = instance_id
            if openai_apikey:
                data["openai_apikey"] = openai_apikey
            
            # Log do payload sendo enviado (sem expor a chave completa)
            log_data = {**data}
            if 'openai_apikey' in log_data:
                log_data['openai_apikey'] = f"{log_data['openai_apikey'][:10]}..." if log_data['openai_apikey'] else None
            logger.debug(f"[UAZAPI] Payload enviado para /message/download: {log_data}")
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            # Log detalhado do erro para debug
            error_text = resp.text[:500] if resp.text else "Sem resposta"
            logger.error(f"[UAZAPI] Erro ao fazer download/transcrição: HTTP {resp.status_code} - {error_text}")
            return {"error": f"HTTP {resp.status_code}", "raw": resp.text}
        except Exception as e:
            return {"error": str(e)}
    
    def find_message(self, message_id: str = None, chatid: str = None, track_id: str = None, 
                     track_source: str = None, limit: int = 1, offset: int = 0) -> dict:
        """
        Busca mensagens usando o endpoint /message/find da Uazapi
        
        Args:
            message_id: ID específico da mensagem para busca exata
            chatid: ID do chat no formato internacional
            track_id: ID de rastreamento para filtrar mensagens
            track_source: Origem do rastreamento para filtrar mensagens
            limit: Número máximo de mensagens a retornar (padrão 1)
            offset: Deslocamento para paginação (0 retorna as mensagens mais recentes)
            
        Returns:
            dict com as mensagens encontradas ou erro
        """
        try:
            url = f"{self.base_url}/message/find"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            
            data = {
                "limit": limit,
                "offset": offset
            }
            
            if message_id:
                data["id"] = message_id
            if chatid:
                data["chatid"] = chatid
            if track_id:
                data["track_id"] = track_id
            if track_source:
                data["track_source"] = track_source
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "raw": resp.text}
        except Exception as e:
            return {"error": str(e)}
    
    def enviar_fatura(self, numero: str, title: str, text: str, footer: str, invoice_number: str, 
                     item_name: str, amount: float, pix_key: str = None, pix_type: str = None, 
                     pix_name: str = None, boleto_code: str = None, delay: int = 300, 
                     instance_id: str = None) -> bool:
        """
        Envia fatura interativa via WhatsApp usando o formato invoice da Uazapi
        
        Args:
            numero: Número do WhatsApp
            title: Título da fatura (ex: "Fatura 85125")
            text: Texto da fatura com quebras de linha \n
            footer: Rodapé (ex: "ASNET Telecom")
            invoice_number: Número da fatura (ex: "85125")
            item_name: Nome do item (ex: "Fatura 85125")
            amount: Valor da fatura (ex: 100.00)
            pix_key: Chave PIX completa (opcional)
            pix_type: Tipo PIX (ex: "EVP") (opcional)
            pix_name: Nome do recebedor PIX (opcional)
            boleto_code: Código do boleto (linha digitável) (opcional)
            delay: Delay em milissegundos antes de enviar (padrão: 300)
            instance_id: ID da instância (opcional)
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Limpar número
            numero_limpo = numero.replace('@s.whatsapp.net', '').replace('@c.us', '')
            
            url = f"{self.base_url}/send/request-payment"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "token": self.token
            }
            
            # Montar payload conforme exemplo do usuário
            data = {
                "number": numero_limpo,
                "title": title,
                "text": text,
                "footer": footer,
                "invoiceNumber": invoice_number,
                "itemName": item_name,
                "amount": amount,
                "delay": delay,
                "readchat": True
            }
            
            # Adicionar dados PIX se fornecidos
            if pix_key:
                data["pixKey"] = pix_key
            if pix_type:
                data["pixType"] = pix_type
            if pix_name:
                data["pixName"] = pix_name
            
            # Adicionar código do boleto se fornecido
            if boleto_code:
                data["boletoCode"] = boleto_code
            
            # Adicionar instance_id se fornecido
            if instance_id:
                data["instance"] = instance_id
            
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                result = resp.json()
                return bool(result.get('id') or result.get('success'))
            else:
                logger.error(f"Erro ao enviar fatura: HTTP {resp.status_code} - {resp.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar fatura via Uazapi: {e}")
            return False