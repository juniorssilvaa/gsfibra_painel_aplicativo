from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()
from core.models import Provedor


class Contact(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, default='')
    email = models.EmailField(blank=True, null=True)
    avatar = models.URLField(blank=True, null=True, help_text="URL da foto do perfil do WhatsApp")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='contacts', null=True, blank=True)
    additional_attributes = models.JSONField(default=dict, blank=True)
    # Campos de bloqueio
    bloqueado_atender = models.BooleanField(default=False, verbose_name='Bloqueado para Atendimento', help_text='Se True, a IA não responderá mensagens deste contato')
    bloqueado_disparos = models.BooleanField(default=False, verbose_name='Bloqueado para Disparos', help_text='Se True, não será possível enviar disparos para este contato')

    def __str__(self):
        return f"{self.name} ({self.phone})"

    class Meta:
        unique_together = ['phone', 'provedor']


class Inbox(models.Model):
    name = models.CharField(max_length=255)
    channel_type = models.CharField(max_length=50)  # whatsapp, telegram, email, etc.
    channel_id = models.CharField(max_length=255, default='default')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='inboxes', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    additional_attributes = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.name} ({self.channel_type})"

    def get_canal_instance(self):
        """
        Retorna a instância real do modelo Canal vinculada a este Inbox.
        Tenta buscar pelo ID numérico armazenado em channel_id.
        """
        from core.models import Canal
        import logging
        logger = logging.getLogger(__name__)

        channel_id = self.channel_id
        
        # Tentar buscar pelo ID
        if channel_id and str(channel_id).isdigit():
            try:
                canal = Canal.objects.filter(id=int(channel_id), provedor=self.provedor).first()
                if canal:
                    return canal
            except (ValueError, TypeError):
                pass

        # Fallback seguro: NUNCA escolher "o primeiro canal ativo" quando existir mais de um.
        # Isso evita enviar mensagem pelo número errado (incidente crítico).
        tipo_map = {
            'whatsapp_oficial': 'whatsapp_oficial',
            # Muitos inboxes de WhatsApp Oficial foram salvos como "whatsapp"
            'whatsapp': 'whatsapp_oficial',
            'telegram': 'telegram',
            'app_mobile': 'app_mobile',
            'instagram': 'instagram',
        }
        tipo_canal = tipo_map.get(self.channel_type, self.channel_type)

        # 1) Tentar canal_id em additional_attributes (se existir)
        extra_canal_id = None
        try:
            extra_canal_id = (self.additional_attributes or {}).get("canal_id") or (self.additional_attributes or {}).get("channel_id")
        except Exception:
            extra_canal_id = None
        if extra_canal_id and str(extra_canal_id).isdigit():
            canal = Canal.objects.filter(id=int(extra_canal_id), provedor=self.provedor).first()
            if canal:
                logger.warning(f"[Inbox {self.id}] channel_id inválido='{channel_id}'. Usando canal_id de additional_attributes={extra_canal_id}.")
                return canal

        # 2) Tentar casar pelo nome do inbox: "WhatsApp - {canal.nome}" ou "{canal.nome}"
        inbox_name = (self.name or "").strip()
        name_guess = inbox_name
        if inbox_name.lower().startswith("whatsapp - "):
            name_guess = inbox_name[len("WhatsApp - "):].strip()
        if name_guess:
            canal = Canal.objects.filter(
                provedor=self.provedor,
                tipo=tipo_canal,
                ativo=True,
                nome=name_guess,
            ).first()
            if canal:
                logger.warning(f"[Inbox {self.id}] channel_id inválido='{channel_id}'. Usando fallback por nome '{name_guess}'.")
                return canal

        # 3) Se existir exatamente 1 canal ativo desse tipo, usar; se houver vários, falhar com segurança
        qs = Canal.objects.filter(provedor=self.provedor, tipo=tipo_canal, ativo=True)
        count = qs.count()
        if count == 1:
            canal = qs.first()
            logger.warning(
                f"[Inbox {self.id}] channel_id inválido='{channel_id}'. Usando único canal ativo do tipo '{tipo_canal}' (canal_id={canal.id})."
            )
            return canal

        logger.error(
            f"[Inbox {self.id}] Canal específico '{channel_id}' não encontrado e fallback ambíguo "
            f"(tipo='{tipo_canal}', ativos={count}). Abortando para evitar envio pelo número errado."
        )
        return None


class Conversation(models.Model):
    STATUS_CHOICES = [
        ('open', 'Aberta'),
        ('closed', 'Fechada'),
        ('pending', 'Pendente'),
        ('snoozed', 'Com IA'),
        ('closing', 'Encerrando'),  # Estado intermediário antes do encerramento definitivo
    ]
    
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='conversations')
    inbox = models.ForeignKey(Inbox, on_delete=models.CASCADE, related_name='conversations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_conversations')
    team = models.ForeignKey('Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations', verbose_name='Equipe')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_user_message_at = models.DateTimeField(null=True, blank=True, help_text='Timestamp da última mensagem recebida do cliente (para cálculo da janela de 24 horas)')
    closing_requested_at = models.DateTimeField(null=True, blank=True, help_text='Data/hora em que o encerramento foi solicitado (para janela de tolerância)')
    waiting_for_agent = models.BooleanField(default=False, help_text='Se True, a conversa aparecerá nas filas dos atendentes humanos. Se False, está sob controle do chatbot e oculta.')
    additional_attributes = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Conversa com {self.contact.name}"
    
    def is_closing_within_tolerance(self, tolerance_minutes=2):
        """
        Verifica se a conversa está em estado 'closing' e ainda dentro da janela de tolerância.
        
        Args:
            tolerance_minutes: Período de tolerância em minutos (padrão: 2 minutos)
            
        Returns:
            bool: True se está em closing e dentro da janela de tolerância, False caso contrário
        """
        if self.status != 'closing':
            return False
        
        if not self.closing_requested_at:
            # Se não tem timestamp, considerar como fora da tolerância (deve ser fechada)
            return False
        
        from django.utils import timezone
        from datetime import timedelta
        
        elapsed = timezone.now() - self.closing_requested_at
        return elapsed <= timedelta(minutes=tolerance_minutes)
    
    def reopen_from_closing(self):
        """
        Reabre uma conversa que estava em estado 'closing'.
        Cancela o encerramento e retorna ao estado 'open'.
        """
        if self.status == 'closing':
            self.status = 'open'
            self.closing_requested_at = None
            self.save(update_fields=['status', 'closing_requested_at'])
            return True
        return False

    def mark_panel_read(self):
        """Marca a conversa como lida no painel (zera badge de novas mensagens)."""
        from django.utils import timezone

        attrs = dict(self.additional_attributes or {})
        attrs['panel_last_read_at'] = timezone.now().isoformat()
        type(self).objects.filter(pk=self.pk).update(additional_attributes=attrs)
        self.additional_attributes = attrs
        return attrs['panel_last_read_at']

    def mark_assigned_at(self, when=None):
        """Registra o momento em que o contato foi atribuído a um atendente."""
        from django.utils import timezone

        attrs = dict(self.additional_attributes or {})
        attrs['assigned_at'] = (when or timezone.now()).isoformat()
        type(self).objects.filter(pk=self.pk).update(additional_attributes=attrs)
        self.additional_attributes = attrs
        return attrs['assigned_at']

    def clear_assigned_at(self):
        """Remove o timestamp de atribuição (ex.: transferência / retorno à fila)."""
        attrs = dict(self.additional_attributes or {})
        if 'assigned_at' not in attrs:
            return
        attrs.pop('assigned_at', None)
        type(self).objects.filter(pk=self.pk).update(additional_attributes=attrs)
        self.additional_attributes = attrs

    def compute_unread_count(self):
        """
        Conta mensagens do cliente posteriores ao último "visto" no painel.
        Sem panel_last_read_at, usa a última mensagem do atendente (ou created_at).
        """
        from django.utils.dateparse import parse_datetime

        if hasattr(self, 'unread_count_annotated') and self.unread_count_annotated is not None:
            return int(self.unread_count_annotated or 0)

        attrs = self.additional_attributes or {}
        since = None
        raw = attrs.get('panel_last_read_at')
        if raw:
            since = parse_datetime(raw) if isinstance(raw, str) else raw

        if since is None:
            last_agent = (
                self.messages.filter(is_from_customer=False)
                .only('created_at')
                .order_by('-created_at')
                .first()
            )
            since = last_agent.created_at if last_agent else self.created_at

        if since is None:
            return 0

        return self.messages.filter(
            is_from_customer=True,
            created_at__gt=since,
        ).count()
    
    def is_24h_window_open(self):
        """
        Verifica se a janela de 24 horas está aberta para envio de mensagens.
        
        Para WhatsApp Official, só é possível enviar mensagens de texto normais
        dentro de 24 horas após a última mensagem do cliente. Após isso, é necessário
        usar templates de mensagem.
        
        IMPORTANTE: SEMPRE busca a mensagem mais recente do cliente e usa o created_at
        real da mensagem. Não usa last_user_message_at para garantir precisão absoluta
        baseada no timestamp real de quando a mensagem foi enviada/recebida.
        
        Returns:
            bool: True se a janela está aberta (menos de 24 horas desde última mensagem do cliente), False caso contrário
        """
        from django.utils import timezone
        from datetime import timedelta
        import logging
        
        logger = logging.getLogger(__name__)
        
        # SEMPRE buscar a mensagem mais recente do cliente para garantir precisão
        # Usar o created_at real da mensagem, que é o timestamp exato de quando foi enviada/recebida
        # Usar only('created_at') para otimizar a query (não precisa buscar outros campos)
        # Usar select_related não é necessário aqui pois só precisamos do created_at
        last_customer_message = self.messages.filter(
            is_from_customer=True
        ).only('created_at').order_by('-created_at').first()
        
        if not last_customer_message:
            # Se não há mensagens do cliente, janela está fechada
            logger.debug(f"[Conversation {self.id}] Sem mensagens do cliente, janela fechada")
            return False
        
        # Usar o created_at da mensagem mais recente do cliente
        # Este é o timestamp real de quando a mensagem foi enviada/recebida
        last_message_time = last_customer_message.created_at
        
        # Calcular diferença entre agora e a última mensagem do cliente
        # timezone.now() já está no timezone correto (America/Belem)
        now = timezone.now()
        time_diff = now - last_message_time
        
        # Janela está aberta se passou menos de 24 horas (exatamente 24 horas = fechada)
        is_open = time_diff < timedelta(hours=24)
        
        # Log para debug
        hours_passed = time_diff.total_seconds() / 3600
        if not is_open:
            logger.info(f"[Conversation {self.id}] Janela fechada: última mensagem do cliente há {hours_passed:.2f} horas (timestamp: {last_message_time}, agora: {now})")
        else:
            logger.info(f"[Conversation {self.id}] Janela aberta: última mensagem do cliente há {hours_passed:.2f} horas (timestamp: {last_message_time}, agora: {now})")
        
        return is_open
    
    def update_last_user_message_at(self, timestamp=None):
        """
        Atualiza o timestamp da última mensagem recebida do cliente.
        
        Args:
            timestamp: Timestamp específico a usar (opcional, usa timezone.now() se None)
        """
        from django.utils import timezone
        self.last_user_message_at = timestamp or timezone.now()
        self.save(update_fields=['last_user_message_at'])


class Message(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Texto'),
        ('image', 'Imagem'),
        ('audio', 'Áudio'),
        ('video', 'Vídeo'),
        ('document', 'Documento'),
        ('location', 'Localização'),
        ('ptt', 'Mensagem de Voz'),
        ('sticker', 'Figurinha'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    is_from_customer = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Arquivos de mídia
    file_url = models.URLField(blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)  # em bytes
    
    additional_attributes = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        
        # Atualizar last_message_at da conversa sempre que uma nova mensagem for salva
        if is_new:
            from django.utils import timezone
            now = self.created_at or timezone.now()
            update_fields = ['last_message_at', 'updated_at']
            self.conversation.last_message_at = now
            if self.is_from_customer:
                self.conversation.last_user_message_at = now
                update_fields.append('last_user_message_at')
            self.conversation.save(update_fields=update_fields)
            if not self.is_from_customer:
                try:
                    from core.attendance_auto_resolve import maybe_auto_resolve_after_outbound_message

                    maybe_auto_resolve_after_outbound_message(self)
                except Exception:
                    pass

    def __str__(self):
        return f"Mensagem de {self.conversation.contact.name}"


class MessageReaction(models.Model):
    """
    Reações (emojis) aplicadas a mensagens do WhatsApp.
    Uma mensagem pode ter múltiplas reações de diferentes usuários.
    """
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    emoji = models.CharField(max_length=10)  # 👍, ❤️, 😂, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    # Armazenar se a reação veio do cliente ou do agente
    is_from_customer = models.BooleanField(default=True)
    # ID externo da reação (se aplicável)
    external_id = models.CharField(max_length=255, blank=True, null=True)
    # Atributos adicionais (ex: message_id da mensagem original que foi reagida)
    additional_attributes = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'message_reactions'
        indexes = [
            models.Index(fields=['message', 'emoji']),
        ]
    
    def __str__(self):
        return f"{self.emoji} em mensagem {self.message.id}"


class Team(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='teams', null=True, blank=True)
    horarios_atendimento = models.TextField(
        null=True,
        blank=True,
        help_text='Horários desta equipe (JSON). Vazio = usa o horário global do provedor.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
    @classmethod
    def get_or_create_ia_team(cls, provedor):
        """
        Não cria mais a equipe virtual "IA".

        Conversas em modo IA usam status (ex.: snoozed) sem precisar de equipe.
        O nome do método é mantido por compatibilidade com callers existentes.
        """
        return None


class TeamMember(models.Model):
    ROLE_CHOICES = [
        ('member', 'Membro'),
        ('leader', 'Líder'),
    ]
    
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['team', 'user']

    def __str__(self):
        return f"{self.user.username} em {self.team.name}"


class RecoverySettings(models.Model):
    """Configurações do recuperador de conversas"""
    provedor = models.OneToOneField(Provedor, on_delete=models.CASCADE, related_name='recovery_settings')
    enabled = models.BooleanField(default=True)
    delay_minutes = models.IntegerField(default=30, help_text="Delay em minutos antes de tentar recuperar")
    max_attempts = models.IntegerField(default=3, help_text="Número máximo de tentativas")
    auto_discount = models.BooleanField(default=False, help_text="Aplicar desconto automático")
    discount_percentage = models.IntegerField(default=10, help_text="Percentual de desconto")
    keywords = models.JSONField(default=list, help_text="Palavras-chave para identificar interesse em planos")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configurações de recuperação - {self.provedor.name}"


class RecoveryAttempt(models.Model):
    """Registro de tentativas de recuperação"""
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('sent', 'Enviada'),
        ('recovered', 'Recuperada'),
        ('failed', 'Falhou'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='recovery_attempts')
    attempt_number = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message_sent = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    response_received_at = models.DateTimeField(null=True, blank=True)
    potential_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    additional_attributes = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Tentativa {self.attempt_number} - {self.conversation.contact.name}"

    class Meta:
        unique_together = ['conversation', 'attempt_number']


# ===== CHAT INTERNO PARA ATENDENTES =====

class InternalChatRoom(models.Model):
    """
    Sala de chat interno para atendentes do provedor
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='chat_rooms')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_chat_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    # Tipos de sala
    ROOM_TYPES = [
        ('general', 'Geral'),
        ('support', 'Suporte'),
        ('sales', 'Vendas'), 
        ('private', 'Privado'),
        ('team', 'Equipe')
    ]
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='general')
    
    class Meta:
        db_table = 'internal_chat_rooms'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.name} - {self.provedor.nome}"

class InternalChatParticipant(models.Model):
    """
    Participantes da sala de chat
    """
    room = models.ForeignKey(InternalChatRoom, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_chat_participants'
        unique_together = ['room', 'user']
        
    def __str__(self):
        return f"{self.user.username} in {self.room.name}"

class InternalChatMessage(models.Model):
    """
    Mensagens do chat interno
    """
    room = models.ForeignKey(InternalChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Tipos de mensagem
    MESSAGE_TYPES = [
        ('text', 'Texto'),
        ('image', 'Imagem'),
        ('video', 'Vídeo'),
        ('audio', 'Áudio'),
        ('file', 'Arquivo'),
        ('system', 'Sistema')
    ]
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    
    # Arquivos de mídia
    file_url = models.URLField(blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)  # em bytes
    
    # Reply/Thread
    reply_to = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # Status da mensagem
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    
    # Metadados adicionais
    additional_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'internal_chat_messages'
        ordering = ['created_at']
        
    def __str__(self):
        content_preview = self.content[:50] if self.content else f"[{self.message_type}]"
        return f"{self.sender.username}: {content_preview}"

class InternalChatMessageRead(models.Model):
    """
    Controle de mensagens lidas por usuário
    """
    message = models.ForeignKey(InternalChatMessage, on_delete=models.CASCADE, related_name='read_receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'internal_chat_message_reads'
        unique_together = ['message', 'user']
        
    def __str__(self):
        return f"{self.user.username} read message {self.message.id}"

class InternalChatReaction(models.Model):
    """
    Reações às mensagens (emojis)
    """
    message = models.ForeignKey(InternalChatMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)  # 👍, ❤️, 😂, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'internal_chat_reactions'
        unique_together = ['message', 'user', 'emoji']
        
    def __str__(self):
        return f"{self.user.username} {self.emoji} on message {self.message.id}"


# ===== CHAT PRIVADO ENTRE USUÁRIOS =====

class PrivateMessage(models.Model):
    """
    Mensagens privadas entre dois usuários
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_private_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_private_messages')
    content = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Tipos de mensagem
    MESSAGE_TYPES = [
        ('text', 'Texto'),
        ('image', 'Imagem'),
        ('video', 'Vídeo'),
        ('audio', 'Áudio'),
        ('file', 'Arquivo'),
        ('system', 'Sistema')
    ]
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    
    # Arquivos de mídia
    file_url = models.URLField(blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)  # em bytes
    
    # Reply/Thread
    reply_to = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # Status da mensagem
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Isolamento por provedor
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='private_messages')
    
    # Metadados adicionais
    additional_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'private_messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', 'recipient', 'provedor']),
            models.Index(fields=['recipient', 'is_read']),
        ]
        
    def __str__(self):
        content_preview = self.content[:50] if self.content else f"[{self.message_type}]"
        return f"{self.sender.username} -> {self.recipient.username}: {content_preview}"
    
    def mark_as_read(self):
        """Marcar mensagem como lida"""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

class PrivateMessageReaction(models.Model):
    """
    Reações às mensagens privadas (emojis)
    """
    message = models.ForeignKey(PrivateMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)  # 👍, ❤️, 😂, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'private_message_reactions'
        unique_together = ['message', 'user', 'emoji']
        
    def __str__(self):
        return f"{self.user.username} {self.emoji} on private message {self.message.id}"


class CSATFeedback(models.Model):
    """
    Modelo para armazenar feedbacks CSAT dos clientes
    """
    EMOJI_RATINGS = [
        ('😡', 'Muito insatisfeito - 1'),
        ('😕', 'Insatisfeito - 2'), 
        ('😐', 'Neutro - 3'),
        ('🙂', 'Satisfeito - 4'),
        ('🤩', 'Muito satisfeito - 5'),
    ]
    
    RATING_VALUES = {
        '😡': 1,
        '😕': 2, 
        '😐': 3,
        '🙂': 4,
        '🤩': 5,
    }
    
    # Relacionamentos
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='csat_feedbacks')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='csat_feedbacks') 
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='csat_feedbacks')
    
    # Dados do feedback
    emoji_rating = models.CharField(max_length=10, choices=EMOJI_RATINGS)
    rating_value = models.IntegerField()  # 1-5 baseado no emoji
    channel_type = models.CharField(max_length=20)  # whatsapp, telegram, email, etc
    
    # Metadados
    feedback_sent_at = models.DateTimeField(auto_now_add=True)
    conversation_ended_at = models.DateTimeField()
    response_time_minutes = models.IntegerField()  # Tempo entre fim da conversa e resposta
    
    # Dados adicionais para auditoria
    original_message = models.TextField(blank=True, null=True)  # Mensagem original do cliente
    additional_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'csat_feedbacks'
        ordering = ['-feedback_sent_at']
        indexes = [
            models.Index(fields=['provedor', 'feedback_sent_at']),
            models.Index(fields=['provedor', 'rating_value']),
            models.Index(fields=['channel_type', 'provedor']),
        ]
        
    def __str__(self):
        return f"CSAT {self.emoji_rating} ({self.rating_value}) - {self.contact} - {self.feedback_sent_at.strftime('%d/%m/%Y')}"
    
    def save(self, *args, **kwargs):
        # Automaticamente definir rating_value baseado no emoji
        if self.emoji_rating and not self.rating_value:
            self.rating_value = self.RATING_VALUES.get(self.emoji_rating, 3)
        super().save(*args, **kwargs)


class CSATRequest(models.Model):
    """
    Modelo para controlar as solicitações de CSAT enviadas
    """
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('sent', 'Enviado'),
        ('responded', 'Respondido'),
        ('expired', 'Expirado'),
    ]
    
    # Relacionamentos
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='csat_requests')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='csat_requests')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='csat_requests')
    
    # Status e timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    conversation_ended_at = models.DateTimeField()
    scheduled_send_at = models.DateTimeField()  # 2 minutos após encerramento
    sent_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Referência ao feedback (quando respondido)
    csat_feedback = models.OneToOneField(CSATFeedback, on_delete=models.CASCADE, null=True, blank=True, related_name='request')
    
    # Metadados
    channel_type = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'csat_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provedor', 'status']),
            models.Index(fields=['scheduled_send_at', 'status']),
        ]
        
    def __str__(self):
        return f"CSAT Request - {self.contact} - {self.status} - {self.conversation_ended_at.strftime('%d/%m/%Y %H:%M')}"


class AILearningAnalysis(models.Model):
    """
    Sinais de aprendizado de um atendimento encerrado (só banco local, nunca vai ao Supabase).
    conversation_id sem FK: a conversa sai do local na rotina noturna e a análise continua.
    """
    OUTCOME_CHOICES = [
        ('ai_resolved', 'Resolvido pela IA'),
        ('ai_transferred', 'IA transferiu para humano'),
        ('agent_took_over', 'Atendente assumiu da IA'),
        ('chatbot', 'Chatbot'),
        ('human_only', 'Somente atendente'),
        ('no_reply', 'Sem resposta'),
    ]

    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='ai_learning_analyses')
    conversation_id = models.BigIntegerField()
    contact_id = models.BigIntegerField(null=True, blank=True)
    channel_type = models.CharField(max_length=30, blank=True, default='')
    conversation_started_at = models.DateTimeField(null=True, blank=True)
    conversation_closed_at = models.DateTimeField(null=True, blank=True)
    customer_messages = models.PositiveIntegerField(default=0)
    ai_messages = models.PositiveIntegerField(default=0)
    chatbot_messages = models.PositiveIntegerField(default=0)
    agent_messages = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    transfer_reason = models.TextField(blank=True, default='')
    # Transferência ou atendente assumindo: material para a etapa de sugestões de aprendizado
    learning_candidate = models.BooleanField(default=False)
    # pending | done | skipped (nada reaproveitável) | failed
    suggestion_status = models.CharField(max_length=10, default='pending')
    suggestion_attempted_at = models.DateTimeField(null=True, blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_learning_analyses'
        constraints = [
            models.UniqueConstraint(fields=['provedor', 'conversation_id'], name='ai_learning_unique_conversation'),
        ]
        indexes = [
            models.Index(fields=['provedor', 'conversation_closed_at'], name='ai_learning_prov_closed_idx'),
        ]

    def __str__(self):
        return f"AILearningAnalysis conv={self.conversation_id} {self.outcome}"


class AILearning(models.Model):
    """
    Aprendizado da IA de um provedor (base de conhecimento consultada por busca, fora do prompt base).
    Só os aprovados chegam à IA, e apenas os relevantes para a mensagem do cliente.
    Sugestões de baixo risco são aprovadas automaticamente; as sensíveis guardam em
    review_reason o motivo de aguardarem o admin.
    """
    STATUS_CHOICES = [
        ('suggested', 'Sugerido'),
        ('approved', 'Aprovado'),
        ('disabled', 'Desativado'),
        ('rejected', 'Rejeitado'),
    ]
    SOURCE_CHOICES = [
        ('llm', 'Sugerido pela IA'),
        ('manual', 'Cadastrado pelo provedor'),
    ]

    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='ai_learnings')
    situation = models.CharField(max_length=300)
    answer = models.TextField()
    keywords = models.CharField(max_length=500, blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='suggested')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='llm')
    source_conversation_ids = models.JSONField(default=list, blank=True)
    review_reason = models.CharField(max_length=200, blank=True, default='')
    times_used = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_learnings'
        indexes = [
            models.Index(fields=['provedor', 'status'], name='ai_learning_prov_status_idx'),
        ]

    def __str__(self):
        return f"AILearning {self.id} [{self.status}] {self.situation[:40]}"


class AdReferral(models.Model):
    """
    Entrada de cliente vinda de anúncio Click-to-WhatsApp (objeto `referral` do webhook da Cloud API).
    Uma linha por entrada: a mesma conversa é reaberta com o mesmo ID, então a origem não pode
    ficar só na conversa. Conversa/contato usam SET_NULL porque a conversa local é migrada e apagada.
    `ctwa_clid` só chega na primeira mensagem e é exigido pela Conversions API (até 7 dias do clique).
    """
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='ad_referrals')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='ad_referrals')
    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='ad_referrals'
    )
    message_external_id = models.CharField(max_length=255, unique=True)
    source_type = models.CharField(max_length=20, blank=True, default='')
    source_id = models.CharField(max_length=64, blank=True, default='')
    source_url = models.TextField(blank=True, default='')
    headline = models.CharField(max_length=500, blank=True, default='')
    body = models.TextField(blank=True, default='')
    media_type = models.CharField(max_length=20, blank=True, default='')
    thumbnail_url = models.TextField(blank=True, default='')
    ctwa_clid = models.CharField(max_length=512, blank=True, default='')
    new_contact = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ad_referrals'
        indexes = [
            models.Index(fields=['provedor', 'created_at'], name='ad_ref_prov_created_idx'),
            models.Index(fields=['provedor', 'source_id'], name='ad_ref_prov_source_idx'),
        ]

    def __str__(self):
        return f"AdReferral {self.id} [{self.source_type}:{self.source_id}]"
