import requests
import logging
from django.conf import settings
from rest_framework import serializers
from .models import Canal, Provedor, Label, User, AuditLog, SystemConfig, Company, CompanyUser, MensagemSistema, ChatbotFlow, RespostaRapida, UserReminder, ProviderGalleryImage

logger = logging.getLogger(__name__)

class ProvedorSerializer(serializers.ModelSerializer):
    sgp_url = serializers.SerializerMethodField()
    sgp_token = serializers.SerializerMethodField()
    sgp_app = serializers.SerializerMethodField()
    whatsapp_url = serializers.SerializerMethodField()
    whatsapp_token = serializers.SerializerMethodField()
    meta_config_id = serializers.SerializerMethodField()
    meta_config_id_connect = serializers.SerializerMethodField()
    channels_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    conversations_count = serializers.SerializerMethodField()

    class Meta:
        model = Provedor
        fields = '__all__'

    def get_sgp_url(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('sgp_url', '')
    def get_sgp_token(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('sgp_token', '')
    def get_sgp_app(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('sgp_app', '')
    def get_whatsapp_url(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('whatsapp_url', '')
    def get_whatsapp_token(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('whatsapp_token', '')
    def get_meta_config_id(self, obj):
        ext = obj.integracoes_externas or {}
        return ext.get('meta_config_id', '1888449245359692')  # Fallback para config padrão (criar nova conta)
    
    def get_meta_config_id_connect(self, obj):
        """Config ID para conectar um app WhatsApp Business existente"""
        ext = obj.integracoes_externas or {}
        return ext.get('meta_config_id_connect', None)  # Se não configurado, retorna None
    
    def get_channels_count(self, obj):
        return obj.canais.filter(ativo=True).count()
    
    def get_users_count(self, obj):
        return obj.admins.count()
    
    def get_conversations_count(self, obj):
        # Contar conversas relacionadas aos inboxes deste provedor
        from conversations.models import Conversation
        return Conversation.objects.filter(inbox__provedor=obj).count()

    def create(self, validated_data):
        try:
            provedor = super().create(validated_data)
            return provedor
        except Exception as e:
            raise

    def update(self, instance, validated_data):
        ext = instance.integracoes_externas or {}
        
        ext.update({
            'sgp_url': self.initial_data.get('sgp_url', ext.get('sgp_url', '')),
            'sgp_token': self.initial_data.get('sgp_token', ext.get('sgp_token', '')),
            'sgp_app': self.initial_data.get('sgp_app', ext.get('sgp_app', '')),
            'whatsapp_url': self.initial_data.get('whatsapp_url', ext.get('whatsapp_url', '')),
            'whatsapp_token': self.initial_data.get('whatsapp_token', ext.get('whatsapp_token', '')),
            'meta_config_id': self.initial_data.get('meta_config_id', ext.get('meta_config_id', '')),
            'meta_config_id_connect': self.initial_data.get('meta_config_id_connect', ext.get('meta_config_id_connect', '')),
        })
        
        validated_data['integracoes_externas'] = ext
        return super().update(instance, validated_data)

class LabelSerializer(serializers.ModelSerializer):
    provedor = ProvedorSerializer(read_only=True)
    class Meta:
        model = Label
        fields = ['id', 'name', 'color', 'description', 'provedor', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class AuditLogSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    provedor = serializers.StringRelatedField()
    provedor_id = serializers.IntegerField(source='provedor.id', read_only=True)
    contact_photo = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'action', 'timestamp', 'ip_address', 'details',
            'provedor', 'provedor_id', 'conversation_id', 'contact_name', 'channel_type', 'csat_rating', 'contact_photo'
        ]
    
    def get_contact_photo(self, obj):
        """Buscar foto do perfil do contato para WhatsApp"""
        if not obj.contact_name or not obj.channel_type:
            return None
            
        # Só buscar foto para WhatsApp
        if obj.channel_type != 'whatsapp':
            return None
            
        try:
            from conversations.models import Contact
            from integrations.utils import fetch_whatsapp_profile_picture
            
            # Buscar contato pelo nome (fuzzy matching)
            contact_name_clean = obj.contact_name.lower().strip()
            contacts = Contact.objects.filter(
                provedor=obj.provedor
            ).exclude(phone__isnull=True).exclude(phone='')
            
            contact = None
            for c in contacts:
                if c.name and c.name.lower().strip() == contact_name_clean:
                    contact = c
                    break
                # Busca por similaridade
                elif c.name and contact_name_clean in c.name.lower():
                    contact = c
                    break
            
            if not contact:
                return None
            
            # Se já tem avatar salvo, usar ele
            if contact.avatar:
                try:
                    # Se avatar é uma string (URL), usar diretamente
                    if isinstance(contact.avatar, str):
                        avatar_url = contact.avatar
                    else:
                        # Se é um campo de arquivo, usar .url
                        avatar_url = contact.avatar.url
                    return avatar_url
                except Exception as e:
                    pass
            
            # Buscar foto via Uazapi
            if contact.phone and obj.provedor:
                provedor = obj.provedor
                if hasattr(provedor, 'integracoes_externas') and provedor.integracoes_externas:
                    integration = provedor.integracoes_externas
                    if isinstance(integration, dict):
                        whatsapp_url = integration.get('whatsapp_url')
                        whatsapp_token = integration.get('whatsapp_token')
                        instance_id = integration.get('instance_id')
                        
                        if whatsapp_url and whatsapp_token and instance_id:
                            profile_pic_url = fetch_whatsapp_profile_picture(
                                phone=contact.phone,
                                instance_name=instance_id,
                                integration_type='uazapi',
                                provedor=provedor
                            )
                            
                            if profile_pic_url:
                                return profile_pic_url
            
            return None
            
        except Exception as e:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Formatação removida - campo conversation_duration não existe mais
        
        # Formatar ação para exibição em português
        action_display = dict(AuditLog.ACTION_CHOICES).get(instance.action, instance.action)
        data['action_display'] = action_display
        
        return data


class ConversationAuditSerializer(serializers.ModelSerializer):
    """Serializer para auditoria completa de conversas"""
    contact = serializers.SerializerMethodField()
    inbox = serializers.SerializerMethodField()
    assigned_agent = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    audit_logs = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = None  # Será definido dinamicamente
        fields = [
            'id', 'contact', 'inbox', 'assigned_agent', 'status', 'status_display',
            'messages', 'audit_logs', 'duration', 'message_count',
            'created_at', 'updated_at', 'last_message_at'
        ]
    
    def get_contact(self, obj):
        if hasattr(obj, 'contact') and obj.contact:
            avatar_url = None
            try:
                if obj.contact.avatar:
                    avatar_url = obj.contact.avatar.url
            except:
                pass
            
            return {
                'id': obj.contact.id,
                'name': obj.contact.name,
                'phone': obj.contact.phone,
                'email': obj.contact.email,
                'avatar': avatar_url
            }
        return None
    
    def get_inbox(self, obj):
        if hasattr(obj, 'inbox') and obj.inbox:
            return {
                'id': obj.inbox.id,
                'name': obj.inbox.name,
                'channel_type': obj.inbox.channel_type,
                'provedor': obj.inbox.provedor.nome if obj.inbox.provedor else None
            }
        return None
    
    def get_assigned_agent(self, obj):
        if hasattr(obj, 'assignee') and obj.assignee:
            return {
                'id': obj.assignee.id,
                'username': obj.assignee.username,
                'first_name': obj.assignee.first_name,
                'last_name': obj.assignee.last_name,
                'user_type': obj.assignee.user_type
            }
        return None
    
    def get_messages(self, obj):
        if hasattr(obj, 'messages') and obj.messages.exists():
            messages = []
            for msg in obj.messages.all()[:50]:  # Limitar a 50 mensagens
                message_data = {
                    'id': msg.id,
                    'content': msg.content,
                    'message_type': msg.message_type,
                    'is_from_customer': msg.is_from_customer,
                    'created_at': msg.created_at
                }
                
                # Adicionar campos opcionais se existirem
                if hasattr(msg, 'media_type'):
                    message_data['media_type'] = msg.media_type
                if hasattr(msg, 'file_url'):
                    message_data['file_url'] = msg.file_url
                
                messages.append(message_data)
            return messages
        return []
    
    def get_audit_logs(self, obj):
        from .models import AuditLog
        logs = AuditLog.objects.filter(
            conversation_id=obj.id,
            action__in=['conversation_closed_agent', 'conversation_closed_ai', 'conversation_transferred', 'conversation_assigned']
        ).order_by('-timestamp')
        
        return [{
            'id': log.id,
            'action': log.action,
            'action_display': dict(AuditLog.ACTION_CHOICES).get(log.action, log.action),
            'user': log.user.username if log.user else None,
            'timestamp': log.timestamp,
            'details': log.details,
            'resolution_type': log.resolution_type
        } for log in logs]
    
    def get_duration(self, obj):
        if obj.created_at and obj.updated_at:
            duration = obj.updated_at - obj.created_at
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        return "0m"
    
    def get_message_count(self, obj):
        if hasattr(obj, 'messages'):
            return obj.messages.count()
        return 0
    
    def get_status_display(self, obj):
        status_map = {
            'open': 'Em Andamento',
            'pending': 'Pendente',
            'closed': 'Encerrada',
            'resolved': 'Resolvida',
            'transferred': 'Transferida'
        }
        return status_map.get(obj.status, obj.status)

class SystemConfigSerializer(serializers.ModelSerializer):
    # Campos esperados pelo frontend
    site_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    default_language = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    timezone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    allow_public_signup = serializers.BooleanField(required=False, default=False)
    max_users_per_company = serializers.IntegerField(required=False, default=10)
    google_api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    openai_transcription_api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    asaas_access_token = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    asaas_webhook_auth_token = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    asaas_sandbox = serializers.BooleanField(required=False, default=True)
    billing_channel_enabled = serializers.BooleanField(required=False, default=False)
    billing_whatsapp_token = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_whatsapp_phone_number_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_whatsapp_waba_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_days_before_due = serializers.IntegerField(required=False, default=3)
    billing_reminder_due_offsets = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=120
    )
    billing_run_window_minutes = serializers.IntegerField(
        required=False, default=0, min_value=0, max_value=45
    )
    billing_provedor_auto_block_enabled = serializers.BooleanField(required=False, default=True)
    billing_provedor_block_min_days_late = serializers.IntegerField(
        required=False, default=4, min_value=0, max_value=365
    )
    billing_run_time = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_run_days = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_template_due_soon = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_template_overdue = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_whatsapp_use_template = serializers.BooleanField(required=False, default=True)
    billing_whatsapp_template_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    billing_whatsapp_template_language = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = SystemConfig
        fields = [
            'id', 'key', 'value', 'description', 'is_active', 
            'created_at', 'updated_at', 'sgp_app', 'sgp_token', 
            'sgp_url', 'google_api_key', 'openai_transcription_api_key',
            'asaas_access_token', 'asaas_webhook_auth_token', 'asaas_sandbox',
            'billing_channel_enabled', 'billing_whatsapp_token', 'billing_whatsapp_phone_number_id',
            'billing_whatsapp_waba_id', 'billing_days_before_due',             'billing_reminder_due_offsets',
            'billing_run_window_minutes',
            'billing_provedor_auto_block_enabled',
            'billing_provedor_block_min_days_late',
            'billing_run_time',
            'billing_run_days', 'billing_template_due_soon', 'billing_template_overdue',
            'billing_whatsapp_use_template', 'billing_whatsapp_template_name', 'billing_whatsapp_template_language',
            # Campos do frontend
            'site_name', 'contact_email', 'default_language', 'timezone',
            'allow_public_signup', 'max_users_per_company', 'google_api_key', 'openai_transcription_api_key',
            'asaas_access_token', 'asaas_webhook_auth_token', 'asaas_sandbox',
            'billing_channel_enabled', 'billing_whatsapp_token', 'billing_whatsapp_phone_number_id',
            'billing_whatsapp_waba_id', 'billing_days_before_due', 'billing_reminder_due_offsets',
            'billing_run_window_minutes',
            'billing_provedor_auto_block_enabled',
            'billing_provedor_block_min_days_late',
            'billing_run_time',
            'billing_run_days', 'billing_template_due_soon', 'billing_template_overdue',
            'billing_whatsapp_use_template', 'billing_whatsapp_template_name', 'billing_whatsapp_template_language',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Converte o modelo para o formato esperado pelo frontend"""
        try:
            # Se não há dados, retornar valores padrão
            if not instance or not hasattr(instance, 'id') or not instance.id:
                return {
                    'id': 1,
                    'key': 'system_config',
                    'value': '{}',
                    'description': 'Configurações gerais do sistema',
                    'is_active': True,
                    'site_name': 'Nio Chat',
                    'contact_email': '',
                    'default_language': 'pt-br',
                    'timezone': 'America/Sao_Paulo',
                    'allow_public_signup': False,
                    'max_users_per_company': 10,
                    'google_api_key': '',
                    'openai_transcription_api_key': '',
                    'sgp_app': '',
                    'sgp_token': '',
                    'sgp_url': '',
                    'asaas_access_token': '',
                    'asaas_webhook_auth_token': '',
                    'asaas_sandbox': True,
                    'billing_channel_enabled': False,
                    'billing_whatsapp_token': '',
                    'billing_whatsapp_phone_number_id': '',
                    'billing_whatsapp_waba_id': '',
                    'billing_days_before_due': 3,
                    'billing_reminder_due_offsets': '',
                    'billing_run_window_minutes': 0,
                    'billing_provedor_auto_block_enabled': True,
                    'billing_provedor_block_min_days_late': 4,
                    'billing_run_time': '09:00',
                    'billing_run_days': '0,1,2,3,4,5,6',
                    'billing_template_due_soon': 'Olá {{nome}}, sua fatura de {{valor}} vence em {{vencimento}} (ID: {{fatura_id}}).',
                    'billing_template_overdue': 'Olá {{nome}}, sua fatura {{fatura_id}} de {{valor}} venceu em {{vencimento}}. Evite bloqueio realizando o pagamento.',
                    'billing_whatsapp_use_template': True,
                    'billing_whatsapp_template_name': 'cobranca_order',
                    'billing_whatsapp_template_language': 'pt_BR',
                    'created_at': None,
                    'updated_at': None
                }
            
            # Chamar super().to_representation() com tratamento de erro
            try:
                data = super().to_representation(instance)
            except Exception as e:
                logger.error(f"Erro ao serializar SystemConfig: {e}", exc_info=True)
                # Retornar dados básicos se a serialização falhar
                data = {
                    'id': instance.id,
                    'key': getattr(instance, 'key', 'system_config'),
                    'value': getattr(instance, 'value', '{}'),
                    'description': getattr(instance, 'description', ''),
                    'is_active': getattr(instance, 'is_active', True),
                    'created_at': instance.created_at.isoformat() if hasattr(instance, 'created_at') and instance.created_at else None,
                    'updated_at': instance.updated_at.isoformat() if hasattr(instance, 'updated_at') and instance.updated_at else None,
                }
            
            # Extrair valores do campo 'value' se estiver em formato JSON
            import json
            try:
                if instance.value:
                    value_data = json.loads(instance.value)
                    if isinstance(value_data, dict):
                        data.update(value_data)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(f"Erro ao parsear JSON do campo value: {e}")
                pass
            
            # Se os campos não existem, usar valores padrão
            data.setdefault('site_name', 'Nio Chat')
            data.setdefault('contact_email', '')
            data.setdefault('default_language', 'pt-br')
            data.setdefault('timezone', 'America/Sao_Paulo')
            data.setdefault('allow_public_signup', False)
            data.setdefault('max_users_per_company', 10)
            
            # IMPORTANTE: google_api_key deve vir do campo direto do modelo, não do JSON value
            if instance and hasattr(instance, 'google_api_key'):
                data['google_api_key'] = instance.google_api_key or ''
            else:
                data.setdefault('google_api_key', '')
            
            # IMPORTANTE: openai_transcription_api_key deve vir do campo direto do modelo, não do JSON value
            if instance and hasattr(instance, 'openai_transcription_api_key'):
                data['openai_transcription_api_key'] = instance.openai_transcription_api_key or ''
            else:
                data.setdefault('openai_transcription_api_key', '')
            
            # IMPORTANTE: asaas_access_token e asaas_sandbox devem vir do modelo
            if instance and hasattr(instance, 'asaas_access_token'):
                data['asaas_access_token'] = instance.asaas_access_token or ''
            else:
                data.setdefault('asaas_access_token', '')

            if instance and hasattr(instance, 'asaas_webhook_auth_token'):
                data['asaas_webhook_auth_token'] = instance.asaas_webhook_auth_token or ''
            else:
                data.setdefault('asaas_webhook_auth_token', '')
                
            if instance and hasattr(instance, 'asaas_sandbox'):
                data['asaas_sandbox'] = instance.asaas_sandbox
            else:
                data.setdefault('asaas_sandbox', True)

            # Configuracoes do canal de cobranca exclusivo do superadmin
            data.setdefault('billing_channel_enabled', getattr(instance, 'billing_channel_enabled', False))
            data.setdefault('billing_whatsapp_token', getattr(instance, 'billing_whatsapp_token', '') or '')
            data.setdefault('billing_whatsapp_phone_number_id', getattr(instance, 'billing_whatsapp_phone_number_id', '') or '')
            data.setdefault('billing_whatsapp_waba_id', getattr(instance, 'billing_whatsapp_waba_id', '') or '')
            data.setdefault('billing_days_before_due', getattr(instance, 'billing_days_before_due', 3))
            data.setdefault(
                'billing_reminder_due_offsets',
                getattr(instance, 'billing_reminder_due_offsets', '') or '',
            )
            data.setdefault(
                'billing_run_window_minutes',
                getattr(instance, 'billing_run_window_minutes', 0),
            )
            data.setdefault(
                'billing_provedor_auto_block_enabled',
                getattr(instance, 'billing_provedor_auto_block_enabled', True),
            )
            data.setdefault(
                'billing_provedor_block_min_days_late',
                getattr(instance, 'billing_provedor_block_min_days_late', 4),
            )
            data.setdefault('billing_run_time', getattr(instance, 'billing_run_time', '09:00') or '09:00')
            data.setdefault('billing_run_days', getattr(instance, 'billing_run_days', '0,1,2,3,4,5,6') or '0,1,2,3,4,5,6')
            data.setdefault('billing_template_due_soon', getattr(instance, 'billing_template_due_soon', '') or '')
            data.setdefault('billing_template_overdue', getattr(instance, 'billing_template_overdue', '') or '')
            data.setdefault('billing_whatsapp_use_template', getattr(instance, 'billing_whatsapp_use_template', True))
            data.setdefault('billing_whatsapp_template_name', getattr(instance, 'billing_whatsapp_template_name', '') or 'cobranca_order')
            data.setdefault('billing_whatsapp_template_language', getattr(instance, 'billing_whatsapp_template_language', '') or 'pt_BR')
            
            # Garantir que campos obrigatórios existam
            data.setdefault('sgp_app', getattr(instance, 'sgp_app', '') or '')
            data.setdefault('sgp_token', getattr(instance, 'sgp_token', '') or '')
            data.setdefault('sgp_url', getattr(instance, 'sgp_url', '') or '')
            data.setdefault('key', getattr(instance, 'key', 'system_config'))
            data.setdefault('value', getattr(instance, 'value', '{}'))
            data.setdefault('description', getattr(instance, 'description', ''))
            data.setdefault('is_active', getattr(instance, 'is_active', True))
            
            return data
        except Exception as e:
            logger.error(f"Erro crítico em to_representation do SystemConfig: {e}", exc_info=True)
            # Retornar estrutura mínima em caso de erro crítico
            return {
                'id': getattr(instance, 'id', 1) if instance else 1,
                'key': 'system_config',
                'value': '{}',
                'description': 'Configurações gerais do sistema',
                'is_active': True,
                'site_name': 'Nio Chat',
                'contact_email': '',
                'default_language': 'pt-br',
                'timezone': 'America/Sao_Paulo',
                'allow_public_signup': False,
                'max_users_per_company': 10,
                'google_api_key': '',
                'openai_transcription_api_key': '',
                'sgp_app': '',
                'sgp_token': '',
                'sgp_url': ''
            }
    
    def update(self, instance, validated_data):
        """Atualiza a instância com os dados validados"""
        # Log para debug
        logger.info(f"[SERIALIZER] Dados recebidos no update: {list(validated_data.keys())}")
        logger.info(f"[SERIALIZER] google_api_key em validated_data: {'google_api_key' in validated_data}")
        
        # IMPORTANTE: Verificar também em initial_data (dados brutos do request)
        if hasattr(self, 'initial_data') and 'google_api_key' in self.initial_data:
            raw_key = self.initial_data.get('google_api_key')
            logger.info(f"[SERIALIZER] google_api_key em initial_data: {raw_key[:30] if raw_key else None}... (tamanho: {len(raw_key) if raw_key else 0})")
        
        # Extrair google_api_key ANTES de processar outros campos
        # Este campo deve ser salvo DIRETAMENTE no modelo, não no JSON value
        google_api_key = validated_data.pop('google_api_key', None)
        
        # Se não está em validated_data, tentar buscar de initial_data
        if google_api_key is None and hasattr(self, 'initial_data'):
            google_api_key = self.initial_data.get('google_api_key')
            logger.info(f"[SERIALIZER] Buscando google_api_key de initial_data: {google_api_key[:30] if google_api_key else None}...")
        
        # Tratar string vazia como None (para não salvar string vazia)
        if google_api_key == '':
            google_api_key = None
            logger.info("[SERIALIZER] google_api_key era string vazia, convertido para None")
        
        logger.info(f"[SERIALIZER] google_api_key final: {google_api_key[:30] if google_api_key else None}... (tamanho: {len(google_api_key) if google_api_key else 0})")
        
        # Extrair openai_transcription_api_key ANTES de processar outros campos
        # Este campo deve ser salvo DIRETAMENTE no modelo, não no JSON value
        openai_transcription_api_key = validated_data.pop('openai_transcription_api_key', None)
        
        # Se não está em validated_data, tentar buscar de initial_data
        if openai_transcription_api_key is None and hasattr(self, 'initial_data'):
            openai_transcription_api_key = self.initial_data.get('openai_transcription_api_key')
            logger.info(f"[SERIALIZER] Buscando openai_transcription_api_key de initial_data: {openai_transcription_api_key[:30] if openai_transcription_api_key else None}...")
        
        # Tratar string vazia como None (para não salvar string vazia)
        if openai_transcription_api_key == '':
            openai_transcription_api_key = None
            logger.info("[SERIALIZER] openai_transcription_api_key era string vazia, convertido para None")
        
        logger.info(f"[SERIALIZER] openai_transcription_api_key final: {openai_transcription_api_key[:30] if openai_transcription_api_key else None}... (tamanho: {len(openai_transcription_api_key) if openai_transcription_api_key else 0})")
        
        # Extrair asaas_access_token e asaas_sandbox
        asaas_access_token = validated_data.pop('asaas_access_token', None)
        asaas_webhook_auth_token = validated_data.pop('asaas_webhook_auth_token', None)
        asaas_sandbox = validated_data.pop('asaas_sandbox', None)
        
        # Se asaas_access_token não está em validated_data, tentar buscar de initial_data
        if asaas_access_token is None and hasattr(self, 'initial_data'):
            asaas_access_token = self.initial_data.get('asaas_access_token')

        if asaas_webhook_auth_token is None and hasattr(self, 'initial_data'):
            asaas_webhook_auth_token = self.initial_data.get('asaas_webhook_auth_token')
            
        # Tratar string vazia como None
        if asaas_access_token == '':
            asaas_access_token = None

        if asaas_webhook_auth_token == '':
            asaas_webhook_auth_token = None
            
        # Extrair campos do frontend
        frontend_fields = {
            'site_name': validated_data.pop('site_name', None),
            'contact_email': validated_data.pop('contact_email', None),
            'default_language': validated_data.pop('default_language', None),
            'timezone': validated_data.pop('timezone', None),
            'allow_public_signup': validated_data.pop('allow_public_signup', None),
            'max_users_per_company': validated_data.pop('max_users_per_company', None),
        }
        
        # Remover None values
        frontend_fields = {k: v for k, v in frontend_fields.items() if v is not None}
        
        # Se há campos do frontend, salvar no campo 'value' como JSON
        if frontend_fields:
            import json
            try:
                # Tentar carregar JSON existente
                existing_value = json.loads(instance.value) if instance.value else {}
            except:
                existing_value = {}
            
            # Atualizar com novos valores
            existing_value.update(frontend_fields)
            validated_data['value'] = json.dumps(existing_value)
        
        # Salvar google_api_key DIRETAMENTE no campo do modelo (CRÍTICO)
        # IMPORTANTE: Sempre tentar salvar, mesmo se for None (para permitir limpar o campo)
        if google_api_key is not None:
            logger.info(f"[SERIALIZER] Salvando google_api_key no modelo: {google_api_key[:30]}... (tamanho: {len(google_api_key)})")
            validated_data['google_api_key'] = google_api_key
            # Garantir que o campo será atualizado diretamente na instância também
            instance.google_api_key = google_api_key
        else:
            logger.warning("[SERIALIZER] google_api_key é None - não será atualizado")

        # Salvar asaas_access_token e asaas_sandbox no modelo
        if asaas_access_token is not None:
            validated_data['asaas_access_token'] = asaas_access_token
            instance.asaas_access_token = asaas_access_token

        if asaas_webhook_auth_token is not None:
            validated_data['asaas_webhook_auth_token'] = asaas_webhook_auth_token
            instance.asaas_webhook_auth_token = asaas_webhook_auth_token
            
        if asaas_sandbox is not None:
            validated_data['asaas_sandbox'] = asaas_sandbox
            instance.asaas_sandbox = asaas_sandbox

        billing_fields = [
            'billing_channel_enabled',
            'billing_whatsapp_token',
            'billing_whatsapp_phone_number_id',
            'billing_whatsapp_waba_id',
            'billing_days_before_due',
            'billing_reminder_due_offsets',
            'billing_run_window_minutes',
            'billing_provedor_auto_block_enabled',
            'billing_provedor_block_min_days_late',
            'billing_run_time',
            'billing_run_days',
            'billing_template_due_soon',
            'billing_template_overdue',
            'billing_whatsapp_use_template',
            'billing_whatsapp_template_name',
            'billing_whatsapp_template_language',
        ]
        for field in billing_fields:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        
        # Salvar openai_transcription_api_key DIRETAMENTE no campo do modelo (CRÍTICO)
        # IMPORTANTE: Sempre tentar salvar, mesmo se for None (para permitir limpar o campo)
        if openai_transcription_api_key is not None:
            logger.info(f"[SERIALIZER] Salvando openai_transcription_api_key no modelo: {openai_transcription_api_key[:30]}... (tamanho: {len(openai_transcription_api_key)})")
            validated_data['openai_transcription_api_key'] = openai_transcription_api_key
            # Garantir que o campo será atualizado diretamente na instância também
            instance.openai_transcription_api_key = openai_transcription_api_key
        else:
            logger.warning("[SERIALIZER] openai_transcription_api_key é None - não será atualizado")
        
        # NÃO definir key se já existe (evitar UNIQUE constraint)
        # O key já deve estar definido na instância existente
        if 'key' in validated_data and instance.key:
            validated_data.pop('key')
        
        # Salvar usando super().update()
        updated_instance = super().update(instance, validated_data)
        
        # Garantir que google_api_key foi salvo (fazer save explícito se necessário)
        if google_api_key is not None and updated_instance.google_api_key != google_api_key:
            logger.warning(f"[SERIALIZER] google_api_key não foi salvo corretamente, forçando save...")
            updated_instance.google_api_key = google_api_key
            updated_instance.save(update_fields=['google_api_key'])
            logger.info(f"[SERIALIZER] google_api_key salvo com sucesso após save explícito")
        
        # Garantir que openai_transcription_api_key foi salvo (fazer save explícito se necessário)
        if openai_transcription_api_key is not None and updated_instance.openai_transcription_api_key != openai_transcription_api_key:
            logger.warning(f"[SERIALIZER] openai_transcription_api_key não foi salvo corretamente, forçando save...")
            updated_instance.openai_transcription_api_key = openai_transcription_api_key
            updated_instance.save(update_fields=['openai_transcription_api_key'])
            logger.info(f"[SERIALIZER] openai_transcription_api_key salvo com sucesso após save explícito")
        
        return updated_instance

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'slug', 'logo', 'description', 'website', 
            'email', 'phone', 'address', 'is_active', 'created_at', 'updated_at'
        ]

class UserSerializer(serializers.ModelSerializer):
    provedor_id = serializers.SerializerMethodField()
    write_provedor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    provedores_admin = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'user_type',
            'avatar', 'phone', 'is_online', 'last_seen', 'created_at', 'updated_at',
            'is_active', 'last_login', 'password', 'permissions',
            'provedor_id', 'write_provedor_id', 'provedores_admin', 'session_timeout', 'language',
            'assignment_message', 'sound_notifications_enabled',
            'new_message_sound', 'new_message_sound_volume',
            'new_conversation_sound', 'new_conversation_sound_volume',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_login']
    
    def get_provedor_id(self, obj):
        return obj.provedor_id
    
    def get_provedores_admin(self, obj):
        """Retorna informações completas sobre os provedores do usuário"""
        try:
            provedores = obj.provedores_admin.all()
            return [
                {
                    'id': p.id,
                    'nome': p.nome,
                    'is_active': p.is_active
                }
                for p in provedores
            ]
        except Exception as e:
            # Tratamento de erro caso haja problema com o relacionamento ou colunas faltantes
            return []
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        provedor_id = validated_data.pop('write_provedor_id', None)
        
        # Atualizar campos básicos
        user = super().update(instance, validated_data)

        # Atualização de senha se fornecida
        if password:
            user.set_password(password)
            user.save()

        # Reatribuição de provedor (ForeignKey)
        if provedor_id is not None:
            try:
                provedor_id_int = int(provedor_id)
                provedor = Provedor.objects.get(id=provedor_id_int)
                # Atualizar o campo ForeignKey direto
                user.provedor = provedor
                user.save(update_fields=['provedor'])
                
                # Manter o ManyToMany para compatibilidade se necessário (legado)
                if hasattr(user, 'provedores_admin'):
                    user.provedores_admin.clear()
                    user.provedores_admin.add(provedor)
            except (Provedor.DoesNotExist, ValueError, TypeError) as e:
                logger.error(f"Erro ao associar provedor {provedor_id} ao usuário {instance.id}: {str(e)}")
            except Exception as e:
                logger.error(f"Erro inesperado ao associar provedor ao usuário {instance.id}: {str(e)}")
        
        return user


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer específico para criação de usuários com seleção de provedor"""
    password = serializers.CharField(write_only=True, required=True)
    provedor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'user_type',
            'avatar', 'phone', 'is_active', 'permissions', 'password', 'provedor_id'
        ]
    
    def create(self, validated_data):
        provedor_id = validated_data.pop('provedor_id', None)
        password = validated_data.pop('password', None)
        
        # Criar usuário
        user = super().create(validated_data)
        
        # Definir senha
        if password:
            user.set_password(password)
            user.save()
        
        # Associar ao provedor se especificado
        if provedor_id:
            try:
                provedor = Provedor.objects.get(id=provedor_id)
                user.provedor = provedor
                user.save(update_fields=['provedor'])
                
                # Manter ManyToMany para compatibilidade legada
                provedor.admins.add(user)
            except Provedor.DoesNotExist:
                pass  # Silenciosamente ignora se o provedor não existir
        
        return user

class CompanyUserSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    company = CompanySerializer(read_only=True)
    
    class Meta:
        model = CompanyUser
        fields = ['id', 'user', 'company', 'role', 'is_active', 'joined_at']
        read_only_fields = ['id', 'joined_at']

class CompanyUserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyUser
        fields = ['id', 'user', 'company', 'role', 'is_active', 'joined_at']
        read_only_fields = ['id', 'joined_at']

class CanalSerializer(serializers.ModelSerializer):
    provedor = ProvedorSerializer(read_only=True)
    state = serializers.SerializerMethodField()
    profile_pic = serializers.SerializerMethodField()
    telegramInfo = serializers.SerializerMethodField()
    telegramStatus = serializers.SerializerMethodField()
    
    class Meta:
        model = Canal
        fields = [
            'id', 'tipo', 'nome', 'ativo', 'provedor', 'ia_ativa',
            'api_id', 'api_hash', 'app_title', 'short_name',  # Telegram
            'verification_code', 'phone_number',  # Telegram/WhatsApp
            'waba_id', 'phone_number_id', 'token', 'status',  # WhatsApp Oficial
            'created_at', 'updated_at',
            'state',  # Status de conexão
            'profile_pic',  # Foto de perfil
            'telegramInfo',  # Dados de perfil do Telegram
            'telegramStatus',  # Status específico do Telegram
            'dados_extras',  # Dados extras (instance_id, etc)
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'provedor']

    def get_state(self, obj):
        # Evolution API removida
        
        # Para sessão WhatsApp (Uazapi) - usar Uazapi
        # whatsapp_session é o valor do banco de dados para sessões Uazapi
        if obj.tipo == 'whatsapp_session' and obj.nome:
            try:
                from .uazapi_client import UazapiClient
                provedor = obj.provedor
                
                if provedor and provedor.integracoes_externas:
                    token = provedor.integracoes_externas.get('whatsapp_token')
                    uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                    
                    if token and uazapi_url:
                        client = UazapiClient(uazapi_url, token)
                        status_result = client.get_instance_status(obj.nome)
                        
                        # A resposta pode ter instance dentro ou no nível raiz
                        instance_data = status_result.get('instance', {})
                        if not instance_data and isinstance(status_result, dict):
                            # Se não tem 'instance', pode estar no nível raiz
                            instance_data = status_result
                        
                        # Buscar status de múltiplas formas
                        status = instance_data.get('status') if instance_data else None
                        if not status:
                            # Tentar buscar do nível raiz também
                            status = status_result.get('status')
                        
                        # Verificar também connected e loggedIn
                        connected = status_result.get('connected', False) or instance_data.get('connected', False)
                        loggedIn = status_result.get('loggedIn', False) or instance_data.get('loggedIn', False)
                        
                        if connected and loggedIn:
                            return 'connected'
                        elif status:
                            return status.lower()
                        else:
                            return 'disconnected'
            except Exception as e:
                return 'disconnected'
        
        # Para WhatsApp Oficial - usar status do canal ou verificar se tem credenciais
        elif obj.tipo == 'whatsapp_oficial':
            # Se tem token e phone_number_id, considerar conectado
            if obj.token and obj.phone_number_id:
                # Usar o status do canal se disponível, senão 'connected'
                return obj.status if obj.status else 'connected'
            else:
                return 'disconnected'
        
        # Para Telegram - verificar se tem sessão E dados do usuário salvos
        elif obj.tipo == 'telegram' and obj.nome:
            try:
                # Verificar se tem sessão E dados do usuário salvos (significa que conectou com sucesso)
                if obj.dados_extras and 'telegram_session' in obj.dados_extras and 'telegram_user' in obj.dados_extras:
                    logger.debug(f"Canal Telegram {obj.nome}: CONECTADO (sessão e usuário salvos)")
                    return 'connected'
                elif obj.dados_extras and 'telegram_session' in obj.dados_extras:
                    logger.debug(f"Canal Telegram {obj.nome}: CONNECTING (apenas sessão, sem usuário)")
                    return 'connecting'
                else:
                    logger.debug(f"Canal Telegram {obj.nome}: DESCONECTADO (sem sessão)")
                    return 'disconnected'
                    
            except Exception as e:
                logger.warning(f"Erro ao verificar status Telegram para {obj.nome}: {e}")
                return 'disconnected'
        
        return None

    def get_profile_pic(self, obj):
        # Para WhatsApp Oficial, buscar de dados_extras primeiro
        if obj.tipo == "whatsapp_oficial":
            # Tentar buscar profilePicUrl (formato usado pelo frontend)
            if obj.dados_extras and obj.dados_extras.get('profilePicUrl'):
                return obj.dados_extras.get('profilePicUrl')
            # Tentar buscar profile_picture_url (formato da API da Meta)
            if obj.dados_extras and obj.dados_extras.get('profile_picture_url'):
                return obj.dados_extras.get('profile_picture_url')
        
        # Resto do código existente...
        # Para Telegram - primeiro verificar se já está salvo em dados_extras
        if obj.tipo == 'telegram' and obj.nome:
            try:
                # Primeiro tentar buscar de dados_extras (mais rápido e já salvo)
                if obj.dados_extras and 'telegram_photo' in obj.dados_extras:
                    photo = obj.dados_extras.get('telegram_photo')
                    if photo:
                        logger.debug(f"Foto de perfil Telegram encontrada em dados_extras para {obj.nome}")
                        return photo
                
                # Se não encontrou em dados_extras, buscar via MTProto (mais lento)
                if obj.dados_extras and 'telegram_session' in obj.dados_extras:
                    from .telegram_service import telegram_service
                    import asyncio
                    
                    # Executar busca de foto assíncrona
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(telegram_service.get_profile_photo(obj))
                        if result.get('success') and result.get('photo_base64'):
                            # Retornar foto em base64 (data URL)
                            logger.debug(f"Foto de perfil Telegram buscada via MTProto para {obj.nome}")
                            return f"data:image/jpeg;base64,{result.get('photo_base64')}"
                    finally:
                        loop.close()
            except Exception as e:
                logger.warning(f"Erro ao buscar foto de perfil Telegram para {obj.nome}: {e}")
                pass
        
        # Evolution API removida
        
        # Para WhatsApp Oficial - buscar via Graph API (endpoint whatsapp_business_profile) e cachear em dados_extras
        if obj.tipo == 'whatsapp_oficial':
            try:
                # Se já está em dados_extras, retornar URL do proxy
                if obj.dados_extras and (obj.dados_extras.get('profile_picture_url') or obj.dados_extras.get('profilePicUrl')):
                    # Tentar obter request do context para construir URL absoluta
                    request = self.context.get('request') if hasattr(self, 'context') and self.context else None
                    if request:
                        proxy_url = request.build_absolute_uri(f'/api/whatsapp/profile-picture/proxy/?channel_id={obj.id}')
                    else:
                        # Fallback: usar configuração ou URL padrão
                        from django.conf import settings
                        api_base_url = getattr(settings, 'API_BASE_URL', None)
                        if not api_base_url:
                            # Tentar usar ALLOWED_HOSTS para construir URL
                            allowed_host = getattr(settings, 'ALLOWED_HOSTS', [])
                            if allowed_host and len(allowed_host) > 0:
                                host = allowed_host[0] if isinstance(allowed_host, list) else allowed_host.split(',')[0]
                                api_base_url = f"https://{host}" if not host.startswith('http') else host
                            else:
                                api_base_url = 'http://localhost:8010'
                        proxy_url = f"{api_base_url}/api/whatsapp/profile-picture/proxy/?channel_id={obj.id}"
                    return proxy_url

                # Se não está em cache, buscar via API usando phone_number_id
                if obj.token and obj.phone_number_id:
                    from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
                    url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{obj.phone_number_id}/whatsapp_business_profile"
                    params = {
                        "fields": "profile_picture_url,about,description",
                        "access_token": obj.token
                    }
                    resp = requests.get(url, params=params, timeout=8)
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        if data and len(data) > 0:
                            profile = data[0]
                            profile_pic = profile.get("profile_picture_url")
                            if profile_pic:
                                # Cachear URL original em ambos os formatos para compatibilidade
                                extras = obj.dados_extras or {}
                                extras["profile_picture_url"] = profile_pic
                                extras["profilePicUrl"] = profile_pic
                                extras["business_profile"] = profile
                                obj.dados_extras = extras
                                obj.save(update_fields=["dados_extras"])
                                
                                # Retornar URL do proxy para evitar erro 403 (URLs da Meta requerem autenticação)
                                # O proxy busca a imagem usando o token e serve diretamente
                                request = self.context.get('request') if hasattr(self, 'context') and self.context else None
                                if request:
                                    proxy_url = request.build_absolute_uri(f'/api/whatsapp/profile-picture/proxy/?channel_id={obj.id}')
                                else:
                                    # Fallback: usar configuração ou URL padrão
                                    from django.conf import settings
                                    api_base_url = getattr(settings, 'API_BASE_URL', None)
                                    if not api_base_url:
                                        allowed_host = getattr(settings, 'ALLOWED_HOSTS', [])
                                        if allowed_host and len(allowed_host) > 0:
                                            host = allowed_host[0] if isinstance(allowed_host, list) else allowed_host.split(',')[0]
                                            api_base_url = f"https://{host}" if not host.startswith('http') else host
                                        else:
                                            api_base_url = 'http://localhost:8010'
                                    proxy_url = f"{api_base_url}/api/whatsapp/profile-picture/proxy/?channel_id={obj.id}"
                                return proxy_url
            except Exception as e:
                logger.warning(f"Erro ao buscar foto de perfil WhatsApp Oficial: {e}")
                pass
        
        # Para sessão WhatsApp (Uazapi) - usar Uazapi
        # whatsapp_session é o valor do banco de dados para sessões Uazapi
        if obj.tipo == 'whatsapp_session' and obj.nome:
            try:
                from .uazapi_client import UazapiClient
                provedor = obj.provedor
                
                if provedor and provedor.integracoes_externas:
                    token = provedor.integracoes_externas.get('whatsapp_token')
                    uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                    
                    if token and uazapi_url:
                        client = UazapiClient(uazapi_url, token)
                        # Usar get_instance_info para obter foto de perfil
                        info_result = client.get_instance_info(obj.nome)
                        
                        # A resposta pode ter instance no nível raiz ou dentro de 'instance'
                        instance_data = info_result.get('instance', {})
                        if not instance_data and isinstance(info_result, dict):
                            # Se não tem 'instance', pode estar no nível raiz
                            instance_data = info_result
                        
                        # Buscar profilePicUrl de múltiplas fontes
                        profile_pic = None
                        if instance_data:
                            profile_pic = instance_data.get('profilePicUrl')
                        if not profile_pic:
                            # Tentar buscar do nível raiz também
                            profile_pic = info_result.get('profilePicUrl')
                        
                        if profile_pic:
                            return profile_pic
            except Exception as e:
                pass
        
        # Para Telegram - buscar foto via MTProto
        elif obj.tipo == 'telegram' and obj.nome:
            try:
                from .telegram_service import telegram_service
                import asyncio
                
                # Executar busca de foto assíncrona
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(telegram_service.get_profile_photo(obj))
                    if result.get('success') and result.get('photo_url'):
                        return result.get('photo_url')
                finally:
                    loop.close()
            except Exception as e:
                pass

    def get_telegramInfo(self, obj):
        if obj.tipo != 'telegram':
            return None
        try:
            user_info = (obj.dados_extras or {}).get('telegram_user') or {}
            photo_data_url = (obj.dados_extras or {}).get('telegram_photo')
            profile_pic_base64 = None
            if photo_data_url and isinstance(photo_data_url, str) and photo_data_url.startswith('data:image'):
                try:
                    profile_pic_base64 = photo_data_url.split(',')[1]
                except Exception:
                    profile_pic_base64 = None
            result = {
                'id': user_info.get('id') or user_info.get('telegram_id'),
                'telegram_id': user_info.get('telegram_id') or user_info.get('id'),
                'username': user_info.get('username'),
                'first_name': user_info.get('first_name') or user_info.get('name'),
                'last_name': user_info.get('last_name'),
                'phone': user_info.get('phone'),
                'name': user_info.get('name') or user_info.get('first_name'),
                'profile_pic': photo_data_url,
                'profile_photo': photo_data_url,
                'profile_pic_base64': profile_pic_base64,
            }
            return result
        except Exception as e:
            logger.warning(f"Erro ao montar telegramInfo para {obj.nome}: {e}")
            return None

    def get_telegramStatus(self, obj):
        if obj.tipo != 'telegram':
            return None
        try:
            status = self.get_state(obj) or 'disconnected'
            return { 'status': status }
        except Exception:
            return { 'status': 'disconnected' }
        
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Adicionar status da sessão WhatsApp (Uazapi) se for do tipo whatsapp_session
        # whatsapp_session é o valor do banco de dados para sessões Uazapi
        if instance.tipo == 'whatsapp_session' and instance.nome:
            try:
                from .uazapi_client import UazapiClient
                provedor = instance.provedor
                
                if provedor and provedor.integracoes_externas:
                    token = provedor.integracoes_externas.get('whatsapp_token')
                    uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                    
                    if token and uazapi_url:
                        client = UazapiClient(uazapi_url, token)
                        # Buscar informações completas da instância (incluindo foto)
                        try:
                            info_result = client.get_instance_info(instance.nome)
                            # Também buscar status para informações de conexão
                            status_result = client.get_instance_status(instance.nome)
                            
                            # Mesclar as informações (info tem prioridade para foto e nome)
                            merged_data = {}
                            if isinstance(status_result, dict):
                                merged_data.update(status_result)
                            if isinstance(info_result, dict):
                                # Atualizar com dados do /instance/info (tem foto e nome)
                                merged_data.update(info_result)
                            
                            data['sessionStatus'] = merged_data if merged_data else {'error': 'Resposta inválida da UazAPI'}
                        except Exception as e:
                            # Se /instance/info falhar, tentar apenas com /instance/status
                            try:
                                status_result = client.get_instance_status(instance.nome)
                                if isinstance(status_result, dict):
                                    data['sessionStatus'] = status_result
                                else:
                                    data['sessionStatus'] = {'error': 'Resposta inválida da UazAPI'}
                            except:
                                data['sessionStatus'] = None
            except Exception as e:
                data['sessionStatus'] = None
        
        # Adicionar informações do Telegram se for do tipo telegram
        if instance.tipo == 'telegram' and instance.nome:
            try:
                # Recarregar o canal do banco para garantir dados atualizados
                instance.refresh_from_db()
                
                # Buscar informações do banco de dados (salvas durante verificação)
                telegram_user = None
                telegram_photo = None
                
                # Verificar se dados_extras existe e tem conteúdo
                if instance.dados_extras:
                    if not isinstance(instance.dados_extras, dict):
                        logger.warning(f"dados_extras não é dict para {instance.nome}, tipo: {type(instance.dados_extras)}")
                    else:
                        telegram_user = instance.dados_extras.get('telegram_user')
                        telegram_photo = instance.dados_extras.get('telegram_photo')
                        
                        logger.info(f"Canal Telegram: {instance.nome} (ID: {instance.id})")
                        logger.info(f"  - dados_extras existe: Sim ({len(instance.dados_extras)} keys)")
                        logger.info(f"  - Keys em dados_extras: {list(instance.dados_extras.keys())}")
                        logger.info(f"  - telegram_user existe: {bool(telegram_user)}")
                        logger.info(f"  - telegram_photo existe: {bool(telegram_photo)}")
                        
                        # Se telegram_user existe mas não é dict, tentar converter
                        if telegram_user and not isinstance(telegram_user, dict):
                            logger.warning(f"telegram_user não é dict, tipo: {type(telegram_user)}")
                            telegram_user = None
                
                # Se não encontrou dados em dados_extras, buscar diretamente do Telegram (igual ao script)
                if not telegram_user:
                    session_string = None
                    if instance.dados_extras and isinstance(instance.dados_extras, dict):
                        session_string = instance.dados_extras.get('telegram_session')
                    
                    if session_string and instance.api_id and instance.api_hash:
                        logger.info(f"telegram_user não encontrado em dados_extras, buscando dados diretamente do Telegram...")
                        try:
                            from core.telegram_service import telegram_service
                            import asyncio
                            
                            # Executar busca de dados assíncrona (igual ao script quick_status + show_user_info)
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                status_result = loop.run_until_complete(telegram_service.get_status(instance))
                                if status_result.get('success') and status_result.get('connected'):
                                    user_data = status_result.get('user', {})
                                    telegram_user = {
                                        'id': user_data.get('id'),
                                        'telegram_id': user_data.get('id'),
                                        'username': user_data.get('username'),
                                        'first_name': user_data.get('first_name'),
                                        'last_name': user_data.get('last_name'),
                                        'phone': user_data.get('phone'),
                                        'name': user_data.get('first_name')
                                    }
                                    telegram_photo = status_result.get('profile_photo_url')
                                    logger.info(f"Dados obtidos diretamente do Telegram: {telegram_user.get('first_name')}")
                            finally:
                                loop.close()
                        except Exception as e:
                            logger.warning(f"Erro ao buscar dados do Telegram: {e}", exc_info=True)
                
                if telegram_user and isinstance(telegram_user, dict):
                    logger.info(f"  - telegram_user keys: {list(telegram_user.keys())}")
                    logger.info(f"  - telegram_user content: {telegram_user}")
                    
                    # Buscar profile_pic diretamente de dados_extras primeiro (mais rápido)
                    profile_pic_value = telegram_photo
                    # Se não encontrou em telegram_photo, tentar buscar do método get_profile_pic
                    if not profile_pic_value:
                        logger.info(f"  - Buscando foto via get_profile_pic...")
                        profile_pic_value = self.get_profile_pic(instance)
                    
                    # Obter state atualizado
                    current_state = data.get('state') or self.get_state(instance)
                    logger.info(f"  - State determinado: {current_state}")
                    
                    # Construir telegramInfo seguindo a estrutura do script de referência
                    telegram_info = {
                        'telegram_id': telegram_user.get('id') or telegram_user.get('telegram_id'),
                        'id': telegram_user.get('id') or telegram_user.get('telegram_id'),
                        'username': telegram_user.get('username'),
                        'first_name': telegram_user.get('first_name'),
                        'last_name': telegram_user.get('last_name'),
                        'phone': telegram_user.get('phone'),
                        'name': telegram_user.get('name') or telegram_user.get('first_name'),  # Campo 'name' para compatibilidade
                        'profile_pic': profile_pic_value,
                        'profile_pic_base64': profile_pic_value,  # Para compatibilidade
                        'profile_photo': profile_pic_value,  # Campo adicional para compatibilidade
                        'status': 'connected' if current_state == 'connected' else 'disconnected',
                        'connected': current_state == 'connected'
                    }
                    data['telegramInfo'] = telegram_info
                    logger.info(f"telegramInfo criado para {instance.nome}:")
                    logger.info(f"  - Nome completo: {telegram_user.get('first_name')} {telegram_user.get('last_name') or ''}")
                    logger.info(f"  - Username: @{telegram_user.get('username')}")
                    logger.info(f"  - ID: {telegram_info.get('telegram_id')}")
                    logger.info(f"  - Phone: {telegram_user.get('phone')}")
                    logger.info(f"  - State: {current_state}")
                    logger.info(f"  - Profile Pic: {'Presente' if profile_pic_value else 'Ausente'}")
                else:
                    data['telegramInfo'] = None
                    logger.warning(f"Não foi possível obter dados do usuário Telegram para {instance.nome}")
            except Exception as e:
                logger.error(f"Erro ao buscar informações do Telegram para {instance.nome}: {str(e)}", exc_info=True)
                data['telegramInfo'] = None
        
        return data
    
    def create(self, validated_data):
        """Cria canal e envia código de verificação se for Telegram"""
        instance = super().create(validated_data)
        
        # Para WhatsApp Oficial, definir nome padrão se não fornecido (após criar para ter acesso ao provedor)
        if instance.tipo == 'whatsapp_oficial' and not instance.nome:
            if instance.provedor:
                instance.nome = f"WhatsApp Oficial - {instance.provedor.nome}"
            else:
                instance.nome = "WhatsApp Oficial"
            instance.save()
        
        # Se for Telegram e tiver credenciais, enviar código de verificação
        if instance.tipo == 'telegram' and instance.api_id and instance.api_hash and instance.phone_number:
            self._telegram_code_result = self._send_telegram_code(instance)
        else:
            self._telegram_code_result = None
        
        return instance
    
    def update(self, instance, validated_data):
        """Atualiza canal e envia código de verificação se for Telegram"""
        instance = super().update(instance, validated_data)
        
        # Se for Telegram e tiver credenciais, enviar código de verificação
        if instance.tipo == 'telegram' and instance.api_id and instance.api_hash and instance.phone_number:
            self._telegram_code_result = self._send_telegram_code(instance)
        else:
            self._telegram_code_result = None
        
        return instance
    
    def _send_telegram_code(self, canal):
        """Envia código de verificação do Telegram"""
        import asyncio
        from .telegram_service import telegram_service
        
        try:
            # Executar de forma síncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(telegram_service.send_code(canal))
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Erro ao enviar código Telegram: {e}")
            return {'success': False, 'error': str(e)}


class MensagemSistemaSerializer(serializers.ModelSerializer):
    provedores_detalhados = serializers.SerializerMethodField()
    visualizacoes_detalhadas = serializers.SerializerMethodField()
    
    class Meta:
        model = MensagemSistema
        fields = [
            'id', 'assunto', 'mensagem', 'tipo', 'provedores', 
            'provedores_count', 'visualizacoes', 'visualizacoes_count',
            'provedores_detalhados', 'visualizacoes_detalhadas',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'provedores_count', 'visualizacoes', 'visualizacoes_count', 'created_at', 'updated_at']
    
    def get_provedores_detalhados(self, obj):
        """Retorna lista de provedores com nomes"""
        from .models import Provedor
        provedores = []
        for provedor_id in obj.provedores:
            try:
                provedor = Provedor.objects.get(id=provedor_id)
                provedores.append({
                    'id': provedor.id,
                    'nome': provedor.nome,
                    'visualizado': str(provedor.id) in obj.visualizacoes
                })
            except Provedor.DoesNotExist:
                provedores.append({
                    'id': provedor_id,
                    'nome': f'Provedor {provedor_id} (não encontrado)',
                    'visualizado': False
                })
        return provedores
    
    def get_visualizacoes_detalhadas(self, obj):
        """Retorna detalhes das visualizações com nomes dos usuários e provedores"""
        from .models import User, Provedor
        visualizacoes = []
        
        if not obj.visualizacoes:
            return []
            
        for key, dados in obj.visualizacoes.items():
            try:
                # No formato novo, a chave é o user_id
                user_id = int(key)
                user = User.objects.filter(id=user_id).first()
                
                # Coletar dados básicos do JSON (conforme views.py)
                # views.py usa: user_id, user_name, visualized_at
                timestamp = dados.get('visualized_at') or dados.get('timestamp')
                user_name = dados.get('user_name') or dados.get('username') or 'Usuário não identificado'
                
                # Tentar obter o provedor para contexto
                provedor_nome = ''
                if user:
                    # Se o usuário é um admin de provedor
                    p_admin = user.provedores_admin.first() if hasattr(user, 'provedores_admin') else None
                    if p_admin:
                        provedor_nome = p_admin.nome
                    elif hasattr(user, 'provedor') and user.provedor:
                        provedor_nome = user.provedor.nome
                
                visualizacoes.append({
                    'user_id': user_id,
                    'username': user_name,
                    'provedor_nome': provedor_nome,
                    'timestamp': timestamp
                })
            except (ValueError, TypeError):
                # Caso ocorra algum erro no parse do ID
                continue
                
        return visualizacoes
    
    def create(self, validated_data):
        # Calcula o número de provedores
        provedores = validated_data.get('provedores', [])
        validated_data['provedores_count'] = len(provedores)
        return super().create(validated_data)

class ChatbotFlowSerializer(serializers.ModelSerializer):
    canal_nome = serializers.SerializerMethodField()

    class Meta:
        model = ChatbotFlow
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_canal_nome(self, obj):
        return obj.canal.nome if obj.canal else None


class PlanoSerializer(serializers.ModelSerializer):
    class Meta:
        from core.models import Plano
        model = Plano
        fields = [
            'id', 'provedor', 'nome', 'descricao',
            'velocidade_download', 'velocidade_upload',
            'preco', 'ativo', 'ordem',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RespostaRapidaSerializer(serializers.ModelSerializer):
    criado_por_nome = serializers.SerializerMethodField()

    class Meta:
        model = RespostaRapida
        fields = ['id', 'provedor', 'titulo', 'conteudo', 'criado_por', 'criado_por_nome', 'created_at', 'updated_at']
        read_only_fields = ['id', 'criado_por', 'created_at', 'updated_at']
        extra_kwargs = {
            'provedor': {'required': False}
        }

    def get_criado_por_nome(self, obj):
        if obj.criado_por:
            return f"{obj.criado_por.first_name} {obj.criado_por.last_name}".strip() or obj.criado_por.username
        return None


class ProviderGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProviderGalleryImage
        fields = [
            'id', 'provedor', 'nome', 'imagem', 'image_url',
            'criado_por', 'created_by_name', 'ativo',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'criado_por', 'created_at', 'updated_at']
        extra_kwargs = {'provedor': {'required': False}}

    def get_image_url(self, obj):
        return f"/api/media/provider-gallery/{obj.id}/"

    def get_created_by_name(self, obj):
        if obj.criado_por:
            return obj.criado_por.get_full_name() or obj.criado_por.username
        return None


class UserReminderSerializer(serializers.ModelSerializer):
    contact_name = serializers.ReadOnlyField(source='contact.name')
    
    class Meta:
        model = UserReminder
        fields = [
            'id', 'user', 'contact', 'contact_name', 'message', 
            'scheduled_time', 'is_notified', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
