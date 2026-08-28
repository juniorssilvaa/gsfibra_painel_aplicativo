"""
Logs detalhados da IA — fase de testes.

Imprime no terminal o fluxo completo de cada turno:
mensagem → tools disponíveis → decisões do LLM → args → resultado → resposta.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("ai.trace")


def _clip(text: Any, limit: int = 240) -> str:
    s = "" if text is None else str(text)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def _mask_cpf(value: Any) -> Any:
    if value is None:
        return value
    digits = re.sub(r"\D", "", str(value))
    if len(digits) in (11, 14):
        return f"{digits[:3]}***{digits[-2:]}"
    return value


def _safe_args(arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    out = {}
    for k, v in arguments.items():
        key = str(k).lower()
        if any(x in key for x in ("cpf", "cnpj", "documento")):
            out[k] = _mask_cpf(v)
        elif isinstance(v, str) and len(v) > 120:
            out[k] = _clip(v, 120)
        else:
            out[k] = v
    return out


def _safe_result(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"success": False, "erro": "resultado_invalido"}
    keys = (
        "success",
        "erro",
        "error",
        "blocked",
        "bloqueado_support",
        "bloqueado_venda",
        "cached",
        "cliente_encontrado",
        "protocolo",
        "mensagem_formatada",
        "mensagem",
    )
    out = {}
    for k in keys:
        if k not in result:
            continue
        val = result[k]
        if k in ("mensagem_formatada", "mensagem", "erro", "error"):
            out[k] = _clip(val, 180)
        else:
            out[k] = val
    return out


def log_turn_start(
    *,
    provedor_id: Any,
    conversation_id: Any,
    channel: str,
    phone: str,
    mensagem: str,
    model: str,
    provider: str,
    tool_names: Sequence[str],
) -> None:
    logger.info("=" * 72)
    logger.info(
        "[AI_TRACE] INICIO | provedor=%s conv=%s canal=%s phone=%s provider=%s model=%s",
        provedor_id,
        conversation_id,
        channel,
        _clip(phone, 40),
        provider,
        model,
    )
    logger.info("[AI_TRACE] MSG_USUARIO | %s", _clip(mensagem, 400))
    logger.info(
        "[AI_TRACE] TOOLS_DISPONIVEIS (%s) | %s",
        len(tool_names),
        ", ".join(tool_names) if tool_names else "(nenhuma)",
    )


def log_llm_decision(
    *,
    turn: int,
    tool_calls: Optional[List[Any]] = None,
    text_reply: Optional[str] = None,
) -> None:
    if tool_calls:
        names = []
        for tc in tool_calls:
            try:
                names.append(tc.function.name)
            except Exception:
                names.append("?")
        logger.info(
            "[AI_TRACE] LLM_DECISAO | turno=%s chama_tools=%s | %s",
            turn,
            len(names),
            " → ".join(names),
        )
        return
    logger.info(
        "[AI_TRACE] LLM_DECISAO | turno=%s sem_tool | responde_texto=%s",
        turn,
        _clip(text_reply, 300),
    )


def log_tool_call(
    *,
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    elapsed_ms: Optional[float] = None,
    blocked: bool = False,
    block_reason: Optional[str] = None,
) -> None:
    args_json = json.dumps(_safe_args(arguments), ensure_ascii=False, default=str)
    res_json = json.dumps(_safe_result(result), ensure_ascii=False, default=str)
    status = "BLOQUEADA" if blocked else ("OK" if (result or {}).get("success") else "FALHA")
    logger.info(
        "[AI_TRACE] TOOL | %s | status=%s | %sms | motivo=%s",
        name,
        status,
        elapsed_ms if elapsed_ms is not None else "?",
        block_reason or "-",
    )
    logger.info("[AI_TRACE] TOOL_ARGS | %s | %s", name, args_json)
    logger.info("[AI_TRACE] TOOL_RESULT | %s | %s", name, res_json)


def log_turn_end(
    *,
    conversation_id: Any,
    resposta: str,
    tool_summary: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[float] = None,
    early_return: bool = False,
) -> None:
    tools = (tool_summary or {}).get("tools") or []
    chain = " → ".join(tools) if tools else "(nenhuma tool)"
    logger.info(
        "[AI_TRACE] FIM | conv=%s early=%s latency_ms=%s tools=%s",
        conversation_id,
        early_return,
        latency_ms,
        chain,
    )
    logger.info("[AI_TRACE] RESPOSTA | %s", _clip(resposta, 400))
    logger.info("=" * 72)
