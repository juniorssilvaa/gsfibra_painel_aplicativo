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

    @staticmethod
    def _is_automation_closure(conversation) -> bool:
        """Encerramento iniciado por bot, chatbot ou IA (não por agente humano)."""
        attrs = dict(getattr(conversation, 'additional_attributes', None) or {})
        if attrs.get('resolucao_automacao'):
            return True
        if str(attrs.get('encerrado_por') or '').lower() == 'ai':
            return True
        closure_source = str(attrs.get('closure_source') or '')
        return closure_source.startswith('chatbot') or closure_source.startswith('ia_')

    @classmethod
    def should_skip_csat_for_automation(
        cls,
        conversation,
        provedor,
        ended_by_user_id=None,
    ) -> bool:
        """
        True quando o provedor desativou CSAT em encerramentos automáticos
        (bot/IA) e a conversa foi encerrada por automação.
        """
        if ended_by_user_id:
            return False
        if not provedor:
            return False
        if getattr(provedor, 'csat_send_on_bot_inactivity_closure', True):
            return False
        return cls._is_automation_closure(conversation)

    # ===========================================================================================
    # AGENDAR ENVIO DE CSAT
    # ===========================================================================================
    @classmethod
    def schedule_csat_request(
        cls,
        conversation_id: int,
        ended_by_user_id: int = None,
        send_immediately: bool = False,
        delay_minutes: int = None,
    ):
        """
        Cria e agenda uma solicitação de CSAT para uma conversa encerrada.

        send_immediately: envia na hora (ex.: agente escolheu CSAT no encerramento),
        sem esperar DELAY_MINUTES e com fallback síncrono se o broker falhar.
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

                # 3️⃣ Política de frequência (intervalo mínimo)
                # Em produção, impede novos envios para o mesmo contato caso já tenha CSAT enviado há menos do intervalo configurado.
                if not settings.DEBUG:
                    provedor = getattr(conversation.inbox, 'provedor', None)
                    now = timezone.now()

                    if provedor:
                        enforce = getattr(provedor, 'csat_enforce_min_interval', True)
                        min_interval_hours = getattr(provedor, 'csat_min_interval_hours', 24) or 24

                        if enforce and min_interval_hours > 0:
                            cutoff = now - timedelta(hours=int(min_interval_hours))
                            recent_csat_for_contact = CSATRequest.objects.filter(
                                contact=conversation.contact,
                                provedor=provedor,
                                sent_at__gte=cutoff,
                                status__in=['sent', 'completed', 'responded'],
                            ).order_by('-sent_at').first()

                            if recent_csat_for_contact:
                                time_since_last = (now - recent_csat_for_contact.sent_at).total_seconds() / 3600
                                logger.info(
                                    f"[CSAT] CSAT bloqueado por intervalo: contato {conversation.contact.id} "
                                    f"enviou há {time_since_last:.1f}h (mínimo={min_interval_hours}h). "
                                    f"Retornando CSAT existente (id={recent_csat_for_contact.id})."
                                )
                                return recent_csat_for_contact

                # 4️⃣ DUPLICIDADE
                # - Agente com envio imediato: expira anteriores da mesma conversa e cria um novo pedido.
                # - Fluxo automático: evita criar pedido duplicado para a mesma conversa.
                if send_immediately:
                    expired = CSATRequest.objects.filter(
                        conversation=conversation,
                        status__in=['pending', 'sent'],
                    ).update(status='expired')
                    if expired:
                        logger.info(
                            f"[CSAT] {expired} solicitação(ões) anterior(es) expirada(s) "
                            f"para reenvio imediato na conversa {conversation_id}"
                        )
                else:
                    if not settings.DEBUG:
                        existing_for_conversation = CSATRequest.objects.filter(
                            conversation=conversation
                        ).first()
                        if existing_for_conversation:
                            logger.info(
                                f"[CSAT] Solicitação já existe para conversa {conversation_id} "
                                f"(id={existing_for_conversation.id}, status={existing_for_conversation.status})"
                            )
                            return existing_for_conversation
                    else:
                        # DESENVOLVIMENTO: Permitir CSATs repetidos para facilitar testes
                        logger.info(
                            f"[CSAT] Modo desenvolvimento (DEBUG=True): permitindo CSAT repetido para conversa {conversation_id}"
                        )

                # 5️⃣ Validar status
                if conversation.status != "closed":
                    logger.warning(
                        f"[CSAT] Conversa {conversation_id} não está fechada — status={conversation.status}"
                    )
                    return None

                # 6️⃣ Validar provedor
                if not conversation.inbox or not conversation.inbox.provedor:
                    logger.error(
                        f"[CSAT] Conversa {conversation_id} sem inbox/provedor. Não é possível agendar CSAT."
                    )
                    return None

                provedor = conversation.inbox.provedor
                if cls.should_skip_csat_for_automation(
                    conversation, provedor, ended_by_user_id=ended_by_user_id
                ):
                    logger.info(
                        f"[CSAT] CSAT não enviado para conversa {conversation_id}: "
                        f"encerramento automático (bot/IA) com envio desativado pelo provedor"
                    )
                    return None

                # 7️⃣ Agendamento
                ended_at = timezone.now()
                effective_delay_minutes = (
                    0
                    if send_immediately
                    else (delay_minutes if delay_minutes is not None else cls.DELAY_MINUTES)
                )
                scheduled_send_at = ended_at + timedelta(minutes=effective_delay_minutes)

                channel_type = getattr(conversation.inbox, "channel_type", "whatsapp")

                # 8️⃣ Criar solicitação
                csat_request = CSATRequest.objects.create(
                    conversation=conversation,
                    contact=conversation.contact,
                    provedor=conversation.inbox.provedor,
                    conversation_ended_at=ended_at,
                    scheduled_send_at=scheduled_send_at,
                    channel_type=channel_type,
                    status="pending",
                )

                # Persistir quem encerrou (assignee é limpo no close; ranking CSAT precisa disso)
                if ended_by_user_id:
                    try:
                        attrs = dict(conversation.additional_attributes or {})
                        attrs['csat_ended_by_user_id'] = int(ended_by_user_id)
                        conversation.additional_attributes = attrs
                        conversation.save(update_fields=['additional_attributes', 'updated_at'])
                    except Exception as attr_err:
                        logger.warning(
                            '[CSAT] Não foi possível gravar csat_ended_by_user_id: %s',
                            attr_err,
                        )

                logger.info(
                    f"[CSAT] Criado CSATRequest id={csat_request.id} para conversa {conversation.id}, "
                    f"envio marcado para {scheduled_send_at}"
                )

            # ==================================================================================
            # DISPATCH: imediato (agente) = síncrono; automático = Dramatiq + fallback
            # ==================================================================================
            if send_immediately:
                cls._send_csat_sync_fallback(csat_request.id)
            else:
                dramatiq_enqueued = False
                try:
                    import dramatiq
                    from niochat.dramatiq_config import broker as configured_broker
                    from .dramatiq_tasks import send_csat_message

                    current_broker = dramatiq.get_broker()
                    if current_broker is not configured_broker:
                        dramatiq.set_broker(configured_broker)
                        send_csat_message.broker = configured_broker

                    now_utc = timezone.now()
                    delay_ms = max(0, int((scheduled_send_at - now_utc).total_seconds() * 1000))

                    if delay_ms > 0:
                        send_csat_message.send_with_options(
                            args=(csat_request.id,), delay=delay_ms
                        )
                        dramatiq_enqueued = True
                        logger.info(
                            f"[CSAT] CSATRequest {csat_request.id} agendado com delay={delay_ms}ms."
                        )
                    else:
                        send_csat_message.send(csat_request.id)
                        dramatiq_enqueued = True
                        logger.info(
                            f"[CSAT] CSATRequest {csat_request.id} enfileirado para envio."
                        )

                except Exception as send_err:
                    logger.error(
                        f"[CSAT] Erro ao enfileirar CSATRequest {csat_request.id}: {send_err}",
                        exc_info=True,
                    )

                if not dramatiq_enqueued:
                    cls._send_csat_sync_fallback(csat_request.id)

            return csat_request

        except Conversation.DoesNotExist:
            logger.error(f"[CSAT] Conversa {conversation_id} não encontrada.")
            return None

        except Exception as e:
            logger.error(f"[CSAT] Erro ao agendar CSAT: {e}", exc_info=True)
            return None

    @classmethod
    def _mark_csat_sent(cls, csat_request_id: int) -> None:
        CSATRequest.objects.filter(id=csat_request_id, status='pending').update(
            status='sent',
            sent_at=timezone.now(),
        )
        # Agendar migração se não houver resposta (mesmo em fallback sync sem RabbitMQ worker)
        try:
            from conversations.dramatiq_tasks import migrate_conversation_after_csat_timeout
            migrate_conversation_after_csat_timeout.send_with_options(
                args=(csat_request_id,),
                delay=5 * 60 * 1000,
            )
        except Exception as schedule_err:
            logger.warning(
                f"[CSAT] Não foi possível agendar timeout de migração para {csat_request_id}: {schedule_err}"
            )

    @classmethod
    def _send_csat_sync_fallback(cls, csat_request_id: int) -> bool:
        """
        Envia CSAT de forma síncrona (lista interativa WhatsApp oficial primeiro).
        """
        try:
            csat_request = CSATRequest.objects.select_related(
                'conversation', 'contact', 'provedor', 'conversation__inbox'
            ).get(id=csat_request_id)
        except CSATRequest.DoesNotExist:
            logger.warning(f"[CSAT] Fallback síncrono: request {csat_request_id} não existe")
            return False

        if csat_request.status not in ('pending',):
            logger.info(
                f"[CSAT] Request {csat_request_id} já está {csat_request.status}, não reenviar"
            )
            return csat_request.status == 'sent'

        channel = (csat_request.channel_type or '').lower()
        if channel == 'instagram':
            try:
                from .csat_instagram import send_csat_instagram
                if send_csat_instagram(csat_request):
                    cls._mark_csat_sent(csat_request_id)
                    logger.info(
                        f"[CSAT] Instagram enviado (sync) request={csat_request_id}"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"[CSAT] Instagram falhou request={csat_request_id}: {e}",
                    exc_info=True,
                )
        if channel in ('whatsapp_oficial', 'whatsapp', 'whatsapp_session'):
            try:
                from .csat_whatsapp import send_csat_interactive_list
                if send_csat_interactive_list(csat_request):
                    cls._mark_csat_sent(csat_request_id)
                    logger.info(
                        f"[CSAT] Lista interativa enviada (sync) request={csat_request_id}"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"[CSAT] Lista interativa falhou request={csat_request_id}: {e}",
                    exc_info=True,
                )

        try:
            from .dramatiq_tasks import send_csat_message
            send_csat_message(csat_request_id)
            csat_request.refresh_from_db()
            if csat_request.status == 'sent':
                logger.info(f"[CSAT] Enviado via dramatiq_tasks (sync) id={csat_request_id}")
                return True
        except Exception as e:
            logger.warning(
                f"[CSAT] dramatiq_tasks (sync) falhou para {csat_request_id}: {e}",
                exc_info=True,
            )

        try:
            from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api
            from .csat_whatsapp import build_csat_list_body
            body = build_csat_list_body(
                csat_request.contact.name,
                csat_request.provedor.nome,
            )
            ok, err = send_via_whatsapp_cloud_api(
                conversation=csat_request.conversation,
                content=body,
                message_type='text',
            )
            if ok:
                cls._mark_csat_sent(csat_request_id)
                logger.info(f"[CSAT] Texto fallback enviado request={csat_request_id}")
                return True
            logger.error(f"[CSAT] Texto fallback falhou: {err}")
        except Exception as e:
            logger.error(f"[CSAT] Texto fallback exceção: {e}", exc_info=True)

        return False

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

            agent_meta = {}
            try:
                attrs = conversation.additional_attributes or {}
                ended_by = attrs.get('csat_ended_by_user_id')
                if not ended_by and isinstance(attrs.get('assigned_user'), dict):
                    ended_by = attrs['assigned_user'].get('id')
                if ended_by:
                    agent_meta['ended_by_user_id'] = int(ended_by)
                    agent_meta['agent_id'] = int(ended_by)
            except Exception:
                agent_meta = {}

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
                    additional_data=agent_meta,
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
                        "daily_stats": [],
                        "agent_ranking": [],
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

            # Banco local (dev / antes da migração / Supabase indisponível)
            feedbacks_local = []
            try:
                local_qs = CSATFeedback.objects.filter(
                    provedor=provedor,
                    feedback_sent_at__gte=start_date,
                    feedback_sent_at__lte=end_date,
                ).select_related('contact').order_by('-feedback_sent_at')
                for fb in local_qs:
                    contact_name = 'Cliente'
                    if fb.contact:
                        contact_name = fb.contact.name or fb.contact.phone or 'Cliente'
                    feedbacks_local.append({
                        'id': fb.id,
                        'provedor_id': provedor.id,
                        'conversation_id': fb.conversation_id,
                        'contact_id': fb.contact_id,
                        'emoji_rating': fb.emoji_rating,
                        'rating_value': fb.rating_value,
                        'channel_type': fb.channel_type,
                        'feedback_sent_at': fb.feedback_sent_at.isoformat(),
                        'original_message': fb.original_message or '',
                        'contact_name': contact_name,
                        'additional_data': fb.additional_data or {},
                    })
                logger.info(f"[CSAT Stats] {len(feedbacks_local)} CSATs no banco local")
            except Exception as local_err:
                logger.warning(f"[CSAT Stats] Erro ao buscar CSAT local: {local_err}")

            # Unir Supabase + local (priorizar registro mais recente por conversa)
            merged = {}
            for fb in feedbacks_supabase + feedbacks_local:
                key = (fb.get('conversation_id'), fb.get('contact_id'))
                existing = merged.get(key)
                if not existing:
                    merged[key] = fb
                    continue
                try:
                    from datetime import datetime
                    def _parse_dt(val):
                        if not val:
                            return None
                        s = str(val)
                        if s.endswith('Z'):
                            s = s.replace('Z', '+00:00')
                        return datetime.fromisoformat(s)
                    d_new = _parse_dt(fb.get('feedback_sent_at'))
                    d_old = _parse_dt(existing.get('feedback_sent_at'))
                    if d_new and d_old and d_new > d_old:
                        merged[key] = fb
                except Exception:
                    merged[key] = fb
            feedbacks_supabase = list(merged.values())
            feedbacks_supabase.sort(
                key=lambda x: x.get('feedback_sent_at') or '',
                reverse=True,
            )

            # ===========================================================================================
            # CALCULAR ESTATÍSTICAS (Supabase + banco local)
            # ===========================================================================================
            total = len(feedbacks_supabase)
            
            if total == 0:
                return {
                    "total_feedbacks": 0,
                    "average_rating": 0,
                    "satisfaction_rate": 0,
                    "rating_distribution": [],
                    "channel_distribution": [],
                    "daily_stats": [],
                    "agent_ranking": [],
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
            
            # Mapa conversa → atendente (reutilizado no ranking e nos feedbacks recentes)
            agent_by_conv = {}
            try:
                agent_by_conv = cls._resolve_agents_for_conversations(
                    provedor, feedbacks_supabase
                )
            except Exception as resolve_err:
                logger.warning(
                    '[CSAT Stats] Falha ao resolver atendentes: %s',
                    resolve_err,
                    exc_info=True,
                )

            users_by_id = {}
            if agent_by_conv:
                try:
                    from core.models import User
                    from core.support_account import exclude_hidden_provedor_users

                    users_by_id = {
                        u.id: u
                        for u in exclude_hidden_provedor_users(
                            User.objects.filter(
                                id__in=list(set(agent_by_conv.values()))
                            ).only(
                                'id',
                                'first_name',
                                'last_name',
                                'username',
                                'user_type',
                                'email',
                            ),
                            viewer=None,
                        )
                    }
                except Exception:
                    users_by_id = {}

            emoji_by_rating = {1: '😡', 2: '😕', 3: '😐', 4: '🙂', 5: '🤩'}

            # Últimos 10 feedbacks (já estão ordenados por feedback_sent_at desc)
            recent_feedbacks_raw = feedbacks_supabase[:50]

            recent_feedbacks = []
            for fb in recent_feedbacks_raw:
                contact_name = fb.get('contact_name', 'Cliente')
                contact_id = fb.get('contact_id')
                conversation_id = fb.get('conversation_id')

                if not contact_name or contact_name == 'Cliente':
                    try:
                        from .models import Contact
                        contact = Contact.objects.filter(id=contact_id).first()
                        if contact:
                            contact_name = contact.name or contact.phone or 'Cliente'
                    except Exception:
                        pass

                if (not contact_name or contact_name == 'Cliente') and conversation_id:
                    try:
                        conv = (
                            Conversation.objects.select_related('contact')
                            .filter(id=conversation_id)
                            .first()
                        )
                        if conv and conv.contact:
                            contact_name = (
                                conv.contact.name or conv.contact.phone or 'Cliente'
                            )
                            if not contact_id:
                                contact_id = conv.contact_id
                    except Exception:
                        pass

                contact_photo = fb.get('contact_photo', None)
                if not contact_photo and contact_id:
                    try:
                        from .models import Contact
                        contact = Contact.objects.filter(id=contact_id).first()
                        if contact and contact.avatar:
                            contact_photo = contact.avatar
                    except Exception:
                        pass

                original_message = fb.get('original_message', '') or ''
                try:
                    rating_value = int(fb.get('rating_value') or 0)
                except (TypeError, ValueError):
                    rating_value = 0
                emoji_rating = fb.get('emoji_rating') or emoji_by_rating.get(
                    rating_value, '😐'
                )

                agent_id = None
                agent_name = None
                try:
                    cid_int = int(conversation_id) if conversation_id is not None else None
                except (TypeError, ValueError):
                    cid_int = None
                if cid_int and cid_int in agent_by_conv:
                    agent_id = agent_by_conv[cid_int]
                    user = users_by_id.get(agent_id)
                    if user:
                        agent_name = (
                            f"{user.first_name or ''} {user.last_name or ''}".strip()
                            or user.username
                        )
                    else:
                        agent_name = 'Atendente'
                elif cid_int:
                    # Sem agente humano identificado → provavelmente IA / automático
                    agent_name = 'IA'

                recent_feedbacks.append({
                    'id': fb.get('id'),
                    'rating_value': rating_value,
                    'emoji_rating': emoji_rating,
                    'channel_type': fb.get('channel_type', 'whatsapp'),
                    'feedback_sent_at': fb.get('feedback_sent_at'),
                    'conversation': conversation_id,
                    'conversation_id': conversation_id,
                    'contact_id': contact_id,
                    'contact_name': contact_name,
                    'contact_photo': contact_photo,
                    'original_message': original_message,
                    'agent_id': agent_id,
                    'agent_name': agent_name,
                })

            logger.info(f"[CSAT Stats] Total: {total} feedbacks do Supabase para provedor {provedor.id}")

            # Evolução temporal (média diária)
            daily_bucket = defaultdict(list)
            for fb in feedbacks_supabase:
                fb_date_str = fb.get('feedback_sent_at')
                if not fb_date_str:
                    continue
                try:
                    from datetime import datetime
                    s = str(fb_date_str)
                    if s.endswith('Z'):
                        s = s.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = timezone.make_aware(dt)
                    day_key = dt.astimezone(timezone.get_current_timezone()).date().isoformat()
                    daily_bucket[day_key].append(float(fb.get('rating_value') or 0))
                except Exception:
                    continue
            daily_stats = [
                {
                    'day': day,
                    'avg_rating': round(sum(vals) / len(vals), 2) if vals else 0,
                    'count': len(vals),
                }
                for day, vals in sorted(daily_bucket.items())
            ]

            # Ranking por atendente
            try:
                agent_ranking = cls._build_agent_ranking_from_map(
                    agent_by_conv, feedbacks_supabase, users_by_id
                )
            except Exception as ranking_err:
                logger.warning(
                    '[CSAT Stats] Falha ao montar ranking de atendentes: %s',
                    ranking_err,
                    exc_info=True,
                )
                agent_ranking = []

            return {
                "total_feedbacks": total,
                "average_rating": round(avg_rating, 1),
                "satisfaction_rate": round(satisfaction_rate),
                "rating_distribution": rating_distribution,
                "channel_distribution": channel_distribution,
                "daily_stats": daily_stats,
                "agent_ranking": agent_ranking,
                "recent_feedbacks": recent_feedbacks,
            }

        except Exception as e:
            logger.error(f"[CSAT] Erro ao calcular estatísticas: {e}", exc_info=True)
            return {}

    @classmethod
    def _resolve_agents_for_conversations(cls, provedor, feedbacks):
        """Retorna {conversation_id: user_id} do atendente que encerrou a conversa."""
        from core.models import AuditLog

        agent_by_conv = {}
        conv_ids = []
        for fb in feedbacks:
            cid = fb.get('conversation_id') or fb.get('conversation')
            if not cid:
                continue
            try:
                conv_ids.append(int(cid))
            except (TypeError, ValueError):
                pass
        conv_ids = list(set(conv_ids))
        if not conv_ids:
            return {}

        for fb in feedbacks:
            cid = fb.get('conversation_id') or fb.get('conversation')
            extra = fb.get('additional_data') or {}
            if not isinstance(extra, dict):
                continue
            aid = extra.get('agent_id') or extra.get('ended_by_user_id')
            if cid and aid:
                try:
                    agent_by_conv[int(cid)] = int(aid)
                except (TypeError, ValueError):
                    pass

        missing = [c for c in conv_ids if c not in agent_by_conv]
        if missing:
            for conv in Conversation.objects.filter(id__in=missing).only(
                'id', 'assignee_id', 'additional_attributes'
            ):
                aid = None
                attrs = conv.additional_attributes or {}
                if attrs.get('csat_ended_by_user_id'):
                    aid = attrs.get('csat_ended_by_user_id')
                elif isinstance(attrs.get('assigned_user'), dict):
                    aid = attrs['assigned_user'].get('id')
                elif conv.assignee_id:
                    aid = conv.assignee_id
                if aid:
                    try:
                        agent_by_conv[conv.id] = int(aid)
                    except (TypeError, ValueError):
                        pass

        still_missing = [c for c in conv_ids if c not in agent_by_conv]
        if still_missing:
            logs = (
                AuditLog.objects.filter(
                    provedor=provedor,
                    conversation_id__in=still_missing,
                    user_id__isnull=False,
                    action__in=[
                        'conversation_closed_manual',
                        'conversation_closed_agent',
                        'conversation_closed_bulk',
                    ],
                )
                .order_by('-timestamp')
                .values('conversation_id', 'user_id')
            )
            for row in logs:
                cid = row.get('conversation_id')
                uid = row.get('user_id')
                if cid and uid and int(cid) not in agent_by_conv:
                    agent_by_conv[int(cid)] = int(uid)

        return agent_by_conv

    @classmethod
    def _build_agent_ranking_from_map(cls, agent_by_conv, feedbacks, users_by_id=None):
        from collections import defaultdict
        from core.models import User
        from core.support_account import exclude_hidden_provedor_users

        if not feedbacks or not agent_by_conv:
            return []

        ratings_by_agent = defaultdict(list)
        for fb in feedbacks:
            cid = fb.get('conversation_id') or fb.get('conversation')
            try:
                cid = int(cid) if cid is not None else None
            except (TypeError, ValueError):
                cid = None
            aid = agent_by_conv.get(cid) if cid else None
            if not aid:
                continue
            try:
                rating = float(fb.get('rating_value') or 0)
            except (TypeError, ValueError):
                continue
            if rating > 0:
                ratings_by_agent[aid].append(rating)

        if not ratings_by_agent:
            return []

        if users_by_id is None:
            users_by_id = {
                u.id: u
                for u in exclude_hidden_provedor_users(
                    User.objects.filter(id__in=list(ratings_by_agent.keys())).only(
                        'id', 'first_name', 'last_name', 'username', 'user_type', 'email'
                    ),
                    viewer=None,
                )
            }

        ranking = []
        for aid, vals in ratings_by_agent.items():
            user = users_by_id.get(aid)
            if not user:
                continue
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
            ranking.append({
                'agent_id': aid,
                'name': name,
                'avg_rating': round(sum(vals) / len(vals), 2),
                'total_feedbacks': len(vals),
            })

        ranking.sort(key=lambda x: (-x['avg_rating'], -x['total_feedbacks'], x['name']))
        return ranking

    @classmethod
    def _build_agent_ranking(cls, provedor, feedbacks):
        """Compat: resolve atendentes e monta ranking."""
        agent_by_conv = cls._resolve_agents_for_conversations(provedor, feedbacks)
        return cls._build_agent_ranking_from_map(agent_by_conv, feedbacks)
