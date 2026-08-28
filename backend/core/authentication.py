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
            return super().authenticate(request)
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f"[AUTH] Erro inesperado na autenticação: {e}", exc_info=True)
            raise
