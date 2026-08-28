"""Contexto do provedor (config, agente, emoji, horário) — complementar ao Prompt Base."""

from __future__ import annotations

from typing import Any, Dict


def build_provider_runtime_hints(provedor) -> Dict[str, Any]:
    uso = (getattr(provedor, "uso_emojis", None) or "").strip().lower()
    if uso in ("sempre", "always", "sim", "yes"):
        regra_emoji = (
            "Toda resposta deve terminar com exatamente um emoji amigável."
        )
    elif uso in ("nunca", "never", "não", "nao", "no"):
        regra_emoji = "É PROIBIDO usar qualquer emoji nas respostas."
    elif uso in ("ocasionalmente", "ocasional", "sometimes"):
        regra_emoji = "Use emoji só quando fizer sentido; no máximo um no final."
    else:
        regra_emoji = ""

    from ai.tools.niohub.horario import obter_horario_local

    hora = obter_horario_local(provedor)

    return {
        "agente": getattr(provedor, "nome_agente_ia", None),
        "provedor": getattr(provedor, "nome", None),
        "uso_emojis": uso or None,
        "regra_emoji": regra_emoji,
        "hora_atual": hora.get("hora"),
        "timezone": hora.get("timezone"),
        "saudacao": hora.get("saudacao"),
        "despedida": hora.get("despedida"),
        "periodo": hora.get("periodo"),
    }


def as_prompt_block(
    hints: Dict[str, Any],
    *,
    has_ai_interaction: bool = False,
    agent_mode: str | None = None,
) -> str:
    parts = [
        f"# CONTEXTO ATUAL: {hints.get('provedor') or ''} | Agente: {hints.get('agente') or ''}",
    ]
    if hints.get("hora_atual"):
        parts.append(
            "# HORÁRIO ATUAL DO PROVEDOR\n"
            f"- Agora: {hints.get('hora_atual')} ({hints.get('timezone')})\n"
            f"- Saudação correta: {hints.get('saudacao')}\n"
            f"- Despedida correta: {hints.get('despedida')}\n"
            "- Nunca diga 'ótimo dia' à noite; use a despedida acima."
        )
    if hints.get("regra_emoji"):
        parts.append(f"# USO DE EMOJIS\n- {hints['regra_emoji']}")
    mode = (agent_mode or "").strip().lower()
    if mode == "support" and not has_ai_interaction:
        parts.append(
            "# TRIAGEM — PRIMEIRO ATENDIMENTO (MODO SUPORTE)\n"
            "- Esta é a primeira resposta da IA nesta conversa.\n"
            "- Se o cliente AINDA NÃO disse o que quer: cumprimente, apresente-se e pergunte "
            "se deseja suporte ao sistema NioHub ou contratar/conhecer planos.\n"
            "- Se o cliente JÁ disse o que quer (fatura, suporte, contratar, etc.): "
            "NÃO faça a pergunta de menu — execute o fluxo pedido.\n"
            "- Pedido de fatura/boleto/PIX da plataforma → peça CPF/CNPJ e use "
            "buscar_faturas_asaas / enviar_fatura_asaas."
        )
    if has_ai_interaction:
        parts.append(
            "A conversa já iniciou. Não se apresente novamente e não use saudações "
            "iniciais se já as usou no histórico."
        )
    return "\n".join(parts)
