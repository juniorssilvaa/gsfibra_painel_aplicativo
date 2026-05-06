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

# ============================================
# BASE
# ============================================

__version__ = "2.38.1"
__version_info__ = (2, 38, 1)

# Compatibilidade legado
VERSION = "2.38.1"
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
    default='127.0.0.1,localhost,api.niohub.com.br,api-local.niohub.com.br,chat.niohub.com.br,chat-local.niohub.com.br,docs.niohub.com.br',
    cast=Csv()
))

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
    'niochat.middleware.PreventAuthRedirectMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
# Fallback inteligente: SQLite para desenvolvimento, Postgres para produção
DEFAULT_DB_URL = "sqlite:///" + str(BASE_DIR / "db.sqlite3") if ENVIRONMENT == "development" else "postgresql://niochat_user:password@localhost:5432/niochat"

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL", default=DEFAULT_DB_URL),
        conn_max_age=60 if ENVIRONMENT == "production" else 0,
    )
}

# connect_timeout é uma opção específica do PostgreSQL e causa erro no SQLite
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": 5,
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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# DRF
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',  # ETAPA 5: Mudar de AllowAny para IsAuthenticated
    ],
    # ETAPA 2 e 3: Paginação controlada (removido PAGE_SIZE = 4000)
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.DefaultPagination',
}

# ============================================
# CORS / CSRF
# ============================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Origem fixa da produção
REQUIRED_CORS_ORIGINS = [
    'https://chat.niohub.com.br',
    'https://api.niohub.com.br',
    'https://docs.niohub.com.br',
    'https://api-local.niohub.com.br',
    'https://chat-local.niohub.com.br',
]

cors_from_env = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:8010,http://localhost:8012,http://localhost:3000,https://chat.niohub.com.br,https://api.niohub.com.br,https://api-local.niohub.com.br,https://chat-local.niohub.com.br',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

CORS_ALLOWED_ORIGINS = list(set(cors_from_env + REQUIRED_CORS_ORIGINS))

csrf_from_env = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8010,http://localhost:8012,http://localhost:3000,https://chat.niohub.com.br,https://api.niohub.com.br,https://api-local.niohub.com.br,https://chat-local.niohub.com.br',
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
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)  # Obrigatório no .env (padrão para testes)
REDIS_PASSWORD = config('REDIS_PASSWORD', default='')  # Opcional (pode ser vazio)
REDIS_DB = config('REDIS_DB', default='0', cast=int)  # Opcional (padrão: 0)
REDIS_USERNAME = config('REDIS_USERNAME', default='')  # Opcional (pode ser vazio)

# Validação: garantir que não está usando localhost
if REDIS_HOST in ('localhost', '127.0.0.1', '::1'):
    import warnings
    warnings.warn(
        f"⚠️  REDIS_HOST está configurado como '{REDIS_HOST}'. "
        f"Configure um IP válido no .env: REDIS_HOST=seu_ip_aqui",
        UserWarning
    )

# Configuração do Channel Layers
# Parâmetros válidos para RedisChannelLayer: hosts, capacity, expiry, prefix, group_expiry
# O channel_layer só será validado quando realmente usado (lazy loading)
# IMPORTANTE: Usar sempre as variáveis do .env, nunca localhost
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            # Usar formato de dicionário para garantir que use as configurações do .env
            # NUNCA usar localhost - sempre usar REDIS_HOST do .env
            'hosts': [{
                'host': REDIS_HOST,  # Do .env (obrigatório)
                'port': REDIS_PORT,   # Do .env (obrigatório)
                'password': REDIS_PASSWORD if REDIS_PASSWORD else None,  # Do .env (opcional)
                'db': REDIS_DB,       # Do .env (opcional, padrão: 0)
            }],
            'capacity': 1500,
            'expiry': 10,
            'group_expiry': 1800,  # TTL dos grupos no Redis: 30 minutos (1800 segundos)
            # Nota: channel_layer_timeout, socket_connect_timeout, socket_timeout e retry_on_timeout
            # não são parâmetros válidos para RedisChannelLayer
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
# ============================================
BACKEND_URL = config('BACKEND_URL', default='https://api.niohub.com.br')
FRONTEND_URL = config('FRONTEND_URL', default='https://chat.niohub.com.br')

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
SUPABASE_URL = config('SUPABASE_URL', default='')
SUPABASE_ANON_KEY = config('SUPABASE_ANON_KEY', default='')
SUPABASE_SERVICE_ROLE_KEY = config('SUPABASE_SERVICE_ROLE_KEY', default='')  # Chave com mais permissões para operações administrativas
SUPABASE_AUDIT_TABLE = config('SUPABASE_AUDIT_TABLE', default='auditoria')
SUPABASE_MESSAGES_TABLE = config('SUPABASE_MESSAGES_TABLE', default='mensagens')
SUPABASE_CSAT_TABLE = config('SUPABASE_CSAT_TABLE', default='csat_feedback')


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

