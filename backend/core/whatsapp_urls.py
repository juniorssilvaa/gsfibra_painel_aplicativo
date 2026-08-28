"""
URLs específicas para endpoints do WhatsApp
Organiza todos os endpoints relacionados ao WhatsApp sob /api/whatsapp/

Estrutura:
- /api/whatsapp/file/ - Servir arquivos da API Uazapi
- /api/whatsapp/profile-picture/ - Buscar foto de perfil
- /api/whatsapp/oficial-info/ - Informações do WhatsApp Oficial (Meta Cloud API)
- /api/whatsapp/session/ - Endpoints para sessões WhatsApp conectadas via API Uazapi (não oficial)
- /api/whatsapp/evolution/ - Endpoints para WhatsApp Evolution API (legado)
"""
from django.urls import path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from rest_framework.authentication import TokenAuthentication
from . import views
from .models import Canal
from rest_framework.permissions import AllowAny

# ===================================================================
# 🔵 Views Wrapper para actions do CanalViewSet
# ===================================================================

def _get_viewset_instance(request, pk=None):
    """
    Cria uma instância do CanalViewSet configurada corretamente.
    
    Args:
        request: Objeto request do Django
        pk: ID do canal (opcional, necessário para endpoints que precisam do objeto)
    
    Returns:
        Instância configurada do CanalViewSet
    """
    viewset = views.CanalViewSet()
    viewset.request = request
    viewset.format_kwarg = None
    viewset.action_map = {}
    if pk:
        viewset.kwargs = {'pk': pk}
        # Configurar get_object para funcionar corretamente
        def get_object():
            try:
                return Canal.objects.get(pk=pk)
            except Canal.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound("Canal não encontrado")
        viewset.get_object = get_object
    return viewset

class WhatsAppProfilePictureView(APIView):
    """
    Endpoint para buscar foto de perfil do WhatsApp.
    Wrapper para get_whatsapp_profile_picture do CanalViewSet.
    """
    def post(self, request):
        viewset = _get_viewset_instance(request)
        return viewset.get_whatsapp_profile_picture(request)

class WhatsAppOficialInfoView(APIView):
    """
    Endpoint para buscar informações do WhatsApp Oficial (Meta Cloud API).
    Wrapper para get_whatsapp_oficial_info do CanalViewSet.
    """
    def get(self, request):
        viewset = _get_viewset_instance(request)
        return viewset.get_whatsapp_oficial_info(request)

class WhatsAppSessionConnectView(APIView):
    """
    Endpoint para conectar uma sessão WhatsApp via API Uazapi.
    Representa WhatsApp conectado na API Uazapi (não oficial).
    Wrapper para connect_whatsapp_session do CanalViewSet.
    """
    def post(self, request):
        viewset = _get_viewset_instance(request)
        return viewset.connect_whatsapp_session(request)

class WhatsAppSessionQRView(APIView):
    """
    Endpoint para gerar QR code ou código de pareamento para sessão WhatsApp.
    Usado para conectar WhatsApp via API Uazapi (não oficial).
    Wrapper para get_whatsapp_session_qr do CanalViewSet.
    """
    def post(self, request):
        # Criar viewset e inicializar corretamente
        viewset = views.CanalViewSet()
        viewset.request = request
        viewset.format_kwarg = None
        viewset.action_map = {}
        viewset.action = 'get_whatsapp_session_qr'
        
        # Chamar o método diretamente
        try:
            return viewset.get_whatsapp_session_qr(request)
        except AttributeError as e:
            return Response({
                'success': False,
                'error': f'Método não encontrado: {str(e)}'
            }, status=500)

class WhatsAppSessionStatusView(APIView):
    """
    Endpoint para verificar status de uma sessão WhatsApp conectada via API Uazapi.
    Wrapper para get_whatsapp_session_status do CanalViewSet.
    """
    def post(self, request, pk):
        # Criar viewset e inicializar corretamente
        viewset = views.CanalViewSet()
        viewset.request = request
        viewset.format_kwarg = None
        viewset.action_map = {}
        viewset.action = 'get_whatsapp_session_status'
        viewset.kwargs = {'pk': pk}
        
        # Configurar get_object para funcionar corretamente
        def get_object():
            try:
                return Canal.objects.get(pk=pk)
            except Canal.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound("Canal não encontrado")
        viewset.get_object = get_object
        
        # Chamar o método diretamente
        try:
            return viewset.get_whatsapp_session_status(request, pk=pk)
        except AttributeError as e:
            return Response({
                'success': False,
                'error': f'Método não encontrado: {str(e)}'
            }, status=500)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro em get_whatsapp_session_status: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

class WhatsAppSessionDisconnectView(APIView):
    """
    Endpoint para desconectar uma sessão WhatsApp da API Uazapi.
    Wrapper para desconectar_instancia do CanalViewSet.
    """
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        try:
            if not request.user or not request.user.is_authenticated:
                return Response({
                    'success': False,
                    'error': 'Usuário não autenticado'
                }, status=401)
            
            try:
                canal = Canal.objects.get(pk=pk)
            except Canal.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Canal não encontrado'
                }, status=404)
            
            from .views import _user_can_access_channel
            if not _user_can_access_channel(request.user, canal):
                return Response({
                    'success': False,
                    'error': 'Você não tem permissão para acessar este canal'
                }, status=403)
            
            if canal.tipo != 'whatsapp_session':
                return Response({
                    'success': False,
                    'error': 'Apenas sessões WhatsApp podem ser desconectadas por aqui'
                }, status=400)
            
            viewset = views.CanalViewSet()
            viewset.request = request
            viewset.format_kwarg = None
            viewset.action_map = {}
            viewset.action = 'desconectar_instancia'
            viewset.kwargs = {'pk': pk}
            viewset.get_object = lambda: canal
            
            metodo = getattr(views.CanalViewSet, 'desconectar_instancia', None)
            if metodo is None:
                return Response({
                    'success': False,
                    'error': 'Método desconectar_instancia não encontrado'
                }, status=500)
            
            return metodo(viewset, request, pk=pk)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Erro ao desconectar sessão: {str(e)}'
            }, status=500)

class WhatsAppSessionDeleteView(APIView):
    """
    Endpoint para deletar uma sessão WhatsApp da API Uazapi.
    Wrapper para deletar_instancia do CanalViewSet.
    """
    def delete(self, request, pk):
        viewset = views.CanalViewSet()
        viewset.request = request
        viewset.format_kwarg = None
        viewset.action_map = {}
        viewset.action = 'deletar_instancia'
        viewset.kwargs = {'pk': pk}
        
        def get_object():
            try:
                return Canal.objects.get(pk=pk)
            except Canal.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound("Canal não encontrado")
        viewset.get_object = get_object
        
        try:
            return viewset.deletar_instancia(request, pk=pk)
        except AttributeError as e:
            return Response({
                'success': False,
                'error': f'Método não encontrado: {str(e)}'
            }, status=500)

# WhatsAppEvolutionLogoutView removida

class WhatsAppServeFileView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, file_id):
        return Response({
            'success': False,
            'error': 'Arquivo não disponível'
        }, status=404)

class WhatsAppProfilePictureProxyView(APIView):
    """
    Endpoint proxy para servir foto de perfil do WhatsApp Oficial.
    Busca a imagem usando o token de acesso e retorna como HttpResponse.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            import requests
            from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
            from core.models import Canal, Provedor
            
            # Obter parâmetros
            channel_id = request.query_params.get('channel_id')
            phone_number_id = request.query_params.get('phone_number_id')
            
            # Buscar canal
            canal = None
            if channel_id:
                try:
                    canal = Canal.objects.get(id=channel_id)
                except Canal.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Canal não encontrado'
                    }, status=404)
            elif phone_number_id:
                # Buscar canal pelo phone_number_id
                canal = Canal.objects.filter(
                    phone_number_id=phone_number_id,
                    tipo='whatsapp_oficial'
                ).first()
            
            if not canal:
                return Response({
                    'success': False,
                    'error': 'Canal não encontrado'
                }, status=404)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                if canal.provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Sem permissão'
                    }, status=403)
            
            # Buscar URL da foto de perfil
            profile_pic_url = None
            
            # Primeiro tentar do cache (dados_extras)
            if canal.dados_extras:
                profile_pic_url = canal.dados_extras.get('profile_picture_url') or canal.dados_extras.get('profilePicUrl')
            
            # Se não está em cache, buscar via API
            if not profile_pic_url and canal.token and canal.phone_number_id:
                url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/whatsapp_business_profile"
                params = {
                    "fields": "profile_picture_url",
                    "access_token": canal.token
                }
                resp = requests.get(url, params=params, timeout=8)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data and len(data) > 0:
                        profile_pic_url = data[0].get("profile_picture_url")
                        # Cachear
                        extras = canal.dados_extras or {}
                        extras["profile_picture_url"] = profile_pic_url
                        extras["profilePicUrl"] = profile_pic_url
                        canal.dados_extras = extras
                        canal.save(update_fields=["dados_extras"])
            
            if not profile_pic_url:
                return Response({
                    'success': False,
                    'error': 'Foto de perfil não encontrada'
                }, status=404)
            
            # Buscar a imagem usando o token
            # A URL da Meta requer o access_token como query parameter
            image_response = requests.get(profile_pic_url, timeout=10)
            
            if image_response.status_code == 200:
                from django.http import HttpResponse
                response = HttpResponse(image_response.content, content_type=image_response.headers.get('Content-Type', 'image/jpeg'))
                # Permitir cache por 1 hora
                response['Cache-Control'] = 'public, max-age=3600'
                return response
            else:
                # Se falhar, tentar com token como query param (algumas URLs da Meta precisam disso)
                if '?' in profile_pic_url:
                    image_url_with_token = f"{profile_pic_url}&access_token={canal.token}"
                else:
                    image_url_with_token = f"{profile_pic_url}?access_token={canal.token}"
                
                image_response = requests.get(image_url_with_token, timeout=10)
                if image_response.status_code == 200:
                    from django.http import HttpResponse
                    response = HttpResponse(image_response.content, content_type=image_response.headers.get('Content-Type', 'image/jpeg'))
                    response['Cache-Control'] = 'public, max-age=3600'
                    return response
                else:
                    return Response({
                        'success': False,
                        'error': f'Erro ao buscar imagem: {image_response.status_code}'
                    }, status=image_response.status_code)
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao servir foto de perfil: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)

urlpatterns = [
    # ===================================================================
    # 🔵 Arquivos e Mídia
    # ===================================================================
    path('file/<str:file_id>/', WhatsAppServeFileView.as_view(), name='whatsapp_serve_file'),
    
    # ===================================================================
    # 🔵 Perfil e Informações
    # ===================================================================
    path('profile-picture/', WhatsAppProfilePictureView.as_view(), name='whatsapp_profile_picture'),
    path('profile-picture/proxy/', WhatsAppProfilePictureProxyView.as_view(), name='whatsapp_profile_picture_proxy'),
    path('oficial-info/', WhatsAppOficialInfoView.as_view(), name='whatsapp_oficial_info'),
    
    # ===================================================================
    # 🔵 WhatsApp Session (API Uazapi - não oficial)
    # Representa WhatsApp conectado via API Uazapi, não a API oficial da Meta
    # ===================================================================
    path('session/connect/', WhatsAppSessionConnectView.as_view(), name='whatsapp_session_connect'),
    path('session/qr/', WhatsAppSessionQRView.as_view(), name='whatsapp_session_qr'),
    path('session/status/<int:pk>/', WhatsAppSessionStatusView.as_view(), name='whatsapp_session_status'),
    path('session/disconnect/<int:pk>/', WhatsAppSessionDisconnectView.as_view(), name='whatsapp_session_disconnect'),
    path('session/delete/<int:pk>/', WhatsAppSessionDeleteView.as_view(), name='whatsapp_session_delete'),
    
    # ===================================================================
    # 🔵 WhatsApp Evolution (Legado)
    # ===================================================================
    # evolution/logout removido
]
