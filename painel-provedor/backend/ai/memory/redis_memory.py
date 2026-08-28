"""
Wrapper de memória da IA.

A implementação permanece em core.redis_memory_service (não duplicar lógica).
"""

from core.redis_memory_service import normalize_phone_number, redis_memory_service

__all__ = ["redis_memory_service", "normalize_phone_number"]
