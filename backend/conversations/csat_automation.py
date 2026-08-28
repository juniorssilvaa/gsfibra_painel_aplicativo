import logging
import json
from datetime import datetime, timedelta
from django.utils import timezone
import dramatiq
from .models import Conversation, CSATRequest, CSATFeedback
from integrations.telegram_service import TelegramService
from integrations.email_service import EmailService

logger = logging.getLogger(__name__)

class CSATAutomationService:
    """
    Serviço para automação de coleta de CSAT
    """
    
    THANK_YOU_MESSAGE = "Obrigado pelo seu feedback! Sua opinião é muito importante para nós. 😊"
    
    @classmethod
    def generate_dynamic_csat_message(cls, provedor, contact, conversation):
        """
        Gera mensagem CSAT dinâmica usando IA com contexto do cliente e provedor.
        🔒 ISOLAMENTO CORRIGIDO: Usa chave com provedor:conversation:phone
        """
        cliente_nome = contact.name
        
        try:
            from core.openai_service import OpenAIService
            from core.redis_memory_service import redis_memory_service, normalize_phone_number
            
            try:
                redis_conn = redis_memory_service.get_redis_sync()
                if redis_conn:
                    # 🔒 CORREÇÃO: Usar novo padrão com isolamento por telefone
                    phone = normalize_phone_number(contact.phone) if contact else "unknown"
                    channel = redis_memory_service.normalize_channel(conversation.inbox.channel_type if conversation and conversation.inbox else "whatsapp")
                    key = f"csat:{provedor.id}:{conversation.id}:{phone}"
                    memory_data = redis_conn.get(key)
                    if memory_data:
                        memory = json.loads(memory_data)
                        if memory.get('nome_cliente'):
                            nome_completo = memory['nome_cliente']
                            cliente_nome = nome_completo.split()[0] if nome_completo else contact.name
                            logger.info(f"Nome do cliente encontrado na memória Redis (isolado): {cliente_nome}")
                else:
                    logger.warning("Conexão Redis não disponível")
            except Exception as e:
                logger.warning(f"Erro ao buscar nome na memória Redis: {e}")
            
            context = f"""Você é um assistente da {provedor.nome} solicitando feedback CSAT.

TAREFA: Criar uma mensagem personalizada para {cliente_nome} pedindo avaliação do atendimento.

FORMATO OBRIGATÓRIO:
1. Cumprimente de forma amigável: "Olá {cliente_nome}!"
2. Mencione a empresa: "{provedor.nome}"
3. Peça feedback de forma natural e cordial
4. SEMPRE termine com esta linha EXATA (copie exatamente):
😡 Péssimo | 😕 Ruim | 😐 Regular | 🙂 Bom | 🤩 Excelente

EXEMPLO:
Olá {cliente_nome}! Como foi sua experiência com nosso atendimento da {provedor.nome}? Sua opinião é muito importante para nós!

😡 Péssimo | 😕 Ruim | 😐 Regular | 🙂 Bom | 🤩 Excelente

IMPORTANTE:
- Use no máximo 3 linhas
- Seja cordial e natural
- Não use emojis extras além dos obrigatórios
- Mantenha o tom da {provedor.nome}"""

            openai_service = OpenAIService()
            response = openai_service.generate_response_sync(
                mensagem=context,
                provedor=provedor,
                contexto={'contact': contact, 'conversation': conversation}
            )

            ai_message = response.get('resposta', '') if isinstance(response, dict) else str(response)
            required_emojis = ['😡', '😕', '😐', '🙂', '🤩']
            missing_emojis = [emoji for emoji in required_emojis if emoji not in ai_message]

            if missing_emojis:
                logger.warning(f"IA não incluiu emojis CSAT: {missing_emojis}.")
                return cls._get_fallback_message(provedor, contact, cliente_nome)
            
            return ai_message.strip()
            
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem CSAT dinâmica: {e}")
            return cls._get_fallback_message(provedor, contact, cliente_nome)
    
    @classmethod
    def _analyze_feedback_with_ai(cls, feedback_text, provedor):
        """
        Usa IA para analisar sentimento do feedback e determinar rating CSAT
        Aceita qualquer texto ou emoji do cliente
        """
        try:
            from core.openai_service import openai_service
            import re

            # Limpar o texto (remover aspas extras, espaços, etc)
            feedback_clean = str(feedback_text).strip().replace('"', '').replace("'", '').strip()

            context = f"""Você é um analisador de sentimento especializado em CSAT (Customer Satisfaction).

TAREFA: Analisar o feedback do cliente e determinar o rating CSAT de 1 a 5.

FEEDBACK DO CLIENTE: "{feedback_clean}"

ESCALA CSAT:
1 = 😡 Muito insatisfeito / Péssimo / Horrível
2 = 😕 Insatisfeito / Ruim / Decepcionado
3 = 😐 Neutro / Regular / OK / Aceitável
4 = 🙂 Satisfeito / Bom / Ótimo
5 = 🤩 Muito satisfeito / Excelente / Perfeito

INSTRUÇÕES:
- Se o cliente escreveu "Regular", "OK", "Normal" ou similar, use rating 3
- Se o cliente escreveu "Bom", "Satisfeito", "Ótimo" ou similar, use rating 4
- Se o cliente escreveu "Excelente", "Perfeito", "Amei" ou similar, use rating 5
- Se o cliente escreveu "Ruim", "Insatisfeito" ou similar, use rating 2
- Se o cliente escreveu "Péssimo", "Horrível" ou similar, use rating 1
- Aceite qualquer forma de escrita (com ou sem acentos, maiúsculas/minúsculas)
- Aceite emojis também

Responda APENAS com um número de 1 a 5:"""
            response = openai_service.generate_response_sync(
                mensagem=context,
                provedor=provedor,
                contexto={'feedback_analysis': True}
            )
            
            ai_response = response.get('resposta', '') if isinstance(response, dict) else str(response)
            # Buscar qualquer número de 1 a 5 na resposta
            rating_match = re.search(r'[1-5]', ai_response)

            if rating_match:
                rating_value = int(rating_match.group())
                emoji_map = {1: '😡', 2: '😕', 3: '😐', 4: '🙂', 5: '🤩'}
                logger.info(f"IA analisou feedback '{feedback_clean}' e retornou rating {rating_value}")
                return {'rating': rating_value, 'emoji': emoji_map[rating_value], 'ai_response': ai_response.strip()}
            
            logger.warning(f"IA não conseguiu determinar rating para: '{feedback_clean}'")
            return None
                
        except Exception as e:
            logger.error(f"Erro na análise de sentimento por IA: {e}")
            return None
    
    @classmethod
    def _get_fallback_message(cls, provedor, contact, cliente_nome=None):
        nome_usar = cliente_nome or contact.name
        return f"""Olá {nome_usar}! Como foi sua experiência com o atendimento da {provedor.nome}?

Pode deixar sua opinião em uma única mensagem:
😡 Péssimo | 😕 Ruim | 😐 Regular | 🙂 Bom | 🤩 Excelente"""
    
    EMOJI_RATINGS = {'😡': 1, '😕': 2, '😐': 3, '🙂': 4, '🤩': 5}
    
    # Mapeamento de palavras-chave para ratings
    TEXT_RATINGS = {
        # Rating 1 (Péssimo)
        'péssimo': 1, 'pessimo': 1, 'horrível': 1, 'horrivel': 1, 'terrível': 1, 'terrivel': 1,
        'ruim demais': 1, 'muito ruim': 1, 'pior': 1, 'odiei': 1, 'detestei': 1,
        # Rating 2 (Ruim)
        'ruim': 2, 'insatisfeito': 2, 'não gostei': 2, 'nao gostei': 2, 'decepcionado': 2,
        'decepcionada': 2, 'fraco': 2, 'precisa melhorar': 2, 'não recomendo': 2, 'nao recomendo': 2,
        # Rating 3 (Regular/Neutro)
        'regular': 3, 'neutro': 3, 'ok': 3, 'mais ou menos': 3, 'mais ou menos': 3,
        'aceitável': 3, 'aceitavel': 3, 'razoável': 3, 'razoavel': 3, 'mediano': 3,
        'normal': 3, 'sem comentários': 3, 'sem comentarios': 3,
        # Rating 4 (Bom)
        'bom': 4, 'muito bom': 4, 'muito boa': 4, 'satisfeito': 4, 'satisfeita': 4, 'gostei': 4, 'legal': 4,
        'ótimo': 4, 'otimo': 4, 'recomendo': 4, 'bom atendimento': 4, 'bom serviço': 4,
        'bom servico': 4, 'atendeu': 4, 'atendeu as expectativas': 4,
        # Rating 5 (Excelente)
        'excelente': 5, 'perfeito': 5, 'perfeita': 5, 'maravilhoso': 5, 'maravilhosa': 5,
        'incrível': 5, 'incrivel': 5, 'fantástico': 5, 'fantastico': 5, 'sensacional': 5,
        'muito bom': 5, 'muito bom!': 5, 'super recomendo': 5, 'top': 5, 'show': 5,
        'melhor': 5, 'amei': 5, 'adorei': 5, 'nota 10': 5, '10/10': 5
    }
    
    @classmethod
    def create_csat_request(cls, conversation):
        """
        DEPRECATED: Use CSATService.schedule_csat_request instead
        Mantido apenas para compatibilidade
        """
        try:
            from .csat_service import CSATService
            return CSATService.schedule_csat_request(conversation.id)
        except Exception as e:
            logger.error(f"Erro ao agendar CSAT request: {e}")
            return None
    
    @classmethod
    def send_csat_message(cls, csat_request_id):
        """
        Envia mensagem de solicitação de CSAT
        """
        try:
            csat_request = CSATRequest.objects.get(id=csat_request_id)
            conversation = csat_request.conversation
            contact = csat_request.contact
            provedor = csat_request.provedor
            
            if conversation.status != 'closed':
                csat_request.status = 'cancelled'
                csat_request.save()
                return False
            
            dynamic_message = cls.generate_dynamic_csat_message(provedor, contact, conversation)
            success = False
            
            if csat_request.channel_type == 'whatsapp':
                success = cls._send_whatsapp_message(provedor, contact, dynamic_message)
            elif csat_request.channel_type == 'telegram':
                success = cls._send_telegram_message(provedor, contact, dynamic_message)
            elif csat_request.channel_type == 'email':
                success = cls._send_email_message(provedor, contact, dynamic_message)
            
            csat_request.status = 'sent' if success else 'failed'
            csat_request.sent_at = timezone.now() if success else None
            csat_request.save()
            return success
                
        except Exception as e:
            logger.error(f"Erro ao enviar CSAT message: {e}")
            return False

    @classmethod
    def process_csat_response(cls, message_text, conversation, contact):
        """
        Processa resposta de CSAT do cliente
        """
        try:
            csat_request = CSATRequest.objects.filter(conversation=conversation, status='sent').first()
            if not csat_request:
                return None
            
            existing_feedback = CSATFeedback.objects.filter(conversation=conversation).first()
            if existing_feedback:
                return existing_feedback
            
            emoji_rating, rating_value = None, None
            
            # 1. Primeiro tentar detectar emoji diretamente
            for emoji, value in cls.EMOJI_RATINGS.items():
                if emoji in message_text:
                    emoji_rating, rating_value = emoji, value
                    break
            
            # 2. Se não encontrou emoji, tentar detectar palavras-chave no texto
            if not emoji_rating:
                message_lower = message_text.lower().strip()
                # Remover aspas e caracteres especiais para comparação
                message_clean = message_lower.replace('"', '').replace("'", '').replace('"', '').strip()
                
                # Procurar palavras-chave (ordem de prioridade: rating 5 -> 1)
                for keyword, value in sorted(cls.TEXT_RATINGS.items(), key=lambda x: x[1], reverse=True):
                    if keyword in message_clean:
                        rating_value = value
                        emoji_map = {1: '😡', 2: '😕', 3: '😐', 4: '🙂', 5: '🤩'}
                        emoji_rating = emoji_map[value]
                        logger.info(f"CSAT detectado por palavra-chave: '{keyword}' = rating {value}")
                        break
            
            # 3. Se ainda não encontrou, usar IA para analisar sentimento
            if not emoji_rating:
                ai_analysis = cls._analyze_feedback_with_ai(message_text, csat_request.provedor)
                if ai_analysis:
                    emoji_rating, rating_value = ai_analysis['emoji'], ai_analysis['rating']
                    logger.info(f"CSAT detectado por IA: rating {rating_value}")
            
            # 4. Se nada funcionou, usar neutro como padrão
            if not emoji_rating:
                emoji_rating, rating_value = '😐', 3
                logger.info(f"CSAT usando padrão neutro (rating 3) para: '{message_text}'")
            
            response_time = timezone.now() - csat_request.conversation_ended_at
            response_time_minutes = int(response_time.total_seconds() / 60)
            
            feedback = CSATFeedback.objects.create(
                conversation=conversation,
                contact=contact,
                provedor=csat_request.provedor,
                emoji_rating=emoji_rating,
                rating_value=rating_value,
                original_message=message_text,
                channel_type=csat_request.channel_type,
                conversation_ended_at=csat_request.conversation_ended_at,
                response_time_minutes=response_time_minutes
            )
            
            csat_request.status = 'completed'
            csat_request.completed_at = timezone.now()
            csat_request.save()

            from core.models import AuditLog
            audit_log = AuditLog.objects.filter(
                conversation_id=conversation.id,
                action__in=['conversation_closed_agent', 'conversation_closed_ai']
            ).first()
            if audit_log:
                audit_log.csat_rating = rating_value
                audit_log.save()
            
            # Salvar no Supabase
            try:
                from core.supabase_service import SupabaseService
                supabase_service = SupabaseService()
                success = supabase_service.save_csat(
                    provedor_id=csat_request.provedor.id,
                    conversation_id=conversation.id,
                    contact_id=contact.id,
                    emoji_rating=emoji_rating,
                    rating_value=rating_value,
                    feedback_sent_at_iso=timezone.now().isoformat(),
                    original_message=message_text,  # Mensagem original do cliente
                    contact_name=contact.name or contact.phone or 'Cliente'  # Nome do contato
                )
                if success:
                    logger.info(f"✓ CSAT enviado para Supabase com sucesso: conversa {conversation.id} - Rating: {rating_value} ({emoji_rating})")
                else:
                    logger.error(f"✗ Falha ao enviar CSAT para Supabase: conversa {conversation.id} - Rating: {rating_value}")
            except Exception as e:
                logger.error(f"✗ Erro ao enviar CSAT para Supabase: {e}", exc_info=True)
            
            cls._send_thank_you_message(csat_request, contact)
            return feedback
            
        except Exception as e:
            logger.error(f"Erro ao processar CSAT response: {e}")
            return None

    @classmethod
    def _send_thank_you_message(cls, csat_request, contact):
        """
        Envia mensagem de agradecimento após feedback CSAT.
        IMPORTANTE: Não reabre a conversa - apenas agradece sem alterar status.
        """
        try:
            provedor = csat_request.provedor
            conversation = csat_request.conversation
            
            logger.info(f"[CSAT] Enviando agradecimento CSAT para {contact.name} via {csat_request.channel_type}")
            
            # Garantir que conversa permaneça fechada (não reabrir)
            if conversation.status != 'closed':
                conversation.status = 'closed'
                conversation.save(update_fields=['status'])
                logger.info(f"[CSAT] Conversa {conversation.id} mantida como 'closed' após agradecimento CSAT")
            
            if csat_request.channel_type == 'whatsapp':
                # Tentar usar WhatsApp Cloud API primeiro (WhatsApp Official)
                success = False
                try:
                    from core.models import Canal
                    canal = Canal.objects.filter(
                        provedor=provedor,
                        tipo="whatsapp_oficial",
                        ativo=True
                    ).first()
                    
                    if canal and canal.token and canal.phone_number_id:
                        # Usar WhatsApp Cloud API (Oficial)
                        from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api
                        success, response = send_via_whatsapp_cloud_api(
                            conversation=conversation,
                            content=cls.THANK_YOU_MESSAGE,
                            message_type='text'
                        )
                        if success:
                            logger.info(f"[CSAT] Agradecimento CSAT enviado com sucesso via WhatsApp Cloud API para {contact.name}")
                    else:
                        # Fallback para Uazapi (não oficial)
                        success = cls._send_whatsapp_message(provedor, contact, cls.THANK_YOU_MESSAGE)
                        if success:
                            logger.info(f"[CSAT] Agradecimento CSAT enviado com sucesso via WhatsApp (Uazapi) para {contact.name}")
                except Exception as api_err:
                    logger.warning(f"[CSAT] Erro ao enviar via WhatsApp Cloud API: {api_err}, tentando fallback...")
                    # Fallback para Uazapi
                    try:
                        success = cls._send_whatsapp_message(provedor, contact, cls.THANK_YOU_MESSAGE)
                        if success:
                            logger.info(f"[CSAT] Agradecimento CSAT enviado com sucesso via WhatsApp (fallback) para {contact.name}")
                    except Exception as fallback_err:
                        logger.error(f"[CSAT] Falha no fallback também: {fallback_err}")
                        success = False
                
                if not success:
                    logger.error(f"[CSAT] Falha ao enviar agradecimento CSAT via WhatsApp para {contact.name}")
            elif csat_request.channel_type == 'telegram':
                cls._send_telegram_message(provedor, contact, cls.THANK_YOU_MESSAGE)
            elif csat_request.channel_type == 'email':
                cls._send_email_message(provedor, contact, cls.THANK_YOU_MESSAGE)
            
            # Garantir novamente que conversa permaneça fechada após envio
            if conversation.status != 'closed':
                conversation.status = 'closed'
                conversation.save(update_fields=['status'])
                logger.info(f"[CSAT] Conversa {conversation.id} mantida como 'closed' após envio de agradecimento")
                
        except Exception as e:
            logger.error(f"[CSAT] Erro ao enviar mensagem de agradecimento: {e}", exc_info=True)

    @classmethod
    def _send_whatsapp_message(cls, provedor, contact, message):
        try:
            from core.uazapi_client import UazapiClient
            from integrations.models import WhatsAppIntegration
            
            # Tentar obter configurações do WhatsAppIntegration primeiro
            whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
            
            if whatsapp_integration:
                base_url = whatsapp_integration.settings.get('whatsapp_url') or whatsapp_integration.webhook_url
                token = whatsapp_integration.access_token
                instance = whatsapp_integration.instance_name
            else:
                # Fallback para integracoes_externas
                config = provedor.integracoes_externas or {}
                base_url = config.get('whatsapp_url')
                token = config.get('whatsapp_token')
                instance = config.get('whatsapp_instance')
            
            if not base_url or not token or not instance:
                logger.error(f"Configurações WhatsApp incompletas para provedor {provedor.id}")
                return False
            
            client = UazapiClient(base_url=base_url, token=token)
            result = client.enviar_mensagem(
                numero=contact.phone,
                texto=message,
                instance_id=instance
            )
            return result is not None
        except Exception as e:
            logger.error(f"Erro ao enviar WhatsApp message: {e}", exc_info=True)
            return False
