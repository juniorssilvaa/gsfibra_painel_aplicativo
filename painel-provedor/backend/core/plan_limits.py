"""Limites do plano contratado no Superadmin (canais e usuários do painel)."""
from __future__ import annotations

import logging
from typing import Optional

from django.db.models import Q

logger = logging.getLogger(__name__)

CANAIS_FORA_DO_LIMITE = ('app_mobile',)
USUARIOS_FORA_DO_LIMITE = ('niohub',)
MSG_FINANCEIRO = 'Entre em contato com o setor financeiro.'


def count_canais(provedor) -> int:
    from core.models import Canal

    return Canal.objects.filter(provedor=provedor).exclude(tipo__in=CANAIS_FORA_DO_LIMITE).count()


def count_usuarios(provedor) -> int:
    from core.models import User

    return (
        User.objects.filter(Q(provedor=provedor) | Q(provedores_admin=provedor))
        .exclude(user_type='superadmin')
        .exclude(username__in=USUARIOS_FORA_DO_LIMITE)
        .distinct()
        .count()
    )


def canal_limit_error(provedor, tipo: str = '') -> Optional[str]:
    """Mensagem de bloqueio se o provedor já atingiu o limite de canais; None se pode criar."""
    if provedor is None or tipo in CANAIS_FORA_DO_LIMITE:
        return None
    limite = provedor.plano_max_canais
    if limite is None:
        return None
    if count_canais(provedor) >= limite:
        return f'Limite de canais atingido (seu plano permite até {limite}). {MSG_FINANCEIRO}'
    return None


def user_limit_error(provedor) -> Optional[str]:
    if provedor is None:
        return None
    limite = provedor.plano_max_usuarios
    if limite is None:
        return None
    if count_usuarios(provedor) >= limite:
        return f'Limite de usuários atingido (seu plano permite até {limite}). {MSG_FINANCEIRO}'
    return None


def _limit_value(raw):
    if raw in (None, '', 0, '0'):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def apply_plan_limits(provedor, data) -> bool:
    """Grava os limites recebidos do Superadmin. Retorna True se algo mudou."""
    if provedor is None or not isinstance(data, dict):
        return False
    novos = {
        'plano_nome': str(data.get('plano_nome') or '')[:100],
        'plano_max_canais': _limit_value(data.get('max_canais')),
        'plano_max_usuarios': _limit_value(data.get('max_usuarios')),
    }
    mudou = [campo for campo, valor in novos.items() if getattr(provedor, campo) != valor]
    if not mudou:
        return False
    for campo in mudou:
        setattr(provedor, campo, novos[campo])
    provedor.save(update_fields=mudou)
    logger.info('[plano] Provedor %s: limites atualizados %s', provedor.id, novos)
    return True


def plan_usage(provedor) -> dict:
    return {
        'plano_nome': provedor.plano_nome,
        'max_canais': provedor.plano_max_canais,
        'max_usuarios': provedor.plano_max_usuarios,
        'canais': count_canais(provedor),
        'usuarios': count_usuarios(provedor),
    }
