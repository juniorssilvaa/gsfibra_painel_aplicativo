from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.contrib.auth import get_user_model

def provider_gallery_upload_to(instance, filename):
    provedor_id = instance.provedor_id or 'unknown'
    return f"provider_gallery/{provedor_id}/{filename}"

# Modelo User personalizado
class User(AbstractUser):
    USER_TYPES = [
        ('superadmin', 'Super Administrador'),
        ('admin', 'Administrador da Empresa'),
        ('agent', 'Atendente'),
    ]
    
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPES,
        default='agent',
        verbose_name='Tipo de Usuário'
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        verbose_name='Avatar'
    )
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name='Telefone'
    )
    is_online = models.BooleanField(
        default=False,
        verbose_name='Online'
    )
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Última Visualização'
    )
    permissions = models.JSONField(
        blank=True,
        default=list,
        verbose_name='Permissões Específicas'
    )
    # Preferências de som por usuário
    sound_notifications_enabled = models.BooleanField(
        default=False,
        verbose_name='Notificações Sonoras Ativas'
    )
    new_message_sound = models.CharField(
        max_length=200,
        default='01.mp3',
        verbose_name='Som para Novas Mensagens'
    )
    new_message_sound_volume = models.FloatField(
        default=1.0,
        verbose_name='Volume das Novas Mensagens'
    )
    new_conversation_sound = models.CharField(
        max_length=200,
        default='02.mp3',
        verbose_name='Som para Novas Conversas'
    )
    new_conversation_sound_volume = models.FloatField(
        default=1.0,
        verbose_name='Volume das Novas Conversas'
    )
    session_timeout = models.IntegerField(
        default=30,
        verbose_name='Timeout da Sessão (minutos)'
    )
    language = models.CharField(
        max_length=10,
        default='pt',
        choices=[
            ('pt', 'Português'),
            ('en', 'English'),
            ('es', 'Español'),
            ('fr', 'Français'),
            ('de', 'Deutsch'),
            ('it', 'Italiano'),
        ],
        verbose_name='Idioma do Sistema'
    )
    assignment_message = models.TextField(
        blank=True,
        null=True,
        help_text='Mensagem enviada automaticamente ao atribuir um atendimento a este usuário',
        verbose_name='Mensagem de Atribuição'
    )
    # Avisos WhatsApp para o atendente (usa o campo phone)
    whatsapp_alert_transfer = models.BooleanField(
        default=True,
        verbose_name='Avisar quando um atendimento for transferido para mim',
    )
    whatsapp_alert_waiting = models.BooleanField(
        default=True,
        verbose_name='Avisar quando entrar um atendimento na fila de espera',
    )
    totp_secret = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='Secret TOTP (2FA)',
    )
    totp_enabled = models.BooleanField(
        default=False,
        verbose_name='2FA ativo',
    )
    totp_enabled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='2FA ativado em',
    )
    # Relacionamento direto com o provedor (Multi-tenant)
    provedor = models.ForeignKey(
        'Provedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utilizadores',
        verbose_name='Provedor Associado'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        ordering = ['-date_joined']

    def __str__(self):
        return self.username


class Company(models.Model):
    name = models.CharField(max_length=200, verbose_name='Nome da Empresa')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True, verbose_name='Logo')
    description = models.TextField(null=True, blank=True, verbose_name='Descrição')
    website = models.URLField(null=True, blank=True, verbose_name='Website')
    email = models.EmailField(null=True, blank=True, verbose_name='E-mail')
    phone = models.CharField(max_length=20, null=True, blank=True, verbose_name='Telefone')
    address = models.TextField(null=True, blank=True, verbose_name='Endereço')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['name']

    def __str__(self):
        return self.name


class CompanyUser(models.Model):
    ROLE_CHOICES = [
        ('superadmin', 'Super Administrador'),
        ('admin', 'Administrador da Empresa'),
        ('agent', 'Atendente'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='company_users')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_users')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='agent', verbose_name='Função')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Usuário da Empresa'
        verbose_name_plural = 'Usuários da Empresa'
        unique_together = ('user', 'company')

    def __str__(self):
        return f"{self.user.username} - {self.company.name}"


class Provedor(models.Model):
    nome = models.CharField(max_length=200)
    site_oficial = models.URLField(null=True, blank=True)
    endereco = models.CharField(max_length=300, null=True, blank=True)
    redes_sociais = models.JSONField(null=True, blank=True, help_text='Redes sociais da empresa')
    horarios_atendimento = models.TextField(null=True, blank=True, help_text='Horários de atendimento (texto ou JSON)')
    dias_atendimento = models.TextField(null=True, blank=True, help_text='Dias de atendimento (texto ou JSON)')
    planos = models.TextField(null=True, blank=True, help_text='Planos da empresa (texto ou JSON)')
    dados_adicionais = models.TextField(null=True, blank=True, help_text='FAQ, orientações, termos, políticas, etc')
    integracoes_externas = models.JSONField(null=True, blank=True, help_text='Dados de integração com SGP/URA: app, token, endpoints personalizados')
    nome_agente_ia = models.CharField(max_length=100, null=True, blank=True)
    estilo_personalidade = models.CharField(max_length=50, null=True, blank=True, help_text='Ex: Formal, Brincalhão, Educado')
    modo_falar = models.CharField(max_length=100, null=True, blank=True, help_text='Ex: Nordestino, Formal, Descontraído')
    uso_emojis = models.CharField(max_length=20, null=True, blank=True, help_text='sempre, ocasionalmente, nunca')
    personalidade = models.JSONField(null=True, blank=True, help_text='Personalidade avançada: vicios_linguagem, caracteristicas, principios, humor')
    personalidade_avancada = models.JSONField(null=True, blank=True, help_text='Campos: vicios_linguagem, caracteristicas, principios, humor')
    email_contato = models.EmailField(null=True, blank=True, help_text='E-mail de contato do provedor')
    taxa_adesao = models.CharField(max_length=100, null=True, blank=True, help_text='Taxa de adesão')
    multa_cancelamento = models.CharField(max_length=200, null=True, blank=True, help_text='Multa de cancelamento')
    tipo_conexao = models.CharField(max_length=100, null=True, blank=True, help_text='Tipo de conexão')
    prazo_instalacao = models.CharField(max_length=100, null=True, blank=True, help_text='Prazo de instalação')
    documentos_necessarios = models.TextField(null=True, blank=True, help_text='Documentos necessários para cadastro')
    planos_internet = models.TextField(null=True, blank=True, help_text='Planos de internet oferecidos')
    planos_descricao = models.TextField(null=True, blank=True, help_text='Descrição detalhada dos planos')
    avatar_agente = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admins = models.ManyToManyField(User, blank=True, help_text='Usuários administradores deste provedor', related_name='provedores_admin')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    bot_mode = models.CharField(
        max_length=20,
        choices=[('ia', 'Inteligência Artificial'), ('chatbot', 'Fluxo de Chatbot')],
        default='ia',
        verbose_name='Modo de Atendimento',
        help_text='Define se o provedor usa IA ou um fluxo de chatbot pré-definido'
    )
    agent_mode = models.CharField(
        max_length=20,
        choices=[
            ('isp', 'Provedor de Internet'),
            ('support', 'Suporte da Plataforma'),
        ],
        default='isp',
        verbose_name='Modo do Agente de IA',
        help_text='isp = regras de ISP/SGP; support = atendimento da plataforma (sem SGP/fatura de internet)',
    )
    support_transfer_notify_phone = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name='WhatsApp para notificar transferências (Modo Suporte)',
        help_text='Número que recebe resumo quando a IA transferir para qualquer equipe (ex.: 5599999999999)',
    )
    automation_schedule_enabled = models.BooleanField(
        default=False,
        verbose_name='Ativar automação por horário',
        help_text='Se ativado, a IA/chatbot liga e desliga automaticamente com base no horário comercial.',
    )
    automation_schedule_mode = models.CharField(
        max_length=32,
        choices=[
            ('outside_business_hours', 'Automação fora do horário comercial'),
            ('inside_business_hours', 'Automação dentro do horário comercial'),
        ],
        default='outside_business_hours',
        verbose_name='Modo da automação por horário',
        help_text='Define se a IA/chatbot funciona dentro ou fora do horário comercial.',
    )
    automation_schedule_apply_holidays = models.BooleanField(
        default=True,
        verbose_name='Aplicar feriados na automação',
        help_text='Se ativado, os feriados cadastrados também influenciam o acionamento automático da IA/chatbot.',
    )
    automation_schedule_fallback_team = models.ForeignKey(
        'conversations.Team',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provedores_fallback_automacao',
        verbose_name='Equipe quando a automação estiver desligada',
        help_text=(
            'Usada no modo "dentro do horário comercial": fora do expediente (ou em feriado), '
            'os atendimentos vão para esta equipe enquanto a IA/chatbot estão desligados.'
        ),
    )
    attendance_holidays = models.JSONField(
        blank=True,
        default=list,
        verbose_name='Feriados do provedor',
        help_text='Lista de feriados e datas especiais usadas para regras de atendimento.',
    )
    attendance_national_holidays = models.JSONField(
        blank=True,
        default=list,
        verbose_name='Feriados nacionais (overrides)',
        help_text=(
            'Overrides de ativação dos feriados nacionais. '
            'Lista de {id, active}; ids ausentes ficam ativos por padrão. '
            'Nome e data não são editáveis pelo provedor.'
        ),
    )

    # ===========================================================================================
    # CSAT (Customer Satisfaction Score)
    # ===========================================================================================
    csat_delay_minutes = models.PositiveSmallIntegerField(
        default=2,
        verbose_name='Delay CSAT (minutos)',
        help_text='Minutos após o encerramento automático para disparar a pesquisa de satisfação ao cliente.'
    )
    csat_send_on_bot_inactivity_closure = models.BooleanField(
        default=True,
        verbose_name='Enviar CSAT no encerramento por inatividade do bot',
        help_text='Se ativado, o sistema envia CSAT quando o chatbot encerra a conversa por inatividade.'
    )

    csat_enforce_min_interval = models.BooleanField(
        default=True,
        verbose_name='Respeitar intervalo mínimo entre envios de CSAT',
        help_text='Se ativado, o sistema não envia novas pesquisas de CSAT para o mesmo contato em um intervalo menor que o configurado.'
    )

    csat_min_interval_hours = models.PositiveSmallIntegerField(
        default=24,
        verbose_name='Intervalo mínimo entre envios (horas)',
        help_text='Quantidade mínima de horas entre envios de CSAT para o mesmo contato.'
    )

    allow_ticket_when_contract_suspended = models.BooleanField(
        default=False,
        verbose_name='Permitir chamado com contrato suspenso',
        help_text=(
            'Se desativado (padrão), clientes com contrato suspenso não abrem chamado '
            'técnico no fluxo de atendimento (chatbot).'
        ),
    )
    suspended_contract_ticket_message = models.TextField(
        blank=True,
        default='',
        verbose_name='Mensagem ao bloquear chamado (contrato suspenso)',
        help_text='Mensagem ao cliente quando o chamado é bloqueado. Vazio = padrão do sistema.',
    )
    send_financial_menu_after_suspended_block = models.BooleanField(
        default=False,
        verbose_name='Enviar menu financeiro após bloquear chamado (suspenso)',
        help_text=(
            'Se ativado, após a mensagem de bloqueio o chatbot envia o menu financeiro '
            'do fluxo (2ª via, liberação por confiança, etc.), quando existir no fluxo ativo.'
        ),
    )
    auto_resolve_keyword_filter_enabled = models.BooleanField(
        default=False,
        verbose_name='Filtrar mensagens automáticas',
        help_text=(
            'Quando ligado, mensagens automáticas de confirmação de pagamento '
            'enviadas por integração externa não reabrem atendimentos já encerrados pelo chatbot.'
        ),
    )
    auto_resolve_keywords = models.TextField(
        blank=True,
        default='',
        verbose_name='Termos do filtro',
        help_text='Um termo por linha. Obrigatório quando o filtro estiver ligado.',
    )
    ai_inform_hours_after_comprovante_transfer = models.BooleanField(
        default=False,
        verbose_name='Informar horário após comprovante',
        help_text=(
            'Se ativado e as regras da base de conhecimento levarem a uma transferência '
            'após comprovante fora do expediente, a IA pode informar horário/feriado. '
            'Desativado (padrão): a IA segue a base de conhecimento do provedor e não '
            'informa horário de funcionamento ao cliente após o comprovante.'
        ),
    )
    chatbot_name = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Nome do chatbot',
        help_text=(
            'Nome exibido no canto superior das mensagens automáticas do bot '
            'em todos os canais (WhatsApp, Telegram, Instagram, etc.).'
        ),
    )
    invoice_intro_message_template = models.TextField(
        blank=True,
        default='',
        verbose_name='Texto do card da fatura',
        help_text=(
            'Texto do body do card de pagamento (WhatsApp Oficial / order_details). '
            'Vazio = padrão do sistema. Variáveis: {{vencimento}}, {{valor}}, '
            '{{valor_original}}, {{multa}}, {{juros}}, {{valores_texto}}, '
            '{{fatura_id}}, {{nome_cliente}}, {{nome_provedor}}, {{instrucoes}}.'
        ),
    )

    # Campos para Integração Asaas
    cpf_cnpj = models.CharField(max_length=20, null=True, blank=True, verbose_name='CPF/CNPJ')
    phone = models.CharField(max_length=20, null=True, blank=True, verbose_name='Telefone Fixo')
    mobile_phone = models.CharField(max_length=20, null=True, blank=True, verbose_name='Celular')
    address_number = models.CharField(max_length=20, null=True, blank=True, verbose_name='Número')
    complement = models.CharField(max_length=255, null=True, blank=True, verbose_name='Complemento')
    province = models.CharField(max_length=100, null=True, blank=True, verbose_name='Bairro')
    postal_code = models.CharField(max_length=20, null=True, blank=True, verbose_name='CEP')
    group_name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Grupo')
    company = models.CharField(max_length=200, null=True, blank=True, verbose_name='Nome da Empresa (Asaas)')
    municipal_inscription = models.CharField(max_length=30, null=True, blank=True, verbose_name='Inscrição Municipal')
    state_inscription = models.CharField(max_length=30, null=True, blank=True, verbose_name='Inscrição Estadual')
    observations = models.TextField(null=True, blank=True, verbose_name='Observações')
    additional_emails = models.TextField(null=True, blank=True, verbose_name='E-mails Adicionais', help_text='Separados por vírgula')
    notification_disabled = models.BooleanField(default=False, verbose_name='Notificações Desativadas')
    foreign_customer = models.BooleanField(default=False, verbose_name='Cliente Estrangeiro')
    asaas_customer_id = models.CharField(max_length=50, null=True, blank=True, verbose_name='Asaas Customer ID')
    
    # Assinaturas Asaas
    asaas_subscription_id = models.CharField(max_length=50, null=True, blank=True, verbose_name='Asaas Subscription ID')
    subscription_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Valor da Mensalidade')
    subscription_cycle = models.CharField(max_length=20, null=True, blank=True, verbose_name='Ciclo de Faturamento')
    subscription_billing_type = models.CharField(max_length=20, null=True, blank=True, verbose_name='Forma de Pagamento')
    subscription_status = models.CharField(max_length=50, null=True, blank=True, verbose_name='Status da Assinatura')
    subscription_next_due_date = models.DateField(null=True, blank=True, verbose_name='Próximo Vencimento')
    block_reason = models.TextField(null=True, blank=True, verbose_name='Motivo do Bloqueio')
    sgp_webhook_token = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Token webhook SGP (disparos)',
        help_text='Token único para o SGP autenticar webhooks de disparo de cobrança neste provedor.',
    )

    class Meta:
        verbose_name = 'Provedor'
        verbose_name_plural = 'Provedores'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Label(models.Model):
    name = models.CharField(max_length=100, verbose_name='Nome')
    color = models.CharField(max_length=7, default='#007bff', verbose_name='Cor', help_text='Cor em formato hexadecimal (ex: #007bff)')
    description = models.TextField(null=True, blank=True, verbose_name='Descrição')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='labels', verbose_name='Empresa', null=True, blank=True)
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='labels', verbose_name='Provedor', null=True, blank=True)

    class Meta:
        verbose_name = 'Rótulo'
        verbose_name_plural = 'Rótulos'

    def __str__(self):
        return self.name


class SystemConfig(models.Model):
    key = models.CharField(max_length=255, unique=True, verbose_name='Chave', default='', blank=True)
    value = models.TextField(verbose_name='Valor', default='', blank=True)
    description = models.TextField(null=True, blank=True, verbose_name='Descrição')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sgp_app = models.CharField(max_length=200, null=True, blank=True, verbose_name='SGP App')
    sgp_token = models.CharField(max_length=500, null=True, blank=True, verbose_name='SGP Token')
    sgp_url = models.URLField(null=True, blank=True, verbose_name='SGP URL')
    hetzner_api_token = models.TextField(null=True, blank=True, verbose_name='Hetzner API Token')
    google_api_key = models.CharField(max_length=255, null=True, blank=True, verbose_name='Google API Key')
    openai_transcription_api_key = models.CharField(max_length=255, null=True, blank=True, verbose_name='OpenAI Transcription API Key', help_text='Chave da API OpenAI exclusivamente para transcrição de áudio. Não será usada para geração de respostas.')
    
    # Asaas Global Config
    asaas_access_token = models.CharField(max_length=255, null=True, blank=True, verbose_name='Asaas Access Token')
    asaas_webhook_auth_token = models.CharField(max_length=255, null=True, blank=True, verbose_name='Asaas Webhook Auth Token')
    asaas_sandbox = models.BooleanField(default=True, verbose_name='Asaas Sandbox Mode')

    # Canal de cobranca exclusivo do superadmin (WhatsApp Oficial)
    billing_channel_enabled = models.BooleanField(default=False, verbose_name='Canal de Cobranca Ativo')
    billing_whatsapp_token = models.TextField(null=True, blank=True, verbose_name='Billing WhatsApp Access Token')
    billing_whatsapp_phone_number_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='Billing Phone Number ID')
    billing_whatsapp_waba_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='Billing WABA ID')
    billing_days_before_due = models.IntegerField(default=3, verbose_name='Dias Antes do Vencimento')
    billing_reminder_due_offsets = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Dias de cobrança em relação ao vencimento',
        help_text='Lista separada por vírgula. Negativos/zero = antes ou no vencimento; positivos = dias após vencido. Vazio = usa só o campo legado “dias antes”.',
    )
    billing_run_window_minutes = models.SmallIntegerField(
        default=0,
        verbose_name='Margem em minutos após o horário (0 = minuto exato)',
        help_text='0 = roda só no minuto escolhido (ex.: 08:30). Maior que 0 = aceita até N minutos depois, se a tarefa atrasar.',
    )
    billing_provedor_auto_block_enabled = models.BooleanField(
        default=True,
        verbose_name='Bloquear provedor automaticamente (Asaas)',
        help_text='Consulta cobranças OVERDUE da assinatura no Asaas e suspende o acesso do provedor após o número de dias configurado.',
    )
    billing_provedor_block_min_days_late = models.PositiveSmallIntegerField(
        default=4,
        verbose_name='Dias após o vencimento para bloquear o provedor',
        help_text='0 = com qualquer atraso em relação ao vencimento. 4 = igual à regra antiga (só bloqueava com “mais de 3 dias” de atraso).',
    )
    billing_run_time = models.CharField(max_length=5, default='09:00', verbose_name='Horario da Rotina (HH:MM)')
    billing_run_days = models.CharField(max_length=20, default='0,1,2,3,4,5,6', verbose_name='Dias da Semana da Rotina')
    billing_template_due_soon = models.TextField(
        default='Olá {{nome}}, sua fatura de {{valor}} vence em {{vencimento}} (ID: {{fatura_id}}).',
        blank=True,
        verbose_name='Mensagem para Fatura a Vencer'
    )
    billing_template_overdue = models.TextField(
        default='Olá {{nome}}, sua fatura {{fatura_id}} de {{valor}} venceu em {{vencimento}}. Evite bloqueio realizando o pagamento.',
        blank=True,
        verbose_name='Mensagem para Fatura Vencida'
    )
    billing_whatsapp_use_template = models.BooleanField(
        default=True,
        verbose_name='Usar template Meta na automação de cobrança',
    )
    billing_whatsapp_template_name = models.CharField(
        max_length=120,
        default='cobranca_order',
        blank=True,
        verbose_name='Nome do template Meta (cobrança)',
    )
    billing_whatsapp_template_language = models.CharField(
        max_length=20,
        default='pt_BR',
        blank=True,
        verbose_name='Idioma do template (cobrança)',
    )

    class Meta:
        verbose_name = 'Configuração do Sistema'
        verbose_name_plural = 'Configurações do Sistema'

    def __str__(self):
        return f"{self.key}: {self.value[:50]}..."


class Canal(models.Model):
    TIPO_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('whatsapp_session', 'WhatsApp QR code'),
        ('whatsapp_oficial', 'WhatsApp Oficial'),
        ('telegram', 'Telegram'),
        ('email', 'Email'),
        ('webchat', 'WebChat'),
        ('instagram', 'Instagram'),
        ('app_mobile', 'Aplicativo'),
    ]
    
    nome = models.CharField(max_length=100, default='')
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES, default='whatsapp')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='canais')
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    dados_extras = models.JSONField(default=dict, blank=True)
    verification_code = models.CharField(max_length=20, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    
    # Campos específicos para Telegram
    api_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='API ID')
    api_hash = models.CharField(max_length=500, null=True, blank=True, verbose_name='Hash da API')
    app_title = models.CharField(max_length=200, null=True, blank=True, verbose_name='App Title')
    short_name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Short Name')
    
    # Campos específicos para WhatsApp Oficial (Cloud API)
    waba_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='WABA ID')
    phone_number_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='Phone Number ID')
    token = models.TextField(null=True, blank=True, verbose_name='Access Token')
    status = models.CharField(max_length=20, default='connected', verbose_name='Status')
    
    # Campo para controlar se a IA está ativa neste canal
    ia_ativa = models.BooleanField(default=True, verbose_name='IA Ativa', help_text='Se desativado, a IA não responderá automaticamente neste canal, mas o provedor ainda poderá enviar e receber mensagens normalmente.')

    # Canal usado só para disparos (cobrança/templates): sem chatbot/timeout automático e sem protocolo ao cliente
    somente_disparo = models.BooleanField(
        default=False,
        verbose_name='Somente disparo',
        help_text=(
            'Se ativo, este canal é tratado como canal de disparo: não gera protocolo e '
            'não aplica timeout/transferência automática do chatbot.'
        ),
    )
    DISPARO_RESPOSTA_FILA = 'fila'
    DISPARO_RESPOSTA_ENCERRAR = 'encerrar'
    DISPARO_RESPOSTA_CHOICES = [
        (DISPARO_RESPOSTA_FILA, 'Enviar para fila humana'),
        (DISPARO_RESPOSTA_ENCERRAR, 'Ignorar e manter encerrado'),
    ]
    disparo_resposta_acao = models.CharField(
        max_length=20,
        choices=DISPARO_RESPOSTA_CHOICES,
        default=DISPARO_RESPOSTA_FILA,
        verbose_name='Ao responder no canal de disparo',
        help_text=(
            'Só vale com “Somente disparo” ativo. '
            '“fila”: envia para fila humana. '
            '“encerrar”: ignora a mensagem do cliente (não grava, sem CSAT, sem reabrir).'
        ),
    )

    class Meta:
        verbose_name = 'Canal'
        verbose_name_plural = 'Canais'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.tipo})"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create', 'Criar'),
        ('edit', 'Editar'),
        ('delete', 'Deletar'),
        ('view', 'Visualizar'),
        ('export', 'Exportar'),
        ('import', 'Importar'),
        ('transfer', 'Transferir'),
        ('close', 'Fechar'),
        ('open', 'Abrir'),
        ('assign', 'Atribuir'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Usuário')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, verbose_name='Ação')
    details = models.TextField(verbose_name='Detalhes', default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='Endereço IP')
    user_agent = models.TextField(null=True, blank=True, verbose_name='User Agent')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Data/Hora')
    provedor = models.ForeignKey(Provedor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Provedor')
    channel_type = models.CharField(max_length=50, null=True, blank=True, verbose_name='Tipo de Canal')
    contact_name = models.CharField(max_length=255, null=True, blank=True, verbose_name='Nome do Contato')
    conversation_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='ID da Conversa')
    csat_rating = models.IntegerField(null=True, blank=True, verbose_name='Avaliação CSAT')

    class Meta:
        verbose_name = 'Log de Auditoria'
        verbose_name_plural = 'Logs de Auditoria'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} - {self.user} - {self.timestamp}"


class MensagemSistema(models.Model):
    # Campos antigos (usados pelo serializer e frontend)
    assunto = models.CharField(max_length=200, verbose_name='Assunto', default='', blank=True)
    mensagem = models.TextField(verbose_name='Mensagem', default='', blank=True)
    imagem_url = models.URLField(max_length=1000, blank=True, default='', verbose_name='URL da imagem')
    hotspots = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Áreas clicáveis na imagem',
        help_text='[{x,y,w,h,url,label}] em % (0-100).',
    )
    cta_links = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Botões / links',
        help_text='[{label,url}].',
    )
    provedores = models.JSONField(default=list, verbose_name='Provedores (IDs)')
    provedores_count = models.IntegerField(default=0, verbose_name='Quantidade de Provedores')
    visualizacoes = models.JSONField(default=dict, verbose_name='Visualizações')
    visualizacoes_count = models.IntegerField(default=0, verbose_name='Quantidade de Visualizações')
    visivel_para_agentes = models.BooleanField(default=True, verbose_name='Visível para Atendentes')
    # ID da mensagem no superadmin (para confirmação de leitura)
    superadmin_message_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='ID mensagem Superadmin',
    )
    
    # Campos novos (mantidos para compatibilidade)
    titulo = models.CharField(max_length=200, verbose_name='Título', default='', blank=True)
    conteudo = models.TextField(verbose_name='Conteúdo', default='', blank=True)
    tipo = models.CharField(max_length=50, choices=[
        ('notificacao', 'Notificação'),
        ('aviso', 'Aviso'),
        ('manutencao', 'Manutenção'),
        ('info', 'Informação'),
        ('warning', 'Aviso'),
        ('error', 'Erro'),
        ('success', 'Sucesso'),
        ('info', 'Informação'),
    ], default='notificacao', verbose_name='Tipo')
    ativa = models.BooleanField(default=True, verbose_name='Ativa')
    data_inicio = models.DateTimeField(null=True, blank=True, verbose_name='Data de Início')
    data_fim = models.DateTimeField(null=True, blank=True, verbose_name='Data de Fim')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='mensagens_sistema', null=True, blank=True, verbose_name='Provedor')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mensagem do Sistema'
        verbose_name_plural = 'Mensagens do Sistema'
        ordering = ['-created_at']

    def marcar_visualizada(self, user_id):
        """Marca mensagem como visualizada por um usuário"""
        if str(user_id) not in self.visualizacoes:
            self.visualizacoes[str(user_id)] = {
                'timestamp': timezone.now().isoformat(),
                'user_id': user_id
            }
            self.visualizacoes_count = len(self.visualizacoes)
            self.save()

    def __str__(self):
        return self.assunto or self.titulo or 'Mensagem sem título'

class ChatbotFlow(models.Model):
    name = models.CharField(max_length=200, verbose_name='Nome do Fluxo')
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='chatbot_flows', verbose_name='Provedor')
    canal = models.ForeignKey(Canal, on_delete=models.SET_NULL, null=True, blank=True, related_name='chatbot_flows', verbose_name='Canal')
    nodes = models.JSONField(default=list, blank=True, verbose_name='Nós do Fluxo')
    edges = models.JSONField(default=list, blank=True, verbose_name='Conexões do Fluxo')
    is_active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Fluxo de Chatbot'
        verbose_name_plural = 'Fluxos de Chatbot'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.provedor.nome})"


class Plano(models.Model):
    """Planos de internet cadastrados pelo provedor"""
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='planos_cadastrados', verbose_name='Provedor')
    nome = models.CharField(max_length=200, verbose_name='Nome do Plano')
    descricao = models.TextField(blank=True, default='', verbose_name='Descrição')
    velocidade_download = models.CharField(max_length=50, blank=True, default='', verbose_name='Velocidade Download')
    velocidade_upload = models.CharField(max_length=50, blank=True, default='', verbose_name='Velocidade Upload')
    preco = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Preço (R$)')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    ordem = models.IntegerField(default=0, verbose_name='Ordem de Exibição')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plano de Internet'
        verbose_name_plural = 'Planos de Internet'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f"{self.nome} - R${self.preco} ({self.provedor.nome})"


class RespostaRapida(models.Model):
    """Respostas rápidas pré-cadastradas para uso no atendimento"""
    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name='respostas_rapidas',
        verbose_name='Provedor'
    )
    titulo = models.CharField(
        max_length=100,
        verbose_name='Título / Atalho',
        help_text='Ex: Fatura, Saudação, Horário — usado para filtrar com /'
    )
    conteudo = models.TextField(
        verbose_name='Conteúdo da Resposta',
        help_text='Texto completo que será enviado ao cliente'
    )
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='respostas_rapidas_criadas',
        verbose_name='Criado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Resposta Rápida'
        verbose_name_plural = 'Respostas Rápidas'
        ordering = ['titulo']

    def __str__(self):
        return f"{self.titulo} ({self.provedor.nome})"


class ProviderGalleryImage(models.Model):
    """Imagens da galeria do provedor para uso em fluxos do chatbot."""
    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name='gallery_images',
        verbose_name='Provedor'
    )
    nome = models.CharField(max_length=120, verbose_name='Nome do arquivo')
    imagem = models.ImageField(upload_to=provider_gallery_upload_to, verbose_name='Imagem')
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gallery_images_created',
        verbose_name='Criado por'
    )
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    arquivo_db = models.BinaryField(null=True, blank=True, verbose_name='Conteúdo do Arquivo (DB)')
    mime_type = models.CharField(max_length=100, null=True, blank=True, verbose_name='Tipo MIME')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Imagem da Galeria'
        verbose_name_plural = 'Galeria de Imagens'
        ordering = ['nome', '-created_at']

    def __str__(self):
        return f"{self.nome} ({self.provedor.nome})"


class UserReminder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reminders')
    contact = models.ForeignKey('conversations.Contact', on_delete=models.SET_NULL, null=True, blank=True, related_name='reminders')
    message = models.TextField(verbose_name='Mensagem do Lembrete')
    scheduled_time = models.DateTimeField(verbose_name='Data/Hora Agendada')
    is_notified = models.BooleanField(default=False, verbose_name='Já Notificado')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lembrete de Usuário'
        verbose_name_plural = 'Lembretes de Usuários'
        ordering = ['scheduled_time']

    def __str__(self):
        return f"Lembrete para {self.user.username} - {self.scheduled_time}"


class ProviderSuggestion(models.Model):
    """Sugestoes / ideias dos provedores para o produto NioHub."""
    STATUS_CHOICES = [
        ('analise', 'Em analise'),
        ('desenvolvimento', 'Em desenvolvimento'),
        ('concluido', 'Concluido'),
    ]

    provedor = models.ForeignKey(
        Provedor,
        on_delete=models.CASCADE,
        related_name='suggestions',
        verbose_name='Provedor',
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suggestions_created',
        verbose_name='Criado por',
    )
    title = models.CharField(max_length=200, verbose_name='Titulo')
    description = models.TextField(verbose_name='Descricao')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='analise',
        verbose_name='Status',
    )
    votes_count = models.PositiveIntegerField(default=0, verbose_name='Votos')
    comments_count = models.PositiveIntegerField(default=0, verbose_name='Comentarios')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sugestao NioHub'
        verbose_name_plural = 'Sugestoes NioHub'
        ordering = ['-votes_count', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class ProviderSuggestionVote(models.Model):
    suggestion = models.ForeignKey(
        ProviderSuggestion,
        on_delete=models.CASCADE,
        related_name='votes',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='suggestion_votes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Voto em Sugestao'
        verbose_name_plural = 'Votos em Sugestoes'
        unique_together = [('suggestion', 'user')]

    def __str__(self):
        return f"Voto de {self.user_id} em {self.suggestion_id}"

