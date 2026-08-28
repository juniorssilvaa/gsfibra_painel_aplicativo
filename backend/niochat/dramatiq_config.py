"""
Configuração central do Dramatiq + RabbitMQ (PRODUÇÃO)

✔ Corrige fallback para localhost:5672
✔ Corrige uso incorreto de host/port/credentials
✔ Corrige SSL/TLS com CA customizada
✔ Garante que o broker seja criado APENAS UMA VEZ
✔ Compatível com Docker / VPS / AWS
"""

import os
import ssl
from pathlib import Path
from urllib.parse import urlparse, unquote

import dramatiq
from decouple import Config, RepositoryEnv
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from dramatiq.brokers.stub import StubBroker

# Importar pika apenas quando necessário (lazy import)
pika = None

# Tentar importar Django settings, mas não falhar se não estiver configurado
try:
    from django.conf import settings
    DJANGO_CONFIGURED = settings.configured
    # Obter BASE_DIR do Django para encontrar o .env
    BASE_DIR = Path(settings.BASE_DIR if hasattr(settings, 'BASE_DIR') else __file__).resolve().parent.parent
except Exception:
    DJANGO_CONFIGURED = False
    # Tentar encontrar o .env no diretório backend (parent de niochat)
    BASE_DIR = Path(__file__).resolve().parent.parent
    # Criar um objeto mock para settings se Django não estiver configurado
    class MockSettings:
        REDIS_URL = ""
        REDIS_HOST = "localhost"
        REDIS_PORT = 6379
        REDIS_PASSWORD = ""
        REDIS_DB = 1
    settings = MockSettings()

# Configurar decouple para usar o arquivo .env no diretório backend
ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    env_config = Config(RepositoryEnv(ENV_FILE))
else:
    # Fallback: usar decouple padrão (procura no diretório atual e parent)
    from decouple import config as env_config
from dramatiq.middleware import (
    AgeLimit,
    Callbacks,
    Pipelines,
    Prometheus,
    Retries,
    TimeLimit,
)
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend


class DjangoMiddleware(dramatiq.Middleware):
    """
    Middleware Dramatiq para garantir que as conexões com o banco de dados
    sejam fechadas após cada tarefa, respeitando o CONN_MAX_AGE do Django.
    Isso é vital para evitar "too many clients already" no PostgreSQL.
    """
    def after_process_message(self, broker, message, *, result=None, exception=None):
        try:
            from django.db import connections
            for conn in connections.all():
                conn.close_if_unusable_or_obsolete()
        except Exception:
            pass


# =============================================================================
# 1️⃣ LEITURA DA URL DO BROKER (OBRIGATÓRIA)
# =============================================================================
# ❌ Antes: Dramatiq criava broker automático (localhost)
# ✅ Agora: falha imediatamente se não estiver configurado

# Verificar se estamos em modo de desenvolvimento
ENVIRONMENT = os.getenv("ENVIRONMENT", env_config("ENVIRONMENT", default="development"))
DEBUG_MODE = os.getenv("DEBUG", env_config("DEBUG", default="False")).lower() == "true"
IS_DEVELOPMENT = ENVIRONMENT.lower() == "development" or DEBUG_MODE

DRAMATIQ_BROKER_URL = (
    os.getenv("DRAMATIQ_BROKER_URL")
    or env_config("DRAMATIQ_BROKER_URL", default="")
)

# Em desenvolvimento, permitir usar StubBroker se não houver configuração
USE_STUB_BROKER = False
if not DRAMATIQ_BROKER_URL:
    if IS_DEVELOPMENT:
        # Em desenvolvimento, usar StubBroker (não requer RabbitMQ)
        USE_STUB_BROKER = True
        print("⚠️  Modo desenvolvimento: usando StubBroker (RabbitMQ não necessário)")
    else:
        raise RuntimeError(
            "DRAMATIQ_BROKER_URL não configurado.\n"
            "Exemplo correto:\n"
            "amqps://usuario:senha@rabbitmq.niohub.com.br:5671/"
        )

if USE_STUB_BROKER:
    # Usar StubBroker para desenvolvimento (não requer RabbitMQ)
    broker = StubBroker()
    parsed_url = None
    is_ssl = False
else:
    parsed_url = urlparse(DRAMATIQ_BROKER_URL)
    
    # ❌ Antes: aceitava localhost silenciosamente
    # ✅ Agora: bloqueia localhost em produção (mas permite em desenvolvimento e hostnames Docker)
    # Permitir hostnames como 'rabbitmq' (comum em Docker) mesmo em produção
    is_localhost = parsed_url.hostname in ("localhost", "127.0.0.1", "::1")
    is_docker_hostname = parsed_url.hostname == "rabbitmq"  # Nome comum de serviço Docker
    
    if not IS_DEVELOPMENT and is_localhost and not is_docker_hostname:
        raise RuntimeError(
            "RabbitMQ NÃO pode usar localhost em produção. "
            "Use o domínio/IP correto."
        )

    is_ssl = parsed_url.scheme == "amqps"

# =============================================================================
# 2️⃣ CONFIGURAÇÃO CORRETA DO SSL (TLS)
# =============================================================================
# ❌ Antes: uso incorreto de pika.SSLOptions
# ❌ Antes: Dramatiq ignorava SSL e caía em fallback
# ✅ Agora: SSLContext puro (forma SUPORTADA pelo Dramatiq)

ssl_context = None

if not USE_STUB_BROKER and is_ssl:
    ca_cert_path = env_config("RABBITMQ_SSL_CA_CERT", default="")

    if ca_cert_path:
        # 🔐 Produção segura com CA
        ssl_context = ssl.create_default_context(cafile=ca_cert_path)
    else:
        # ⚠️ Fallback APENAS para dev/teste
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

# =============================================================================
# 3️⃣ CRIAÇÃO DO BROKER (FORMA CORRETA)
# =============================================================================
# ❌ Antes: host/port/credentials → fallback interno
# ✅ Agora: URL COMPLETA (sem SSL) ou parâmetros explícitos (com SSL)

if not USE_STUB_BROKER:
    # Importar pika apenas quando necessário
    if pika is None:
        import pika
    
    try:
        if is_ssl and ssl_context:
            # Com SSL: usar parâmetros explícitos
            host = parsed_url.hostname
            port = parsed_url.port or 5671
            username = parsed_url.username or "guest"
            password = unquote(parsed_url.password or "guest")
            virtual_host = parsed_url.path[1:] if parsed_url.path and len(parsed_url.path) > 1 else "/"
            
            broker = RabbitmqBroker(
                host=host,
                port=port,
                credentials=pika.PlainCredentials(username, password),
                virtual_host=virtual_host,
                ssl_options=pika.SSLOptions(ssl_context),
                confirm_delivery=True,
                # 🛠 Estabilidade máxima para conexões em nuvem
                heartbeat=60,  
                connection_attempts=10,
                retry_delay=10,
                socket_timeout=30,
                blocked_connection_timeout=60
            )
        else:
            # Sem SSL: usar parâmetros explícitos
            host = parsed_url.hostname
            port = parsed_url.port or 5672
            username = parsed_url.username or "guest"
            password = unquote(parsed_url.password or "guest")
            virtual_host = unquote(parsed_url.path[1:]) if parsed_url.path and len(parsed_url.path) > 1 else "/"
            
            broker = RabbitmqBroker(
                host=host,
                port=port,
                credentials=pika.PlainCredentials(username, password),
                virtual_host=virtual_host,
                confirm_delivery=True,
                # Configurações de estabilidade
                heartbeat=60,
                connection_attempts=10,
                retry_delay=10,
                socket_timeout=30,
                blocked_connection_timeout=60
            )
    except Exception as e:
        raise RuntimeError(f"Erro ao criar RabbitMQ Broker: {e}") from e

# =============================================================================
# 4️⃣ BACKEND DE RESULTADOS (REDIS)
# =============================================================================

# Obter configuração do Redis
try:
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        redis_host = getattr(settings, "REDIS_HOST", "localhost")
        redis_port = getattr(settings, "REDIS_PORT", 6379)
        redis_password = getattr(settings, "REDIS_PASSWORD", "")
        redis_db = getattr(settings, "REDIS_DB", 0)
        
        if redis_password:
            redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
except (AttributeError, TypeError):
    redis_url = env_config("REDIS_URL", default="")
    if not redis_url:
        redis_host = env_config("REDIS_HOST", default="localhost")
        redis_port = env_config("REDIS_PORT", default=6379, cast=int)
        redis_password = env_config("REDIS_PASSWORD", default="")
        redis_db = env_config("REDIS_DB", default=0, cast=int)
        
        if redis_password:
            redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

parsed_redis = urlparse(redis_url)

redis_backend_host = parsed_redis.hostname
redis_backend_port = parsed_redis.port or 6379
redis_backend_password = parsed_redis.password or ""
redis_backend_db = int(parsed_redis.path[1:]) if parsed_redis.path and len(parsed_redis.path) > 1 else 0

results_backend = RedisBackend(
    host=redis_backend_host,
    port=redis_backend_port,
    password=redis_backend_password,
    db=redis_backend_db,
)

# =============================================================================
# 5️⃣ MIDDLEWARES (CONFIÁVEIS PARA PRODUÇÃO)
# =============================================================================

if not USE_STUB_BROKER:
    existing_middleware_types = {type(m) for m in broker.middleware}

    if AgeLimit not in existing_middleware_types:
        broker.add_middleware(AgeLimit(max_age=86_400_000))

    if TimeLimit not in existing_middleware_types:
        broker.add_middleware(TimeLimit(time_limit=1_800_000))

    if Callbacks not in existing_middleware_types:
        broker.add_middleware(Callbacks())

    if Pipelines not in existing_middleware_types:
        broker.add_middleware(Pipelines())

    if Prometheus not in existing_middleware_types:
        broker.add_middleware(Prometheus())

    if Retries not in existing_middleware_types:
        broker.add_middleware(
            Retries(
                max_retries=10,
                min_backoff=30_000,
                max_backoff=900_000,
            )
        )

    if Results not in existing_middleware_types:
        broker.add_middleware(Results(backend=results_backend))

    if DjangoMiddleware not in existing_middleware_types:
        broker.add_middleware(DjangoMiddleware())

# =============================================================================
# 6️⃣ REGISTRO GLOBAL DO BROKER (CRÍTICO)
# =============================================================================

dramatiq.set_broker(broker)

# =============================================================================
# 7️⃣ AGENDADOR INTERNO (CRON HEARTBEAT)
# =============================================================================

# Enfileira finalize_closing + cobrança superadmin a cada ~60s (útil com worker Dramatiq).
# O Daphne também dispara a mesma lógica em processo via niochat.asgi_periodic (sem fila).
# RUN_HEARTBEAT=true exige broker + worker; senão as mensagens ficam na fila.
RUN_HEARTBEAT = os.getenv("RUN_HEARTBEAT", "false").lower() == "true"

if RUN_HEARTBEAT:
    import threading
    import time
    from django.utils import timezone

    def heartbeat_worker():
        """Thread que dispara tarefas periódicas a cada 120 segundos"""
        print("💓 [HEARTBEAT] Iniciando agendador interno de tarefas periódicas...")
        
        # Esperar um pouco para o Django terminar de carregar
        time.sleep(15) 
        
        while True:
            try:
                from conversations.dramatiq_tasks import finalize_closing_conversations
                from integrations.dramatiq_tasks import send_superadmin_billing_reminders
                print(f"💓 [HEARTBEAT] {timezone.now()} - Disparando tarefa de encerramento automático...")
                finalize_closing_conversations.send()
                send_superadmin_billing_reminders.send()
            except Exception as e:
                print(f"💓 [HEARTBEAT] Erro ao disparar tarefa periódica: {e}")
            
            time.sleep(60)

    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    heartbeat_thread.start()
