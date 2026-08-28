import json
import logging
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SupabaseService:
    """Cliente simples para enviar Auditoria e CSAT ao Supabase via REST.

    Usa configurações do Django settings.py
    """

    def __init__(self) -> None:
        self.base_url: str = getattr(settings, 'SUPABASE_URL', '').rstrip("/")
        
        # Tentar usar SERVICE_ROLE_KEY primeiro (mais permissões), depois ANON_KEY
        self.api_key: str = getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '') or getattr(settings, 'SUPABASE_ANON_KEY', '')
        self.using_service_role: bool = bool(getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', ''))

        # Tabelas (ajuste os nomes conforme seu esquema no Supabase)
        self.audit_table: str = getattr(settings, 'SUPABASE_AUDIT_TABLE', 'auditoria')
        self.messages_table: str = getattr(settings, 'SUPABASE_MESSAGES_TABLE', 'mensagens')
        self.csat_table: str = getattr(settings, 'SUPABASE_CSAT_TABLE', 'csat_feedback')

        if not self.base_url or not self.api_key:
            logger.warning("Supabase não configurado (SUPABASE_URL/SUPABASE_ANON_KEY ausentes). Integração ficará desabilitada.")
        else:
            key_type = "SERVICE_ROLE" if self.using_service_role else "ANON"
            logger.info(f"Supabase configurado: URL={self.base_url}, Key Type={key_type}")

    def _headers(self, provedor_id: int = None) -> Dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",  # não precisamos do payload de volta
        }
        
        # Adicionar provedor_id no header para RLS
        if provedor_id:
            headers["X-Provedor-ID"] = str(provedor_id)
            
        return headers

    def _is_enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _post(self, table: str, payload: Dict[str, Any], provedor_id: int = None, upsert: bool = False) -> bool:
        """
        Envia dados para Supabase usando POST (INSERT) ou UPSERT
        
        Args:
            table: Nome da tabela
            payload: Dados a serem enviados
            provedor_id: ID do provedor (para RLS)
            upsert: Se True, usa POST com Prefer: resolution=merge-duplicates para fazer UPSERT
                    (atualiza se existir, cria se não existir)
        """
        if not self._is_enabled():
            return False
        try:
            url = f"{self.base_url}/rest/v1/{table}"
            headers = self._headers(provedor_id)
            
            if upsert:
                # UPSERT: POST com Prefer: resolution=merge-duplicates
                # Isso faz INSERT ... ON CONFLICT ... DO UPDATE automaticamente
                # Combinar com return=minimal (já existe no _headers)
                headers['Prefer'] = 'resolution=merge-duplicates,return=minimal'
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
            else:
                # POST normal (INSERT)
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
            
            if response.status_code in (200, 201, 204):
                logger.info(f"✓ Dados enviados com sucesso para Supabase ({table})")
                return True
            # Erro 409 (Conflict) - duplicate key: se já existe e não é upsert, considerar como sucesso
            if response.status_code == 409:
                error_data = response.json() if response.text else {}
                if 'duplicate key' in str(error_data).lower() or '23505' in str(error_data):
                    if upsert:
                        # Se é upsert e deu 409, algo está errado
                        logger.warning(f"Erro ao fazer upsert no Supabase ({table}): {response.text}")
                        return False
                    else:
                        # Se não é upsert e já existe, considerar como sucesso (idempotência)
                        logger.info(f"Registro já existe no Supabase ({table}), considerando como sucesso")
                        return True
            logger.warning(f"Falha ao enviar para Supabase ({table}): {response.status_code} - {response.text}")
            return False
        except Exception as exc:
            logger.error(f"Erro ao enviar dados ao Supabase ({table}): {exc}")
            return False

    def save_audit(self, *, provedor_id: int, conversation_id: int, action: str, details: Dict[str, Any],
                   user_id: Optional[int] = None, ended_at_iso: Optional[str] = None) -> bool:
        logger.info(f"Tentando salvar auditoria (conversa {conversation_id}, ação: {action}) no Supabase...")
        payload: Dict[str, Any] = {
            "provedor_id": provedor_id,
            "conversation_id": conversation_id,
            "action": action,
            "details": details,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        if ended_at_iso is not None:
            payload["ended_at"] = ended_at_iso
        result = self._post(self.audit_table, payload, provedor_id)
        if result:
            logger.info(f"✓ Auditoria salva no Supabase com sucesso (conversa {conversation_id})")
        else:
            logger.error(f"✗ Falha ao salvar auditoria no Supabase (conversa {conversation_id})")
        return result

    def save_message(self, *, provedor_id: int, conversation_id: int, contact_id: int,
                     content: str, message_type: str = 'text', is_from_customer: bool = True,
                     external_id: Optional[str] = None, file_url: Optional[str] = None,
                     file_name: Optional[str] = None, file_size: Optional[int] = None,
                     additional_attributes: Optional[Dict[str, Any]] = None,
                     created_at_iso: Optional[str] = None, updated_at_iso: Optional[str] = None) -> bool:
        """
        Salva mensagem no Supabase (NUNCA usa UPSERT - dados históricos não podem ser sobrescritos)
        Se a mensagem já existir, retorna True (considera como sucesso para idempotência)
        """
        payload: Dict[str, Any] = {
            "provedor_id": provedor_id,
            "conversation_id": conversation_id,
            "contact_id": contact_id,
            "content": content,
            "message_type": message_type,
            "is_from_customer": is_from_customer,
        }
        if external_id is not None:
            payload["external_id"] = external_id
        if file_url is not None:
            payload["file_url"] = file_url
        if file_name is not None:
            payload["file_name"] = file_name
        if file_size is not None:
            payload["file_size"] = file_size
        if additional_attributes is not None:
            payload["additional_attributes"] = additional_attributes
        if created_at_iso is not None:
            payload["created_at"] = created_at_iso
        if updated_at_iso is not None:
            payload["updated_at"] = updated_at_iso
        # IMPORTANTE: upsert=False - mensagens NUNCA devem ser sobrescritas (auditoria)
        result = self._post(self.messages_table, payload, provedor_id, upsert=False)
        # Log apenas em caso de erro para não poluir os logs (muitas mensagens)
        if not result:
            logger.error(f"✗ Falha ao salvar mensagem (conversa {conversation_id}) no Supabase")
        return result

    def save_csat(self, *, provedor_id: int, conversation_id: int, contact_id: int,
                  emoji_rating: str, rating_value: int, feedback_sent_at_iso: Optional[str] = None,
                  original_message: Optional[str] = None, contact_name: Optional[str] = None) -> bool:
        """
        Salva feedback CSAT no Supabase
        
        Args:
            provedor_id: ID do provedor
            conversation_id: ID da conversa
            contact_id: ID do contato
            emoji_rating: Emoji da avaliação (ex: '😊', '🤩')
            rating_value: Valor numérico da avaliação (1-5)
            feedback_sent_at_iso: Data/hora ISO do feedback (opcional)
            original_message: Mensagem original do cliente que gerou o CSAT (opcional)
            contact_name: Nome do contato (opcional)
        
        Returns:
            True se salvou com sucesso, False caso contrário
        """
        if not self._is_enabled():
            logger.warning("Supabase não configurado, não é possível salvar CSAT")
            return False
            
        payload: Dict[str, Any] = {
            "provedor_id": provedor_id,
            "conversation_id": conversation_id,
            "contact_id": contact_id,
            "emoji_rating": emoji_rating,
            "rating_value": rating_value,
            "original_message": original_message or '',  # Sempre incluir, mesmo se vazio
        }
        if feedback_sent_at_iso is not None:
            payload["feedback_sent_at"] = feedback_sent_at_iso
        if contact_name is not None:
            payload["contact_name"] = contact_name
        
        logger.info(f"Tentando salvar CSAT no Supabase: {payload}")
        result = self._post(self.csat_table, payload, provedor_id, upsert=False)
        
        if result:
            logger.info(f"✓ CSAT salvo no Supabase com sucesso: conversa {conversation_id}, rating {rating_value}")
        else:
            logger.error(f"✗ Falha ao salvar CSAT no Supabase: conversa {conversation_id}, rating {rating_value}")
        
        return result

    def save_conversation(self, *, provedor_id: int, conversation_id: int, contact_id: int,
                         inbox_id: Optional[int] = None, status: str = 'open',
                         assignee_id: Optional[int] = None, team_id: Optional[int] = None,
                         created_at_iso: Optional[str] = None, updated_at_iso: Optional[str] = None,
                         last_message_at_iso: Optional[str] = None, ended_at_iso: Optional[str] = None,
                         additional_attributes: Optional[Dict[str, Any]] = None) -> bool:
        """
        Salva conversa no Supabase (NUNCA usa UPSERT - dados históricos não podem ser sobrescritos)
        Se a conversa já existir, retorna True (considera como sucesso para idempotência)
        """
        logger.info(f"Tentando salvar conversa {conversation_id} no Supabase...")
        payload: Dict[str, Any] = {
            "id": conversation_id,
            "provedor_id": provedor_id,
            "contact_id": contact_id,
            "status": status,
        }
        if inbox_id is not None:
            payload["inbox_id"] = inbox_id
        if assignee_id is not None:
            payload["assignee_id"] = assignee_id
        if team_id is not None:
            payload["team_id"] = team_id
        if created_at_iso is not None:
            payload["created_at"] = created_at_iso
        if updated_at_iso is not None:
            payload["updated_at"] = updated_at_iso
        if last_message_at_iso is not None:
            payload["last_message_at"] = last_message_at_iso
        if ended_at_iso is not None:
            payload["ended_at"] = ended_at_iso
        if additional_attributes is not None:
            payload["additional_attributes"] = additional_attributes
        # IMPORTANTE: upsert=False - conversas NUNCA devem ser sobrescritas (auditoria)
        result = self._post("conversations", payload, provedor_id, upsert=False)
        if result:
            logger.info(f"✓ Conversa {conversation_id} salva no Supabase com sucesso")
        else:
            logger.error(f"✗ Falha ao salvar conversa {conversation_id} no Supabase")
        return result

    def save_contact(self, *, provedor_id: int, contact_id: int, name: str,
                    phone: Optional[str] = None, email: Optional[str] = None,
                    avatar: Optional[str] = None, created_at_iso: Optional[str] = None,
                    updated_at_iso: Optional[str] = None, additional_attributes: Optional[Dict[str, Any]] = None) -> bool:
        """
        Salva ou atualiza contato no Supabase (UPSERT)
        Se o contato já existir, os dados serão atualizados
        """
        logger.info(f"Tentando salvar contato {contact_id} no Supabase...")
        payload: Dict[str, Any] = {
            "id": contact_id,
            "provedor_id": provedor_id,
            "name": name,
        }
        if phone is not None:
            payload["phone"] = phone
        if email is not None:
            payload["email"] = email
        if avatar is not None:
            payload["avatar"] = avatar
        if created_at_iso is not None:
            payload["created_at"] = created_at_iso
        if updated_at_iso is not None:
            payload["updated_at"] = updated_at_iso
        if additional_attributes is not None:
            payload["additional_attributes"] = additional_attributes
        # Usar upsert=True para atualizar se já existir
        result = self._post("contacts", payload, provedor_id, upsert=True)
        if result:
            logger.info(f"✓ Contato {contact_id} salvo no Supabase com sucesso")
        else:
            logger.error(f"✗ Falha ao salvar contato {contact_id} no Supabase")
        return result

    def save_inbox(self, *, provedor_id: int, inbox_id: int, name: str,
                  channel_type: str, additional_attributes: Optional[Dict[str, Any]] = None) -> bool:
        """
        Salva ou atualiza inbox no Supabase (UPSERT)
        Se o inbox já existir, os dados serão atualizados
        """
        logger.info(f"Tentando salvar inbox {inbox_id} no Supabase...")
        payload: Dict[str, Any] = {
            "id": inbox_id,
            "provedor_id": provedor_id,
            "name": name,
            "channel_type": channel_type,
        }
        if additional_attributes is not None:
            payload["additional_attributes"] = additional_attributes
        # Usar upsert=True para atualizar se já existir
        result = self._post("inboxes", payload, provedor_id, upsert=True)
        if result:
            logger.info(f"✓ Inbox {inbox_id} salvo no Supabase com sucesso")
        else:
            logger.error(f"✗ Falha ao salvar inbox {inbox_id} no Supabase")
        return result

    def _get(self, table: str, filters: Optional[Dict[str, Any]] = None, provedor_id: int = None) -> Optional[Any]:
        """
        Busca dados do Supabase usando GET
        
        Args:
            table: Nome da tabela
            filters: Dicionário com filtros (ex: {'id': 'eq.123'})
            provedor_id: ID do provedor (para RLS)
        
        Returns:
            Lista de resultados ou None em caso de erro
        """
        if not self._is_enabled():
            logger.warning(f"[SUPABASE] Supabase não está habilitado (base_url={self.base_url}, api_key={'***' if self.api_key else None})")
            return None
        try:
            url = f"{self.base_url}/rest/v1/{table}"
            headers = self._headers(provedor_id)
            # Remover Prefer para receber dados de volta
            headers.pop('Prefer', None)
            
            params = {}
            if filters:
                # Separar filtros de ordenação
                order_param = None
                for key, value in filters.items():
                    if key == 'order':
                        order_param = value
                    else:
                        # O Supabase usa o formato: nome_coluna=operador.valor
                        # Ex: id=eq.123
                        params[key] = value
                
                if order_param:
                    params['order'] = order_param
            
            logger.info(f"[SUPABASE] Fazendo GET em {url} com params={params}, provedor_id={provedor_id}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            logger.info(f"[SUPABASE] Resposta: status={response.status_code}, tamanho={len(response.text) if response.text else 0}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[SUPABASE] Busca bem-sucedida em {table}: {len(data) if isinstance(data, list) else 1} registro(s)")
                return data
            else:
                logger.warning(f"[SUPABASE] Falha ao buscar do Supabase ({table}): {response.status_code} - {response.text[:200]}")
                return None
        except Exception as exc:
            logger.error(f"[SUPABASE] Erro ao buscar dados do Supabase ({table}): {exc}", exc_info=True)
            return None

    def get_conversation(self, conversation_id: int, provedor_id: int = None) -> Optional[Dict[str, Any]]:
        """Busca uma conversa no Supabase"""
        logger.info(f"[SUPABASE] Buscando conversa {conversation_id} no Supabase (provedor_id={provedor_id})")
        result = self._get("conversations", {'id': f'eq.{conversation_id}'}, provedor_id)
        logger.info(f"[SUPABASE] Resultado da busca: {result is not None}, tipo: {type(result)}")
        if result and isinstance(result, list) and len(result) > 0:
            logger.info(f"[SUPABASE] Conversa encontrada no Supabase: {result[0].get('id')}")
            return result[0]
        logger.warning(f"[SUPABASE] Conversa {conversation_id} não encontrada no Supabase")
        return None

    def get_contact(self, contact_id: int, provedor_id: int = None) -> Optional[Dict[str, Any]]:
        """Busca um contato no Supabase"""
        result = self._get("contacts", {'id': f'eq.{contact_id}'}, provedor_id)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_inbox(self, inbox_id: int, provedor_id: int = None) -> Optional[Dict[str, Any]]:
        """Busca um inbox no Supabase"""
        result = self._get("inboxes", {'id': f'eq.{inbox_id}'}, provedor_id)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_csat_feedback(self, conversation_id: int, provedor_id: int = None) -> Optional[Dict[str, Any]]:
        """Busca CSAT feedback de uma conversa no Supabase"""
        result = self._get(self.csat_table, {'conversation_id': f'eq.{conversation_id}'}, provedor_id)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        return None

    def get_messages(self, conversation_id: int, provedor_id: int = None) -> list:
        """Busca mensagens de uma conversa no Supabase"""
        result = self._get(self.messages_table, {'conversation_id': f'eq.{conversation_id}', 'order': 'created_at'}, provedor_id)
        if result and isinstance(result, list):
            return result
        return []


supabase_service = SupabaseService()