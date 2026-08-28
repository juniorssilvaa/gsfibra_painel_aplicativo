import urllib.parse
import logging
import time
from collections import defaultdict
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from core.tenant_context import attach_tenant_context_to_scope

logger = logging.getLogger(__name__)

# Cache para rate limiting de logs de token inválido
_invalid_token_log_cache = defaultdict(lambda: {'count': 0, 'last_log': 0})
INVALID_TOKEN_LOG_THROTTLE_SECONDS = 60


class TokenAuthMiddleware:
    """
    Middleware ASGI para autenticação de WebSocket.
    Preferência: ticket de curta duração (?ticket=). Token DRF longo na query
    só é aceito se REALTIME_ALLOW_LEGACY_TOKEN_QUERY=True.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.inner(scope, receive, send)

        try:
            attach_tenant_context_to_scope(scope)
        except Exception as e:
            logger.warning("WebSocket tenant context indisponível: %s", e)
            scope["tenant_context"] = {
                "host": "",
                "subdomain": None,
                "provedor_id": None,
                "source": "none",
                "resolved": False,
            }

        query_string = scope.get("query_string", b"").decode("utf-8")
        params = dict(urllib.parse.parse_qsl(query_string))

        ticket = (params.get("ticket") or params.get("rt") or "").strip()
        token_key = (params.get("token") or "").strip()

        user = None
        if ticket:
            user = await self.get_user_from_ticket(ticket)
        elif token_key:
            from core.realtime_tickets import allow_legacy_token_query
            if allow_legacy_token_query():
                user = await self.get_user_from_token(token_key)
            else:
                logger.warning(
                    "WebSocket: token DRF na query rejeitado (use ?ticket= de /api/auth/realtime-ticket/)"
                )

        if user and user.is_active:
            scope["user"] = user
            logger.debug(
                "WebSocket autenticado: user_id=%s, username=%s",
                user.id,
                user.username,
            )
        else:
            if ticket or token_key:
                now = time.time()
                cache_key = (ticket or token_key)[:20]
                cache_entry = _invalid_token_log_cache[cache_key]
                if now - cache_entry['last_log'] >= INVALID_TOKEN_LOG_THROTTLE_SECONDS:
                    logger.warning("WebSocket: credencial inválida ou usuário inativo")
                    cache_entry['last_log'] = now
                    cache_entry['count'] = 0
                else:
                    cache_entry['count'] += 1
            else:
                logger.debug("WebSocket: conexão sem ticket — AnonymousUser")
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_user_from_ticket(self, ticket):
        try:
            from core.realtime_tickets import user_from_realtime_ticket
            return user_from_realtime_ticket(ticket)
        except Exception as e:
            logger.error("Erro ao validar ticket WebSocket: %s", e, exc_info=True)
            return None
        finally:
            from django.db import close_old_connections
            close_old_connections()

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        try:
            from core.auth_token_cache import user_from_token_key
            return user_from_token_key(token_key)
        except Exception as e:
            logger.error("Erro ao buscar token: %s", e, exc_info=True)
            return None
        finally:
            from django.db import close_old_connections
            close_old_connections()


def TokenAuthMiddlewareStack(inner):
    from channels.auth import AuthMiddlewareStack
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))
