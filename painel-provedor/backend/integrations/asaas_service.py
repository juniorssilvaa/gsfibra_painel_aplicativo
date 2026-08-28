"""
Serviço para integração com a API do Asaas (Faturamento Global)
"""
import requests
import logging
from typing import Dict, Any, Optional, List
from core.models import SystemConfig
from integrations.asaas_entity import (
    asaas_customer_is_active,
    asaas_entity_is_removed,
    asaas_payment_is_active,
    confirm_payments_on_asaas,
)

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
            raw_sandbox = getattr(config, 'asaas_sandbox', True)
            if isinstance(raw_sandbox, str):
                self.is_sandbox = raw_sandbox.strip().lower() in ('1', 'true', 'yes', 'on')
            else:
                self.is_sandbox = bool(raw_sandbox) if raw_sandbox is not None else True
        else:
            self.access_token = ''
            self.is_sandbox = True
            
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.PRODUCTION_URL
        
        if self.access_token:
            logger.info(
                "[AsaasService] Ambiente %s — %s",
                "sandbox" if self.is_sandbox else "produção",
                self.base_url,
            )
        else:
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
        
        payload = self._build_customer_payload(provider_data)
            
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

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        pid = (payment_id or '').strip()
        if not pid:
            return {"success": False, "error": "payment_id vazio"}
        url = f"{self.base_url}/payments/{pid}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code in (200, 201):
                return {"success": True, "data": response.json()}
            if response.status_code == 404 or asaas_entity_is_removed(response.status_code, response.text):
                return {"success": False, "status_code": 404, "error": response.text}
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

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

    def _build_customer_payload(self, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """Monta payload de cliente Asaas a partir dos dados do provedor."""
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
        return {k: v for k, v in payload.items() if v is not None}

    def update_customer(self, customer_id: str, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """Atualiza cliente existente no Asaas (PUT /customers/{id})."""
        url = f"{self.base_url}/customers/{customer_id}"
        payload = self._build_customer_payload(provider_data)
        try:
            logger.info(
                f"[AsaasService] Atualizando cliente {customer_id} "
                f"(notificationDisabled={payload.get('notificationDisabled')})"
            )
            response = requests.put(url, json=payload, headers=self._get_headers(), timeout=30)
            if response.status_code != 200:
                logger.error(f"[AsaasService] Erro ao atualizar cliente ({response.status_code}): {response.text}")
                return {"success": False, "error": response.text}
            data = response.json()
            return {"success": True, "customer_id": data.get("id"), "data": data}
        except Exception as e:
            logger.error(f"[AsaasService] Erro de conexão ao atualizar cliente: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """
        Busca detalhes de um cliente
        """
        url = f"{self.base_url}/customers/{customer_id}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                data = response.json()
                if not asaas_customer_is_active(data):
                    return {
                        "success": False,
                        "status_code": 200,
                        "deleted": True,
                        "error": "Cliente excluído no Asaas",
                        "data": data,
                    }
                return {"success": True, "data": data}
            if asaas_entity_is_removed(response.status_code, response.text):
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "deleted": True,
                    "error": response.text,
                }
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

    @staticmethod
    def _notification_all_disabled_payload(notif_id: str) -> Dict[str, Any]:
        """Payload que desmarca todos os canais de uma notificação no painel Asaas."""
        return {
            "id": notif_id,
            "enabled": False,
            "emailEnabledForProvider": False,
            "smsEnabledForProvider": False,
            "emailEnabledForCustomer": False,
            "smsEnabledForCustomer": False,
            "whatsappEnabledForCustomer": False,
            "phoneCallEnabledForCustomer": False,
        }

    def update_notification(self, notification_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atualiza uma configuração de notificação específica (PUT /v3/notifications/{id}).
        """
        url = f"{self.base_url}/notifications/{notification_id}"
        body = {k: v for k, v in data.items() if k != "id"}
        try:
            response = requests.put(url, json=body, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            logger.error(
                f"[AsaasService] Falha ao atualizar notificação {notification_id} "
                f"({response.status_code}): {response.text}"
            )
            return {"success": False, "error": response.text, "status_code": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bulk_disable_notifications(self, customer_id: str) -> Dict[str, Any]:
        """
        Desativa todas as notificações de um cliente (todos os canais do painel Asaas).
        Tenta batch PUT; se falhar, atualiza uma a uma via PUT.
        """
        logger.info(f"[AsaasService] Desativando todas as notificações do cliente {customer_id}")

        list_res = self.list_notifications(customer_id)
        if not list_res.get("success"):
            logger.error(f"[AsaasService] Falha ao listar notificações: {list_res.get('error')}")
            return {"success": False, "error": list_res.get("error") or "Falha ao listar notificações"}

        notifications = list_res.get("data", []) or []
        if not notifications:
            logger.warning(f"[AsaasService] Nenhuma notificação retornada para o cliente {customer_id}")
            return {"success": True, "updated": 0}

        batch_items = [
            self._notification_all_disabled_payload(n.get("id"))
            for n in notifications
            if n.get("id")
        ]

        if batch_items:
            url = f"{self.base_url}/notifications/batch"
            try:
                response = requests.put(
                    url,
                    json={"customer": customer_id, "notifications": batch_items},
                    headers=self._get_headers(),
                    timeout=60,
                )
                if response.status_code == 200:
                    logger.info(
                        f"[AsaasService] Batch: {len(batch_items)} notificações desativadas para {customer_id}"
                    )
                    return {"success": True, "updated": len(batch_items), "mode": "batch"}
                logger.warning(
                    f"[AsaasService] Batch falhou ({response.status_code}), tentando item a item: {response.text}"
                )
            except Exception as e:
                logger.warning(f"[AsaasService] Batch exceção, tentando item a item: {e}")

        results = []
        for notif in notifications:
            notif_id = notif.get("id")
            if not notif_id:
                continue
            item = self._notification_all_disabled_payload(notif_id)
            payload = {k: v for k, v in item.items() if k != "id"}
            logger.info(f"[AsaasService] Desativando notificação {notif_id} ({notif.get('event')})")
            res = self.update_notification(notif_id, payload)
            results.append(res)

        failed = [r for r in results if not r.get("success")]
        if failed:
            return {
                "success": False,
                "updated": len(results) - len(failed),
                "error": failed[0].get("error"),
                "mode": "individual",
            }
        return {"success": True, "updated": len(results), "mode": "individual"}

    def apply_notification_settings(self, customer_id: str, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sincroniza notificationDisabled no cliente e, se marcado, desativa todas as notificações granulares.
        """
        disabled = bool(provider_data.get("notification_disabled"))
        customer_res = self.update_customer(customer_id, provider_data)
        if not customer_res.get("success"):
            return {"success": False, "error": customer_res.get("error"), "step": "customer"}

        if not disabled:
            return {"success": True, "customer": customer_res, "notifications": None}

        notif_res = self.bulk_disable_notifications(customer_id)
        if not notif_res.get("success"):
            return {
                "success": False,
                "error": notif_res.get("error"),
                "step": "notifications",
                "customer": customer_res,
            }
        return {"success": True, "customer": customer_res, "notifications": notif_res}

    def find_customers_by_cpf_cnpj(self, cpf_cnpj: str, *, limit: int = 10) -> Dict[str, Any]:
        """
        Busca clientes no Asaas por CPF/CNPJ (GET /customers?cpfCnpj=).
        """
        digits = "".join(ch for ch in str(cpf_cnpj or "") if ch.isdigit())
        if len(digits) not in (11, 14):
            return {"success": False, "error": "CPF/CNPJ inválido"}
        url = f"{self.base_url}/customers"
        params = {"cpfCnpj": digits, "limit": max(1, min(int(limit or 10), 50))}
        try:
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            if response.status_code != 200:
                logger.error(
                    "[AsaasService] Erro ao buscar clientes por CPF (%s): %s",
                    response.status_code,
                    response.text[:500],
                )
                return {"success": False, "error": response.text, "status_code": response.status_code}
            body = response.json() if response.content else {}
            data = body.get("data", []) if isinstance(body, dict) else []
            active = [c for c in (data or []) if asaas_customer_is_active(c)]
            return {"success": True, "data": active, "total_count": len(active)}
        except Exception as e:
            logger.error("[AsaasService] Erro de conexão ao buscar clientes por CPF: %s", e)
            return {"success": False, "error": str(e)}

    def get_payment_identification_field(self, payment_id: str) -> Dict[str, Any]:
        """Linha digitável do boleto (GET /payments/{id}/identificationField)."""
        pid = (payment_id or "").strip()
        if not pid:
            return {"success": False, "error": "payment_id vazio"}
        url = f"{self.base_url}/payments/{pid}/identificationField"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            return {"success": False, "status_code": response.status_code, "error": response.text}
        except Exception as e:
            return {"success": False, "error": str(e)}
