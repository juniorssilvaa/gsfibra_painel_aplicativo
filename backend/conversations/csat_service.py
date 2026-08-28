"""
Serviço para gerenciar CSAT (Customer Satisfaction Score)
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from core.models import Provedor
from .models import Conversation, Contact, CSATFeedback, CSATRequest

logger = logging.getLogger(__name__)


class CSATService:
    """
    Serviço para gerenciar coleta e envio de feedback CSAT
    """

    CSAT_EMOJIS = ['😡', '😕', '😐', '🙂', '🤩']
    EMOJI_RATINGS = {'😡': 1, '😕': 2, '😐': 3, '🙂': 4, '🤩': 5}
    DELAY_MINUTES = 2  # tempo para envio do CSAT após encerramento

    # ===========================================================================================
    # AGENDAR ENVIO DE CSAT
    # ===========================================================================================
    @classmethod
    def schedule_csat_request(cls, conversation_id: int, ended_by_user_id: int = None):
        """
        Cria e agenda uma solicitação de CSAT para uma conversa encerrada.
        """

        try:
            with transaction.atomic():

                # 1️⃣ BLOQUEAR APENAS A LINHA DA CONVERSA — sem joins
                locked_conv = (
                    Conversation.objects
                    .select_for_update()
                    .only("id", "status", "inbox_id", "contact_id")
                    .get(id=conversation_id)
                )

                # 2️⃣ RECARREGAR COM RELACIONAMENTOS (sem FOR UPDATE)
                conversation = (
                    Conversation.objects
                    .select_related("inbox", "inbox__provedor", "contact")
                    .get(id=conversation_id)
                )

                # 3️⃣ VERIFICAR DUPLICIDADE (apenas em produção)
                from django.conf import settings
                
                if not settings.DEBUG:
                    # PRODUÇÃO: Verificar se já existe CSAT para esta conversa
                    # OU se foi enviado CSAT para este contato há menos de 24 horas
                    from datetime import timedelta
                    now = timezone.now()
                    twenty_four_hours_ago = now - timedelta(hours=24)
                    
                    # Verificar CSATs para a mesma conversa
                    existing_for_conversation = CSATRequest.objects.filter(
                        conversation=conversation
                    ).first()
                    
                    if existing_for_conversation:
                        logger.info(
                            f"[CSAT] Solicitação já existe para conversa {conversation_id} "
                            f"(id={existing_for_conversation.id}, status={existing_for_conversation.status})"
                        )
                        return existing_for_conversation
                    
                    # Verificar CSATs enviados para o mesmo contato nas últimas 24 horas
                    recent_csat_for_contact = CSATRequest.objects.filter(
                        contact=conversation.contact,
                        provedor=conversation.inbox.provedor,
                        sent_at__gte=twenty_four_hours_ago,
                        status__in=['sent', 'completed', 'responded']
                    ).order_by('-sent_at').first()
                    
                    if recent_csat_for_contact:
                        time_since_last = (now - recent_csat_for_contact.sent_at).total_seconds() / 3600
                        logger.info(
                            f"[CSAT] CSAT já enviado para contato {conversation.contact.id} há {time_since_last:.1f} horas. "
                            f"É necessário aguardar 24 horas entre envios (em produção)."
                        )
                        return recent_csat_for_contact
                else:
                    # DESENVOLVIMENTO: Permitir CSATs repetidos para facilitar testes
                    logger.info(
                        f"[CSAT] Modo desenvolvimento (DEBUG=True): permitindo CSAT repetido para conversa {conversation_id}"
                    )

                # 4️⃣ Validar status
                if conversation.status != "closed":
                    logger.warning(
                        f"[CSAT] Conversa {conversation_id} não está fechada — status={conversation.status}"
                    )
                    return None

                # 5️⃣ Validar provedor
                if not conversation.inbox or not conversation.inbox.provedor:
                    logger.error(
                        f"[CSAT] Conversa {conversation_id} sem inbox/provedor. Não é possível agendar CSAT."
                    )
                    return None

                # 6️⃣ Agendamento
                ended_at = timezone.now()
                scheduled_send_at = ended_at + timedelta(minutes=cls.DELAY_MINUTES)

                channel_type = getattr(conversation.inbox, "channel_type", "whatsapp")

                # 7️⃣ Criar solicitação
                csat_request = CSATRequest.objects.create(
                    conversation=conversation,
                    contact=conversation.contact,
                    provedor=conversation.inbox.provedor,
                    conversation_ended_at=ended_at,
                    scheduled_send_at=scheduled_send_at,
                    channel_type=channel_type,
                    status="pending",
                )

                logger.info(
                    f"[CSAT] Criado CSATRequest id={csat_request.id} para conversa {conversation.id}, "
                    f"envio marcado para {scheduled_send_at}"
                )

            # ==================================================================================
            # ENVIAR PARA DRAMATIQ (FORA DA TRANSACTION)
            # ==================================================================================
            try:
                import dramatiq
                from niochat.dramatiq_config import broker as configured_broker
                from .dramatiq_tasks import send_csat_message

                # Garantir que o broker correto está configurado globalmente
                current_broker = dramatiq.get_broker()
                if current_broker is not configured_broker:
                    dramatiq.set_broker(configured_broker)
                    # Re-registrar o ator com o broker correto
                    send_csat_message.broker = configured_broker

                now_utc = timezone.now()
                delay_ms = max(0, int((scheduled_send_at - now_utc).total_seconds() * 1000))

                if delay_ms > 0:
                    message = send_csat_message.send_with_options(
                        args=(csat_request.id,), delay=delay_ms
                    )
                    logger.info(
                        f"[CSAT] CSATRequest {csat_request.id} agendado com delay={delay_ms}ms."
                    )
                else:
                    message = send_csat_message.send(csat_request.id)
                    logger.info(
                        f"[CSAT] CSATRequest {csat_request.id} enviado imediatamente (atrasado)."
                    )

            except Exception as send_err:
                logger.error(f"[CSAT] Erro ao enviar CSATRequest ao Dramatiq: {send_err}", exc_info=True)

            return csat_request

        except Conversation.DoesNotExist:
            logger.error(f"[CSAT] Conversa {conversation_id} não encontrada.")
            return None

        except Exception as e:
            logger.error(f"[CSAT] Erro ao agendar CSAT: {e}", exc_info=True)
            return None

    # ===========================================================================================
    # PROCESSAR RESPOSTA DO CLIENTE
    # ===========================================================================================
    @classmethod
    def process_csat_response(cls, message_content: str, contact: Contact, conversation: Conversation):
        """
        Processa uma resposta de CSAT enviada pelo cliente.
        """

        try:
            detected_emoji = next(
                (emoji for emoji in cls.CSAT_EMOJIS if emoji in message_content), None
            )

            if not detected_emoji:
                logger.info(f"[CSAT] Nenhum emoji CSAT encontrado na mensagem: {message_content}")
                return None

            csat_request = CSATRequest.objects.filter(
                conversation=conversation,
                contact=contact,
                status__in=["pending", "sent"],
            ).first()

            if not csat_request:
                logger.info(f"[CSAT] Nenhum CSATRequest pendente para contact={contact.id}")
                return None

            response_time = (
                (timezone.now() - csat_request.sent_at).total_seconds() / 60
                if csat_request.sent_at else 0
            )

            rating_value = cls.EMOJI_RATINGS.get(detected_emoji, 0)

            with transaction.atomic():
                feedback = CSATFeedback.objects.create(
                    conversation=conversation,
                    contact=contact,
                    provedor=conversation.inbox.provedor,
                    emoji_rating=detected_emoji,
                    rating_value=rating_value,
                    channel_type=csat_request.channel_type,
                    conversation_ended_at=csat_request.conversation_ended_at,
                    response_time_minutes=int(response_time),
                    original_message=message_content,
                    feedback_sent_at=timezone.now(),
                )

                csat_request.status = "responded"
                csat_request.responded_at = timezone.now()
                csat_request.csat_feedback = feedback
                csat_request.save()

                if getattr(conversation, "status", None) != "closed":
                    conversation.status = "closed"
                    if hasattr(conversation, "ended_at"):
                        conversation.ended_at = timezone.now()
                    conversation.save()

            logger.info(
                f"[CSAT] Feedback registrado: {detected_emoji} (valor={rating_value}) do contato={contact.id}"
            )
            return feedback

        except Exception as e:
            logger.error(f"[CSAT] Erro ao processar resposta: {e}", exc_info=True)
            return None

    # ===========================================================================================
    # DASHBOARD — ESTATÍSTICAS CSAT
    # ===========================================================================================
    @classmethod
    def get_csat_stats(cls, provedor, days: int = 30):
        """
        Retorna estatísticas para o dashboard de CSAT do provedor.
        IMPORTANTE: Busca APENAS do Supabase - nunca do banco local.
        """

        try:
            from collections import defaultdict

            if isinstance(provedor, int):
                provedor = Provedor.objects.get(id=provedor)

            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)

            # ===========================================================================================
            # BUSCAR APENAS DO SUPABASE (NUNCA DO BANCO LOCAL)
            # ===========================================================================================
            feedbacks_supabase = []
            try:
                import requests
                from django.conf import settings
                
                supabase_url = getattr(settings, 'SUPABASE_URL', None)
                supabase_key = getattr(settings, 'SUPABASE_ANON_KEY', None)
                csat_table = getattr(settings, 'SUPABASE_CSAT_TABLE', 'csat_feedback')
                
                if not supabase_url or not supabase_key:
                    logger.warning("[CSAT Stats] Supabase não configurado, retornando estatísticas vazias")
                    return {
                        "total_feedbacks": 0,
                        "average_rating": 0,
                        "satisfaction_rate": 0,
                        "rating_distribution": [],
                        "channel_distribution": [],
                        "recent_feedbacks": [],
                    }
                
                url = f"{supabase_url}/rest/v1/{csat_table}"
                headers = {
                    'apikey': supabase_key,
                    'Authorization': f'Bearer {supabase_key}',
                    'Content-Type': 'application/json',
                    'X-Provedor-ID': str(provedor.id)
                }
                
                # Buscar todos os CSATs do provedor e filtrar por data no código
                # (Supabase PostgREST não aceita múltiplos filtros na mesma coluna facilmente)
                # Usar select=* para buscar TODOS os campos (mesma lógica do retrieve da conversa)
                params = {
                    'provedor_id': f'eq.{provedor.id}',
                    'order': 'feedback_sent_at.desc',
                    'select': '*'  # Buscar todos os campos, incluindo original_message
                }
                
                logger.info(f"[CSAT Stats] Buscando CSATs do Supabase para provedor {provedor.id}")
                response = requests.get(url, headers=headers, params=params, timeout=10)
                
                if response.status_code == 200:
                    all_feedbacks_raw = response.json()
                    if isinstance(all_feedbacks_raw, list):
                        # Filtrar por data no código (período especificado)
                        for fb in all_feedbacks_raw:
                            fb_date_str = fb.get('feedback_sent_at')
                            if fb_date_str:
                                try:
                                    from datetime import datetime
                                    # Converter string ISO para datetime
                                    if fb_date_str.endswith('Z'):
                                        fb_date = datetime.fromisoformat(fb_date_str.replace('Z', '+00:00'))
                                    else:
                                        fb_date = datetime.fromisoformat(fb_date_str)
                                    
                                    # Converter para timezone do Django para comparação
                                    if fb_date.tzinfo is None:
                                        fb_date = timezone.make_aware(fb_date)
                                    else:
                                        fb_date = fb_date.astimezone(timezone.get_current_timezone())
                                    
                                    # Verificar se está no período
                                    if start_date <= fb_date <= end_date:
                                        feedbacks_supabase.append(fb)
                                except (ValueError, TypeError) as date_err:
                                    logger.warning(f"[CSAT Stats] Erro ao parsear data {fb_date_str}: {date_err}")
                                    pass
                    logger.info(f"[CSAT Stats] {len(feedbacks_supabase)} CSATs encontrados no Supabase (filtrados de {len(all_feedbacks_raw) if isinstance(all_feedbacks_raw, list) else 0} total)")
                else:
                    logger.warning(f"[CSAT Stats] Erro ao buscar do Supabase: status {response.status_code}, response={response.text[:200]}")
            except Exception as supabase_err:
                logger.error(f"[CSAT Stats] Erro ao buscar CSATs do Supabase: {supabase_err}", exc_info=True)

            # ===========================================================================================
            # CALCULAR ESTATÍSTICAS APENAS COM DADOS DO SUPABASE
            # ===========================================================================================
            total = len(feedbacks_supabase)
            
            if total == 0:
                return {
                    "total_feedbacks": 0,
                    "average_rating": 0,
                    "satisfaction_rate": 0,
                    "rating_distribution": [],
                    "channel_distribution": [],
                    "recent_feedbacks": [],
                }
            
            # Calcular média de rating
            total_rating = sum(fb.get('rating_value', 0) for fb in feedbacks_supabase)
            avg_rating = total_rating / total if total > 0 else 0
            
            # Distribuição de ratings
            rating_dist = defaultdict(int)
            for fb in feedbacks_supabase:
                rating_value = fb.get('rating_value', 0)
                emoji_rating = fb.get('emoji_rating', '😐')
                rating_dist[(emoji_rating, rating_value)] += 1
            
            rating_distribution = [
                {"emoji_rating": emoji, "rating_value": rating, "count": count}
                for (emoji, rating), count in rating_dist.items()
            ]
            
            # Distribuição por canal
            channel_dist = defaultdict(int)
            for fb in feedbacks_supabase:
                channel_type = fb.get('channel_type', 'whatsapp')
                channel_dist[channel_type] += 1
            
            channel_distribution = [
                {"channel_type": channel, "count": count}
                for channel, count in channel_dist.items()
            ]
            
            # Taxa de satisfação
            satisfied = sum(1 for fb in feedbacks_supabase if fb.get('rating_value', 0) >= 4)
            satisfaction_rate = (satisfied / total * 100) if total > 0 else 0
            
            # Últimos 10 feedbacks (já estão ordenados por feedback_sent_at desc do Supabase)
            recent_feedbacks_raw = feedbacks_supabase[:10]
            
            # Converter para formato esperado pelo frontend
            recent_feedbacks = []
            for fb in recent_feedbacks_raw:
                # Buscar nome do contato se disponível (pode estar no Supabase ou buscar do banco local)
                contact_name = fb.get('contact_name', 'Cliente')
                contact_id = fb.get('contact_id')
                
                # Se não tiver contact_name no Supabase, tentar buscar do banco local
                if not contact_name or contact_name == 'Cliente':
                    try:
                        from .models import Contact
                        contact = Contact.objects.filter(id=contact_id).first()
                        if contact:
                            contact_name = contact.name or contact.phone or 'Cliente'
                    except Exception:
                        pass
                
                # Buscar foto do contato se disponível
                contact_photo = fb.get('contact_photo', None)
                if not contact_photo and contact_id:
                    try:
                        from .models import Contact
                        contact = Contact.objects.filter(id=contact_id).first()
                        if contact and contact.avatar:
                            contact_photo = contact.avatar
                    except Exception:
                        pass
                
                # IMPORTANTE: original_message sempre do Supabase, nunca do banco local
                original_message = fb.get('original_message', '') or ''
                
                recent_feedbacks.append({
                    'id': fb.get('id'),
                    'rating_value': fb.get('rating_value', 0),
                    'emoji_rating': fb.get('emoji_rating', '😐'),
                    'channel_type': fb.get('channel_type', 'whatsapp'),
                    'feedback_sent_at': fb.get('feedback_sent_at'),
                    'conversation': fb.get('conversation_id'),  # Número, não objeto
                    'conversation_id': fb.get('conversation_id'),
                    'contact_id': fb.get('contact_id'),
                    'contact_name': contact_name,  # String, não objeto
                    'contact_photo': contact_photo,  # String URL ou None
                    'original_message': original_message,  # Sempre do Supabase
                })
            
            logger.info(f"[CSAT Stats] Total: {total} feedbacks do Supabase para provedor {provedor.id}")
            
            return {
                "total_feedbacks": total,
                "average_rating": round(avg_rating, 1),
                "satisfaction_rate": round(satisfaction_rate),
                "rating_distribution": rating_distribution,
                "channel_distribution": channel_distribution,
                "recent_feedbacks": recent_feedbacks,
            }

        except Exception as e:
            logger.error(f"[CSAT] Erro ao calcular estatísticas: {e}", exc_info=True)
            return {}
