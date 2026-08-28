"""
Middlewares customizados para o NioChat
"""

from django.utils.deprecation import MiddlewareMixin
from django.http import HttpRequest, HttpResponse
from django.conf import settings
import logging
from core.tenant_context import attach_tenant_context_to_request

logger = logging.getLogger(__name__)


class NgrokHostMiddleware(MiddlewareMixin):
    """
    Middleware para permitir hosts dinâmicos do ngrok e outros túneis.
    Adiciona o host automaticamente ao ALLOWED_HOSTS se não estiver lá.
    """
    
    def process_request(self, request: HttpRequest):
        # Obtém o host diretamente do META, sem validar (evita DisallowedHost)
        host = request.META.get('HTTP_HOST') or request.META.get('SERVER_NAME', '')
        
        if host:
            # Remove porta se presente
            host = host.split(':')[0]
            
            # Adiciona ao ALLOWED_HOSTS se não estiver lá
            if host not in settings.ALLOWED_HOSTS:
                # Evita adicionar hosts inválidos
                if host and (
                    host.endswith('.ngrok.io') or
                    host.endswith('.ngrok-free.app') or
                    host.endswith('.trycloudflare.com') or
                    host.startswith('localhost') or
                    host.startswith('127.0.0.1') or
                    host in ['localhost', '127.0.0.1', '0.0.0.0']
                ):
                    settings.ALLOWED_HOSTS.append(host)
        
        return None  # Continua o processamento normal


class HealthCheckExemptMiddleware(MiddlewareMixin):
    """
    Middleware para interceptar health check ANTES do SecurityMiddleware.
    Evita loop infinito de redirect HTTPS no endpoint /api/health/
    Retorna resposta direta 200 OK sem passar pelo SecurityMiddleware.
    Deve ser adicionado ANTES do SecurityMiddleware.
    """
    
    def process_request(self, request: HttpRequest):
        """
        Intercepta requisições de health check e retorna resposta direta
        ANTES do SecurityMiddleware processar (evitando redirect HTTPS).
        """
        # Obtém o path de múltiplas formas para garantir que captura
        request_path = (
            request.path or 
            request.path_info or 
            request.META.get('PATH_INFO', '') or 
            (request.META.get('REQUEST_URI', '').split('?')[0] if request.META.get('REQUEST_URI') else '')
        )
        
        # Normaliza o path removendo query string e barra final
        if request_path:
            request_path = request_path.split('?')[0].rstrip('/')
        
        # Verifica se é uma requisição de health check
        if request_path in ['/api/health', '/api/health/'] and request.method in ['GET', 'HEAD', 'OPTIONS']:
            # Retorna resposta JSON direta SEM acessar o banco de dados
            import json
            response = HttpResponse(
                json.dumps({"status": "ok"}), 
                content_type="application/json", 
                status=200
            )
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            return response
        
        return None  # Continua o processamento normal


class PreventAuthRedirectMiddleware(MiddlewareMixin):
    """
    Middleware para evitar redirecionamentos 301 em rotas críticas.
    Normaliza a URL antes do CommonMiddleware processar.
    Deve ser adicionado antes do CommonMiddleware.
    """
    
    def process_request(self, request: HttpRequest):
        # Normaliza a URL da rota de autenticação para evitar redirecionamentos
        if request.path == '/api-token-auth' and request.method == 'POST':
            # Força a URL a ter a barra final para evitar redirecionamento do CommonMiddleware
            request.path = '/api-token-auth/'
            request.path_info = '/api-token-auth/'
        
        # ===================================================================
        # 🔵 CRÍTICO: Intercepta health check e retorna resposta direta
        # Evita que passe pelo CommonMiddleware e SecurityMiddleware que causam redirecionamento 301
        # ===================================================================
        # Obtém o path de múltiplas formas para garantir que captura
        request_path = (
            request.path or 
            request.path_info or 
            request.META.get('PATH_INFO', '') or 
            (request.META.get('REQUEST_URI', '').split('?')[0] if request.META.get('REQUEST_URI') else '')
        )
        
        # Normaliza o path para a verificação
        path_to_check = request_path
        if path_to_check:
            path_to_check = path_to_check.split('?')[0].rstrip('/')
            
        # O HealthCheckExemptMiddleware já deve ter capturado isso, mas mantemos
        # aqui como redundância de segurança para rotas críticas.
        if path_to_check == '/api/health' and request.method in ['GET', 'HEAD', 'OPTIONS']:
            import json
            response = HttpResponse(
                json.dumps({"status": "ok"}), 
                content_type="application/json", 
                status=200
            )
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            return response
        
        # ===================================================================
        # 🔵 CRÍTICO: Normaliza URL do callback OAuth do Facebook
        # Com APPEND_SLASH = False, Django não redireciona automaticamente
        # O Facebook pode enviar com ou sem barra final
        # ===================================================================
        # if request.path == '/auth/facebook/callback' and request.method in ['GET', 'POST', 'HEAD']:
        #     # Força a URL a ter a barra final para garantir match com a rota
        #     request.path = '/auth/facebook/callback/'
        #     request.path_info = '/auth/facebook/callback/'
        #     request.META['PATH_INFO'] = '/auth/facebook/callback/'
        
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse):
        """
        Intercepta respostas de redirecionamento 301 para rotas críticas
        e as converte em respostas diretas sem redirecionamento.
        """
        # Se for um redirecionamento 301 relacionado ao health check, retorna resposta direta
        if response.status_code == 301:
            location = response.get('Location', '')
            request_path = request.path or request.META.get('PATH_INFO', '')
            
            # Verifica se é um redirecionamento relacionado ao health check
            if '/api/health' in location or '/api/health' in request_path or '/api/health' in str(request.path_info):
                # Retorna resposta direta ao invés de redirecionamento
                import json
                return HttpResponse(
                    json.dumps({"status": "ok"}), 
                    content_type="application/json", 
                    status=200
                )
        
        return response


class TenantContextMiddleware(MiddlewareMixin):
    """
    Resolve o tenant por subdomínio sem forçar bloqueios.
    Mantém compatibilidade com o fluxo atual por provedor_id.
    """

    def process_request(self, request: HttpRequest):
        try:
            attach_tenant_context_to_request(request)
        except Exception as exc:
            logger.warning("Falha ao resolver tenant context: %s", exc)
            request.tenant_context = {
                "host": "",
                "subdomain": None,
                "provedor_id": None,
                "source": "none",
                "resolved": False,
            }
            request.tenant_provedor_id = None
            request.tenant_subdomain = None
        return None
