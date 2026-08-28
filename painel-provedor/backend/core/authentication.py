import logging
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class LoggedTokenAuthentication(TokenAuthentication):
    """
    TokenAuthentication padrão do DRF.
    """
    
    def authenticate(self, request):
        try:
            result = super().authenticate(request)
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f"[AUTH] Erro inesperado na autenticação: {e}", exc_info=True)
            raise
        if result is None:
            return None
        user, token = result
        from core.login_provedor_access import api_access_denied_message_for_user

        denied = api_access_denied_message_for_user(user)
        if denied:
            raise AuthenticationFailed(denied)
        return user, token
