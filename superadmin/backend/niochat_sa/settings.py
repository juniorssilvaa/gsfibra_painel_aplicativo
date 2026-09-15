import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_env_file = BASE_DIR / '.env'
if _env_file.is_file():
    try:
        from decouple import Config, RepositoryEnv
        _env_config = Config(RepositoryEnv(str(_env_file)))

        def _env(key, default=''):
            val = _env_config(key, default=default)
            return '' if val is None else str(val).strip()
    except Exception:
        def _env(key, default=''):
            return os.environ.get(key, default)
else:
    def _env(key, default=''):
        return os.environ.get(key, default)

SECRET_KEY = _env('SECRET_KEY') or 'duNOiviCMS^9k^Nweqg@D%yg9&NT#p5QvR)2@ouHwrin8+HCeVjE1L^e0qesNoFL%AuI$l#ilpX!5*Wa'

DEBUG = _env('DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in _env('ALLOWED_HOSTS', '*').split(',') if h.strip()]

# Configurações para Proxy Reverso (Traefik/HTTPS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

CSRF_TRUSTED_ORIGINS = [
    'https://app.niohub.com.br',
    'https://admin.niohub.com.br',
    'https://*.niohub.com.br',
    'https://api-local.niohub.com.br',
    'http://127.0.0.1:8010',
    'http://localhost:8010',
]

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'super_core',
    'mobile_app',
    'acs',
    'channels',
]

ASGI_APPLICATION = 'niochat_sa.asgi.application'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'niochat_sa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'niochat_sa.wsgi.application'
ASGI_APPLICATION = 'niochat_sa.asgi.application'

import dj_database_url
import os

if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
elif os.environ.get('POSTGRES_HOST') or os.environ.get('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB') or 'niohub_superadmin',
            'USER': os.environ.get('POSTGRES_USER') or 'niohub',
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD') or 'NiohubSuperadmin@2026',
            'HOST': os.environ.get('POSTGRES_HOST', 'superadmin-postgres'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.superadmin.sqlite3',
        }
    }

AUTH_USER_MODEL = 'super_core.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

CORS_ALLOW_ALL_ORIGINS = True

# Meta / Facebook
# Necessário para finalizar a conexão do canal via Meta no superadmin.
FACEBOOK_APP_SECRET = _env('FACEBOOK_APP_SECRET')
INSTAGRAM_APP_ID = _env('INSTAGRAM_APP_ID')
INSTAGRAM_APP_SECRET = _env('INSTAGRAM_APP_SECRET')
ADMIN_WEBHOOK_SECRET = _env('ADMIN_WEBHOOK_SECRET')
SUPERADMIN_CI_TOKEN = _env('SUPERADMIN_CI_TOKEN') or ADMIN_WEBHOOK_SECRET
BACKEND_URL = _env('BACKEND_URL', 'https://api-local.niohub.com.br')
TENANT_WEBHOOK_BASE_URL = _env('TENANT_WEBHOOK_BASE_URL', '')
# Deve coincidir com o token configurado na Meta App e nos tenants (Portainer injeta o mesmo valor).
# Se a env vier vazia (ficheiros .env com WHATSAPP_WEBHOOK_VERIFY_TOKEN=), usar o default do painel-provedor.
WHATSAPP_WEBHOOK_VERIFY_TOKEN = (
    (os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN') or '').strip() or 'niochat_webhook_verify_token'
)
