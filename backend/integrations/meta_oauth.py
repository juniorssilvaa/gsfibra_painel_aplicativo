"""
Callback OAuth da Meta para WhatsApp Embedded Signup

Este módulo implementa o callback OAuth para WhatsApp Embedded Signup.
Conforme documentação oficial da Meta:
https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users

FLUXO CORRETO PARA EMBEDDED SIGNUP:
1. Meta redireciona para /api/auth/facebook/callback/ com code e state
2. Callback valida code e redireciona para frontend com sucesso
3. Frontend recebe evento FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING via postMessage
4. Frontend chama POST /api/canais/whatsapp_embedded_signup_finish/ com waba_id
5. Backend processa integração usando SYSTEM USER TOKEN (não OAuth token)

IMPORTANTE:
- NÃO fazer token exchange no callback (isso é para OAuth clássico)
- NÃO buscar WABA ID ou Phone Numbers no callback
- Apenas validar e redirecionar

Endpoint: /api/auth/facebook/callback/
"""
import requests
import logging
import json
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
from urllib.parse import urlparse, urlunparse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from core.models import Provedor, Canal

logger = logging.getLogger(__name__)

META_APP_ID = '713538217881661'
META_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', None)

FRONT_URL = getattr(settings, 'FRONTEND_URL', 'https://chat.niohub.com.br')
BACK_URL = getattr(settings, 'BACKEND_URL', 'https://api.niohub.com.br')

GRAPH_API_VERSION = 'v19.0'
PHONE_NUMBERS_API_VERSION = 'v24.0'

REQUIRED_PERMISSIONS = [
    'whatsapp_business_messaging',
    'whatsapp_business_management'
]


def get_frontend_url() -> str:
    """
    Obtém FRONTEND_URL com fallback seguro.
    Se vier configurado com domínio de API, converte para domínio de chat.
    """
    front_url = (getattr(settings, 'FRONTEND_URL', None) or FRONT_URL or 'https://chat.niohub.com.br').rstrip('/')
    try:
        parsed = urlparse(front_url)
        host = parsed.netloc or ''
        if host.startswith('api-local.'):
            host = host.replace('api-local.', 'chat-local.', 1)
        elif host.startswith('api.'):
            host = host.replace('api.', 'chat.', 1)
        normalized = urlunparse((parsed.scheme or 'https', host, parsed.path, '', '', ''))
        return normalized.rstrip('/')
    except Exception:
        return 'https://chat.niohub.com.br'


def get_backend_url() -> str:
    """Obtém a URL do backend de forma centralizada."""
    backend_url = getattr(settings, 'BACKEND_URL', None)
    
    if not backend_url:
        raise RuntimeError("BACKEND_URL não configurado no settings.")
    
    if not backend_url.startswith('http'):
        backend_url = f"https://{backend_url}"
    
    backend_url_lower = backend_url.lower()
    is_localhost = (
        'localhost' in backend_url_lower or 
        '127.0.0.1' in backend_url_lower or
        ':8010' in backend_url_lower or
        ':8000' in backend_url_lower
    )
    
    if is_localhost:
        backend_url = 'https://api.niohub.com.br'
    
    if backend_url.startswith('http://') and 'api.niohub.com.br' in backend_url:
        backend_url = backend_url.replace('http://', 'https://')
    
    return backend_url


def build_facebook_oauth_url(provider_id: int, config_id: Optional[str] = None) -> str:
    """Constrói a URL OAuth do Facebook para WhatsApp Embedded Signup."""
    # IMPORTANTE: redirect_uri DEVE corresponder exatamente ao configurado no Meta App Dashboard
    # Configurado no painel: https://api.niohub.com.br/api/auth/facebook/callback/
    backend_url = get_backend_url()
    redirect_uri = f"{backend_url}/api/auth/facebook/callback/"
    
    redirect_uri_lower = redirect_uri.lower()
    if 'localhost' in redirect_uri_lower or '127.0.0.1' in redirect_uri_lower:
        redirect_uri = "https://api.niohub.com.br/api/auth/facebook/callback/"
    
    if not config_id:
        config_id = '1888449245359692'
    
    state = f"provider_{provider_id}"
    
    extras = {
        "sessionInfoVersion": "3",
        "featureType": "whatsapp_business_app_onboarding",
        "is_hosted_es": True,
        "version": "v3"
    }
    
    params = {
        "client_id": META_APP_ID,
        "config_id": config_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "display": "popup",
        "override_default_response_type": "true",
        "extras": json.dumps(extras)
    }
    
    query_string = urlencode(params)
    oauth_url = f"https://www.facebook.com/v24.0/dialog/oauth?{query_string}"
    
    return oauth_url


@csrf_exempt
@require_http_methods(["GET", "POST", "HEAD"])
def meta_callback(request):
    """
    Callback OAuth da Meta - aceita tanto GET (redirect direto) quanto POST (do frontend)
    """
    """
    Callback OAuth da Meta para WhatsApp Embedded Signup.
    
    IMPORTANTE: Para Embedded Signup, este callback NÃO deve fazer token exchange.
    O fluxo correto é:
    1. Meta redireciona para este callback com code e state
    2. Este callback apenas valida e redireciona de volta ao frontend
    3. O frontend recebe o evento FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING via postMessage
    4. O frontend chama POST /api/canais/whatsapp_embedded_signup_finish/ com waba_id
    5. O backend processa a integração usando SYSTEM USER TOKEN
    
    Conforme documentação oficial:
    https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
    """
    frontUrl = get_frontend_url()
    if request.method == "HEAD":
        return JsonResponse({}, status=200)
    
    # Aceitar code e state tanto de GET quanto de POST (para suportar página intermediária)
    code = request.GET.get("code") or request.POST.get("code")
    state = request.GET.get("state") or request.POST.get("state")
    
    # Se for POST e não tiver code/state no body, tentar JSON
    if request.method == "POST" and not code:
        try:
            import json as json_lib
            if hasattr(request, 'body') and request.body:
                body_data = json_lib.loads(request.body)
                code = body_data.get('code') or code
                state = body_data.get('state') or state
        except:
            pass
    
    # Detectar fluxos
    is_billing_superadmin = bool(state and str(state).startswith("billing_superadmin_"))
    is_provider_flow = bool(state and str(state).startswith("provider_"))

    # Extrair provider_id do state
    provider_id = 1
    if is_provider_flow:
        try:
            provider_id = int(state.replace("provider_", ""))
        except ValueError:
            pass
    
    # Validar que code existe (obrigatório para Embedded Signup)
    if not code:
        if is_billing_superadmin:
            return redirect(f"{frontUrl}/app/superadmin/configuracoes?oauth_error=no_code")
        if is_provider_flow:
            return redirect(f"{frontUrl}/app/accounts/{provider_id}/integracoes?oauth_error=no_code")
        return redirect(f"{frontUrl}/app/superadmin/configuracoes?oauth_error=no_code")
    
    if is_provider_flow and not is_billing_superadmin:
        # Validar provedor (somente fluxo de provedor)
        try:
            provedor = Provedor.objects.get(id=provider_id)
        except Provedor.DoesNotExist:
            return redirect(f"{frontUrl}/app/accounts/1/integracoes?oauth_error=provider_not_found")

        # Verificar se já existe canal conectado (caso de retry)
        try:
            canal_existente = Canal.objects.filter(
                provedor=provedor,
                tipo="whatsapp_oficial",
                ativo=True,
                status="connected"
            ).first()

            if canal_existente:
                # Se já está conectado, redirecionar sem parâmetros (card já mostra connected)
                return redirect(f"{frontUrl}/app/accounts/{provider_id}/integracoes")
        except Exception:
            pass
    
    # Para Embedded Signup, apenas redirecionar SEM oauth_success
    # O callback OAuth NÃO significa sucesso - apenas retorno do usuário
    # O frontend receberá o evento FINISH via postMessage e chamará whatsapp_embedded_signup_finish
    # O card deve entrar em estado "processing" quando detectar code na URL
    
    # Se for POST (requisição da página intermediária), retornar JSON
    if request.method == "POST":
        # A página intermediária vai processar e redirecionar para integracoes
        if is_billing_superadmin:
            redirect_url = f"{frontUrl}/app/meta/finalizando-superadmin?code={code}&state={state}"
        else:
            redirect_url = f"{frontUrl}/app/meta/finalizando?code={code}&state={state}"
        return JsonResponse({
            'success': True,
            'redirect_url': redirect_url,
            'provider_id': provider_id,
            'message': 'Callback processado com sucesso'
        })
    
    # Detectar se deve redirecionar para localhost (debug)
    # Se o state contiver '_local', usamos o localhost
    is_local = '_local' in state if state else False
    current_front_url = "http://localhost:8012" if is_local else frontUrl
    
    if is_billing_superadmin:
        redirect_url = f"{current_front_url}/app/meta/finalizando-superadmin?code={code}&state={state}"
    else:
        redirect_url = f"{current_front_url}/app/meta/finalizando?code={code}&state={state}"
    
    # Retornar uma pequena página HTML que avisa o término. 
    # Se for popup, ela pode tentar avisar a janela pai.
    html_content = f"""
    <html>
        <head><title>Finalizando...</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background: #0f172a; color: white;">
            <h2>Configuração concluída!</h2>
            <p>Você pode fechar esta janela agora.</p>
            <script>
                // Tentar avisar a janela pai via postMessage se possível
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'META_OAUTH_CALLBACK_COMPLETE',
                        code: '{code}',
                        state: '{state}'
                    }}, '*');
                }}
                // Em popup: fechar após avisar a janela pai (evita cair em URL 404 no domínio de API)
                if (window.opener) {{
                    setTimeout(function() {{
                        try {{ window.close(); }} catch (e) {{}}
                    }}, 300);
                }} else {{
                    // Sem opener (fallback): redireciona para a tela esperada no frontend
                    window.location.href = '{redirect_url}';
                }}
            </script>
        </body>
    </html>
    """
    return HttpResponse(html_content)


def exchange_code_for_short_lived_token(code: str, redirect_uri: str) -> dict:
    """Troca authorization_code por short-lived access token."""
    response = requests.get(
        "https://graph.facebook.com/v19.0/oauth/access_token",
        params={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": redirect_uri,
            "code": code
        },
        timeout=30
    )
    
    if response.status_code != 200:
        error_text = response.text
        raise Exception(f"Token exchange failed: {error_text}")
    
    token_data = response.json()
    
    if 'access_token' not in token_data:
        raise Exception("Access token not found in response")
    
    return token_data


def exchange_short_for_long_lived_token(short_lived_token: str) -> dict:
    """Troca short-lived token por long-lived access token."""
    response = requests.get(
        "https://graph.facebook.com/v19.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "fb_exchange_token": short_lived_token
        },
        timeout=30
    )
    
    if response.status_code != 200:
        error_text = response.text
        raise Exception(f"Long-lived token exchange failed: {error_text}")
    
    token_data = response.json()
    
    if 'access_token' not in token_data:
        raise Exception("Access token not found in response")
    
    return token_data


def validate_token_permissions(access_token: str) -> bool:
    """Valida se o token possui as permissões necessárias."""
    try:
        response = requests.get(
            "https://graph.facebook.com/v19.0/me/permissions",
            params={"access_token": access_token},
            timeout=30
        )
        
        if response.status_code != 200:
            return False
        
        permissions_data = response.json()
        permissions_list = permissions_data.get("data", [])
        
        granted_permissions = [
            perm.get("permission") 
            for perm in permissions_list 
            if perm.get("status") == "granted"
        ]
        
        missing_permissions = [
            perm for perm in REQUIRED_PERMISSIONS 
            if perm not in granted_permissions
        ]
        
        if missing_permissions:
            return False
        
        return True
        
    except Exception:
        return False
