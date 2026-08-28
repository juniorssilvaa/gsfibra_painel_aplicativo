"""Registro dinâmico de Tools — a IA só conhece o nome; o Registry resolve o handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Union


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Dict[str, Any]]
    tags: Set[str] = field(default_factory=set)
    # Backends de ERP (sgp/ixc). Tools de pagamento/CRM/etc. deixam None.
    erp: Optional[Set[str]] = None
    require_erp: bool = False
    permissions: Set[str] = field(default_factory=set)
    source: str = "niohub"  # "integrations" | "niohub"
    aliases: Set[str] = field(default_factory=set)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec
        for alias in spec.aliases or set():
            self._aliases[alias] = spec.name

    def clear(self) -> None:
        self._tools.clear()
        self._aliases.clear()

    def resolve_name(self, name: str) -> str:
        return self._aliases.get(name, name)

    def get(self, name: str) -> Optional[ToolSpec]:
        resolved = self.resolve_name(name)
        return self._tools.get(resolved)

    def list_specs(
        self,
        *,
        tags: Optional[Set[str]] = None,
        erp: Optional[str] = None,
        source: Optional[str] = None,
        include_integrations: bool = True,
        include_niohub: bool = True,
    ) -> List[ToolSpec]:
        out: List[ToolSpec] = []
        for spec in self._tools.values():
            if source and spec.source != source:
                continue
            if spec.source == "integrations" and not include_integrations:
                continue
            if spec.source == "niohub" and not include_niohub:
                continue
            if tags and not (spec.tags & tags):
                continue
            # Só filtra por ERP quando a tool exige backend ERP (não pagamento/CRM genérico)
            if spec.require_erp or spec.erp:
                if not erp:
                    continue
                if spec.erp and erp not in spec.erp:
                    continue
            out.append(spec)
        return out

    def openai_schemas(
        self,
        *,
        tags: Optional[Set[str]] = None,
        erp: Optional[str] = None,
        source: Optional[str] = None,
        include_integrations: bool = True,
        include_niohub: bool = True,
    ) -> List[Dict[str, Any]]:
        schemas = []
        for spec in self.list_specs(
            tags=tags,
            erp=erp,
            source=source,
            include_integrations=include_integrations,
            include_niohub=include_niohub,
        ):
            params = dict(spec.parameters or {})
            params.pop("additionalProperties", None)
            params.pop("additionalproperties", None)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": params,
                    },
                }
            )
        return schemas


tool_registry = ToolRegistry()


def register_tool(
    *,
    name: str,
    handler: Callable[..., Dict[str, Any]],
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    tags: Optional[Sequence[str]] = None,
    erp: Optional[Union[str, Sequence[str]]] = None,
    permissions: Optional[Sequence[str]] = None,
    source: str = "niohub",
    aliases: Optional[Sequence[str]] = None,
    require_erp: Optional[bool] = None,
) -> ToolSpec:
    """API principal de registro. A IA nunca recebe o handler — só o nome."""
    erp_set: Optional[Set[str]] = None
    if erp:
        erp_set = {erp} if isinstance(erp, str) else set(erp)

    is_integration = source == "integrations" or bool(erp_set)
    resolved_source = "integrations" if is_integration else "niohub"
    # Exige ERP apenas se a tool declarar backends ERP (sgp/ixc…)
    resolved_require_erp = (
        require_erp if require_erp is not None else bool(erp_set)
    )

    spec = ToolSpec(
        name=name,
        description=description,
        parameters=parameters or {"type": "object", "properties": {}},
        handler=handler,
        tags=set(tags or []),
        erp=erp_set,
        require_erp=resolved_require_erp,
        permissions=set(permissions or []),
        source=resolved_source,
        aliases=set(aliases or []),
    )
    tool_registry.register(spec)
    return spec
