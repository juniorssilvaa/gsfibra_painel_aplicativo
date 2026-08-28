"""
Serviço para integração com a API do Asaas (Faturamento Global)
"""
import requests
import logging
from typing import Dict, Any, Optional, List
from core.models import SystemConfig

logger = logging.getLogger(__name__)

class AsaasService:
    """
    Serviço centralizado para operações na API do Asaas
    """
    
    PRODUCTION_URL = "https://api.asaas.com/v3"
    SANDBOX_URL = "https://api-sandbox.asaas.com/v3"
    
    def __init__(self):
        """
        Inicializa o serviço buscando as chaves globais no SystemConfig
        """
        config = SystemConfig.objects.filter(key='system_config').first()
        if not config:
            config = SystemConfig.objects.first()
            
        if config:
            self.access_token = config.asaas_access_token or ''
            self.is_sandbox = getattr(config, 'asaas_sandbox', True)
        else:
            self.access_token = ''
            self.is_sandbox = True
            
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.PRODUCTION_URL
        
        if not self.access_token:
            logger.warning("[AsaasService] Token de acesso não configurado no SystemConfig (coluna asaas_access_token)")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "access_token": self.access_token,
            "Content-Type": "application/json"
        }

    def create_customer(self, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria um cliente no Asaas com os dados detalhados do provedor
        """
        url = f"{self.base_url}/customers"
        
        # Mapeamento de campos Nio Chat -> Asaas
        payload = {
            "name": provider_data.get("nome"),
            "cpfCnpj": provider_data.get("cpf_cnpj"),
            "email": provider_data.get("email_contato"),
            "phone": provider_data.get("phone"),
            "mobilePhone": provider_data.get("mobile_phone"),
            "address": provider_data.get("endereco"),
            "addressNumber": provider_data.get("address_number"),
            "complement": provider_data.get("complement"),
            "province": provider_data.get("province"),
            "postalCode": provider_data.get("postal_code"),
            "externalReference": f"provider_{provider_data.get('id')}" if provider_data.get('id') else None,
            "notificationDisabled": provider_data.get("notification_disabled", False),
            "additionalEmails": provider_data.get("additional_emails"),
            "municipalInscription": provider_data.get("municipal_inscription"),
            "stateInscription": provider_data.get("state_inscription"),
            "observations": provider_data.get("observations"),
            "groupName": provider_data.get("group_name"),
            "company": provider_data.get("company"),
            "foreignCustomer": provider_data.get("foreign_customer", False),
        }
        
        # Remover campos nulos ou vazios para evitar erros na API se ela for rigorosa
        payload = {k: v for k, v in payload.items() if v is not None}
            
        try:
            logger.info(f"[AsaasService] Tentando criar cliente: {payload.get('name')} ({payload.get('cpfCnpj')})")
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                logger.error(f"[AsaasService] Erro API Asaas ({response.status_code}): {response.text}")
                return {"success": False, "error": response.text}
                
            data = response.json()
            logger.info(f"[AsaasService] Cliente criado com sucesso: {data.get('id')}")
            return {"success": True, "customer_id": data.get("id"), "data": data}
        except Exception as e:
            logger.error(f"[AsaasService] Erro de conexão ao criar cliente: {str(e)}")
            return {"success": False, "error": str(e)}

    def list_payments(
        self,
        customer: str = None,
        status: str = None,
        due_date_ge: str = None,
        due_date_le: str = None,
        subscription_id: str = None
    ) -> Dict[str, Any]:
        """
        Lista cobranças com filtros (cliente, status, data de vencimento)
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
        if subscription_id:
            params["subscription"] = subscription_id
            
        try:
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return {"success": True, "data": data.get("data", []), "total_count": data.get("totalCount")}
        except Exception as e:
            logger.error(f"[AsaasService] Erro ao listar pagamentos: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_subscription(self, subscription_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria uma assinatura (recorrência) no Asaas
        """
        url = f"{self.base_url}/subscriptions"
        
        payload = {
            "customer": subscription_data.get("customer"),
            "billingType": subscription_data.get("billingType", "BOLETO"),
            "value": subscription_data.get("value"),
            "nextDueDate": subscription_data.get("nextDueDate"),
            "cycle": subscription_data.get("cycle", "MONTHLY"),
            "description": subscription_data.get("description"),
            "externalReference": subscription_data.get("externalReference"),
            "notificationDisabled": subscription_data.get("notificationDisabled", False),
        }
        
        # Remover campos nulos
        payload = {k: v for k, v in payload.items() if v is not None}
        
        try:
            logger.info(f"[AsaasService] Tentando criar assinatura para cliente {payload.get('customer')}")
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            
            if response.status_code != 200:
                logger.error(f"[AsaasService] Erro API Asaas Subscriptions ({response.status_code}): {response.text}")
                return {"success": False, "error": response.text}
                
            data = response.json()
            logger.info(f"[AsaasService] Assinatura criada com sucesso: {data.get('id')}")
            return {"success": True, "subscription_id": data.get("id"), "data": data}
        except Exception as e:
            logger.error(f"[AsaasService] Erro de conexão ao criar assinatura: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """
        Busca detalhes de uma assinatura específica
        """
        url = f"{self.base_url}/subscriptions/{subscription_id}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_payment_documents(self, payment_id: str) -> Dict[str, Any]:
        """
        Lista documentos anexados à cobrança (ex.: PDF da nota).
        GET /v3/payments/{id}/documents
        """
        url = f"{self.base_url}/payments/{payment_id}/documents"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code != 200:
                return {"success": False, "error": response.text, "status_code": response.status_code}
            body = response.json()
            if isinstance(body, list):
                return {"success": True, "data": body}
            return {"success": True, "data": body.get("data", []) if isinstance(body, dict) else []}
        except Exception as e:
            logger.error(f"[AsaasService] Erro ao listar documentos do pagamento {payment_id}: {e}")
            return {"success": False, "error": str(e)}

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

    def list_notifications(self, customer_id: str) -> Dict[str, Any]:
        """
        Lista todas as configurações de notificação de um cliente
        """
        url = f"{self.base_url}/notifications"
        params = {"customer": customer_id}
        try:
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json().get("data", [])}
            return {"success": False, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_notification(self, notification_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atualiza uma configuração de notificação específica
        """
        url = f"{self.base_url}/notifications/{notification_id}"
        try:
            response = requests.put(url, json=data, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            return {"success": False, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bulk_disable_notifications(self, customer_id: str) -> List[Dict[str, Any]]:
        """
        Desativa todas as notificações de um cliente de forma granular
        """
        logger.info(f"[AsaasService] Iniciando desativação granular de notificações para cliente {customer_id}")
        results = []
        
        list_res = self.list_notifications(customer_id)
        if not list_res.get("success"):
            logger.error(f"[AsaasService] Falha ao listar notificações para desativação: {list_res.get('error')}")
            return [{"success": False, "error": "Falha ao listar notificações"}]

        notifications = list_res.get("data", [])
        for notif in notifications:
            notif_id = notif.get("id")
            payload = {
                "enabled": False,
                "emailEnabledForCustomer": False,
                "smsEnabledForCustomer": False,
                "whatsappEnabledForCustomer": False,
                "phoneCallEnabledForCustomer": False
            }
            logger.info(f"[AsaasService] Desativando notificação {notif_id} do tipo {notif.get('event')}")
            res = self.update_notification(notif_id, payload)
            results.append(res)
            
        return results
