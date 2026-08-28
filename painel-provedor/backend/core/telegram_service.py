"""
Serviço de integração com Telegram usando Telethon (MTProto)
Versão completa com autenticação robusta - Adaptado para modelo Canal
"""

import asyncio
import logging
import time
import os
import tempfile
from typing import Optional, Dict, Any, Callable
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    ApiIdInvalidError,
)
from django.conf import settings
from asgiref.sync import sync_to_async
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


def _normalize_telegram_credentials(api_id, api_hash):
    """Limpa e valida api_id/api_hash vindos do formulário."""
    api_id_raw = str(api_id or '').strip().replace(' ', '')
    api_hash_raw = str(api_hash or '').strip().replace(' ', '')
    if not api_id_raw or not api_hash_raw:
        return None, None, 'API ID e API Hash são obrigatórios'
    try:
        api_id_int = int(api_id_raw)
    except (TypeError, ValueError):
        return None, None, 'API ID inválido. Use apenas números (ex.: 12345678)'
    if api_id_int <= 0:
        return None, None, 'API ID inválido'
    if len(api_hash_raw) < 20:
        return None, None, (
            'API Hash parece incompleto. Copie o Hash completo em '
            'https://my.telegram.org/apps'
        )
    return api_id_int, api_hash_raw, None


class TelegramMTProtoService:
    """Serviço de integração Telegram usando MTProto - Compatível com modelo Canal"""
    
    def __init__(self):
        self.clients = {}  # Armazenar clientes ativos por canal_id
        self.code_hashes = {}  # Armazenar phone_code_hash por canal_id
        self.temp_clients = {}  # Armazenar clientes temporários durante autenticação
        
    async def create_client(self, channel, use_string_session=True):
        """Criar cliente MTProto para um canal - usando mesma lógica do test_telegram_auth.py"""
        try:
            api_id, api_hash, cred_err = _normalize_telegram_credentials(
                getattr(channel, 'api_id', None),
                getattr(channel, 'api_hash', None),
            )
            if cred_err:
                logger.warning(f'Credenciais Telegram inválidas para canal {getattr(channel, "id", None)}: {cred_err}')
                return None

            # Se tiver sessão salva e usar StringSession, usar ela
            if use_string_session:
                session_string = None
                if channel.dados_extras and 'telegram_session' in channel.dados_extras:
                    session_string = channel.dados_extras['telegram_session']
                    logger.info(f'Usando sessão salva (StringSession) para canal {channel.id}')
                
                # Criar sessão (nova ou recuperada) - igual ao script
                session = StringSession(session_string) if session_string else StringSession()
                
                client = TelegramClient(
                    session,
                    api_id,
                    api_hash,
                )
            else:
                # Para envio de código, usar nome de sessão simples como no script de teste
                session_name = f'telegram_session_{channel.id}'
                logger.info(f'Criando cliente com nome de sessão simples: {session_name}')
                
                client = TelegramClient(
                    session_name,
                    api_id,
                    api_hash,
                )
            
            logger.info(f'Cliente criado para canal {channel.id}: API_ID={api_id}')
            return client
        except Exception as e:
            logger.error(f"Erro ao criar cliente MTProto: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def send_code(self, channel):
        """Enviar código de verificação via SMS - EXATAMENTE como test_telegram_auth.py"""
        API_ID, API_HASH, cred_err = _normalize_telegram_credentials(
            channel.api_id, channel.api_hash
        )
        PHONE = (channel.phone_number or '').strip()
        
        # Formatar telefone (igual ao script)
        PHONE = PHONE.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not PHONE:
            return {'success': False, 'error': 'Número de telefone não configurado'}
        if not PHONE.startswith('+'):
            PHONE = '+' + PHONE
        
        if cred_err:
            return {'success': False, 'error': cred_err}
        
        # EXATAMENTE como no script - linhas 12-17
        logger.info("=" * 60)
        logger.info("TESTE DE AUTENTICACAO TELEGRAM")
        logger.info("=" * 60)
        logger.info(f"Telefone: {PHONE}")
        logger.info(f"API ID: {API_ID}")
        logger.info(f"API Hash length: {len(API_HASH)}")
        logger.info("")
        
        # Usar StringSession para poder salvar a sessão como string depois
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        # EXATAMENTE como no script - linhas 21-89
        try:
            # Linhas 22-24 do script
            logger.info("Conectando ao Telegram...")
            await client.connect()
            logger.info("[OK] Conectado!")
            logger.info("")
            
            # Linhas 27-36 do script
            if await client.is_user_authorized():
                logger.info("JA ESTA AUTORIZADO!")
                me = await client.get_me()
                logger.info(f"   Nome: {me.first_name} {me.last_name or ''}")
                logger.info(f"   Username: @{me.username}")
                logger.info(f"   ID: {me.id}")
                logger.info(f"   Telefone: {me.phone}")
                logger.info("")
                logger.info("[OK] Sessao valida! O servico esta funcionando corretamente.")
                
                # Salvar sessão para persistência (adicionado para NioChat)
                session_string = client.session.save()
                if not channel.dados_extras:
                    channel.dados_extras = {}
                channel.dados_extras['telegram_session'] = session_string
                # Usar sync_to_async para salvar no contexto assíncrono
                await sync_to_async(channel.save)()
                
                self.clients[channel.id] = client
                return {
                    'success': True,
                    'already_authorized': True,
                    'message': 'Já autenticado',
                    'user': {
                        'id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'phone': me.phone
                    }
                }
            else:
                # Linhas 38-48 do script
                logger.info("NAO AUTORIZADO - Enviando codigo de verificacao...")
                # force_sms é legado e costuma ser ignorado; o código geralmente chega no app Telegram
                try:
                    result = await client.send_code_request(PHONE)
                except TypeError:
                    result = await client.send_code_request(PHONE, force_sms=True)
                logger.info(f"[OK] Codigo enviado!")
                logger.info(f"   Phone Code Hash: {result.phone_code_hash[:20]}...")
                logger.info(f"   Tipo: {result.type}")
                logger.info("")
                logger.info("Para completar a autenticacao:")
                logger.info("   1. Abra o Telegram no celular")
                logger.info("   2. Voce recebera um codigo de 5 digitos")
                logger.info("   3. Use esse codigo no sistema web")
                logger.info("")
                
                # Armazenar phone_code_hash e sessão para uso no verify_code
                self.code_hashes[channel.id] = result.phone_code_hash
                
                # IMPORTANTE: Salvar a sessão ANTES de desconectar
                # Isso preserva o data center correto para o verify_code
                session_string = client.session.save()
                self.temp_sessions = getattr(self, 'temp_sessions', {})
                self.temp_sessions[channel.id] = session_string
                logger.info(f"Sessão temporária salva (length: {len(session_string)})")

                # Persistir no banco: hash/sessão em memória se perdem entre requests/reload
                try:
                    extras = dict(channel.dados_extras or {})
                    extras['telegram_pending_auth'] = {
                        'phone_code_hash': result.phone_code_hash,
                        'temp_session': session_string,
                        'phone': PHONE,
                        'sent_at': time.time(),
                        'code_type': str(getattr(result, 'type', '') or ''),
                    }
                    # Ainda não autenticado — não expor sessão definitiva
                    extras.pop('telegram_session', None)
                    extras.pop('telegram_user', None)

                    @sync_to_async(thread_sensitive=False)
                    def _persist_pending():
                        from core.models import Canal
                        Canal.objects.filter(id=channel.id).update(
                            status='connecting',
                            dados_extras=extras,
                        )

                    await _persist_pending()
                    channel.dados_extras = extras
                    logger.info(
                        "[TelegramAuth] Pending auth persistido no canal %s (hash=%s...)",
                        channel.id,
                        result.phone_code_hash[:12],
                    )
                except Exception as persist_err:
                    logger.error(
                        "[TelegramAuth] Falha ao persistir pending auth do canal %s: %s",
                        channel.id,
                        persist_err,
                        exc_info=True,
                    )
                
                # Desconectar cliente
                try:
                    await client.disconnect()
                except:
                    pass
                
                return {
                    'success': True,
                    'message': f'Código enviado para {PHONE} (verifique o app Telegram ou SMS)',
                    'phone': PHONE,
                    'phone_code_hash': result.phone_code_hash,
                    'channel_id': channel.id,
                }
            
        except ApiIdInvalidError:
            logger.error(
                "[TelegramAuth] api_id/api_hash inválidos para canal %s (api_id=%s hash_len=%s)",
                getattr(channel, 'id', None),
                API_ID,
                len(API_HASH or ''),
            )
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            return {
                'success': False,
                'error': (
                    'API ID / API Hash inválidos. Confira os dados em '
                    'https://my.telegram.org/apps e cole novamente sem espaços.'
                ),
            }
        except FloodWaitError as e:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            return {
                'success': False,
                'error': f'Telegram pediu para aguardar {e.seconds} segundos antes de tentar novamente.',
            }
        except Exception as e:
            # Linhas 85-89 do script
            logger.error(f"ERRO: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            err = str(e)
            if 'api_id/api_hash' in err.lower() or 'ApiIdInvalid' in err:
                err = (
                    'API ID / API Hash inválidos. Confira os dados em '
                    'https://my.telegram.org/apps e cole novamente sem espaços.'
                )
            return {'success': False, 'error': err}
    
    async def verify_code(self, channel, code):
        """Verificar código recebido via SMS - EXATAMENTE como test_telegram_auth.py (linhas 50-77)"""
        API_ID, API_HASH, cred_err = _normalize_telegram_credentials(
            channel.api_id, channel.api_hash
        )
        PHONE = (channel.phone_number or '').strip()
        PHONE = PHONE.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        code = str(code or '').strip().replace(' ', '').replace('-', '')
        if not PHONE:
            return {'success': False, 'error': 'Número de telefone não configurado'}
        if not PHONE.startswith('+'):
            PHONE = '+' + PHONE
        
        if cred_err:
            return {'success': False, 'error': cred_err}

        if not code:
            return {'success': False, 'error': 'Código de verificação é obrigatório'}
        
        # Obter phone_code_hash: memória primeiro, fallback no banco (dados_extras)
        pending = {}
        try:
            await sync_to_async(channel.refresh_from_db)()
            pending = dict((channel.dados_extras or {}).get('telegram_pending_auth') or {})
        except Exception:
            pending = {}

        phone_code_hash = self.code_hashes.get(channel.id) or pending.get('phone_code_hash')
        if not phone_code_hash:
            logger.warning(
                "[TelegramAuth] phone_code_hash ausente para canal %s (memória=%s, pending=%s). "
                "Usuário precisa solicitar o código novamente.",
                channel.id,
                channel.id in self.code_hashes,
                bool(pending),
            )
            return {
                'success': False,
                'error': 'Sessão de verificação expirada ou perdida. Solicite o código novamente.',
            }

        if pending.get('phone'):
            PHONE = str(pending.get('phone')).strip() or PHONE
        
        # Usar a sessão temporária salva no send_code (preserva o data center correto)
        from telethon.sessions import StringSession
        
        temp_session = ''
        if hasattr(self, 'temp_sessions') and channel.id in self.temp_sessions:
            temp_session = self.temp_sessions[channel.id]
        if not temp_session:
            temp_session = pending.get('temp_session') or ''
        logger.info(
            "[TelegramAuth] verify_code canal=%s code_len=%s session_len=%s hash=%s...",
            channel.id,
            len(code),
            len(temp_session or ''),
            str(phone_code_hash)[:12],
        )
        
        client = TelegramClient(StringSession(temp_session), API_ID, API_HASH)
        
        try:
            # Conectar ao Telegram
            logger.info("Conectando ao Telegram...")
            await client.connect()
            logger.info("[OK] Conectado!")
            
            # EXATAMENTE como no script - linhas 51-77
            # Linhas 55-64 do script
            logger.info(f"Verificando codigo {code}...")
            try:
                # Linha 57 do script
                await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
                logger.info("[OK] Codigo aceito!")
                
                # Linhas 60-64 do script
                me = await client.get_me()
                logger.info(f"AUTENTICACAO COMPLETA!")
                logger.info(f"   Nome: {me.first_name} {me.last_name or ''}")
                logger.info(f"   Username: @{me.username}")
                logger.info(f"   ID: {me.id}")
                
                # Salvar sessão para persistência (adicionado para NioChat)
                logger.info("Salvando sessão no banco de dados...")
                session_string = client.session.save()
                if not channel.dados_extras:
                    channel.dados_extras = {}
                channel.dados_extras['telegram_session'] = session_string
                
                # Salvar informações do usuário no banco para acesso rápido
                channel.dados_extras['telegram_user'] = {
                    'telegram_id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'phone': me.phone
                }
                
                # Tentar buscar e salvar foto de perfil
                try:
                    import base64
                    photo_bytes = await client.download_profile_photo(me, bytes)
                    if photo_bytes:
                        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
                        channel.dados_extras['telegram_photo'] = f"data:image/jpeg;base64,{photo_base64}"
                        logger.info("Foto de perfil salva no banco de dados!")
                except Exception as e:
                    logger.warning(f"Erro ao salvar foto de perfil: {e}")
                
                # Salvar dados no banco usando update() para garantir persistência
                logger.info("Salvando canal no banco de dados...")
                try:
                    from core.models import Canal
                    
                    # Preparar dados_extras para atualização
                    updated_dados_extras = channel.dados_extras.copy() if channel.dados_extras else {}
                    updated_dados_extras['telegram_session'] = session_string
                    updated_dados_extras['telegram_user'] = {
                        'telegram_id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'phone': me.phone
                    }
                    updated_dados_extras.pop('telegram_pending_auth', None)
                    
                    # Tentar adicionar foto se foi salva
                    if 'telegram_photo' in channel.dados_extras:
                        updated_dados_extras['telegram_photo'] = channel.dados_extras['telegram_photo']
                    
                    # Usar update() direto - mais confiável que save()
                    @sync_to_async(thread_sensitive=False)
                    def update_channel():
                        Canal.objects.filter(id=channel.id).update(
                            status='connected',
                            ativo=True,
                            dados_extras=updated_dados_extras
                        )
                    
                    await update_channel()
                    logger.info(f"Canal {channel.id} salvo com sucesso no banco de dados!")
                    logger.info(f"Session string salva (length: {len(session_string)})")
                except Exception as e:
                    logger.error(f"Erro ao salvar canal: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # Liberar a sessão MTProto: se manter conectado aqui, o listener
                # do telegram_manager pode falhar com AUTH_KEY_DUPLICATED.
                try:
                    await client.disconnect()
                    logger.info("[TelegramAuth] Cliente de autenticação desconectado")
                except Exception as disc_err:
                    logger.warning("[TelegramAuth] Falha ao desconectar cliente auth: %s", disc_err)
                if channel.id in self.clients:
                    del self.clients[channel.id]
                
                # Limpar temporários
                logger.info("Limpando temporários...")
                if channel.id in self.code_hashes:
                    del self.code_hashes[channel.id]
                if hasattr(self, 'temp_sessions') and channel.id in self.temp_sessions:
                    del self.temp_sessions[channel.id]
                
                # Desconectar cliente antigo dos temp_clients se existir
                old_client = self.temp_clients.get(channel.id)
                if old_client:
                    try:
                        logger.info("Desconectando cliente antigo...")
                        await old_client.disconnect()
                        logger.info("Cliente antigo desconectado!")
                    except Exception as e:
                        logger.warning(f"Erro ao desconectar cliente antigo: {e}")
                    del self.temp_clients[channel.id]

                # Iniciar listener no loop ASGI (não no loop temporário da view).
                # await restart_canal_listener aqui quebra com:
                # "You cannot submit onto CurrentThreadExecutor from its own thread"
                # e o loop da view é fechado após a resposta.
                try:
                    from integrations.telegram_service import telegram_manager
                    started = telegram_manager.schedule_restart_canal_listener(channel.id)
                    logger.info(
                        "[TelegramAuth] Listener pós-auth canal=%s started=%s",
                        channel.id,
                        started,
                    )
                except Exception as listen_err:
                    logger.error(
                        "[TelegramAuth] Falha ao iniciar listener pós-auth canal=%s: %s",
                        channel.id,
                        listen_err,
                        exc_info=True,
                    )
                
                logger.info("Retornando resposta de sucesso...")
                result = {
                    'success': True,
                    'status': 'CONNECTED',
                    'message': 'Autenticação completa',
                    'user': {
                        'id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'phone': me.phone
                    }
                }
                logger.info(f"Resultado a ser retornado: {result}")
                return result
                
            except SessionPasswordNeededError:
                # Linhas 66-72 do script
                logger.info("SENHA 2FA NECESSARIA")
                # Armazenar cliente para verificar senha depois
                self.temp_clients[channel.id] = client
                return {
                    'success': False, 
                    'error': 'Senha de 2FA necessária',
                    'needs_password': True
                }
            except PhoneCodeInvalidError:
                logger.error("Código inválido")
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                return {'success': False, 'error': 'Código inválido. Verifique e tente novamente.'}
            except PhoneCodeExpiredError:
                logger.error("Código expirado")
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                return {'success': False, 'error': 'Código expirado. Solicite um novo código.'}
            except FloodWaitError as e:
                logger.error(f'Flood wait: {e.seconds} segundos')
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                return {'success': False, 'error': f'Aguarde {e.seconds} segundos antes de tentar novamente.'}
        except Exception as e:
            logger.error(f"ERRO: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {'success': False, 'error': str(e)}

    async def verify_password(self, channel, password):
        """Verificar senha de 2FA quando exigida - EXATAMENTE como test_telegram_auth.py (linhas 68-72)"""
        # Usar cliente temporário armazenado (do verify_code quando precisa 2FA)
        client = self.temp_clients.get(channel.id)
        if not client:
            return {'success': False, 'error': 'Sessão expirada. Solicite um novo código.'}
        
        try:
            # EXATAMENTE como no script - linhas 68-72
            # Linha 70 do script
            await client.sign_in(password=password)
            
            # Linhas 71-72 do script
            me = await client.get_me()
            logger.info(f"[OK] 2FA Verificado! Autenticado como: {me.first_name}")
            logger.info(f"   Nome: {me.first_name} {me.last_name or ''}")
            logger.info(f"   Username: @{me.username}")
            logger.info(f"   ID: {me.id}")
            
            # Salvar sessão para persistência (adicionado para NioChat)
            session_string = client.session.save()
            if not channel.dados_extras:
                channel.dados_extras = {}
            channel.dados_extras['telegram_session'] = session_string
            channel.dados_extras['telegram_user'] = {
                'telegram_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'phone': me.phone,
            }
            channel.dados_extras.pop('telegram_pending_auth', None)
            channel.status = 'connected'
            channel.ativo = True
            await sync_to_async(channel.save, thread_sensitive=False)()

            # Liberar client auth para o listener não sofrer AUTH_KEY_DUPLICATED
            try:
                await client.disconnect()
            except Exception:
                pass
            if channel.id in self.clients:
                del self.clients[channel.id]
            if channel.id in self.code_hashes:
                del self.code_hashes[channel.id]
            if channel.id in self.temp_clients:
                del self.temp_clients[channel.id]

            try:
                from integrations.telegram_service import telegram_manager
                started = telegram_manager.schedule_restart_canal_listener(channel.id)
                logger.info("[TelegramAuth] Listener pós-2FA canal=%s started=%s", channel.id, started)
            except Exception as listen_err:
                logger.error(
                    "[TelegramAuth] Falha ao iniciar listener pós-2FA canal=%s: %s",
                    channel.id,
                    listen_err,
                    exc_info=True,
                )
            
            return {
                'success': True,
                'status': 'CONNECTED',
                'message': 'Senha 2FA verificada com sucesso',
                'user': {
                    'id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'phone': me.phone
                }
            }
        except Exception as e:
            logger.error(f"ERRO ao verificar senha 2FA: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    async def get_status(self, channel):
        """Verificar status da conexão MTProto"""
        try:
            if channel.id in self.clients:
                client = self.clients[channel.id]
                if client.is_connected():
                    me = await client.get_me()
                    if me:
                        return {
                            'success': True,
                            'status': 'CONNECTED',
                            'user': {
                                'id': me.id,
                                'username': me.username,
                                'first_name': me.first_name,
                                'last_name': me.last_name,
                                'phone': me.phone
                            }
                        }
            
            return {'success': False, 'status': 'DISCONNECTED'}
            
        except Exception as e:
            logger.error(f"Erro ao verificar status: {str(e)}")
            return {'success': False, 'status': 'DISCONNECTED', 'error': str(e)}
    
    async def disconnect(self, channel_id):
        """Desconectar cliente MTProto"""
        try:
            if channel_id in self.clients:
                client = self.clients[channel_id]
                await client.disconnect()
                del self.clients[channel_id]
                return {'success': True, 'message': 'Desconectado com sucesso'}
            return {'success': False, 'error': 'Cliente não encontrado'}
        except Exception as e:
            logger.error(f"Erro ao desconectar: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def check_connection(self, channel):
        """Teste de conexão em tempo real"""
        try:
            client = await self.create_client(channel)
            if not client:
                return {'success': False, 'connected': False, 'error': 'Erro ao criar cliente'}
            
            # Tentar conectar
            await client.connect()
            
            # Verificar se está conectado
            is_connected = client.is_connected()
            
            # Verificar se está autorizado
            is_authorized = await client.is_user_authorized()
            
            if is_connected and is_authorized:
                me = await client.get_me()
                await client.disconnect()
                
                return {
                    'success': True,
                    'connected': True,
                    'authorized': True,
                    'user_id': me.id if me else None,
                    'username': me.username if me else None
                }
            else:
                await client.disconnect()
                return {
                    'success': True,
                    'connected': is_connected,
                    'authorized': is_authorized,
                    'message': 'Conectado mas não autorizado' if is_connected else 'Não conectado'
                }
                
        except Exception as e:
            logger.error(f"Erro ao verificar conexão: {str(e)}")
            return {'success': False, 'connected': False, 'error': str(e)}
    
    async def get_user_info(self, channel):
        """Dados do usuário (nome, ID, username) - EXATAMENTE como no exemplo"""
        try:
            # Verificar se já tem cliente ativo
            if channel.id in self.clients:
                client = self.clients[channel.id]
                if not client.is_connected():
                    await client.connect()
            else:
                # Criar novo cliente usando sessão salva
                client = await self.create_client(channel, use_string_session=True)
                if not client:
                    return {'success': False, 'error': 'Erro ao criar cliente'}
                
                await client.connect()
                
                # Verificar se está autorizado
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return {'success': False, 'error': 'Não autorizado. Faça login primeiro.'}
                
                # Armazenar cliente
                self.clients[channel.id] = client
            
            # Obter dados do usuário
            me = await client.get_me()
            
            if me:
                return {
                    'success': True,
                    'connected': True,
                    'user': {
                        'telegram_id': me.id,
                        'id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'phone': me.phone,
                        'is_bot': me.bot if hasattr(me, 'bot') else False
                    }
                }
            else:
                return {'success': False, 'error': 'Não foi possível obter dados do usuário'}
                
        except Exception as e:
            logger.error(f"Erro ao obter dados do usuário: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def get_profile_photo(self, channel):
        """Foto do perfil em base64"""
        try:
            import base64
            from io import BytesIO
            
            # Verificar se já tem cliente ativo
            if channel.id in self.clients:
                client = self.clients[channel.id]
            else:
                # Criar novo cliente
                client = await self.create_client(channel)
                if not client:
                    return {'success': False, 'error': 'Erro ao criar cliente'}
                
                await client.connect()
                
                # Verificar se está autorizado
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return {'success': False, 'error': 'Não autorizado. Faça login primeiro.'}
            
            # Obter dados do usuário
            me = await client.get_me()
            
            if not me:
                return {'success': False, 'error': 'Não foi possível obter dados do usuário'}
            
            # Baixar foto de perfil
            photo_bytes = await client.download_profile_photo(me, bytes)
            
            if photo_bytes:
                # Converter para base64
                photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
                
                return {
                    'success': True,
                    'photo_base64': photo_base64,
                    'photo': photo_base64,
                    'photo_url': f'data:image/jpeg;base64,{photo_base64}'
                }
            else:
                return {
                    'success': True,
                    'photo': None,
                    'message': 'Usuário não possui foto de perfil'
                }
                
        except Exception as e:
            logger.error(f"Erro ao obter foto de perfil: {str(e)}")
            return {'success': False, 'error': str(e)}

    async def test_auth(self, api_id, api_hash, phone, session_name='test_session_niochat'):
        """
        Método de teste que replica exatamente o test_telegram_auth.py
        Para testar o envio de código SMS
        """
        logger.info("=" * 60)
        logger.info("TESTE DE AUTENTICACAO TELEGRAM")
        logger.info("=" * 60)
        logger.info(f"Telefone: {phone}")
        logger.info(f"API ID: {api_id}")
        logger.info("")
        print("=" * 60)
        print("TESTE DE AUTENTICACAO TELEGRAM")
        print("=" * 60)
        print(f"Telefone: {phone}")
        print(f"API ID: {api_id}")
        print("")
        
        client = TelegramClient(session_name, api_id, api_hash)
        
        try:
            logger.info("Conectando ao Telegram...")
            print("Conectando ao Telegram...")
            await client.connect()
            logger.info("[OK] Conectado!")
            print("[OK] Conectado!")
            print("")
            
            # Verificar se já está autorizado
            if await client.is_user_authorized():
                logger.info("JA ESTA AUTORIZADO!")
                print("JA ESTA AUTORIZADO!")
                me = await client.get_me()
                logger.info(f"   Nome: {me.first_name} {me.last_name or ''}")
                logger.info(f"   Username: @{me.username}")
                logger.info(f"   ID: {me.id}")
                logger.info(f"   Telefone: {me.phone}")
                print(f"   Nome: {me.first_name} {me.last_name or ''}")
                print(f"   Username: @{me.username}")
                print(f"   ID: {me.id}")
                print(f"   Telefone: {me.phone}")
                print("")
                logger.info("[OK] Sessao valida! O servico esta funcionando corretamente.")
                print("[OK] Sessao valida! O servico esta funcionando corretamente.")
            else:
                logger.info("NAO AUTORIZADO - Enviando codigo de verificacao...")
                print("NAO AUTORIZADO - Enviando codigo de verificacao...")
                result = await client.send_code_request(phone, force_sms=True)
                logger.info(f"[OK] Codigo enviado via SMS!")
                logger.info(f"   Phone Code Hash: {result.phone_code_hash[:20]}...")
                logger.info(f"   Tipo: {result.type}")
                print(f"[OK] Codigo enviado via SMS!")
                print(f"   Phone Code Hash: {result.phone_code_hash[:20]}...")
                print(f"   Tipo: {result.type}")
                print("")
                print("Para completar a autenticacao:")
                print("   1. Abra o Telegram no celular")
                print("   2. Voce recebera um codigo de 5 digitos")
                print("   3. Use esse codigo no sistema web")
                print("")
                
                return {
                    'success': True,
                    'code_sent': True,
                    'phone_code_hash': result.phone_code_hash,
                    'message': 'Código enviado com sucesso!'
                }
            
            await client.disconnect()
            logger.info("")
            logger.info("=" * 60)
            logger.info("TESTE CONCLUIDO")
            logger.info("=" * 60)
            print("")
            print("=" * 60)
            print("TESTE CONCLUIDO")
            print("=" * 60)
            
            return {
                'success': True,
                'already_authorized': True,
                'message': 'Já autorizado'
            }
            
        except Exception as e:
            logger.error(f"ERRO: {e}")
            print(f"ERRO: {e}")
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())
            await client.disconnect()
            return {
                'success': False,
                'error': str(e)
            }

# Instância global do serviço
telegram_service = TelegramMTProtoService()
