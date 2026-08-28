"""
Tool Executor — firewall de execução.

Tool existe? → permissão → ERP → mode support → venda → executa → valida → log → retorna
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from ai.audit.tool_log import ToolCallLog
from ai.definitions.tool_definitions import detect_erp
from ai.registry.tool_registry import tool_registry

logger = logging.getLogger(__name__)

ERP_TOOLS = {
    "buscar_cliente",
    "selecionar_contrato",
    "gerar_fatura",
    "verificar_manutencao",
    "verificar_acesso",
    "abrir_chamado",
    "liberar_confianca",
    "consulta_viabilidade",
}


class ToolExecutor:
    def __init__(self, registry=None, actions_handler=None):
        self.registry = registry or tool_registry
        self.actions = actions_handler

    @staticmethod
    def agent_mode(provedor) -> str:
        return (getattr(provedor, "agent_mode", None) or "isp").strip().lower()

    @staticmethod
    def is_sales_contratation_context(
        mensagem: str, messages: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        existing_keywords = (
            "fatura", "boleto", "segunda via", "sem internet", "internet lenta",
            "meu plano", "liberar", "desbloqueio", "suspenso", "pagamento atrasado",
            "sem sinal", "led vermelho", "chamado",
        )
        sales_keywords = (
            "contratar", "contratação", "contratacao", "quero assinar",
            "quero fechar", "vamos fechar", "como faço para contratar",
            "como faco para contratar", "vou querer esse", "quero esse plano",
            "quero o plano", "fechar o plano", "processo de contratação",
            "processo de contratacao", "finalizar a contratação",
            "finalizar a contratacao", "equipe comercial",
            "viabilidade", "tem cobertura", "chega internet", "atende meu bairro",
        )
        texts: List[str] = [mensagem or ""]
        if messages:
            for m in messages[-10:]:
                content = m.get("content")
                if isinstance(content, str) and content.strip():
                    texts.append(content)
        blob = " ".join(texts).lower()
        if any(k in blob for k in existing_keywords):
            return False
        return any(k in blob for k in sales_keywords)

    def filter_result_for_prompt(self, res: Dict[str, Any], fname: str) -> Dict[str, Any]:
        if not isinstance(res, dict):
            return {"success": False, "erro": "Resultado inválido"}

        # Passa dados estruturados; a IA redige o texto ao cliente.
        # Evita listas/dicts gigantes; contratos resumidos são permitidos.
        out: Dict[str, Any] = {}
        for key, val in res.items():
            if key in ("mensagem_formatada", "instrucao_ia", "mensagem_manutencao_raw"):
                continue
            if isinstance(val, (dict, list)):
                if key in ("contratos", "manutencoes", "resultados", "caixas", "imagens_enviadas", "falhas", "tags_disponiveis", "hosts_resumo", "faturas", "faturas_pagas_recentes", "clientes") and isinstance(val, list):
                    out[key] = val[:40] if key in ("contratos", "faturas", "faturas_pagas_recentes", "clientes") else val[:8]
                elif key in ("filtros_usados", "consulta_endereco", "consulta_coordenadas", "cliente", "provedor_painel") and isinstance(val, dict):
                    # Passa resumo estruturado; listas internas ja vem limitadas
                    slim = {}
                    for sk, sv in val.items():
                        if sk in ("resultados", "caixas") and isinstance(sv, list):
                            slim[sk] = sv[:8]
                        elif not isinstance(sv, (dict, list)):
                            slim[sk] = sv
                        elif sk in ("resultados", "caixas"):
                            slim[sk] = sv[:8] if isinstance(sv, list) else sv
                    out[key] = slim
                elif key == "horario_info" and isinstance(val, dict):
                    out["dentro_horario"] = val.get("dentro_horario", True)
                    if val.get("proximo_horario"):
                        out["proximo_horario"] = val.get("proximo_horario")
                    if val.get("mensagem"):
                        out["mensagem_horario"] = val.get("mensagem")
                    if val.get("fonte"):
                        out["fonte_horario"] = val.get("fonte")
                    feriado = val.get("feriado")
                    if isinstance(feriado, dict) and feriado.get("name"):
                        out["feriado"] = feriado.get("name")
                continue
            if key == "mensagem_cliente_sugerida" and val:
                out[key] = val
                continue
            out[key] = val
        # Garante campos da galeria/planos no prompt da IA
        for k in ("modo", "usar_texto", "planos_texto", "nota", "enviadas", "tag", "alteracoes", "enfileirado", "wifi_ssid", "wifi_ssid_5g", "confirmacao_selecao", "precisa_confirmar_dados", "mensagem_cliente_sugerida"):
            if k in res and k not in out:
                out[k] = res[k]
        if "success" not in out:
            out["success"] = not bool(out.get("erro") or out.get("error"))
        return out

    def _validate_return(self, res: Any, fname: str) -> Dict[str, Any]:
        if not isinstance(res, dict):
            return {"success": False, "erro": f"Tool '{fname}' retornou formato inválido."}
        if "success" not in res:
            res = dict(res)
            res["success"] = not bool(res.get("erro") or res.get("error"))
        return res

    def execute_sync(
        self,
        provedor,
        fname: str,
        fargs: Dict[str, Any],
        contexto: Dict[str, Any],
        conversation_id: int,
        *,
        mensagem: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        audit: Optional[ToolCallLog] = None,
    ) -> Dict[str, Any]:
        audit = audit or ToolCallLog()
        started = audit.start(fname, fargs)
        resolved = self.registry.resolve_name(fname)
        spec = self.registry.get(resolved)

        # 1) Tool existe?
        if not spec:
            res = {"success": False, "erro": f"Tool '{fname}' não registrada."}
            audit.finish(
                name=resolved,
                arguments=fargs,
                result=res,
                started_at=started,
                conversation_id=conversation_id,
                provedor_id=getattr(provedor, "id", None),
                blocked=True,
                block_reason="not_registered",
            )
            return res

        # 2) Modo support bloqueia ERP
        if self.agent_mode(provedor) == "support" and (
            spec.source == "integrations" or resolved in ERP_TOOLS
        ):
            res = {
                "success": False,
                "bloqueado_support": True,
                "erro": (
                    "Modo Suporte da Plataforma: ferramentas de integrações externas não estão disponíveis. "
                    "Use a base de conhecimento e, se necessário, transferir_conversa."
                ),
            }
            audit.finish(
                name=resolved,
                arguments=fargs,
                result=res,
                started_at=started,
                conversation_id=conversation_id,
                provedor_id=getattr(provedor, "id", None),
                blocked=True,
                block_reason="support_mode",
            )
            return res

        # 3) ERP do provedor suporta a tool?
        if spec.require_erp or spec.source == "integrations":
            erp = detect_erp(provedor)
            if not erp or (spec.erp and erp not in spec.erp):
                res = {
                    "success": False,
                    "erro": (
                        f"Tool '{resolved}' exige ERP "
                        f"{sorted(spec.erp) if spec.erp else 'configurado'}, "
                        f"provedor tem: {erp or 'nenhum'}."
                    ),
                }
                audit.finish(
                    name=resolved,
                    arguments=fargs,
                    result=res,
                    started_at=started,
                    conversation_id=conversation_id,
                    provedor_id=getattr(provedor, "id", None),
                    blocked=True,
                    block_reason="erp_unsupported",
                )
                return res

        # 4) Contexto de venda bloqueia busca de cliente ERP
        if resolved == "buscar_cliente" and self.is_sales_contratation_context(
            mensagem, messages
        ):
            res = {
                "success": False,
                "bloqueado_venda": True,
                "erro": (
                    "Consulta ao ERP bloqueada: o cliente está em fluxo de CONTRATAÇÃO/VENDA. "
                    "NÃO consulte o ERP. Chame transferir_conversa para COMERCIAL ou VENDAS."
                ),
                "acao_obrigatoria": "transferir_conversa",
                "equipe_sugerida": "COMERCIAL",
            }
            audit.finish(
                name=resolved,
                arguments=fargs,
                result=res,
                started_at=started,
                conversation_id=conversation_id,
                provedor_id=getattr(provedor, "id", None),
                blocked=True,
                block_reason="sales_context",
            )
            return res

        # 5) Executa
        try:
            ctx = contexto
            if mensagem and isinstance(contexto, dict) and not contexto.get("mensagem"):
                ctx = dict(contexto)
                ctx["mensagem"] = mensagem
            raw = spec.handler(
                provedor=provedor,
                arguments=fargs,
                contexto=ctx,
                conversation_id=conversation_id,
                actions=self.actions,
                mensagem=mensagem or "",
                messages=messages,
            )
        except Exception as e:
            logger.error("[AI] Erro na tool %s: %s", resolved, e, exc_info=True)
            raw = {"success": False, "erro": str(e)}

        # 6) Valida retorno
        res = self._validate_return(raw, resolved)

        # 7) Log
        audit.finish(
            name=resolved,
            arguments=fargs,
            result=res,
            started_at=started,
            conversation_id=conversation_id,
            provedor_id=getattr(provedor, "id", None),
        )
        return res

    async def execute(
        self,
        provedor,
        fname: str,
        fargs: Dict[str, Any],
        contexto: Dict[str, Any],
        conversation_id: int,
        *,
        mensagem: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        audit: Optional[ToolCallLog] = None,
    ) -> Dict[str, Any]:
        return await sync_to_async(self.execute_sync)(
            provedor,
            fname,
            fargs,
            contexto,
            conversation_id,
            mensagem=mensagem,
            messages=messages,
            audit=audit,
        )
