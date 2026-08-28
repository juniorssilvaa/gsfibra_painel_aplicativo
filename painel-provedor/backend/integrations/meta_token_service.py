"""
Serviço de Renovação de Tokens do WhatsApp Cloud API (Meta)

Este módulo gerencia a renovação automática de long-lived access tokens da Meta
para garantir que canais WhatsApp Oficial nunca expirem em produção.

PROBLEMA RESOLVIDO:
- Tokens long-lived expiram em ~60 dias
- Se expirarem, o canal para de funcionar
- Usuário precisa fazer OAuth novamente manualmente

SOLUÇÃO:
- Renovação automática quando faltam ≤ 7 dias para expirar
- Job diário verifica e renova tokens próximos da expiração
- Sistema resiliente a falhas (não desativa canal se renovação falhar)

FLUXO:
1. Job diário busca canais com token expirando em ≤ 7 dias
2. Para cada canal, chama renew_long_lived_token()
3. Atualiza token e expires_at no banco
4. Loga sucesso/falha sem expor token completo

IMPORTANTE:
- NUNCA salvar short-lived token
- NUNCA sobrescrever token se renovação falhar
- NUNCA logar token completo (apenas mascarado)
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from django.conf import settings
from core.models import Canal

logger = logging.getLogger(__name__)

# Configurações da Meta
META_APP_ID = '713538217881661'
META_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', None)
GRAPH_API_VERSION = 'v24.0'

# Dias antes da expiração para iniciar renovação
RENEWAL_THRESHOLD_DAYS = 7

if not META_APP_SECRET:
    logger.warning("FACEBOOK_APP_SECRET não configurado. Renovação de tokens não funcionará.")


def renew_long_lived_token(current_token: str) -> Dict:
    """
    Renova um long-lived token da Meta antes da expiração.
    
    A Meta permite renovar um long-lived token usando outro long-lived token.
    Isso estende a validade por ~60 dias novamente, mantendo o canal ativo.
    
    IMPORTANTE:
    - Usa o mesmo endpoint de troca short-lived → long-lived
    - Mas aceita long-lived token como entrada (fb_exchange_token)
    - Retorna novo long-lived token válido por ~60 dias
    
    Args:
        current_token: Long-lived token atual que será renovado
    
    Returns:
        Dict com:
            - access_token: Novo long-lived token
            - expires_in: Segundos até expiração (~5184000 = 60 dias)
    
    Raises:
        Exception: Se a renovação falhar (token inválido, API error, etc)
    
    Exemplo:
        >>> token_data = renew_long_lived_token("EAABsbCS1iHg...")
        >>> new_token = token_data['access_token']
        >>> expires_in = token_data['expires_in']  # ~5184000 segundos
    """
    logger.info("Iniciando renovação de long-lived token")
    
    if not META_APP_SECRET:
        raise Exception("FACEBOOK_APP_SECRET não configurado")
    
    # Endpoint da Meta para renovação de token
    # IMPORTANTE: Usa o mesmo endpoint de troca, mas aceita long-lived como entrada
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
    
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "fb_exchange_token": current_token
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Erro ao renovar token: {response.status_code} - {error_text}")
            raise Exception(f"Token renewal failed: {error_text}")
        
        token_data = response.json()
        
        # Validar que o token foi retornado
        if 'access_token' not in token_data:
            logger.error(f"Access token não encontrado na resposta: {token_data}")
            raise Exception("Access token not found in response")
        
        expires_in = token_data.get('expires_in', 5184000)  # Default: 60 dias
        expires_days = expires_in / 86400
        
        token_masked = f"{token_data['access_token'][:20]}...{token_data['access_token'][-10:]}"
        logger.info(f"✓ Token renovado com sucesso (expira em {expires_days:.1f} dias): {token_masked}")
        
        return token_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de rede ao renovar token: {str(e)}")
        raise Exception(f"Network error during token renewal: {str(e)}")
    except Exception as e:
        logger.error(f"Erro inesperado ao renovar token: {str(e)}", exc_info=True)
        raise


def token_needs_renewal(expires_at: Optional[datetime]) -> bool:
    """
    Verifica se um token precisa ser renovado.
    
    REGRA DE RENOVAÇÃO:
    - Renovar quando faltar ≤ 7 dias para expirar
    - Nunca esperar expirar completamente
    - Dar margem de segurança para falhas de rede/API
    
    POR QUE 7 DIAS:
    - Permite múltiplas tentativas se a renovação falhar
    - Evita renovação desnecessária (rate limit da Meta)
    - Garante que nunca expire em produção
    
    Args:
        expires_at: Data/hora de expiração do token (pode ser None)
    
    Returns:
        True se o token expira em ≤ 7 dias, False caso contrário
    
    Exemplo:
        >>> from datetime import datetime, timedelta
        >>> expires_soon = datetime.now() + timedelta(days=5)
        >>> token_needs_renewal(expires_soon)  # True
        >>> expires_later = datetime.now() + timedelta(days=30)
        >>> token_needs_renewal(expires_later)  # False
    """
    if not expires_at:
        # Se não tem data de expiração, assumir que precisa renovar (token antigo)
        logger.warning("Token sem data de expiração - assumindo que precisa renovar")
        return True
    
    # Calcular dias até expiração
    days_until_expiry = (expires_at - datetime.now()).days
    
    # Renovar se faltar ≤ 7 dias
    needs_renewal = days_until_expiry <= RENEWAL_THRESHOLD_DAYS
    
    if needs_renewal:
        logger.info(f"Token expira em {days_until_expiry} dias - precisa renovar")
    else:
        logger.debug(f"Token expira em {days_until_expiry} dias - ainda válido")
    
    return needs_renewal


def update_canal_token(canal: Canal, new_token: str, expires_in: int) -> None:
    """
    Atualiza o token e data de expiração de um canal de forma segura.
    
    IMPORTANTE:
    - Atualiza APENAS campos relacionados ao token
    - Mantém todos os outros dados do canal intactos
    - Registra histórico da renovação
    
    Args:
        canal: Objeto Canal a ser atualizado
        new_token: Novo long-lived token
        expires_in: Segundos até expiração
    """
    # Calcular nova data de expiração
    expires_at = datetime.now() + timedelta(seconds=expires_in)
    
    # Atualizar token
    canal.token = new_token
    
    # Atualizar dados_extras de forma segura (não sobrescrever outros dados)
    if not canal.dados_extras:
        canal.dados_extras = {}
    
    canal.dados_extras.update({
        "token_expires_at": expires_at.isoformat(),
        "token_type": "long_lived_renewed",
        "last_token_renewal": datetime.now().isoformat()
    })
    
    # Manter outros dados importantes
    if "meta_business_id" not in canal.dados_extras:
        # Preservar dados existentes se não estiverem presentes
        pass
    
    canal.save()
    
    logger.info(f"✓ Canal {canal.id} atualizado com novo token (expira em {expires_at.strftime('%Y-%m-%d %H:%M:%S')})")


def check_and_renew_canal_token(canal: Canal) -> bool:
    """
    Verifica e renova o token de um canal específico se necessário.
    
    Esta função:
    1. Verifica se o token precisa ser renovado
    2. Tenta renovar se necessário
    3. Atualiza o banco apenas se renovação for bem-sucedida
    4. Retorna True se renovou, False caso contrário
    
    IMPORTANTE:
    - NUNCA sobrescreve token se renovação falhar
    - NUNCA desativa canal se renovação falhar
    - Registra erros para análise posterior
    
    Args:
        canal: Canal a verificar/renovar
    
    Returns:
        True se renovou com sucesso, False caso contrário
    """
    # Validar que é um canal WhatsApp Oficial
    if canal.tipo != "whatsapp_oficial":
        logger.warning(f"Canal {canal.id} não é WhatsApp Oficial (tipo: {canal.tipo})")
        return False
    
    # Validar que está ativo
    if not canal.ativo:
        logger.debug(f"Canal {canal.id} não está ativo - pulando renovação")
        return False
    
    # Validar que tem token
    if not canal.token:
        logger.warning(f"Canal {canal.id} não tem token - pulando renovação")
        return False
    
    # Extrair data de expiração
    expires_at = None
    if canal.dados_extras and "token_expires_at" in canal.dados_extras:
        try:
            expires_at_str = canal.dados_extras["token_expires_at"]
            expires_at = datetime.fromisoformat(expires_at_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Erro ao parsear expires_at do canal {canal.id}: {e}")
    
    # Verificar se precisa renovar
    if not token_needs_renewal(expires_at):
        if expires_at:
            days_left = (expires_at - datetime.now()).days
            logger.debug(f"Canal {canal.id} - Token ainda válido ({days_left} dias restantes)")
        return False
    
        # Tentar renovar
        logger.info(f"Renovando token do canal {canal.id} (provedor: {canal.provedor_id})")
        
        try:
            # Renovar token
            token_data = renew_long_lived_token(canal.token)
            
            new_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 5184000)
            
            # Atualizar banco apenas se renovação foi bem-sucedida
            # IMPORTANTE: Esta função só é chamada se renovação foi bem-sucedida
            # Se falhar, o token antigo permanece no banco
            update_canal_token(canal, new_token, expires_in)
            
            logger.info(f"Token do canal {canal.id} renovado com sucesso")
            return True
            
        except Exception as e:
            # NUNCA desativar canal se renovação falhar
            # NUNCA sobrescrever token se renovação falhar
            # Apenas logar erro e tentar novamente no próximo ciclo
            logger.error(f"Falha ao renovar token do canal {canal.id}: {str(e)}")
            
            # Verificar se token já expirou
            if expires_at and expires_at < datetime.now():
                logger.warning(f"Token do canal {canal.id} já expirou - marcar como expired")
                # Marcar como expired mas manter ativo=True para permitir novo OAuth
                canal.status = "expired"
                canal.save()
                # Não desativar (ativo=True) para permitir que usuário faça novo OAuth
            
            return False

