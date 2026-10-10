"""
Serviço de integração com Telegram usando Telethon (MTProto)
Usa o modelo Canal para buscar credenciais
"""

import asyncio
import base64
import logging
import re
import threading
from typing import Optional, Dict, Any, Callable
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    UnauthorizedError,
    AuthKeyUnregisteredError
)
from telethon.tl.types import (
    User as TelegramUser,
    Chat,
    Channel as TelegramChannel,
    MessageMediaGeo,
    MessageMediaVenue,
    MessageMediaPhoto,
    MessageMediaDocument,
)
from django.conf import settings
from asgiref.sync import sync_to_async
from core.horario_utils import verificar_automacao_agendada
from core.models import Canal, Company, Provedor
from conversations.models import Contact, Conversation, Message, Inbox

logger = logging.getLogger(__name__)


def _db(fn: Callable):
    """
    ORM a partir de corrotinas Telegram.

    thread_sensitive=False evita RuntimeError
    "You cannot submit onto CurrentThreadExecutor from its own thread"
    quando a view sync roda sob Daphne (ASGI) e cria um loop temporário.
    """
    return sync_to_async(fn, thread_sensitive=False)

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
                session_string = self.canal.dados_extras.get('telegram_session', '') or ''

            if not session_string:
                logger.warning(
                    "[Telegram] initialize_client canal=%s sem sessão autenticada",
                    getattr(self.canal, 'id', None),
                )
                return False

            if not self.canal.api_id or not self.canal.api_hash:
                logger.warning(
                    "[Telegram] initialize_client canal=%s sem api_id/api_hash",
                    getattr(self.canal, 'id', None),
                )
                return False
            
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
                logger.warning(
                    "[Telegram] Sessão do canal %s não autorizada",
                    getattr(self.canal, 'id', None),
                )
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
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
                await _db(self.canal.save)()

            self.canal.status = 'connected'
            await _db(self.canal.save)()
            logger.info("[Telegram] Cliente autorizado canal=%s", getattr(self.canal, 'id', None))
            return True

        except Exception as e:
            logger.error(
                "[Telegram] Erro initialize_client canal=%s: %s",
                getattr(self.canal, 'id', None),
                e,
                exc_info=True,
            )
            self.canal.status = 'error'
            try:
                await _db(self.canal.save)()
            except Exception:
                pass
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
            logger.info(
                "[Telegram] Listener já em execução canal=%s",
                getattr(self.canal, 'id', None),
            )
            return

        try:
            if not self.client:
                ok = await self.initialize_client()
                if not ok:
                    logger.error(
                        "[Telegram] Não foi possível iniciar listener canal=%s (cliente)",
                        getattr(self.canal, 'id', None),
                    )
                    return

            if not self.client.is_connected():
                await self.client.connect()

            self.is_running = True

            @self.client.on(events.NewMessage(incoming=True))
            async def handler(event):
                # Processar mensagem recebida em uma tarefa separada para não travar o listener
                try:
                    asyncio.create_task(self.process_incoming_message(event))
                except Exception as handler_err:
                    logger.error("[Telegram] Erro no handler NewMessage: %s", handler_err, exc_info=True)

            logger.info(
                "[Telegram] Listener ativo (run_until_disconnected) canal=%s",
                getattr(self.canal, 'id', None),
            )
            await self.client.run_until_disconnected()

        except Exception as e:
            logger.error(
                "[Telegram] start_listener falhou canal=%s: %s",
                getattr(self.canal, 'id', None),
                e,
                exc_info=True,
            )
            self.is_running = False
        finally:
            self.is_running = False
            logger.warning(
                "[Telegram] Listener finalizado canal=%s",
                getattr(self.canal, 'id', None),
            )

    async def process_incoming_message(self, event):
        """Processa cada mensagem recebida e salva no banco"""
        try:
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            logger.info(
                "[Telegram] Mensagem recebida canal=%s chat_id=%s sender=%s text=%r",
                getattr(self.canal, 'id', None),
                getattr(message, 'chat_id', None),
                getattr(sender, 'id', None) if sender else None,
                (message.message or '')[:80],
            )
            
            # Ignorar mensagens de canais/bots se necessário
            if isinstance(chat, TelegramChannel) and chat.broadcast:
                return

            # Obter conteúdo
            content = message.message or ""
            is_edited = False # No listener inicial, não detectamos edição
            message_type = 'text'
            additional_attrs = {
                'telegram_message_id': message.id,
                'telegram_chat_id': message.chat_id,
                'telegram_sender_id': message.sender_id,
                'is_edited': is_edited,
            }

            # Localização (pin / venue) — extrair coordenadas para a IA
            lat = lng = None
            loc_name = loc_address = None
            geo = getattr(message, 'geo', None)
            media = getattr(message, 'media', None)
            if geo is not None and getattr(geo, 'lat', None) is not None:
                lat = geo.lat
                lng = geo.long
            elif isinstance(media, MessageMediaGeo) and getattr(media, 'geo', None):
                lat = media.geo.lat
                lng = media.geo.long
            elif isinstance(media, MessageMediaVenue) and getattr(media, 'geo', None):
                lat = media.geo.lat
                lng = media.geo.long
                loc_name = (getattr(media, 'title', None) or '').strip() or None
                loc_address = (getattr(media, 'address', None) or '').strip() or None

            if lat is not None and lng is not None:
                message_type = 'location'
                additional_attrs.update({
                    'latitude': lat,
                    'longitude': lng,
                    'is_location_message': True,
                    'source': 'telegram',
                })
                if loc_name:
                    additional_attrs['location_name'] = loc_name
                if loc_address:
                    additional_attrs['location_address'] = loc_address
                parts = [
                    "Cliente compartilhou a localização atual",
                    f"latitude={lat}",
                    f"longitude={lng}",
                ]
                if loc_name:
                    parts.append(f"nome={loc_name}")
                if loc_address:
                    parts.append(f"endereco={loc_address}")
                content = ". ".join(parts) + "."
                logger.info(
                    "[Telegram] Localização recebida: lat=%s lng=%s",
                    lat, lng,
                )

            # 1. Obter ou criar contato
            contact = await self.get_or_create_contact(sender, chat)

            # 2. Obter ou criar conversa
            conversation = await self.get_or_create_conversation(contact, chat)

            file_url = None
            attachments = []
            if message.media and message_type != 'location':
                media_info = await self.process_media(message, conversation.id)
                if media_info:
                    attachments.append(media_info)
                    file_url = media_info.get('file_url')
                    detected = media_info.get('message_type') or 'document'
                    if message_type == 'text':
                        message_type = detected
                    local_path = media_info.get('file_path')
                    try:
                        from ai.media_inbound import enrich_inbound_media_for_ai

                        provedor_media = await sync_to_async(lambda: self.canal.provedor)()
                        ai_text, media_extra = await sync_to_async(enrich_inbound_media_for_ai)(
                            provedor_media,
                            message_type,
                            local_path,
                            caption=content or '',
                        )
                        if media_extra:
                            additional_attrs.update(media_extra)
                        if ai_text:
                            content = ai_text
                        elif not content:
                            content = "[Mídia]"
                    except Exception as media_ai_err:
                        logger.warning(
                            "[Telegram] Falha ao preparar mídia para IA: %s",
                            media_ai_err,
                        )
                        if not content:
                            content = "[Mídia]"

            additional_attrs['attachments'] = attachments

            # 3. Salvar mensagem no banco do Nio Chat
            @sync_to_async
            def create_message():
                return Message.objects.create(
                    conversation=conversation,
                    content=content or "[Mídia]",
                    message_type=message_type,
                    is_from_customer=True,
                    external_id=str(message.id),
                    file_url=file_url,
                    additional_attributes=additional_attrs,
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
                if message_type == 'location' and lat is not None and lng is not None:
                    try:
                        await sync_to_async(redis_memory_service.update_ai_state_sync)(
                            provedor.id,
                            conversation.id,
                            {
                                "latitude": lat,
                                "longitude": lng,
                                "coordenada": f"{lat},{lng}",
                            },
                            'telegram',
                            contact.phone,
                        )
                    except Exception as e:
                        logger.warning(
                            "[Telegram] Erro ao salvar coordenadas no estado da IA: %s", e
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
            logger.error("[Telegram] Erro ao processar mensagem: %s", e, exc_info=True)
    # ==========================================================
    # CHAMAR IA / CHATBOT E ENVIAR RESPOSTA
    # ==========================================================
    async def call_ai_and_respond(self, conversation, contact, chat, content: str, reply_to_id: int):
        """Responde automaticamente no Telegram: ChatbotEngine (bot_mode=chatbot) ou OpenAI (bot_mode=ia)."""
        try:
            conversation = await sync_to_async(Conversation.objects.get)(id=conversation.id)

            bloqueado = await sync_to_async(lambda: getattr(contact, 'bloqueado_atender', False))()
            if bloqueado:
                logger.info(
                    "[Telegram] Automação ignorada: contato %s bloqueado (ATENDER=OFF)",
                    getattr(contact, 'id', None),
                )
                return

            provedor = await sync_to_async(lambda: self.canal.provedor)()
            if not provedor:
                return
            if not getattr(provedor, 'is_active', True):
                logger.info(
                    f"[Telegram] Automação ignorada: provedor {provedor.id} inativo. "
                    f"Motivo: {getattr(provedor, 'block_reason', '')}"
                )
                return

            bot_mode = await sync_to_async(
                lambda: (getattr(provedor, 'bot_mode', None) or 'ia').strip().lower()
            )()
            automacao_agendada = await sync_to_async(verificar_automacao_agendada)(provedor)

            if not automacao_agendada.get('ativa', True):
                logger.info(
                    "[Telegram] Automação ignorada por agenda automática provedor=%s modo=%s motivo=%s",
                    provedor.id,
                    automacao_agendada.get('modo'),
                    automacao_agendada.get('motivo'),
                )
                try:
                    from conversations.inbound_routing import encaminhar_quando_automacao_desligada
                    from core.chatbot_engine import ChatbotEngine

                    def _route_and_notify():
                        route = encaminhar_quando_automacao_desligada(
                            provedor, conversation, automacao_agendada
                        )
                        if route.get('encaminhado') and route.get('primeira_vez') and route.get('aviso'):
                            ChatbotEngine.send_message_agnostic_sync(
                                conversation, route['aviso']
                            )
                        return route

                    await sync_to_async(_route_and_notify)()
                except Exception as route_err:
                    logger.warning(
                        "[Telegram] Falha ao encaminhar fallback de automação conv=%s: %s",
                        getattr(conversation, 'id', None),
                        route_err,
                    )
                return

            # ---------- Modo CHATBOT (mesmo fluxo do WhatsApp) ----------
            if bot_mode == 'chatbot':
                from conversations.inbound_routing import resolve_inbound_csat_gate
                from core.chatbot_engine import ChatbotEngine

                def _prepare_chatbot_conv():
                    gate = resolve_inbound_csat_gate(
                        conversation,
                        message_text=content or '',
                        contact=contact,
                        provedor=provedor,
                        allow_closing_reopen=True,
                    )
                    conversation.refresh_from_db()
                    return gate

                csat_gate = await sync_to_async(_prepare_chatbot_conv)()
                if csat_gate.get('csat_feedback'):
                    logger.info(
                        '[Telegram] CSAT explícito processado — chatbot não chamado conv=%s',
                        conversation.id,
                    )
                    return

                conversation = await sync_to_async(Conversation.objects.get)(id=conversation.id)

                is_assigned = conversation.assignee_id is not None
                is_human_queue = bool(getattr(conversation, 'waiting_for_agent', False))
                is_active_agent_status = conversation.status in [
                    'open', 'closed', 'closing', 'resolved', 'finalizada', 'encerrada',
                ]
                if is_assigned or is_human_queue or is_active_agent_status:
                    logger.info(
                        "[Telegram] ChatbotEngine suprimido conv=%s: assignee=%s waiting_for_agent=%s status=%s",
                        conversation.id,
                        conversation.assignee_id,
                        is_human_queue,
                        conversation.status,
                    )
                    return

                logger.info(
                    "[Telegram] Provedor %s em modo CHATBOT. Invocando ChatbotEngine conv=%s",
                    provedor.id,
                    conversation.id,
                )
                try:
                    async with self.client.action(chat.id, 'typing'):
                        result = await ChatbotEngine.process_message(
                            provedor_id=provedor.id,
                            conversation_id=conversation.id,
                            message_content=content or '',
                            button_id=None,
                            canal_id=getattr(self.canal, 'id', None),
                        )
                except Exception as chatbot_err:
                    logger.error(
                        "[Telegram] Erro ao invocar ChatbotEngine conv=%s: %s",
                        conversation.id,
                        chatbot_err,
                        exc_info=True,
                    )
                    return

                # Garantir visibilidade nas abas Espera + Automação (pending + waiting=False)
                @sync_to_async
                def _ensure_chatbot_queue_status():
                    conversation.refresh_from_db()
                    if conversation.assignee_id or conversation.waiting_for_agent:
                        return
                    changed = []
                    if conversation.status != 'pending':
                        conversation.status = 'pending'
                        changed.append('status')
                    if conversation.waiting_for_agent is not False:
                        conversation.waiting_for_agent = False
                        changed.append('waiting_for_agent')
                    if changed:
                        conversation.save(update_fields=changed + ['updated_at'])

                try:
                    await _ensure_chatbot_queue_status()
                except Exception as st_err:
                    logger.warning(
                        "[Telegram] Falha ao ajustar status fila chatbot conv=%s: %s",
                        conversation.id,
                        st_err,
                    )

                handled = result[0] if isinstance(result, tuple) else result
                if handled:
                    logger.info(
                        "[Telegram] Chatbot processou conv=%s: %s",
                        conversation.id,
                        result[1] if isinstance(result, tuple) else '',
                    )
                else:
                    logger.warning(
                        "[Telegram] Chatbot não executou nó conv=%s: %s",
                        conversation.id,
                        result[1] if isinstance(result, tuple) else '',
                    )
                return

            # ---------- Modo IA ----------
            if bot_mode != 'ia':
                logger.info(
                    f"[Telegram] Automação ignorada: provedor {provedor.id} bot_mode={bot_mode}"
                )
                return

            # Liberar CSAT pendente se o cliente pediu algo novo (não nota explícita)
            def _release_csat_for_ia():
                from conversations.inbound_routing import resolve_inbound_csat_gate
                gate = resolve_inbound_csat_gate(
                    conversation,
                    message_text=content or '',
                    contact=contact,
                    provedor=provedor,
                    allow_closing_reopen=True,
                )
                conversation.refresh_from_db()
                return gate

            csat_gate = await sync_to_async(_release_csat_for_ia)()
            if csat_gate.get('csat_feedback'):
                logger.info(
                    '[Telegram] CSAT explícito processado — IA não chamada conv=%s',
                    conversation.id,
                )
                return

            status = conversation.status
            assignee_id = conversation.assignee_id
            if status == 'open' or assignee_id:
                return

            # Verificar se a IA está ativa no canal
            canal_ia_ativa = await sync_to_async(lambda: self.canal.ia_ativa)()
            if not canal_ia_ativa:
                logger.info(f"[Telegram] IA NÃO chamada - canal {self.canal.id} ({self.canal.nome}) tem IA desativada (ia_ativa=False)")
                return
            
            # 2. Chamar Orquestrador de IA (Mestre)
            from ai.service import openai_service
            
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
                from ai.response_formatter import AIResponseFormatter
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

                # Após resposta da IA: não reverter fila humana (pending + waiting_for_agent).
                @sync_to_async
                def update_status_after_ai():
                    conversation.refresh_from_db(
                        fields=['status', 'assignee_id', 'waiting_for_agent']
                    )
                    if conversation.waiting_for_agent or conversation.assignee_id:
                        return
                    if conversation.status in (
                        'pending', 'closed', 'closing', 'resolved',
                        'finalizada', 'encerrada', 'snoozed',
                    ):
                        return
                    conversation.status = 'snoozed'
                    conversation.save(update_fields=['status'])
                await update_status_after_ai()

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
            canal_id = getattr(self.canal, 'id', None)
            inbox, created = Inbox.objects.get_or_create(
                provedor=provedor,
                channel_type="telegram",
                defaults={
                    "name": "Telegram",
                    "channel_id": str(canal_id) if canal_id else None,
                    "additional_attributes": {
                        "phone_number": phone_number,
                        "canal_id": canal_id,
                    },
                },
            )
            # Garantir vínculo ao canal deste listener (get_canal_instance / envio chatbot)
            attrs = dict(inbox.additional_attributes or {})
            changed = False
            if canal_id and str(inbox.channel_id or '') != str(canal_id):
                inbox.channel_id = str(canal_id)
                changed = True
            if canal_id and attrs.get('canal_id') != canal_id:
                attrs['canal_id'] = canal_id
                inbox.additional_attributes = attrs
                changed = True
            if changed:
                inbox.save(update_fields=['channel_id', 'additional_attributes'])
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
    def _classify_telegram_media(self, message) -> str:
        if getattr(message, 'voice', None):
            return 'ptt'
        if getattr(message, 'audio', None):
            return 'audio'
        if getattr(message, 'photo', None) or isinstance(getattr(message, 'media', None), MessageMediaPhoto):
            return 'image'
        if getattr(message, 'video_note', None) or getattr(message, 'video', None):
            return 'video'
        if getattr(message, 'sticker', None):
            return 'sticker'
        doc = getattr(message, 'document', None)
        mime = (getattr(doc, 'mime_type', None) or '') if doc else ''
        if isinstance(getattr(message, 'media', None), MessageMediaDocument) and not mime:
            mime = getattr(getattr(message.media, 'document', None), 'mime_type', None) or ''
        if mime.startswith('image/'):
            return 'image'
        if mime.startswith('audio/'):
            return 'audio'
        if mime.startswith('video/'):
            return 'video'
        return 'document'

    async def process_media(self, message, conversation_id: int = None) -> Optional[Dict[str, Any]]:
        try:
            import os
            from django.conf import settings

            dest_dir = None
            if conversation_id:
                dest_dir = os.path.join(str(settings.MEDIA_ROOT), 'messages', str(conversation_id))
                os.makedirs(dest_dir, exist_ok=True)

            file_path = await message.download_media(file=dest_dir)
            if not file_path:
                return None

            file_url = None
            filename = os.path.basename(str(file_path))
            if conversation_id and filename:
                file_url = f'/api/media/messages/{conversation_id}/{filename}/'.replace('\\', '/')

            return {
                'type': 'file',
                'file_path': str(file_path),
                'file_name': filename,
                'file_url': file_url,
                'message_type': self._classify_telegram_media(message),
            }
        except Exception:
            logger.exception('[Telegram] Erro ao baixar mídia')
            return None

    # ==========================================================
    # ENVIAR MENSAGEM
    # ==========================================================
    @staticmethod
    def format_menu_text(text, buttons=None):
        """
        Conta usuário (MTProto) NÃO consegue exibir ReplyKeyboard/InlineKeyboard no app do
        cliente — isso só funciona quando o remetente é um Bot (@BotFather).

        Como fallback (igual ao WhatsApp em texto), embute opções numeradas no corpo
        da mensagem. O ChatbotEngine já aceita número ou título da opção.
        """
        body = (text or '').rstrip()
        items = []
        for b in buttons or []:
            if isinstance(b, dict):
                title = (b.get('title') or b.get('id') or '').strip()
            else:
                title = str(b or '').strip()
            if title:
                items.append(title)

        if not items:
            return body

        lines = [body, '', 'Opções:']
        for idx, title in enumerate(items, start=1):
            lines.append(f'{idx}. {title}')
        return '\n'.join(lines)

    async def send_message(self, chat_id, text, reply_to_message_id=None, buttons=None):
        """
        Envia mensagem para um chat.
        buttons: lista de {id, title} — opções são embutidas no texto (conta usuário).
        """
        if not self.client:
            await self.initialize_client()
        
        if not self.client.is_connected():
            await self.client.connect()
            
        try:
            from core.chatbot_display import strip_whatsapp_asterisks

            message_text = strip_whatsapp_asterisks(text or '')
            if buttons:
                message_text = self.format_menu_text(message_text, buttons)

            kwargs = {
                'entity': chat_id,
                'message': message_text,
            }
            if reply_to_message_id:
                kwargs['reply_to'] = reply_to_message_id

            # NÃO anexar reply_markup: clientes Telegram ignoram teclado de conta usuário.
            return await self.client.send_message(**kwargs)
        except Exception as e:
            logger.error(f"[Telegram] Erro ao enviar mensagem: {e}")
            return None

    async def send_photo(self, chat_id, photo_bytes, caption=None, filename='image.png'):
        """Envia imagem (ex.: QR Code PIX) para um chat."""
        from io import BytesIO

        if not self.client:
            await self.initialize_client()
        if not self.client.is_connected():
            await self.client.connect()

        try:
            buf = BytesIO(photo_bytes)
            buf.name = filename or 'image.png'
            return await self.client.send_file(
                chat_id,
                buf,
                caption=caption or '',
                force_document=False,
            )
        except Exception as e:
            logger.error(f"[Telegram] Erro ao enviar foto: {e}")
            return None

    async def send_document_url(self, chat_id, file_url, caption=None, filename=None):
        """Envia documento a partir de URL (ex.: boleto PDF), baixando bytes quando possível."""
        from io import BytesIO

        import requests as http_requests

        if not self.client:
            await self.initialize_client()
        if not self.client.is_connected():
            await self.client.connect()

        try:
            name = filename or 'boleto.pdf'
            file_payload = file_url
            try:
                resp = http_requests.get(file_url, timeout=45, allow_redirects=True)
                if resp.ok and resp.content:
                    ctype = (resp.headers.get('Content-Type') or '').lower()
                    # Só envia como arquivo se for PDF/octet; páginas HTML vão como link no caption
                    if 'pdf' in ctype or name.lower().endswith('.pdf') or resp.content[:4] == b'%PDF':
                        if not name.lower().endswith('.pdf') and 'pdf' in ctype:
                            name = f'{name}.pdf' if '.' not in name else name
                        buf = BytesIO(resp.content)
                        buf.name = name
                        file_payload = buf
                    elif len(resp.content) > 100 and 'text/html' not in ctype:
                        buf = BytesIO(resp.content)
                        buf.name = name
                        file_payload = buf
            except Exception as dl_exc:
                logger.warning('[Telegram] Download documento falhou, tentando URL direta: %s', dl_exc)

            return await self.client.send_file(
                chat_id,
                file_payload,
                caption=caption or '',
                force_document=True,
            )
        except Exception as e:
            logger.error(f"[Telegram] Erro ao enviar documento: {e}")
            return None

    def run_coro(self, coro, timeout: float = 45):
        """
        Executa coroutine no loop do client Telethon (necessário a partir de threads sync
        como fatura_service / sync_to_async).
        """
        loop = getattr(self, '_client_loop', None)
        if loop and loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running and running is loop:
            raise RuntimeError('Não use run_coro de dentro do mesmo loop do Telegram')
        return asyncio.run(coro)


class TelegramManager:
    """Gerenciador de múltiplas integrações Telegram"""
    
    def __init__(self):
        self.services: Dict[int, TelegramService] = {}
        # Loop ASGI (Daphne) onde os listeners devem viver
        self._asgi_loop: Optional[asyncio.AbstractEventLoop] = None
        self._fallback_loop: Optional[asyncio.AbstractEventLoop] = None
        self._fallback_thread: Optional[threading.Thread] = None
        self._fallback_lock = threading.Lock()

    def bind_asgi_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Registra o loop do ASGI para agendar listeners pós-auth."""
        try:
            self._asgi_loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self._asgi_loop = loop

    def get_service(self, canal_id: int):
        """Retorna o TelegramService ativo do canal, se houver."""
        return self.services.get(canal_id)

    def _ensure_fallback_loop(self) -> asyncio.AbstractEventLoop:
        """Loop dedicado em thread daemon se o ASGI não estiver disponível."""
        with self._fallback_lock:
            if self._fallback_loop and self._fallback_loop.is_running():
                return self._fallback_loop

            ready = threading.Event()
            holder: Dict[str, Any] = {}

            def _runner():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                holder['loop'] = loop
                ready.set()
                loop.run_forever()

            t = threading.Thread(target=_runner, name='telegram-fallback-loop', daemon=True)
            t.start()
            ready.wait(timeout=10)
            self._fallback_loop = holder.get('loop')
            self._fallback_thread = t
            if not self._fallback_loop:
                raise RuntimeError('Não foi possível criar loop fallback do Telegram')
            return self._fallback_loop

    def schedule_restart_canal_listener(self, canal_id: int, timeout: float = 90) -> bool:
        """
        Reinicia o listener fora do loop temporário da view de autenticação.

        A view sync sob Daphne usa um event loop descartável; o listener precisa
        ficar no loop ASGI (ou num fallback persistente).
        """
        target_loop = None
        if self._asgi_loop is not None and self._asgi_loop.is_running():
            target_loop = self._asgi_loop
        else:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            # Só reutiliza se não for o loop descartável prestes a fechar —
            # quem chama isto deve preferir ASGI/fallback.
            if running is not None and running is self._asgi_loop:
                target_loop = running

        if target_loop is None:
            target_loop = self._ensure_fallback_loop()

        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.restart_canal_listener(canal_id),
                target_loop,
            )
            return bool(fut.result(timeout=timeout))
        except Exception as e:
            logger.error(
                "[Telegram] Falha ao agendar restart listener canal=%s: %s",
                canal_id,
                e,
                exc_info=True,
            )
            return False
    
    async def start_integration(self, integration_id: int) -> bool:
        """Iniciar integração específica"""
        try:
            # Captura o loop vivo (ASGI) para usos futuros pós-auth
            try:
                self.bind_asgi_loop()
            except Exception:
                pass

            from integrations.models import TelegramIntegration
            from core.models import Canal
            
            # Tentar buscar pelo TelegramIntegration primeiro
            try:
                integration = await _db(
                    lambda: TelegramIntegration.objects.get(id=integration_id, is_active=True)
                )()
                
                # Buscar ou criar Canal correspondente
                def _get_or_create_canal():
                    if not Canal.objects.filter(tipo='telegram', provedor=integration.provedor).exists():
                        from core.plan_limits import canal_limit_error

                        limite = canal_limit_error(integration.provedor, 'telegram')
                        if limite:
                            raise PermissionError(limite)
                    return Canal.objects.get_or_create(
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

                canal, created = await _db(_get_or_create_canal)()
                
            except TelegramIntegration.DoesNotExist:
                # Se não encontrar TelegramIntegration, tentar buscar Canal diretamente
                canal = await _db(
                    lambda: Canal.objects.get(id=integration_id, tipo='telegram', ativo=True)
                )()
            
            # Sempre recarregar do banco (sessão pode ter acabado de ser salva no auth)
            canal = await _db(lambda: Canal.objects.get(id=canal.id))()
            extras = canal.dados_extras or {}
            if not extras.get('telegram_session'):
                logger.warning(
                    "[Telegram] Canal %s sem telegram_session — listener não iniciado",
                    canal.id,
                )
                return False
            
            if integration_id not in self.services:
                service = TelegramService(canal)
                self.services[integration_id] = service
            else:
                # Atualizar referência do canal (novas credenciais/sessão)
                old = self.services[integration_id]
                if old.client:
                    try:
                        if old.client.is_connected():
                            await old.client.disconnect()
                    except Exception:
                        pass
                self.services[integration_id].canal = canal
                self.services[integration_id].client = None
                self.services[integration_id].is_running = False
            
            service = self.services[integration_id]
            service.canal = canal
            
            # Inicializar cliente
            success = await service.initialize_client()
            
            if success:
                # Atualizar status do canal
                if hasattr(canal, 'status'):
                    canal.status = 'connected'
                    await _db(canal.save)()
                
                # Atualizar TelegramIntegration se existir
                try:
                    def _mark_connected():
                        integ = TelegramIntegration.objects.get(id=integration_id)
                        integ.is_connected = True
                        integ.save()
                        return integ

                    await _db(_mark_connected)()
                except TelegramIntegration.DoesNotExist:
                    pass
                
                # CRÍTICO: iniciar listener de mensagens em background.
                # Antes só autenticava o cliente e NÃO registrava NewMessage.
                async def _run_listener():
                    try:
                        logger.info("[Telegram] Iniciando listener de mensagens canal_id=%s", canal.id)
                        await service.start_listener()
                    except Exception as listen_err:
                        logger.error(
                            "[Telegram] Listener encerrou/falhou canal_id=%s: %s",
                            canal.id,
                            listen_err,
                            exc_info=True,
                        )
                        service.is_running = False

                asyncio.create_task(_run_listener())
                logger.info("Integração Telegram %s iniciada (listener em background)", integration_id)
                return True
            else:
                logger.warning(
                    "Falha ao inicializar cliente Telegram integration_id=%s",
                    integration_id,
                )
                return False
                
        except Exception as e:
            logger.error(f"Erro ao iniciar integração Telegram {integration_id}: {e}", exc_info=True)
            return False
    
    async def stop_integration(self, integration_id: int):
        """Parar integração específica"""
        try:
            from integrations.models import TelegramIntegration
            
            if integration_id in self.services:
                service = self.services[integration_id]
                
                # Desconectar cliente
                if service.client and service.client.is_connected():
                    try:
                        await service.client.disconnect()
                    except Exception:
                        pass
                
                service.is_running = False
                del self.services[integration_id]
            
            # Atualizar status no banco
            try:
                def _mark_disconnected():
                    integ = TelegramIntegration.objects.get(id=integration_id)
                    integ.is_connected = False
                    integ.save()
                    return integ

                await _db(_mark_disconnected)()
            except TelegramIntegration.DoesNotExist:
                pass
            
            logger.info(f"Integração Telegram {integration_id} parada")
            
        except Exception as e:
            logger.error(f"Erro ao parar integração Telegram {integration_id}: {e}", exc_info=True)

    async def restart_canal_listener(self, canal_id: int) -> bool:
        """Reinicia o listener de um Canal Telegram (após autenticação)."""
        try:
            if canal_id in self.services:
                await self.stop_integration(canal_id)
            return await self.start_integration(canal_id)
        except Exception as e:
            logger.error(
                "[Telegram] Falha ao reiniciar listener canal_id=%s: %s",
                canal_id,
                e,
                exc_info=True,
            )
            return False

    async def start_all_integrations(self):
        """Iniciar todas as integrações Telegram ativas"""
        try:
            self.bind_asgi_loop()
            from integrations.models import TelegramIntegration
            from core.models import Canal
            
            # Buscar integrações TelegramIntegration ativas
            integrations = await _db(
                lambda: list(
                    TelegramIntegration.objects.filter(is_active=True).values_list('id', flat=True)
                )
            )()
            
            for integration_id in integrations:
                try:
                    await self.start_integration(integration_id)
                except Exception as e:
                    logger.error(f"Erro ao iniciar integração Telegram {integration_id}: {e}", exc_info=True)
            
            # Buscar Canais Telegram ativos COM sessão autenticada
            def _connected_canal_ids():
                ids = []
                qs = Canal.objects.filter(tipo='telegram', ativo=True)
                for c in qs.only('id', 'dados_extras'):
                    extras = c.dados_extras or {}
                    if extras.get('telegram_session') and extras.get('telegram_user'):
                        ids.append(c.id)
                return ids

            canals = await _db(_connected_canal_ids)()
            
            for canal_id in canals:
                if canal_id not in integrations and canal_id not in self.services:
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
