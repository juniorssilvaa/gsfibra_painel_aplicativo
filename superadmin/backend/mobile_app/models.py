"""
Models do aplicativo mobile do cliente (legado app_provedor),
unificados no Postgres do Superadmin Niohub.

Fonte: app_provedor/backend/core/models.py
Provedor Niohub (super_core.Provedor) substitui o antigo Provider 1:1.
"""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class MobileAppProfile(models.Model):
    """
    Extensão do Provedor para o app mobile do cliente final.
    Criar este registro = habilitar o app para o provedor.
    """
    provedor = models.OneToOneField(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_app',
    )
    logo = models.ImageField(upload_to='mobile_app/logos/', blank=True, null=True)
    login_logo = models.ImageField(upload_to='mobile_app/logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#0D70B3')
    # Tema do app (vazio = o app usa a cor padrão embutida no build).
    secondary_color = models.CharField(max_length=7, blank=True, default='')
    login_bg_color = models.CharField(max_length=7, blank=True, default='')
    login_button_color = models.CharField(max_length=7, blank=True, default='')
    login_text_color = models.CharField(max_length=7, blank=True, default='')
    app_bg_color = models.CharField(max_length=7, blank=True, default='')
    card_color = models.CharField(max_length=7, blank=True, default='')
    # Posição horizontal do logo no topo da tela inicial: 0 = esquerda, 50 = centro, 100 = direita.
    home_logo_position = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    # Cores embutidas no build do app deste provedor (enviadas pelo próprio app).
    app_default_theme = models.JSONField(default=dict, blank=True)
    glass_intensity = models.IntegerField(default=82)
    glass_blur = models.IntegerField(default=18)
    ambient_shadow = models.IntegerField(default=55)
    # Contato específico do app (pode espelhar Provedor.cpf_cnpj / phone)
    cnpj = models.CharField(max_length=20, blank=True, null=True)
    number = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # SGP / ERP (app)
    ERP_TYPE_CHOICES = (
        ('sgp', 'SGP'),
        ('receitanet', 'ReceitaNet'),
    )
    erp_type = models.CharField(
        max_length=20,
        choices=ERP_TYPE_CHOICES,
        default='sgp',
        help_text='ERP usado pelo app mobile (SGP ou ReceitaNet).',
    )
    sgp_url = models.URLField(max_length=255, blank=True, null=True)
    sgp_token = models.CharField(max_length=500, unique=True, blank=True, null=True)
    sgp_app_name = models.CharField(max_length=255, blank=True, null=True)
    sgp_token_created_at = models.DateTimeField(blank=True, null=True)
    webhook_url = models.URLField(max_length=500, blank=True, null=True)
    # Versão mínima/atual do app (devices abaixo = desatualizados)
    latest_app_version = models.CharField(max_length=32, blank=True, null=True)
    terms_text = models.TextField(blank=True, default='')
    privacy_text = models.TextField(blank=True, default='')

    # GenieACS
    genieacs_url = models.URLField(max_length=255, blank=True, null=True)
    genieacs_token = models.TextField(blank=True, null=True)
    genieacs_user = models.CharField(max_length=255, blank=True, null=True)
    genieacs_password = models.CharField(max_length=255, blank=True, null=True)

    # Fila de atendimento do app no painel NioChat (ID da equipe no tenant)
    app_default_team_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text='ID da equipe no painel de atendimento que recebe chats do app (aba Espera).',
    )

    class Meta:
        verbose_name = 'Perfil App Mobile'
        verbose_name_plural = 'Perfis App Mobile'

    def __str__(self):
        return f'App Mobile — {self.provedor.nome}'

    def get_active_token(self):
        token_obj = self.tokens.filter(is_active=True).first()
        return token_obj.token if token_obj else None

    def generate_new_token(self):
        self.tokens.all().delete()
        return MobileProviderToken.objects.create(profile=self)


class MobileProviderToken(models.Model):
    """Token sk_live_* usado pelo app / SGP / webhooks de push."""
    token = models.CharField(max_length=255, unique=True, db_index=True)
    profile = models.ForeignKey(
        MobileAppProfile,
        on_delete=models.CASCADE,
        related_name='tokens',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Token do App'
        verbose_name_plural = 'Tokens do App'

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets
            self.token = f'sk_live_{secrets.token_hex(24)}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.profile} — {self.token[:15]}...'


class MobileAppConfig(models.Model):
    """Flags de ferramentas/atalhos do app (ligado ao perfil)."""
    profile = models.OneToOneField(
        MobileAppProfile,
        on_delete=models.CASCADE,
        related_name='app_config',
    )
    active_shortcuts = models.JSONField(default=list, blank=True)
    active_tools = models.JSONField(default=list, blank=True)
    social_links = models.JSONField(default=list, blank=True)
    update_warning_active = models.BooleanField(default=False)

    tool_faturas = models.BooleanField(default=True)
    tool_connected_devices = models.BooleanField(default=True)
    tool_speed_test = models.BooleanField(default=True)
    tool_auto_unlock = models.BooleanField(default=True)
    tool_wifi = models.BooleanField(default=True)
    tool_cameras = models.BooleanField(default=False)
    shortcut_wifi = models.BooleanField(default=True)

    SPEED_TEST_CHOICES = [
        ('fast', 'Fast.com'),
        ('speedtest', 'Speedtest.net'),
    ]
    speed_test_provider = models.CharField(
        max_length=20,
        choices=SPEED_TEST_CHOICES,
        default='fast',
    )

    class Meta:
        verbose_name = 'Configuração do App'
        verbose_name_plural = 'Configurações do App'

    def __str__(self):
        return f'Config — {self.profile.provedor.nome}'


class MobileAppUser(models.Model):
    """Cliente final que usa o aplicativo mobile."""
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_app_users',
    )
    name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    cpf = models.CharField(max_length=14)
    external_id = models.CharField(max_length=100, blank=True, null=True)
    customer_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    pppoe_login = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    genieacs_device_id = models.CharField(max_length=255, blank=True, null=True)

    wifi_ssid_2g = models.CharField(max_length=100, blank=True, null=True)
    wifi_password_2g = models.CharField(max_length=100, blank=True, null=True)
    wifi_ssid_5g = models.CharField(max_length=100, blank=True, null=True)
    wifi_password_5g = models.CharField(max_length=100, blank=True, null=True)

    modem_manufacturer = models.CharField(max_length=255, blank=True, null=True)
    modem_model = models.CharField(max_length=255, blank=True, null=True)
    modem_external_ip = models.CharField(max_length=64, blank=True, null=True)
    modem_uptime_seconds = models.BigIntegerField(blank=True, null=True)
    modem_last_sync_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(blank=True, null=True)
    tags = models.CharField(max_length=255, blank=True, null=True)
    dismissed_warnings = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Cliente do App'
        verbose_name_plural = 'Clientes do App'
        unique_together = ('provedor', 'cpf')

    def __str__(self):
        return f'{self.name or self.cpf} ({self.provedor_id})'

    @property
    def is_online(self):
        if not self.last_active_at:
            return False
        from datetime import timedelta
        from django.utils import timezone
        return self.last_active_at >= timezone.now() - timedelta(minutes=5)


class MobileDevice(models.Model):
    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]
    user = models.ForeignKey(
        MobileAppUser,
        on_delete=models.CASCADE,
        related_name='devices',
    )
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_devices',
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    model = models.CharField(max_length=100)
    os_version = models.CharField(max_length=50)
    app_version = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    push_token = models.CharField(max_length=255, unique=True, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(blank=True, null=True)
    push_confirmed = models.BooleanField(default=False)
    push_confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Dispositivo do App'
        verbose_name_plural = 'Dispositivos do App'
        unique_together = ('provedor', 'push_token')

    def __str__(self):
        return f'{self.platform} — {self.model}'

    @property
    def is_online(self):
        if not self.last_active:
            return False
        from datetime import timedelta
        from django.utils import timezone
        return self.last_active >= timezone.now() - timedelta(minutes=5)


class MobileInAppWarning(models.Model):
    TYPE_CHOICES = [
        ('info', 'Informativo'),
        ('success', 'Sucesso'),
        ('warning', 'Aviso'),
        ('critical', 'Crítico'),
    ]
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_in_app_warnings',
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    whatsapp_btn = models.CharField(max_length=20, blank=True, null=True)
    sticky = models.BooleanField(default=False)
    show_home = models.BooleanField(default=False)
    target_cpfs = models.TextField(blank=True, null=True)
    target_contracts = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Aviso In-App'
        verbose_name_plural = 'Avisos In-App'

    def __str__(self):
        return self.title


class MobilePlan(models.Model):
    TYPE_CHOICES = [
        ('FIBRA', 'Fibra Óptica'),
        ('RADIO', 'Rádio'),
        ('CABO', 'Cabo'),
    ]
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_plans',
    )
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='FIBRA')
    download_speed = models.IntegerField()
    upload_speed = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Plano (App)'
        verbose_name_plural = 'Planos (App)'

    def __str__(self):
        return f'{self.name} — {self.provedor.nome}'


class MobileNotificationTemplate(models.Model):
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_notification_templates',
    )
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    body = models.TextField()
    type = models.CharField(
        max_length=20,
        choices=[
            ('info', 'Informativo'),
            ('promo', 'Promocional'),
            ('warning', 'Aviso'),
        ],
        default='info',
    )
    image_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mobile_notification_templates',
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Template de Push'
        verbose_name_plural = 'Templates de Push'

    def __str__(self):
        return f'{self.name} ({self.provedor.nome})'


class MobileScheduledNotification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('sent', 'Enviada'),
        ('failed', 'Falhou'),
        ('cancelled', 'Cancelada'),
    ]
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_scheduled_notifications',
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    type = models.CharField(
        max_length=20,
        choices=[
            ('info', 'Informativo'),
            ('promo', 'Promocional'),
            ('warning', 'Aviso'),
        ],
        default='info',
    )
    image_url = models.URLField(max_length=500, blank=True, null=True)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    segment_type = models.CharField(max_length=20, default='all')
    segment_tags = models.CharField(max_length=500, blank=True, null=True)
    segment_search = models.CharField(max_length=255, blank=True, null=True)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mobile_scheduled_notifications',
    )

    class Meta:
        ordering = ['scheduled_at']
        indexes = [models.Index(fields=['status', 'scheduled_at'])]
        verbose_name = 'Push Agendado'
        verbose_name_plural = 'Pushes Agendados'

    def is_due(self):
        from django.utils import timezone
        return self.status == 'pending' and self.scheduled_at <= timezone.now()


class MobileNotification(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Enviado'),
        ('failed', 'Falha'),
        ('pending', 'Pendente'),
    ]
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_notifications',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    recipients_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Notificação Push'
        verbose_name_plural = 'Notificações Push'


class MobileNotificationLog(models.Model):
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_notification_logs',
    )
    source = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    body = models.TextField()
    recipients_count = models.IntegerField()
    success_count = models.IntegerField()
    failure_count = models.IntegerField()
    notif_type = models.CharField(max_length=20, blank=True, default='info')
    link = models.CharField(max_length=500, blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    segment_type = models.CharField(max_length=32, blank=True, default='all')
    # Lista de destinatários: [{name, cpf, login, status, token_suffix}]
    recipients = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Log de notificação'
        verbose_name_plural = 'Logs de notificação'


class MobileAppFunction(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    users = models.ManyToManyField(
        MobileAppUser,
        related_name='functions',
        blank=True,
    )

    def __str__(self):
        return self.name


class MobileNetworkTelemetry(models.Model):
    user = models.ForeignKey(
        MobileAppUser,
        on_delete=models.CASCADE,
        related_name='telemetries',
    )
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_telemetries',
    )
    ssid = models.CharField(max_length=255, blank=True, null=True)
    wifi_dbm = models.IntegerField(blank=True, null=True)
    band = models.CharField(max_length=50, blank=True, null=True)
    link_speed = models.IntegerField(blank=True, null=True)
    latency = models.FloatField(blank=True, null=True)
    packet_loss = models.FloatField(blank=True, null=True)
    jitter = models.FloatField(blank=True, null=True)
    network_type = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MobileAIChatSession(models.Model):
    user = models.ForeignKey(
        MobileAppUser,
        on_delete=models.CASCADE,
        related_name='chat_sessions',
    )
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_chat_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class MobileAIChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'Usuário'),
        ('assistant', 'Assistente'),
        ('system', 'Sistema'),
    ]
    session = models.ForeignKey(
        MobileAIChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class MobileActivityLog(models.Model):
    """Auditoria de eventos do app (login, Wi‑Fi, chamados, etc.)."""
    EVENT_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('register', 'Registrou o app'),
        ('wifi_password_changed', 'Alterou senha Wi-Fi'),
        ('wifi_ssid_changed', 'Alterou SSID Wi-Fi'),
        ('ticket_opened', 'Abriu chamado'),
        ('invoice_viewed', 'Visualizou fatura'),
        ('push_received', 'Recebeu push'),
        ('device_registered', 'Registrou dispositivo'),
        ('other', 'Outro'),
    ]
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_activity_logs',
    )
    user = models.ForeignKey(
        MobileAppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
    )
    event = models.CharField(max_length=64, choices=EVENT_CHOICES, db_index=True)
    event_label = models.CharField(max_length=120, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Log de atividade do App'
        verbose_name_plural = 'Logs de atividade do App'
        indexes = [
            models.Index(fields=['provedor', '-created_at']),
        ]

    def __str__(self):
        return f'{self.event} — {self.provedor_id}'

    def display_label(self):
        if self.event_label:
            return self.event_label
        return dict(self.EVENT_CHOICES).get(self.event, self.event)


class MobileSystemSettings(models.Model):
    """Singleton de config global do app (ex.: Gemini)."""
    gemini_api_key = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração Global do App'
        verbose_name_plural = 'Configurações Globais do App'

    def __str__(self):
        return 'Configurações Globais do App Mobile'

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj


class MobileSupportMedia(models.Model):
    """Arquivo de mídia do chat de atendimento no app (texto/imagem/áudio/etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provedor = models.ForeignKey(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='mobile_support_media',
    )
    cpf = models.CharField(max_length=20, db_index=True)
    file = models.FileField(upload_to='mobile_support/%Y/%m/')
    content_type = models.CharField(max_length=120, blank=True, default='')
    original_name = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mídia do chat do app'
        verbose_name_plural = 'Mídias do chat do app'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.cpf} — {self.original_name or self.id}'
        return obj
