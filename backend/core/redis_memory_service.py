"""
Serviço de memória para o Chatbot - Agora usando o Banco de Dados (Django ORM).
Removemos a dependência do Redis para simplificar a infraestrutura.

Os dados são salvos no campo additional_attributes['chatbot_memory'] da Conversation.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import timezone as dt_timezone
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async
import asyncio

logger = logging.getLogger(__name__)

# Limite de mensagens no contexto (últimas N)
CONTEXT_MAX_MESSAGES = 15

def normalize_phone_number(phone: str) -> str:
    """Normaliza número de telefone para formato padrão E.164 (apenas números)."""
    if not phone:
        return "unknown"
    phone_str = str(phone)
    if "@" in phone_str:
        phone_str = phone_str.split("@")[0]
    cleaned = "".join(filter(str.isdigit, phone_str))
    return cleaned or "unknown"

def _default_state(updated_at: str) -> Dict[str, Any]:
    return {"flow": "NONE", "step": "INICIAL", "updated_at": updated_at}

class RedisConversationMemoryService:
    """
    Classe mantida com o mesmo nome para evitar quebra de compatibilidade nos imports,
    mas agora utiliza o Banco de Dados (Django ORM) em vez de Redis.
    """
    def __init__(self):
        # TTL não é mais estritamente necessário no DB, mas mantemos a estrutura
        self.memory_ttl = 30 * 60   # 30 minutos (conceitual)
        self.lock_ttl = 30          # 30 segundos

    def _now_iso(self) -> str:
        return timezone.now().astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")

    def _parse_memory(self, raw_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse da memória salvada no JSONField. Retorna { state, context } com defaults."""
        now = self._now_iso()
        if not raw_data or not isinstance(raw_data, dict):
            return {"state": _default_state(now), "context": []}
        
        state = raw_data.get("state") or _default_state(now)
        context = raw_data.get("context")
        if not isinstance(context, list):
            context = []
        return {"state": state, "context": context}

    # --- MEMÓRIA VIA DATABASE ---
    def _get_conversation_sync(self, conversation_id: int):
        from conversations.models import Conversation
        try:
            return Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return None

    async def get_ai_memory(self, provedor_id: int, conversation_id: int, channel: str, phone: str) -> Dict[str, Any]:
        """Busca memória do banco de dados (additional_attributes['chatbot_memory'])."""
        conv = await sync_to_async(self._get_conversation_sync)(conversation_id)
        if not conv:
            return self._parse_memory(None)
        
        memory = conv.additional_attributes.get('chatbot_memory')
        return self._parse_memory(memory)

    def get_ai_memory_sync(self, provedor_id: int, conversation_id: int, channel: str, phone: str) -> Dict[str, Any]:
        conv = self._get_conversation_sync(conversation_id)
        if not conv:
            return self._parse_memory(None)
        
        memory = conv.additional_attributes.get('chatbot_memory')
        return self._parse_memory(memory)

    async def _set_memory(self, provedor_id: int, conversation_id: int, channel: str, phone: str, state: Dict[str, Any], context: List[Dict[str, Any]]):
        """Persiste a memória no banco de dados."""
        state["updated_at"] = self._now_iso()
        memory_payload = {
            "state": state, 
            "context": context[-CONTEXT_MAX_MESSAGES:]
        }
        
        def save_sync():
            conv = self._get_conversation_sync(conversation_id)
            if conv:
                if not isinstance(conv.additional_attributes, dict):
                    conv.additional_attributes = {}
                conv.additional_attributes['chatbot_memory'] = memory_payload
                conv.save(update_fields=['additional_attributes'])
        
        await sync_to_async(save_sync)()

    def _set_memory_sync(self, provedor_id: int, conversation_id: int, channel: str, phone: str, state: Dict[str, Any], context: List[Dict[str, Any]]):
        state["updated_at"] = self._now_iso()
        memory_payload = {
            "state": state, 
            "context": context[-CONTEXT_MAX_MESSAGES:]
        }
        conv = self._get_conversation_sync(conversation_id)
        if conv:
            if not isinstance(conv.additional_attributes, dict):
                conv.additional_attributes = {}
            conv.additional_attributes['chatbot_memory'] = memory_payload
            conv.save(update_fields=['additional_attributes'])

    # --- ESTADO (STATE) ---
    async def get_ai_state(self, provedor_id: int, conversation_id: int, channel: str, phone: str) -> Dict[str, Any]:
        mem = await self.get_ai_memory(provedor_id, conversation_id, channel, phone)
        return mem["state"]

    def get_ai_state_sync(self, provedor_id: int, conversation_id: int, channel: str, phone: str) -> Dict[str, Any]:
        mem = self.get_ai_memory_sync(provedor_id, conversation_id, channel, phone)
        return mem["state"]

    async def set_ai_state(self, provedor_id: int, conversation_id: int, data: Dict[str, Any], channel: str, phone: str):
        mem = await self.get_ai_memory(provedor_id, conversation_id, channel, phone)
        mem["state"] = {**data, "updated_at": self._now_iso()}
        await self._set_memory(provedor_id, conversation_id, channel, phone, mem["state"], mem["context"])

    async def update_ai_state(self, provedor_id: int, conversation_id: int, updates: Dict[str, Any], channel: str, phone: str):
        mem = await self.get_ai_memory(provedor_id, conversation_id, channel, phone)
        mem["state"].update(updates or {})
        await self._set_memory(provedor_id, conversation_id, channel, phone, mem["state"], mem["context"])

    def update_ai_state_sync(self, provedor_id: int, conversation_id: int, updates: Dict[str, Any], channel: str, phone: str):
        mem = self.get_ai_memory_sync(provedor_id, conversation_id, channel, phone)
        mem["state"].update(updates or {})
        self._set_memory_sync(provedor_id, conversation_id, channel, phone, mem["state"], mem["context"])

    # --- CONTEXTO (CONTEXT) ---
    async def add_ai_context(self, provedor_id: int, conversation_id: int, role: str, content: str, channel: str, phone: str):
        mem = await self.get_ai_memory(provedor_id, conversation_id, channel, phone)
        msg = {"role": role, "content": content, "timestamp": self._now_iso()}
        mem["context"].append(msg)
        mem["context"] = mem["context"][-CONTEXT_MAX_MESSAGES:]
        await self._set_memory(provedor_id, conversation_id, channel, phone, mem["state"], mem["context"])

    async def get_ai_context(self, provedor_id: int, conversation_id: int, channel: str, phone: str, limit: int = 10) -> List[Dict[str, Any]]:
        mem = await self.get_ai_memory(provedor_id, conversation_id, channel, phone)
        ctx = mem.get("context") or []
        return ctx[-limit:] if limit else ctx

    # --- LOCK (Simulado no DB ou omitido se não houver alta concorrência) ---
    async def acquire_lock(self, provedor_id: int, conversation_id: int, channel: str, phone: str) -> bool:
        # Por simplicidade na migração para DB sem Redis, retornamos True.
        # Se precisar de lock real, teria que ser via select_for_update ou flag no DB.
        return True

    async def release_lock(self, provedor_id: int, conversation_id: int, channel: str, phone: str):
        pass

    # --- LIMPEZA ---
    async def clear_memory(self, provedor_id: int, conversation_id: int, channel: str, phone: str):
        def clear_sync():
            conv = self._get_conversation_sync(conversation_id)
            if conv and 'chatbot_memory' in conv.additional_attributes:
                del conv.additional_attributes['chatbot_memory']
                conv.save(update_fields=['additional_attributes'])
        await sync_to_async(clear_sync)()

    def clear_memory_sync(self, provedor_id: int, conversation_id: int, channel: str, phone: str):
        conv = self._get_conversation_sync(conversation_id)
        if conv and 'chatbot_memory' in conv.additional_attributes:
            del conv.additional_attributes['chatbot_memory']
            conv.save(update_fields=['additional_attributes'])

    # --- COMPATIBILIDADE ---
    def add_message_to_conversation_sync(self, provedor_id: int, conversation_id: int, sender: str, content: str, channel: str, phone: str, **kwargs):
        role = "user" if sender == "customer" else "assistant"
        mem = self.get_ai_memory_sync(provedor_id, conversation_id, channel, phone)
        msg = {"role": role, "content": content, "timestamp": self._now_iso()}
        mem["context"].append(msg)
        mem["context"] = mem["context"][-CONTEXT_MAX_MESSAGES:]
        self._set_memory_sync(provedor_id, conversation_id, channel, phone, mem["state"], mem["context"])

    async def add_message_to_conversation(self, provedor_id: int, conversation_id: int, sender: str, content: str, channel: str, phone: str, **kwargs):
        role = "user" if sender == "customer" else "assistant"
        await self.add_ai_context(provedor_id, conversation_id, role, content, channel, phone)

    def clear_conversation_memory_sync(self, provedor_id: int, conversation_id: int, channel: str = "whatsapp", phone: str = "unknown"):
        self.clear_memory_sync(provedor_id, conversation_id, channel, phone)

    async def migrate_unknown_phone(self, provedor_id: int, conversation_id: int, channel: str, phone: str):
        # No DB a memória é vinculada ao conversation_id (PK), então phone não é a chave primária.
        # Não há necessidade de migrar entre 'unknown' e phone se usarmos o conversation_id.
        pass

# Instância global
redis_memory_service = RedisConversationMemoryService()
