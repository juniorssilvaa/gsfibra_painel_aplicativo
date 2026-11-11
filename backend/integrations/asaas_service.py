"""
Serviço para integração com a API do Asaas (Faturamento Global) - Versão Superadmin
"""
import requests
import logging
from typing import Dict, Any, Optional, List

from integrations.asaas_entity import (
    asaas_entity_is_removed,
    asaas_payment_is_active,
    confirm_payments_on_asaas,
)
from integrations.asaas_config import (
    ASAAS_API_PRODUCTION,
    ASAAS_API_SANDBOX,
    get_asaas_access_token,
    get_asaas_base_url,
    is_asaas_sandbox,
)

logger = logging.getLogger(__name__)

class AsaasService:
    """
    Serviço centralizado para operações na API do Asaas
    """
    
    PRODUCTION_URL = ASAAS_API_PRODUCTION
    SANDBOX_URL = ASAAS_API_SANDBOX
    
    def __init__(self):
        """
        Inicializa o serviço buscando as chaves globais no SystemConfig.payload
        """
        self.access_token = get_asaas_access_token()
        self.is_sandbox = is_asaas_sandbox()
        self.base_url = get_asaas_base_url()
        
        if not self.access_token:
            logger.warning("[AsaasService] Token de acesso não configurado no SystemConfig.payload (campo asaas_access_token)")
        else:
            logger.info(
                "[AsaasService] Ambiente %s — %s",
                "sandbox" if self.is_sandbox else "produção",
                self.base_url,
            )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "access_token": self.access_token,
            "Content-Type": "application/json",
            "accept": "application/json"
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, headers=self._get_headers(), timeout=30, **kwargs)
            if response.status_code in [200, 201]:
                return {"success": True, "data": response.json()}
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        pid = (payment_id or '').strip()
        if not pid:
            return {"success": False, "error": "payment_id vazio"}
        return self._request('GET', f'/payments/{pid}')

    def fetch_active_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        res = self.get_payment(payment_id)
        if not res.get('success'):
            sc = res.get('status_code')
            if sc == 404 or asaas_entity_is_removed(sc, res.get('error')):
                return None
            logger.warning(
                "[AsaasService] GET payment %s falhou: %s",
                payment_id,
                res.get('error'),
            )
            return None
        data = res.get('data')
        return data if asaas_payment_is_active(data) else None

    def confirm_payments(self, payments: list | None, *, max_items: int = 50) -> list:
        return confirm_payments_on_asaas(
            payments,
            self.fetch_active_payment,
            max_items=max_items,
        )

    def list_payments(
        self,
        customer: str = None,
        status: str = None,
        due_date_ge: str = None,
        due_date_le: str = None,
        payment_date_ge: str = None,
        payment_date_le: str = None,
        subscription_id: str = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Lista cobranças com filtros (cliente, status, vencimento, data de pagamento)
        """
        url = f"{self.base_url}/payments"
        params = {}
        
        if customer:
            params["customer"] = customer
        if status:
            params["status"] = status
        if due_date_ge:
            params["dueDate[ge]"] = due_date_ge
        if due_date_le:
            params["dueDate[le]"] = due_date_le
        if payment_date_ge:
            params["paymentDate[ge]"] = payment_date_ge
        if payment_date_le:
            params["paymentDate[le]"] = payment_date_le
        if subscription_id:
            params["subscription"] = subscription_id
        if offset:
            params["offset"] = int(offset)
        if limit:
            params["limit"] = int(limit)

        try:
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return {"success": True, "data": data.get("data", []), "total_count": data.get("totalCount")}
        except Exception as e:
            logger.error(f"[AsaasService] Erro ao listar pagamentos: {str(e)}")
            return {"success": False, "error": str(e)}

    def list_subscriptions(
        self,
        status: str = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Lista assinaturas no Asaas (paginado)."""
        url = f"{self.base_url}/subscriptions"
        params: Dict[str, Any] = {
            "offset": int(offset or 0),
            "limit": int(limit or 100),
        }
        if status:
            params["status"] = status
        try:
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "data": data.get("data", []),
                "total_count": data.get("totalCount"),
            }
        except Exception as e:
            logger.error(f"[AsaasService] Erro ao listar assinaturas: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_payment_billing_info(self, payment_id: str) -> Dict:
        return self._request('GET', f'/payments/{payment_id}/billingInfo')

    def get_payment_pix_qr_code(self, payment_id: str) -> Dict[str, Any]:
        """
        Gera/Recupera o QR Code Pix de uma cobrança específica
        """
        url = f"{self.base_url}/payments/{payment_id}/pixQrCode"
        try:
            logger.info(f"[AsaasService] Buscando QR Code Pix para fatura {payment_id}")
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            
            logger.error(f"[AsaasService] Erro ao buscar QR Code ({response.status_code}): {response.text}")
            return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"[AsaasService] Erro de conexão ao buscar QR Code: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """
        Busca detalhes de um cliente
        """
        url = f"{self.base_url}/customers/{customer_id}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}
