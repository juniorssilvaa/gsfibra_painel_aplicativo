"""
Registro de tarefas do Dramatiq para o módulo de conversas
"""
import dramatiq
import logging
import sys
import django
from django.conf import settings

# Configurar encoding UTF-8 para Windows (de forma segura)
# Não substituir stdout/stderr durante "migrate" para evitar "I/O operation on closed file"
if sys.platform == 'win32' and 'migrate' not in sys.argv:
    try:
        import io
        if hasattr(sys.stderr, 'buffer'):
            try:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            except (ValueError, AttributeError, OSError):
                pass
        if hasattr(sys.stdout, 'buffer'):
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            except (ValueError, AttributeError, OSError):
                pass
    except Exception:
        pass

# Configurar logging básico para garantir que logs apareçam (de forma segura)
try:
    # Tentar usar stderr, se não estiver disponível, usar stdout
    try:
        stream = sys.stderr
        # Verificar se o stream está disponível
        if not hasattr(stream, 'write'):
            stream = sys.stdout
    except (ValueError, AttributeError, OSError):
        stream = sys.stdout
    
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=stream,
        force=True  # Forçar recriação se já configurado
    )
except Exception:
    # Se não conseguir configurar logging, continuar sem ele
    pass

# Configurar Django antes de importar models
if not settings.configured:
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
    django.setup()

from django.utils import timezone
from conversations.models import CSATRequest, Conversation
from core.uazapi_client import UazapiClient

logger = logging.getLogger(__name__)

# IMPORTANTE: Garantir que o broker está configurado ANTES de decorar o ator
# O decorator @dramatiq.actor registra o ator no broker atual no momento da importação
# Por isso precisamos garantir que o broker esteja configurado antes

# Tentar obter o broker atual
try:
    broker = dramatiq.get_broker()
    logger.info(f"Broker disponível: {type(broker).__name__}")
except Exception:
    # Se não há broker configurado, será configurado pelo dramatiq_config
    # IMPORTANTE: Quando executar o worker, passe os módulos explicitamente:
    # python -m dramatiq conversations.dramatiq_tasks integrations.dramatiq_tasks
    # O dramatiq_config deve ser importado antes (via niochat/__init__.py ou explicitamente)
    logger.warning("Broker não configurado ainda - será configurado pelo dramatiq_config")

# Decorar a função como ator Dramatiq
# IMPORTANTE: O decorator @dramatiq.actor registra automaticamente o ator no broker
# Usa fila dedicada niochat_csat_queue para isolamento e melhor controle
@dramatiq.actor(
    actor_name="migrate_conversation_after_csat_timeout",
    queue_name="niochat_csat_queue",
    time_limit=120000  # 2 minutos - suficiente para migração
)
def migrate_conversation_after_csat_timeout(csat_request_id: int):
    """
    Migra histórico para Supabase após timeout de 5 minutos sem resposta CSAT.
    Esta função é chamada automaticamente 5 minutos após o envio do CSAT se não houver resposta.
    """
    try:
        from django.db import transaction
        from datetime import timedelta
        
        logger.info(f"[CSATTimeout] Verificando timeout para CSAT request {csat_request_id}")
        
        with transaction.atomic():
            csat_request = CSATRequest.objects.select_for_update().select_related(
                'conversation', 'contact', 'provedor'
            ).get(id=csat_request_id)
            
            # Verificar se ainda está pendente (não foi respondido)
            if csat_request.status != 'sent':
                logger.info(f"[CSATTimeout] CSAT request {csat_request_id} não está mais 'sent' (status: {csat_request.status}), ignorando")
                return
            
            # Verificar se realmente passaram 5 minutos desde o envio
            if not csat_request.sent_at:
                logger.warning(f"[CSATTimeout] CSAT request {csat_request_id} não tem sent_at, ignorando")
                return
            
            now_utc = timezone.now()
            time_since_sent = (now_utc - csat_request.sent_at).total_seconds() / 60
            
            if time_since_sent < 5:
                logger.info(f"[CSATTimeout] CSAT request {csat_request_id} enviado há {time_since_sent:.1f} minutos, ainda aguardando resposta")
                return
            
            # Verificar se já foi respondido entre o envio da tarefa e agora
            csat_request.refresh_from_db()
            if csat_request.status != 'sent':
                logger.info(f"[CSATTimeout] CSAT request {csat_request_id} foi respondido durante verificação, ignorando")
                return
            
            conversation = csat_request.conversation
            
            # Marcar CSAT como expirado
            csat_request.status = 'expired'
            csat_request.save(update_fields=['status'])
            logger.info(f"[CSATTimeout] CSAT request {csat_request_id} marcado como expirado (sem resposta há {time_since_sent:.1f} minutos)")
            
            # Garantir que conversa está fechada
            if conversation.status != 'closed':
                conversation.status = 'closed'
                conversation.save(update_fields=['status'])
            
            # Migrar histórico para Supabase
            try:
                from core.chat_migration_service import chat_migration_service
                migration_result = chat_migration_service.encerrar_e_migrar(
                    conversation_id=conversation.id,
                    metadata={
                        'migrado_apos_csat_timeout': True,
                        'csat_request_id': csat_request.id,
                        'timeout_minutes': time_since_sent
                    }
                )
                if migration_result.get('success'):
                    logger.info(f"[CSATTimeout] Histórico migrado para Supabase após timeout CSAT - conversa {conversation.id}")
                else:
                    logger.warning(f"[CSATTimeout] Falha ao migrar histórico após timeout CSAT: {migration_result.get('errors', [])}")
            except Exception as migration_err:
                logger.error(f"[CSATTimeout] Erro ao migrar histórico após timeout CSAT: {migration_err}", exc_info=True)
                
    except CSATRequest.DoesNotExist:
        logger.warning(f"[CSATTimeout] CSAT request {csat_request_id} não encontrado")
        return
    except Exception as e:
        logger.error(f"[CSATTimeout] Erro ao processar timeout CSAT {csat_request_id}: {e}", exc_info=True)


@dramatiq.actor(
    actor_name="send_csat_message",
    queue_name="niochat_csat_queue",
    time_limit=60000  # 60 segundos - retry configurado no middleware
)
def send_csat_message(csat_request_id: int):
    """
    Tarefa Dramatiq para enviar mensagem de solicitação CSAT
    Usa fila dedicada 'niochat_csat_queue' para isolamento e melhor controle de workers
    Retry e backoff são gerenciados pelo middleware Retries configurado em dramatiq_config.py
    """
    # Log quando o ator é registrado (isso acontece na importação)
    if not hasattr(send_csat_message, '_logged_registration'):
        try:
            broker = dramatiq.get_broker()
            actors = broker.actors
            if 'send_csat_message' in actors:
                queue_name = actors['send_csat_message'].queue_name
                logger.info(f"✓ Ator 'send_csat_message' registrado na fila '{queue_name}'")
            else:
                logger.warning(f"⚠ Ator decorado mas não encontrado no broker. Atores: {list(actors.keys())}")
        except Exception as e:
            logger.warning(f"Erro ao verificar registro: {e}")
        send_csat_message._logged_registration = True
    
    logger.info(f"Processando CSAT request {csat_request_id}")
    
    try:
        from django.db import transaction
        
        # Verificar se o CSATRequest existe antes de tentar fazer lock
        try:
            csat_request_exists = CSATRequest.objects.filter(id=csat_request_id).exists()
            if not csat_request_exists:
                logger.warning(f"CSAT request {csat_request_id} não existe no banco de dados. Pode ter sido deletado ou nunca foi criado.")
                return
        except Exception as check_err:
            logger.warning(f"Erro ao verificar existência do CSAT request {csat_request_id}: {check_err}")
            # Continuar tentando buscar mesmo assim
        
        # Buscar CSAT request com lock para evitar race conditions
        with transaction.atomic():
            csat_request = CSATRequest.objects.select_for_update().get(id=csat_request_id)
            
            # Validar status antes de processar
            if csat_request.status != 'pending':
                logger.info(
                    f"CSAT request {csat_request_id} não está pendente "
                    f"(status: {csat_request.status}), ignorando"
                )
                return
            
            # Validar se a conversa ainda está fechada
            conversation = csat_request.conversation
            if conversation.status != 'closed':
                logger.warning(
                    f"Conversa {conversation.id} não está fechada "
                    f"(status: {conversation.status}), expirando CSAT {csat_request_id}"
                )
                csat_request.status = 'expired'
                csat_request.save(update_fields=['status'])
                return
            
            # Verificação de timing: se scheduled_send_at foi definido, verificar se já é hora
            # (O Dramatiq já gerencia isso com delay/eta, mas esta é uma verificação de segurança)
            if csat_request.scheduled_send_at:
                now_utc = timezone.now()
                scheduled_utc = csat_request.scheduled_send_at
                time_diff = (scheduled_utc - now_utc).total_seconds()
                
                # Se ainda não é hora (com margem de 10 segundos para evitar problemas de sincronização)
                if time_diff > 10:
                    logger.warning(
                        f"CSAT request {csat_request_id} chegou antes do horário agendado. "
                        f"Re-agendando com delay de {int(time_diff * 1000)}ms"
                    )
                    # Re-agendar para o horário correto
                    delay_ms = max(0, int(time_diff * 1000))
                    if delay_ms > 0:
                        send_csat_message.send_with_options(
                            args=(csat_request_id,),
                            delay=delay_ms
                        )
                        return
        
        # Buscar novamente fora da transação para evitar lock prolongado durante envio
        csat_request = CSATRequest.objects.select_related('provedor', 'contact', 'conversation').get(id=csat_request_id)
        
        # Montar mensagem de feedback
        provedor = csat_request.provedor
        contact = csat_request.contact
        
        # Obter nome do contato
        contact_name = contact.name or "Cliente"
        provedor_name = provedor.nome
        
        csat_message = (
            f"Olá {contact_name}! Gostaríamos de saber como foi seu atendimento na {provedor_name}. "
            f"Sua opinião faz toda a diferença para melhorarmos nossos serviços!\n\n"
            f"😡 Péssimo | 😕 Ruim | 😐 Regular | 🙂 Bom | 🤩 Excelente"
        )
        
        # Enviar mensagem baseado no canal
        success = False
        error_detail = None
        
        try:
            if csat_request.channel_type in ['whatsapp', 'whatsapp_oficial', 'whatsapp_session']:
                logger.info(f"Enviando CSAT {csat_request_id} via WhatsApp ({csat_request.channel_type}) para contato {contact.id}")
                success = _send_whatsapp_csat(csat_request, csat_message)
            elif csat_request.channel_type == 'telegram':
                logger.info(f"Enviando CSAT {csat_request_id} via Telegram para contato {contact.id}")
                success = _send_telegram_csat(csat_request, csat_message)
            else:
                logger.warning(
                    f"Canal {csat_request.channel_type} não suportado para CSAT {csat_request_id}"
                )
                error_detail = f"Canal {csat_request.channel_type} não suportado"
        except Exception as send_error:
            logger.error(
                f"Erro ao enviar CSAT {csat_request_id} via {csat_request.channel_type}: {send_error}",
                exc_info=True
            )
            error_detail = str(send_error)
            success = False
        
        # Atualizar status de forma atômica
        with transaction.atomic():
            csat_request = CSATRequest.objects.select_for_update().get(id=csat_request_id)
            
            if success:
                csat_request.status = 'sent'
                csat_request.sent_at = timezone.now()
                csat_request.save(update_fields=['status', 'sent_at'])
                logger.info(
                    f"CSAT {csat_request_id} enviado com sucesso para contato {contact.id} "
                    f"via {csat_request.channel_type}"
                )
                
                # Agendar migração automática após 5 minutos se não houver resposta
                try:
                    from datetime import timedelta
                    timeout_delay_ms = 5 * 60 * 1000  # 5 minutos em milissegundos
                    
                    migrate_conversation_after_csat_timeout.send_with_options(
                        args=(csat_request_id,),
                        delay=timeout_delay_ms
                    )
                    logger.info(
                        f"[CSAT] Migração automática agendada para CSAT {csat_request_id} "
                        f"após 5 minutos sem resposta"
                    )
                except Exception as schedule_err:
                    logger.warning(
                        f"[CSAT] Erro ao agendar migração automática para CSAT {csat_request_id}: {schedule_err}"
                    )
                    # Não bloquear - continuar mesmo se falhar o agendamento
            else:
                # Não marcar como failed imediatamente - deixar retry do middleware tentar novamente
                # Apenas logar o erro
                logger.error(
                    f"Falha ao enviar CSAT {csat_request_id}: {error_detail or 'Erro desconhecido'}"
                )
                # Lançar exceção para que o middleware de retry processe
                raise Exception(f"Falha ao enviar CSAT: {error_detail or 'Erro desconhecido'}")
            
    except CSATRequest.DoesNotExist:
        logger.warning(f"CSAT request {csat_request_id} não encontrado no banco de dados. Pode ter sido deletado ou nunca foi criado. Ignorando.")
        # Não lançar exceção - request não existe, não há o que fazer
        # Isso pode acontecer se:
        # 1. O CSATRequest foi deletado antes do processamento (ex: limpeza de dados)
        # 2. O CSATRequest nunca foi criado corretamente
        # 3. Há um problema de timing entre criação e processamento
        return
    except Exception as e:
        logger.error(
            f"Erro ao processar CSAT {csat_request_id}: {e}",
            exc_info=True
        )
        # Re-lançar exceção para que o middleware de retry processe
        raise


def _send_whatsapp_csat(csat_request: CSATRequest, message: str) -> bool:
    """
    Enviar mensagem CSAT via WhatsApp usando UazapiClient
    """
    try:
        from integrations.models import WhatsAppIntegration
        
        provedor = csat_request.provedor
        
        # Buscar integração WhatsApp do provedor (primeiro no model, depois no JSON)
        whatsapp_integration = WhatsAppIntegration.objects.filter(
            provedor=provedor
        ).first()
        
        # Obter credenciais
        if whatsapp_integration:
            # Usar dados do model WhatsAppIntegration
            uazapi_url = whatsapp_integration.settings.get('whatsapp_url') or whatsapp_integration.webhook_url
            uazapi_token = whatsapp_integration.access_token
            instance_name = whatsapp_integration.instance_name
        else:
            # Fallback para integracoes_externas (campo JSON do Provedor)
            integracoes = provedor.integracoes_externas or {}
            uazapi_url = integracoes.get('whatsapp_url')
            uazapi_token = integracoes.get('whatsapp_token')
            instance_name = integracoes.get('instance') or integracoes.get('instance_name')
        
        if not uazapi_url or not uazapi_token:
            logger.error(f"No WhatsApp integration found for provider {provedor.id}. Missing URL or token.")
            return False
        
        # Se não tiver instance_name, tentar buscar do canal da conversa
        if not instance_name and csat_request.conversation.inbox:
            from core.models import Canal
            # Buscar canal WhatsApp relacionado ao inbox
            canal = Canal.objects.filter(
                provedor=provedor,
                tipo__in=['whatsapp', 'whatsapp_session', 'whatsapp_oficial'],
                ativo=True
            ).first()
            
            if canal:
                # Buscar instance_id dos dados_extras do canal
                instance_name = canal.dados_extras.get('instance_id') or canal.nome
        
        # Obter dados de contato
        contact = csat_request.contact
        phone_number = contact.additional_attributes.get('sender_lid') or contact.phone
        
        if not phone_number:
            logger.error(f"No phone number found for contact {contact.id}")
            return False
        
        # Enviar via Uazapi
        client = UazapiClient(
            base_url=uazapi_url,
            token=uazapi_token
        )
        
        result = client.enviar_mensagem(
            numero=phone_number,
            texto=message,
            instance_id=instance_name
        )
        
        if result:
            logger.info(
                f"CSAT enviado via WhatsApp: provedor={csat_request.provedor.id}, "
                f"contato={csat_request.contact.id}, instance={instance_name}"
            )
        else:
            logger.warning(
                f"Falha ao enviar CSAT via WhatsApp: provedor={csat_request.provedor.id}, "
                f"contato={csat_request.contact.id}, instance={instance_name}, telefone={phone_number}"
            )
        
        return result
        
    except Exception as e:
        logger.error(
            f"Erro ao enviar CSAT via WhatsApp (request {csat_request.id}): {e}",
            exc_info=True
        )
        return False


def _send_telegram_csat(csat_request: CSATRequest, message: str) -> bool:
    """
    Enviar mensagem CSAT via Telegram
    TODO: Implementar quando necessário
    """
    logger.warning(f"Envio via Telegram não implementado para CSAT request {csat_request.id}")
    return False


@dramatiq.actor(
    actor_name="test_send_message",
    queue_name="niochat_conversation_queue",
    time_limit=30000  # 30 segundos
)
def test_send_message(phone_number: str, message: str, provedor_id: int = None):
    """
    Tarefa de teste para enviar mensagem via WhatsApp
    Usa fila 'niochat_conversation_queue' para teste
    """
    logger.info(f"[TEST] Enviando mensagem de teste para {phone_number}")
    
    try:
        from core.models import Provedor
        
        # Buscar provedor
        if provedor_id:
            provedor = Provedor.objects.get(id=provedor_id)
        else:
            # Usar primeiro provedor disponível
            provedor = Provedor.objects.first()
        
        if not provedor:
            logger.error("[TEST] Nenhum provedor encontrado")
            return False
        
        # Obter configurações Uazapi
        integracoes = provedor.integracoes_externas or {}
        uazapi_url = integracoes.get('whatsapp_url')
        uazapi_token = integracoes.get('whatsapp_token')
        instance_name = integracoes.get('whatsapp_instance')
        
        if not uazapi_url or not uazapi_token:
            logger.error(f"[TEST] Configurações Uazapi não encontradas para provedor {provedor.id}")
            return False
        
        # Enviar mensagem
        client = UazapiClient(base_url=uazapi_url, token=uazapi_token)
        result = client.enviar_mensagem(
            numero=phone_number,
            texto=message,
            instance_id=instance_name
        )
        
        if result:
            logger.info(f"[TEST] Mensagem enviada com sucesso para {phone_number}")
        else:
            logger.warning(f"[TEST] Falha ao enviar mensagem para {phone_number}")
        
        return result
        
    except Exception as e:
        logger.error(f"[TEST] Erro ao enviar mensagem de teste: {e}", exc_info=True)
        return False


@dramatiq.actor(
    actor_name="encerrar_conversa_timeout",
    queue_name="niochat_conversation_queue",
    time_limit=30000  # 30 segundos
)
def encerrar_conversa_timeout(conversation_id: int, ultima_mensagem_ia_id: int = None):
    """
    Tarefa Dramatiq para encerrar conversa automaticamente após 3 minutos de timeout
    Usa fila dedicada 'niochat_conversation_queue' para isolamento
    """
    logger.info(f"[TIMEOUT 3MIN] Verificando se deve encerrar conversa {conversation_id}")
    
    try:
        from django.db import transaction
        from core.models import AuditLog
        from core.supabase_service import supabase_service
        
        with transaction.atomic():
            # Buscar conversa com lock para evitar race conditions
            conversation = Conversation.objects.select_for_update().select_related(
                'inbox', 'inbox__provedor', 'contact'
            ).get(id=conversation_id)
            
            # Verificar se a conversa já está fechada
            if conversation.status == 'closed':
                logger.info(f"[TIMEOUT 3MIN] Conversa {conversation_id} já está fechada, ignorando")
                return
            
            # Verificar se houve nova mensagem do cliente após a pergunta de finalização
            # Se houver, não encerrar (cliente respondeu antes do timeout)
            if ultima_mensagem_ia_id:
                from conversations.models import Message
                try:
                    ultima_mensagem_ia = Message.objects.get(id=ultima_mensagem_ia_id)
                    # Verificar se há mensagens do cliente após a última mensagem da IA
                    mensagens_apos = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=True,
                        created_at__gt=ultima_mensagem_ia.created_at
                    ).exists()
                    
                    if mensagens_apos:
                        logger.info(
                            f"[TIMEOUT 3MIN] Cliente respondeu antes do timeout na conversa {conversation_id}, "
                            f"cancelando encerramento automático"
                        )
                        return
                except Message.DoesNotExist:
                    logger.warning(f"[TIMEOUT 3MIN] Mensagem IA {ultima_mensagem_ia_id} não encontrada")
            
            # Encerrar conversa
            conversation.status = 'closed'
            conversation.save(update_fields=['status'])
            
            # Calcular duração
            duracao = None
            if conversation.created_at:
                duracao = timezone.now() - conversation.created_at
            
            # Contar mensagens
            message_count = conversation.messages.count()
            
            # Criar AuditLog (verificar se já existe para evitar duplicação)
            try:
                # Verificar se já existe um AuditLog para esta conversa com esta ação
                existing_log = AuditLog.objects.filter(
                    conversation_id=conversation.id,
                    action='conversation_closed_timeout'
                ).first()
                
                # Só criar se não existir
                if not existing_log:
                    details_text = (
                        f"Conversa encerrada automaticamente por timeout de 3 minutos "
                        f"com {conversation.contact.name} via {conversation.inbox.channel_type}"
                    )
                    if duracao:
                        details_text += f" | Duração: {duracao}"
                    if message_count:
                        details_text += f" | Mensagens: {message_count}"
                    
                    AuditLog.objects.create(
                        user=None,  # Sistema automático
                        action='conversation_closed_timeout',
                        ip_address='127.0.0.1',
                        details=details_text,
                        provedor=conversation.inbox.provedor if conversation.inbox else None,
                        conversation_id=conversation.id,
                        contact_name=conversation.contact.name if conversation.contact else 'Desconhecido',
                        channel_type=conversation.inbox.channel_type if conversation.inbox else 'Desconhecido'
                    )
                else:
                    logger.info(f"[TIMEOUT 3MIN] AuditLog já existe para conversa {conversation.id}, evitando duplicação")
            except Exception as audit_err:
                logger.error(f"[TIMEOUT 3MIN] Erro ao criar/verificar AuditLog: {audit_err}")
            
            # Enviar auditoria para Supabase
            try:
                supabase_service.save_audit(
                    provedor_id=conversation.inbox.provedor_id if conversation.inbox else None,
                    conversation_id=conversation.id,
                    action='conversation_closed_timeout',
                    details={
                        'motivo': 'Cliente não respondeu após confirmação de resolução (timeout 3min)',
                        'encerrado_por': 'sistema_automatico',
                        'duracao_minutos': round(duracao.total_seconds() / 60, 2) if duracao else None,
                        'quantidade_mensagens': message_count
                    },
                    user_id=None,
                    ended_at_iso=timezone.now().isoformat()
                )
            except Exception as sup_err:
                logger.warning(f"[TIMEOUT 3MIN] Erro ao enviar auditoria para Supabase: {sup_err}")
            
                # Limpar memória Redis/DB com normalização estrita
                try:
                    from core.redis_memory_service import redis_memory_service
                    provedor_id = conversation.inbox.provedor_id if conversation.inbox else None
                    original_channel = conversation.inbox.channel_type if conversation.inbox else "whatsapp"
                    channel = redis_memory_service.normalize_channel(original_channel)
                    phone = conversation.contact.phone if conversation.contact else "unknown"
                    
                    # Nome amigável para o log
                    friendly_channel = "WhatsApp Oficial" if original_channel == "whatsapp_oficial" else original_channel.capitalize()
                    
                    redis_memory_service.clear_memory_sync(provedor_id, conversation_id, channel, phone)
                    logger.info(f"[TIMEOUT 3MIN] Memória limpa para conversa {conversation_id} ({friendly_channel}:{phone})")
                except Exception as redis_err:
                    logger.warning(f"[TIMEOUT 3MIN] Erro ao limpar memória: {redis_err}")
            
            logger.info(
                f"[TIMEOUT 3MIN] Conversa {conversation_id} encerrada automaticamente "
                f"após timeout de 3 minutos"
            )
            
    except Conversation.DoesNotExist:
        logger.error(f"[TIMEOUT 3MIN] Conversa {conversation_id} não encontrada no banco de dados")
        return
    except Exception as e:
        logger.error(
            f"[TIMEOUT 3MIN] Erro ao encerrar conversa {conversation_id} por timeout: {e}",
            exc_info=True
        )


@dramatiq.actor(
    actor_name="finalize_single_conversation",
    queue_name="niochat_conversation_queue",
    time_limit=60000,  # 1 minuto
    max_retries=2
)
def finalize_single_conversation(conversation_id: int):
    """
    Task assíncrona para finalizar uma conversa específica após a janela de tolerância.
    Usada quando a IA encerra um atendimento - agendada com delay de 2 minutos.
    """
    # Log quando o ator é registrado (isso acontece na importação)
    if not hasattr(finalize_single_conversation, '_logged_registration'):
        try:
            broker = dramatiq.get_broker()
            actors = broker.actors
            if 'finalize_single_conversation' in actors:
                queue_name = actors['finalize_single_conversation'].queue_name
                logger.info(f"✓ Ator 'finalize_single_conversation' registrado na fila '{queue_name}'")
            else:
                logger.warning(f"⚠ Ator decorado mas não encontrado no broker. Atores: {list(actors.keys())}")
        except Exception as e:
            logger.warning(f"Erro ao verificar registro: {e}")
        finalize_single_conversation._logged_registration = True
    
    try:
        from conversations.closing_service import closing_service
        from conversations.models import Conversation
        
        logger.info(f"[FINALIZE_SINGLE] Finalizando conversa {conversation_id} após janela de tolerância")
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            logger.warning(f"[FINALIZE_SINGLE] Conversa {conversation_id} não encontrada")
            return
        
        # Finalizar a conversa (cria CSAT, migra, limpa Redis)
        if closing_service.finalize_closing(conversation):
            logger.info(f"[FINALIZE_SINGLE] ✓ Conversa {conversation_id} finalizada com sucesso")
        else:
            logger.warning(f"[FINALIZE_SINGLE] ✗ Falha ao finalizar conversa {conversation_id}")
            
    except Exception as e:
        logger.error(
            f"[FINALIZE_SINGLE] Erro ao finalizar conversa {conversation_id}: {e}",
            exc_info=True
        )


@dramatiq.actor(
    time_limit=300000,  # 5 minutos
    max_retries=3,
    min_backoff=60000,  # 1 minuto
    max_backoff=300000  # 5 minutos
)
def finalize_closing_conversations():
    """
    Task assíncrona para finalizar conversas em estado 'closing' que excederam a janela de tolerância.
    
    Esta task deve ser executada periodicamente (ex: a cada 5 minutos) para processar
    conversas que estão em estado intermediário 'closing' e finalizá-las definitivamente.
    
    A task processa todas as conversas em 'closing' que excederam a janela de tolerância
    (padrão: 2 minutos) e as marca como 'closed', permitindo que sejam migradas para Supabase.
    """
    try:
        from conversations.closing_service import closing_service
        
        logger.info("[FINALIZE_CLOSING] Iniciando processamento de conversas em 'closing'...")
        
        # Processar conversas em 'closing' que excederam a tolerância
        stats = closing_service.process_final_closures()
        
        logger.info(
            f"[FINALIZE_CLOSING] Processamento concluído: "
            f"{stats['finalized']} finalizadas, {stats['errors']} erros "
            f"(total encontrado: {stats['total_found']})"
        )
        
        return stats
        
    except Exception as e:
        logger.error(
            f"[FINALIZE_CLOSING] Erro ao processar conversas em 'closing': {e}",
            exc_info=True
        )
        return {'error': str(e)}





@dramatiq.actor(
    actor_name="notify_message_event",
    queue_name="niochat_conversation_queue",
    time_limit=30000,  # 30 segundos
    max_retries=3
)
def notify_message_event(message_id: int):
    """
    Tarefa Dramatiq para notificar o painel sobre novas mensagens via WebSocket.
    Substitui o uso inseguro de threads no Signal de Message.
    """
    from conversations.models import Message
    from conversations.serializers import MessageSerializer, ConversationSerializer
    from conversations.services import ConversationNotificationService
    
    try:
        # Buscar mensagem e carregar relações necessárias para garantir dados completos
        message = Message.objects.select_related(
            'conversation', 
            'conversation__contact', 
            'conversation__assignee', 
            'conversation__inbox', 
            'conversation__inbox__provedor'
        ).get(id=message_id)
        
        conversation = message.conversation
        provedor_id = conversation.inbox.provedor.id if conversation.inbox and conversation.inbox.provedor else None
        
        if not provedor_id:
            logger.debug(f"[MessageTask] Conversa {conversation.id} sem provedor, pulando")
            return

        # Serializar dados completos para o front
        message_data = MessageSerializer(message).data
        conversation_data = ConversationSerializer(conversation).data
        
        logger.info(
            f"[MessageTask] Notificando mensagem {message_id} "
            f"para conversa {conversation.id}, provedor {provedor_id}"
        )
        
        if message.is_from_customer:
            ConversationNotificationService.notify_message_received(
                provedor_id, 
                conversation.id, 
                message_data,
                conversation_data
            )
        else:
            ConversationNotificationService.notify_message_sent(
                provedor_id, 
                conversation.id, 
                message_data,
                conversation_data
            )
            
    except Message.DoesNotExist:
        logger.warning(f"[MessageTask] Mensagem {message_id} não encontrada")
    except Exception as e:
        logger.error(f"[MessageTask] Erro ao notificar mensagem {message_id}: {e}", exc_info=True)