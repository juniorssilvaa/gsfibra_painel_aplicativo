from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class VpsServer(models.Model):
    name = models.CharField(max_length=100)
    api_url = models.URLField(help_text="Ex: https://vps1.niohub.com.br:9443")
    portainer_api_key = models.CharField(max_length=255)
    endpoint_id = models.IntegerField(default=1)
    max_capacity = models.IntegerField(default=3)
    redis_host = models.CharField(max_length=255, default='localhost')
    redis_password = models.CharField(max_length=255, blank=True)
    # Em Docker/Swarm o host deve ser o nome do serviço na rede (ex.: rabbitmq), nunca localhost.
    rabbitmq_url = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Servidor VPS"
        verbose_name_plural = "Servidores VPS"

class User(AbstractUser):
    USER_TYPES = [
        ('superadmin', 'Super Administrador'),
        ('admin', 'Administrador'),
        ('agent', 'Atendente'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='agent')
    provedor = models.ForeignKey('Provedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    session_timeout = models.IntegerField(default=30)
    phone = models.CharField(max_length=30, null=True, blank=True)
    preferred_language = models.CharField(max_length=20, default='pt-BR', blank=True)

class Company(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class Provedor(models.Model):
    RELEASE_CHANNELS = [
        ('beta', 'Beta (Atualização Automática)'),
        ('stable', 'Estável (Atualização Controlada)'),
        ('manual', 'Manual'),
    ]
    nome = models.CharField(max_length=200)
    vps = models.ForeignKey(VpsServer, on_delete=models.SET_NULL, null=True, blank=True, related_name='provedores')

    subdomain = models.CharField(max_length=100, unique=True, null=True, blank=True)
    site_oficial = models.URLField(null=True, blank=True)
    endereco = models.CharField(max_length=300, null=True, blank=True)
    email_contato = models.EmailField(null=True, blank=True)
    bot_mode = models.CharField(max_length=20, default='ia')
    agent_mode = models.CharField(
        max_length=20,
        default='isp',
        help_text='isp = provedor de internet; support = suporte/comercial da plataforma',
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=30, default='ativo')
    cpf_cnpj = models.CharField(max_length=30, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    mobile_phone = models.CharField(max_length=30, null=True, blank=True)
    address_number = models.CharField(max_length=30, null=True, blank=True)
    complement = models.CharField(max_length=255, null=True, blank=True)
    province = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    group_name = models.CharField(max_length=100, null=True, blank=True)
    company = models.CharField(max_length=200, null=True, blank=True)
    municipal_inscription = models.CharField(max_length=50, null=True, blank=True)
    state_inscription = models.CharField(max_length=50, null=True, blank=True)
    observations = models.TextField(null=True, blank=True)
    additional_emails = models.TextField(null=True, blank=True)
    notification_disabled = models.BooleanField(default=False)
    foreign_customer = models.BooleanField(default=False)
    asaas_customer_id = models.CharField(max_length=60, null=True, blank=True)
    asaas_subscription_id = models.CharField(max_length=60, null=True, blank=True)
    # Portador da assinatura: asaas | inter (escolhido ao criar o cliente/assinatura)
    BILLING_PROVIDER_ASAAS = 'asaas'
    BILLING_PROVIDER_INTER = 'inter'
    BILLING_PROVIDER_CHOICES = [
        (BILLING_PROVIDER_ASAAS, 'Asaas'),
        (BILLING_PROVIDER_INTER, 'Banco Inter'),
    ]
    billing_provider = models.CharField(
        max_length=20,
        choices=BILLING_PROVIDER_CHOICES,
        default=BILLING_PROVIDER_ASAAS,
        help_text='Gateway usado para assinatura/cobrança deste provedor',
    )
    subscription_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subscription_cycle = models.CharField(max_length=20, default='MONTHLY', null=True, blank=True)
    subscription_billing_type = models.CharField(max_length=30, default='BOLETO', null=True, blank=True)
    subscription_status = models.CharField(max_length=30, default='PENDING', null=True, blank=True)
    subscription_next_due_date = models.DateField(null=True, blank=True)
    redes_sociais = models.JSONField(default=dict, blank=True)
    nome_agente_ia = models.CharField(max_length=100, null=True, blank=True)
    estilo_personalidade = models.CharField(max_length=60, null=True, blank=True)
    modo_falar = models.CharField(max_length=100, null=True, blank=True)
    uso_emojis = models.CharField(max_length=20, null=True, blank=True)
    personalidade = models.TextField(null=True, blank=True)
    taxa_adesao = models.CharField(max_length=100, null=True, blank=True)
    inclusos_plano = models.TextField(null=True, blank=True)
    multa_cancelamento = models.CharField(max_length=200, null=True, blank=True)
    tipo_conexao = models.CharField(max_length=100, null=True, blank=True)
    prazo_instalacao = models.CharField(max_length=100, null=True, blank=True)
    documentos_necessarios = models.TextField(null=True, blank=True)
    users_count = models.IntegerField(default=0)
    conversations_count = models.IntegerField(default=0)
    integracoes_externas = models.JSONField(null=True, blank=True)
    
    # Canais de Atualização
    release_channel = models.CharField(max_length=20, choices=RELEASE_CHANNELS, default='stable')
    last_update = models.DateTimeField(null=True, blank=True)
    current_version = models.CharField(max_length=50, default='1.0.0')

    # Senha de primeiro acesso ao painel do tenant (encriptada; ver panel_bootstrap_crypto)
    panel_bootstrap_password_ciphertext = models.TextField(
        blank=True,
        default='',
        help_text='Senha em texto puro é guardada encriptada ao criar/alterar user do superadmin ligado ao provedor.',
    )
    # Token de integração Superadmin -> Tenant (enviado no header Authorization: Bearer)
    # Mantido por provedor para comunicação isolada entre os painéis.
    integration_token = models.CharField(max_length=255, blank=True, default='')
    integration_token_last_used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']


class ProvedorHealth(models.Model):
    """Último boletim de saúde enviado pelo tenant no heartbeat."""
    provedor = models.OneToOneField(Provedor, on_delete=models.CASCADE, related_name='health')
    reported_at = models.DateTimeField()
    data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Saúde {self.provedor_id} @ {self.reported_at:%Y-%m-%d %H:%M}"


class SystemUpdate(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Na fila'),
        (STATUS_RUNNING, 'Em andamento'),
        (STATUS_DONE, 'Concluído'),
        (STATUS_FAILED, 'Falhou'),
    ]

    version = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    release_date = models.DateTimeField(auto_now_add=True)
    channel = models.CharField(max_length=20, choices=Provedor.RELEASE_CHANNELS)
    is_deployed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    source = models.CharField(max_length=20, default='ui')
    results = models.JSONField(default=list, blank=True)
    promote_ok = models.BooleanField(null=True, blank=True)
    promote_log = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.version} ({self.channel})"

    class Meta:
        ordering = ['-release_date']


class Canal(models.Model):
    nome = models.CharField(max_length=100, default='')
    tipo = models.CharField(max_length=50, default='telegram')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='canais')
    ativo = models.BooleanField(default=True)
    dados_extras = models.JSONField(default=dict, blank=True)
    instance_id = models.CharField(max_length=255, null=True, blank=True)
    api_key = models.CharField(max_length=255, null=True, blank=True)
    api_id = models.CharField(max_length=255, null=True, blank=True)
    api_hash = models.CharField(max_length=255, null=True, blank=True)
    app_title = models.CharField(max_length=200, null=True, blank=True)
    short_name = models.CharField(max_length=100, null=True, blank=True)
    verification_code = models.CharField(max_length=20, null=True, blank=True)
    phone_number = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    smtp_host = models.CharField(max_length=255, null=True, blank=True)
    smtp_port = models.CharField(max_length=10, null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    # Campos para WhatsApp Cloud API (roteamento do webhook)
    waba_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="WhatsApp Business Account ID")
    phone_number_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Phone Number ID da Meta")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']

class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=60, default='view')
    details = models.TextField(default='', blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

class MensagemSistema(models.Model):
    assunto = models.CharField(max_length=200, default='', blank=True)
    mensagem = models.TextField(default='', blank=True)
    # Banner/imagem do aviso (URL pública) + áreas clicáveis em % da imagem
    imagem_url = models.URLField(max_length=1000, blank=True, default='')
    hotspots = models.JSONField(
        default=list,
        blank=True,
        help_text='Áreas clicáveis na imagem: [{x,y,w,h,url,label}] em % (0-100).',
    )
    cta_links = models.JSONField(
        default=list,
        blank=True,
        help_text='Botões abaixo da imagem: [{label,url}].',
    )
    provedores = models.JSONField(default=list, blank=True)
    tipo = models.CharField(max_length=30, default='notificacao')
    visivel_para_agentes = models.BooleanField(default=True)
    visualizacoes = models.JSONField(default=dict, blank=True)
    visualizacoes_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

class BillingTemplate(models.Model):
    template_id = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=30, default='UTILITY')
    language = models.CharField(max_length=20, default='pt_BR')
    status = models.CharField(max_length=30, default='PENDING')
    body_text = models.TextField(default='', blank=True)
    components = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class SystemConfig(models.Model):
    payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProductSuggestion(models.Model):
    STATUS_CHOICES = [
        ("analise", "Em analise"),
        ("desenvolvimento", "Em desenvolvimento"),
        ("concluido", "Concluido"),
    ]

    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name="product_suggestions",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="analise")
    author_name = models.CharField(max_length=200, blank=True, default="")
    author_user_id = models.IntegerField(null=True, blank=True)
    votes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-votes_count", "-created_at"]

    def __str__(self):
        return self.title


class ProductSuggestionVote(models.Model):
    suggestion = models.ForeignKey(
        ProductSuggestion,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    voter_provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name="product_suggestion_votes",
    )
    voter_user_id = models.IntegerField()
    voter_name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("suggestion", "voter_provedor", "voter_user_id")]


class ProductSuggestionComment(models.Model):
    """Comentario publico: qualquer usuario de qualquer provedor pode comentar."""

    suggestion = models.ForeignKey(
        ProductSuggestion,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author_provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name="product_suggestion_comments",
    )
    author_user_id = models.IntegerField()
    author_name = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment #{self.id} on suggestion {self.suggestion_id}"


class BillingSendLog(models.Model):
    """Registro de mensagens de cobrança WhatsApp enviadas pelo Superadmin aos provedores."""

    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='billing_send_logs',
    )
    asaas_payment_id = models.CharField(max_length=60, blank=True, default='')
    asaas_customer_id = models.CharField(max_length=60, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    template_name = models.CharField(max_length=120, blank=True, default='')
    due_offset = models.IntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['success', 'created_at']),
        ]

    def __str__(self):
        status = 'ok' if self.success else 'err'
        return f"BillingSend {self.asaas_payment_id} ({status})"


class InterBillingCharge(models.Model):
    """Cobrança emitida no Banco Inter (boleto + Pix) vinculada a um provedor."""

    STATUS_PENDING = 'PENDING'
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_OVERDUE = 'OVERDUE'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_RECEIVED, 'Recebido'),
        (STATUS_OVERDUE, 'Vencido'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name='inter_charges',
    )
    codigo_solicitacao = models.CharField(max_length=80, unique=True, db_index=True)
    seu_numero = models.CharField(max_length=15, blank=True, default='', db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_vencimento = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=40, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    linha_digitavel = models.CharField(max_length=120, blank=True, default='')
    pix_copia_cola = models.TextField(blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_vencimento', '-id']
        indexes = [
            models.Index(fields=['provedor', 'status']),
            models.Index(fields=['data_vencimento', 'status']),
        ]

    def __str__(self):
        return f"InterCharge {self.codigo_solicitacao} ({self.status})"

