"""Agregador: registra tools de integrações + NioHub e monta schemas por provedor."""

from __future__ import annotations

from typing import Any, Dict, List

from ai.registry.tool_registry import tool_registry

_REGISTERED = False


def detect_erp(provedor) -> str | None:
    integracoes = provedor.integracoes_externas or {}
    sgp_ok = integracoes.get("sgp_enabled", False) or all(
        [
            integracoes.get("sgp_url"),
            integracoes.get("sgp_token"),
            integracoes.get("sgp_app"),
        ]
    )
    if sgp_ok:
        return "sgp"
    if integracoes.get("ixc_enabled"):
        return "ixc"
    return None


def register_all_tools() -> None:
    global _REGISTERED
    if _REGISTERED and tool_registry._tools:
        return
    from ai.definitions.integrations import register_all as register_integrations
    from ai.definitions.niohub import register_all as register_niohub

    tool_registry.clear()
    register_niohub()
    register_integrations()
    _REGISTERED = True


def build_tools_for_provedor(provedor) -> List[Dict[str, Any]]:
    register_all_tools()
    agent_mode = (getattr(provedor, "agent_mode", None) or "isp").strip().lower()
    integracoes = provedor.integracoes_externas or {}
    acs_ok = bool(
        (integracoes.get("acs_url") or "").strip()
        and (integracoes.get("acs_token") or "").strip()
    )

    if agent_mode == "support":
        schemas = tool_registry.openai_schemas(include_integrations=False, include_niohub=True)
        return _filter_tools_for_provedor(schemas, viabilidade_ativa=True, acs_ok=acs_ok)

    erp = detect_erp(provedor)
    schemas = tool_registry.openai_schemas(
        include_integrations=True,
        include_niohub=True,
        erp=erp,
    )

    # Toggle: se a consulta de viabilidade estiver desativada pelo provedor,
    # a tool nem é oferecida à IA — assim ela nunca chama nem comenta sobre isso
    # com o cliente (padrão é ativo, para não quebrar provedores já configurados).
    viabilidade_ativa = bool(integracoes.get("sgp_viabilidade_ativa", True))
    return _filter_tools_for_provedor(schemas, viabilidade_ativa=viabilidade_ativa, acs_ok=acs_ok)


def _filter_tools_for_provedor(
    schemas: List[Dict[str, Any]],
    *,
    viabilidade_ativa: bool,
    acs_ok: bool,
) -> List[Dict[str, Any]]:
    seen = set()
    cleaned = []
    for t in schemas:
        name = (t.get("function") or {}).get("name")
        if not name or name in seen:
            continue
        if name == "consulta_viabilidade" and not viabilidade_ativa:
            continue
        if name in ("consultar_wifi_acs", "alterar_wifi_acs") and not acs_ok:
            continue
        seen.add(name)
        cleaned.append(t)
    return cleaned


__all__ = [
    "register_all_tools",
    "build_tools_for_provedor",
    "detect_erp",
]
