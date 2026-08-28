import urllib.parse
import logging
import time
from collections import defaultdict
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

# Cache para rate limiting de logs de token inválido
# Evita spam de logs para o mesmo token
_invalid_token_log_cache = defaultdict(lambda: {'count': 0, 'last_log': 0})
INVALID_TOKEN_LOG_THROTTLE_SECONDS = 60  # Logar no máximo 1 vez por minuto por token


class TokenAuthMiddleware:
    """
    Middleware ASGI para autenticação de WebSocket via token na querystring.
    Compatível com Channels 4 e Django 5.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Apenas processar WebSocket connections
        if scope["type"] != "websocket":
            return await self.inner(scope, receive, send)

        # Obter query string
        query_string = scope.get("query_string", b"").decode("utf-8")
        params = dict(urllib.parse.parse_qsl(query_string))

        token_key = params.get("token")
        
        # Log para debug
        if token_key:
            logger.debug(f"WebSocket: Tentando autenticar com token: {token_key[:20]}...")

        if token_key:
            try:
                user = await self.get_user_from_token(token_key)
                if user and user.is_active:
                    # Token válido e usuário ativo - autenticar usuário
                    scope["user"] = user
                    logger.debug(f"WebSocket autenticado: user_id={user.id}, username={user.username}, user_type={getattr(user, 'user_type', 'N/A')}")
                else:
                    # Token inválido ou usuário inativo
                    # Rate limiting: logar apenas uma vez por minuto por token
                    now = time.time()
                    token_cache_key = token_key[:20]  # Usar primeiros 20 chars como chave
                    cache_entry = _invalid_token_log_cache[token_cache_key]
                    
                    # Rate limiting: não logar repetidamente o mesmo token inválido
                    if now - cache_entry['last_log'] >= INVALID_TOKEN_LOG_THROTTLE_SECONDS:
                        logger.warning(f"WebSocket: Token inválido ou usuário inativo (token: {token_cache_key}...)")
                        cache_entry['last_log'] = now
                        cache_entry['count'] = 0
                    else:
                        cache_entry['count'] += 1
                    
                    # Definir como AnonymousUser - o consumer vai verificar e fechar
                    scope["user"] = AnonymousUser()
            except Exception as e:
                logger.error(f"Erro ao autenticar token WebSocket: {e}", exc_info=True)
                scope["user"] = AnonymousUser()
        else:
            # Sem token na querystring - definir como AnonymousUser
            logger.debug("WebSocket: Conexão sem token - definindo AnonymousUser")
            scope["user"] = AnonymousUser()

        # Sempre chamar inner - o consumer vai verificar user.is_authenticated e fechar se necessário
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """Busca o usuário a partir do token"""
        try:
            # Usar get() com tratamento de exceção específico
            token = Token.objects.select_related("user").get(key=token_key)
            if token.user.is_active:
                logger.debug(f"Token válido encontrado: user_id={token.user.id}, username={token.user.username}")
                return token.user
            else:
                logger.warning(f"Token encontrado mas usuário inativo: user_id={token.user.id}")
                return None
        except Token.DoesNotExist:
            logger.debug(f"Token não encontrado no banco: {token_key[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar token: {e}", exc_info=True)
            return None


def TokenAuthMiddlewareStack(inner):
    """
    Stack de middlewares para WebSocket.
    Usa TokenAuthMiddleware + AuthMiddlewareStack (para compatibilidade com sessões)
    """
    from channels.auth import AuthMiddlewareStack
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))

