from rest_framework import viewsets, permissions, status, serializers, filters
import django_filters.rest_framework
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Q
from core.models import Provedor, User, AuditLog, Canal
from core.pagination import DefaultPagination
from rest_framework.pagination import PageNumberPagination
from .models import Contact, Inbox, Conversation, Message, Team, TeamMember
from .models import CSATFeedback, MessageReaction
from .serializers import (
    ContactSerializer, InboxSerializer, ConversationSerializer,
    ConversationListSerializer, ConversationUpdateSerializer, MessageSerializer, TeamSerializer, TeamMemberSerializer
)
from .services import ConversationNotificationService
from .message_visibility import apply_agent_message_visibility_filter, waiting_queue_content_redacted_for_agent
from integrations.conversation_voice_calls_mixin import ConversationVoiceCallsMixin
from rest_framework.permissions import AllowAny
from integrations.models import WhatsAppIntegration
from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api, send_reaction, translate_whatsapp_error
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests
import json
import base64
import logging

logger = logging.getLogger(__name__)
from django.http import FileResponse, Http404, JsonResponse, HttpResponse
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import os
from datetime import datetime, timedelta
from django.db.models import Count, Avg


from ai.service import openai_service
# async_to_sync já importado acima

class TextCorrectionView(APIView):
    """
    Endpoint para correção gramatical de mensagens via IA.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        text = request.data.get('text')
        language = request.data.get('language', 'pt-BR')
        
        if not text:
            return Response({'error': 'Texto é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            provedor = getattr(request.user, 'provedor', None)
            if not provedor and hasattr(request.user, 'provedores_admin'):
                provedor = request.user.provedores_admin.first()
            corrected_text = async_to_sync(openai_service.correct_text)(
                text, language, provedor=provedor
            )

            return Response({
                'success': True,
                'corrected_text': corrected_text
            })
        except Exception as e:
            logger.error(f"Erro na view de correção de texto: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e),
                'corrected_text': text # Retorna o original em caso de erro
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def log_conversation_closure(request, conversation, action_type, resolution_type=None, user=None):
    """
    Função utilitária para registrar auditoria de conversas encerradas
    """
    try:
        # Verificar se já existe um AuditLog para esta conversa com esta ação para evitar duplicação
        existing_log = AuditLog.objects.filter(
            conversation_id=conversation.id,
            action=action_type
        ).first()
        
        # Só criar se não existir
        if existing_log:
            logger.info(f"AuditLog já existe para conversa {conversation.id} com ação {action_type}, evitando duplicação")
            return existing_log
        
        # Calcular duração da conversa
        duration = None
        if conversation.created_at and conversation.updated_at:
            duration = conversation.updated_at - conversation.created_at
        
        # Contar mensagens
        message_count = conversation.messages.count()
        
        # Obter provedor da conversa
        provedor = conversation.inbox.provedor if conversation.inbox else None
        
        # Obter IP
        ip_address = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else '127.0.0.1'
        
        # Criar log de auditoria
        details = f"Conversa encerrada com {conversation.contact.name} via {conversation.inbox.channel_type}"
        if resolution_type:
            details += f" | Resolução: {resolution_type}"
        if duration:
            details += f" | Duração: {duration}"
        if message_count:
            details += f" | Mensagens: {message_count}"
        
        audit_log = AuditLog.objects.create(
            user=user or request.user,
            action=action_type,
            ip_address=ip_address,
            details=details,
            provedor=provedor,
            conversation_id=conversation.id,
            contact_name=conversation.contact.name,
            channel_type=conversation.inbox.channel_type
        )
        
        # Enviar auditoria para Supabase
        try:
            from core.supabase_service import supabase_service
            supabase_success = supabase_service.save_audit(
                provedor_id=conversation.inbox.provedor_id,
                conversation_id=conversation.id,
                action=action_type,
                details={'resolution_type': resolution_type or 'manual', 'details': details},
                user_id=(user.id if user and user.is_authenticated else None),
                ended_at_iso=(conversation.updated_at.isoformat() if conversation.updated_at else None)
            )
        except Exception as _sup_err:
            pass
        
        # Enviar dados da conversa para Supabase
        try:
            from core.supabase_service import supabase_service
            supabase_service.save_conversation(
                provedor_id=conversation.inbox.provedor_id,
                conversation_id=conversation.id,
                contact_id=conversation.contact_id,
                inbox_id=conversation.inbox_id,
                status=conversation.status,
                assignee_id=conversation.assignee_id,
                created_at_iso=conversation.created_at.isoformat(),
                updated_at_iso=conversation.updated_at.isoformat(),
                ended_at_iso=conversation.updated_at.isoformat(),
                additional_attributes=conversation.additional_attributes
            )
        except Exception as _conv_err:
            pass
        
        # Enviar dados do contato para Supabase
        try:
            contact = conversation.contact
            supabase_service.save_contact(
                provedor_id=conversation.inbox.provedor_id,
                contact_id=contact.id,
                name=contact.name,
                phone=getattr(contact, 'phone', None),
                email=getattr(contact, 'email', None),
                avatar=getattr(contact, 'avatar', None),
                created_at_iso=contact.created_at.isoformat(),
                updated_at_iso=contact.updated_at.isoformat(),
                additional_attributes=contact.additional_attributes
            )
        except Exception as _contact_err:
            pass
        
        # Enviar todas as mensagens da conversa para Supabase
        try:
            # from conversations.models import Message
            messages = Message.objects.filter(conversation=conversation).order_by('created_at')
            messages_sent = 0
            
            for msg in messages:
                success = supabase_service.save_message(
                    provedor_id=conversation.inbox.provedor_id,
                    conversation_id=conversation.id,
                    contact_id=contact.id,
                    content=msg.content,
                    message_type=msg.message_type,
                    is_from_customer=msg.is_from_customer,
                    external_id=msg.external_id,
                    file_url=msg.file_url,
                    file_name=getattr(msg, 'file_name', None),
                    file_size=getattr(msg, 'file_size', None),
                    additional_attributes=msg.additional_attributes,
                    created_at_iso=msg.created_at.isoformat()
                )
                if success:
                    messages_sent += 1
        except Exception as _msg_err:
            pass
        
        # Agendar solicitação de CSAT para 2 minutos após encerramento
        try:
            from .csat_service import CSATService
            csat_request = CSATService.schedule_csat_request(
                conversation_id=conversation.id,
                ended_by_user_id=user.id if user and user.is_authenticated else None
            )
            if csat_request:
                pass
            else:
                logger.warning(f"Falha ao agendar CSAT para conversa {conversation.id}")
        except ImportError as import_error:
            logger.error(f"Erro ao importar CSATService: {import_error}")
        except Exception as csat_error:
            logger.error(f"Erro ao agendar CSAT para conversa {conversation.id}: {csat_error}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Erro crítico em log_conversation_closure para conversa {conversation.id}: {e}", exc_info=True)


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'phone', 'email']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        
        # Filtrar por provedor específico se fornecido (para superadmin)
        provedor_id = self.request.query_params.get('provedor_id')
        if provedor_id and user.user_type == 'superadmin':
            try:
                provedor_id_int = int(provedor_id)
                return Contact.objects.filter(provedor_id=provedor_id_int)
            except (ValueError, TypeError):
                pass
        
        if user.user_type == 'superadmin':
            return Contact.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                # Verificar se algum provedor está suspenso
                for provedor in provedores:
                    if not provedor.is_active:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied('Seu provedor está temporariamente suspenso. Entre em contato com o suporte.')
                return Contact.objects.filter(provedor__in=provedores)
            return Contact.objects.none()
    
    def perform_create(self, serializer):
        """Define provedor ao criar contato quando não enviado (contexto da conta atual)."""
        user = self.request.user
        data = serializer.validated_data
        if data.get('provedor') is None and user.user_type != 'superadmin':
            provedores = Provedor.objects.filter(admins=user, is_active=True)
            first = provedores.first()
            if first:
                serializer.save(provedor=first)
                return
        serializer.save()

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """
        Apaga múltiplos contatos de uma vez.

        Body: { "ids": [1,2,3] }
        Retorna: { deleted: N, not_found: [..] }
        """
        ids = request.data.get('ids') or request.data.get('contact_ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids (lista) é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        # normalizar ids para int
        normalized = []
        for v in ids:
            try:
                normalized.append(int(v))
            except (TypeError, ValueError):
                continue
        if not normalized:
            return Response({'error': 'Nenhum id válido recebido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(id__in=normalized)
        found_ids = list(qs.values_list('id', flat=True))
        not_found = sorted(list(set(normalized) - set(found_ids)))

        with transaction.atomic():
            deleted, _ = qs.delete()

        return Response({'success': True, 'deleted': deleted, 'not_found': not_found})

    @action(detail=False, methods=['post'], url_path='import-csv')
    def import_csv(self, request):
        """
        Importa contatos via CSV.

        Aceita colunas (case-insensitive) típicas do export do painel:
        - Nome / name
        - Email / email
        - Telefone / phone
        Colunas extras são ignoradas.
        """
        import csv
        import io
        import re

        user = request.user
        upload = request.FILES.get('file') or request.FILES.get('csv') or request.FILES.get('arquivo')
        if not upload:
            return Response({'error': 'Arquivo CSV é obrigatório (campo file).'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolver provedor alvo
        provedor = None
        provedor_id = request.data.get('provedor') or request.data.get('provedor_id') or request.query_params.get('provedor_id')
        if user.user_type == 'superadmin':
            if provedor_id:
                try:
                    provedor = Provedor.objects.filter(id=int(provedor_id)).first()
                except (TypeError, ValueError):
                    provedor = None
        else:
            provedor = Provedor.objects.filter(admins=user, is_active=True).first()

        if not provedor:
            return Response({'error': 'Provedor não encontrado para o usuário atual.'}, status=status.HTTP_400_BAD_REQUEST)

        raw = upload.read()
        # Tentar UTF-8 e fallback para latin-1 (export do Excel)
        text = None
        for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            return Response({'error': 'Não foi possível ler o CSV (encoding inválido).'}, status=status.HTTP_400_BAD_REQUEST)

        # Detectar delimitador comum
        sample = text[:4096]
        delimiter = ';' if sample.count(';') > sample.count(',') else ','

        f = io.StringIO(text)
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return Response({'error': 'CSV sem cabeçalho (header).'}, status=status.HTTP_400_BAD_REQUEST)

        def _norm_key(k: str) -> str:
            return re.sub(r'\s+', ' ', str(k or '').strip().lower())

        field_map = {_norm_key(k): k for k in (reader.fieldnames or [])}

        def _get(row, *keys):
            for k in keys:
                col = field_map.get(_norm_key(k))
                if col and col in row:
                    return row.get(col)
            return None

        def _clean_phone(v: str) -> str:
            s = str(v or '').strip()
            if not s:
                return ''
            s = s.replace('@s.whatsapp.net', '').replace('@lid', '')
            # manter + se vier; remover tudo que não é dígito
            digits = re.sub(r'\D', '', s)
            return digits

        created = 0
        updated = 0
        skipped = 0
        errors = []

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):  # 1 = header
                try:
                    name = (_get(row, 'Nome', 'name') or '').strip()
                    email = (_get(row, 'Email', 'email') or '').strip() or None
                    phone = _clean_phone(_get(row, 'Telefone', 'phone') or '')

                    if not phone:
                        skipped += 1
                        continue
                    if not name:
                        name = 'Sem nome'

                    obj = Contact.objects.filter(provedor=provedor, phone=phone).first()
                    if obj:
                        changed = False
                        if name and obj.name != name:
                            obj.name = name
                            changed = True
                        if email != obj.email:
                            obj.email = email
                            changed = True
                        if changed:
                            obj.save(update_fields=['name', 'email', 'updated_at'])
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        Contact.objects.create(
                            provedor=provedor,
                            name=name,
                            email=email,
                            phone=phone,
                        )
                        created += 1
                except Exception as e:
                    errors.append({'line': idx, 'error': str(e)})

        return Response(
            {
                'success': True,
                'provedor_id': provedor.id,
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'errors': errors[:50],
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['patch'], url_path='toggle-block-atender')
    def toggle_block_atender(self, request, pk=None):
        """Toggle do bloqueio para atendimento (IA não responde)"""
        contact = self.get_object()
        contact.bloqueado_atender = not contact.bloqueado_atender
        contact.save(update_fields=['bloqueado_atender', 'updated_at'])
        
        # Registrar log de auditoria
        from core.models import AuditLog
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        AuditLog.objects.create(
            user=request.user,
            action='update',
            ip_address=ip,
            details=f'Contato {"bloqueado" if contact.bloqueado_atender else "desbloqueado"} para atendimento: {contact.name} ({contact.phone})',
            provedor=contact.provedor
        )
        
        return Response({
            'success': True,
            'bloqueado_atender': contact.bloqueado_atender,
            'message': f'Contato {"bloqueado" if contact.bloqueado_atender else "desbloqueado"} para atendimento com sucesso'
        })
    
    @action(detail=True, methods=['patch'], url_path='toggle-block-disparos')
    def toggle_block_disparos(self, request, pk=None):
        """Toggle do bloqueio para disparos"""
        contact = self.get_object()
        contact.bloqueado_disparos = not contact.bloqueado_disparos
        contact.save(update_fields=['bloqueado_disparos', 'updated_at'])
        
        # Registrar log de auditoria
        from core.models import AuditLog
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        AuditLog.objects.create(
            user=request.user,
            action='update',
            ip_address=ip,
            details=f'Contato {"bloqueado" if contact.bloqueado_disparos else "desbloqueado"} para disparos: {contact.name} ({contact.phone})',
            provedor=contact.provedor
        )
        
        return Response({
            'success': True,
            'bloqueado_disparos': contact.bloqueado_disparos,
            'message': f'Contato {"bloqueado" if contact.bloqueado_disparos else "desbloqueado"} para disparos com sucesso'
        })


class InboxViewSet(viewsets.ModelViewSet):
    queryset = Inbox.objects.all()
    serializer_class = InboxSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return Inbox.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                # Verificar se algum provedor está suspenso
                for provedor in provedores:
                    if not provedor.is_active:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied('Seu provedor está temporariamente suspenso. Entre em contato com o suporte.')
                return Inbox.objects.filter(provedor__in=provedores)
            return Inbox.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        request = self.request
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        inbox = serializer.save()
        company_name = inbox.company.name if inbox.company else 'Desconhecida'
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='create',
            ip_address=ip,
            details=f"Empresa {company_name} criou novo canal: {inbox.name}"
        )

    def perform_destroy(self, instance):
        user = self.request.user
        request = self.request
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        company_name = instance.company.name if instance.company else 'Desconhecida'
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='delete',
            ip_address=ip,
            details=f"Empresa {company_name} excluiu canal: {instance.name}"
        )
        instance.delete()


class ConversationViewSet(ConversationVoiceCallsMixin, viewsets.ModelViewSet):
    """
    ETAPA 3 e 4: ViewSet otimizado para /api/conversations
    
    - Exclui conversas fechadas por padrão (no banco)
    - Usa select_related para reduzir queries
    - Força paginação via DefaultPagination
    - Usa ConversationListSerializer para listagem (leve)
    """
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DefaultPagination  # ETAPA 3: Forçar paginação controlada
    
    @action(detail=False, methods=['get'], url_path='dashboard_stats')
    def dashboard_stats(self, request):
        """
        Action para retornar estatísticas rápidas do dashboard.
        """
        user = request.user
        provedor = None
        
        # Se for superadmin, permitir passar provedor_id como parâmetro
        if user.user_type == 'superadmin':
            provedor_id_param = request.GET.get('provedor_id')
            if provedor_id_param:
                try:
                    provedor_id = int(provedor_id_param)
                    provedor = Provedor.objects.filter(id=provedor_id).first()
                except (ValueError, TypeError):
                    return Response({'error': 'provedor_id inválido'}, status=400)
        
        # Se não foi passado como parâmetro, buscar do usuário
        if not provedor:
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
            if not provedor:
                from .models import TeamMember
                tm = TeamMember.objects.filter(user=user).select_related('team__provedor').first()
                if tm and tm.team:
                    provedor = tm.team.provedor
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
            if not provedor and hasattr(user, 'provedor') and user.provedor:
                provedor = user.provedor
            if not provedor:
                provedor = Provedor.objects.filter(admins=user).first()
        
        if not provedor:
            return Response({'error': 'Provedor não identificado para este atendente'}, status=400)
        
        # 1. Queryset global do provedor para estatísticas (ignora filtros de equipe do agente)
        qs_ativas = Conversation.objects.filter(
            inbox__provedor=provedor
        ).exclude(
            status__in=['closed', 'encerrada', 'resolved', 'finalizada', 'closing']
        )
        
        # 2. Contagens explícitas e robustas
        conversas_abertas = qs_ativas.filter(assignee__isnull=False).count()
        conversas_pendentes = qs_ativas.filter(waiting_for_agent=True, assignee__isnull=True).count()
        conversas_ia = qs_ativas.filter(waiting_for_agent=False, assignee__isnull=True).count()
        
        # LOG PARA DEPURAÇÃO
        import logging
        logger_stats = logging.getLogger('conversations.dashboard_debug')
        logger_stats.info(f"--- DASHBOARD REFRESH (Provedor {provedor.id}) ---")
        logger_stats.info(f"IA: {conversas_ia} | Espera: {conversas_pendentes} | Atendimento: {conversas_abertas}")
        
        # 3. Métricas históricas
        from django.db.models import Count, Q
        provedor_filter = Q(inbox__provedor=provedor)
        
        total_stats = Conversation.objects.filter(provedor_filter).aggregate(
            total=Count('id'),
            finalizadas_local=Count('id', filter=Q(status__in=['closed', 'encerrada', 'resolved', 'finalizada']))
        )
        
        total_conversas_local = total_stats['total'] or 0
        conversas_resolvidas_local = total_stats['finalizadas_local'] or 0
        conversas_em_andamento = conversas_abertas + conversas_pendentes + conversas_ia
        
        # Estatísticas de conversas - Supabase (encerradas)
        conversas_resolvidas_supabase = 0
        try:
            import requests
            from django.conf import settings
            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Prefer': 'count=exact'
            }
            params = {'provedor_id': f'eq.{provedor.id}', 'status': 'eq.closed', 'select': 'id'}
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                content_range = response.headers.get('Content-Range', '')
                if content_range:
                    conversas_resolvidas_supabase = int(content_range.split('/')[-1])
        except Exception:
            pass
            
        total_encerradas = conversas_resolvidas_local + conversas_resolvidas_supabase
        
        return Response({
            'stats': {
                'conversas_abertas': conversas_abertas,
                'conversas_pendentes': conversas_pendentes,
                'conversas_ia': conversas_ia,
                'total_resolvidas': total_encerradas,
                'conversas_em_andamento': conversas_em_andamento,
                'total_geral': total_encerradas + conversas_em_andamento
            }
        })

    def get_queryset(self, include_bot=None):
        """
        ETAPA 4: Queryset otimizado com exclusão de conversas fechadas e select_related.
        
        Retorna queryset de conversas com isolamento por provedor.
        Se superadmin passar provedor_id como parâmetro, filtra apenas aquele provedor.
        """
        # Se include_bot não foi passado via argumento, verificar query_params
        if include_bot is None:
            include_bot = self.request.query_params.get('include_bot', 'false') == 'true'
            
        user = self.request.user
        
        # ETAPA 4: Excluir conversas fechadas no banco para listagem (reduz carga).
        # retrieve, update, partial_update precisam aceitar qualquer status: o frontend pode
        # enviar PATCH logo após um encerramento (race condition) e a action
        # close_conversation_agent usa get_object() que também passa por aqui.
        if self.action in ('retrieve', 'update', 'partial_update', 'close_conversation_agent',
                           'close_conversation_ai', 'assign_conversation'):
            base_queryset = Conversation.objects.all()
        else:
            # Status fechados: closed, encerrada, resolved, finalizada, closing
            base_queryset = Conversation.objects.exclude(
                status__in=['closed', 'encerrada', 'resolved', 'finalizada', 'closing']
            )
        
        # Ocultar conversas do bot (waiting_for_agent=False) apenas na listagem.
        # Em ações de detalhe/alteração precisamos permitir qualquer conversa do provedor,
        # senão fluxos de encerramento podem receber 404 indevidamente.
        if self.action == 'list' and not include_bot:
            base_queryset = base_queryset.filter(waiting_for_agent=True)
        
        # Otimização: prefetch_related para mensagens apenas na listagem (evita N+1 no get_last_message)
        # Prefetch apenas a última mensagem para reduzir carga
        from django.db.models import Prefetch, Q
        from .models import Message
        messages_prefetch = Prefetch(
            'messages',
            queryset=Message.objects.order_by('-created_at')[:1],
            to_attr='last_message_prefetched'
        )
        
        # Helper para aplicar otimizações comuns
        from django.db.models.functions import Coalesce, Cast
        from django.db.models import Count, F, OuterRef, Subquery, DateTimeField
        from django.db.models.fields.json import KeyTextTransform
        
        def apply_optimizations(qs):
            qs = qs.select_related(
                'contact', 'inbox', 'inbox__provedor', 'assignee', 'team'
            )
            # Aplicar prefetch apenas na listagem
            if self.action == 'list':
                qs = qs.prefetch_related(messages_prefetch)
                last_agent_at = Message.objects.filter(
                    conversation_id=OuterRef('pk'),
                    is_from_customer=False,
                ).order_by('-created_at').values('created_at')[:1]
                qs = qs.annotate(
                    _panel_last_read_at=Cast(
                        KeyTextTransform('panel_last_read_at', 'additional_attributes'),
                        DateTimeField(),
                    ),
                    _last_agent_at=Subquery(last_agent_at, output_field=DateTimeField()),
                ).annotate(
                    _unread_since=Coalesce('_panel_last_read_at', '_last_agent_at', 'created_at'),
                ).annotate(
                    unread_count_annotated=Count(
                        'messages',
                        filter=Q(
                            messages__is_from_customer=True,
                            messages__created_at__gt=F('_unread_since'),
                        ),
                        distinct=True,
                    )
                )
            
            return qs.annotate(
                sort_date=Coalesce('last_message_at', 'created_at')
            ).order_by('-sort_date')
        
        # Filtrar por provedor específico se fornecido (para superadmin)
        provedor_id_param = self.request.query_params.get('provedor_id')
        if provedor_id_param and user.user_type == 'superadmin':
            try:
                provedor_id_int = int(provedor_id_param)
                return apply_optimizations(
                    base_queryset.filter(inbox__provedor_id=provedor_id_int)
                )
            except (ValueError, TypeError):
                pass
        
        # Superadmin vê todas as conversas (exceto fechadas)
        if user.user_type == 'superadmin':
            return apply_optimizations(base_queryset)
        
        # Admin vê todas as conversas do seu provedor (exceto fechadas)
        elif user.user_type == 'admin':
            # Tentar obter provedores onde o usuário é admin explicitamente ou pelo campo provedor
            provedores_obj = Provedor.objects.filter(Q(admins=user) | Q(id=getattr(user, 'provedor_id', None)))
            
            if provedores_obj.exists():
                # Verificar se algum provedor está suspenso
                for prov in provedores_obj:
                    if not prov.is_active:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied('Seu provedor está temporariamente suspenso. Entre em contato com o suporte.')
                return apply_optimizations(
                    base_queryset.filter(inbox__provedor__in=provedores_obj)
                )
            return Conversation.objects.none()
        # Agent (atendente)
        else:
            # Buscar equipes do usuário
            user_teams = TeamMember.objects.filter(user=user).values_list('team_id', flat=True)
            user_permissions = getattr(user, 'permissions', [])
            if not isinstance(user_permissions, list):
                user_permissions = []
            
            # Buscar provedor do usuário (garantir que temos o provedor base)
            user_provider = user.provedor
            if not user_provider:
                tm = TeamMember.objects.filter(user=user).select_related('team__provedor').first()
                if tm and tm.team:
                    user_provider = tm.team.provedor

            if not user_provider:
                return Conversation.objects.none()

            # Base: todas as conversas ativas do provedor do usuário
            provider_queryset = base_queryset.filter(inbox__provedor=user_provider)
            
            # 1. Minhas conversas (onde sou atendente)
            my_convs = provider_queryset.filter(assignee=user)
            
            # 2. Conversas em Espera (Fila Global do Provedor)
            # Para garantir que o Dashboard mostre o que o card laranja conta
            unassigned_waiting = provider_queryset.filter(waiting_for_agent=True, assignee__isnull=True)
            
            # 3. Conversas do Bot (se tiver permissão ou fallback)
            has_no_special_permissions = not any(p in user_permissions for p in ['view_ai_conversations', 'view_team_unassigned'])
            if 'view_ai_conversations' in user_permissions or 'view_chatbot_conversations' in user_permissions:
                ai_convs = provider_queryset.filter(waiting_for_agent=False, assignee__isnull=True)
            else:
                ai_convs = Conversation.objects.none()
            
            # Combinar tudo e garantir que o que está em espera seja visível
            final_qs = (my_convs | unassigned_waiting | ai_convs).distinct()
            return apply_optimizations(final_qs)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Buscar detalhes da conversa
        FLUXO:
        1. Buscar do banco LOCAL primeiro (conversas abertas)
        2. Se não encontrar, buscar do Supabase (conversas encerradas/migradas)
        """
        import logging
        import requests
        from django.conf import settings
        # logger = logging.getLogger(__name__)
        conversation_id = kwargs.get('pk')
        
        # Converter para int se necessário
        try:
            conversation_id = int(conversation_id)
        except (ValueError, TypeError):
            logger.error(f"[RETRIEVE] ID de conversa inválido: {conversation_id}")
            return Response({'error': 'ID de conversa inválido'}, status=400)
        
        # 1. PRIMEIRO: Buscar do banco LOCAL (conversas abertas)
        try:
            conversation = Conversation.objects.select_related(
                'contact', 'inbox', 'inbox__provedor', 'assignee', 'team'
            ).get(id=conversation_id)
            
            # Conversa encontrada no banco local - retornar dados locais
            logger.debug(f"[RETRIEVE] Conversa {conversation_id} encontrada no banco local (status: {conversation.status})")

            # Abrir no painel = marcar como lida (zera badge de novas mensagens na lista)
            try:
                conversation.mark_panel_read()
            except Exception:
                pass
            
            # Buscar mensagens do banco local (painel: oculta histórico anterior ao retorno ao bot)
            messages_qs = Message.objects.filter(conversation=conversation).order_by('created_at')
            messages_qs = apply_agent_message_visibility_filter(messages_qs, conversation, request)
            messages = list(messages_qs)
            
            # Montar resposta com dados locais
            contact = conversation.contact
            inbox = conversation.inbox
            provedor = inbox.provedor if inbox else None
            
            # Calcular is_24h_window_open usando o método do modelo
            # Isso garante que sempre usa o timestamp real da mensagem mais recente do cliente
            is_24h_window_open = conversation.is_24h_window_open()
            
            logger.info(f"[RETRIEVE] Conversa {conversation_id} - is_24h_window_open={is_24h_window_open}, last_user_message_at={conversation.last_user_message_at}")

            from core.media_signing import sign_media_url
            
            result = {
                'id': conversation.id,
                'status': conversation.status,
                'waiting_for_agent': conversation.waiting_for_agent,
                'panel_waiting_content_hidden': waiting_queue_content_redacted_for_agent(request, conversation),
                'created_at': conversation.created_at.isoformat() if conversation.created_at else None,
                'updated_at': conversation.updated_at.isoformat() if conversation.updated_at else None,
                'last_message_at': conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                'last_user_message_at': conversation.last_user_message_at.isoformat() if conversation.last_user_message_at else None,
                'is_24h_window_open': is_24h_window_open,
                'additional_attributes': conversation.additional_attributes or {},
                'contact': {
                    'id': contact.id if contact else None,
                    'name': contact.name if contact else None,
                    'phone': contact.phone if contact else None,
                    'email': contact.email if contact else None,
                    'avatar': getattr(contact, 'avatar', None),
                    'photo': getattr(contact, 'avatar', None),
                    'additional_attributes': contact.additional_attributes if contact else {},
                } if contact else None,
                'inbox': {
                    'id': inbox.id if inbox else None,
                    'channel_type': inbox.channel_type if inbox else None,
                    'name': inbox.name if inbox else None,
                    'custom_name': InboxSerializer(inbox).data.get('custom_name') if inbox else None,
                    'channel_real_id': InboxSerializer(inbox).data.get('channel_real_id') if inbox else None,
                    'provedor': {
                        'id': provedor.id if provedor else None,
                        'nome': provedor.nome if provedor else None,
                    } if provedor else None,
                } if inbox else None,
                'assignee': {
                    'id': conversation.assignee.id,
                    'username': conversation.assignee.username,
                    'first_name': conversation.assignee.first_name,
                    'last_name': conversation.assignee.last_name,
                } if conversation.assignee else None,
                'team': {
                    'id': conversation.team.id,
                    'name': conversation.team.name,
                } if conversation.team else None,
                'messages': [
                    {
                        'id': msg.id,
                        'content': msg.content,
                        'message_type': msg.message_type,
                        'is_from_customer': msg.is_from_customer,
                        'created_at': msg.created_at.isoformat() if msg.created_at else None,
                        'external_id': msg.external_id,
                        'file_url': sign_media_url(msg.file_url) if msg.file_url else None,
                        'additional_attributes': msg.additional_attributes or {},
                    } for msg in messages
                ],
            }
            
            return Response(result)
            
        except Conversation.DoesNotExist:
            # Conversa não está no banco local - buscar do Supabase (já foi migrada)
            logger.debug(f"[RETRIEVE] Conversa {conversation_id} não encontrada no banco local, buscando no Supabase")
        except Exception as e:
            logger.error(f"[RETRIEVE] Erro ao buscar conversa {conversation_id} do banco local: {e}")
        
        # 2. FALLBACK: Buscar do Supabase (conversas encerradas/migradas)
        try:
            
            # Usar a mesma lógica do teste que funcionou
            supabase_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
            supabase_key = getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '') or getattr(settings, 'SUPABASE_ANON_KEY', '')
            
            if not supabase_url or not supabase_key:
                logger.warning(f"[RETRIEVE] Supabase não configurado")
                return Response({'error': 'Conversa não encontrada'}, status=404)
            
            # Headers (mesma lógica do teste)
            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
            }
            
            # Obter provedor_id do usuário (opcional, para RLS)
            from core.models import Provedor
            user = request.user
            provedor_id = None
            if user.user_type == 'admin':
                provedores = Provedor.objects.filter(admins=user)
                if provedores.exists():
                    provedor_id = provedores.first().id
            elif hasattr(user, 'provedor_id') and user.provedor_id:
                provedor_id = user.provedor_id
            elif hasattr(user, 'provedor') and user.provedor:
                provedor_id = user.provedor.id
            
            if provedor_id:
                headers["X-Provedor-ID"] = str(provedor_id)
            
            logger.info(f"[RETRIEVE] Provedor ID: {provedor_id}, User: {user.username}, User Type: {user.user_type}")
            
            # Buscar conversa no Supabase (mesma lógica do teste)
            url = f"{supabase_url}/rest/v1/conversations"
            params = {'id': f'eq.{conversation_id}'}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            logger.info(f"[RETRIEVE] Resposta Supabase: status={response.status_code}")
            
            if response.status_code == 200:
                conversations = response.json()
                if conversations and isinstance(conversations, list) and len(conversations) > 0:
                    conversation_data = conversations[0]
                    logger.info(f"[RETRIEVE] Conversa encontrada no Supabase: {conversation_data.get('id')}")
                    
                    # Obter provedor_id da conversa se não tiver do usuário
                    if not provedor_id:
                        provedor_id = conversation_data.get('provedor_id')
                        if provedor_id:
                            headers["X-Provedor-ID"] = str(provedor_id)
                    
                    # Buscar dados do contato (mesma lógica do teste)
                    contact_data = {}
                    if conversation_data.get('contact_id'):
                        contact_url = f"{supabase_url}/rest/v1/contacts"
                        contact_params = {'id': f'eq.{conversation_data.get("contact_id")}'}
                        contact_response = requests.get(contact_url, headers=headers, params=contact_params, timeout=10)
                        if contact_response.status_code == 200:
                            contacts = contact_response.json()
                            if contacts and isinstance(contacts, list) and len(contacts) > 0:
                                contact_data = contacts[0]
                    
                    # NOTA: A tabela 'inboxes' não existe no Supabase
                    # O channel_type será extraído dos detalhes do audit log ou será 'whatsapp' por padrão
                    channel_type = 'whatsapp'  # Padrão
                    
                    # Tentar extrair channel_type do audit log
                    try:
                        audit_url = f"{supabase_url}/rest/v1/auditoria"
                        audit_params = {
                            'conversation_id': f'eq.{conversation_id}',
                            'limit': 1,
                            'order': 'created_at.desc'
                        }
                        audit_response = requests.get(audit_url, headers=headers, params=audit_params, timeout=5)
                        if audit_response.status_code == 200:
                            audit_logs = audit_response.json()
                            if audit_logs and isinstance(audit_logs, list) and len(audit_logs) > 0:
                                audit_log = audit_logs[0]
                                details = audit_log.get('details', {})
                                if isinstance(details, dict):
                                    details_str = details.get('details', '')
                                    if isinstance(details_str, str):
                                        if 'whatsapp' in details_str.lower():
                                            channel_type = 'whatsapp'
                                        elif 'telegram' in details_str.lower():
                                            channel_type = 'telegram'
                                        elif 'email' in details_str.lower():
                                            channel_type = 'email'
                                        elif 'webchat' in details_str.lower():
                                            channel_type = 'webchat'
                                        elif 'facebook' in details_str.lower():
                                            channel_type = 'facebook'
                                        elif 'instagram' in details_str.lower():
                                            channel_type = 'instagram'
                    except Exception as e:
                        logger.warning(f"[RETRIEVE] Erro ao buscar channel_type do audit log: {e}")
                    
                    # Buscar CSAT feedback
                    csat_data = {}
                    csat_url = f"{supabase_url}/rest/v1/{getattr(settings, 'SUPABASE_CSAT_TABLE', 'csat_feedback')}"
                    csat_params = {'conversation_id': f'eq.{conversation_id}'}
                    csat_response = requests.get(csat_url, headers=headers, params=csat_params, timeout=10)
                    if csat_response.status_code == 200:
                        csats = csat_response.json()
                        if csats and isinstance(csats, list) and len(csats) > 0:
                            csat_data = csats[0]
                    
                    # Buscar mensagens do Supabase
                    messages_data = []
                    messages_url = f"{supabase_url}/rest/v1/{getattr(settings, 'SUPABASE_MESSAGES_TABLE', 'mensagens')}"
                    # Construir query corretamente
                    messages_params = {
                        'conversation_id': f'eq.{conversation_id}',
                        'order': 'created_at.asc',
                        'select': '*'
                    }
                    # Adicionar provedor_id se disponível
                    if provedor_id:
                        messages_params['provedor_id'] = f'eq.{provedor_id}'
                    
                    # Tentar buscar mensagens
                    try:
                        messages_response = requests.get(
                            messages_url, 
                            headers=headers, 
                            params=messages_params, 
                            timeout=10
                        )
                        if messages_response.status_code == 200:
                            messages_json = messages_response.json()
                            if isinstance(messages_json, list):
                                messages_data = messages_json
                                logger.info(f"[RETRIEVE] {len(messages_data)} mensagens encontradas no Supabase")
                            else:
                                logger.warning(f"[RETRIEVE] Resposta de mensagens não é uma lista: {type(messages_json)}")
                        else:
                            logger.warning(f"[RETRIEVE] Erro ao buscar mensagens: {messages_response.status_code} - {messages_response.text[:200]}")
                            # Se deu erro 400, pode ser problema com o select ou formato da query
                            # Tentar sem o select primeiro
                            if messages_response.status_code == 400:
                                messages_params_no_select = {
                                    'conversation_id': f'eq.{conversation_id}',
                                    'order': 'created_at.asc'
                                }
                                if provedor_id:
                                    messages_params_no_select['provedor_id'] = f'eq.{provedor_id}'
                                messages_response2 = requests.get(
                                    messages_url, 
                                    headers=headers, 
                                    params=messages_params_no_select, 
                                    timeout=10
                                )
                                if messages_response2.status_code == 200:
                                    messages_json = messages_response2.json()
                                    if isinstance(messages_json, list):
                                        messages_data = messages_json
                                        logger.info(f"[RETRIEVE] {len(messages_data)} mensagens encontradas no Supabase (sem select)")
                    except Exception as e:
                        logger.warning(f"[RETRIEVE] Exceção ao buscar mensagens: {e}")
                    
                    # Buscar provedor (se disponível via conversation)
                    provedor_data = {}
                    provedor_id_final = conversation_data.get('provedor_id')
                    if provedor_id_final:
                        try:
                            provedor = Provedor.objects.get(id=provedor_id_final)
                            provedor_data = {
                                'id': provedor.id,
                                'nome': provedor.nome,
                                'is_active': provedor.is_active
                            }
                        except Provedor.DoesNotExist:
                            pass
                    
                    # Calcular is_24h_window_open baseado nas mensagens do Supabase
                    # Buscar a mensagem mais recente do cliente
                    is_24h_window_open = False
                    last_user_message_at = None
                    if messages_data:
                        from django.utils import timezone
                        from datetime import timedelta
                        # Filtrar mensagens do cliente e encontrar a mais recente
                        customer_messages = [msg for msg in messages_data if msg.get('is_from_customer')]
                        if customer_messages:
                            # Ordenar por created_at e pegar a mais recente
                            customer_messages.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                            last_customer_msg = customer_messages[0]
                            if last_customer_msg.get('created_at'):
                                try:
                                    # Tentar usar datetime.fromisoformat primeiro (Python 3.7+)
                                    created_at_str = last_customer_msg['created_at']
                                    if isinstance(created_at_str, str):
                                        # Remover 'Z' ou '+00:00' e converter
                                        if created_at_str.endswith('Z'):
                                            created_at_str = created_at_str[:-1] + '+00:00'
                                        try:
                                            from datetime import datetime
                                            last_msg_time = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                        except (ValueError, AttributeError):
                                            # Fallback para dateutil se disponível
                                            try:
                                                from dateutil import parser
                                                last_msg_time = parser.isoparse(created_at_str)
                                            except ImportError:
                                                # Último fallback: usar timezone.now() se não conseguir parsear
                                                logger.warning(f"[RETRIEVE] Não foi possível parsear created_at: {created_at_str}")
                                                last_msg_time = timezone.now()
                                        
                                        # Converter para timezone aware se necessário
                                        if timezone.is_naive(last_msg_time):
                                            last_msg_time = timezone.make_aware(last_msg_time)
                                        last_user_message_at = last_msg_time
                                        # Calcular se passou 24 horas
                                        now = timezone.now()
                                        time_diff = now - last_msg_time
                                        is_24h_window_open = time_diff < timedelta(hours=24)
                                except Exception as e:
                                    logger.warning(f"[RETRIEVE] Erro ao calcular is_24h_window_open: {e}", exc_info=True)
                    
                    # Montar resposta no formato esperado pelo frontend
                    result = {
                        'id': conversation_data.get('id'),
                        'status': conversation_data.get('status'),
                        'created_at': conversation_data.get('created_at'),
                        'updated_at': conversation_data.get('updated_at'),
                        'ended_at': conversation_data.get('ended_at') or conversation_data.get('updated_at'),
                        'last_message_at': conversation_data.get('last_message_at') or conversation_data.get('updated_at'),
                        'last_user_message_at': last_user_message_at.isoformat() if last_user_message_at else None,
                        'is_24h_window_open': is_24h_window_open,
                        'assignee_id': conversation_data.get('assignee_id'),
                        'contact': {
                            'id': contact_data.get('id'),
                            'name': contact_data.get('name') or 'Desconhecido',
                            'phone': contact_data.get('phone'),
                            'email': contact_data.get('email'),
                            'avatar': contact_data.get('avatar'),
                            'photo': contact_data.get('photo') or contact_data.get('avatar')
                        },
                    'inbox': {
                        'id': conversation_data.get('inbox_id'),
                        'channel_type': channel_type,
                        'name': None,
                        'provedor': provedor_data
                    },
                        'csat': csat_data if csat_data else None,
                        'messages': messages_data,
                        'message_count': len(messages_data) if messages_data else 0
                    }
                    
                    logger.info(f"[RETRIEVE] Retornando dados da conversa {conversation_id} do Supabase")
                    return Response(result)
                else:
                    logger.warning(f"[RETRIEVE] Conversa {conversation_id} não encontrada no Supabase (lista vazia)")
                    return Response({'error': 'Conversa não encontrada'}, status=404)
            else:
                logger.warning(f"[RETRIEVE] Erro ao buscar no Supabase: {response.status_code} - {response.text[:200]}")
                return Response({'error': 'Conversa não encontrada'}, status=404)
                
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.error(f"[RETRIEVE] Erro ao buscar conversa {conversation_id} no Supabase: {e}", exc_info=True)
            # Se falhar tudo, retornar 404
            return Response({'error': 'Conversa não encontrada'}, status=404)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ConversationListSerializer
        elif self.action in ['update', 'partial_update']:
            return ConversationUpdateSerializer
        return ConversationSerializer
    
    def _format_message_with_agent_name(self, content: str, user, channel_type: str) -> str:
        """
        Formata a mensagem com o nome do agente no formato correto para cada canal.
        
        Para Telegram: Nome completo em negrito (**texto**)
        Para WhatsApp: Nome completo em negrito (*texto*)
        
        Formato:
        Nome Completo
        
        Mensagem aqui
        
        Remove formatações antigas como "*Nome disse:*" antes de aplicar a nova formatação.
        """
        import re
        
        # Obter nome completo do agente primeiro (necessário para remover formatações antigas)
        agent_name = user.get_full_name() if user else ""
        if not agent_name:
            agent_name = user.username if user else "Atendente"
        
        # Remover formatações antigas do tipo "*Nome disse:*" ou "**Nome disse:**"
        # Padrões: *texto disse:* ou **texto disse:** ou *texto disse: ou **texto disse:
        # Remove também linhas vazias que possam estar antes ou depois
        content = re.sub(r'^\s*\*{1,2}.*?disse:\*{0,2}\s*\n*', '', content, flags=re.IGNORECASE | re.MULTILINE)
        content = content.strip()
        
        # Se o conteúdo ainda começar com o nome do agente (caso o frontend tenha adicionado), remover também
        if agent_name:
            # Remover linha que começa apenas com o nome (sem formatação de negrito)
            # Pode estar em uma linha separada seguida de linha vazia
            content = re.sub(rf'^\s*{re.escape(agent_name)}\s*\n+', '', content, flags=re.IGNORECASE | re.MULTILINE)
            content = content.strip()
        
        # Formatar nome com negrito conforme o canal
        if channel_type == 'app_mobile':
            # App mostra o nome do atendente na UI — não embutir assinatura no texto.
            return content
        if channel_type == 'telegram':
            # Telegram usa **texto** para negrito
            formatted_name = f"**{agent_name}**"
        elif channel_type == 'instagram':
            # Instagram não interpreta *negrito* em texto — usar nome limpo
            formatted_name = agent_name
        else:
            # WhatsApp usa *texto* para negrito
            formatted_name = f"*{agent_name}*"
        
        # Retornar mensagem formatada: nome em cima, conteúdo embaixo
        if channel_type == 'instagram':
            return f"{formatted_name}\n{content}"
        return f"{formatted_name}\n\n{content}"

    def _deliver_outbound_text(self, conversation, content: str):
        """
        Envia texto já formatado ao canal da conversa (WhatsApp / Telegram / Instagram).
        Retorna (success: bool, response).
        """
        channel_type = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
        try:
            if channel_type == 'telegram':
                return self._send_telegram_message(conversation, content)

            if channel_type in ['whatsapp', 'whatsapp_oficial']:
                canal_oficial = conversation.inbox.get_canal_instance() if conversation.inbox else None
                if canal_oficial and canal_oficial.token and getattr(canal_oficial, 'phone_number_id', None):
                    if not conversation.is_24h_window_open():
                        return False, translate_whatsapp_error(131047)
                    return send_via_whatsapp_cloud_api(
                        conversation,
                        content,
                        'text',
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                if channel_type == 'whatsapp':
                    return send_via_uazapi(conversation, content, 'text', None, None)
                return False, 'Canal WhatsApp não configurado'

            if channel_type == 'instagram':
                from integrations.instagram_send import send_instagram_text

                contact = conversation.contact
                canal_instagram = conversation.inbox.get_canal_instance() if conversation.inbox else None
                recipient_id = (contact.additional_attributes or {}).get('instagram_scoped_id') or contact.phone
                if canal_instagram and canal_instagram.token and recipient_id:
                    success, ig_response, ig_error = send_instagram_text(
                        canal_instagram,
                        str(recipient_id),
                        content,
                    )
                    return success, ig_response if success else ig_error
                return False, 'Canal Instagram não configurado'

            if channel_type == 'app_mobile':
                from conversations.app_mobile import send_app_mobile_outbound

                return send_app_mobile_outbound(conversation, content, 'text')

            return False, f'Canal não suportado: {channel_type}'
        except Exception as e:
            logger.error(f"[_deliver_outbound_text] Erro: {e}", exc_info=True)
            return False, str(e)

    def _send_telegram_message(self, conversation, content, reply_to_message_id=None):
        """
        Envia mensagem de AGENTE HUMANO para o Telegram via MTProto
        
        IMPORTANTE:
        - NÃO chama IA
        - NÃO altera status da conversa
        - Apenas envia a mensagem via Telethon (MTProto)
        
        Args:
            conversation: Objeto Conversation
            content: Conteúdo da mensagem
            reply_to_message_id: ID da mensagem a responder (opcional)
            
        Returns:
            tuple: (success: bool, response: str)
        """
        import logging
        # logger = logging.getLogger(__name__)
        logger.info(f"[_SEND_TELEGRAM] Iniciando envio Telegram: conversation_id={conversation.id}, content_length={len(content)}")
        
        try:
            from integrations.telegram_service import telegram_manager
            import asyncio
            
            # Obter o chat_id do contato ou da última mensagem recebida
            contact = conversation.contact
            logger.info(f"[_SEND_TELEGRAM] Contato: id={contact.id}, phone={contact.phone}, additional_attrs_keys={list(contact.additional_attributes.keys()) if contact.additional_attributes else []}")
            
            # Primeiro tentar pegar o chat_id da última mensagem recebida (mais confiável)
            # from conversations.models import Message
            last_message = Message.objects.filter(
                conversation=conversation,
                is_from_customer=True
            ).order_by('-created_at').first()
            
            chat_id = None
            if last_message and last_message.additional_attributes:
                chat_id = last_message.additional_attributes.get('telegram_chat_id')
            
            # Fallback: usar do contato
            if not chat_id:
                chat_id = (
                    contact.additional_attributes.get('telegram_chat_id') or
                    contact.additional_attributes.get('telegram_user_id')
                )
            
            if not chat_id:
                return False, "Contato não possui telegram_chat_id ou telegram_user_id"
            
            # Converter para int
            try:
                chat_id = int(chat_id)
            except (ValueError, TypeError):
                return False, f"chat_id inválido: {chat_id}"
            
            # Obter o canal do Telegram associado ao inbox
            from core.models import Canal
            canal = Canal.objects.filter(
                provedor=conversation.inbox.provedor,
                tipo='telegram',
                ativo=True
            ).first()
            
            logger.info(f"[_SEND_TELEGRAM] chat_id obtido: {chat_id}")
            
            if not canal:
                logger.error(f"[_SEND_TELEGRAM] Nenhum canal Telegram ativo encontrado para provedor {conversation.inbox.provedor.id}")
                return False, "Nenhum canal Telegram ativo encontrado"
            
            logger.info(f"[_SEND_TELEGRAM] Canal encontrado: id={canal.id}, nome={getattr(canal, 'nome', 'N/A')}")
            
            # Criar/obter event loop único para toda a operação
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Obter ou iniciar o serviço do Telegram
            service = telegram_manager.get_service(canal.id)
            logger.info(f"[_SEND_TELEGRAM] Serviço obtido do manager: {service is not None}, canal_id={canal.id}")
            
            # Se o serviço existe mas o cliente não está conectado, tentar reconectar
            if service and service.client:
                try:
                    is_connected = service.client.is_connected()
                    logger.info(f"[_SEND_TELEGRAM] Serviço existente - cliente conectado: {is_connected}")
                    if not is_connected:
                        logger.warning("[_SEND_TELEGRAM] Serviço existe mas cliente desconectado, reconectando...")
                        loop.run_until_complete(service.client.connect())
                except Exception as check_error:
                    logger.warning(f"[_SEND_TELEGRAM] Erro ao verificar conexão do serviço existente: {check_error}, recriando...")
                    service = None
            
            if not service:
                logger.warning(f"[_SEND_TELEGRAM] Serviço não encontrado ou inválido, criando novo serviço...")
                # Criar um novo serviço Telegram diretamente (não precisa iniciar o listener completo)
                from integrations.telegram_service import TelegramService
                service = TelegramService(canal)
                try:
                    logger.info(f"[_SEND_TELEGRAM] Inicializando cliente Telegram...")
                    initialized = loop.run_until_complete(service.initialize_client())
                    if initialized:
                        # Armazenar o serviço no manager para reutilização
                        telegram_manager.services[canal.id] = service
                        logger.info(f"[_SEND_TELEGRAM] Serviço criado e inicializado: cliente={service.client is not None}, conectado={service.client.is_connected() if service.client else False}")
                    else:
                        logger.error(f"[_SEND_TELEGRAM] Falha ao inicializar cliente Telegram")
                        return False, "Falha ao inicializar cliente Telegram"
                except Exception as init_error:
                    logger.error(f"[_SEND_TELEGRAM] Erro ao inicializar serviço: {init_error}", exc_info=True)
                    return False, f"Erro ao inicializar serviço: {str(init_error)}"
            
            if not service:
                logger.error(f"[_SEND_TELEGRAM] Não foi possível criar o serviço Telegram")
                return False, "Não foi possível criar o serviço Telegram"
            
            # Enviar a mensagem usando send_message com chat_id (funciona para chats privados)
            logger.info(f"[_SEND_TELEGRAM] Tentando enviar mensagem Telegram: chat_id={chat_id}, canal_id={canal.id}, content_length={len(content)}")
            
            try:
                # Verificar se o cliente foi criado em outro loop que está rodando
                client_loop = getattr(service, '_client_loop', None)
                current_loop = None
                try:
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
                
                # Se o cliente foi criado em outro loop que está rodando, usar run_coroutine_threadsafe
                if client_loop and current_loop and client_loop != current_loop and client_loop.is_running():
                    logger.info(f"[_SEND_TELEGRAM] Cliente em outro loop ({client_loop}), usando run_coroutine_threadsafe...")
                    future = asyncio.run_coroutine_threadsafe(
                        service.send_message(chat_id, content, reply_to_message_id),
                        client_loop
                    )
                    success = future.result(timeout=30)
                else:
                    # Usar o loop atual normalmente (send_message vai tratar internamente se necessário)
                    logger.info(f"[_SEND_TELEGRAM] Usando loop atual para envio...")
                    success = loop.run_until_complete(
                        service.send_message(chat_id, content, reply_to_message_id)
                    )
                
                if success:
                    logger.info(f"[_SEND_TELEGRAM] Mensagem Telegram enviada com sucesso para chat_id={chat_id}")
                else:
                    logger.error(f"[_SEND_TELEGRAM] Falha ao enviar mensagem Telegram para chat_id={chat_id}")
                
                return success, "Mensagem enviada com sucesso" if success else "Falha ao enviar"
            except Exception as send_error:
                logger.error(f"[_SEND_TELEGRAM] Erro ao enviar mensagem Telegram: {send_error}", exc_info=True)
                return False, f"Erro ao enviar: {str(send_error)}"
                
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.error(f"Erro ao enviar mensagem humana para Telegram: {e}", exc_info=True)
            return False, str(e)
    
    @action(detail=False, methods=['POST'], url_path='start-with-template', url_name='start-with-template')
    def start_with_template(self, request):
        """
        Iniciar conversa com cliente usando template do WhatsApp.
        Usado quando a janela de atendimento está fechada (após 24h).
        """
        import logging
        # logger = logging.getLogger(__name__)
        logger.info(f"[START_WITH_TEMPLATE] Método chamado - dados: {request.data}")
        
        from integrations.whatsapp_cloud_send import send_template_message
        # Contact, Inbox, Canal e Provedor já estão importados no topo do arquivo
        
        phone = request.data.get('phone')
        template_name = request.data.get('template_name')
        template_language = request.data.get('template_language', 'pt_BR')
        template_components = request.data.get('template_components', [])
        provedor_id = request.data.get('provedor_id')
        canal_id = request.data.get('canal_id')
        
        if not phone:
            return Response({'error': 'Número de telefone é obrigatório'}, status=400)
        
        if not template_name:
            return Response({'error': 'Nome do template é obrigatório'}, status=400)
        
        # Buscar provedor
        provedor = None
        try:
            if provedor_id:
                provedor = Provedor.objects.get(id=provedor_id)
            else:
                user = request.user
                # Tentar buscar por provedores_admin (relacionamento ManyToMany)
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                # Tentar buscar por admins (outro relacionamento possível)
                elif hasattr(user, 'provedor') and user.provedor:
                    provedor = user.provedor
                else:
                    # Tentar buscar por filtro admins
                    provedores = Provedor.objects.filter(admins=user)
                    if provedores.exists():
                        provedor = provedores.first()
                
                if not provedor:
                    logger.warning(f"[START_WITH_TEMPLATE] Provedor não encontrado para usuário {user.id} ({user.username})")
                    return Response({'error': 'Provedor não encontrado. Verifique se o usuário está associado a um provedor.'}, status=400)
        except Provedor.DoesNotExist:
            return Response({'error': 'Provedor não encontrado'}, status=404)
        
        # Buscar canal WhatsApp Oficial
        try:
            if canal_id:
                canal = Canal.objects.get(id=canal_id, tipo='whatsapp_oficial', provedor=provedor)
            else:
                canal = Canal.objects.filter(tipo='whatsapp_oficial', provedor=provedor, ativo=True).first()
            
            if not canal:
                return Response({'error': 'Canal WhatsApp Oficial não encontrado'}, status=404)
        except Canal.DoesNotExist:
            return Response({'error': 'Canal WhatsApp Oficial não encontrado'}, status=404)
        
        # Buscar ou criar contato (aceita DDI internacional; só prefixa 55 em BR local)
        from core.phone_utils import is_valid_whatsapp_phone, normalize_whatsapp_phone

        phone_clean = normalize_whatsapp_phone(phone)
        if not is_valid_whatsapp_phone(phone_clean):
            return Response(
                {
                    "error": (
                        "Telefone inválido. Informe com DDI do país "
                        "(8 a 15 dígitos)."
                    )
                },
                status=400,
            )
        
        # Manter o formato com '+' no banco para facilitar o envio direto à Meta
        # No entanto, a busca deve ser flexível. Por segurança, vamos salvar sem '+' no banco 
        # mas adicionar no envio. Se o usuário já informou com '+', phone_clean filtrado remove.
        # Vamos garantir que buscas futuras considerem apenas dígitos.
        
        contact, contact_created = Contact.objects.get_or_create(
            phone=phone_clean,
            provedor=provedor,
            defaults={
                'name': request.data.get('contact_name', f'Cliente {phone_clean[-8:]}'),
            }
        )
        
        # Buscar ou criar inbox
        inbox, inbox_created = Inbox.objects.get_or_create(
            provedor=provedor,
            channel_id=canal.id,
            defaults={
                'name': f'WhatsApp - {canal.nome or canal.phone_number}',
                'channel_type': 'whatsapp_oficial',
            }
        )
        
        # Buscar ou criar conversa
        # Se conversation_id foi fornecido, tentar usar a conversa existente
        conversation_id = request.data.get('conversation_id')
        conversation = None
        
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, contact=contact, inbox=inbox)
                logger.info(f"[START_WITH_TEMPLATE] Usando conversa existente: {conversation.id}")
            except Conversation.DoesNotExist:
                logger.warning(f"[START_WITH_TEMPLATE] Conversa {conversation_id} não encontrada, criando nova")
        
        if not conversation:
            conversation, conversation_created = Conversation.objects.get_or_create(
                contact=contact,
                inbox=inbox,
                defaults={
                    'status': 'open',
                    'assignee': request.user,
                }
            )
            if conversation_created:
                logger.info(f"[START_WITH_TEMPLATE] Nova conversa criada e atribuída a {request.user.username}: {conversation.id}")
                conversation.mark_assigned_at()
            else:
                # Importante: Se a conversa já existia, garantir que seja aberta e atribuída
                conversation.status = 'open'
                conversation.assignee = request.user
                conversation.save(update_fields=['status', 'assignee'])
                conversation.mark_assigned_at()
                logger.info(f"[START_WITH_TEMPLATE] Conversa existente {conversation.id} (recuperada por contato/inbox) aberta e atribuída a {request.user.username}")
        else:
            # Conversa existente (fornecida por ID): exige Atender antes de enviar template
            if not conversation.assignee_id and getattr(request.user, 'user_type', None) != 'superadmin':
                return Response(
                    {
                        'error': 'Atribua a conversa para enviar mensagens.',
                        'code': 'assignment_required',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            conversation.status = 'open'
            conversation.save(update_fields=['status'])
            logger.info(f"[START_WITH_TEMPLATE] Conversa existente {conversation.id} (fornecida por ID) reaberta")
        
        # Se não foram fornecidos componentes, buscar o template para verificar se tem variáveis
        components_prepared = False
        template_found = None  # Inicializar template_found
        if not template_components or len(template_components) == 0:
            from integrations.whatsapp_templates import list_message_templates
            success_list, templates_list, error_list = list_message_templates(canal)
            if success_list and templates_list:
                # Procurar o template na lista
                for t in templates_list:
                    if t.get('name') == template_name and t.get('language') == template_language:
                        template_found = t
                        break
                
                # Se encontrou o template e tem variáveis no body, preparar componentes
                if template_found:
                    for comp in template_found.get('components', []):
                        if comp.get('type') == 'BODY' and 'example' in comp:
                            # Template tem variáveis, precisamos enviar componentes
                            example_values = comp.get('example', {}).get('body_text', [])
                            if example_values and len(example_values) > 0:
                                # Usar os valores de exemplo
                                params = []
                                for val in example_values[0]:
                                    params.append({"type": "text", "text": str(val)})
                                
                                template_components = [{
                                    "type": "body",
                                    "parameters": params
                                }]
                                components_prepared = True
                                logger.info(f"[START_WITH_TEMPLATE] Preparando {len(params)} parâmetros do template: {[p['text'] for p in params]}")
                                break
        
        # Se template_components ainda for lista vazia, converter para None (template sem variáveis)
        if not components_prepared and (not template_components or len(template_components) == 0):
            template_components = None
        
        # Enviar template
        success, error_message, response_data = send_template_message(
            canal=canal,
            recipient_number=phone_clean,
            template_name=template_name,
            template_language=template_language,
            template_components=template_components if template_components else None
        )
        
        if not success:
            return Response({
                'error': error_message,
                'conversation_id': conversation.id
            }, status=400)
        
        # Criar mensagem no banco de dados após envio bem-sucedido
        try:
            import json
            # from conversations.models import Message
            
            # Extrair message_id da resposta da Meta
            message_id = None
            if response_data:
                if isinstance(response_data, dict):
                    messages = response_data.get('messages', [])
                    if messages and len(messages) > 0:
                        message_id = messages[0].get('id')
                elif isinstance(response_data, str):
                    try:
                        response_dict = json.loads(response_data)
                        messages = response_dict.get('messages', [])
                        if messages and len(messages) > 0:
                            message_id = messages[0].get('id')
                    except:
                        pass
            
            # Criar conteúdo da mensagem baseado no template
            template_content = f"[Template: {template_name}]"
            if template_found:
                # Tentar extrair texto do template
                for comp in template_found.get('components', []):
                    if comp.get('type') == 'BODY' and comp.get('text'):
                        template_content = comp.get('text')
                        break
                    elif comp.get('type') == 'HEADER' and comp.get('format') == 'TEXT' and comp.get('text'):
                        template_content = comp.get('text')
                        break
            
            # Criar mensagem no banco
            message = Message.objects.create(
                conversation=conversation,
                content=template_content,
                message_type='text',
                is_from_customer=False,
                external_id=message_id,
                additional_attributes={
                    'template_name': template_name,
                    'template_language': template_language,
                    'is_template': True,
                    'sent_via': 'whatsapp_cloud_api'
                }
            )
            
            logger.info(f"[START_WITH_TEMPLATE] Mensagem criada no banco: id={message.id}, external_id={message_id}")
            
        except Exception as e:
            logger.error(f"[START_WITH_TEMPLATE] Erro ao criar mensagem no banco: {str(e)}", exc_info=True)
            # Não falhar a requisição se houver erro ao criar mensagem
            # A mensagem será criada quando o webhook da Meta confirmar
        
        # Notificar via WebSocket para atualização em tempo real no frontend
        try:
            ConversationNotificationService.notify_conversation_updated(
                provedor.id,
                conversation.id,
                'conversation_assigned', # Usar assigned para forçar ida para aba "Minhas"
                {'assignee_id': request.user.id}
            )
            logger.info(f"[START_WITH_TEMPLATE] Notificação WebSocket enviada para conversa {conversation.id}")
        except Exception as e:
            logger.error(f"[START_WITH_TEMPLATE] Erro ao enviar notificação WebSocket: {str(e)}")
        
        # Serializar conversa
        serializer = ConversationSerializer(conversation)
        
        return Response({
            'success': True,
            'conversation': serializer.data,
            'template_sent': True,
            'message': 'Template enviado com sucesso'
        }, status=201)
    
    def perform_create(self, serializer):
        user = self.request.user
        request = self.request
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        
        from django.utils import timezone
        conversation = serializer.save(last_message_at=timezone.now())
        
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='create',
            ip_address=ip,
            details=f"Conversa criada: {conversation.contact.name}"
        )

    def perform_update(self, serializer):
        user = self.request.user
        request = self.request
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        
        # Verificar se a conversa está sendo fechada
        old_status = serializer.instance.status
        conversation = serializer.save()
        new_status = conversation.status
        
        # Se a conversa foi fechada, registrar auditoria e criar CSAT
        if old_status != 'closed' and new_status == 'closed':
            
            # Chamar função de log de encerramento
            log_conversation_closure(
                request=request,
                conversation=conversation,
                action_type='conversation_closed_agent',
                resolution_type='manual_closure',
                user=user
            )
        else:
            # Log normal de edição
            from core.models import AuditLog
            AuditLog.objects.create(
                user=user,
                action='edit',
                ip_address=ip,
                details=f"Conversa atualizada: {conversation.contact.name}"
            )

    def perform_destroy(self, instance):
        user = self.request.user
        request = self.request
        ip = request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='delete',
            ip_address=ip,
            details=f"Conversa excluída: {instance.contact.name}"
        )
        instance.delete()

    @action(detail=False, methods=['get'])
    def recovery_stats(self, request):
        """Estatísticas do recuperador de conversas"""
        user = self.request.user
        provedor_id = request.query_params.get('provedor_id')
        
        if not provedor_id:
            return Response({'error': 'provedor_id é obrigatório'}, status=400)
        
        try:
            provedor = Provedor.objects.get(id=provedor_id)
        except Provedor.DoesNotExist:
            return Response({'error': 'Provedor não encontrado'}, status=404)
        
        # Verificar permissão
        if user.user_type != 'superadmin' and provedor not in Provedor.objects.filter(admins=user):
            return Response({'error': 'Sem permissão'}, status=403)
        
        # Buscar conversas do provedor
        conversations = Conversation.objects.filter(inbox__provedor=provedor)
        
        # Calcular estatísticas
        total_conversations = conversations.count()
        recovered_conversations = conversations.filter(
            additional_attributes__recovery_status='recovered'
        ).count()
        pending_recoveries = conversations.filter(
            additional_attributes__recovery_status='pending'
        ).count()
        
        conversion_rate = (recovered_conversations / total_conversations * 100) if total_conversations > 0 else 0
        
        # Calcular tempo médio de resposta (real)
        # Exemplo: calcular diferença entre lastAttempt e response_received_at das conversas recuperadas
        response_times = []
        for conv in conversations.filter(additional_attributes__recovery_status='recovered'):
            last_attempt = conv.additional_attributes.get('recovery_last_attempt')
            response_time = conv.additional_attributes.get('recovery_response_time')
            if last_attempt and response_time:
                try:
                    from datetime import datetime
                    fmt = '%Y-%m-%dT%H:%M:%S' if 'T' in last_attempt else '%Y-%m-%d %H:%M:%S'
                    t1 = datetime.strptime(last_attempt[:19], fmt)
                    t2 = datetime.strptime(response_time[:19], fmt)
                    diff = (t2 - t1).total_seconds()
                    response_times.append(diff)
                except Exception:
                    pass
        if response_times:
            avg_seconds = sum(response_times) / len(response_times)
            avg_min = int(avg_seconds // 60)
            avg_h = avg_min // 60
            avg_min = avg_min % 60
            average_response_time = f"{avg_h}h {avg_min}min" if avg_h else f"{avg_min}min"
        else:
            average_response_time = ''
        
        # Buscar conversas em recuperação
        recovery_conversations = conversations.filter(
            additional_attributes__recovery_status__in=['pending', 'recovered']
        ).select_related('contact')[:10]
        
        recovery_data = []
        for conv in recovery_conversations:
            recovery_data.append({
                'id': conv.id,
                'contact': {
                    'name': conv.contact.name,
                    'phone': conv.contact.phone
                },
                'lastMessage': conv.additional_attributes.get('recovery_last_message', ''),
                'status': conv.additional_attributes.get('recovery_status', 'pending'),
                'attempts': conv.additional_attributes.get('recovery_attempts', 0),
                'lastAttempt': conv.additional_attributes.get('recovery_last_attempt'),
                'potentialValue': conv.additional_attributes.get('recovery_potential_value', 0)
            })
        
        return Response({
            'stats': {
                'totalAttempts': total_conversations,
                'successfulRecoveries': recovered_conversations,
                'pendingRecoveries': pending_recoveries,
                'conversionRate': round(conversion_rate, 1),
                'averageResponseTime': average_response_time
            },
            'conversations': recovery_data
        })

    @action(detail=False, methods=['post'])
    def recovery_settings(self, request):
        """Salvar configurações do recuperador"""
        user = self.request.user
        provedor_id = request.data.get('provedor_id')
        
        if not provedor_id:
            return Response({'error': 'provedor_id é obrigatório'}, status=400)
        
        try:
            provedor = Provedor.objects.get(id=provedor_id)
        except Provedor.DoesNotExist:
            return Response({'error': 'Provedor não encontrado'}, status=404)
        
        # Verificar permissão
        if user.user_type != 'superadmin' and provedor not in Provedor.objects.filter(admins=user):
            return Response({'error': 'Sem permissão'}, status=403)
        
        from .models import RecoverySettings

        recovery_settings, _ = RecoverySettings.objects.get_or_create(provedor=provedor)
        recovery_settings.enabled = request.data.get('enabled', recovery_settings.enabled)
        recovery_settings.delay_minutes = request.data.get('delayMinutes', recovery_settings.delay_minutes)
        recovery_settings.max_attempts = request.data.get('maxAttempts', recovery_settings.max_attempts)
        recovery_settings.auto_discount = request.data.get('autoDiscount', recovery_settings.auto_discount)
        recovery_settings.discount_percentage = request.data.get(
            'discountPercentage',
            recovery_settings.discount_percentage
        )
        recovery_settings.save()

        return Response({
            'message': 'Configurações salvas com sucesso',
            'recovery_enabled': recovery_settings.enabled,
            'delay_minutes': recovery_settings.delay_minutes,
            'max_attempts': recovery_settings.max_attempts,
            'auto_discount': recovery_settings.auto_discount,
            'discount_percentage': recovery_settings.discount_percentage,
            'updated_at': recovery_settings.updated_at.isoformat(),
        })

    @action(detail=True, methods=['post'], url_path='mark_panel_read')
    def mark_panel_read(self, request, pk=None):
        """Zera o badge de novas mensagens da conversa no painel."""
        try:
            conversation = self.get_object()
        except Exception:
            return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        try:
            read_at = conversation.mark_panel_read()
            return Response({'ok': True, 'panel_last_read_at': read_at, 'unread_count': 0})
        except Exception as e:
            logger.error(f"Erro em mark_panel_read: {e}", exc_info=True)
            return Response({'error': 'Falha ao marcar como lida'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        try:
            conversation = self.get_object()
        except Exception:
            # Caso a conversa não seja encontrada (ex: filtrada pelo get_queryset sem include_bot)
            return Response({'error': 'Conversa não encontrada ou acesso negado. Verifique se o chatbot está ativo e use o parâmetro adequado.'}, status=status.HTTP_404_NOT_FOUND)
            
        user_id = request.data.get('user_id')
        team_id = request.data.get('team_id')
        
        if not user_id and not team_id:
            return Response({'error': 'user_id ou team_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        
        target_user = None
        team = None
        try:
            if user_id:
                # Transferir para usuário específico (deixar sem assignee para ele se atribuir)
                try:
                    target_user = User.objects.get(id=user_id)
                    conversation.assignee = None
                    conversation.status = 'pending'
                    conversation.waiting_for_agent = True
                    conversation.updated_at = timezone.now()
                    # Salvar informação do usuário de destino nos additional_attributes
                    if not conversation.additional_attributes:
                        conversation.additional_attributes = {}
                    conversation.additional_attributes['assigned_user'] = {
                        'id': target_user.id,
                        'name': f"{target_user.first_name} {target_user.last_name}".strip() or target_user.username
                    }
                    conversation.additional_attributes.pop('assigned_at', None)
                except User.DoesNotExist:
                    return Response({'error': 'Usuário de destino não encontrado'}, status=status.HTTP_404_NOT_FOUND)
            elif team_id:
                # Transferir para equipe
                from .models import Team
                try:
                    team = Team.objects.get(id=team_id)
                    conversation.team = team
                    conversation.assignee = None
                    conversation.status = 'pending'
                    conversation.waiting_for_agent = True
                    conversation.updated_at = timezone.now()
                    
                    # Salvar também nos additional_attributes para compatibilidade
                    if not conversation.additional_attributes:
                        conversation.additional_attributes = {}
                    conversation.additional_attributes.pop('assigned_at', None)
                    conversation.additional_attributes['assigned_team'] = {
                        'id': team.id,
                        'name': team.name
                    }
                except Team.DoesNotExist:
                    return Response({'error': f'Equipe com ID {team_id} não encontrada no banco de dados.'}, status=status.HTTP_404_NOT_FOUND)
            
            conversation.save()

            # Aviso WhatsApp aos atendentes com telefone no perfil
            try:
                provedor = getattr(getattr(conversation, "inbox", None), "provedor", None)
                if provedor:
                    from core.agent_alert_notify import notify_agents_waiting_alert

                    notify_agents_waiting_alert(
                        provedor,
                        conversation,
                        target_user=target_user,
                        team=team if not target_user else None,
                        motivo="Transferência pelo painel",
                        exclude_user_id=getattr(request.user, "id", None),
                    )
            except Exception as notify_err:
                logger.warning(
                    "[Transfer] Falha ao notificar atendentes conv=%s: %s",
                    conversation.id,
                    notify_err,
                )
            
            # Serializar conversa completa para retorno
            serializer = ConversationSerializer(conversation)
            
            return Response({
                'success': True,
                'conversation': serializer.data
            })
        except Exception as e:
            return Response({'error': f'Erro interno ao processar transferência: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Atribuir conversa para o usuário atual. Otimizado para concorrência."""
        from django.db import transaction
        from django.db.utils import OperationalError
        import time

        max_retries = 3
        retry_delay_seconds = 0.12

        for attempt in range(max_retries):
            try:
                assignment_to_send = None
                response_data = None
                with transaction.atomic():
                # Lock na conversa para evitar que múltiplos agentes se atribuam simultaneamente
                # CORREÇÃO: Usar select_for_update() sem select_related() para evitar erro com outer joins
                # Carregar relacionamentos depois do lock
                    conversation = Conversation.objects.select_for_update().get(pk=pk)
                # Pré-carregar relacionamentos necessários (lazy loading)
                    _ = conversation.inbox
                    if conversation.inbox:
                        _ = conversation.inbox.provedor
                    _ = conversation.contact
                    user = request.user
                
                # Verificar permissões
                    if not self._can_manage_conversation(user, conversation):
                        return Response({'error': 'Você não possui permissão para atribuir este atendimento.'}, status=403)
                
                # Se já está atribuída ao próprio usuário, retornar sucesso
                    if conversation.assignee_id == user.id and conversation.status == 'open':
                        if not (conversation.additional_attributes or {}).get('assigned_at'):
                            conversation.mark_assigned_at()
                        serializer = ConversationSerializer(conversation)
                        return Response({
                            'success': True,
                            'message': 'Este atendimento já estava atribuído para você.',
                            'conversation': serializer.data
                        })

                # Verificar se a conversa já está fechada
                    if conversation.status in ['closed', 'closing']:
                        return Response({'error': 'Não é possível atribuir um atendimento já encerrado.'}, status=400)
                
                # Atribuir conversa
                    conversation.assignee = user
                    conversation.status = 'open'
                    conversation.waiting_for_agent = True
                    conversation.updated_at = timezone.now()
                    attrs = dict(conversation.additional_attributes or {})
                    attrs['assigned_at'] = timezone.now().isoformat()
                    conversation.additional_attributes = attrs
                    conversation.save()
                
                # Registrar auditoria
                    from core.models import AuditLog
                    AuditLog.objects.create(
                        user=user,
                        action='conversation_assigned',
                        ip_address=request.META.get('REMOTE_ADDR', '127.0.0.1'),
                        details=f"Conversa atribuída para {user.get_full_name() or user.username}",
                        provedor=conversation.inbox.provedor,
                        conversation_id=conversation.id,
                        contact_name=conversation.contact.name,
                        channel_type=conversation.inbox.channel_type
                    )
                
                # Adicionar mensagem de sistema
                    Message.objects.create(
                        conversation=conversation,
                        content=f"Conversa atribuída para {user.get_full_name() or user.username}",
                        message_type='text',
                        is_from_customer=False,
                        additional_attributes={
                            'system_message': True,
                            'action': 'conversation_assigned',
                            'assigned_to': user.id
                        }
                    )

                    assignment_to_send = None
                    if user.assignment_message and user.assignment_message.strip():
                        channel_type = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
                        agent_name = (user.get_full_name() or '').strip() or user.username or 'Atendente'
                        formatted_content = self._format_message_with_agent_name(
                            user.assignment_message, user, channel_type
                        )
                        assignment_msg = Message.objects.create(
                            conversation=conversation,
                            content=user.assignment_message.strip(),
                            message_type='text',
                            is_from_customer=False,
                            additional_attributes={
                                'system_message': False,
                                'action': 'assignment_message',
                                'sent_by': user.id,
                                'agent_name': agent_name,
                            }
                        )
                        assignment_to_send = {
                            'message': assignment_msg,
                            'formatted_content': formatted_content,
                            'conversation_id': conversation.id,
                            'channel_type': channel_type,
                        }

                # Serializar resposta (ainda dentro da transação)
                    serializer = ConversationSerializer(conversation)
                    response_data = {
                        'success': True,
                        'message': f'Conversa atribuída para {user.get_full_name() or user.username}',
                        'conversation': serializer.data
                    }

                # Enviar mensagem de atribuição ao cliente FORA da transação (rede)
                if assignment_to_send:
                    try:
                        conv = Conversation.objects.select_related(
                            'inbox', 'inbox__provedor', 'contact'
                        ).get(id=assignment_to_send['conversation_id'])
                        success, channel_response = self._deliver_outbound_text(
                            conv,
                            assignment_to_send['formatted_content'],
                        )
                        msg = assignment_to_send['message']
                        attrs = dict(msg.additional_attributes or {})
                        attrs['sent_success'] = bool(success)
                        attrs['channel_type'] = assignment_to_send['channel_type']
                        if success:
                            attrs['last_status'] = 'sent'
                            attrs['sent_at'] = timezone.now().isoformat()
                            if isinstance(channel_response, dict):
                                messages = channel_response.get('messages') or []
                                if messages and isinstance(messages, list) and messages[0].get('id'):
                                    msg.external_id = messages[0]['id']
                                    attrs['external_id'] = messages[0]['id']
                                attrs['whatsapp_response'] = channel_response
                        else:
                            attrs['error_message'] = str(channel_response)[:500]
                            logger.warning(
                                f"[ASSIGN] Falha ao enviar mensagem de atribuição "
                                f"conv={conv.id}: {channel_response}"
                            )
                        msg.additional_attributes = attrs
                        update_fields = ['additional_attributes']
                        if msg.external_id:
                            update_fields.append('external_id')
                        msg.save(update_fields=update_fields)
                    except Exception as e:
                        logger.error(f"[ASSIGN] Erro ao enviar msg atribuição: {e}", exc_info=True)

                return Response(response_data)
            except OperationalError as e:
                # SQLite em desenvolvimento pode bloquear sob concorrência curta.
                # Fazemos tentativas rápidas antes de retornar erro ao usuário.
                if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(retry_delay_seconds * (attempt + 1))
                    continue
                logger.error(f"Erro de banco ao atribuir conversa: {e}", exc_info=True)
                return Response(
                    {'error': 'Não foi possível concluir a atribuição neste momento. Tente novamente em instantes.'},
                    status=503
                )
            except Exception as e:
                logger.error(f"Erro ao atribuir conversa: {e}", exc_info=True)
                return Response(
                    {'error': 'Não foi possível atribuir o atendimento agora. Tente novamente em instantes.'},
                    status=500
                )

    @action(detail=True, methods=['post'])
    def close_conversation_agent(self, request, pk=None):
        """Encerrar conversa por atendente"""
        try:
            conversation = self.get_object()
        except Exception:
            # Conversa não encontrada no PostgreSQL local
            # Verificar se foi migrada para o Supabase
            conversation_id = pk or request.data.get('conversation_id')
            if conversation_id:
                try:
                    from core.chat_migration_service import chat_migration_service
                    # Obter provedor_id do usuário
                    provedor_id = None
                    if hasattr(request.user, 'provedor') and request.user.provedor:
                        provedor_id = request.user.provedor.id
                    elif hasattr(request.user, 'provedor_id'):
                        provedor_id = request.user.provedor_id
                    
                    # Tentar verificar no Supabase
                    if provedor_id and chat_migration_service.verificar_conversa_no_supabase(int(conversation_id), provedor_id):
                        return Response({
                            'error': 'Esta conversa já foi encerrada e migrada para o histórico. Ela não pode ser encerrada novamente.',
                            'migrated': True,
                            'conversation_id': conversation_id
                        }, status=410)  # 410 Gone - recurso não está mais disponível
                except Exception as e:
                    logger.debug(f"Erro ao verificar conversa no Supabase: {e}")
                    pass
            
            logger.warning(f"[CloseConversation] Conversa {conversation_id} não encontrada. ProvedorID: {provedor_id}")
            return Response({
                'error': 'Conversa não encontrada',
                'conversation_id': conversation_id
            }, status=404)
        
        user = request.user
        
        # Verificar se o usuário tem permissão para encerrar a conversa
        if not self._can_manage_conversation(user, conversation):
            return Response({'error': 'Sem permissão para encerrar esta conversa'}, status=403)
        
        # Verificar se a conversa já está fechada ou em closing
        if conversation.status in ['closed', 'closing']:
            return Response({'error': f'Conversa já está {conversation.status}'}, status=400)
        
        # Obter dados da requisição
        resolution_type = request.data.get('resolution_type', 'resolved')
        resolution_notes = request.data.get('resolution_notes', '')
        send_csat = request.data.get('send_csat', True)
        if isinstance(send_csat, str):
            send_csat = send_csat.strip().lower() in ('1', 'true', 'yes', 'sim', 'y')
        
        # Atualizar status da conversa (liberar flags humanas para próximo ciclo do bot)
        conversation.status = 'closed'
        conversation.assignee = None
        conversation.waiting_for_agent = False
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['status', 'assignee', 'waiting_for_agent', 'updated_at'])

        # CSAT (opcional): envio imediato com lista interativa WhatsApp
        csat_sent = False
        csat_request_id = None
        csat_blocked_recently = False
        if send_csat:
            try:
                from .csat_service import CSATService
                csat_req = CSATService.schedule_csat_request(
                    conversation_id=conversation.id,
                    ended_by_user_id=user.id if user and user.is_authenticated else None,
                    send_immediately=True,
                )
                if csat_req:
                    csat_req.refresh_from_db()
                    csat_request_id = csat_req.id
                    # Se o CSAT retornado for de outra conversa (ex.: bloqueio por intervalo mínimo),
                    # considere como não enviado neste encerramento.
                    csat_blocked_recently = csat_req.conversation_id != conversation.id
                    csat_sent = (csat_req.status == 'sent' and not csat_blocked_recently)
                    if not csat_sent:
                        logger.error(
                            f"[CSAT] Pesquisa não enviada ao cliente — conversa {conversation.id}, "
                            f"request={csat_req.id} status={csat_req.status}"
                        )
            except Exception as csat_error:
                logger.error(
                    f"[CSAT] Erro ao agendar CSAT para conversa {conversation.id}: {csat_error}",
                    exc_info=True
                )
        
        # Calcular duração da conversa
        duracao = None
        if conversation.created_at:
            duracao = timezone.now() - conversation.created_at
        
        # Contar mensagens
        message_count = conversation.messages.count()
        
        # Criar AuditLog no Django (para estatísticas funcionarem)
        # Verificar se já existe um log para esta conversa para evitar duplicação
        try:
            from core.models import AuditLog
            provedor = conversation.inbox.provedor
            
            # Verificar se já existe um AuditLog para esta conversa com esta ação
            existing_log = AuditLog.objects.filter(
                conversation_id=conversation.id,
                action='conversation_closed_manual'
            ).first()
            
            # Só criar se não existir
            if not existing_log:
                details_text = f"Conversa encerrada manualmente por {user.get_full_name() or user.username} com {conversation.contact.name} via {conversation.inbox.channel_type}"
                if resolution_type:
                    details_text += f" | Tipo de resolução: {resolution_type}"
                if resolution_notes:
                    details_text += f" | Observações: {resolution_notes}"
                if duracao:
                    details_text += f" | Duração: {duracao}"
                if message_count:
                    details_text += f" | Mensagens: {message_count}"
                
                AuditLog.objects.create(
                    user=user,
                    action='conversation_closed_manual',
                    ip_address=request.META.get('REMOTE_ADDR', '127.0.0.1'),
                    details=details_text,
                    provedor=provedor,
                    conversation_id=conversation.id,
                    contact_name=conversation.contact.name,
                    channel_type=conversation.inbox.channel_type
                )
            else:
                logger.info(f"AuditLog já existe para conversa {conversation.id}, evitando duplicação")
        except Exception as audit_err:
            # logger.warning(f"Falha ao criar/verificar AuditLog no Django: {audit_err}")
            logger.warning(f"Falha ao criar/verificar AuditLog no Django: {audit_err}")
        
        try:
            from core.redis_memory_service import redis_memory_service
            p_id = conversation.inbox.provedor_id if (conversation.inbox and conversation.inbox.provedor_id) else None
            
            # Se não tem provedor_id via inbox, tenta via atributo direto ou request
            if not p_id:
                p_id = getattr(conversation, 'provedor_id', None)
            
            if p_id:
                redis_cleared = redis_memory_service.clear_conversation_memory_sync(
                    provedor_id=p_id,
                    conversation_id=conversation.id
                )
                if redis_cleared:
                    logger.info(f"[CloseConversation] ✓ Memória Redis limpa imediatamente para conversa {conversation.id} (provedor {p_id})")
                else:
                    logger.warning(f"[CloseConversation] ✗ Falha ao limpar memória Redis para conversa {conversation.id}")
            else:
                logger.warning(f"[CloseConversation] ⚠ Não foi possível determinar provedor_id para limpar Redis da conversa {conversation.id}")
        except Exception as redis_err:
            logger.error(f"[CloseConversation] Erro ao limpar memória Redis da conversa {conversation.id}: {redis_err}", exc_info=True)
        
        # IMPORTANTE: Criar mensagem de sistema ANTES da migração
        # (após migração, a conversa será removida do local)
        try:
            # from conversations.models import Message
            Message.objects.create(
                conversation=conversation,
                content=f"Conversa encerrada por {user.get_full_name() or user.username}. Resolução: {resolution_type}. {resolution_notes}",
                message_type='text',
                is_from_customer=False,
                additional_attributes={
                    'system_message': True,
                    'action': 'conversation_closed',
                    'closed_by': user.id,
                    'resolution_type': resolution_type,
                    'resolution_notes': resolution_notes
                }
            )
        except Exception as msg_err:
            logger.warning(f"Erro ao criar mensagem de sistema: {msg_err}")
        
        # Migração: adiar se CSAT foi solicitado (conversa local precisa existir para envio/resposta)
        if send_csat:
            logger.info(
                f"[CloseConversation] Migração adiada para conversa {conversation.id} "
                f"(aguardando CSAT — resposta do cliente ou timeout)"
            )
        else:
            logger.info(
                f"[CloseConversation] Migrando conversa {conversation.id} para Supabase (sem CSAT)"
            )
            try:
                from core.chat_migration_service import chat_migration_service
                migration_result = chat_migration_service.encerrar_e_migrar(
                    conversation_id=conversation.id,
                    metadata={
                        'encerrado_por': 'agent',
                        'finalizado_por': 'agente_imediato',
                        'resolution_type': resolution_type,
                        'resolution_notes': resolution_notes,
                        'user_id': user.id
                    }
                )
                if migration_result.get('success'):
                    logger.info(
                        f"[CloseConversation] ✓ Conversa {conversation.id} migrada para Supabase"
                    )
                else:
                    logger.warning(
                        f"[CloseConversation] ✗ Falha ao migrar conversa {conversation.id}: "
                        f"{migration_result.get('errors', [])}"
                    )
            except Exception as migration_err:
                logger.error(
                    f"[CloseConversation] Erro ao migrar conversa {conversation.id}: {migration_err}",
                    exc_info=True,
                )
        
        # Enviar notificação WebSocket para atualizar o frontend
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'painel_{conversation.inbox.provedor.id}',
                {
                    'type': 'conversation_status_changed',
                    'conversation': {
                        'id': conversation.id,
                        'status': conversation.status,
                        'assignee': conversation.assignee.username if conversation.assignee else None,
                        'updated_at': conversation.updated_at.isoformat()
                    },
                    'message': f'Conversa {conversation.id} encerrada por {user.username}',
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            pass
        
        resp_message = 'Conversa encerrada com sucesso'
        if send_csat and not csat_sent:
            if csat_blocked_recently:
                resp_message = (
                    'Conversa encerrada, mas a pesquisa CSAT não foi enviada porque respeita '
                    'o intervalo mínimo configurado entre envios para o mesmo cliente.'
                )
            else:
                resp_message = (
                    'Conversa encerrada, mas a pesquisa CSAT não foi enviada ao cliente. '
                    'Verifique o canal WhatsApp e tente novamente.'
                )
        return Response({
            'status': 'success',
            'message': resp_message,
            'conversation_id': conversation.id,
            'resolution_type': resolution_type,
            'csat_sent': csat_sent,
            'csat_request_id': csat_request_id,
        })
    
    @action(detail=True, methods=['get'])
    def details_from_supabase(self, request, pk=None):
        """Buscar detalhes da conversa do Supabase"""
        try:
            import requests
            from django.conf import settings
            
            # Buscar dados da conversa no Supabase
            url = f'{settings.SUPABASE_URL}/rest/v1/conversations'
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json'
            }
            
            # Filtrar por ID da conversa
            params = {'id': f'eq.{pk}'}
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                conversations = response.json()
                if conversations:
                    conv_data = conversations[0]
                    
                    # Buscar dados do contato
                    contact_url = f'{settings.SUPABASE_URL}/rest/v1/contacts'
                    contact_params = {'id': f'eq.{conv_data.get("contact_id")}'}
                    contact_response = requests.get(contact_url, headers=headers, params=contact_params)
                    
                    contact_data = {}
                    if contact_response.status_code == 200:
                        contacts = contact_response.json()
                        if contacts:
                            contact_data = contacts[0]
                    
                    # Buscar CSAT feedback
                    csat_url = f'{settings.SUPABASE_URL}/rest/v1/csat_feedback'
                    csat_params = {'conversation_id': f'eq.{pk}'}
                    csat_response = requests.get(csat_url, headers=headers, params=csat_params)
                    
                    csat_data = {}
                    if csat_response.status_code == 200:
                        csats = csat_response.json()
                        if csats:
                            csat_data = csats[0]
                    
                    # Buscar mensagens
                    messages_url = f'{settings.SUPABASE_URL}/rest/v1/mensagens'
                    messages_params = {'conversation_id': f'eq.{pk}'}
                    messages_response = requests.get(messages_url, headers=headers, params=messages_params)
                    
                    messages_data = []
                    if messages_response.status_code == 200:
                        messages_data = messages_response.json()
                    
                    # Montar resposta
                    result = {
                        'conversation': {
                            'id': conv_data.get('id'),
                            'status': conv_data.get('status'),
                            'created_at': conv_data.get('created_at'),
                            'updated_at': conv_data.get('updated_at'),
                            'ended_at': conv_data.get('ended_at'),
                            'assignee_id': conv_data.get('assignee_id')
                        },
                        'contact': {
                            'id': contact_data.get('id'),
                            'name': contact_data.get('name'),
                            'phone': contact_data.get('phone'),
                            'email': contact_data.get('email'),
                            'avatar': contact_data.get('avatar')
                        },
                        'csat': {
                            'rating_value': csat_data.get('rating_value'),
                            'emoji_rating': csat_data.get('emoji_rating'),
                            'feedback_sent_at': csat_data.get('feedback_sent_at')
                        },
                        'messages': messages_data,
                        'message_count': len(messages_data)
                    }
                    
                    return Response(result)
                else:
                    return Response({'error': 'Conversa não encontrada no Supabase'}, status=404)
            else:
                return Response({'error': 'Erro ao buscar conversa no Supabase'}, status=500)
                
        except Exception as e:
            return Response({'error': f'Erro interno: {str(e)}'}, status=500)

    @action(detail=True, methods=['post'])
    def close_conversation_ai(self, request, pk=None):
        """Encerrar conversa por IA"""
        conversation = self.get_object()
        user = request.user
        
        # Verificar se o usuário tem permissão para encerrar a conversa
        if not self._can_manage_conversation(user, conversation):
            return Response({'error': 'Sem permissão para encerrar esta conversa'}, status=403)
        
        # Verificar se a conversa já está fechada ou em closing
        if conversation.status in ['closed', 'closing']:
            return Response({'error': f'Conversa já está {conversation.status}'}, status=400)
        
        # Obter dados da requisição
        resolution_type = request.data.get('resolution_type', 'ai_resolved')
        resolution_notes = request.data.get('resolution_notes', '')
        ai_reason = request.data.get('ai_reason', 'Resolução automática por IA')
        
        # Usar ClosingService para solicitar encerramento (estado intermediário 'closing')
        from conversations.closing_service import closing_service
        closing_service.request_closing(conversation)
        
        # Atualizar updated_at
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        
        # Limpar memória Redis da conversa encerrada IMEDIATAMENTE
        try:
            from core.redis_memory_service import redis_memory_service
            redis_cleared = redis_memory_service.clear_conversation_memory_sync(
                provedor_id=conversation.inbox.provedor_id if conversation.inbox else None,
                conversation_id=conversation.id
            )
            if redis_cleared:
                logger.info(f"[CloseConversationAI] ✓ Memória Redis limpa imediatamente para conversa {conversation.id} (encerrada pela IA via API)")
            else:
                logger.warning(f"[CloseConversationAI] ✗ Falha ao limpar memória Redis para conversa {conversation.id}")
        except Exception as redis_err:
            logger.error(f"[CloseConversationAI] Erro ao limpar memória Redis da conversa {conversation.id}: {redis_err}", exc_info=True)
        
        # Registrar auditoria
        log_conversation_closure(
            request=request,
            conversation=conversation,
            action_type='conversation_closed_ai',
            resolution_type=resolution_type,
            user=user
        )
        
        # Adicionar mensagem de sistema sobre o encerramento por IA
        Message.objects.create(
            conversation=conversation,
            content=f"Conversa encerrada automaticamente pela IA. Motivo: {ai_reason}. Resolução: {resolution_type}. {resolution_notes}",
            message_type='text',
            is_from_customer=False,
            additional_attributes={
                'system_message': True,
                'action': 'conversation_closed_ai',
                'closed_by_ai': True,
                'ai_reason': ai_reason,
                'resolution_type': resolution_type,
                'resolution_notes': resolution_notes
            }
        )
        
        # Migrar para Supabase IMEDIATAMENTE quando encerrada pela IA via API
        logger.info(f"[CloseConversationAI] Migrando conversa {conversation.id} para Supabase imediatamente (encerrada pela IA via API)")
        try:
            # Primeiro, finalizar a conversa (mudar de 'closing' para 'closed')
            conversation.status = 'closed'
            conversation.save(update_fields=['status'])
            
            from core.chat_migration_service import chat_migration_service
            migration_result = chat_migration_service.encerrar_e_migrar(
                conversation_id=conversation.id,
                metadata={
                    'encerrado_por': 'ai',
                    'finalizado_por': 'api_imediato',
                    'ai_reason': ai_reason,
                    'resolution_type': resolution_type,
                    'resolution_notes': resolution_notes,
                    'user_id': user.id
                }
            )
            if migration_result.get('success'):
                logger.info(f"[CloseConversationAI] ✓ Conversa {conversation.id} migrada para Supabase imediatamente (encerrada pela IA via API)")
            else:
                logger.warning(f"[CloseConversationAI] ✗ Falha ao migrar conversa {conversation.id} para Supabase: {migration_result.get('errors', [])}")
        except Exception as migration_err:
            logger.error(f"[CloseConversationAI] Erro ao migrar conversa {conversation.id} para Supabase: {migration_err}", exc_info=True)
        
        return Response({
            'status': 'success',
            'message': 'Conversa encerrada pela IA com sucesso',
            'conversation_id': conversation.id,
            'resolution_type': resolution_type,
            'ai_reason': ai_reason
        })
    
    def _agent_belongs_to_provedor(self, user, provedor) -> bool:
        """Atendente vinculado ao provedor via FK ou membro de equipe."""
        if not provedor:
            return False
        if getattr(user, 'provedor_id', None) == provedor.id:
            return True
        return TeamMember.objects.filter(user=user, team__provedor=provedor).exists()

    def _can_manage_conversation(self, user, conversation):
        """Verificar se o usuário pode gerenciar a conversa"""
        # Superadmin pode gerenciar todas as conversas
        if user.user_type == 'superadmin':
            return True
        
        # Admin pode gerenciar conversas do seu provedor
        if user.user_type == 'admin':
            provedores = Provedor.objects.filter(admins=user)
            return provedores.filter(id=conversation.inbox.provedor.id).exists()
        
        # Atendente: próprio atendimento ou mesmo provedor (FK ou equipe)
        if user.user_type == 'agent':
            if conversation.assignee_id == user.id:
                return True
            provedor = conversation.inbox.provedor if conversation.inbox else None
            return self._agent_belongs_to_provedor(user, provedor)
        
        return False

    _BULK_CLOSE_STATUSES = frozenset(
        ['closed', 'encerrada', 'resolved', 'finalizada', 'closing']
    )

    def _resolve_provedor_for_bulk_action(self, request):
        user = request.user
        provedor_id = request.data.get('provedor_id') or request.query_params.get('provedor_id')
        provedor = None

        if user.user_type == 'superadmin':
            if provedor_id:
                try:
                    provedor = Provedor.objects.filter(id=int(provedor_id)).first()
                except (TypeError, ValueError):
                    provedor = None
            if not provedor and getattr(user, 'provedor_id', None):
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
        elif user.user_type == 'admin':
            if provedor_id:
                try:
                    provedor = Provedor.objects.filter(id=int(provedor_id), admins=user).first()
                except (TypeError, ValueError):
                    provedor = None
            if not provedor:
                provedor = Provedor.objects.filter(admins=user, is_active=True).first()

        return provedor

    def _bulk_close_queryset(self, request):
        from datetime import timedelta

        from django.db.models.functions import Coalesce

        user = request.user
        provedor = self._resolve_provedor_for_bulk_action(request)
        if not provedor:
            return None, 'Provedor não identificado para esta operação.'

        if user.user_type not in ('superadmin', 'admin'):
            return None, 'Sem permissão para encerramento em lote.'

        scope = str(request.data.get('scope') or 'automation').strip().lower()
        min_minutes = request.data.get('min_minutes')
        max_minutes = request.data.get('max_minutes')

        if scope not in ('automation', 'waiting'):
            return None, 'Escopo inválido. Use automation ou waiting.'

        qs = Conversation.objects.filter(inbox__provedor=provedor).exclude(
            status__in=self._BULK_CLOSE_STATUSES
        )

        if scope == 'automation':
            qs = qs.filter(assignee__isnull=True, waiting_for_agent=False)
        else:
            qs = qs.filter(assignee__isnull=True, waiting_for_agent=True)

        qs = qs.annotate(
            ref_at=Coalesce('updated_at', 'last_message_at', 'created_at')
        )
        now = timezone.now()

        if min_minutes is not None and str(min_minutes).strip() != '':
            try:
                mins = max(0, int(min_minutes))
                qs = qs.filter(ref_at__lte=now - timedelta(minutes=mins))
            except (TypeError, ValueError):
                return None, 'min_minutes inválido.'

        if max_minutes is not None and str(max_minutes).strip() != '':
            try:
                mins = max(0, int(max_minutes))
                qs = qs.filter(ref_at__gte=now - timedelta(minutes=mins))
            except (TypeError, ValueError):
                return None, 'max_minutes inválido.'

        return qs, None

    @action(detail=False, methods=['post'], url_path='bulk-close-preview')
    def bulk_close_preview(self, request):
        """Conta conversas que seriam encerradas pelo filtro informado."""
        qs, error = self._bulk_close_queryset(request)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'count': qs.count(), 'scope': request.data.get('scope') or 'all'})

    @action(detail=False, methods=['post'], url_path='bulk-close')
    def bulk_close(self, request):
        """Encerra em lote conversas abertas conforme escopo e tempo configurados."""
        user = request.user
        if user.user_type not in ('superadmin', 'admin'):
            return Response({'error': 'Sem permissão para encerramento em lote.'}, status=403)

        qs, error = self._bulk_close_queryset(request)
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        provedor = self._resolve_provedor_for_bulk_action(request)
        conversation_ids = list(qs.values_list('id', flat=True))
        count = len(conversation_ids)
        if count == 0:
            return Response({
                'closed': 0,
                'ids': [],
                'message': 'Nenhuma conversa encontrada com os filtros informados.',
            })

        now = timezone.now()
        with transaction.atomic():
            qs.update(
                status='closed',
                assignee_id=None,
                waiting_for_agent=False,
                closing_requested_at=None,
                updated_at=now,
            )
            try:
                scope = request.data.get('scope') or 'all'
                min_minutes = request.data.get('min_minutes')
                max_minutes = request.data.get('max_minutes')
                filters = [f'escopo={scope}']
                if min_minutes not in (None, ''):
                    filters.append(f'min_minutos={min_minutes}')
                if max_minutes not in (None, ''):
                    filters.append(f'max_minutos={max_minutes}')
                AuditLog.objects.create(
                    user=user,
                    action='conversation_closed_bulk',
                    ip_address=request.META.get('REMOTE_ADDR', '127.0.0.1'),
                    details=(
                        f'Encerramento em lote de {count} conversa(s) '
                        f'({", ".join(filters)}) por '
                        f'{user.get_full_name() or user.username}'
                    ),
                    provedor=provedor,
                )
            except Exception as audit_err:
                logger.warning('[BulkClose] Falha ao registrar AuditLog: %s', audit_err)

        logger.info(
            '[BulkClose] %s conversa(s) encerradas — provedor=%s user=%s',
            count,
            provedor.id if provedor else None,
            user.id,
        )
        return Response({
            'closed': count,
            'ids': conversation_ids,
            'message': f'{count} atendimento(s) encerrado(s) com sucesso.',
        })




def send_media_via_uazapi(conversation, file_url, media_type, caption, reply_to_message_id=None, local_message_id=None):
    """
    Envia mídia via Uazapi usando a URL do arquivo ou base64
    
    Args:
        conversation: Objeto Conversation
        file_url: URL do arquivo
        media_type: Tipo de mídia (image, video, document, audio, etc)
        caption: Legenda da mídia
        reply_to_message_id: ID da mensagem para responder
        local_message_id: ID da mensagem local para usar como track_id
    """
    try:
        # Iniciando envio de mídia
        
        # Log específico para PTT
        # Determinar tipo de mídia
        
        # Obter credenciais do provedor
        provedor = conversation.inbox.provedor
        uazapi_token = None
        uazapi_url = None
        
        # Buscar na integração WhatsApp primeiro
        whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
        if whatsapp_integration:
            uazapi_token = whatsapp_integration.access_token
            uazapi_url = (
                whatsapp_integration.settings.get('whatsapp_url')
                if whatsapp_integration.settings else None
            )
            # NÃO usar webhook_url como fallback - é a URL local para receber webhooks
            # if not uazapi_url:
            #     uazapi_url = whatsapp_integration.webhook_url
            # URL da integração WhatsApp
        else:
            # Fallback inicial para integracoes_externas
            integracoes = provedor.integracoes_externas or {}
            uazapi_token = uazapi_token or integracoes.get('whatsapp_token')
            uazapi_url = uazapi_url or integracoes.get('whatsapp_url')

        # Reforço: mesmo que exista integração WhatsApp, garanta preenchimento a partir de integracoes_externas
        integracoes_ref = provedor.integracoes_externas or {}
        if not uazapi_token:
            uazapi_token = integracoes_ref.get('whatsapp_token')
        if not uazapi_url:
            uazapi_url = integracoes_ref.get('whatsapp_url')
        
        if not uazapi_token or not uazapi_url:
            return False, "Token ou URL do Uazapi não configurados"
        
        # Garantir que a URL termina com /send/media
        if uazapi_url and not uazapi_url.endswith('/send/media'):
            uazapi_url = uazapi_url.rstrip('/') + '/send/media'
        
        # Obter número do contato
        contact = conversation.contact
        sender_lid = contact.additional_attributes.get('sender_lid')
        chatid = contact.additional_attributes.get('chatid')
        
        # Verificar se não estamos enviando para o número conectado
        instance = conversation.inbox.additional_attributes.get('instance')
        if instance:
            clean_instance = instance.replace('@s.whatsapp.net', '').replace('@c.us', '')
            clean_chatid = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '') if chatid else ''
            clean_sender_lid = sender_lid.replace('@lid', '').replace('@c.us', '') if sender_lid else ''
            
            if (clean_chatid == clean_instance) or (clean_sender_lid == clean_instance):
                return False, "Não é possível enviar mensagens para o número conectado na instância"
        
        # Usar APENAS chatid, ignorar sender_lid
        success = False
        send_result = None
        
        if chatid:
            try:
                # Converter URL para base64 e manter bytes (para usar no client)
                file_base64 = None
                file_bytes = None
                
                # Se file_url é uma URL local, ler o arquivo e converter para base64
                if file_url.startswith('/api/media/'):
                    # Construir caminho completo do arquivo
                    normalized_url = file_url.rstrip('/')
                    file_path = normalized_url.replace('/api/media/messages/', '')
                    conversation_id, filename = file_path.split('/', 1)
                    full_path = os.path.join(settings.MEDIA_ROOT, 'messages', conversation_id, filename)
                    
                    if os.path.exists(full_path):
                        with open(full_path, 'rb') as f:
                            file_bytes = f.read()
                            file_base64 = base64.b64encode(file_bytes).decode('utf-8')
                    else:
                        return False, f"Arquivo não encontrado: {full_path}"
                elif file_url.startswith('data:'):
                    # Já é base64
                    # data URL contém base64 depois de ","
                    try:
                        file_base64 = file_url.split(',', 1)[1]
                    except Exception:
                        file_base64 = file_url
                else:
                    # URL externa, tentar baixar
                    try:
                        response = requests.get(file_url, timeout=30)
                        if response.status_code == 200:
                            file_bytes = response.content
                            file_base64 = base64.b64encode(file_bytes).decode('utf-8')
                        else:
                            return False, f"Erro ao baixar arquivo: {response.status_code}"
                    except Exception as e:
                        return False, f"Erro ao baixar arquivo: {str(e)}"
                
                # Detectar MIME básico a partir do tipo/arquivo
                mime = None
                if media_type == 'image':
                    # Tentar inferir pelo nome do arquivo
                    ext = (filename.split('.')[-1].lower() if 'filename' in locals() else 'png')
                    mime = 'image/jpeg' if ext in ['jpg', 'jpeg'] else 'image/png'
                elif media_type == 'video':
                    mime = 'video/mp4'
                elif media_type in ['audio', 'ptt']:
                    # ptt = push-to-talk (ogg/opus normalmente)
                    mime = 'audio/ogg'
                elif media_type == 'document':
                    # Para documentos, detectar MIME pela extensão
                    if 'filename' in locals() and filename:
                        ext = filename.split('.')[-1].lower()
                        mime_map = {
                            'pdf': 'application/pdf',
                            'doc': 'application/msword',
                            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            'xls': 'application/vnd.ms-excel',
                            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        }
                        mime = mime_map.get(ext, 'application/pdf')
                    else:
                        mime = 'application/pdf'
                
                file_field = file_base64
                # Para imagens/vídeos/áudios/documentos enviar como data URL base64 quando tivermos os bytes
                if mime and file_base64 and not (isinstance(file_base64, str) and file_base64.startswith('data:')):
                    file_field = f"data:{mime};base64,{file_base64}"
                
                # Limpar número (chatid -> apenas dígitos)
                number_clean = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '')

                # Formato correto da API Uazapi para mídia
                payload = {
                    'number': number_clean,
                    'type': 'ptt' if media_type == 'ptt' else media_type,
                    'file': file_field,
                    'readchat': True
                }
                
                # Legenda: Uazapi usa campo 'text'
                if caption and media_type != 'ptt':
                    payload['text'] = caption
                
                # Enviar usando o mesmo cliente da rotina manual (mais robusto)
                try:
                    from core.uazapi_client import UazapiClient
                    client = UazapiClient(uazapi_url.replace('/send/media',''), uazapi_token)
                    # Preferir bytes quando disponíveis
                    if not file_bytes and file_base64:
                        import base64 as _b64
                        file_bytes = _b64.b64decode(file_base64)
                    numero_envio = number_clean
                    
                    # Preparar reply_id se fornecido
                    reply_id = None
                    if reply_to_message_id:
                        # Extrair apenas o ID da mensagem (remover prefixos se houver)
                        if isinstance(reply_to_message_id, str) and ':' in reply_to_message_id:
                            reply_id = reply_to_message_id.split(':', 1)[1]
                        else:
                            reply_id = str(reply_to_message_id)
                    
                    # Usar método específico baseado no tipo de mídia
                    if media_type in ['ptt', 'audio', 'myaudio']:
                        # Para áudio, usar método específico
                        ok = client.enviar_audio(numero_envio, file_bytes, audio_type=media_type, legenda=(caption or ''), instance_id=None, reply_id=reply_id)
                    elif media_type == 'image':
                        # Para imagem, usar método de imagem
                        ok = client.enviar_imagem(numero_envio, file_bytes, legenda=(caption or ''), instance_id=None, reply_id=reply_id)
                    else:
                        # Para outros tipos (documento, video, etc), usar método de documento
                        # Extrair nome do arquivo do file_url ou usar filename se disponível
                        nome_arquivo = "documento.pdf"
                        if 'filename' in locals() and filename:
                            nome_arquivo = filename
                        elif file_url:
                            # Tentar extrair do file_url
                            if '/' in file_url:
                                nome_arquivo = file_url.split('/')[-1]
                                # Remover query params se houver
                                if '?' in nome_arquivo:
                                    nome_arquivo = nome_arquivo.split('?')[0]
                                # Remover fragmentos se houver
                                if '#' in nome_arquivo:
                                    nome_arquivo = nome_arquivo.split('#')[0]
                            # Se não tem extensão, adicionar .pdf como padrão para documentos
                            if media_type == 'document' and not nome_arquivo.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.rtf')):
                                nome_arquivo = f"{nome_arquivo}.pdf"
                        
                        # Para documentos, usar base64 ou URL completa conforme disponível
                        # A Uazapi aceita URL ou base64, então preferir base64 se disponível (mais confiável)
                        if 'file_field' in locals() and file_field:
                            # Usar base64 (data URL ou base64 puro)
                            documento_data = file_field
                        elif 'file_base64' in locals() and file_base64:
                            # Se temos base64 mas não file_field, criar data URL
                            mime_doc = 'application/pdf' if media_type == 'document' else 'application/octet-stream'
                            documento_data = f"data:{mime_doc};base64,{file_base64}"
                        else:
                            # Fallback: usar file_url (deve ser URL completa e acessível)
                            documento_data = file_url
                        
                        # Usar ID da mensagem local como track_id para facilitar busca posterior
                        ok = client.enviar_documento(
                            numero_envio, 
                            documento_data, 
                            nome_arquivo=nome_arquivo, 
                            legenda=(caption or ''), 
                            instance_id=None, 
                            reply_id=reply_id,
                            track_id=local_message_id,
                            track_source='niochat'
                        )
                    
                    success = bool(ok)
                    send_result = {'ok': ok}
                except Exception as e:
                    success = False
                    send_result = {'error': str(e)}
                    
            except Exception as e:
                pass
        else:
            pass
        
        if success:
            return True, f"Mídia enviada com sucesso: {send_result}"
        else:
            return False, f"Erro na Uazapi: Falha ao enviar mídia para chatid"
            
    except Exception as e:
        return False, f"Erro ao enviar mídia via Uazapi: {str(e)}"


def send_via_uazapi(conversation, content, message_type, instance, reply_to_message_id=None):
    """
    Envia mensagem via Uazapi usando a mesma lógica da IA
    """
    try:
        # Obter credenciais do provedor (mesma lógica da IA)
        provedor = conversation.inbox.provedor
        uazapi_token = None
        uazapi_url = None
        
        # Buscar na integração WhatsApp primeiro
        whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
        if whatsapp_integration:
            uazapi_token = whatsapp_integration.access_token
            uazapi_url = (
                whatsapp_integration.settings.get('whatsapp_url')
                if whatsapp_integration.settings else None
            )
            # NÃO usar webhook_url como fallback - é a URL local para receber webhooks
            # if not uazapi_url:
            #     uazapi_url = whatsapp_integration.webhook_url
        
        # Fallback para integracoes_externas
        if not uazapi_token or uazapi_token == '':
            integracoes = provedor.integracoes_externas or {}
            uazapi_token = integracoes.get('whatsapp_token')
        if not uazapi_url or uazapi_url == '':
            integracoes = provedor.integracoes_externas or {}
            uazapi_url = integracoes.get('whatsapp_url')
        
        if not uazapi_token or not uazapi_url:
            return False, "Token ou URL do Uazapi não configurados"
        
        # Garantir que a URL termina com /send/text
        if uazapi_url and not uazapi_url.endswith('/send/text'):
            uazapi_url = uazapi_url.rstrip('/') + '/send/text'
        
        
        # Obter número do contato (mesma lógica da IA)
        contact = conversation.contact
        sender_lid = contact.additional_attributes.get('sender_lid')
        chatid = contact.additional_attributes.get('chatid')
        
        # Verificar se não estamos enviando para o número conectado
        instance = conversation.inbox.additional_attributes.get('instance')
        if instance:
            clean_instance = instance.replace('@s.whatsapp.net', '').replace('@c.us', '')
            clean_chatid = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '') if chatid else ''
            clean_sender_lid = sender_lid.replace('@lid', '').replace('@c.us', '') if sender_lid else ''
            
            if (clean_chatid == clean_instance) or (clean_sender_lid == clean_instance):
                return False, "Não é possível enviar mensagens para o número conectado na instância"
        
        # Usar APENAS chatid, ignorar sender_lid
        success = False
        send_result = None
        
        if chatid:
            try:
                # Formato correto da API Uazapi
                payload = {
                    'number': chatid,
                    'text': content
                }
                
                # Adicionar informações de resposta se existir
                if reply_to_message_id:
                    # Formato correto para Uazapi - usar replyid conforme documentação
                    # Formato correto para Uazapi - usar apenas o ID da mensagem
                    if isinstance(reply_to_message_id, str):
                        # Se o ID contém ":", pegar apenas a parte após ":"
                        if ':' in reply_to_message_id:
                            short_id = reply_to_message_id.split(':', 1)[1]
                            payload['replyid'] = short_id
                        else:
                            payload['replyid'] = reply_to_message_id
                    
                    # Tentar formato alternativo se o primeiro falhar
                    # Algumas APIs esperam um objeto com mais informações
                    if isinstance(reply_to_message_id, str) and ':' in reply_to_message_id:
                        # Se o ID contém ":", pode ser necessário apenas a parte após ":"
                        short_id = reply_to_message_id.split(':', 1)[1]
                
                response = requests.post(
                    uazapi_url,
                    headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    send_result = response.json() if response.content else response.status_code
                    success = True
                else:
                    send_result = f"Erro na API Uazapi: {response.status_code} - {response.text}"
            except Exception as e:
                send_result = f"Erro ao enviar: {str(e)}"
        else:
            send_result = "Nenhum chatid encontrado para envio"
        
        if success:
            return True, f"Mensagem enviada com sucesso: {send_result}"
        else:
            return False, f"Erro na Uazapi: Falha ao enviar para chatid"
            
    except Exception as e:
        return False, f"Erro ao enviar via Uazapi: {str(e)}"


def send_presence_via_uazapi(conversation, presence_type):
    """
    Envia indicador de presença (digitando) via Uazapi
    """
    try:
        # Obter credenciais do provedor (mesma lógica da IA)
        provedor = conversation.inbox.provedor
        uazapi_token = None
        uazapi_url = None
        
        # Buscar na integração WhatsApp primeiro
        whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
        if whatsapp_integration:
            uazapi_token = whatsapp_integration.access_token
            uazapi_url = (
                whatsapp_integration.settings.get('whatsapp_url')
                if whatsapp_integration.settings else None
            )
            # NÃO usar webhook_url como fallback - é a URL local para receber webhooks
            # if not uazapi_url:
            #     uazapi_url = whatsapp_integration.webhook_url
        
        # Fallback para integracoes_externas
        if not uazapi_token or uazapi_token == '':
            integracoes = provedor.integracoes_externas or {}
            uazapi_token = integracoes.get('whatsapp_token')
        if not uazapi_url or uazapi_url == '':
            integracoes = provedor.integracoes_externas or {}
            uazapi_url = integracoes.get('whatsapp_url')
        
        if not uazapi_token or not uazapi_url:
            return False, "Token ou URL do Uazapi não configurados"
        
        # Garantir que a URL termina com /message/presence
        if uazapi_url and not uazapi_url.endswith('/message/presence'):
            uazapi_url = uazapi_url.rstrip('/') + '/message/presence'
        
        
        # Obter número do contato (mesma lógica da IA)
        contact = conversation.contact
        sender_lid = contact.additional_attributes.get('sender_lid')
        chatid = contact.additional_attributes.get('chatid')
        
        # Tentar enviar para ambos os números como a IA faz
        success = False
        send_result = None
        
        for destino in [sender_lid, chatid]:
            if not destino:
                continue
            try:
                # Formato correto da API Uazapi para presença
                # Mapear presence_type para o formato da Uazapi
                uazapi_presence = 'composing' if presence_type == 'typing' else presence_type
                
                payload = {
                    'number': destino,
                    'presence': uazapi_presence,  # composing, recording, paused
                    'delay': 2000  # 2 segundos de duração
                }
                response = requests.post(
                    uazapi_url,
                    headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    send_result = response.json() if response.content else response.status_code
                    success = True
                    break
            except Exception as e:
                continue
        
        if success:
            return True, f"Presença enviada com sucesso: {send_result}"
        else:
            return False, f"Erro na Uazapi: Falha ao enviar presença para todos os destinos"
            
    except Exception as e:
        return False, f"Erro ao enviar presença via Uazapi: {str(e)}"


class MessagePagination(PageNumberPagination):
    """Paginação customizada para mensagens - permite até 10000 mensagens por página"""
    page_size = 1000
    page_size_query_param = 'page_size'
    max_page_size = 10000


class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = MessagePagination
    
    def get_queryset(self):
        user = self.request.user
        
        # Filtrar por conversa específica se fornecido
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id and conversation_id.lower() not in ('null', 'none', ''):
            try:
                conversation_id_int = int(conversation_id)
                queryset = Message.objects.filter(conversation_id=conversation_id_int).prefetch_related('reactions')
                try:
                    conv = Conversation.objects.get(pk=conversation_id_int)
                    queryset = apply_agent_message_visibility_filter(queryset, conv, self.request)
                except Conversation.DoesNotExist:
                    pass
            except (ValueError, TypeError):
                # Se não for um número válido, ignorar o filtro e construir queryset padrão
                queryset = None
        else:
            queryset = None
        
        # Se queryset não foi definido (None), construir queryset padrão baseado no tipo de usuário
        if queryset is None:
            # Superadmin vê todas as mensagens
            if user.user_type == 'superadmin':
                queryset = Message.objects.all().prefetch_related('reactions')
            
            # Admin vê todas as mensagens do seu provedor
            elif user.user_type == 'admin':
                provedores = Provedor.objects.filter(admins=user)
                if provedores.exists():
                    queryset = Message.objects.filter(conversation__inbox__provedor__in=provedores).prefetch_related('reactions')
                else:
                    queryset = Message.objects.none()
            
            # Agent (atendente) - implementar permissões baseadas em equipes e permissões específicas
            else:
                # Buscar equipes do usuário
                user_teams = TeamMember.objects.filter(user=user).values_list('team_id', flat=True)
                
                if not user_teams.exists():
                    # Se não está em nenhuma equipe, só vê mensagens de conversas atribuídas a ele
                    queryset = Message.objects.filter(conversation__assignee=user).prefetch_related('reactions')
                else:
                    # Buscar provedores das equipes do usuário
                    provedores_equipes = Team.objects.filter(id__in=user_teams).values_list('provedor_id', flat=True)
                    
                    # Verificar permissões específicas do usuário
                    user_permissions = getattr(user, 'permissions', [])
                    
                    # Base: mensagens de conversas do provedor das equipes do usuário
                    base_queryset = Message.objects.filter(conversation__inbox__provedor_id__in=provedores_equipes).prefetch_related('reactions')
                    
                    # Filtrar baseado nas permissões
                    if 'view_ai_conversations' in user_permissions or 'view_chatbot_conversations' in user_permissions:
                        # Pode ver mensagens de conversas com IA
                        ai_messages = base_queryset.filter(
                            conversation__status='snoozed'
                        )
                    else:
                        ai_messages = Message.objects.none()
                    
                    if 'view_assigned_conversations' in user_permissions:
                        # Pode ver mensagens de conversas atribuídas a ele
                        assigned_messages = base_queryset.filter(conversation__assignee=user)
                    else:
                        assigned_messages = Message.objects.none()
                    
                    if 'view_team_unassigned' in user_permissions:
                        # Pode ver mensagens de conversas não atribuídas da equipe dele
                        team_unassigned_messages = base_queryset.filter(conversation__assignee__isnull=True)
                    else:
                        team_unassigned_messages = Message.objects.none()
                    
                    # Combinar todos os querysets permitidos
                    queryset = ai_messages | assigned_messages | team_unassigned_messages
                    
                    # Se não tem nenhuma permissão específica, só vê mensagens de conversas atribuídas a ele
                    if not user_permissions:
                        queryset = base_queryset.filter(conversation__assignee=user)
        
        # Ordenar por data de criação (mais antigas primeiro) e garantir que reactions está incluído
        if queryset is not None and not hasattr(queryset, '_prefetch_related_lookups'):
            queryset = queryset.prefetch_related('reactions')
        return queryset.order_by('created_at') if queryset is not None else Message.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(is_from_customer=False)

    def _format_message_with_agent_name(self, content: str, user, channel_type: str) -> str:
        """
        Formata a mensagem com o nome do agente no formato correto para cada canal.
        
        Para Telegram: Nome completo em negrito (**texto**)
        Para WhatsApp: Nome completo em negrito (*texto*)
        
        Formato:
        Nome Completo
        
        Mensagem aqui
        
        Remove formatações antigas como "*Nome disse:*" antes de aplicar a nova formatação.
        """
        import re
        
        # Obter nome completo do agente primeiro (necessário para remover formatações antigas)
        agent_name = user.get_full_name() if user else ""
        if not agent_name:
            agent_name = user.username if user else "Atendente"
        
        # Remover formatações antigas do tipo "*Nome disse:*" ou "**Nome disse:**"
        # Padrões: *texto disse:* ou **texto disse:** ou *texto disse: ou **texto disse:
        # Remove também linhas vazias que possam estar antes ou depois
        content = re.sub(r'^\s*\*{1,2}.*?disse:\*{0,2}\s*\n*', '', content, flags=re.IGNORECASE | re.MULTILINE)
        content = content.strip()
        
        # Se o conteúdo ainda começar com o nome do agente (caso o frontend tenha adicionado), remover também
        if agent_name:
            # Remover linha que começa apenas com o nome (sem formatação de negrito)
            # Pode estar em uma linha separada seguida de linha vazia
            content = re.sub(rf'^\s*{re.escape(agent_name)}\s*\n+', '', content, flags=re.IGNORECASE | re.MULTILINE)
            content = content.strip()
        
        # Formatar nome com negrito conforme o canal
        if channel_type == 'app_mobile':
            # App mostra o nome do atendente na UI — não embutir assinatura no texto.
            return content
        if channel_type == 'telegram':
            # Telegram usa **texto** para negrito
            formatted_name = f"**{agent_name}**"
        elif channel_type == 'instagram':
            formatted_name = agent_name
        else:
            # WhatsApp usa *texto* para negrito
            formatted_name = f"*{agent_name}*"
        
        if channel_type == 'instagram':
            return f"{formatted_name}\n{content}"
        return f"{formatted_name}\n\n{content}"

    def _reject_reply_without_human_assignee(self, user, conversation):
        """Automação/espera sem atendente, ou supervisão (admin vendo conversa de outro agente)."""
        if getattr(user, 'user_type', None) == 'superadmin':
            return None
        if not conversation.assignee_id:
            return Response(
                {
                    'error': 'Atribua a conversa para enviar mensagens.',
                    'code': 'assignment_required',
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if conversation.assignee_id != user.id:
            if getattr(user, 'user_type', None) == 'admin':
                provedor = conversation.inbox.provedor if conversation.inbox_id else None
                if provedor and user.provedores_admin.filter(id=provedor.id).exists():
                    return Response(
                        {
                            'error': 'Modo supervisão: apenas visualização. O atendimento pertence a outro agente.',
                            'code': 'supervisor_readonly',
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            return Response(
                {
                    'error': 'Sem permissão para enviar mensagens nesta conversa.',
                    'code': 'not_assignee',
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    @action(detail=False, methods=['post'])
    def send_text(self, request):
        """Enviar mensagem de texto"""
        logger.info("[DEBUG] Daphne auto-reload test - send_text called")
        import logging
        # logger = logging.getLogger(__name__)
        
        conversation_id = request.data.get('conversation_id')
        content = request.data.get('content')
        reply_to_message_id = request.data.get('reply_to_message_id')
        reply_to_content = request.data.get('reply_to_content')
        
        logger.info(f"[SEND_TEXT] Iniciando envio de mensagem: conversation_id={conversation_id}, content_length={len(content) if content else 0}")
        
        if not conversation_id or not content:
            logger.warning(f"[SEND_TEXT] Parâmetros inválidos: conversation_id={conversation_id}, content={bool(content)}")
            return Response({'error': 'conversation_id e content são obrigatórios'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            logger.info(f"[SEND_TEXT] Conversa encontrada: id={conversation.id}, inbox_id={conversation.inbox_id if conversation.inbox else None}")

            blocked = self._reject_reply_without_human_assignee(request.user, conversation)
            if blocked is not None:
                return blocked
            
            # Verificar o tipo de canal
            channel_type = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
            
            # Obter usuário que está enviando (atendente)
            user = request.user
            
            # Formatar mensagem com nome do agente
            formatted_content = self._format_message_with_agent_name(content, user, channel_type)
            agent_name = (user.get_full_name() or '').strip() or (user.username if user else '') or 'Atendente'
            
            # Preparar additional_attributes
            additional_attrs = {
                'agent_name': agent_name,
                'sent_by': user.id if user else None,
            }
            if reply_to_message_id:
                additional_attrs['reply_to_message_id'] = reply_to_message_id
                additional_attrs['reply_to_content'] = reply_to_content
                additional_attrs['is_reply'] = True
            
            # Salvar mensagem no banco (salvar o conteúdo original, não o formatado)
            message = Message.objects.create(
                conversation=conversation,
                content=content,  # Salvar conteúdo original
                message_type='text',
                is_from_customer=False,
                additional_attributes=additional_attrs
            )
            logger.info(f"[SEND_TEXT] Mensagem salva no banco: id={message.id}")
            
            # NÃO enviar para Supabase aqui - só vai para Supabase quando a conversa for encerrada
            
            logger.info(f"[SEND_TEXT] Channel type detectado: {channel_type}, inbox={conversation.inbox.id if conversation.inbox else None}")
            
            if channel_type == 'telegram':
                # Enviar para o Telegram (usar conteúdo formatado)
                logger.info(f"[SEND_TEXT] Enviando para Telegram...")
                success, telegram_response = self._send_telegram_message(conversation, formatted_content, reply_to_message_id)
                logger.info(f"[SEND_TEXT] Resultado Telegram: success={success}, response={telegram_response}")
            elif channel_type in ['whatsapp', 'whatsapp_oficial']:
                # Obter canal específico vinculado ao inbox
                canal_oficial = conversation.inbox.get_canal_instance()
                
                if canal_oficial and canal_oficial.token and canal_oficial.phone_number_id:
                    # Verificar se a janela de 24 horas está aberta para WhatsApp Official
                    if not conversation.is_24h_window_open():
                        error_message = translate_whatsapp_error(131047)
                        logger.warning(f"[SEND_TEXT] Janela de 24 horas fechada para conversa {conversation.id}")
                        
                        # Salvar mensagem com erro
                        additional_attrs = message.additional_attributes or {}
                        additional_attrs['sent_success'] = False
                        additional_attrs['channel_type'] = channel_type
                        additional_attrs['error_message'] = error_message
                        additional_attrs['error_code'] = 131047
                        additional_attrs['delivery_error_code'] = 131047
                        additional_attrs['delivery_error_message'] = error_message
                        message.additional_attributes = additional_attrs
                        message.save(update_fields=['additional_attributes'])
                        
                        # Retornar erro para o frontend
                        response_data = MessageSerializer(message).data
                        response_data['sent_success'] = False
                        response_data['channel_type'] = channel_type
                        response_data['whatsapp_sent'] = False
                        response_data['error_message'] = error_message
                        response_data['error_code'] = 131047
                        
                        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Enviar via WhatsApp Cloud API (Oficial)
                    logger.info(f"[SEND_TEXT] Janela de 24 horas está aberta, enviando via WhatsApp Cloud API (Oficial)...")
                    from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api, send_reaction, translate_whatsapp_error
                    
                    # Para WhatsApp Official, precisamos usar o external_id (wamid) da mensagem original
                    whatsapp_reply_id = None
                    if reply_to_message_id:
                        try:
                            # Se já for um wamid (string começando com "wamid."), usar diretamente
                            if isinstance(reply_to_message_id, str) and reply_to_message_id.startswith('wamid.'):
                                whatsapp_reply_id = reply_to_message_id
                                logger.info(f"[SEND_TEXT] Usando wamid diretamente para reply: {whatsapp_reply_id}")
                            else:
                                # Se for um ID numérico, buscar a mensagem original para obter o external_id (wamid)
                                try:
                                    reply_id_int = int(reply_to_message_id)
                                    original_message = Message.objects.filter(
                                        id=reply_id_int,
                                        conversation=conversation
                                    ).first()
                                    if original_message and original_message.external_id:
                                        whatsapp_reply_id = original_message.external_id
                                        logger.info(f"[SEND_TEXT] Usando external_id para reply: {whatsapp_reply_id}")
                                    else:
                                        logger.warning(f"[SEND_TEXT] Mensagem original não encontrada ou sem external_id: {reply_to_message_id}")
                                except (ValueError, TypeError):
                                    # Se não for um número válido, tentar usar como string (pode ser um wamid)
                                    whatsapp_reply_id = str(reply_to_message_id)
                                    logger.info(f"[SEND_TEXT] Usando reply_to_message_id como string para reply: {whatsapp_reply_id}")
                        except Exception as e:
                            logger.error(f"[SEND_TEXT] Erro ao buscar mensagem original para reply: {str(e)}")
                    
                    success, whatsapp_response = send_via_whatsapp_cloud_api(
                        conversation,
                        formatted_content,
                        'text',
                        None,
                        None,  # file_path
                        None,  # file_name
                        None,  # mime_type
                        None,  # is_voice_message
                        whatsapp_reply_id  # reply_to_message_id (external_id/wamid)
                    )
                    logger.info(f"[SEND_TEXT] Resultado WhatsApp Oficial: success={success}")
                elif channel_type == 'whatsapp':
                    # Fallback para Uazapi apenas se o canal for explicitamente 'whatsapp' (não oficial)
                    logger.info(f"[SEND_TEXT] Enviando via Uazapi (WhatsApp não oficial)...")
                    success, whatsapp_response = send_via_uazapi(conversation, formatted_content, 'text', None, reply_to_message_id)
                else:
                    logger.warning(f"[SEND_TEXT] Canal {channel_type} configurado mas sem método de envio adequado.")
                    success = False
                    whatsapp_response = "Canal não suportado ou não configurado adequadamente."
            elif channel_type == 'instagram':
                from integrations.instagram_send import send_instagram_text

                contact = conversation.contact
                canal_instagram = conversation.inbox.get_canal_instance()
                recipient_id = (contact.additional_attributes or {}).get('instagram_scoped_id') or contact.phone

                instagram_reply_mid = None
                if reply_to_message_id:
                    try:
                        if isinstance(reply_to_message_id, str) and not reply_to_message_id.isdigit():
                            instagram_reply_mid = reply_to_message_id
                            logger.info('[SEND_TEXT] Usando mid Instagram diretamente para reply: %s', instagram_reply_mid)
                        else:
                            reply_id_int = int(reply_to_message_id)
                            original_message = Message.objects.filter(
                                id=reply_id_int,
                                conversation=conversation,
                            ).first()
                            if original_message:
                                instagram_reply_mid = original_message.external_id
                                if not instagram_reply_mid:
                                    orig_attrs = original_message.additional_attributes or {}
                                    for resp_key in ('instagram_response', 'whatsapp_response'):
                                        resp = orig_attrs.get(resp_key)
                                        if isinstance(resp, dict) and resp.get('message_id'):
                                            instagram_reply_mid = str(resp['message_id'])
                                            original_message.external_id = instagram_reply_mid
                                            original_message.save(update_fields=['external_id'])
                                            break
                                if instagram_reply_mid:
                                    logger.info('[SEND_TEXT] Usando external_id Instagram para reply: %s', instagram_reply_mid)
                                else:
                                    logger.warning(
                                        '[SEND_TEXT] Mensagem original não encontrada ou sem external_id: %s',
                                        reply_to_message_id,
                                    )
                            else:
                                logger.warning(
                                    '[SEND_TEXT] Mensagem original não encontrada ou sem external_id: %s',
                                    reply_to_message_id,
                                )
                    except (ValueError, TypeError):
                        instagram_reply_mid = str(reply_to_message_id)
                        logger.info('[SEND_TEXT] Usando reply_to_message_id como mid Instagram: %s', instagram_reply_mid)
                    except Exception as e:
                        logger.error('[SEND_TEXT] Erro ao buscar mensagem original para reply Instagram: %s', e)

                if canal_instagram and canal_instagram.token and recipient_id:
                    success, ig_response, ig_error = send_instagram_text(
                        canal_instagram,
                        str(recipient_id),
                        formatted_content,
                        reply_to_mid=instagram_reply_mid,
                    )
                    whatsapp_response = ig_response
                    if not success:
                        logger.warning('[SEND_TEXT] Falha Instagram: %s', ig_error)
                else:
                    logger.warning('[SEND_TEXT] Canal Instagram não configurado ou contato sem IGSID')
                    success = False
                    whatsapp_response = 'Canal Instagram não configurado'
            elif channel_type == 'app_mobile':
                from conversations.app_mobile import send_app_mobile_outbound

                logger.info('[SEND_TEXT] Enviando para o aplicativo...')
                success, whatsapp_response = send_app_mobile_outbound(
                    conversation, formatted_content, 'text'
                )
            else:
                # Se não for telegram nem whatsapp, falhar silenciosamente ou logar
                logger.warning(f"[SEND_TEXT] Tipo de canal desconhecido: {channel_type}")
                success = False
            
            # Se o envio foi bem-sucedido, atualizar a mensagem
            if success:
                additional_attrs = message.additional_attributes or {}
                additional_attrs['sent_success'] = True
                additional_attrs['channel_type'] = channel_type
                
                # Definir status inicial como "sent" quando mensagem é enviada com sucesso
                # Isso garante que o ticket apareça imediatamente no frontend
                additional_attrs['last_status'] = 'sent'
                additional_attrs['sent_at'] = timezone.now().isoformat()
                
                if channel_type == 'telegram':
                    additional_attrs['telegram_sent'] = True
                elif channel_type == 'app_mobile':
                    additional_attrs['app_mobile_sent'] = True
                    if isinstance(whatsapp_response, dict) and whatsapp_response.get('file_url'):
                        additional_attrs['app_file_url'] = whatsapp_response['file_url']
                elif channel_type == 'instagram' and 'whatsapp_response' in locals() and isinstance(whatsapp_response, dict):
                    ig_mid = whatsapp_response.get('message_id')
                    if ig_mid:
                        message.external_id = str(ig_mid)
                        additional_attrs['external_id'] = str(ig_mid)
                    additional_attrs['instagram_sent'] = True
                    additional_attrs['instagram_response'] = whatsapp_response
                elif channel_type in ('whatsapp', 'whatsapp_oficial') and 'whatsapp_response' in locals() and whatsapp_response:
                    try:
                        import json
                        import re
                        
                        # Tentar extrair o ID da resposta do WhatsApp
                        # Pode ser string JSON ou dict
                        response_data = whatsapp_response
                        if isinstance(whatsapp_response, str):
                            try:
                                response_data = json.loads(whatsapp_response)
                            except:
                                # Se não for JSON válido, tentar regex
                                pass
                        
                        # Tentar extrair message_id de diferentes formatos
                        message_id = None
                        
                        # Formato WhatsApp Cloud API: {"messages": [{"id": "wamid.xxx"}]}
                        if isinstance(response_data, dict):
                            messages = response_data.get("messages", [])
                            if messages and isinstance(messages, list) and len(messages) > 0:
                                message_id = messages[0].get("id")
                        
                        # Se não encontrou no formato dict, tentar regex
                        if not message_id and isinstance(whatsapp_response, str):
                            id_patterns = [
                                r'"id":\s*"([^"]+)"',
                                r"'id':\s*'([^']+)'",
                                r'id["\']?\s*:\s*["\']([^"\']+)["\']',
                                r'messageid["\']?\s*:\s*["\']([^"\']+)["\']',
                                r'wamid\.[A-Za-z0-9_-]+'  # Formato wamid do WhatsApp Cloud API
                            ]
                            
                            for pattern in id_patterns:
                                match = re.search(pattern, whatsapp_response)
                                if match:
                                    message_id = match.group(1) if match.groups() else match.group(0)
                                    break
                        
                        if message_id:
                            additional_attrs['external_id'] = message_id
                            # IMPORTANTE: Salvar também no campo external_id para facilitar busca de status
                            message.external_id = message_id
                        
                        additional_attrs['whatsapp_sent'] = True
                        additional_attrs['whatsapp_response'] = whatsapp_response
                    except Exception as e:
                        logger.warning(f"[SEND_TEXT] Erro ao extrair external_id: {str(e)}")
                        pass
                
                message.additional_attributes = additional_attrs
                # Salvar external_id e additional_attributes juntos
                message.save(update_fields=['external_id', 'additional_attributes'])
            else:
                # Envio falhou - marcar na mensagem e salvar mensagem de erro
                additional_attrs = message.additional_attributes or {}
                additional_attrs['sent_success'] = False
                additional_attrs['channel_type'] = channel_type
                
                # Salvar mensagem de erro se disponível
                error_message = None
                error_code = None
                if channel_type == 'telegram':
                    if 'telegram_response' in locals() and telegram_response:
                        error_message = str(telegram_response)
                else:
                    if 'whatsapp_response' in locals() and whatsapp_response:
                        # Tentar extrair erro do formato JSON retornado pela função
                        try:
                            import json
                            if isinstance(whatsapp_response, str):
                                try:
                                    error_data = json.loads(whatsapp_response)
                                    if isinstance(error_data, dict):
                                        error_message = error_data.get('error_message', str(whatsapp_response))
                                        error_code = error_data.get('error_code')
                                except:
                                    # Se não for JSON válido, usar a string diretamente
                                    error_message = str(whatsapp_response)
                            else:
                                error_message = str(whatsapp_response)
                        except:
                            error_message = str(whatsapp_response)
                
                if error_message:
                    additional_attrs['error_message'] = error_message
                    if error_code:
                        additional_attrs['error_code'] = error_code
                        # Salvar também como delivery_error_code para consistência com webhooks
                        additional_attrs['delivery_error_code'] = error_code
                        additional_attrs['delivery_error_message'] = error_message
                
                message.additional_attributes = additional_attrs
                message.save(update_fields=['additional_attributes'])
            
            # Atualizar mensagem do banco antes de retornar
            message.refresh_from_db()
            
            # A notificação agora é feita via signal (post_save no modelo Message)
            # para garantir que a ordenação mude em tempo real no dashboard
            # e a mensagem apareça no chat area.
            logger.info(f"[SEND_TEXT] Mensagem {message.id} processada com sucesso. Notificação via signal disparada.")
            
            response_data = MessageSerializer(message).data
            response_data['sent_success'] = success
            response_data['channel_type'] = channel_type
            
            if channel_type == 'telegram':
                response_data['telegram_sent'] = success
                if not success and 'telegram_response' in locals() and telegram_response:
                    response_data['error_message'] = str(telegram_response)
            else:
                response_data['whatsapp_sent'] = success
                if 'whatsapp_response' in locals():
                    response_data['whatsapp_response'] = whatsapp_response
                    # Incluir mensagem de erro na resposta se o envio falhou
                    if not success and whatsapp_response:
                        # Tentar extrair erro do formato JSON retornado pela função
                        try:
                            import json
                            if isinstance(whatsapp_response, str):
                                try:
                                    error_data = json.loads(whatsapp_response)
                                    if isinstance(error_data, dict):
                                        response_data['error_message'] = error_data.get('error_message', str(whatsapp_response))
                                        error_code = error_data.get('error_code')
                                        if error_code:
                                            response_data['error_code'] = error_code
                                    else:
                                        response_data['error_message'] = str(whatsapp_response)
                                except:
                                    # Se não for JSON válido, usar a string diretamente
                                    response_data['error_message'] = str(whatsapp_response)
                            else:
                                response_data['error_message'] = str(whatsapp_response)
                        except:
                            response_data['error_message'] = str(whatsapp_response)
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def send_interactive(self, request):
        """
        Enviar mensagem interativa com botões (WhatsApp Oficial)
        Payload esperado: { "conversation_id": 123, "content": "Texto", "buttons": [{"id": "btn1", "title": "Botão 1"}] }
        """
        conversation_id = request.data.get('conversation_id')
        content = request.data.get('content')
        buttons = request.data.get('buttons', [])
        header = request.data.get('header')
        footer = request.data.get('footer')
        message_type = request.data.get('message_type', 'interactive')
        order_details = request.data.get('order_details')
        
        logger.info(f"[SEND_INTERACTIVE] Iniciando: conversation_id={conversation_id}, type={message_type}")
        
        if not conversation_id or not content:
            return Response({'error': 'conversation_id e content são obrigatórios'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            conversation = Conversation.objects.get(id=conversation_id)

            blocked = self._reject_reply_without_human_assignee(request.user, conversation)
            if blocked is not None:
                return blocked

            channel_type = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
            user = request.user
            
            # Formatar conteúdo com nome do agente (exceto para pagamentos profissionais)
            if message_type != 'order_details':
                formatted_content = self._format_message_with_agent_name(content, user, channel_type)
            else:
                formatted_content = content
            
            # Salvar mensagem no banco
            message = Message.objects.create(
                conversation=conversation,
                content=content,
                message_type=message_type,
                is_from_customer=False,
                additional_attributes={
                    'buttons': buttons, 
                    'header': header, 
                    'footer': footer, 
                    'order_details': order_details,
                    'sent_success': False
                }
            )
            
            if channel_type in ['whatsapp', 'whatsapp_oficial']:
                canal_oficial = conversation.inbox.get_canal_instance()
                
                if canal_oficial and canal_oficial.token and canal_oficial.phone_number_id:
                    # Verificar janela de 24h
                    if not conversation.is_24h_window_open():
                        return Response({'error': 'Janela de 24 horas fechada. Use um template.'}, status=status.HTTP_400_BAD_REQUEST)
                        
                    from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api
                    success, whatsapp_response = send_via_whatsapp_cloud_api(
                        conversation,
                        formatted_content,
                        message_type, # Pode ser 'interactive' ou 'order_details'
                        buttons=buttons,
                        header=header,
                        footer=footer,
                        order_details=order_details
                    )
                    
                    if success:
                        import json
                        attrs = message.additional_attributes or {}
                        attrs.update({'sent_success': True, 'whatsapp_sent': True, 'last_status': 'sent'})
                        
                        try:
                            resp_data = json.loads(whatsapp_response)
                            msg_id = resp_data.get('messages', [{}])[0].get('id')
                            if msg_id:
                                message.external_id = msg_id
                        except: pass
                        
                        message.additional_attributes = attrs
                        message.save()
                        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
                    else:
                        return Response({'error': f'Falha no envio: {whatsapp_response}'}, status=status.HTTP_400_BAD_REQUEST)
                        
            return Response({'error': 'Canal não suporta mensagens interativas.'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[SEND_INTERACTIVE] Erro: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _send_telegram_message(self, conversation, content, reply_to_message_id=None):
        """
        Envia mensagem de AGENTE HUMANO para o Telegram via MTProto
        
        IMPORTANTE:
        - NÃO chama IA
        - NÃO altera status da conversa
        - Apenas envia a mensagem via Telethon (MTProto)
        
        Args:
            conversation: Objeto Conversation
            content: Conteúdo da mensagem
            reply_to_message_id: ID da mensagem a responder (opcional)
            
        Returns:
            tuple: (success: bool, response: str)
        """
        import logging
        # logger = logging.getLogger(__name__)
        logger.info(f"[_SEND_TELEGRAM] Iniciando envio Telegram: conversation_id={conversation.id}, content_length={len(content)}")
        
        try:
            from integrations.telegram_service import telegram_manager
            import asyncio
            
            # Obter o chat_id do contato ou da última mensagem recebida
            # Em chats privados, chat_id = user_id, mas é melhor usar o chat_id da mensagem
            contact = conversation.contact
            logger.info(f"[_SEND_TELEGRAM] Contato: id={contact.id}, phone={contact.phone}, additional_attrs_keys={list(contact.additional_attributes.keys()) if contact.additional_attributes else []}")
            
            # Primeiro tentar pegar o chat_id da última mensagem recebida (mais confiável)
            # from conversations.models import Message
            last_message = Message.objects.filter(
                conversation=conversation,
                is_from_customer=True
            ).order_by('-created_at').first()
            
            chat_id = None
            if last_message and last_message.additional_attributes:
                chat_id = last_message.additional_attributes.get('telegram_chat_id')
            
            # Fallback: usar do contato
            if not chat_id:
                chat_id = (
                    contact.additional_attributes.get('telegram_chat_id') or
                    contact.additional_attributes.get('telegram_user_id')
                )
            
            if not chat_id:
                return False, "Contato não possui telegram_chat_id ou telegram_user_id"
            
            # Converter para int
            try:
                chat_id = int(chat_id)
            except (ValueError, TypeError):
                return False, f"chat_id inválido: {chat_id}"
            
            # Obter o canal do Telegram associado ao inbox
            from core.models import Canal
            canal = Canal.objects.filter(
                provedor=conversation.inbox.provedor,
                tipo='telegram',
                ativo=True
            ).first()
            
            logger.info(f"[_SEND_TELEGRAM] chat_id obtido: {chat_id}")
            
            if not canal:
                logger.error(f"[_SEND_TELEGRAM] Nenhum canal Telegram ativo encontrado para provedor {conversation.inbox.provedor.id}")
                return False, "Nenhum canal Telegram ativo encontrado"
            
            logger.info(f"[_SEND_TELEGRAM] Canal encontrado: id={canal.id}, nome={getattr(canal, 'nome', 'N/A')}")
            
            # Criar/obter event loop único para toda a operação
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Obter ou iniciar o serviço do Telegram
            service = telegram_manager.get_service(canal.id)
            logger.info(f"[_SEND_TELEGRAM] Serviço obtido do manager: {service is not None}, canal_id={canal.id}")
            
            # Se o serviço existe mas o cliente não está conectado, tentar reconectar
            if service and service.client:
                try:
                    is_connected = service.client.is_connected()
                    logger.info(f"[_SEND_TELEGRAM] Serviço existente - cliente conectado: {is_connected}")
                    if not is_connected:
                        logger.warning("[_SEND_TELEGRAM] Serviço existe mas cliente desconectado, reconectando...")
                        loop.run_until_complete(service.client.connect())
                except Exception as check_error:
                    logger.warning(f"[_SEND_TELEGRAM] Erro ao verificar conexão do serviço existente: {check_error}, recriando...")
                    service = None
            
            if not service:
                logger.warning(f"[_SEND_TELEGRAM] Serviço não encontrado ou inválido, criando novo serviço...")
                # Criar um novo serviço Telegram diretamente (não precisa iniciar o listener completo)
                from integrations.telegram_service import TelegramService
                service = TelegramService(canal)
                try:
                    logger.info(f"[_SEND_TELEGRAM] Inicializando cliente Telegram...")
                    initialized = loop.run_until_complete(service.initialize_client())
                    if initialized:
                        # Armazenar o serviço no manager para reutilização
                        telegram_manager.services[canal.id] = service
                        logger.info(f"[_SEND_TELEGRAM] Serviço criado e inicializado: cliente={service.client is not None}, conectado={service.client.is_connected() if service.client else False}")
                    else:
                        logger.error(f"[_SEND_TELEGRAM] Falha ao inicializar cliente Telegram")
                        return False, "Falha ao inicializar cliente Telegram"
                except Exception as init_error:
                    logger.error(f"[_SEND_TELEGRAM] Erro ao inicializar serviço: {init_error}", exc_info=True)
                    return False, f"Erro ao inicializar serviço: {str(init_error)}"
            
            if not service:
                logger.error(f"[_SEND_TELEGRAM] Não foi possível criar o serviço Telegram")
                return False, "Não foi possível criar o serviço Telegram"
            
            # Enviar a mensagem usando send_message com chat_id (funciona para chats privados)
            # O método send_message já trata automaticamente o problema de event loops diferentes
            logger.info(f"[_SEND_TELEGRAM] Tentando enviar mensagem Telegram: chat_id={chat_id}, canal_id={canal.id}, content_length={len(content)}")
            
            try:
                # Verificar se o cliente foi criado em outro loop que está rodando
                client_loop = getattr(service, '_client_loop', None)
                current_loop = None
                try:
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
                
                # Se o cliente foi criado em outro loop que está rodando, usar run_coroutine_threadsafe
                if client_loop and current_loop and client_loop != current_loop and client_loop.is_running():
                    logger.info(f"[_SEND_TELEGRAM] Cliente em outro loop ({client_loop}), usando run_coroutine_threadsafe...")
                    future = asyncio.run_coroutine_threadsafe(
                        service.send_message(chat_id, content, reply_to_message_id),
                        client_loop
                    )
                    success = future.result(timeout=30)
                else:
                    # Usar o loop atual normalmente (send_message vai tratar internamente se necessário)
                    logger.info(f"[_SEND_TELEGRAM] Usando loop atual para envio...")
                    success = loop.run_until_complete(
                        service.send_message(chat_id, content, reply_to_message_id)
                    )
                
                if success:
                    logger.info(f"[_SEND_TELEGRAM] Mensagem Telegram enviada com sucesso para chat_id={chat_id}")
                else:
                    logger.error(f"[_SEND_TELEGRAM] Falha ao enviar mensagem Telegram para chat_id={chat_id}")
                
                return success, "Mensagem enviada com sucesso" if success else "Falha ao enviar"
            except Exception as send_error:
                logger.error(f"[_SEND_TELEGRAM] Erro ao enviar mensagem Telegram: {send_error}", exc_info=True)
                return False, f"Erro ao enviar: {str(send_error)}"
                
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.error(f"Erro ao enviar mensagem humana para Telegram: {e}", exc_info=True)
            return False, str(e)

    def _send_telegram_media(self, conversation, file_path, media_type, caption=""):
        """
        Envia mídia de AGENTE HUMANO para o Telegram via MTProto
        
        IMPORTANTE:
        - NÃO chama IA
        - NÃO altera status da conversa
        - Apenas envia o arquivo via Telethon (MTProto)
        
        Args:
            conversation: Objeto Conversation
            file_path: Caminho local do arquivo
            media_type: Tipo de mídia
            caption: Legenda opcional
            
        Returns:
            tuple: (success: bool, response: str)
        """
        try:
            from integrations.telegram_service import telegram_manager
            import asyncio
            
            # Obter o telegram_user_id do contato
            contact = conversation.contact
            telegram_user_id = (
                contact.additional_attributes.get('telegram_user_id') or 
                contact.additional_attributes.get('telegram_chat_id')
            )
            
            if not telegram_user_id:
                return False, "Contato não possui telegram_user_id"
            
            # Converter para int
            try:
                telegram_user_id = int(telegram_user_id)
            except (ValueError, TypeError):
                return False, f"telegram_user_id inválido: {telegram_user_id}"
            
            # Obter o canal do Telegram associado ao inbox
            from core.models import Canal
            canal = Canal.objects.filter(
                provedor=conversation.inbox.provedor,
                tipo='telegram',
                ativo=True
            ).first()
            
            if not canal:
                return False, "Nenhum canal Telegram ativo encontrado"
            
            # Obter ou iniciar o serviço do Telegram
            service = telegram_manager.get_service(canal.id)
            
            if not service:
                # Tentar iniciar o serviço
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(telegram_manager.start_integration(canal.id))
                    service = telegram_manager.get_service(canal.id)
                finally:
                    loop.close()
            
            if not service:
                return False, "Não foi possível iniciar o serviço Telegram"
            
            # Enviar o arquivo usando send_human_media (SEM IA, SEM alterar status)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(
                    service.send_human_media(telegram_user_id, file_path, caption)
                )
                return success, "Mídia enviada com sucesso" if success else "Falha ao enviar mídia"
            finally:
                loop.close()
                
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.error(f"Erro ao enviar mídia para Telegram: {e}", exc_info=True)
            return False, str(e)

    @action(detail=False, methods=['post'])
    def send_media(self, request):
        """Enviar mídia (imagem, vídeo, documento, áudio)"""
        conversation_id = request.data.get('conversation_id')
        media_type = request.data.get('media_type')  # image, video, document, audio, myaudio, ptt, sticker
        file = request.FILES.get('file')
        caption = request.data.get('caption', '')
        reply_to_message_id = request.data.get('reply_to_message_id')
        
        if not conversation_id or not media_type or not file:
            return Response({'error': 'conversation_id, media_type e file são obrigatórios'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)

            blocked = self._reject_reply_without_human_assignee(request.user, conversation)
            if blocked is not None:
                return blocked

            channel_type = conversation.inbox.channel_type if conversation.inbox else 'whatsapp'
            
            # Criar diretório se não existir
            import os
            from django.conf import settings
            media_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conversation_id))
            os.makedirs(media_dir, exist_ok=True)

            # Validação do tipo de arquivo
            import mimetypes
            
            # Tentar usar python-magic se disponível, senão usar mimetypes padrão
            try:
                import magic
                # Ler os primeiros 2048 bytes para validação
                file_content = file.read(2048)
                file.seek(0)  # Voltar ao início do arquivo
                mime = magic.from_buffer(file_content, mime=True)
            except (ImportError, ModuleNotFoundError):
                # Fallback: usar mimetypes baseado na extensão do arquivo
                mime, _ = mimetypes.guess_type(file.name)
                if not mime:
                    # Se não conseguir detectar, usar extensão como fallback
                    ext = os.path.splitext(file.name)[1].lower()
                    mime_map = {
                        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.png': 'image/png', '.gif': 'image/gif',
                        '.webp': 'image/webp', '.mp4': 'video/mp4',
                        '.webm': 'video/webm', '.mp3': 'audio/mpeg',
                        '.ogg': 'audio/ogg', '.pdf': 'application/pdf'
                    }
                    mime = mime_map.get(ext, 'application/octet-stream')
            
            # Lista de tipos MIME permitidos
            allowed_mimetypes = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp',
                'video/mp4', 'video/webm',
                'audio/mpeg', 'audio/ogg', 'audio/webm', 'application/pdf'
            ]
            if channel_type == 'instagram':
                allowed_mimetypes = [
                    'image/jpeg', 'image/png',
                    'video/mp4', 'video/ogg', 'video/webm', 'video/quicktime', 'video/x-msvideo',
                    'audio/mpeg', 'audio/mp4', 'audio/x-m4a', 'audio/wav', 'audio/wave', 'audio/x-wav',
                    'audio/aac', 'audio/x-aac',
                    'application/pdf',
                ]
            
            if mime not in allowed_mimetypes:
                if channel_type == 'app_mobile' and (
                    mime.startswith('image/')
                    or mime.startswith('audio/')
                    or mime.startswith('video/')
                    or mime in ('application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                ):
                    pass
                else:
                    return Response({'error': f'Tipo de arquivo não permitido: {mime}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Salvar o arquivo
            file_path = os.path.join(media_dir, file.name)
            with open(file_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
            
            # Para áudios enviados (PTT), manter formato original
            final_filename = file.name
            final_file_path = file_path
            
            # Obter usuário que está enviando (atendente)
            user = request.user
            
            # Formatar caption com nome do agente se houver caption
            formatted_caption = ""
            if caption:
                formatted_caption = self._format_message_with_agent_name(caption, user, channel_type)
            
            # Log do tipo de arquivo recebido
            
            # WhatsApp: normalizar áudio para formato reproduzível no app do cliente
            canal_oficial_check = None
            if conversation.inbox:
                canal_oficial_check = Canal.objects.filter(
                    provedor=conversation.inbox.provedor,
                    tipo="whatsapp_oficial",
                    ativo=True
                ).first()

            if media_type in ('ptt', 'audio', 'myaudio') and channel_type in ('whatsapp', 'whatsapp_oficial'):
                from integrations.whatsapp_media import ensure_whatsapp_audio_format

                file_ext_original = os.path.splitext(final_filename)[1].lower()
                converted_path, converted_name, converted_mime = ensure_whatsapp_audio_format(
                    final_file_path,
                    final_filename,
                    media_dir,
                    media_type,
                )
                if not converted_path or not converted_name:
                    error_msg = (
                        "Não foi possível converter o áudio para um formato compatível com WhatsApp. "
                        "Instale o ffmpeg no servidor ou envie MP3/OGG/M4A."
                    )
                    logger.error('[SEND_MEDIA] %s (ext=%s, type=%s)', error_msg, file_ext_original, media_type)
                    return Response({
                        'error': error_msg,
                        'details': (
                            f'Formato {file_ext_original} não é aceito diretamente pela Meta. '
                            'Gravações do navegador (.webm) e arquivos .wav precisam de conversão.'
                        ),
                    }, status=status.HTTP_400_BAD_REQUEST)
                final_file_path = converted_path
                final_filename = converted_name
                if converted_mime:
                    mime = converted_mime
                logger.info('[SEND_MEDIA] Áudio pronto para WhatsApp: %s (mime=%s)', final_filename, mime)

            # Vídeo WhatsApp Oficial: converter para MP4 (H.264/AAC) se necessário
            elif (
                media_type == 'video'
                and canal_oficial_check
                and channel_type in ('whatsapp', 'whatsapp_oficial')
            ):
                file_ext_original = os.path.splitext(final_filename)[1].lower()

                # Converter vídeo para MP4 (H.264/AAC) se necessário
                if media_type == 'video':
                    # Formatos suportados pela Meta: .mp4 e .3gp (com codec H.264 e AAC)
                    supported_video_formats = ['.mp4', '.3gp']
                    if file_ext_original not in supported_video_formats:
                        # Converter para MP4 com codec H.264 e AAC
                        try:
                            import subprocess
                            import shutil
                            
                            # Verificar se ffmpeg está disponível (mesmo código usado para áudio)
                            ffmpeg_path = shutil.which('ffmpeg')
                            
                            if not ffmpeg_path and os.name == 'nt':
                                ffmpeg_path = shutil.which('ffmpeg.exe')
                            
                            if not ffmpeg_path and os.name == 'nt':
                                common_paths = [
                                    r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
                                    r'C:\ffmpeg\bin\ffmpeg.exe',
                                    r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                                    r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
                                ]
                                for path in common_paths:
                                    if os.path.exists(path):
                                        ffmpeg_path = path
                                        break
                            
                            if not ffmpeg_path and os.name == 'nt':
                                try:
                                    ps_cmd = ['powershell', '-Command', 
                                             'Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source']
                                    ps_result = subprocess.run(
                                        ps_cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        timeout=5,
                                        text=True
                                    )
                                    if ps_result.returncode == 0 and ps_result.stdout.strip():
                                        potential_path = ps_result.stdout.strip()
                                        if os.path.exists(potential_path):
                                            ffmpeg_path = potential_path
                                except Exception:
                                    pass
                            
                            if not ffmpeg_path:
                                try:
                                    test_result = subprocess.run(
                                        ['ffmpeg', '-version'],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        timeout=5
                                    )
                                    if test_result.returncode == 0:
                                        ffmpeg_path = 'ffmpeg'
                                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                                    pass
                            
                            if not ffmpeg_path:
                                error_msg = "ffmpeg não está instalado ou não está no PATH. Para enviar vídeos em formatos não suportados via WhatsApp Oficial, é necessário instalar o ffmpeg no servidor e adicioná-lo ao PATH do sistema."
                                logger.error(f"[SEND_MEDIA] {error_msg}")
                                return Response({
                                    'error': error_msg,
                                    'details': f'O formato {file_ext_original} não é suportado pela Meta WhatsApp Cloud API. Formatos aceitos: MP4, 3GP (com codec H.264 para vídeo e AAC para áudio). É necessário converter usando ffmpeg.'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            logger.info(f"[SEND_MEDIA] ffmpeg encontrado em: {ffmpeg_path}")
                            
                            # Converter para MP4 com codec H.264 (vídeo) e AAC (áudio)
                            output_ext = '.mp4'
                            base_name = os.path.splitext(final_filename)[0]
                            converted_filename = f"{base_name}{output_ext}"
                            converted_file_path = os.path.join(media_dir, converted_filename)
                            
                            logger.info(f"[SEND_MEDIA] Convertendo vídeo {final_filename} para {converted_filename} (formato suportado pela Meta)")
                            
                            # Converter usando ffmpeg para MP4 (H.264/AAC)
                            # -c:v libx264: codec de vídeo H.264
                            # -c:a aac: codec de áudio AAC
                            # -preset medium: balance entre velocidade e qualidade
                            # -crf 23: qualidade (23 é um bom padrão)
                            cmd = [
                                ffmpeg_path, '-i', final_file_path,
                                '-c:v', 'libx264',  # Codec de vídeo H.264
                                '-c:a', 'aac',      # Codec de áudio AAC
                                '-preset', 'medium',
                                '-crf', '23',
                                '-movflags', '+faststart',  # Otimização para streaming
                                '-y',  # Sobrescrever se existir
                                converted_file_path
                            ]
                            
                            # Executar conversão com timeout de 120 segundos (vídeos podem demorar mais)
                            result = subprocess.run(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                timeout=120
                            )
                            
                            if result.returncode == 0 and os.path.exists(converted_file_path):
                                # Usar arquivo convertido
                                final_file_path = converted_file_path
                                final_filename = converted_filename
                                logger.info(f"[SEND_MEDIA] Conversão de vídeo bem-sucedida: {converted_filename}")
                            else:
                                error_msg = result.stderr.decode('utf-8', errors='ignore')
                                logger.error(f"[SEND_MEDIA] Erro ao converter vídeo: {error_msg}")
                                return Response({
                                    'error': 'Erro ao converter vídeo para formato suportado',
                                    'details': error_msg[:500] if error_msg else 'Falha na conversão do arquivo. A Meta requer codec H.264 para vídeo e AAC para áudio.'
                                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                        except subprocess.TimeoutExpired:
                            logger.error(f"[SEND_MEDIA] Timeout ao converter vídeo")
                            return Response({
                                'error': 'Timeout ao converter vídeo',
                                'details': 'A conversão do arquivo demorou mais de 120 segundos'
                            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                        except Exception as e:
                            logger.error(f"[SEND_MEDIA] Erro ao converter vídeo: {str(e)}")
                            return Response({
                                'error': 'Erro ao processar vídeo',
                                'details': str(e)
                            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Instagram: áudio deve ser wav/mp4/aac (m4a é rejeitado pela API — subcode 2534080)
            if channel_type == 'instagram' and media_type in ('ptt', 'audio', 'myaudio'):
                from integrations.instagram_media import convert_audio_for_instagram

                file_ext_ig = os.path.splitext(final_filename)[1].lower()
                if file_ext_ig in ('.m4a', '.ogg', '.webm') or file_ext_ig not in ('.aac', '.wav', '.mp4'):
                    base_name = os.path.splitext(final_filename)[0]
                    converted_path, converted_name = convert_audio_for_instagram(
                        final_file_path, media_dir, base_name
                    )
                    if converted_path and converted_name:
                        final_file_path = converted_path
                        final_filename = converted_name
                        mime = 'audio/mp4'
                    else:
                        return Response({
                            'error': 'Não foi possível converter o áudio para formato Instagram (mp4/aac)',
                            'details': 'Instale ffmpeg no servidor ou envie áudio em wav ou mp4.',
                        }, status=status.HTTP_400_BAD_REQUEST)
            
            # Gerar URL pública para o arquivo
            file_url = f"/api/media/messages/{conversation_id}/{final_filename}/"
            
            # Preparar atributos adicionais
            agent_name = (user.get_full_name() or '').strip() or (user.username if user else '') or 'Atendente'
            additional_attrs = {
                'file_path': final_file_path,
                'file_url': file_url,
                'file_name': final_filename,
                'file_size': os.path.getsize(final_file_path),
                'local_file_url': file_url,  # Adicionar URL local para compatibilidade
                'agent_name': agent_name,
                'sent_by': user.id if user else None,
            }
            
            # Adicionar informações de reply se houver
            if reply_to_message_id:
                additional_attrs['reply_to_message_id'] = reply_to_message_id
                additional_attrs['is_reply'] = True
            
            # Salvar mensagem no banco (sem legenda genérica para PTT/áudio: o player já indica o tipo)
            content_to_save = caption if caption else ""
            
            message = Message.objects.create(
                conversation=conversation,
                content=content_to_save,
                message_type=media_type,
                file_url=file_url,
                additional_attributes=additional_attrs,
                is_from_customer=False
            )
            
            # NÃO enviar para Supabase aqui - só vai para Supabase quando a conversa for encerrada
            
            # Verificar o tipo de canal e enviar para o destino correto
            # channel_type já definido no início do método
            
            if channel_type == 'telegram':
                # Enviar mídia para o Telegram (usar caption formatada se houver)
                caption_to_send = formatted_caption if formatted_caption else caption
                success, response_msg = self._send_telegram_media(conversation, final_file_path, media_type, caption_to_send)
            elif channel_type in ['whatsapp', 'whatsapp_oficial']:
                # Detectar se é WhatsApp Oficial (Cloud) ou Uazapi
                caption_to_send = formatted_caption if formatted_caption else caption
                canal_oficial = Canal.objects.filter(
                    provedor=conversation.inbox.provedor,
                    tipo="whatsapp_oficial",
                    ativo=True
                ).first() if conversation.inbox else None

                if canal_oficial:
                    # Verificar se a janela de 24 horas está aberta para WhatsApp Official
                    if not conversation.is_24h_window_open():
                        error_message = translate_whatsapp_error(131047)
                        logger.warning(f"[SEND_MEDIA] Janela de 24 horas fechada para conversa {conversation.id}")
                        
                        # Salvar mensagem com erro
                        additional_attrs = message.additional_attributes or {}
                        additional_attrs['sent_success'] = False
                        additional_attrs['channel_type'] = channel_type
                        additional_attrs['error_message'] = error_message
                        additional_attrs['error_code'] = 131047
                        additional_attrs['delivery_error_code'] = 131047
                        additional_attrs['delivery_error_message'] = error_message
                        message.additional_attributes = additional_attrs
                        message.save(update_fields=['additional_attributes'])
                        
                        # Retornar erro para o frontend
                        response_data = MessageSerializer(message).data
                        response_data['sent_success'] = False
                        response_data['channel_type'] = channel_type
                        response_data['whatsapp_sent'] = False
                        response_data['error_message'] = error_message
                        response_data['error_code'] = 131047
                        
                        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                    
                    # A conversão de .webm para .ogg já foi feita antes de criar a mensagem (se necessário)
                    # Detectar MIME type do arquivo
                    import mimetypes
                    detected_mime, _ = mimetypes.guess_type(final_file_path)
                    if not detected_mime:
                        # Fallback baseado na extensão
                        ext = os.path.splitext(final_filename)[1].lower()
                        mime_map = {
                            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                            '.png': 'image/png', '.gif': 'image/gif',
                            '.webp': 'image/webp', 
                            '.mp4': 'video/mp4', '.3gp': 'video/3gpp',
                            '.webm': 'video/webm', 
                            '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg',
                            '.pdf': 'application/pdf'
                        }
                        detected_mime = mime_map.get(ext, 'application/octet-stream')
                    
                    # Mensagem de voz (PTT) vs áudio comum — flag voice afeta reprodução no WhatsApp
                    from integrations.whatsapp_media import is_whatsapp_voice_message
                    is_voice = is_whatsapp_voice_message(media_type)
                    
                    # Para WhatsApp Official, precisamos usar o external_id (wamid) da mensagem original para reply
                    whatsapp_reply_id = None
                    if reply_to_message_id:
                        try:
                            # Se já for um wamid (string começando com "wamid."), usar diretamente
                            if isinstance(reply_to_message_id, str) and reply_to_message_id.startswith('wamid.'):
                                whatsapp_reply_id = reply_to_message_id
                                logger.info(f"[SEND_MEDIA] Usando wamid diretamente para reply: {whatsapp_reply_id}")
                            else:
                                # Se for um ID numérico, buscar a mensagem original para obter o external_id (wamid)
                                try:
                                    reply_id_int = int(reply_to_message_id)
                                    original_message = Message.objects.filter(
                                        id=reply_id_int,
                                        conversation=conversation
                                    ).first()
                                    if original_message and original_message.external_id:
                                        whatsapp_reply_id = original_message.external_id
                                        logger.info(f"[SEND_MEDIA] Usando external_id para reply: {whatsapp_reply_id}")
                                    else:
                                        logger.warning(f"[SEND_MEDIA] Mensagem original não encontrada ou sem external_id: {reply_to_message_id}")
                                except (ValueError, TypeError):
                                    # Se não for um número válido, tentar usar como string (pode ser um wamid)
                                    whatsapp_reply_id = str(reply_to_message_id)
                                    logger.info(f"[SEND_MEDIA] Usando reply_to_message_id como string para reply: {whatsapp_reply_id}")
                        except Exception as e:
                            logger.error(f"[SEND_MEDIA] Erro ao buscar mensagem original para reply: {str(e)}")
                    
                    # Enviar via WhatsApp Cloud API usando upload de mídia (recomendado)
                    success, response_msg = send_via_whatsapp_cloud_api(
                        conversation=conversation,
                        content=caption_to_send or "",
                        message_type=media_type,
                        file_path=final_file_path,  # Caminho local do arquivo
                        file_name=final_filename,   # Nome do arquivo (importante para documentos)
                        mime_type=detected_mime,    # Tipo MIME
                        is_voice_message=is_voice if media_type in ('audio', 'ptt', 'myaudio') else None,
                        file_url=None,              # Não usar URL, usar upload
                        reply_to_message_id=whatsapp_reply_id  # external_id (wamid) da mensagem original
                    )

                    # Se sucesso, tentar extrair external_id e salvar
                    try:
                        resp_data = response_msg
                        if isinstance(response_msg, str):
                            resp_data = json.loads(response_msg)
                        if isinstance(resp_data, dict):
                            messages_arr = resp_data.get("messages") or []
                            if messages_arr:
                                msg_id = messages_arr[0].get("id")
                                if msg_id:
                                    message.external_id = msg_id
                                    add_attrs = message.additional_attributes or {}
                                    add_attrs["external_id"] = msg_id
                                    message.additional_attributes = add_attrs
                                    message.save(update_fields=["external_id", "additional_attributes"])
                                    logger.info(f"[SEND_MEDIA] external_id salvo: message={message.id} wamid={msg_id}")
                                else:
                                    logger.warning(f"[SEND_MEDIA] Resposta sem 'id' em messages[0]: {resp_data}")
                            else:
                                logger.warning(f"[SEND_MEDIA] Resposta sem 'messages': success={success} resp_data={resp_data}")
                        else:
                            logger.warning(f"[SEND_MEDIA] response_msg não é dict/JSON válido: success={success} tipo={type(response_msg)} valor={response_msg}")
                    except Exception as extract_err:
                        logger.error(f"[SEND_MEDIA] Erro ao extrair/salvar external_id: {extract_err} | response_msg={response_msg}", exc_info=True)
                elif channel_type == 'whatsapp':
                    # Enviar para o WhatsApp via Uazapi com a URL da mídia apenas se o canal for explicitamente 'whatsapp'
                    success, response_msg = send_media_via_uazapi(
                        conversation, file_url, media_type, caption_to_send, reply_to_message_id, local_message_id=str(message.id)
                    )
                else:
                    logger.warning(f"[SEND_MEDIA] Canal {channel_type} configurado mas sem método de envio adequado.")
                    success = False
                    response_msg = "Canal não suportado para mídia ou não configurado."
            elif channel_type == 'app_mobile':
                from conversations.app_mobile import send_app_mobile_outbound

                caption_to_send = formatted_caption if formatted_caption else caption
                success, response_msg = send_app_mobile_outbound(
                    conversation,
                    caption_to_send or '',
                    media_type,
                    file_path=final_file_path,
                    file_name=final_filename,
                    mime_type=mime,
                )
                if success and isinstance(response_msg, dict) and response_msg.get('file_url'):
                    add_attrs = message.additional_attributes or {}
                    add_attrs['app_file_url'] = response_msg['file_url']
                    add_attrs['sent_success'] = True
                    add_attrs['channel_type'] = 'app_mobile'
                    add_attrs['app_mobile_sent'] = True
                    # Manter file_url local do painel; app usa app_file_url.
                    if not add_attrs.get('local_file_url') and message.file_url:
                        add_attrs['local_file_url'] = message.file_url
                    message.additional_attributes = add_attrs
                    message.save(update_fields=['additional_attributes'])
            elif channel_type == 'instagram':
                from integrations.instagram_send import send_instagram_media

                contact = conversation.contact
                canal_instagram = conversation.inbox.get_canal_instance()
                recipient_id = (contact.additional_attributes or {}).get('instagram_scoped_id') or contact.phone
                caption_to_send = formatted_caption if formatted_caption else caption

                if canal_instagram and canal_instagram.token and recipient_id:
                    success, ig_response, ig_error = send_instagram_media(
                        canal_instagram,
                        str(recipient_id),
                        media_type,
                        file_url,
                        caption=caption_to_send or None,
                        mime_type=mime,
                    )
                    response_msg = ig_response
                    if success and isinstance(ig_response, dict):
                        ig_mid = ig_response.get('message_id')
                        if ig_mid:
                            message.external_id = str(ig_mid)
                            add_attrs = message.additional_attributes or {}
                            add_attrs['external_id'] = str(ig_mid)
                            add_attrs['sent_success'] = True
                            add_attrs['channel_type'] = 'instagram'
                            add_attrs['instagram_sent'] = True
                            add_attrs['instagram_response'] = ig_response
                            message.additional_attributes = add_attrs
                            message.save(update_fields=['external_id', 'additional_attributes'])
                    elif not success:
                        logger.warning('[SEND_MEDIA] Falha Instagram: %s', ig_error)
                else:
                    logger.warning('[SEND_MEDIA] Canal Instagram não configurado ou contato sem IGSID')
                    success = False
                    response_msg = 'Canal Instagram não configurado'
            else:
                logger.warning(f"[SEND_MEDIA] Tipo de canal desconhecido: {channel_type}")
                success = False
            
            # Atualizar mensagem do banco antes de serializar para WebSocket (garantir external_id e atributos atualizados)
            message.refresh_from_db()
            
            # A notificação agora é feita via signal (post_save no modelo Message)
            # para garantir que a ordenação mude em tempo real no dashboard
            
            response_data = MessageSerializer(message).data
            response_data['sent_success'] = success
            response_data['channel_type'] = channel_type
            
            # Salvar mensagem de erro se o envio falhou
            if not success:
                additional_attrs = message.additional_attributes or {}
                additional_attrs['sent_success'] = False
                additional_attrs['channel_type'] = channel_type
                
                error_message = None
                error_code = None
                if channel_type == 'telegram':
                    if 'response_msg' in locals() and response_msg:
                        error_message = str(response_msg)
                else:
                    if 'response_msg' in locals() and response_msg:
                        # Tentar extrair erro do formato JSON retornado pela função
                        try:
                            if isinstance(response_msg, str):
                                try:
                                    error_data = json.loads(response_msg)
                                    if isinstance(error_data, dict):
                                        error_message = error_data.get('error_message', str(response_msg))
                                        error_code = error_data.get('error_code')
                                except:
                                    # Se não for JSON válido, usar a string diretamente
                                    error_message = str(response_msg)
                            else:
                                error_message = str(response_msg)
                        except:
                            error_message = str(response_msg)
                
                if error_message:
                    additional_attrs['error_message'] = error_message
                    if error_code:
                        additional_attrs['error_code'] = error_code
                
                message.additional_attributes = additional_attrs
                message.save(update_fields=['additional_attributes'])
            
            if channel_type == 'telegram':
                response_data['telegram_sent'] = success
                if not success and 'response_msg' in locals() and response_msg:
                    response_data['error_message'] = str(response_msg)
            elif channel_type == 'instagram':
                response_data['instagram_sent'] = success
                if 'response_msg' in locals() and response_msg:
                    response_data['instagram_response'] = response_msg
                if not success and 'response_msg' in locals() and response_msg:
                    response_data['error_message'] = str(response_msg)
            else:
                response_data['whatsapp_sent'] = success
                if 'response_msg' in locals():
                    response_data['whatsapp_response'] = response_msg
                    # Incluir mensagem de erro na resposta se o envio falhou
                    if not success and response_msg:
                        response_data['error_message'] = str(response_msg)
                        # Extrair código de erro se disponível
                        try:
                            if isinstance(response_msg, str):
                                try:
                                    error_data = json.loads(response_msg)
                                    if isinstance(error_data, dict) and 'error' in error_data:
                                        error_code = error_data['error'].get('code')
                                        if error_code:
                                            response_data['error_code'] = error_code
                                except:
                                    pass
                        except:
                            pass
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)


    @action(detail=False, methods=['post'])
    def presence(self, request):
        """Enviar status de presença (digitando)"""
        conversation_id = request.data.get('conversation_id')
        presence_type = request.data.get('presence_type', 'typing')  # typing, recording, paused
        
        if not conversation_id:
            return Response({'error': 'conversation_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            
            # Enviar indicador de presença para o WhatsApp via Uazapi
            success, whatsapp_response = send_presence_via_uazapi(conversation, presence_type)
            
            return Response({
                'status': 'success',
                'conversation_id': conversation_id,
                'presence_type': presence_type,
                'whatsapp_sent': success,
                'whatsapp_response': whatsapp_response
            })
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def react(self, request):
        """Enviar reação a uma mensagem. Otimizado para concorrência e idempotência."""
        from django.db import transaction
        try:
            message_id = request.data.get('message_id')
            emoji = request.data.get('emoji', '')
            
            if not message_id:
                return Response({'error': 'message_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar a mensagem com select_related para eficiência
            try:
                message = Message.objects.select_related('conversation', 'conversation__inbox', 'conversation__inbox__provedor').get(id=message_id)
            except Message.DoesNotExist:
                return Response({'error': 'Mensagem não encontrada'}, status=status.HTTP_404_NOT_FOUND)
            
            conversation = message.conversation
            user = request.user

            # 1. SEGURANÇA: Verificar se o usuário tem permissão
            if user.user_type != 'superadmin':
                # Só o atendente atribuído ou admin do provedor pode reagir
                provedores = user.provedores_admin.all()
                if not provedores.filter(id=conversation.inbox.provedor_id).exists():
                    if conversation.assignee_id != user.id:
                        return Response({'error': 'Sem permissão para esta mensagem'}, status=status.HTTP_403_FORBIDDEN)
            
            # 2. CONCORRÊNCIA E IDEMPOTÊNCIA
            # IMPORTANTE: Remover select_for_update() para evitar deadlock com SQLite
            # Usar get_or_create em vez de update_or_create para reduzir conflitos
            max_retries = 3
            retry_count = 0
            reaction_obj = None  # Inicializar antes do loop
            
            while retry_count < max_retries:
                try:
                    with transaction.atomic():
                        # Obter external_id (ID da mensagem no WhatsApp) ANTES de salvar no banco
                        whatsapp_message_id = message.external_id or (message.additional_attributes or {}).get('whatsapp_message_id')
                        
                        # 3. API EXTERNA (Se for WhatsApp) - fazer ANTES de salvar no banco
                        if conversation.inbox.channel_type in ['whatsapp', 'whatsapp_oficial'] and whatsapp_message_id:
                            from integrations.whatsapp_cloud_send import send_reaction
                            success, response_msg = send_reaction(conversation, whatsapp_message_id, emoji)
                            
                            if not success:
                                return Response({'success': False, 'error': response_msg}, status=500)
                        elif conversation.inbox.channel_type == 'instagram' and whatsapp_message_id:
                            from integrations.instagram_send import send_instagram_reaction, send_instagram_unreact

                            contact = conversation.contact
                            canal_instagram = conversation.inbox.get_canal_instance()
                            recipient_id = (
                                (contact.additional_attributes or {}).get('instagram_scoped_id') or contact.phone
                            )
                            if not canal_instagram or not canal_instagram.token or not recipient_id:
                                return Response(
                                    {'success': False, 'error': 'Canal Instagram não configurado'},
                                    status=500,
                                )
                            if emoji == '':
                                success, response_msg, ig_error = send_instagram_unreact(
                                    canal_instagram, str(recipient_id), whatsapp_message_id
                                )
                            else:
                                success, response_msg, ig_error = send_instagram_reaction(
                                    canal_instagram, str(recipient_id), whatsapp_message_id, emoji
                                )
                            if not success:
                                err = ig_error if 'ig_error' in locals() else response_msg
                                return Response({'success': False, 'error': err}, status=500)

                        # 4. BANCO LOCAL - usar get_or_create para evitar deadlock
                        if emoji == '':
                            # Remover reações do agente se emoji for vazio (unreact)
                            MessageReaction.objects.filter(message=message, is_from_customer=False).delete()
                            reaction_obj = None
                        else:
                            # Verificar se já existe antes (idempotência)
                            existing = MessageReaction.objects.filter(message=message, is_from_customer=False, emoji=emoji).first()
                            if existing:
                                # Reação já existe, atualizar additional_attributes
                                reaction_obj = existing
                                attrs = dict(existing.additional_attributes) if existing.additional_attributes else {}
                                attrs['sent_by'] = user.id
                                attrs['sent_at'] = datetime.now().isoformat()
                                existing.additional_attributes = attrs
                                existing.save(update_fields=['additional_attributes'])
                            else:
                                # Criar nova reação usando get_or_create (mais seguro que update_or_create)
                                reaction_obj, created = MessageReaction.objects.get_or_create(
                                    message=message,
                                    is_from_customer=False,
                                    emoji=emoji,
                                    defaults={
                                        'additional_attributes': {
                                            'sent_by': user.id,
                                            'sent_at': datetime.now().isoformat()
                                        }
                                    }
                                )
                                
                                # Se não foi criado (concorrência), atualizar
                                if not created:
                                    attrs = dict(reaction_obj.additional_attributes) if reaction_obj.additional_attributes else {}
                                    attrs['sent_by'] = user.id
                                    attrs['sent_at'] = datetime.now().isoformat()
                                    reaction_obj.additional_attributes = attrs
                                    reaction_obj.save(update_fields=['additional_attributes'])
                            
                        # Se chegou aqui, a transação foi bem-sucedida, sair do loop
                        break
                        
                except Exception as db_error:
                    retry_count += 1
                    error_str = str(db_error).lower()
                    # Se for erro de lock e ainda há tentativas, retentar
                    if ('locked' in error_str or 'database is locked' in error_str or 'operationalerror' in error_str) and retry_count < max_retries:
                        import time
                        time.sleep(0.1 * retry_count)  # Backoff exponencial
                        continue
                    else:
                        # Se não for erro de lock ou esgotaram as tentativas, relançar o erro
                        raise

            # 5. NOTIFICAÇÃO (WebSocket) - Emitir apenas um evento (fora do loop while)
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"conversation_{conversation.id}",
                        {
                            "type": "message_reaction",
                            "message_id": message.id,
                            "reaction": {
                                "id": reaction_obj.id if reaction_obj else None,
                                "emoji": emoji,
                                "is_from_customer": False,
                                "removed": emoji == ''
                            }
                        }
                    )
            except Exception as ws_error:
                # Log mas não falhar se WebSocket der erro
                logger.warning(f"Erro ao enviar WebSocket de reação: {ws_error}")

            return Response({
                'success': True,
                'message': 'Reação processada com sucesso',
                'reaction': {'emoji': emoji, 'message_id': message.id}
            })

        except Exception as e:
            logger.error(f"Erro crítico em react: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['post'])
    def delete_message(self, request):
        """Apagar mensagem para todos"""
        try:
            message_id = request.data.get('message_id')
            
            if not message_id:
                return Response({'error': 'message_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Buscar a mensagem
            message = Message.objects.get(id=message_id)
            conversation = message.conversation
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                provedores = Provedor.objects.filter(admins=user)
                if not provedores.exists() or conversation.inbox.provedor not in provedores:
                    return Response({'error': 'Sem permissão para esta mensagem'}, status=status.HTTP_403_FORBIDDEN)
            
            # Verificar se a mensagem tem ID externo (para WhatsApp)
            external_id = message.external_id
            
            # Se tem external_id, tentar excluir via Uazapi
            if external_id:
                # Buscar credenciais Uazapi
                provedor = conversation.inbox.provedor
                uazapi_token = provedor.integracoes_externas.get('whatsapp_token')
                uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                
                if uazapi_token and uazapi_url:
                    # Preparar payload para Uazapi
                    chat_id = conversation.contact.phone
                    if not chat_id.endswith('@s.whatsapp.net'):
                        chat_id = f"{chat_id}@s.whatsapp.net"
                    
                    # Tentar diferentes formatos de ID
                    id_formats = [external_id]
                    
                    # Se o ID contém ":", tentar sem o prefixo
                    if ':' in external_id:
                        short_id = external_id.split(':', 1)[1]
                        id_formats.append(short_id)
                    
                    # Se o ID não contém ":", tentar com o prefixo do provedor
                    else:
                        # Buscar o número do provedor
                        provedor_number = None
                        if provedor.integracoes_externas:
                            # Tentar extrair o número do provedor das configurações
                            instance = provedor.integracoes_externas.get('instance')
                            if instance:
                                provedor_number = instance.replace('@s.whatsapp.net', '').replace('@c.us', '')
                        
                        if provedor_number:
                            full_id = f"{provedor_number}:{external_id}"
                            id_formats.append(full_id)
                    
                    
                    success = False
                    for msg_id in id_formats:
                        payload = {
                            'number': chat_id,
                            'id': msg_id
                        }
                        
                        
                        # Apagar mensagem via Uazapi
                        response = requests.post(
                            f"{uazapi_url.rstrip('/')}/message/delete",
                            headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                            json=payload,
                            timeout=10
                        )
                        
                        
                        if response.status_code == 200:
                            result = response.json()
                            success = True
                            break
                        else:
                            pass
                    
                    if success:
                        # Se conseguiu apagar via Uazapi, verificar se é mensagem da IA
                        if not message.is_from_customer:
                            # Mensagem da IA: apagar apenas do WhatsApp, manter no sistema
                            return Response({
                                'success': True,
                                'message': 'Mensagem apagada do WhatsApp com sucesso',
                                'data': result
                            })
                        else:
                            # Mensagem do cliente: marcar como deletada no sistema também
                            additional_attrs = message.additional_attributes or {}
                            additional_attrs['status'] = 'deleted'
                            additional_attrs['deleted_at'] = str(datetime.now())
                            message.additional_attributes = additional_attrs
                            message.save()
                    else:
                        result = {'error': f'Erro Uazapi: todos os formatos falharam'}
                        return Response({
                            'success': False,
                            'message': 'Não foi possível apagar a mensagem no WhatsApp',
                            'data': result
                        })
                else:
                    result = {'warning': 'Configuração Uazapi não encontrada'}
                    return Response({
                        'success': False,
                        'message': 'Configuração Uazapi não encontrada',
                        'data': result
                    })
            else:
                result = {'warning': 'Mensagem não possui ID externo'}
                return Response({
                    'success': False,
                    'message': 'Mensagem não possui ID externo para exclusão',
                    'data': result
                })
            
            # Só chega aqui se o Uazapi retornou sucesso
            # Atualizar status da mensagem local (sempre)
            additional_attrs = message.additional_attributes or {}
            additional_attrs['status'] = 'deleted'
            additional_attrs['deleted_at'] = str(datetime.now())
            message.additional_attributes = additional_attrs
            message.save()
            
            # Emitir evento WebSocket
            channel_layer = get_channel_layer()
            from conversations.serializers import MessageSerializer
            message_data = MessageSerializer(message).data
            
            async_to_sync(channel_layer.group_send)(
                f'conversation_{conversation.id}',
                {
                    'type': 'chat_message',
                    'message': message_data,
                    'sender': None,
                    'timestamp': message.updated_at.isoformat(),
                }
            )
            
            # Serializar a mensagem atualizada
            from conversations.serializers import MessageSerializer
            message_data = MessageSerializer(message).data
            
            return Response({
                'success': True,
                'message': 'Mensagem apagada com sucesso',
                'data': result,
                'updated_message': message_data
            })
                
        except Message.DoesNotExist:
            return Response({'error': 'Mensagem não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erro interno: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='typing-indicator', url_name='typing-indicator')
    def typing_indicator(self, request):
        """
        Envia indicador de digitação (typing indicator) via WhatsApp Cloud API.
        
        Este endpoint deve ser chamado quando o atendente começar a digitar uma resposta.
        O indicador será removido automaticamente quando uma mensagem for enviada ou após 25 segundos.
        
        IMPORTANTE: Apenas envie o indicador se você realmente for responder em breve.
        """
        import time as _time
        t_start = _time.monotonic()
        try:
            message_id = request.data.get('message_id')
            conversation_id = request.data.get('conversation_id')
            
            if not message_id and not conversation_id:
                return Response({
                    'error': 'message_id ou conversation_id é obrigatório'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Se fornecer conversation_id, buscar a última mensagem do cliente
            if conversation_id and not message_id:
                try:
                    conversation = Conversation.objects.select_related(
                        'inbox', 'inbox__provedor', 'assignee'
                    ).get(id=conversation_id)

                    # Verificar permissões (caminho rápido: atendente já é o assignee)
                    user = request.user
                    if user.user_type != 'superadmin' and conversation.assignee_id != user.id:
                        provedores = Provedor.objects.filter(admins=user)
                        if not provedores.exists() or conversation.inbox.provedor not in provedores:
                            return Response({
                                'error': 'Sem permissão para esta conversa'
                            }, status=status.HTTP_403_FORBIDDEN)
                    
                    # Buscar última mensagem recebida do cliente nesta conversa
                    last_message = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=True
                    ).order_by('-created_at').only('id', 'external_id').first()
                    
                    if not last_message or not last_message.external_id:
                        return Response({
                            'error': 'Nenhuma mensagem do cliente encontrada para enviar indicador'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                    message_id = last_message.external_id
                    channel_type = conversation.inbox.channel_type if conversation.inbox else None
                    if channel_type not in ('whatsapp', 'whatsapp_oficial'):
                        return Response({
                            'error': 'Esta funcionalidade é apenas para mensagens do WhatsApp'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Buscar o canal exato vinculado a este inbox (evita pegar outro
                    # canal whatsapp_oficial do mesmo provedor sem token/phone_number_id).
                    canal = conversation.inbox.get_canal_instance()
                    
                    if not canal:
                        return Response({
                            'error': 'Canal WhatsApp não encontrado'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                except Conversation.DoesNotExist:
                    return Response({
                        'error': 'Conversa não encontrada'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                # Se fornecer message_id diretamente, buscar a mensagem
                try:
                    message = Message.objects.get(external_id=message_id)
                    conversation = message.conversation
                    
                    # Verificar permissões
                    user = request.user
                    if user.user_type != 'superadmin':
                        provedores = Provedor.objects.filter(admins=user)
                        if not provedores.exists() or conversation.inbox.provedor not in provedores:
                            if conversation.assignee != user:
                                return Response({
                                    'error': 'Sem permissão para esta mensagem'
                                }, status=status.HTTP_403_FORBIDDEN)
                    
                    channel_type = conversation.inbox.channel_type if conversation.inbox else None
                    if channel_type not in ('whatsapp', 'whatsapp_oficial'):
                        return Response({
                            'error': 'Esta funcionalidade é apenas para mensagens do WhatsApp'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Buscar o canal exato vinculado a este inbox (evita pegar outro
                    # canal whatsapp_oficial do mesmo provedor sem token/phone_number_id).
                    canal = conversation.inbox.get_canal_instance()
                    
                    if not canal:
                        return Response({
                            'error': 'Canal WhatsApp não encontrado'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                except Message.DoesNotExist:
                    return Response({
                        'error': 'Mensagem não encontrada'
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Enviar indicador de digitação
            t_before_meta = _time.monotonic()
            from integrations.whatsapp_cloud_send import send_typing_indicator
            success, error_msg = send_typing_indicator(canal, message_id)
            t_end = _time.monotonic()
            logger.info(
                f"[TypingIndicator] total={(t_end - t_start) * 1000:.0f}ms "
                f"db={(t_before_meta - t_start) * 1000:.0f}ms "
                f"meta_api={(t_end - t_before_meta) * 1000:.0f}ms success={success}"
            )
            
            if success:
                return Response({
                    'success': True,
                    'message': 'Indicador de digitação enviado com sucesso'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': error_msg or 'Erro ao enviar indicador de digitação'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Erro ao enviar indicador de digitação: {str(e)}", exc_info=True)
            return Response({
                'error': f'Erro ao enviar indicador de digitação: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        """
        Marca as mensagens do WhatsApp como lidas na API da Meta e no banco local.
        Otimizado para concorrência e idempotência.
        """
        from django.db import transaction
        try:
            message_id = request.data.get('message_id')
            if not message_id:
                return Response({'error': 'message_id é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)

            # Buscar mensagem com select_related para evitar múltiplas queries
            try:
                message = Message.objects.select_related(
                    'conversation', 
                    'conversation__inbox', 
                    'conversation__inbox__provedor'
                ).get(id=message_id)
            except Message.DoesNotExist:
                return Response({'error': 'Mensagem não encontrada'}, status=status.HTTP_404_NOT_FOUND)

            conversation = message.conversation
            user = request.user

            # 1. SEGURANÇA: Verificar se o usuário tem permissão
            if user.user_type != 'superadmin':
                # Só o atendente atribuído pode marcar como lida
                if conversation.assignee_id != user.id:
                    return Response({'success': True, 'message': 'Ignorado: usuário não é o atendente atribuído'})

            # 2. VALIDAÇÃO: Apenas WhatsApp e mensagens recebidas
            if not message.is_from_customer or conversation.inbox.channel_type not in ['whatsapp', 'whatsapp_oficial']:
                return Response({'error': 'Apenas mensagens do cliente via WhatsApp podem ser marcadas como lidas'}, status=status.HTTP_400_BAD_REQUEST)

            # 3. CONCORRÊNCIA E IDEMPOTÊNCIA
            with transaction.atomic():
                # Lock na conversa para evitar que múltiplos requests processem a mesma marcação
                conv_locked = Conversation.objects.select_for_update().get(id=conversation.id)
                
                # Se esta mensagem já está marcada como lida, nada a fazer
                if message.additional_attributes and message.additional_attributes.get('marked_as_read_at'):
                    return Response({'success': True, 'message': 'Já marcada como lida'})

                # Obter external_id
                whatsapp_message_id = message.external_id or (message.additional_attributes or {}).get('whatsapp_message_id')
                if not whatsapp_message_id:
                    return Response({'error': 'Mensagem não possui ID externo do WhatsApp'}, status=status.HTTP_400_BAD_REQUEST)

                # 4. API META: Chamar API uma única vez
                from integrations.whatsapp_cloud_send import mark_message_as_read
                success, error_msg = mark_message_as_read(conversation, whatsapp_message_id)

                if success:
                    # 5. ATUALIZAÇÃO EM MASSA (Bulk Update)
                    now_str = datetime.now().isoformat()
                    
                    # Marcar todas as mensagens pendentes nesta conversa ATÉ a mensagem atual
                    unread_qs = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=True,
                        created_at__lte=message.created_at
                    ).exclude(additional_attributes__has_key='marked_as_read_at')

                    if unread_qs.exists():
                        for msg in unread_qs:
                            attrs = msg.additional_attributes or {}
                            attrs['marked_as_read_at'] = now_str
                            attrs['marked_as_read_by'] = user.id
                            msg.additional_attributes = attrs
                        
                        # bulk_update é MUITO mais eficiente que saves individuais
                        Message.objects.bulk_update(unread_qs, ['additional_attributes'])

                    return Response({
                        'success': True,
                        'message': f'Mensagens marcadas como lidas até {message_id}'
                    })
                else:
                    return Response({
                        'success': False,
                        'error': error_msg or 'Erro na API da Meta'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Erro crítico em mark_as_read: {str(e)}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        # Equipe virtual "IA" não é mais usada nem exibida na gestão de equipes
        base = Team.objects.exclude(name__iexact='IA')
        if user.user_type == 'superadmin':
            return base
        else:
            # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
            provedores = user.provedores_admin.all()
            if provedores.exists():
                return base.filter(provedor__in=provedores)
            return Team.objects.none()
    
    def perform_create(self, serializer):
        """Definir empresa automaticamente baseado no usuário atual e adicionar membros corretamente"""
        user = self.request.user
        team_name = (serializer.validated_data.get('name') or '').strip()
        if team_name.upper() == 'IA':
            raise serializers.ValidationError(
                {'name': 'Não é permitido criar uma equipe com o nome IA.'}
            )
        
        # Para superadmin, permitir escolher empresa ou usar a primeira
        if user.user_type == 'superadmin':
            provedor = serializer.validated_data.get('provedor')
            if not provedor:
                provedor = Provedor.objects.first()
                if not provedor:
                    raise serializers.ValidationError("Nenhum provedor encontrado no sistema")
        else:
            # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
            provedores = user.provedores_admin.all()
            if not provedores.exists():
                raise serializers.ValidationError("Usuário não está associado a nenhum provedor")
            provedor = provedores.first()
        
        # Salvar a equipe com a empresa definida
        team = serializer.save(provedor=provedor)
        
        # Registrar log de auditoria
        from core.models import AuditLog
        ip = self.request.META.get('REMOTE_ADDR') if hasattr(self.request, 'META') else None
        AuditLog.objects.create(
            user=user,
            action='create',
            ip_address=ip,
            details=f'Equipe criada: {team.name}',
            provedor=provedor
        )
        
        # Adicionar membros a partir do payload da requisição
        members_ids = self.request.data.get('members', [])
        if isinstance(members_ids, str):
            # Se vier como string JSON, converte
            import json
            try:
                members_ids = json.loads(members_ids)
            except Exception:
                members_ids = []
        for member_id in members_ids:
            try:
                member_user = User.objects.get(id=member_id)
                TeamMember.objects.get_or_create(user=member_user, team=team)
            except User.DoesNotExist:
                pass
        return team
    
    def perform_update(self, serializer):
        # Atualizar equipe e seus membros
        user = self.request.user
        # Para superadmin, permitir escolher empresa ou usar a primeira
        if user.user_type == 'superadmin':
            provedor = serializer.validated_data.get('provedor')
            if not provedor:
                provedor = Provedor.objects.first()
                if not provedor:
                    raise serializers.ValidationError("Nenhum provedor encontrado no sistema")
        else:
            # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
            provedores = user.provedores_admin.all()
            if not provedores.exists():
                raise serializers.ValidationError("Usuário não está associado a nenhum provedor")
            provedor = provedores.first()
        # Salvar a equipe com a empresa definida
        team = serializer.save(provedor=provedor)
        if 'members' in self.request.data:
            TeamMember.objects.filter(team=team).delete()
            members_ids = self.request.data.get('members', [])
            if isinstance(members_ids, str):
                import json
                try:
                    members_ids = json.loads(members_ids)
                except Exception:
                    members_ids = []
            for member_id in members_ids:
                try:
                    member_user = User.objects.get(id=member_id)
                    TeamMember.objects.get_or_create(user=member_user, team=team)
                except User.DoesNotExist:
                    pass
        return team
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """Adicionar membro à equipe"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        is_admin = request.data.get('is_admin', False)
        
        try:
            user = User.objects.get(id=user_id)
            team_member, created = TeamMember.objects.get_or_create(
                user=user,
                team=team,
                defaults={'is_admin': is_admin}
            )
            
            if created:
                return Response({'status': 'member added'})
            else:
                return Response({'error': 'User already in team'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        """Remover membro da equipe"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            team_member = TeamMember.objects.get(user_id=user_id, team=team)
            team_member.delete()
            return Response({'status': 'member removed'})
        except TeamMember.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def perform_destroy(self, instance):
        """Registrar log de auditoria quando equipe é excluída"""
        user = self.request.user
        ip = self.request.META.get('REMOTE_ADDR') if hasattr(self.request, 'META') else None
        
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user,
            action='delete',
            ip_address=ip,
            details=f'Equipe excluída: {instance.name}',
            provedor=instance.provedor
        )
        
        # Executar a exclusão
        instance.delete()


class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.all()
    serializer_class = TeamMemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return TeamMember.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                return TeamMember.objects.filter(team__provedor__in=provedores)
            return TeamMember.objects.none()


def serve_media_file(request, conversation_id, filename):
    """
    Serve media files for conversations.
    Requer URL assinada (?expires=&sig=) ou Authorization: Token com ACL do provedor.
    Se o arquivo sumiu do disco, tenta rebaixar via WhatsApp Graph API (media_id).
    """
    from urllib.parse import unquote, quote
    from django.http import Http404, FileResponse, HttpResponseForbidden
    from core.media_signing import (
        media_require_signed_url,
        user_may_access_conversation_media,
        verify_request_media_signature,
    )
    from core.auth_token_cache import user_from_token_key

    def _resolve_media_paths(conv_id, name):
        """Paths possíveis (WORKDIR backend vs imagem dramatiq)."""
        names = [name, unquote(name)]
        roots = [
            os.path.join(settings.MEDIA_ROOT, 'messages', str(conv_id)),
            os.path.join('/app/backend/media', 'messages', str(conv_id)),
            os.path.join('/app/painel-provedor/backend/media', 'messages', str(conv_id)),
        ]
        seen = set()
        for root in roots:
            real_root = os.path.realpath(root) if os.path.isdir(root) else root
            if real_root in seen:
                continue
            seen.add(real_root)
            for n in names:
                candidate = os.path.join(root, n)
                if os.path.isfile(candidate):
                    return candidate, root
        return None, roots[0]

    def _extract_media_id(name, message_obj):
        attrs = (message_obj.additional_attributes or {}) if message_obj else {}
        mid = attrs.get('whatsapp_media_id') or attrs.get('media_id')
        if mid:
            return str(mid)
        # media_{ts}_{media_id}.ext
        m = re.search(r'media_\d+_(\d+)\.[A-Za-z0-9]+$', name or '')
        if m:
            return m.group(1)
        return None

    def _find_message_for_file(conv_id, name):
        from conversations.models import Message
        qs = Message.objects.filter(conversation_id=conv_id).order_by('-id')
        # file_name exato ou URL contendo o nome
        msg = qs.filter(file_name=name).first()
        if msg:
            return msg
        msg = qs.filter(file_url__icontains=name).first()
        if msg:
            return msg
        msg = qs.filter(additional_attributes__local_file_url__icontains=name).first()
        return msg

    def _try_recover_file(conversation, name):
        msg = _find_message_for_file(conversation.id, name)
        media_id = _extract_media_id(name, msg)
        if not media_id:
            return None
        canal = None
        try:
            inbox = getattr(conversation, 'inbox', None)
            if inbox is not None and hasattr(inbox, 'get_canal_instance'):
                canal = inbox.get_canal_instance()
            if not canal and inbox is not None:
                provedor_id = getattr(inbox, 'provedor_id', None)
                if provedor_id:
                    canal = Canal.objects.filter(
                        provedor_id=provedor_id, tipo='whatsapp_oficial', ativo=True
                    ).first()
        except Exception:
            canal = None
        if not canal or not canal.token:
            return None
        try:
            from integrations.coexistence_webhooks import download_whatsapp_media_as
            return download_whatsapp_media_as(media_id, canal, conversation.id, name)
        except Exception as exc:
            logger.warning("[ServeMedia] recover failed conv=%s file=%s: %s", conversation.id, name, exc)
            return None

    try:
        import re
        from django.conf import settings
        from core.models import Canal

        decoded_filename = unquote(filename)

        try:
            conversation = Conversation.objects.select_related('inbox').get(id=conversation_id)
        except Conversation.DoesNotExist:
            logger.error(f"[ServeMedia] Conversa {conversation_id} não encontrada")
            raise Http404("Conversa não encontrada")

        # Auth: assinatura HMAC (img/audio) OU token DRF no header com ACL
        signed_ok = verify_request_media_signature(request)
        auth_user = None
        auth_header = request.META.get('HTTP_AUTHORIZATION') or ''
        if auth_header.startswith('Token '):
            auth_user = user_from_token_key(auth_header[7:].strip())

        if media_require_signed_url():
            if not signed_ok:
                if not auth_user or not user_may_access_conversation_media(auth_user, conversation):
                    return HttpResponseForbidden("Assinatura de mídia inválida ou expirada")
            if auth_user and not user_may_access_conversation_media(auth_user, conversation):
                return HttpResponseForbidden("Sem permissão para esta mídia")

        file_path, media_dir = _resolve_media_paths(conversation_id, decoded_filename)
        final_filename = decoded_filename

        if not file_path:
            recovered = _try_recover_file(conversation, decoded_filename)
            if recovered and os.path.isfile(recovered):
                file_path = recovered
                final_filename = os.path.basename(recovered)
            else:
                # Evita spam: um warning por request (não error com stack)
                logger.warning(
                    "[ServeMedia] Arquivo ausente conv=%s file=%s dir=%s",
                    conversation_id,
                    decoded_filename,
                    media_dir,
                )
                raise Http404(f"Arquivo não encontrado: {decoded_filename}")

        real_media_root = os.path.realpath(str(settings.MEDIA_ROOT))
        alt_roots = [
            real_media_root,
            os.path.realpath('/app/backend/media'),
            os.path.realpath('/app/painel-provedor/backend/media'),
        ]
        real_file_path = os.path.realpath(file_path)
        if not any(
            real_file_path.startswith(root + os.sep) or real_file_path == root
            for root in alt_roots
            if root
        ):
            raise Http404("Acesso negado")

        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'

        safe_filename = quote(final_filename, safe='')

        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{final_filename}"; filename*=UTF-8\'\'{safe_filename}'
        response['Cache-Control'] = 'private, max-age=60'
        response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '') or '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response['Vary'] = 'Origin'

        return response

    except Conversation.DoesNotExist:
        raise Http404("Conversa não encontrada")
    except Http404:
        raise
    except Exception as e:
        logger.error(f"[ServeMedia] Erro ao servir arquivo {filename}: {e}", exc_info=True)
        raise Http404(f"Erro ao servir arquivo: {str(e)}")


from django.views.decorators.http import require_http_methods

@require_http_methods(["GET", "HEAD"])
def proxy_external_media(request):
    """
    Proxy para servir mídia externa (evita CORS).
    Requer URL assinada ou Authorization: Token.
    """
    import requests
    import mimetypes
    from urllib.parse import urlparse, parse_qs
    from django.http import HttpResponseForbidden
    from core.media_signing import media_require_signed_url, verify_request_media_signature
    from core.auth_token_cache import user_from_token_key

    if media_require_signed_url():
        signed_ok = verify_request_media_signature(request)
        auth_ok = False
        auth_header = request.META.get('HTTP_AUTHORIZATION') or ''
        if auth_header.startswith('Token '):
            auth_ok = user_from_token_key(auth_header[7:].strip()) is not None
        if not signed_ok and not auth_ok:
            return HttpResponseForbidden("Assinatura de mídia inválida ou expirada")

    # Obter URL do parâmetro
    external_url = request.GET.get('url')
    conversation_id_param = request.GET.get('conversation_id')
    
    if not external_url:
        return HttpResponse("URL não fornecida", status=400, content_type="text/plain")
    
    # Converter conversation_id para int se fornecido
    conversation_id = None
    if conversation_id_param:
        try:
            conversation_id = int(conversation_id_param)
        except (ValueError, TypeError):
            logger.warning(f"[ProxyMedia] conversation_id inválido: {conversation_id_param}")
    
    # Validar que é uma URL externa válida
    try:
        parsed = urlparse(external_url)
        if not parsed.scheme or not parsed.netloc:
            return HttpResponse("URL inválida", status=400, content_type="text/plain")
        
        # HTTPS sempre; HTTP só para hosts locais (Superadmin/dev do canal app)
        if parsed.scheme == 'https':
            pass
        elif parsed.scheme == 'http':
            host = (parsed.hostname or '').lower()
            local_hosts = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
            if host not in local_hosts and not getattr(settings, 'DEBUG', False):
                return HttpResponse(
                    "Apenas URLs HTTPS são permitidas",
                    status=400,
                    content_type="text/plain",
                )
        else:
            return HttpResponse("Apenas URLs HTTPS são permitidas", status=400, content_type="text/plain")
            
    except Exception:
        return HttpResponse("URL inválida", status=400, content_type="text/plain")
    
    try:
        # Headers padrão
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NioChat/1.0)'
        }
        
        # Se for URL do WhatsApp (lookaside.fbsbx.com), tentar usar token do canal
        is_whatsapp_url = 'lookaside.fbsbx.com' in external_url or 'facebook.com' in external_url
        
        if is_whatsapp_url and conversation_id:
            try:
                # Buscar conversa e canal para obter token
                conversation = Conversation.objects.select_related('inbox', 'inbox__provedor').get(id=conversation_id)
                inbox = conversation.inbox
                
                # Buscar canal WhatsApp associado ao inbox
                if inbox and inbox.provedor:
                    canal = Canal.objects.filter(
                        provedor=inbox.provedor,
                        tipo='whatsapp',
                        ativo=True
                    ).first()
                    
                    if canal and hasattr(canal, 'token') and canal.token:
                        # Usar token do canal para autenticação
                        headers['Authorization'] = f"Bearer {canal.token}"
                        logger.debug(f"[ProxyMedia] Usando token do canal {canal.id} para URL do WhatsApp")
            except (Conversation.DoesNotExist, AttributeError, Exception) as e:
                logger.warning(f"[ProxyMedia] Não foi possível obter token do canal: {e}")
                # Continuar sem token (pode funcionar se a URL já tiver autenticação)
        
        # Fazer requisição para a URL externa
        response = requests.get(external_url, headers=headers, stream=True, timeout=30, allow_redirects=True)
        
        if response.status_code != 200:
            logger.error(f"[ProxyMedia] Erro ao buscar mídia: {response.status_code} - {response.text[:200]}")
            return HttpResponse(
                f"Erro ao buscar mídia: {response.status_code}", 
                status=response.status_code, 
                content_type="text/plain"
            )
        
        # Determinar content-type
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        
        # Criar resposta Django com stream
        django_response = HttpResponse(content_type=content_type)
        
        # Adicionar headers CORS
        django_response['Access-Control-Allow-Origin'] = '*'
        django_response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        django_response['Access-Control-Allow-Headers'] = '*'
        
        # Copiar conteúdo do stream
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                django_response.write(chunk)
        
        return django_response
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao fazer proxy de mídia externa: {e}")
        return HttpResponse(f"Erro ao buscar mídia: {str(e)}", status=500, content_type="text/plain")
    except Exception as e:
        logger.error(f"Erro inesperado ao fazer proxy de mídia: {e}", exc_info=True)
        return HttpResponse("Erro interno", status=500, content_type="text/plain")


from rest_framework.views import APIView

class DashboardStatsView(APIView):
    """
    API para estatísticas do dashboard - Funcional
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        provedor = None
        
        # Se for superadmin, permitir passar provedor_id como parâmetro
        if user.user_type == 'superadmin':
            provedor_id_param = request.GET.get('provedor_id')
            if provedor_id_param:
                try:
                    provedor_id = int(provedor_id_param)
                    provedor = Provedor.objects.filter(id=provedor_id).first()
                    if not provedor:
                        return Response(
                            {'error': 'Provedor não encontrado'}, 
                            status=400
                        )
                except (ValueError, TypeError):
                    return Response(
                        {'error': 'provedor_id inválido'}, 
                        status=400
                    )
        
        # Se não foi passado como parâmetro, buscar do usuário
        if not provedor:
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
            if not provedor and hasattr(user, 'provedor') and user.provedor:
                provedor = user.provedor
            if not provedor:
                provedor = Provedor.objects.filter(admins=user).first()
        
        if not provedor:
            from core.support_account import fallback_provedor_for_niohub

            provedor = fallback_provedor_for_niohub(user)

        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=400)
        
        # 1. Queryset global do provedor para estatísticas (ignora filtros de equipe do agente)
        qs_ativas = Conversation.objects.filter(
            inbox__provedor=provedor
        ).exclude(
            status__in=['closed', 'encerrada', 'resolved', 'finalizada', 'closing']
        )
        
        # 2. Contagens explícitas e robustas (IA, Espera, Atendimento)
        conversas_abertas = qs_ativas.filter(assignee__isnull=False).count()
        conversas_pendentes = qs_ativas.filter(waiting_for_agent=True, assignee__isnull=True).count()
        conversas_ia = qs_ativas.filter(waiting_for_agent=False, assignee__isnull=True).count()
        
        # LOG PARA DEPURAÇÃO
        import logging
        logger_stats = logging.getLogger('conversations.dashboard_debug')
        logger_stats.info(f"--- DASHBOARD REFRESH (Provedor {provedor.id}) ---")
        logger_stats.info(f"IA: {conversas_ia} | Espera: {conversas_pendentes} | Atendimento: {conversas_abertas}")
        
        # 3. Métricas históricas
        provedor_filter = Q(inbox__provedor=provedor)
        
        # Buscar totais históricos (incluindo finalizadas)
        total_stats = Conversation.objects.filter(provedor_filter).aggregate(
            total=Count('id'),
            finalizadas_local=Count('id', filter=Q(status__in=['closed', 'encerrada', 'resolved', 'finalizada']))
        )
        
        total_conversas_local = total_stats['total'] or 0
        conversas_resolvidas_local = total_stats['finalizadas_local'] or 0
        
        conversas_em_andamento = conversas_abertas + conversas_pendentes + conversas_ia
        
        # Estatísticas de conversas - Supabase (encerradas)
        # OTIMIZAÇÃO: Usar count=exact para obter apenas o total sem buscar todos os registros
        conversas_resolvidas_supabase = 0
        try:
            import requests
            from django.conf import settings

            _supabase_timeout = getattr(settings, 'SUPABASE_REQUEST_TIMEOUT', 3)
            if not getattr(settings, 'SUPABASE_ENABLED', True):
                raise Exception("Supabase desabilitado (SUPABASE_ENABLED=False)")

            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'count=exact'
            }
            params = {
                'provedor_id': f'eq.{provedor.id}',
                'status': 'eq.closed',
                'select': 'id,provedor_id'
            }
            response = requests.get(url, headers=headers, params=params, timeout=_supabase_timeout)
            if response.status_code == 200:
                # Usar o header Content-Range se disponível (mais eficiente)
                content_range = response.headers.get('Content-Range', '')
                if content_range:
                    # Formato: "0-99/1234" - pegar o último número
                    try:
                        count_from_header = int(content_range.split('/')[-1])
                        # SEMPRE validar os dados retornados, mesmo que o header diga que há registros
                        data = response.json()
                        if isinstance(data, list):
                            # Validar que todos os registros pertencem ao provedor correto
                            valid_count = sum(1 for item in data if item.get('provedor_id') == provedor.id)
                            # Se valid_count for diferente do header, usar apenas o valid_count (mais seguro)
                            # Se o header retornar mais registros do que os validados, pode ser que o Supabase
                            # não esteja filtrando corretamente - então confiamos apenas nos dados validados
                            conversas_resolvidas_supabase = valid_count
                            if valid_count != count_from_header:
                                logger.warning(f"[DashboardStats] Supabase retornou {count_from_header} registros, mas apenas {valid_count} pertencem ao provedor {provedor.id}")
                        else:
                            conversas_resolvidas_supabase = 0
                    except (ValueError, IndexError):
                        # Fallback: contar itens retornados e validar
                        data = response.json()
                        if isinstance(data, list):
                            conversas_resolvidas_supabase = sum(1 for item in data if item.get('provedor_id') == provedor.id)
                        else:
                            conversas_resolvidas_supabase = 0
                else:
                    data = response.json()
                    if isinstance(data, list):
                        # Validar que todos os registros pertencem ao provedor correto
                        conversas_resolvidas_supabase = sum(1 for item in data if item.get('provedor_id') == provedor.id)
                    else:
                        conversas_resolvidas_supabase = 0
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.warning(f"Erro ao buscar conversas do Supabase para provedor {provedor.id}: {e}")
            conversas_resolvidas_supabase = 0
        
        from conversations.dashboard_resolution_stats import get_resolution_breakdown

        resolution_stats = get_resolution_breakdown(provedor)
        resolvidas_automacao_ia = resolution_stats['resolvidas_automacao_ia']
        resolvidas_automacao_local = resolution_stats['resolvidas_automacao_local']
        resolvidas_automacao_supabase = resolution_stats['resolvidas_automacao_supabase']
        resolvidas_encerrado_manual = resolution_stats['resolvidas_encerrado_manual']
        resolvidas_manual_local = resolution_stats['resolvidas_manual_local']
        resolvidas_manual_supabase = resolution_stats['resolvidas_manual_supabase']
        resolvidas_demais_encerramentos = resolution_stats['resolvidas_demais_encerramentos']
        
        # Combinar totais
        total_conversas = total_conversas_local + conversas_resolvidas_supabase
        conversas_resolvidas = conversas_resolvidas_local + conversas_resolvidas_supabase
        
        # Log para debug
        logger.info(
            f"[DashboardStats] Provedor {provedor.id} - Local: {conversas_resolvidas_local} resolvidas, "
            f"Supabase: {conversas_resolvidas_supabase} resolvidas, automação (IA/bot): {resolvidas_automacao_ia}, "
            f"manual (agente): {resolvidas_encerrado_manual}"
        )
        
        # Estatísticas de contatos únicos
        contatos_unicos = Contact.objects.filter(provedor=provedor).count()
        contatos_bloqueados_atender = Contact.objects.filter(provedor=provedor, bloqueado_atender=True).count()
        contatos_bloqueados_disparos = Contact.objects.filter(provedor=provedor, bloqueado_disparos=True).count()
        
        # Estatísticas de mensagens (últimos 30 dias)
        # OTIMIZAÇÃO: Usar select_related para evitar joins desnecessários
        data_30_dias_atras = timezone.now() - timedelta(days=30)
        mensagens_30_dias = Message.objects.filter(
            conversation__inbox__provedor=provedor,
            created_at__gte=data_30_dias_atras
        ).select_related('conversation__inbox').count()
        
        # Tempo de resposta (real via CSATFeedback.response_time_minutes)
        # Se não houver CSAT no período, retornamos 0min para não inventar valores.
        from django.db.models import Avg
        try:
            avg_response_minutes = (
                CSATFeedback.objects
                .filter(
                    provedor=provedor,
                    feedback_sent_at__gte=data_30_dias_atras,
                )
                .aggregate(avg=Avg('response_time_minutes'))
                .get('avg')
            ) or 0
        except Exception:
            avg_response_minutes = 0

        tempo_medio_resposta = f"{avg_response_minutes:.1f}min" if avg_response_minutes else "0min"
        # Campo historicamente usado como "primeira resposta" no frontend;
        # aqui mantemos o mesmo valor baseado em CSAT para permanecer 100% real.
        tempo_primeira_resposta = tempo_medio_resposta
        
        # Taxa de resolução
        if total_conversas > 0:
            taxa_resolucao = f"{int((conversas_resolvidas / total_conversas) * 100)}%"
        else:
            taxa_resolucao = "0%"
        
        # Satisfação média - usar dados reais do CSAT
        try:
            from .csat_service import CSATService
            csat_stats = CSATService.get_csat_stats(provedor, 30)
            satisfacao_media = f"{csat_stats.get('average_rating', 0.0):.1f}"
        except Exception as e:
            # Sem CSAT: não inventar valor, manter 0.0
            satisfacao_media = "0.0"
        
        # Estatísticas por canal - Contar CANAIS reais do provedor por tipo
        try:
            from core.models import Canal
            from collections import defaultdict
            
            # Buscar todos os canais do provedor
            canais_provedor = Canal.objects.filter(provedor=provedor)
            
            # Agrupar canais por tipo, normalizando tipos de WhatsApp
            canais_por_tipo = defaultdict(int)
            for canal in canais_provedor:
                tipo = canal.tipo
                # Normalizar tipos de WhatsApp para 'whatsapp'
                if tipo in ['whatsapp', 'whatsapp_session', 'whatsapp_oficial']:
                    tipo_normalizado = 'whatsapp'
                else:
                    tipo_normalizado = tipo
                canais_por_tipo[tipo_normalizado] += 1
            
            # Formatar para manter compatibilidade com o frontend (que espera 'inbox__channel_type')
            canais_stats = []
            for tipo, total in sorted(canais_por_tipo.items(), key=lambda x: x[1], reverse=True):
                canais_stats.append({
                    'inbox__channel_type': tipo,
                    'total': total
                })
                
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas de canais: {e}")
            canais_stats = []
        
        # Performance dos atendentes com dados reais
        # OTIMIZAÇÃO: Usar agregações ao invés de loops com queries individuais
        atendentes_performance = []
        try:
            from core.models import User
            
            # OTIMIZAÇÃO: Buscar usuários do provedor com prefetch
            # Ocultar niohub/superadmin da Performance (ações deles seguem em Atividade Recente)
            from core.support_account import exclude_hidden_provedor_users

            usuarios_provedor = exclude_hidden_provedor_users(
                User.objects.filter(
                    Q(provedores_admin=provedor)
                    | Q(user_type='agent', provedores_admin=provedor)
                ).only('id', 'first_name', 'last_name', 'username', 'email'),
                viewer=getattr(self.request, 'user', None),
            )
            
            # OTIMIZAÇÃO: Buscar todas as estatísticas de uma vez usando agregações
            from django.db.models import Prefetch
            usuarios_ids = list(usuarios_provedor.values_list('id', flat=True))
            
            if usuarios_ids:
                # Agregar conversas por atendente
                conversas_por_atendente = Conversation.objects.filter(
                    provedor_filter,
                    assignee_id__in=usuarios_ids
                ).values('assignee_id').annotate(
                    total=Count('id')
                )
                conversas_dict = {item['assignee_id']: item['total'] for item in conversas_por_atendente}
                
                # Agregar CSAT e tempo de resposta por atendente
                csat_por_atendente = CSATFeedback.objects.filter(
                    provedor=provedor,
                    conversation__assignee_id__in=usuarios_ids
                ).values('conversation__assignee_id').annotate(
                    avg_rating=Avg('rating_value'),
                    avg_response=Avg('response_time_minutes')
                )
                csat_dict = {item['conversation__assignee_id']: item['avg_rating'] for item in csat_por_atendente}
                response_time_dict = {item['conversation__assignee_id']: item['avg_response'] for item in csat_por_atendente}
                
                # Buscar emojis recentes (apenas para atendentes com conversas)
                for usuario in usuarios_provedor:
                    total_conversas_usuario = conversas_dict.get(usuario.id, 0)
                    # Inicializar variáveis antes de usar
                    csat_medio = 0
                    recent_emojis = []
                    
                    if total_conversas_usuario > 0:
                        csat_medio = csat_dict.get(usuario.id, 0) or 0
                        
                        # Buscar emojis recentes apenas se necessário
                        recent_emojis = list(
                            CSATFeedback.objects.filter(
                                provedor=provedor,
                                conversation__assignee=usuario
                            ).order_by('-feedback_sent_at')[:3].values_list('emoji_rating', flat=True)
                        )
                
                    atendentes_performance.append({
                        'id': usuario.id,
                        'name': f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username,
                        'email': usuario.email,
                        'conversations': total_conversas_usuario,
                        'csat': round(csat_medio, 1) if csat_medio > 0 else 0,
                        'responseTime': round(float(response_time_dict.get(usuario.id) or 0), 2),
                        'recent_emojis': recent_emojis
                    })
        except Exception as e:
            import logging
            # logger = logging.getLogger(__name__)
            logger.error(f"Erro ao calcular performance dos atendentes: {e}")

        # Fila de espera (SLA) — conversas aguardando atendente humano
        fila_espera = {
            'total': conversas_pendentes,
            'criticos': 0,
            'alerta': 0,
            'ok': 0,
            'sla_alerta_minutos': 5,
            'sla_critico_minutos': 15,
            'itens': [],
        }
        try:
            from django.db.models.functions import Coalesce

            agora = timezone.now()
            waiting_qs = (
                Conversation.objects.filter(
                    inbox__provedor=provedor,
                    waiting_for_agent=True,
                    assignee__isnull=True,
                )
                .exclude(status__in=['closed', 'encerrada', 'resolved', 'finalizada', 'closing'])
                .select_related('contact', 'inbox', 'team')
                .annotate(
                    wait_ref=Coalesce(
                        'last_user_message_at',
                        'last_message_at',
                        'updated_at',
                        'created_at',
                    )
                )
                .order_by('wait_ref')[:15]
            )
            itens = []
            criticos = alerta = ok = 0
            for conv in waiting_qs:
                ref = (
                    getattr(conv, 'wait_ref', None)
                    or conv.last_user_message_at
                    or conv.last_message_at
                    or conv.updated_at
                    or conv.created_at
                )
                waiting_seconds = max(0, int((agora - ref).total_seconds())) if ref else 0
                waiting_minutes = waiting_seconds // 60
                if waiting_minutes >= 15:
                    sla_level = 'critico'
                    criticos += 1
                elif waiting_minutes >= 5:
                    sla_level = 'alerta'
                    alerta += 1
                else:
                    sla_level = 'ok'
                    ok += 1
                contact_name = 'Cliente'
                if conv.contact:
                    contact_name = conv.contact.name or conv.contact.phone or 'Cliente'
                channel = getattr(conv.inbox, 'channel_type', None) or 'whatsapp'
                team_name = None
                if conv.team_id and conv.team:
                    team_name = conv.team.name
                else:
                    attrs = conv.additional_attributes or {}
                    assigned_team = attrs.get('assigned_team')
                    if isinstance(assigned_team, dict):
                        team_name = assigned_team.get('name') or assigned_team.get('nome')
                itens.append({
                    'id': conv.id,
                    'contact_name': contact_name,
                    'channel_type': channel,
                    'team_name': team_name,
                    'waiting_minutes': waiting_minutes,
                    'waiting_seconds': waiting_seconds,
                    'sla_level': sla_level,
                    'wait_since': ref.isoformat() if ref else None,
                })
            # Contagens de SLA no total da fila (não só nos 15 listados)
            all_waiting = (
                Conversation.objects.filter(
                    inbox__provedor=provedor,
                    waiting_for_agent=True,
                    assignee__isnull=True,
                )
                .exclude(status__in=['closed', 'encerrada', 'resolved', 'finalizada', 'closing'])
                .annotate(
                    wait_ref=Coalesce(
                        'last_user_message_at',
                        'last_message_at',
                        'updated_at',
                        'created_at',
                    )
                )
                .values_list('wait_ref', flat=True)
            )
            criticos = alerta = ok = 0
            for ref in all_waiting:
                if not ref:
                    ok += 1
                    continue
                mins = max(0, int((agora - ref).total_seconds())) // 60
                if mins >= 15:
                    criticos += 1
                elif mins >= 5:
                    alerta += 1
                else:
                    ok += 1
            fila_espera = {
                'total': criticos + alerta + ok,
                'criticos': criticos,
                'alerta': alerta,
                'ok': ok,
                'sla_alerta_minutos': 5,
                'sla_critico_minutos': 15,
                'itens': itens,
            }
        except Exception as fila_err:
            logger.error(f"Erro ao montar fila de espera SLA: {fila_err}", exc_info=True)
        
        return Response({
            'provedor_id': provedor.id,
            'total_conversas': total_conversas,
            'conversas_abertas': conversas_abertas,
            'conversas_pendentes': conversas_pendentes,
            'conversas_ia': conversas_ia,
            'conversas_resolvidas': conversas_resolvidas,
            'resolvidas_automacao_ia': resolvidas_automacao_ia,
            'resolvidas_encerrado_manual': resolvidas_encerrado_manual,
            'resolvidas_demais_encerramentos': resolvidas_demais_encerramentos,
            'bot_mode': getattr(provedor, 'bot_mode', 'ia'),
            'conversas_em_andamento': conversas_em_andamento,
            'contatos_unicos': contatos_unicos,
            'contatos_bloqueados_atender': contatos_bloqueados_atender,
            'contatos_bloqueados_disparos': contatos_bloqueados_disparos,
            'mensagens_30_dias': mensagens_30_dias,
            'tempo_medio_resposta': tempo_medio_resposta,
            'tempo_primeira_resposta': tempo_primeira_resposta,
            'taxa_resolucao': taxa_resolucao,
            'satisfacao_media': satisfacao_media,
            'canais': list(canais_stats),
            'atendentes': atendentes_performance,
            'fila_espera': fila_espera,
            'atividades': []
        })
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        return user.provedores_admin.first()


class DashboardResponseTimeHourlyView(APIView):
    """
    API para tempo de resposta por hora do dashboard
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        provedor = None

        # Se for superadmin, permitir passar provedor_id como parâmetro
        if user.user_type == 'superadmin':
            provedor_id_param = request.GET.get('provedor_id')
            if provedor_id_param:
                try:
                    provedor_id = int(provedor_id_param)
                    provedor = Provedor.objects.filter(id=provedor_id).first()
                    if not provedor:
                        return Response({'error': 'Provedor não encontrado'}, status=400)
                except (ValueError, TypeError):
                    return Response({'error': 'provedor_id inválido'}, status=400)

        # Se não foi passado como parâmetro, buscar do usuário
        if not provedor:
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
            if not provedor and hasattr(user, 'provedor') and user.provedor:
                provedor = user.provedor
            if not provedor:
                provedor = Provedor.objects.filter(admins=user).first()

        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=400)

        now = timezone.now()
        start_dt = now - timedelta(hours=24)

        from django.db.models import Avg
        from django.db.models.functions import ExtractHour

        hours = list(range(24))
        response_times = [0] * 24

        qs = (
            CSATFeedback.objects
            .filter(
                provedor=provedor,
                feedback_sent_at__gte=start_dt,
                feedback_sent_at__lte=now,
            )
            .annotate(hour=ExtractHour('feedback_sent_at'))
            .values('hour')
            .annotate(avg_response=Avg('response_time_minutes'))
            .order_by('hour')
        )

        for row in qs:
            h = int(row.get('hour', 0))
            avg_response = row.get('avg_response') or 0
            if 0 <= h < 24:
                response_times[h] = round(avg_response, 2)

        avg_all = (
            CSATFeedback.objects
            .filter(
                provedor=provedor,
                feedback_sent_at__gte=start_dt,
                feedback_sent_at__lte=now,
            )
            .aggregate(avg=Avg('response_time_minutes'))
            .get('avg') or 0
        )

        return Response({
            'hours': hours,
            'response_times': response_times,
            'average': round(avg_all, 2),
        })


class ConversationAnalysisView(APIView):
    """
    API para análise detalhada de conversas por provedor
    Retorna estatísticas filtradas por período com isolamento por provedor
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        import logging
        from datetime import datetime, timedelta
        from django.db.models import Count, Q, Avg
        
        user = request.user
        provedor = None
        
        # Se for superadmin, permitir passar provedor_id como parâmetro
        if user.user_type == 'superadmin':
            provedor_id_param = request.GET.get('provedor_id')
            if provedor_id_param:
                try:
                    provedor_id = int(provedor_id_param)
                    provedor = Provedor.objects.filter(id=provedor_id).first()
                    if not provedor:
                        return Response(
                            {'error': 'Provedor não encontrado'}, 
                            status=400
                        )
                except (ValueError, TypeError):
                    return Response(
                        {'error': 'provedor_id inválido'}, 
                        status=400
                    )
        
        # Se não foi passado como parâmetro, buscar do usuário
        if not provedor:
            # Tentar por provedor_id primeiro
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor = Provedor.objects.filter(id=user.provedor_id).first()
            
            # Se não encontrou, tentar por relacionamento direto
            if not provedor and hasattr(user, 'provedor') and user.provedor:
                provedor = user.provedor
            
            # Se ainda não encontrou, tentar por admins
            if not provedor:
                provedor = Provedor.objects.filter(admins=user).first()
        
        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=400)
        
        # Parâmetros de filtro: intervalo explícito (calendário) ou presets (period)
        from datetime import time as dtime

        start_param = request.GET.get('start_date')
        end_param = request.GET.get('end_date')

        if start_param and end_param:
            try:
                start_d = datetime.strptime(start_param, '%Y-%m-%d').date()
                end_d = datetime.strptime(end_param, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Use start_date e end_date no formato YYYY-MM-DD'}, status=400)
            if start_d > end_d:
                return Response({'error': 'Data inicial não pode ser maior que a final'}, status=400)
            if (end_d - start_d).days > 366:
                return Response({'error': 'Intervalo máximo: 366 dias'}, status=400)
            period = 'custom'
        else:
            period = request.GET.get('period', 'week')
            today_d = timezone.localdate()
            if period == 'today':
                start_d = end_d = today_d
            elif period == 'week':
                end_d = today_d
                start_d = end_d - timedelta(days=6)
            elif period == 'month':
                end_d = today_d
                start_d = end_d - timedelta(days=29)
            elif period == 'quarter':
                end_d = today_d
                start_d = end_d - timedelta(days=89)
            else:
                end_d = today_d
                start_d = end_d - timedelta(days=6)
                period = 'week'

        start_dt = timezone.make_aware(datetime.combine(start_d, dtime.min))
        end_dt = timezone.make_aware(datetime.combine(end_d, dtime.max))

        base_filter = (
            Q(inbox__provedor=provedor)
            & Q(created_at__date__gte=start_d)
            & Q(created_at__date__lte=end_d)
        )

        total_conversations_local = Conversation.objects.filter(base_filter).count()
        total_conversations_supabase = self._get_total_conversations_from_supabase(provedor.id, start_dt, end_dt)
        total_conversations = total_conversations_local + total_conversations_supabase

        conversations_by_day = self._get_conversations_by_day(provedor, start_d, end_d, start_dt, end_dt)
        channel_distribution = self._get_channel_distribution(provedor, start_d, end_d, start_dt, end_dt)

        # Summary: tudo calculado com dados reais (sem valores fixos/“mock”).
        active_agents = (
            Conversation.objects
            .filter(base_filter)
            .exclude(assignee__isnull=True)
            .values('assignee_id')
            .distinct()
            .count()
        )

        csat_window = CSATFeedback.objects.filter(
            provedor=provedor,
            feedback_sent_at__gte=start_dt,
            feedback_sent_at__lte=end_dt,
        )

        avg_response_minutes = csat_window.aggregate(avg=Avg('response_time_minutes')).get('avg') or 0
        avg_rating = csat_window.aggregate(avg=Avg('rating_value')).get('avg') or 0

        data = {
            'period': period,
            'date_range': {
                'start': start_d.strftime('%Y-%m-%d'),
                'end': end_d.strftime('%Y-%m-%d')
            },
            'summary': {
                'totalConversations': total_conversations,
                'avgResponseTime': f"{avg_response_minutes:.1f}min" if avg_response_minutes else "0min",
                'activeAgents': active_agents,
                'satisfactionRate': f"{avg_rating:.1f}",
            },
            'conversationsByDay': conversations_by_day,
            'channelDistribution': channel_distribution,
            'provedor': provedor.nome
        }
        
        return Response(data)
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        return user.provedores_admin.first()
    
    def _get_conversations_by_day(self, provedor, start_d, end_d, start_dt, end_dt):
        """Conversas por dia — contagem total de atendimentos (abertas ou não) no intervalo."""
        from django.db.models import Count, Q
        from datetime import timedelta
        from collections import defaultdict

        conversations_by_day_local = Conversation.objects.filter(
            inbox__provedor=provedor,
            created_at__date__gte=start_d,
            created_at__date__lte=end_d,
        ).extra(
            select={'date': 'DATE(conversations_conversation.created_at)'}
        ).values('date').annotate(
            conversations=Count('id'),
            resolved=Count('id', filter=Q(status__in=['resolved', 'closed']))
        ).order_by('date')

        conversations_by_day_supabase = self._get_conversations_by_day_from_supabase(
            provedor.id, start_dt, end_dt
        )

        combined_data = defaultdict(lambda: {'conversations': 0, 'resolved': 0})

        def normalize_date(date_value):
            if isinstance(date_value, str):
                return date_value
            elif hasattr(date_value, 'strftime'):
                return date_value.strftime('%Y-%m-%d')
            return str(date_value)

        for item in conversations_by_day_local:
            date_str = normalize_date(item['date'])
            combined_data[date_str]['conversations'] += item['conversations']
            combined_data[date_str]['resolved'] += item['resolved']

        for item in conversations_by_day_supabase:
            date_str = normalize_date(item['date'])
            combined_data[date_str]['conversations'] += item['conversations']
            combined_data[date_str]['resolved'] += item['resolved']

        lookup = dict(combined_data)
        formatted_data = []
        d = start_d
        while d <= end_d:
            key = d.strftime('%Y-%m-%d')
            row = lookup.get(key, {'conversations': 0, 'resolved': 0})
            formatted_data.append({
                'date': d.strftime('%d/%m'),
                'conversations': row['conversations'],
                'resolved': row['resolved'],
            })
            d += timedelta(days=1)
        return formatted_data

    def _get_channel_distribution(self, provedor, start_d, end_d, start_dt, end_dt):
        """Distribuição de conversas por canal (PostgreSQL + Supabase)"""
        from django.db.models import Count
        from collections import defaultdict

        channel_stats_local = Conversation.objects.filter(
            inbox__provedor=provedor,
            created_at__date__gte=start_d,
            created_at__date__lte=end_d,
        ).values('inbox__channel_type').annotate(
            count=Count('id')
        ).order_by('-count')

        channel_stats_supabase = self._get_channel_distribution_from_supabase(
            provedor.id, start_dt, end_dt
        )
        
        # Combinar dados
        combined_stats = defaultdict(int)
        
        # Adicionar dados do PostgreSQL
        for item in channel_stats_local:
            channel_type = item['inbox__channel_type']
            combined_stats[channel_type] += item['count']
        
        # Adicionar dados do Supabase
        for item in channel_stats_supabase:
            channel_type = item.get('channel_type') or item.get('inbox__channel_type')
            if channel_type:
                combined_stats[channel_type] += item['count']
        
        # Converter para lista
        channel_stats = [
            {'inbox__channel_type': channel_type, 'count': count}
            for channel_type, count in sorted(combined_stats.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Mapear nomes e cores dos canais
        channel_colors = {
            'whatsapp': '#10b981',
            'telegram': '#06b6d4',
            'email': '#f59e0b',
            'webchat': '#8b5cf6',
            'facebook': '#1877f2',
            'instagram': '#e4405f'
        }
        
        channel_names = {
            'whatsapp': 'WhatsApp',
            'whatsapp_session': 'WhatsApp QR',
            'whatsapp_oficial': 'WhatsApp Oficial',
            'telegram': 'Telegram',
            'email': 'Email',
            'webchat': 'Chat Web',
            'facebook': 'Facebook',
            'instagram': 'Instagram'
        }
        
        formatted_data = []
        for item in channel_stats:
            channel_type = item['inbox__channel_type']
            pretty_name = channel_names.get(channel_type)
            if not pretty_name:
                pretty_name = str(channel_type).replace('_', ' ').title() if channel_type else 'Canal'
            formatted_data.append({
                'name': pretty_name,
                'value': item['count'],
                'color': channel_colors.get(channel_type, '#94a3b8')
            })
        
        return formatted_data
    
    def _get_total_conversations_from_supabase(self, provedor_id, start_date, end_date):
        """Busca total de conversas do Supabase no período"""
        try:
            import requests
            from django.conf import settings

            _t = getattr(settings, 'SUPABASE_REQUEST_TIMEOUT', 3)
            if not getattr(settings, 'SUPABASE_ENABLED', True):
                return 0

            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'count=exact'
            }
            params = [
                ('provedor_id', f'eq.{provedor_id}'),
                ('created_at', f'gte.{start_date.isoformat()}'),
                ('created_at', f'lte.{end_date.isoformat()}'),
                ('select', 'id'),
            ]
            response = requests.get(url, headers=headers, params=params, timeout=_t)
            
            if response.status_code == 200:
                # Contar registros retornados
                data = response.json()
                return len(data) if isinstance(data, list) else 0
            
            return 0
        except Exception as e:
            logger.warning(f"Erro ao buscar conversas do Supabase: {e}")
            return 0
    
    def _get_conversations_by_day_from_supabase(self, provedor_id, start_date, end_date):
        """Busca conversas por dia do Supabase"""
        try:
            import requests
            from django.conf import settings
            from datetime import datetime
            from collections import defaultdict

            _t = getattr(settings, 'SUPABASE_REQUEST_TIMEOUT', 3)
            if not getattr(settings, 'SUPABASE_ENABLED', True):
                return []

            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json'
            }
            params = [
                ('provedor_id', f'eq.{provedor_id}'),
                ('created_at', f'gte.{start_date.isoformat()}'),
                ('created_at', f'lte.{end_date.isoformat()}'),
                ('select', 'id,created_at,status'),
            ]
            response = requests.get(url, headers=headers, params=params, timeout=_t)
            
            if response.status_code == 200:
                conversations = response.json()
                if not isinstance(conversations, list):
                    return []
                
                # Agrupar por dia
                by_day = defaultdict(lambda: {'conversations': 0, 'resolved': 0})
                
                for conv in conversations:
                    created_at_str = conv.get('created_at')
                    if created_at_str:
                        try:
                            # Parsear data (formato ISO)
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            date_str = created_at.date().strftime('%Y-%m-%d')
                            
                            by_day[date_str]['conversations'] += 1
                            
                            # Se status é closed, contar como resolvida
                            if conv.get('status') in ['closed', 'resolved']:
                                by_day[date_str]['resolved'] += 1
                        except Exception:
                            continue
                
                # Converter para lista
                return [
                    {'date': date, 'conversations': data['conversations'], 'resolved': data['resolved']}
                    for date, data in sorted(by_day.items())
                ]
            
            return []
        except Exception as e:
            logger.warning(f"Erro ao buscar conversas por dia do Supabase: {e}")
            return []
    
    def _get_channel_distribution_from_supabase(self, provedor_id, start_date, end_date):
        """Busca distribuição por canal do Supabase"""
        try:
            import requests
            from django.conf import settings
            from collections import defaultdict

            url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
            headers = {
                'apikey': settings.SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
                'Content-Type': 'application/json'
            }

            params = [
                ('provedor_id', f'eq.{provedor_id}'),
                ('created_at', f'gte.{start_date.isoformat()}'),
                ('created_at', f'lte.{end_date.isoformat()}'),
                ('select', 'id,inbox_id,additional_attributes'),
            ]
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                conversations = response.json()
                if not isinstance(conversations, list):
                    return []
                
                # Buscar channel_type dos additional_attributes ou buscar inbox do PostgreSQL
                channel_stats = defaultdict(int)
                
                for conv in conversations:
                    # Tentar obter channel_type do additional_attributes
                    additional_attrs = conv.get('additional_attributes', {})
                    if isinstance(additional_attrs, dict):
                        channel_type = additional_attrs.get('channel_type')
                        if channel_type:
                            channel_stats[channel_type] += 1
                    else:
                        # Se não tiver no additional_attributes, buscar do inbox no PostgreSQL
                        inbox_id = conv.get('inbox_id')
                        if inbox_id:
                            try:
                                from .models import Inbox
                                inbox = Inbox.objects.filter(id=inbox_id).first()
                                if inbox and inbox.channel_type:
                                    channel_stats[inbox.channel_type] += 1
                            except Exception:
                                pass
                
                # Converter para lista
                return [
                    {'channel_type': channel_type, 'count': count}
                    for channel_type, count in channel_stats.items()
                ]
            
            return []
        except Exception as e:
            logger.warning(f"Erro ao buscar distribuição por canal do Supabase: {e}")
            return []
