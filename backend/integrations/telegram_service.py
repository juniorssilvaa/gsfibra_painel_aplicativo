"""
Serviço de integração com Telegram usando Telethon (MTProto)
Usa o modelo Canal para buscar credenciais
"""

import asyncio
import base64
import logging
import re
from typing import Optional, Dict, Any
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    UnauthorizedError,
    AuthKeyUnregisteredError
)
from telethon.tl.types import User as TelegramUser, Chat, Channel as TelegramChannel
from django.conf import settings
from asgiref.sync import sync_to_async
from core.models import Canal, Company, Provedor
from conversations.models import Contact, Conversation, Message, Inbox

logger = logging.getLogger(__name__)

class TelegramService:
    """
    Serviço responsável por:

    - Autenticar sessão MTProto
    - Verificar status real
    - Pegar foto do perfil
    - Desconectar (logout MTProto)
    - Receber mensagens (listener)
    - Enviar mensagens
    
    Usa o modelo Canal em vez de TelegramIntegration
    """

    def __init__(self, canal: Canal):
        self.canal = canal
        self.client: Optional[TelegramClient] = None
        self.is_running = False
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None  # Loop onde o cliente foi criado

    # ==========================================================
    # INICIALIZA CLIENTE TELEGRAM
    # ==========================================================
    async def initialize_client(self):
        """Inicializar cliente Telegram usando StringSession"""
        try:
            # Buscar session_string de dados_extras
            session_string = ''
            if self.canal.dados_extras and 'telegram_session' in self.canal.dados_extras:
                session_string = self.canal.dados_extras.get('telegram_session', '')
            
            session = StringSession(session_string)

            self.client = TelegramClient(
                session,
                int(self.canal.api_id),
                self.canal.api_hash
            )

            await self.client.connect()

            # Armazenar o event loop onde o cliente foi criado
            self._client_loop = asyncio.get_event_loop()

            # Se não está autenticado, tenta sincronizar
            if not await self.client.is_user_authorized():
                try:
                    await self.client.sign_in()
                except SessionPasswordNeededError:
                    return False
                except Exception:
                    return False

            # Salvar sessão caso nova
            new_session = self.client.session.save()
            old_session = ''
            if self.canal.dados_extras:
                old_session = self.canal.dados_extras.get('telegram_session', '')

            if new_session != old_session:
                if not self.canal.dados_extras:
                    self.canal.dados_extras = {}
                self.canal.dados_extras['telegram_session'] = new_session
                await sync_to_async(self.canal.save)()

            self.canal.status = 'connected'
            await sync_to_async(self.canal.save)()

            return True

        except Exception as e:
            self.canal.status = 'error'
            await sync_to_async(self.canal.save)()
            return False

    # ==========================================================
    # STATUS REAL DO TELEGRAM
    # ==========================================================
    async def get_status(self) -> dict:
        """Verifica se a sessão está realmente válida"""
        try:
            if not self.client:
                await self.initialize_client()

            await self.client.connect()

            try:
                await self.client.sign_in()
            except SessionPasswordNeededError:
                return {"status": "disconnected", "message": "Requer senha 2FA."}
            except (UnauthorizedError, AuthKeyUnregisteredError):
                return {"status": "disconnected", "message": "Sessão inválida."}
            except Exception:
                pass

            me = await self.client.get_me()
            if not me:
                return {"status": "disconnected"}

            return {
                "status": "connected",
                "id": me.id,
                "name": me.first_name,
                "username": me.username,
                "phone": me.phone
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ==========================================================
    # FOTO DO PERFIL — BASE64
    # ==========================================================
    async def get_profile_photo(self) -> Optional[str]:
        """Retorna a foto de perfil em Base64"""
        try:
            if not self.client:
                await self.initialize_client()

            me = await self.client.get_me()
            photo_bytes = await self.client.download_profile_photo(me, file=bytes)

            if not photo_bytes:
                return None

            return base64.b64encode(photo_bytes).decode()

        except Exception as e:
            return None
    
    async def get_user_profile_photo(self, user: TelegramUser) -> Optional[str]:
        """
        Retorna a foto de perfil de um usuário Telegram em Base64
        
        Args:
            user: Objeto TelegramUser do Telethon
            
        Returns:
            String Base64 da foto ou None se não houver foto
        """
        try:
            if not self.client:
                await self.initialize_client()
            
            # Garantir que o cliente está conectado
            if not self.client.is_connected():
                await self.client.connect()
            
            # Tentar baixar a foto do perfil do usuário
            photo_bytes = await self.client.download_profile_photo(user, file=bytes)
            
            if not photo_bytes:
                return None
            
            # Converter para Base64
            photo_base64 = base64.b64encode(photo_bytes).decode()
            
            # Criar data URL para salvar no campo avatar
            # Detectar tipo de imagem pelos primeiros bytes
            if photo_bytes.startswith(b'\xff\xd8'):
                mime_type = 'image/jpeg'
            elif photo_bytes.startswith(b'\x89PNG'):
                mime_type = 'image/png'
            elif photo_bytes.startswith(b'GIF'):
                mime_type = 'image/gif'
            elif photo_bytes.startswith(b'RIFF') and b'WEBP' in photo_bytes[:12]:
                mime_type = 'image/webp'
            else:
                mime_type = 'image/jpeg'  # Default
            
            # Retornar data URL
            data_url = f"data:{mime_type};base64,{photo_base64}"
            return data_url

        except Exception as e:
            return None

    async def fetch_contact_photo_by_phone(self, phone_number: str) -> Optional[str]:
        """Busca foto de contato pelo número de telefone"""
        try:
            if not self.client:
                await self.initialize_client()
            
            if not self.client.is_connected():
                await self.client.connect()
            
            # Tentar encontrar o usuário pelo telefone
            entity = await self.client.get_entity(phone_number)
            if entity and isinstance(entity, TelegramUser):
                return await self.get_user_profile_photo(entity)
            return None
        except Exception:
            return None

    # ==========================================================
    # DESCONECTAR (Logout)
    # ==========================================================
    async def disconnect(self):
        """Desconecta e limpa sessão se solicitado"""
        try:
            if self.client:
                if self.client.is_connected():
                    await self.client.log_out()
                    await self.client.disconnect()
                
                # Limpar dados do canal
                self.canal.status = 'disconnected'
                if self.canal.dados_extras:
                    self.canal.dados_extras.pop('telegram_session', None)
                await sync_to_async(self.canal.save)()
                
                return True
            return False
        except Exception:
            return False

    # ==========================================================
    # PROCESSAR MENSAGENS RECEBIDAS (LISTENER)
    # ==========================================================
    async def start_listener(self):
        """Inicia o listener de mensagens em background"""
        if self.is_running:
            return

        try:
            if not self.client:
                await self.initialize_client()

            if not self.client.is_connected():
                await self.client.connect()

            self.is_running = True

            @self.client.on(events.NewMessage(incoming=True))
            async def handler(event):
                # Processar mensagem recebida em uma tarefa separada para não travar o listener
                asyncio.create_task(self.process_incoming_message(event))

            await self.client.run_until_disconnected()

        except Exception as e:
            self.is_running = False

    async def process_incoming_message(self, event):
        """Processa cada mensagem recebida e salva no banco"""
        try:
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # Ignorar mensagens de canais/bots se necessário
            if isinstance(chat, TelegramChannel) and chat.broadcast:
                return

            # Obter conteúdo
            content = message.message or ""
            is_edited = False # No listener inicial, não detectamos edição
            
            # Processar mídia
            attachments = []
            if message.media:
                media_info = await self.process_media(message)
                if media_info:
                    attachments.append(media_info)

            # 1. Obter ou criar contato
            contact = await self.get_or_create_contact(sender, chat)
            
            # 2. Obter ou criar conversa
            conversation = await self.get_or_create_conversation(contact, chat)

            # 3. Salvar mensagem no banco do Nio Chat
            @sync_to_async
            def create_message():
                return Message.objects.create(
                    conversation=conversation,
                    content=content or "[Mídia]",
                    message_type='text' if not attachments else 'media',
                    is_from_customer=True,
                    external_id=str(message.id),
                    additional_attributes={
                        'telegram_message_id': message.id,
                        'telegram_chat_id': message.chat_id,
                        'telegram_sender_id': message.sender_id,
                        'is_edited': is_edited,
                        'attachments': attachments
                    }
                )
            
            system_message = await create_message()

            # Salvar no Redis para a IA
            if content:
                from core.redis_memory_service import redis_memory_service
                provedor = await sync_to_async(lambda: self.canal.provedor)()
                await redis_memory_service.add_message_to_conversation(
                    provedor_id=provedor.id,
                    conversation_id=conversation.id,
                    sender='customer',
                    content=content,
                    channel='telegram',
                    phone=contact.phone
                )
            
            # Atualizar last_message_at e last_user_message_at da conversa
            @sync_to_async
            def update_conversation_timestamps():
                from django.utils import timezone
                conversation.last_message_at = timezone.now()
                conversation.last_user_message_at = timezone.now()
                conversation.save(update_fields=['last_message_at', 'last_user_message_at'])
            
            await update_conversation_timestamps()

            # ==========================================================
            # NOTIFICAR VIA WEBSOCKET (tempo real para o frontend)
            # ==========================================================
            await self._notify_websocket(conversation, contact, system_message)

            # ==========================================================
            # CHAMAR IA PARA RESPONDER AUTOMATICAMENTE
            # ==========================================================
            if content and not is_edited:
                await self.call_ai_and_respond(conversation, contact, chat, content, message.id)

        except Exception as e:
            pass

    # ==========================================================
    # CHAMAR IA E ENVIAR RESPOSTA
    # ==========================================================
    async def call_ai_and_respond(self, conversation, contact, chat, content: str, reply_to_id: int):
        """Chama a IA e envia a resposta automaticamente no Telegram com LOCK e Contexto Forte"""
        try:
            # 1. Verificações de Elegibilidade
            status = await sync_to_async(lambda: conversation.status)()
            assignee_id = await sync_to_async(lambda: conversation.assignee_id)()
            
            if status == 'open' or assignee_id:
                return

            bloqueado = await sync_to_async(lambda: getattr(contact, 'bloqueado_atender', False))()
            if bloqueado:
                return

            provedor = await sync_to_async(lambda: self.canal.provedor)()
            if not provedor:
                return
            if not getattr(provedor, 'is_active', True):
                logger.info(
                    f"[Telegram] IA ignorada: provedor {provedor.id} inativo. "
                    f"Motivo: {getattr(provedor, 'block_reason', '')}"
                )
                return
            
            # Verificar se a IA está ativa no canal
            canal_ia_ativa = await sync_to_async(lambda: self.canal.ia_ativa)()
            if not canal_ia_ativa:
                logger.info(f"[Telegram] IA NÃO chamada - canal {self.canal.id} ({self.canal.nome}) tem IA desativada (ia_ativa=False)")
                return
            
            # 2. Chamar Orquestrador de IA (Mestre)
            from core.openai_service import openai_service
            
            # Contexto forte para a IA
            contexto = {
                'conversation': conversation,
                'contact': contact,
                'canal': 'telegram',
                'provedor_id': provedor.id,
                'conversation_id': conversation.id,
                'contact_phone': contact.phone
            }

            # 2.1 Indicador de Digitação (Início)
            try:
                # No Telethon, usamos chat_action('typing')
                typing_action = self.client.action(chat.id, 'typing')
            except Exception:
                typing_action = None

            # Chamar a IA (com lock interno)
            ia_result = await openai_service.generate_response(
                mensagem=content,
                provedor=provedor,
                contexto=contexto
            )

            if not ia_result.get('success'):
                motivo = ia_result.get('motivo', ia_result.get('erro', 'desconhecido'))
                if motivo != "IA_BUSY":
                    logger.warning(f"[Telegram] IA falhou para {conversation.id}: {motivo}")
                return

            resposta_ia = ia_result.get('resposta')
            
            # 🚨 SEGURANÇA CRÍTICA: Remover qualquer código antes de enviar ao cliente
            if resposta_ia:
                from core.ai_response_formatter import AIResponseFormatter
                formatter = AIResponseFormatter()
                resposta_ia = formatter.remover_exposicao_funcoes(resposta_ia)
            if not resposta_ia:
                return
            
            # 2.2 Delay proporcional (Telegram)
            try:
                # Delay proporcional (1s para cada 60 chars, min 1.5s, max 5s)
                delay = min(max(len(resposta_ia) / 60, 1.5), 5)
                # Se typing_action foi criado com 'async with', ele para após o contexto.
                # Como usamos apenas o delay aqui, vamos usar um sleep.
                async with self.client.action(chat.id, 'typing'):
                    await asyncio.sleep(delay)
            except Exception as e:
                logger.warning(f"[Telegram] Erro ao simular digitação: {e}")

            # 3. Enviar resposta no Telegram
            chat_id = chat.id
            try:
                enviado = await self.send_message(chat_id, resposta_ia, reply_to_message_id=reply_to_id)
            except Exception as send_error:
                logger.error(f"[Telegram] Erro ao enviar resposta IA: {send_error}")
                return

            if enviado:
                # 4. Salvar Mensagem e Atualizar Memória
                ai_message = await sync_to_async(Message.objects.create)(
                    conversation=conversation,
                    content=resposta_ia,
                    message_type='text',
                    is_from_customer=False,
                    additional_attributes={
                        'telegram_chat_id': chat_id,
                        'is_ai_response': True,
                        'from_ai': True,
                        'ai_conversation_id': ia_result.get('ai_conversation_id'),
                        'reply_to_message_id': reply_to_id
                    }
                )
                
                # Salvar resposta da IA no Redis
                from core.redis_memory_service import redis_memory_service
                await redis_memory_service.add_message_to_conversation(
                    provedor_id=provedor.id,
                    conversation_id=conversation.id,
                    sender='ai',
                    content=resposta_ia,
                    channel='telegram',
                    phone=contact.phone
                )

                # Mudar status para 'snoozed' (atendida pela IA)
                if conversation.status == 'pending':
                    @sync_to_async
                    def update_status():
                        conversation.status = 'snoozed'
                        conversation.save(update_fields=['status'])
                    await update_status()

                logger.info(f"[Telegram] IA respondeu com sucesso para {conversation.id}")
                
                # Notificar via WebSocket
                await self._notify_ai_response(conversation, contact, ai_message)

        except Exception as e:
            logger.error(f"[Telegram] Erro fatal no fluxo IA: {e}", exc_info=True)

    # ==========================================================
    # CRIAR CONTATO
    # ==========================================================
    async def get_or_create_contact(self, sender, chat) -> Contact:
        try:
            provedor = await sync_to_async(lambda: self.canal.provedor)()
            
            if isinstance(sender, TelegramUser):
                name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or str(sender.id)
                phone = sender.phone if sender.phone else f"tg_{sender.id}"
                access_hash = sender.access_hash
                
                @sync_to_async
                def get_or_create_user_contact():
                    existing = Contact.objects.filter(
                        provedor=provedor,
                        phone=phone
                    ).first()
                    
                    if existing:
                        # Atualizar access_hash se necessário
                        if not existing.additional_attributes:
                            existing.additional_attributes = {}
                        existing.additional_attributes['telegram_access_hash'] = access_hash
                        existing.save(update_fields=['additional_attributes'])
                        return existing
                    
                    # Criar novo contato
                    contact = Contact.objects.create(
                        provedor=provedor,
                        name=name,
                        phone=phone,
                        additional_attributes={
                            'telegram_user_id': sender.id,
                            'telegram_chat_id': sender.id,
                            'telegram_username': sender.username,
                            'telegram_access_hash': access_hash
                        }
                    )
                    return contact

                contact = await get_or_create_user_contact()
                
                # Buscar foto do perfil se não tiver avatar
                @sync_to_async
                def check_has_photo():
                    return bool(contact.avatar) or bool(contact.additional_attributes.get('telegram_photo') if contact.additional_attributes else False)
                
                has_photo = await check_has_photo()
                if not has_photo:
                    try:
                        profile_photo_data_url = await self.get_user_profile_photo(sender)
                        if profile_photo_data_url:
                            @sync_to_async
                            def update_photo():
                                if not contact.additional_attributes:
                                    contact.additional_attributes = {}
                                contact.additional_attributes['telegram_photo'] = profile_photo_data_url
                                contact.save(update_fields=['additional_attributes'])
                            await update_photo()
                    except Exception:
                        pass
                
                return contact

            else:
                title = getattr(chat, "title", f"Chat {chat.id}")
                phone = f"tg_chat_{chat.id}"
                
                @sync_to_async
                def get_or_create_chat_contact():
                    existing = Contact.objects.filter(
                        provedor=provedor,
                        phone=phone
                    ).first()
                    
                    if existing:
                        return existing
                    
                    contact = Contact.objects.create(
                        provedor=provedor,
                        name=title,
                        phone=phone,
                        additional_attributes={
                            'telegram_chat_id': chat.id,
                            'telegram_chat_type': type(chat).__name__
                        }
                    )
                    return contact

                return await get_or_create_chat_contact()

        except Exception:
            provedor = await sync_to_async(lambda: self.canal.provedor)()
            @sync_to_async
            def create_unknown_contact():
                import time
                return Contact.objects.create(
                    provedor=provedor,
                    name="Desconhecido",
                    phone=f"tg_unknown_{int(time.time())}"
                )
            return await create_unknown_contact()

    # ==========================================================
    # CRIAR CONVERSA
    # ==========================================================
    async def get_or_create_conversation(self, contact: Contact, chat) -> Conversation:
        provedor = await sync_to_async(lambda: self.canal.provedor)()
        phone_number = self.canal.phone_number
        
        @sync_to_async
        def get_or_create_inbox():
            inbox, _ = Inbox.objects.get_or_create(
                provedor=provedor,
                channel_type="telegram",
                defaults={
                    "name": "Telegram",
                    "additional_attributes": {"phone_number": phone_number}
                }
            )
            return inbox

        @sync_to_async
        def get_or_create_conv(inbox):
            from conversations.models import Team
            
            existing = Conversation.objects.filter(
                contact=contact,
                inbox=inbox,
                status__in=["open", "pending", "snoozed"]
            ).first()
            
            if existing:
                return existing
            
            bot_mode = getattr(provedor, 'bot_mode', 'ia')
            ia_team = None
            if bot_mode == 'ia':
                ia_team = Team.get_or_create_ia_team(provedor)
            
            return Conversation.objects.create(
                contact=contact,
                inbox=inbox,
                status="snoozed" if bot_mode == 'ia' else "pending",
                team=ia_team,
                assignee=None
            )

        inbox = await get_or_create_inbox()
        conversation = await get_or_create_conv(inbox)
        return conversation

    # ==========================================================
    # NOTIFICAR VIA WEBSOCKET
    # ==========================================================
    async def _notify_websocket(self, conversation: Conversation, contact: Contact, message: Message):
        """Notifica o frontend via WebSocket sobre nova mensagem"""
        # A notificação é feita via signal (post_save no modelo Message)
        pass

    async def _notify_ai_response(self, conversation: Conversation, contact: Contact, message: Message):
        """Notifica o frontend via WebSocket sobre resposta da IA"""
        # A notificação é feita via signal
        pass

    # ==========================================================
    # PROCESSAR MÍDIA
    # ==========================================================
    async def process_media(self, message) -> Optional[Dict[str, Any]]:
        try:
            file_path = await message.download_media()
            if file_path:
                return {
                    "type": "file",
                    "file_path": file_path,
                    "file_name": "arquivo",
                }
            return None
        except Exception:
            return None

    # ==========================================================
    # ENVIAR MENSAGEM
    # ==========================================================
    async def send_message(self, chat_id, text, reply_to_message_id=None):
        """Envia mensagem para um chat"""
        if not self.client:
            await self.initialize_client()
        
        if not self.client.is_connected():
            await self.client.connect()
            
        try:
            return await self.client.send_message(
                chat_id,
                text,
                reply_to=reply_to_message_id
            )
        except Exception as e:
            logger.error(f"[Telegram] Erro ao enviar mensagem: {e}")
            return None


class TelegramManager:
    """Gerenciador de múltiplas integrações Telegram"""
    
    def __init__(self):
        self.services: Dict[int, TelegramService] = {}
    
    async def start_integration(self, integration_id: int) -> bool:
        """Iniciar integração específica"""
        try:
            from integrations.models import TelegramIntegration
            from core.models import Canal
            
            # Tentar buscar pelo TelegramIntegration primeiro
            try:
                integration = await sync_to_async(TelegramIntegration.objects.get)(
                    id=integration_id,
                    is_active=True
                )
                
                # Buscar ou criar Canal correspondente
                canal, created = await sync_to_async(Canal.objects.get_or_create)(
                    tipo='telegram',
                    provedor=integration.provedor,
                    defaults={
                        'api_id': integration.api_id,
                        'api_hash': integration.api_hash,
                        'phone_number': integration.phone_number,
                        'status': 'disconnected',
                        'dados_extras': {
                            'telegram_session': integration.session_string or ''
                        } if integration.session_string else {}
                    }
                )
                
            except TelegramIntegration.DoesNotExist:
                # Se não encontrar TelegramIntegration, tentar buscar Canal diretamente
                canal = await sync_to_async(Canal.objects.get)(
                    id=integration_id,
                    tipo='telegram',
                    ativo=True
                )
            
            if integration_id not in self.services:
                service = TelegramService(canal)
                self.services[integration_id] = service
            
            service = self.services[integration_id]
            
            # Inicializar cliente
            success = await service.initialize_client()
            
            if success:
                service.is_running = True
                if hasattr(canal, 'status'):
                    canal.status = 'connected'
                    await sync_to_async(canal.save)()
                
                # Atualizar TelegramIntegration se existir
                try:
                    integration = await sync_to_async(TelegramIntegration.objects.get)(id=integration_id)
                    integration.is_connected = True
                    await sync_to_async(integration.save)()
                except TelegramIntegration.DoesNotExist:
                    pass
                
                logger.info(f"Integração Telegram {integration_id} iniciada")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Erro ao iniciar integração Telegram {integration_id}: {e}", exc_info=True)
            return False
    
    async def stop_integration(self, integration_id: int):
        """Parar integração específica"""
        try:
            from integrations.models import TelegramIntegration
            from core.models import Canal
            
            if integration_id in self.services:
                service = self.services[integration_id]
                
                # Desconectar cliente
                if service.client and service.client.is_connected():
                    await service.client.disconnect()
                
                service.is_running = False
                del self.services[integration_id]
            
            # Atualizar status no banco
            try:
                integration = await sync_to_async(TelegramIntegration.objects.get)(id=integration_id)
                integration.is_connected = False
                await sync_to_async(integration.save)()
            except TelegramIntegration.DoesNotExist:
                pass
            
            # Atualizar Canal se existir
            try:
                canal = await sync_to_async(Canal.objects.get)(
                    id=integration_id,
                    tipo='telegram'
                )
                canal.status = 'disconnected'
                await sync_to_async(canal.save)()
            except Canal.DoesNotExist:
                pass
            
            logger.info(f"Integração Telegram {integration_id} parada")
            
        except Exception as e:
            logger.error(f"Erro ao parar integração Telegram {integration_id}: {e}", exc_info=True)
    
    async def start_all_integrations(self):
        """Iniciar todas as integrações Telegram ativas"""
        try:
            from integrations.models import TelegramIntegration
            from core.models import Canal
            
            # Buscar integrações TelegramIntegration ativas
            integrations = await sync_to_async(list)(
                TelegramIntegration.objects.filter(is_active=True).values_list('id', flat=True)
            )
            
            for integration_id in integrations:
                try:
                    await self.start_integration(integration_id)
                except Exception as e:
                    logger.error(f"Erro ao iniciar integração Telegram {integration_id}: {e}", exc_info=True)
            
            # Buscar Canais Telegram ativos
            canals = await sync_to_async(list)(
                Canal.objects.filter(
                    tipo='telegram',
                    ativo=True
                ).values_list('id', flat=True)
            )
            
            for canal_id in canals:
                # Só iniciar se ainda não foi iniciado via TelegramIntegration
                if canal_id not in integrations:
                    try:
                        await self.start_integration(canal_id)
                    except Exception as e:
                        logger.error(f"Erro ao iniciar Canal Telegram {canal_id}: {e}", exc_info=True)
                        
        except Exception as e:
            logger.error(f"Erro ao iniciar todas as integrações Telegram: {e}", exc_info=True)
    
    async def stop_all_integrations(self):
        """Parar todas as integrações Telegram"""
        integration_ids = list(self.services.keys())
        for integration_id in integration_ids:
            try:
                await self.stop_integration(integration_id)
            except Exception as e:
                logger.error(f"Erro ao parar integração Telegram {integration_id}: {e}", exc_info=True)


# Instância global do gerenciador
telegram_manager = TelegramManager()
