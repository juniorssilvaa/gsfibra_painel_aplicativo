"""Tools NioHub — hora atual e horário de atendimento do provedor."""

from __future__ import annotations

from typing import Any, Dict, List

from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core.horario_utils import parse_horarios_atendimento, verificar_horario_atendimento


def _resolve_tz(provedor=None):
    """Usa TIME_ZONE do Django (America/Belem no NioHub)."""
    name = getattr(settings, "TIME_ZONE", None) or "America/Belem"
    try:
        return ZoneInfo(name), name
    except Exception:
        return ZoneInfo("America/Belem"), "America/Belem"


def saudacao_por_hora(hour: int) -> str:
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def despedida_por_hora(hour: int) -> str:
    if 5 <= hour < 12:
        return "Tenha um ótimo dia"
    if 12 <= hour < 18:
        return "Tenha uma ótima tarde"
    return "Tenha uma ótima noite"


def _fmt_hora_display(hora: str) -> str:
    h = (hora or "").strip()
    if h in ("00:00", "24:00"):
        return "meia-noite"
    return h


def formatar_horarios_atendimento(horarios: List[Dict[str, Any]]) -> str:
    """Texto legível dos horários configurados no painel."""
    if not horarios:
        return ""
    dias_map = {
        "segunda": "Segunda-feira",
        "terça": "Terça-feira",
        "terca": "Terça-feira",
        "quarta": "Quarta-feira",
        "quinta": "Quinta-feira",
        "sexta": "Sexta-feira",
        "sábado": "Sábado",
        "sabado": "Sábado",
        "domingo": "Domingo",
    }
    linhas = []
    for d in horarios:
        dia_raw = (d.get("dia") or "").lower().strip()
        dia_base = dia_raw.split("-")[0].split(" ")[0]
        dia = dias_map.get(dia_base, (d.get("dia") or "").strip() or dia_raw.capitalize())
        periodos = d.get("periodos") or []
        if not periodos:
            linhas.append(f"{dia}: Fechado")
            continue
        partes = []
        for p in periodos:
            inicio, fim = p.get("inicio"), p.get("fim")
            if inicio and fim:
                partes.append(f"{_fmt_hora_display(inicio)} às {_fmt_hora_display(fim)}")
        linhas.append(f"{dia}: {' e '.join(partes)}" if partes else f"{dia}: Fechado")
    return "\n".join(linhas)


def obter_horario_local(provedor=None) -> Dict[str, Any]:
    tz, tz_name = _resolve_tz(provedor)
    now = timezone.now().astimezone(tz)
    hour = now.hour
    dias = (
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    )
    return {
        "success": True,
        "hora": now.strftime("%H:%M"),
        "hora_completa": now.strftime("%H:%M:%S"),
        "data": now.strftime("%d/%m/%Y"),
        "dia_semana": dias[now.weekday()],
        "timezone": tz_name,
        "periodo": (
            "manha" if 5 <= hour < 12 else "tarde" if 12 <= hour < 18 else "noite"
        ),
        "saudacao": saudacao_por_hora(hour),
        "despedida": despedida_por_hora(hour),
        "mensagem": (
            f"Agora são {now.strftime('%H:%M')} ({tz_name}), "
            f"{dias[now.weekday()]} {now.strftime('%d/%m/%Y')}. "
            f"Use a saudação '{saudacao_por_hora(hour)}' e a despedida '{despedida_por_hora(hour)}'."
        ),
    }


def obter_horario_atendimento(provedor) -> Dict[str, Any]:
    """Horário de funcionamento configurado no painel do provedor."""
    raw = getattr(provedor, "horarios_atendimento", None)
    horarios = parse_horarios_atendimento(raw)
    info = verificar_horario_atendimento(provedor)
    texto = formatar_horarios_atendimento(horarios)
    if not texto:
        return {
            "success": True,
            "configurado": False,
            "dentro_horario": True,
            "horarios_texto": "",
            "nota": (
                "Nao ha horario de atendimento configurado no painel. "
                "Diga que a equipe atende em horario comercial e ofereca ajuda."
            ),
        }
    return {
        "success": True,
        "configurado": True,
        "dentro_horario": bool(info.get("dentro_horario")),
        "proximo_horario": info.get("proximo_horario"),
        "fonte": info.get("fonte") or "provedor",
        "mensagem": info.get("mensagem"),
        "feriado": (
            (info.get("feriado") or {}).get("name")
            if isinstance(info.get("feriado"), dict)
            else None
        ),
        "horarios_texto": texto,
        "nota": (
            "Use APENAS estes horarios do painel. Nao invente. "
            "Se dentro_horario=false, informe o cliente com o motivo "
            "(feriado, se houver) e quando sera atendido (proximo_horario). "
            "Informe o cliente com suas palavras (pode resumir dias iguais)."
        ),
    }


def consultar_hora_atual(*, provedor, arguments=None, contexto=None, conversation_id=None, actions=None, **_kw):
    """Tool interna: hora atual no fuso do provedor para saudação correta."""
    return obter_horario_local(provedor)


def consultar_horario_atendimento(*, provedor, arguments=None, contexto=None, conversation_id=None, actions=None, **_kw):
    """Tool interna: horário de funcionamento do provedor (painel)."""
    return obter_horario_atendimento(provedor)
