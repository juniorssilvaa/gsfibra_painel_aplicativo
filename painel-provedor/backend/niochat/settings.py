"""
Django settings for niochat project.
"""

# ============================================
# CORREÇÃO CRÍTICA: Sobrescrever supports_color ANTES DE QUALQUER COISA
# ============================================
# Isso DEVE ser feito antes de importar qualquer módulo do Django
# para evitar erro quando stdout está fechado (comum com Daphne)
import sys

def safe_supports_color_wrapper():
    """Wrapper seguro para supports_color que não falha quando stdout está fechado"""
    try:
        # Tentar verificar se stdout está disponível de forma segura
        if not hasattr(sys.stdout, 'isatty'):
            return False
        try:
            return sys.stdout.isatty()
        except (ValueError, AttributeError, OSError):
            return False
    except Exception:
        return False

# Sobrescrever a função ANTES de importar Django
# Isso evita o erro "I/O operation on closed file" quando o Django tenta usar cores
try:
    import django.core.management.color
    django.core.management.color.supports_color = safe_supports_color_wrapper
except (ImportError, AttributeError):
    # Se Django ainda não foi importado, vamos fazer isso depois
    pass

# ============================================
# IMPORTS PADRÃO
# ============================================
from pathlib import Path
import dj_database_url
from decouple import Csv
import logging
from django.core.exceptions import ImproperlyConfigured

# ============================================
# BASE
# ============================================

__version__ = "2.77.1"
__version_info__ = (2, 77, 1)

# Compatibilidade legado
VERSION = "2.77.1"
BASE_DIR = Path(__file__).resolve().parent.parent

# Sempre usar config que prioriza variáveis de ambiente sobre arquivo .env
# Isso é importante para Docker/Portainer onde variáveis vêm do ambiente
# O decouple procura automaticamente o .env no diretório atual e nos diretórios pais
# Quando o Django é iniciado via manage.py ou daphne, o diretório de trabalho é backend/
# então o .env em backend/.env será encontrado automaticamente
from decouple import config

SECRET_KEY = config('SECRET_KEY', default='django-insecure-temp-key')
DEBUG = config('DEBUG', default=False, cast=bool)

ENVIRONMENT = config('ENVIRONMENT', default='development')

ALLOWED_HOSTS = list(config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost,app.niohub.com.br,api.niohub.com.br,api-local.niohub.com.br,chat-local.niohub.com.br,docs.niohub.com.br',
    cast=Csv()
))

# Multi-tenant: aceitar qualquer subdomínio de niohub.com.br
if '.niohub.com.br' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.niohub.com.br')

# Feature flag para resolução de tenant por subdomínio.
# Safe by default: mantém o comportamento legado até ativar via .env.
SUBDOMAIN_TENANT_ENABLED = config('SUBDOMAIN_TENANT_ENABLED', default=False, cast=bool)
SUBDOMAIN_PRIMARY_DOMAINS = list(config(
    'SUBDOMAIN_PRIMARY_DOMAINS',
    default='niohub.com.br',
    cast=Csv()
))
SUBDOMAIN_RESERVED_LABELS = list(config(
    'SUBDOMAIN_RESERVED_LABELS',
    default='www,api,chat,docs,admin,front,api-local,chat-local,localhost',
    cast=Csv()
))
SUBDOMAIN_TENANT_CACHE_TTL = config('SUBDOMAIN_TENANT_CACHE_TTL', default=300, cast=int)

# ============================================
# APPS
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'channels',
    'django_filters',

    # Local apps
    'core',
    'conversations.apps.ConversationsConfig',  # Usar AppConfig para garantir importação de dramatiq_tasks
    'integrations.apps.IntegrationsConfig',  # Usar AppConfig para garantir importação de dramatiq_tasks
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',

    # Custom middleware ANTES do SecurityMiddleware para interceptar health check
    'niochat.middleware.HealthCheckExemptMiddleware',
    
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',

    # Custom middlewares
    'niochat.middleware.NgrokHostMiddleware',
    'niochat.middleware.TenantContextMiddleware',
    'niochat.middleware.PreventAuthRedirectMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.provedor_suspension.ProvedorSuspensionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.db_connections.CloseDatabaseConnectionsMiddleware',
]

ROOT_URLCONF = 'niochat.urls'

# ============================================
# TEMPLATES
# ============================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'niochat.wsgi.application'
ASGI_APPLICATION = 'niochat.asgi.application'

# ============================================
# DATABASE
# ============================================
# 1) Se POSTGRES_* vier definido (recomendado em Docker/Portainer), usa configuração direta.
# 2) Caso contrário, mantém compatibilidade com DATABASE_URL.
POSTGRES_DB = config("POSTGRES_DB", default="")
POSTGRES_USER = config("POSTGRES_USER", default="")
POSTGRES_PASSWORD = config("POSTGRES_PASSWORD", default="")
POSTGRES_HOST = config("POSTGRES_HOST", default="")
POSTGRES_PORT = config("POSTGRES_PORT", default="5432")

if ENVIRONMENT == "production":
    _stack_name = (
        config("DOCKER_STACK_NAME", default="").strip()
        or config("TRAEFIK_ROUTER_PREFIX", default="").strip()
    )
    if _stack_name and POSTGRES_HOST in ("", "postgres"):
        POSTGRES_HOST = f"{_stack_name}_postgres"

if POSTGRES_DB:
    if not POSTGRES_HOST:
        if ENVIRONMENT == "production":
            raise ImproperlyConfigured(
                "POSTGRES_HOST ausente em produção. Defina POSTGRES_HOST no ambiente para evitar fallback em localhost."
            )
        POSTGRES_HOST = "localhost"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": POSTGRES_DB,
            "USER": POSTGRES_USER,
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": POSTGRES_HOST,
            "PORT": POSTGRES_PORT,
            "CONN_MAX_AGE": config(
                "POSTGRES_CONN_MAX_AGE",
                default=0 if ENVIRONMENT == "production" else 0,
                cast=int,
            ),
        }
    }
else:
    # Fallback inteligente: SQLite para desenvolvimento.
    # Em produção, exige DATABASE_URL explícito para não cair em localhost.
    DEFAULT_DB_URL = "sqlite:///" + str(BASE_DIR / "db.sqlite3") if ENVIRONMENT == "development" else ""
    database_url = config("DATABASE_URL", default=DEFAULT_DB_URL)
    if ENVIRONMENT == "production" and not database_url:
        raise ImproperlyConfigured(
            "Banco não configurado em produção. Defina POSTGRES_DB/USER/PASSWORD/HOST/PORT ou DATABASE_URL."
        )
    DATABASES = {
        "default": dj_database_url.config(
            default=database_url,
            conn_max_age=config(
                "POSTGRES_CONN_MAX_AGE",
                default=0 if ENVIRONMENT == "production" else 0,
                cast=int,
            ),
        )
    }

# connect_timeout é uma opção específica do PostgreSQL e causa erro no SQLite
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    # keepalives: reduz ligações TCP “mortas” atrás de LB / NAT sem fechar CONN_MAX_AGE cedo demais
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": int(config("POSTGRES_CONNECT_TIMEOUT", default=10)),
        "keepalives": 1,
        "keepalives_idle": int(config("POSTGRES_KEEPALIVES_IDLE", default=30)),
        "keepalives_interval": int(config("POSTGRES_KEEPALIVES_INTERVAL", default=10)),
        "keepalives_count": int(config("POSTGRES_KEEPALIVES_COUNT", default=5)),
    }

# ============================================
# PASSWORD VALIDATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Belem'
USE_I18N = True
USE_TZ = True

# ============================================
# STATIC / MEDIA
# ============================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Segurança: tickets WS/SSE e URLs de mídia assinadas
REALTIME_TICKET_MAX_AGE = config('REALTIME_TICKET_MAX_AGE', default=90, cast=int)
REALTIME_ALLOW_LEGACY_TOKEN_QUERY = config('REALTIME_ALLOW_LEGACY_TOKEN_QUERY', default=False, cast=bool)
MEDIA_SIGNED_URL_TTL = config('MEDIA_SIGNED_URL_TTL', default=86400, cast=int)
MEDIA_SIGNED_URL_TTL_EXTERNAL = config('MEDIA_SIGNED_URL_TTL_EXTERNAL', default=604800, cast=int)
MEDIA_REQUIRE_SIGNED_URL = config('MEDIA_REQUIRE_SIGNED_URL', default=True, cast=bool)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# DRF
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.authentication.LoggedTokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'core.permissions.ProvedorNotSuspended',
    ],
    # ETAPA 2 e 3: Paginação controlada (removido PAGE_SIZE = 4000)
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.DefaultPagination',
}

# ============================================
# CORS / CSRF
# ============================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Origens fixas permitidas (superadmin e local dev)
REQUIRED_CORS_ORIGINS = [
    'https://app.niohub.com.br',
    'https://api.niohub.com.br',
    'https://connect.niohub.com.br',
    'https://docs.niohub.com.br',
    'https://api-local.niohub.com.br',
    'https://chat-local.niohub.com.br',
]

cors_from_env = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:8010,http://localhost:8012,http://localhost:3000,https://api.niohub.com.br,https://api-local.niohub.com.br,https://chat-local.niohub.com.br',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

CORS_ALLOWED_ORIGINS = list(set(cors_from_env + REQUIRED_CORS_ORIGINS))

csrf_from_env = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8010,http://localhost:8012,http://localhost:3000,https://api.niohub.com.br,https://api-local.niohub.com.br,https://chat-local.niohub.com.br',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

CSRF_TRUSTED_ORIGINS = list(set(csrf_from_env + REQUIRED_CORS_ORIGINS))

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'connection',
    'upgrade',
]

CORS_EXPOSE_HEADERS = ['Content-Type', 'Authorization']

# ============================================
# SECURITY / PROXY (INTELIGENTE)
# ============================================

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

if ENVIRONMENT == "production":
    # Backend atrás do Traefik com HTTPS real
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

elif ENVIRONMENT == "staging":
    # Caso o backend venha a ser exposto pelo Túnel Cloudflare
    SECURE_PROXY_SSL_HEADER = ('HTTP_CF_VISITOR', '{"scheme":"https"}')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

else:  # development
    # Desenvolvimento local (com ou sem Cloudflare Tunnel)
    SECURE_PROXY_SSL_HEADER = None
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOWED_ORIGINS.extend([
        "http://127.0.0.1",
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8010",
        "http://localhost:8012",
        "https://*.trycloudflare.com"
    ])

    CSRF_TRUSTED_ORIGINS.extend([
        "http://127.0.0.1",
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8010",
        "http://localhost:8012",
        "https://*.trycloudflare.com"
    ])

# ============================================
# CHANNELS / REDIS
# ============================================

# Variáveis Redis para uso em outros módulos
# IMPORTANTE: Todas as configurações DEVEM vir do .env
# O decouple procura o .env no diretório atual ou no diretório pai
# Valores padrão para testes/GitHub Actions (devem ser sobrescritos no .env em produção)
REDIS_HOST = config('REDIS_HOST', default='localhost')  # Obrigatório no .env (padrão para testes)
if ENVIRONMENT == "production":
    _stack_name = (
        config("DOCKER_STACK_NAME", default="").strip()
        or config("TRAEFIK_ROUTER_PREFIX", default="").strip()
    )
    if _stack_name and REDIS_HOST in ("", "redis", "localhost"):
        REDIS_HOST = f"{_stack_name}_redis"
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)  # Obrigatório no .env (padrão para testes)
REDIS_PASSWORD = config('REDIS_PASSWORD', default='')  # Opcional (pode ser vazio)
REDIS_DB = config('REDIS_DB', default='0', cast=int)  # Opcional (padrão: 0)
REDIS_USERNAME = config('REDIS_USERNAME', default='')  # Opcional (pode ser vazio)

LOCAL_DEV = config('LOCAL_DEV', default='0').lower() in ('1', 'true', 'yes', 'on')
USE_INMEMORY_CHANNEL_LAYER = (
    LOCAL_DEV
    or config('CHANNEL_LAYER_BACKEND', default='').lower() == 'inmemory'
)

if USE_INMEMORY_CHANNEL_LAYER:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [{
                    'host': REDIS_HOST,
                    'port': REDIS_PORT,
                    'password': REDIS_PASSWORD if REDIS_PASSWORD else None,
                    'db': REDIS_DB,
                }],
                'capacity': 1500,
                'expiry': 10,
                'group_expiry': 1800,
            },
        },
    }

# ============================================
# TELEGRAM
# ============================================
TELEGRAM_API_ID = config('TELEGRAM_API_ID', default='')
TELEGRAM_API_HASH = config('TELEGRAM_API_HASH', default='')

# ============================================
# META / FACEBOOK
# ============================================
FACEBOOK_APP_SECRET = config('FACEBOOK_APP_SECRET', default='')
# Instagram: definido após _env() — variáveis injectadas pelo Docker/Portainer
# Token de verificação do webhook do WhatsApp Cloud API
# Deve ser configurado no painel da Meta e aqui no .env
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config('WHATSAPP_WEBHOOK_VERIFY_TOKEN', default='niochat_webhook_verify_token')

# Token do Sistema da Meta (System User Token) para operações administrativas (ex: inscrever apps)
WHATSAPP_SYSTEM_USER_TOKEN = config('WHATSAPP_SYSTEM_USER_TOKEN', default='')

# ============================================
# URLs DO SISTEMA (FONTE ÚNICA DE VERDADE)
# ============================================
# IMPORTANTE: Estas URLs são usadas para OAuth e webhooks.
# BACKEND_URL: URL do backend (usado para redirect_uri do OAuth)
# FRONTEND_URL: URL do frontend (usado para redirecionamentos após OAuth)
#
# POR QUE ESTAS CONFIGURAÇÕES SÃO IMPORTANTES:
# - O redirect_uri do OAuth DEVE ser exatamente igual ao configurado no Meta App Dashboard
# - Se BACKEND_URL não estiver configurado, o OAuth falhará com erro explícito (fail fast)
# - NUNCA usar localhost em produção (a função get_backend_url() valida isso)
#
# Configuração no .env:
# BACKEND_URL=https://api.niohub.com.br
# FRONTEND_URL=https://chat.niohub.com.br
# (valores definidos após _env() — prioridade Docker/Portainer sobre .env da imagem)
# ============================================

# ============================================
# SUPERADMIN (lookup de provedor_id para niohub + integrações)
# ============================================
# IMPORTANTE: python-decouple's AutoConfig, ao encontrar qualquer ficheiro .env na
# hierarquia, lê APENAS esse ficheiro e ignora os.environ completamente.
# Para variáveis críticas injectadas pelo Docker/Portainer usamos os.environ.get()
# como prioridade máxima, com config() como fallback para desenvolvimento local.
import os as _os

def _env(key, default=''):
    """Lê variável de ambiente: os.environ tem prioridade sobre decouple/ficheiro .env."""
    return (_os.environ.get(key) or config(key, default=default) or default).strip()


def _tenant_url_from_subdomain() -> str:
    """URL pública do tenant (FE + API no mesmo host), injectada pelo Portainer via SUBDOMAIN."""
    subdomain = _env('SUBDOMAIN')
    if not subdomain:
        return ''
    if subdomain.startswith('http://') or subdomain.startswith('https://'):
        return subdomain.rstrip('/')
    return f'https://{subdomain}'.rstrip('/')


_tenant_public_url = _tenant_url_from_subdomain()

SUPERADMIN_ID_PROVEDOR_API = _env('SUPERADMIN_ID_PROVEDOR_API').rstrip('/')
SUPERADMIN_RESOLVE_API_URL = _env('SUPERADMIN_RESOLVE_API_URL').rstrip('/')
SUPERADMIN_API_URL = _env('SUPERADMIN_API_URL').rstrip('/')
SUPERADMIN_PROVEDOR_ID = _env('SUPERADMIN_PROVEDOR_ID')
SUPERADMIN_PROVIDER_TOKEN = _env('SUPERADMIN_PROVIDER_TOKEN')
AWESOMEAPI_TOKEN = _env('AWESOMEAPI_TOKEN')
ADMIN_WEBHOOK_SECRET = _env('ADMIN_WEBHOOK_SECRET')

# NioHub Calls — voz WhatsApp (QR), independente da API oficial Meta
NIOHUB_CALLS_BASE_URL = _env('NIOHUB_CALLS_BASE_URL', '')
NIOHUB_CALLS_API_KEY = _env('NIOHUB_CALLS_API_KEY', '')
# URL interna do Django para webhooks do Go (rede Docker Swarm, ex.: http://stack_niochat-backend:8010)
NIOHUB_CALLS_WEBHOOK_SELF_URL = _env('NIOHUB_CALLS_WEBHOOK_SELF_URL', '')

# Instagram Business Login — credenciais injectadas pelo superadmin (Portainer)
INSTAGRAM_APP_ID = _env('INSTAGRAM_APP_ID')
INSTAGRAM_APP_SECRET = _env('INSTAGRAM_APP_SECRET')

# URLs: prioridade env explícito → SUBDOMAIN do Portainer → vazio (resolvido em runtime pela request)
BACKEND_URL = _env('BACKEND_URL') or _tenant_public_url
FRONTEND_URL = _env('FRONTEND_URL') or _tenant_public_url

# NioHub Calls — defaults automáticos em produção (Swarm), igual Postgres/Redis.
if ENVIRONMENT == "production":
    from urllib.parse import urlparse as _urlparse

    _voice_stack = (
        config("DOCKER_STACK_NAME", default="").strip()
        or config("TRAEFIK_ROUTER_PREFIX", default="").strip()
    )
    if _voice_stack and not (NIOHUB_CALLS_BASE_URL or "").strip():
        NIOHUB_CALLS_BASE_URL = f"http://{_voice_stack}_niohub-calls:8080"

    _public_tenant = (BACKEND_URL or FRONTEND_URL or _tenant_public_url or "").strip().rstrip("/")
    _webhook_host = (_urlparse((NIOHUB_CALLS_WEBHOOK_SELF_URL or "").strip()).hostname or "").lower()
    if _public_tenant and (not (NIOHUB_CALLS_WEBHOOK_SELF_URL or "").strip() or "_" in _webhook_host):
        NIOHUB_CALLS_WEBHOOK_SELF_URL = _public_tenant

if DEBUG and not SUPERADMIN_API_URL and not SUPERADMIN_ID_PROVEDOR_API:
    SUPERADMIN_API_URL = 'http://127.0.0.1:8010'

# ============================================
# EMAIL
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default='587', cast=lambda v: int(v) if v else 587)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default='True', cast=lambda v: v.lower() == 'true' if v else True)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# ============================================
# REDIS EXTRA
# ============================================
# Construir REDIS_URL de forma segura
# Se REDIS_URL estiver no .env, usa diretamente. Senão, constrói a partir das variáveis individuais
REDIS_URL_ENV = config('REDIS_URL', default='')
if REDIS_URL_ENV:
    REDIS_URL = REDIS_URL_ENV
elif REDIS_USERNAME and REDIS_PASSWORD:
    REDIS_URL = f"redis://{REDIS_USERNAME}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
elif REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# ============================================
# CUSTOM USER
# ============================================
AUTH_USER_MODEL = 'core.User'
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']
APPEND_SLASH = False

# ============================================
# SUPABASE
# ============================================
SUPABASE_URL = _env('SUPABASE_URL')
SUPABASE_ANON_KEY = _env('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_ROLE_KEY = config('SUPABASE_SERVICE_ROLE_KEY', default='')
SUPABASE_AUDIT_TABLE = config('SUPABASE_AUDIT_TABLE', default='auditoria')
SUPABASE_MESSAGES_TABLE = config('SUPABASE_MESSAGES_TABLE', default='mensagens')
SUPABASE_CSAT_TABLE = config('SUPABASE_CSAT_TABLE', default='csat_feedback')
SUPABASE_CONTACTS_TABLE = config('SUPABASE_CONTACTS_TABLE', default='contacts')
SUPABASE_CONVERSATIONS_TABLE = config('SUPABASE_CONVERSATIONS_TABLE', default='conversations')

# Conversas encerradas ficam no banco local até a rotina noturna (00:00) migrar ao Supabase.
# False volta ao comportamento antigo (migra e remove do local logo ao encerrar).
DEFER_CLOSED_MIGRATION = config('DEFER_CLOSED_MIGRATION', default=True, cast=bool)

# Aprendizado da IA: sugestões geradas pelo LLM do provedor (usa a chave de IA dele).
# O limite é de atendimentos analisados por provedor por dia.
AI_LEARNING_SUGGESTIONS_ENABLED = config('AI_LEARNING_SUGGESTIONS_ENABLED', default=True, cast=bool)
AI_LEARNING_DAILY_LIMIT = config('AI_LEARNING_DAILY_LIMIT', default=30, cast=int)
AI_LEARNING_AUTO_APPROVE_SAFE = config('AI_LEARNING_AUTO_APPROVE_SAFE', default=True, cast=bool)

# Desative com SUPABASE_ENABLED=False quando a VPS não tiver acesso ao Supabase.
# Por padrão é True apenas se SUPABASE_URL estiver configurado.
_supabase_enabled_env = _env('SUPABASE_ENABLED')
SUPABASE_ENABLED = (
    _supabase_enabled_env.lower() not in ('false', '0', 'no', 'off')
    if _supabase_enabled_env
    else bool(SUPABASE_URL)
)
# Timeout padrão para chamadas HTTP ao Supabase (segundos).
# Reduza para 2 se a VPS tiver latência alta ou acesso instável.
SUPABASE_REQUEST_TIMEOUT = int(_env('SUPABASE_REQUEST_TIMEOUT') or '3')


# ============================================
# LOGGING
# ============================================
# Configuração de logging que trata stdout fechado (comum ao usar Daphne)
# Garantir que supports_color está sobrescrito antes de configurar LOGGING
try:
    import django.core.management.color
    django.core.management.color.supports_color = safe_supports_color_wrapper
except (ImportError, AttributeError):
    pass


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s',
        },
        'django.server': {
            'format': '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'django.server': {
            'class': 'logging.StreamHandler',
            'formatter': 'django.server',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['django.server'],
            'level': 'INFO',
            'propagate': False,
        },
        'niochat': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,  # CORRIGIDO: False evita duplicação de logs
        },
        'conversations': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'integrations': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ============================================
# SENTRY (monitoramento de erros e performance)
# ============================================
# Funciona em produção com DEBUG=False: basta definir SENTRY_DSN e ENVIRONMENT no .env.
# Em desenvolvimento, deixe SENTRY_DSN vazio para não enviar eventos.
SENTRY_DSN = config('SENTRY_DSN', default='')
SENTRY_TEST_KEY = config('SENTRY_TEST_KEY', default='')  # para /api/sentry-test/?key= em produção
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    # Captura logs como breadcrumbs (INFO e acima); ERROR vira evento
    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR,
    )

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,  # ex: production, development
        release=VERSION,
        integrations=[
            DjangoIntegration(),
            RedisIntegration(),
            sentry_logging,
        ],
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        profiles_sample_rate=config('SENTRY_PROFILES_SAMPLE_RATE', default=0.0, cast=float),
        send_default_pii=config('SENTRY_SEND_PII', default=False, cast=bool),
        debug=DEBUG,  # só afeta logs no console; eventos são enviados com DEBUG=True ou False
    )

