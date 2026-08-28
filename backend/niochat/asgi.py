"""
ASGI config for niochat project.

"""


import os
import sys
import logging

# Patch supports_color ANTES de importar Django
def safe_supports_color():
    """Versão segura de supports_color que não falha quando stdout está fechado"""
    try:
        if not hasattr(sys.stdout, 'isatty'):
            return False
        try:
            return sys.stdout.isatty()
        except (ValueError, AttributeError, OSError):
            return False
    except Exception:
        return False

try:
    import django.core.management.color
    django.core.management.color.supports_color = safe_supports_color
except (ImportError, AttributeError):
    pass

# Patch do Daphne server para evitar erro com streams fechados no access logging
# A abordagem mais simples: modificar o método log_action diretamente
try:
    import daphne.server
    
    # Salvar o método original log_action
    _original_log_action = daphne.server.Server.log_action
    
    def safe_log_action(self, protocol, action, details):
        """Versão segura de log_action que não falha quando o stream está fechado"""
        try:
            return _original_log_action(self, protocol, action, details)
        except (ValueError, AttributeError, OSError, IOError):
            # Se o stream estiver fechado, simplesmente ignorar o erro de logging
            pass
    
    # Substituir o método log_action pela versão segura
    daphne.server.Server.log_action = safe_log_action
    
except (ImportError, AttributeError, TypeError):
    # Se não conseguir importar ou modificar, não fazer nada
    pass

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "niochat.settings")

# Carrega a aplicação HTTP do Django
# Usar lazy loading para evitar problemas na inicialização
try:
    django_asgi_app = get_asgi_application()
except Exception as e:
    # Não fazer raise para permitir que o servidor continue mesmo se ASGI falhar
    # O runserver usa WSGI, então ASGI não é crítico
    import sys
    if 'runserver' not in sys.argv:
        raise
    django_asgi_app = None

# Importar routing apenas após Django estar inicializado
try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from conversations.routing import websocket_urlpatterns
except Exception as e:
    # Criar routing vazio para não quebrar o servidor
    websocket_urlpatterns = []
    from channels.routing import ProtocolTypeRouter, URLRouter




# ==========================

# Middleware custom de Token

# ==========================

from core.middleware.ws_auth import TokenAuthMiddlewareStack




# ==========================

# ASGI Routing (Final)

# ==========================


try:
    if django_asgi_app is None:
        # Se django_asgi_app falhou, criar uma aplicação dummy
        async def dummy_app(scope, receive, send):
            from django.http import HttpResponse
            response = HttpResponse("ASGI não disponível", status=503)
            await send({
                'type': 'http.response.start',
                'status': 503,
                'headers': [[b'content-type', b'text/plain; charset=utf-8']],
            })
            await send({
                'type': 'http.response.body',
                'body': 'ASGI não disponível'.encode('utf-8'),
            })
        django_asgi_app = dummy_app
    
    # Criar aplicação base
    base_application = ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": TokenAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    })
    
    # ==========================================================
    # INICIALIZAR WORKER DO TELEGRAM NO STARTUP DO ASGI
    # ==========================================================
    _telegram_worker_started = False
    
    async def startup_telegram_worker():
        """Inicia o worker do Telegram em background"""
        global _telegram_worker_started
        if _telegram_worker_started:
            return
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("[TELEGRAM WORKER] Iniciando worker do Telegram...")
            
            from integrations.telegram_service import telegram_manager
            import asyncio
            
            # Iniciar todas as integrações Telegram em background
            # O método start_all_integrations já cria tasks em background internamente
            await telegram_manager.start_all_integrations()
            _telegram_worker_started = True
            logger.info("[TELEGRAM WORKER] Worker do Telegram iniciado com sucesso!")
        except Exception as e:
            # Log do erro mas não fazer raise para não impedir o servidor de iniciar
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[TELEGRAM WORKER] Erro ao iniciar worker do Telegram: {e}", exc_info=True)
    
    async def shutdown_telegram_worker():
        """Para o worker do Telegram no shutdown do ASGI"""
        global _telegram_worker_started
        if not _telegram_worker_started:
            return
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("[TELEGRAM WORKER] Parando worker do Telegram...")
            
            from integrations.telegram_service import telegram_manager
            
            # Parar todas as integrações
            await telegram_manager.stop_all_integrations()
            _telegram_worker_started = False
            logger.info("[TELEGRAM WORKER] Worker do Telegram parado com sucesso!")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[TELEGRAM WORKER] Erro ao parar worker do Telegram: {e}", exc_info=True)
    
    # Wrapper ASGI com lifecycle events e inicialização lazy
    async def asgi_app_with_lifecycle(scope, receive, send):
        """Wrapper ASGI que gerencia lifecycle events e inicia worker lazy"""
        if scope["type"] == "lifespan":
            import logging
            logger = logging.getLogger(__name__)
            logger.info("[TELEGRAM WORKER] Lifespan event detectado")
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await startup_telegram_worker()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await shutdown_telegram_worker()
                    await send({"type": "lifespan.shutdown.complete"})
                    break
        else:
            # Inicialização lazy: se o worker ainda não foi iniciado, iniciar agora
            # (para casos onde o servidor não suporta lifespan events)
            if not _telegram_worker_started:
                import asyncio
                import logging
                logger = logging.getLogger(__name__)
                logger.info("[TELEGRAM WORKER] Inicialização lazy - iniciando worker do Telegram...")
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Se o loop já está rodando, criar task em background
                        logger.info("[TELEGRAM WORKER] Loop já está rodando, criando task em background...")
                        asyncio.create_task(startup_telegram_worker())
                    else:
                        # Se não está rodando, iniciar diretamente
                        logger.info("[TELEGRAM WORKER] Loop não está rodando, iniciando diretamente...")
                        await startup_telegram_worker()
                except Exception as e:
                    # Se falhar, tentar iniciar em background de qualquer forma
                    logger.warning(f"[TELEGRAM WORKER] Erro na inicialização lazy: {e}, tentando em background...")
                    try:
                        asyncio.create_task(startup_telegram_worker())
                    except Exception as e2:
                        logger.error(f"[TELEGRAM WORKER] Erro ao criar task em background: {e2}", exc_info=True)
            
            # Para HTTP e WebSocket, usar a aplicação base
            await base_application(scope, receive, send)
    
    application = asgi_app_with_lifecycle

    # Cobrança superadmin + finalize closing no mesmo processo do Daphne (sem worker Dramatiq obrigatório)
    try:
        from niochat.asgi_periodic import start_inline_periodic_tasks

        start_inline_periodic_tasks()
    except Exception as periodic_err:
        logging.getLogger(__name__).warning(
            "[ASGI periodic] não iniciado: %s", periodic_err, exc_info=True
        )
except Exception as e:
    # Não fazer raise - permitir que o servidor continue
    import sys
    if 'runserver' not in sys.argv:
        raise
    # Criar aplicação básica sem lifecycle
    application = base_application if 'base_application' in locals() else django_asgi_app
    try:
        from niochat.asgi_periodic import start_inline_periodic_tasks

        start_inline_periodic_tasks()
    except Exception:
        pass
