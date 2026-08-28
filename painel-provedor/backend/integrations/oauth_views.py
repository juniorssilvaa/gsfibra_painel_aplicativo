"""
Views para processar OAuth callback do Meta/Facebook para WhatsApp Embedded Signup

⚠️ LEGADO - NÃO USAR
Este módulo contém um handler OAuth alternativo que não está sendo usado.
O handler ativo está em integrations/meta_oauth.py (meta_callback).

Este arquivo é mantido apenas para referência histórica.
Para novas implementações, usar meta_oauth.py.
"""
import requests
import logging
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.conf import settings
from core.models import Provedor
from .models import WhatsAppIntegration

logger = logging.getLogger(__name__)

FACEBOOK_APP_ID = '713538217881661'
# O FACEBOOK_APP_SECRET é carregado do settings.py que lê do .env.development
FACEBOOK_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', None)

if not FACEBOOK_APP_SECRET:
    logger.warning("FACEBOOK_APP_SECRET não configurado. Adicione FACEBOOK_APP_SECRET no .env.development")


@csrf_exempt
@require_http_methods(["GET"])
def whatsapp_oauth_callback(request):
    """
    Processa o callback OAuth do Facebook/Meta após o usuário autorizar o WhatsApp Embedded Signup.
    
    URL esperada: /app/oauth/callback/?code=XXXX&state=provider_X
    
    Fluxo:
    1. Recebe code e state do Facebook
    2. Extrai provider_id do state (formato: provider_X)
    3. Troca code por access_token
    4. Salva informações na integração WhatsApp
    5. Redireciona para página de integrações
    """
    try:
        # Obter parâmetros da URL
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        error_reason = request.GET.get('error_reason')
        error_description = request.GET.get('error_description')
        
        # Verificar se houve erro
        if error:
            logger.error(f"Erro no OAuth callback: {error} - {error_reason} - {error_description}")
            # Redirecionar para página de integrações com mensagem de erro
            provider_id = _extract_provider_id(state)
            if provider_id:
                return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_error={error}')
            return redirect('/app/accounts/1/integracoes?oauth_error=unknown')
        
        # Validar parâmetros obrigatórios
        if not code:
            logger.error("Código OAuth não fornecido")
            provider_id = _extract_provider_id(state)
            if provider_id:
                return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_error=no_code')
            return redirect('/app/accounts/1/integracoes?oauth_error=no_code')
        
        if not state:
            logger.error("State não fornecido")
            return redirect('/app/accounts/1/integracoes?oauth_error=no_state')
        
        # Extrair provider_id do state (formato: provider_X)
        provider_id = _extract_provider_id(state)
        if not provider_id:
            logger.error(f"State inválido: {state}")
            return redirect('/app/accounts/1/integracoes?oauth_error=invalid_state')
        
        # Buscar provedor
        try:
            provedor = Provedor.objects.get(id=provider_id)
        except Provedor.DoesNotExist:
            logger.error(f"Provedor não encontrado: {provider_id}")
            return redirect('/app/accounts/1/integracoes?oauth_error=provider_not_found')
        
        # Determinar redirect_uri usado (dev ou prod)
        is_production = request.get_host() == 'chat.niohub.com.br'
        redirect_uri = 'https://chat.niohub.com.br/app/oauth/callback/' if is_production else 'https://chat.niohub.com.br/app/oauth/callback/'
        
        # Trocar code por access_token
        token_url = 'https://graph.facebook.com/v24.0/oauth/access_token'
        token_params = {
            'client_id': FACEBOOK_APP_ID,
            'client_secret': FACEBOOK_APP_SECRET,
            'redirect_uri': redirect_uri,
            'code': code
        }
        
        logger.info(f"Trocando code por access_token para provedor {provider_id}")
        token_response = requests.get(token_url, params=token_params)
        
        if token_response.status_code != 200:
            logger.error(f"Erro ao trocar code por token: {token_response.status_code} - {token_response.text}")
            return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_error=token_exchange_failed')
        
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            logger.error(f"Access token não retornado: {token_data}")
            return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_error=no_access_token')
        
        # Obter informações do WhatsApp Business Account
        # Primeiro, obter informações do usuário/app
        me_url = 'https://graph.facebook.com/v24.0/me'
        me_response = requests.get(me_url, params={'access_token': access_token})
        
        if me_response.status_code != 200:
            logger.error(f"Erro ao obter informações do usuário: {me_response.status_code} - {me_response.text}")
            # Continuar mesmo assim, podemos salvar o token
        
        # Buscar WhatsApp Business Accounts associados
        waba_url = 'https://graph.facebook.com/v24.0/me/businesses'
        waba_response = requests.get(waba_url, params={'access_token': access_token})
        
        waba_id = None
        phone_number_id = None
        
        if waba_response.status_code == 200:
            waba_data = waba_response.json()
            businesses = waba_data.get('data', [])
            if businesses:
                # Pegar o primeiro business account
                waba_id = businesses[0].get('id')
                
                # Buscar phone numbers associados
                if waba_id:
                    phone_numbers_url = f'https://graph.facebook.com/v24.0/{waba_id}/owned_phone_numbers'
                    phone_response = requests.get(phone_numbers_url, params={'access_token': access_token})
                    
                    if phone_response.status_code == 200:
                        phone_data = phone_response.json()
                        phone_numbers = phone_data.get('data', [])
                        if phone_numbers:
                            phone_number_id = phone_numbers[0].get('id')
        
        # Buscar ou criar integração WhatsApp
        whatsapp_integration, created = WhatsAppIntegration.objects.get_or_create(
            provedor=provedor,
            defaults={
                'phone_number': phone_number_id or '',
                'access_token': access_token,
                'is_active': True,
                'is_connected': True,
                'settings': {
                    'phone_number_id': phone_number_id,
                    'cloud_api_access_token': access_token,
                    'waba_id': waba_id,
                }
            }
        )
        
        if not created:
            # Atualizar integração existente
            whatsapp_integration.access_token = access_token
            whatsapp_integration.is_active = True
            whatsapp_integration.is_connected = True
            
            # Atualizar settings
            if not whatsapp_integration.settings:
                whatsapp_integration.settings = {}
            
            whatsapp_integration.settings.update({
                'phone_number_id': phone_number_id,
                'cloud_api_access_token': access_token,
                'waba_id': waba_id,
            })
            
            if phone_number_id:
                whatsapp_integration.phone_number = phone_number_id
            
            whatsapp_integration.save()
        
        logger.info(f"Integração WhatsApp atualizada para provedor {provider_id}: phone_number_id={phone_number_id}, waba_id={waba_id}")
        
        # Redirecionar para página de integrações com sucesso
        return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_success=1')
        
    except Exception as e:
        logger.error(f"Erro ao processar OAuth callback: {str(e)}", exc_info=True)
        provider_id = _extract_provider_id(state) if 'state' in locals() else None
        if provider_id:
            return redirect(f'/app/accounts/{provider_id}/integracoes?oauth_error=internal_error')
        return redirect('/app/accounts/1/integracoes?oauth_error=internal_error')


def _extract_provider_id(state):
    """
    Extrai o ID do provedor do state.
    Formato esperado: provider_X onde X é o ID do provedor
    """
    if not state:
        return None
    
    if state.startswith('provider_'):
        try:
            provider_id = int(state.replace('provider_', ''))
            return provider_id
        except ValueError:
            return None
    
    return None

