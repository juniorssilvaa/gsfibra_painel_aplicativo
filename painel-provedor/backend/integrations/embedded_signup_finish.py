"""
Funções para processar o finish do WhatsApp Embedded Signup
"""
import requests
import logging
from typing import Optional, Dict, Tuple
from django.conf import settings
from django.utils import timezone
from core.models import Canal, Provedor
from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION, GRAPH_API_VERSION, META_APP_ID, META_APP_SECRET

logger = logging.getLogger(__name__)

def exchange_code_for_token(code: str) -> Optional[str]:
    """
    Troca o Authorization Code pelo Access Token da Meta.
    Válido por 30 segundos conforme documentação.
    """
    try:
        # Endpoint oficial de troca de token para Embedded Signup
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        params = {
            'client_id': META_APP_ID,
            'client_secret': META_APP_SECRET,
            'code': code
        }
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            token = response.json().get('access_token')
            return token
        else:
            return None
    except Exception as e:
        return None

def fetch_phone_numbers_from_waba(waba_id: str, access_token: str) -> Optional[Dict]:
    """Busca dados da conta e telefone usando o token obtido."""
    try:
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{waba_id}/phone_numbers"
        response = requests.get(url, params={"access_token": access_token}, timeout=30)
        
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data:
                # Prioriza o primeiro número que não seja de teste
                phone = data[0]
                for p in data:
                    if "test" not in p.get("verified_name", "").lower():
                        phone = p
                        break
                return {
                    "phone_number_id": phone.get("id"),
                    "display_phone_number": phone.get("display_phone_number", ""),
                    "verified_name": phone.get("verified_name", ""),
                    "code_verification_status": phone.get("code_verification_status", ""),
                    "quality_rating": phone.get("quality_rating", ""),
                    "waba_id": waba_id
                }
        return None
    except Exception as e:
        return None

def sync_smb_app_state(phone_number_id: str, access_token: str):
    """Sincroniza estado do App SMB conforme recomendado na docs (Coexistence)."""
    try:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/smb_app_data"
        requests.post(url, json={"messaging_product": "whatsapp", "sync_type": "state"}, params={"access_token": access_token}, timeout=10)
    except: pass

def sync_history(phone_number_id: str, access_token: str):
    """Inicia sincronização de histórico (obrigatório em 24h)."""
    try:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/smb_app_data"
        requests.post(url, json={"messaging_product": "whatsapp", "sync_type": "history"}, params={"access_token": access_token}, timeout=10)
    except: pass

def fetch_business_profile(phone_number_id: str, access_token: str) -> Optional[Dict]:
    """
    Busca o perfil empresarial do WhatsApp Business incluindo foto do perfil.
    
    Endpoint: GET /<PHONE_NUMBER_ID>/whatsapp_business_profile
    """
    try:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/whatsapp_business_profile"
        params = {
            "fields": "about,address,description,email,profile_picture_url,websites,vertical",
            "access_token": access_token
        }
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data and len(data) > 0:
                profile = data[0]
                logger.info(f"[WhatsAppBusinessProfile] Perfil encontrado para phone_number_id {phone_number_id}")
                return profile
            else:
                logger.warning(f"[WhatsAppBusinessProfile] Nenhum perfil encontrado para phone_number_id {phone_number_id}")
                return None
        else:
            logger.warning(f"[WhatsAppBusinessProfile] Erro ao buscar perfil: HTTP {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"[WhatsAppBusinessProfile] Exceção ao buscar perfil: {str(e)}")
        return None

def subscribe_app_to_waba(waba_id: str) -> bool:
    """
    Inscreve o App do NioChat no WABA do cliente para receber webhooks de mensagens.
    Usa o SYSTEM USER TOKEN configurado (Token de Sistema do Parceiro Tech).
    """
    system_token = getattr(settings, 'WHATSAPP_SYSTEM_USER_TOKEN', None)
    if not system_token:
        logger.error("[MetaSubscription] WHATSAPP_SYSTEM_USER_TOKEN não configurado no settings.py ou .env")
        return False
        
    # Endpoint oficial da Meta para inscrição de Apps em WABAs
    # POST https://graph.facebook.com/v19.0/{waba_id}/subscribed_apps
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{waba_id}/subscribed_apps"
    headers = {
        "Authorization": f"Bearer {system_token}",
        "Content-Type": "application/json"
    }
    # O campo "messages" é obrigatório para receber os webhooks de mensagens recebidas
    body = {
        "subscribed_fields": ["messages"]
    }
    
    try:
        logger.info(f"[MetaSubscription] Tentando inscrever app no WABA {waba_id}...")
        response = requests.post(url, headers=headers, json=body, timeout=30)
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            logger.info(f"[MetaSubscription] App NioChat inscrito com sucesso no WABA {waba_id}")
            return True
        else:
            # Pode falhar se o token não tiver permissão whatsapp_business_management no WABA
            logger.error(f"[MetaSubscription] Erro ao inscrever app no WABA {waba_id}: {data}")
            return False
    except Exception as e:
        logger.error(f"[MetaSubscription] Exceção ao inscrever app no WABA {waba_id}: {str(e)}")
        return False

def process_embedded_signup_finish(
    provider_id: int,
    waba_id: Optional[str] = None,
    code: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    business_id: Optional[str] = None,
    page_ids: Optional[list] = None,
    channel_id: Optional[int] = None
) -> Tuple[bool, Optional[Canal], Optional[str]]:
    """
    Processa a finalização do WhatsApp Embedded Signup.
    Realiza a troca de token, persiste os dados e inscreve o app no WABA.
    """
    try:
        provedor = Provedor.objects.get(id=provider_id)
        access_token = None
        
        # 1. TROCA DE TOKEN (Obrigatório se code estiver presente)
        if code:
            access_token = exchange_code_for_token(code)
            if not access_token:
                return False, None, "Falha na troca de token com a Meta (Code expirado ou inválido)"

        # 2. Localizar ou criar o canal
        if channel_id:
            canal = Canal.objects.filter(id=channel_id, provedor=provedor).first()
            if not canal:
                # Se o ID foi passado mas não existe, talvez tenha sido deletado
                # Criar um novo como fallback conservador
                canal = Canal.objects.create(
                    provedor=provedor, tipo="whatsapp_oficial", 
                    nome=f"WhatsApp Oficial", status="connecting", ativo=True
                )
        else:
            # Fallback original: buscar o primeiro canal whatsapp_oficial do provedor
            canal = Canal.objects.filter(provedor=provedor, tipo="whatsapp_oficial").first()
            
        if not canal:
            canal = Canal.objects.create(
                provedor=provedor, tipo="whatsapp_oficial", 
                nome=f"WhatsApp Oficial", status="connecting", ativo=True
            )
        else:
            canal.status = "connecting"
            canal.save(update_fields=['status'])
        
        if access_token:
            canal.token = access_token
        if waba_id:
            canal.waba_id = waba_id
        if phone_number_id:
            canal.phone_number_id = phone_number_id
            
        # Salvar business_id nos dados extras se disponível
        if business_id:
            if not canal.dados_extras:
                canal.dados_extras = {}
            canal.dados_extras["business_id"] = business_id

        # 3. Buscar dados completos via API para confirmar sucesso
        if canal.token and canal.waba_id:
            phone_data = fetch_phone_numbers_from_waba(canal.waba_id, canal.token)
            if phone_data:
                canal.phone_number = phone_data["display_phone_number"]
                canal.phone_number_id = phone_data["phone_number_id"]
                if not canal.dados_extras:
                    canal.dados_extras = {}
                canal.dados_extras.update(phone_data)
                
                # 4. Buscar perfil empresarial (incluindo foto do perfil)
                if canal.phone_number_id and canal.token:
                    profile = fetch_business_profile(canal.phone_number_id, canal.token)
                    if profile:
                        profile_picture_url = profile.get("profile_picture_url")
                        if profile_picture_url:
                            # Salvar URL da foto do perfil nos dados extras
                            canal.dados_extras["profile_picture_url"] = profile_picture_url
                            canal.dados_extras["profilePicUrl"] = profile_picture_url
                            canal.dados_extras["business_about"] = profile.get("about")
                            canal.dados_extras["business_description"] = profile.get("description")
                            canal.dados_extras["business_address"] = profile.get("address")
                            canal.dados_extras["business_email"] = profile.get("email")
                            canal.dados_extras["business_vertical"] = profile.get("vertical")
                            canal.dados_extras["business_websites"] = profile.get("websites", [])
                            logger.info(f"[WhatsAppBusinessProfile] Perfil empresarial obtido com sucesso")
                
                # 5. Sincronizações (Fluxo Coexistence)
                sync_smb_app_state(canal.phone_number_id, canal.token)
                sync_history(canal.phone_number_id, canal.token)

        # 6. INSCRIÇÃO DO APP NO WABA (CRÍTICO PARA RECEBER MENSAGENS)
        # Este passo garante que a Meta envie os webhooks de mensagens para o nosso backend
        subscription_success = False
        if canal.waba_id:
            # Verificar se já está inscrito para evitar chamadas duplicadas desnecessárias
            # (embora a API da Meta seja idempotente)
            is_already_subscribed = canal.dados_extras.get("app_subscribed", False)
            
            if not is_already_subscribed:
                subscription_success = subscribe_app_to_waba(canal.waba_id)
                if subscription_success:
                    canal.dados_extras["app_subscribed"] = True
                    canal.dados_extras["subscribed_at"] = timezone.now().isoformat()
            else:
                subscription_success = True
                logger.info(f"[MetaSubscription] WABA {canal.waba_id} já consta como inscrito")

        # 7. Finalizar status do canal
        if subscription_success:
            canal.status = "connected"
            logger.info(f"[EmbeddedSignup] Canal {canal.id} conectado e inscrito com sucesso")
        else:
            canal.status = "pending"
            logger.warning(f"[EmbeddedSignup] Canal {canal.id} persistido mas falhou na inscrição do app")

        canal.ativo = True
        canal.save()

        # ─── Notificar Superadmin sobre o canal conectado (background) ────────
        # O Superadmin precisa saber o waba_id para rotear webhooks corretamente.
        # Executado em thread daemon para não bloquear a resposta ao provedor.
        if canal.waba_id and canal.status in ("connected", "pending"):
            import threading
            from integrations.superadmin_notifier import notify_superadmin_channel_connected
            t = threading.Thread(
                target=notify_superadmin_channel_connected,
                args=(canal,),
                daemon=True
            )
            t.start()

        return True, canal, None
    except Exception as e:
        logger.error(f"[EmbeddedSignup] Erro crítico no finish: {str(e)}", exc_info=True)
        return False, None, str(e)
