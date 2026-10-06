import logging
import json
import re
import asyncio
import random
import time
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from django.utils import timezone
from asgiref.sync import sync_to_async, async_to_sync

# Importações necessárias do projeto
from core.models import Provedor, AuditLog
from ai.tools.niohub._runtime import DatabaseTools
from ai.tools.niohub._runtime import DATABASE_FUNCTION_MAPPING
from core.sgp_client import SGPClient, SGPInvalidResponse
from core.fatura_service import FaturaService
from core.redis_memory_service import redis_memory_service
from conversations.closing_service import closing_service, stamp_automation_closure_trace
from core.chat_migration_service import chat_migration_service

logger = logging.getLogger(__name__)

# Nomes legado -> limpos (execucao interna)
ERP_NAME_ALIASES = {
    "consultar_cliente_sgp": "buscar_cliente",
    "gerar_fatura_completa": "gerar_fatura",
    "verificar_manutencao_sgp": "verificar_manutencao",
    "verificar_acesso_sgp": "verificar_acesso",
    "criar_chamado_tecnico": "abrir_chamado",
    "liberar_por_confianca": "liberar_confianca",
    "consultar_viabilidade": "consulta_viabilidade",
    "escolher_contrato": "selecionar_contrato",
}

NIOHUB_NAME_ALIASES = {
    "buscar_equipes_disponiveis": "buscar_equipes",
    "buscar_membro_disponivel_equipe": "buscar_membro_equipe",
    "executar_transferencia_conversa": "transferir_conversa",
    "transferir_conversa_inteligente": "transferir_inteligente",
    "buscar_conversas_ativas": "buscar_conversas",
    "criar_resumo_suporte": "criar_resumo",
    "encerrar_atendimento": "encerrar_atendimento",
}

def normalize_erp_tool_name(name: str) -> str:
    return ERP_NAME_ALIASES.get(name, name)

def normalize_niohub_tool_name(name: str) -> str:
    return NIOHUB_NAME_ALIASES.get(name, name)


def _parse_coordenadas(function_args: dict) -> Optional[tuple]:
    """Extrai (lat, lng) de latitude/longitude ou string coordenada."""
    lat = function_args.get("latitude")
    lng = function_args.get("longitude")
    if lat is not None and lng is not None and str(lat).strip() and str(lng).strip():
        return str(lat).strip().replace(",", "."), str(lng).strip().replace(",", ".")

    raw = (
        function_args.get("coordenada")
        or function_args.get("coordenadas")
        or function_args.get("location")
        or ""
    )
    raw = str(raw).strip()
    if not raw:
        return None

    # Aceita "lat,lng" / "lat lng" / "lat;lng"
    cleaned = raw.replace(";", ",").replace("|", ",")
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    else:
        parts = [p.strip() for p in cleaned.split() if p.strip()]
    if len(parts) >= 2:
        return parts[0].replace(",", "."), parts[1].replace(",", ".")
    return None


def _bool_flag_viabilidade(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("1", "true", "sim", "viavel", "ok"):
        return True
    if s in ("0", "false", "nao", "não", "inviavel", "inviável"):
        return False
    return None


def _avaliar_viabilidade_endereco(sgp_res) -> dict:
    """Normaliza resposta de POST /api/ura/viabilidade/ (ex.: {"viabilidade": true})."""
    if not isinstance(sgp_res, dict):
        return {
            "consultado": True,
            "sucesso": False,
            "viavel": False,
            "erro": "Resposta invalida do SGP (endereco).",
            "resultados": [],
        }
    if sgp_res.get("success") is False or sgp_res.get("error"):
        return {
            "consultado": True,
            "sucesso": False,
            "viavel": False,
            "erro": sgp_res.get("error") or sgp_res.get("msg") or "Falha na consulta por endereco.",
            "resultados": [],
        }

    resultados = (
        sgp_res.get("results")
        or sgp_res.get("resultados")
        or sgp_res.get("viabilidades")
        or sgp_res.get("data")
        or []
    )
    if isinstance(resultados, dict):
        resultados = [resultados]
    if not isinstance(resultados, list):
        resultados = []

    viavel = None
    for key in ("viabilidade", "viavel", "viable", "tem_viabilidade", "cobertura"):
        if key in sgp_res:
            parsed = _bool_flag_viabilidade(sgp_res.get(key))
            if parsed is not None:
                viavel = parsed
            break
    if viavel is None and resultados:
        first = resultados[0] if isinstance(resultados[0], dict) else {}
        for key in ("viabilidade", "viavel", "viable", "tem_viabilidade", "cobertura"):
            if key in first:
                parsed = _bool_flag_viabilidade(first.get(key))
                if parsed is not None:
                    viavel = parsed
                break
    if viavel is None and resultados:
        viavel = True

    resumo = []
    for item in resultados[:8]:
        if not isinstance(item, dict):
            continue
        resumo.append({
            k: item.get(k)
            for k in (
                "logradouro", "rua", "bairro", "cidade", "cep",
                "numero", "numero_inicial", "numero_final",
                "viabilidade", "viavel", "status", "msg", "mensagem", "tecnologia",
                "observacao", "obs",
            )
            if item.get(k) is not None
        })

    return {
        "consultado": True,
        "sucesso": True,
        "viavel": bool(viavel),
        "conclusivo": viavel is not None,
        "status": sgp_res.get("status"),
        "msg": sgp_res.get("msg") or sgp_res.get("message") or "",
        "quantidade_resultados": len(resultados),
        "resultados": resumo,
    }


def _avaliar_viabilidade_coordenadas(sgp_res) -> dict:
    """Normaliza resposta de GET /api/ura/viabilidadeinstalacao/."""
    if not isinstance(sgp_res, dict):
        return {
            "consultado": True,
            "sucesso": False,
            "viavel": False,
            "erro": "Resposta invalida do SGP (coordenadas).",
            "caixas": [],
        }
    if sgp_res.get("success") is False or sgp_res.get("error"):
        return {
            "consultado": True,
            "sucesso": False,
            "viavel": False,
            "erro": sgp_res.get("error") or "Falha na consulta por coordenadas.",
            "caixas": [],
        }

    raw = sgp_res.get("raw", sgp_res)
    caixas = []
    if isinstance(raw, list):
        for bloco in raw:
            if not isinstance(bloco, dict):
                continue
            maps = bloco.get("SGPMaps") or bloco.get("sgpmaps") or bloco.get("caixas") or []
            if isinstance(maps, list):
                for c in maps:
                    if isinstance(c, dict):
                        caixas.append({
                            "nome": c.get("nome"),
                            "distancia": c.get("distancia"),
                            "lat": c.get("lat"),
                            "lng": c.get("lng"),
                        })
    elif isinstance(raw, dict):
        maps = raw.get("SGPMaps") or raw.get("sgpmaps") or raw.get("caixas") or []
        if isinstance(maps, list):
            for c in maps:
                if isinstance(c, dict):
                    caixas.append({
                        "nome": c.get("nome"),
                        "distancia": c.get("distancia"),
                        "lat": c.get("lat"),
                        "lng": c.get("lng"),
                    })

    caixas_ord = sorted(
        caixas,
        key=lambda x: (x.get("distancia") is None, x.get("distancia") or 0),
    )[:8]

    return {
        "consultado": True,
        "sucesso": True,
        "viavel": len(caixas) > 0,
        "quantidade_caixas": len(caixas),
        "caixas": caixas_ord,
    }


# Base de conhecimento pedindo fatura completa (boleto + PIX), como no chatbot paymentMethod=ambos
_KB_FATURA_AMBOS_PATTERNS = (
    "boleto e pix",
    "pix e boleto",
    "boleto/pix",
    "pix/boleto",
    "boleto + pix",
    "pix + boleto",
    "fatura completa",
    "fatura do cliente completa",
    "completa boleto",
    "enviar boleto e pix",
    "envie boleto e pix",
    "envia boleto e pix",
    "sempre envia a fatura",
    "sempre envie a fatura",
    "as duas formas",
    "duas formas de pagamento",
    "formas de pagamento",
    "ambos boleto",
    "ambos pix",
    "boleto tambem",
    "boleto também",
    "enviar o boleto",
    "envie o boleto",
    "envia o boleto",
    "enviar boleto",
    "envie boleto",
    "envia boleto",
)


def _normalize_tipo_pagamento(raw: Optional[str], default: str = "pix") -> str:
    """Normaliza para pix | boleto | ambos (mesmo contrato do chatbot/fatura_service)."""
    tp = str(raw or "").lower().strip()
    if not tp:
        return default
    if any(x in tp for x in ("ambos", "ambas", "todos", "completo", "completa", "pix_boleto", "boleto_pix")):
        return "ambos"
    if "boleto" in tp and "pix" in tp:
        return "ambos"
    if "boleto" in tp:
        return "boleto"
    if "pix" in tp:
        return "pix"
    return default


def provedor_exige_fatura_boleto_e_pix(provedor) -> bool:
    """
    Detecta na base de conhecimento (dados_adicionais) se o provedor pede
    fatura completa (boleto + PIX), ex.: "sempre envia a fatura completa Boleto e PIX".
    """
    kb = (getattr(provedor, "dados_adicionais", None) or "").strip().lower()
    if not kb:
        return False
    # Tipografia comum: "Boleto é PIX" = "Boleto e PIX"
    kb_n = (
        kb.replace(" é ", " e ")
        .replace(" eh ", " e ")
        .replace(" & ", " e ")
    )
    if not any(k in kb_n for k in ("fatura", "boleto", "pix", "pagamento", "cobran")):
        return False
    return any(p in kb_n for p in _KB_FATURA_AMBOS_PATTERNS)


def _resolve_tipo_pagamento_fatura(provedor, function_args: dict) -> str:
    """
    Prioridade:
    1) Regra na base de conhecimento → ambos
    2) Parametro da tool (IA) → pix|boleto|ambos
    3) Padrao → pix
    """
    if provedor_exige_fatura_boleto_e_pix(provedor):
        return "ambos"
    raw = (
        function_args.get("tipo_pagamento")
        or function_args.get("paymentMethod")
        or function_args.get("tipoPagamento")
    )
    return _normalize_tipo_pagamento(raw, default="pix")


def _extract_cpf_cnpj(text: str) -> Optional[str]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if len(digits) in (11, 14) and digits.isdigit():
        return digits
    return None


def _resolver_contrato_id(cid_arg, conversation_state: Optional[dict] = None) -> Dict[str, Any]:
    """
    Garante o ID de contrato do ERP (ex.: 2255), nunca CPF/CNPJ.
    Se a IA passar CPF, usa contrato_id salvo no estado após buscar_cliente.
    """
    state = conversation_state or {}
    state_cid = re.sub(r"[^\d]", "", str(state.get("contrato_id") or state.get("contrato") or "")) or None
    raw = re.sub(r"[^\d]", "", str(cid_arg or "")) if cid_arg is not None else ""

    def _is_doc(digits: str) -> bool:
        return bool(digits) and len(digits) in (11, 14)

    # Com a lista do cliente no estado, só vale contrato dele: posição da lista vira o id real
    # e qualquer outro número (ex.: "1" passado como id) é descartado.
    ids_cliente = [cid for cid in (_contrato_id_of(c) for c in _lista_contratos_estado(state)) if cid]
    if raw and not _is_doc(raw) and ids_cliente and raw not in ids_cliente:
        idx = int(raw) if raw.isdigit() else 0
        raw = ids_cliente[idx - 1] if 1 <= idx <= len(ids_cliente) else ""

    # Estado tem ID de contrato válido
    if state_cid and not _is_doc(state_cid):
        if state.get("contrato_escolhido") and raw and not _is_doc(raw) and raw != state_cid:
            return {
                "ok": False,
                "erro": (
                    f"O cliente escolheu o contrato {state_cid} nesta conversa. "
                    "Se ele pediu outro contrato, chame selecionar_contrato com o contrato que ele indicou "
                    "e depois repita esta acao; senao, repita sem informar contrato."
                ),
            }
        if not raw or _is_doc(raw) or raw == state_cid:
            return {
                "ok": True,
                "contrato_id": state_cid,
                "corrigido_de_cpf": bool(raw and _is_doc(raw)),
            }

    # Argumento parece ID de contrato (não CPF/CNPJ)
    if raw and not _is_doc(raw):
        return {"ok": True, "contrato_id": raw}

    if raw and _is_doc(raw):
        return {
            "ok": False,
            "erro": (
                "O parametro 'contrato' recebeu CPF/CNPJ. "
                "Chame buscar_cliente e use o contrato_id retornado (nao o CPF)."
            ),
        }

    return {
        "ok": False,
        "erro": "Contrato obrigatorio. Chame buscar_cliente e use o contrato_id retornado.",
    }


def _extract_pppoe_login(contrato: Optional[dict]) -> str:
    """Extrai login PPPoE de um contrato SGP/IXC."""
    if not isinstance(contrato, dict):
        return ""
    for key in (
        "servico_login",
        "pppoe_login",
        "login",
        "usuario",
        "usuario_pppoe",
        "login_pppoe",
        "user",
    ):
        val = contrato.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _contrato_id_of(contrato: Optional[dict]) -> str:
    if not isinstance(contrato, dict):
        return ""
    raw = contrato.get("contratoId") or contrato.get("contrato_id") or contrato.get("contrato") or ""
    return re.sub(r"[^\d]", "", str(raw)) or str(raw or "").strip()


def _endereco_contrato(contrato: Optional[dict]) -> str:
    if not isinstance(contrato, dict):
        return ""
    end_parts = [
        contrato.get("endereco_logradouro"),
        contrato.get("endereco_numero"),
        contrato.get("endereco_bairro"),
        contrato.get("endereco_cidade"),
        contrato.get("endereco_uf"),
    ]
    return " ".join(str(p).strip() for p in end_parts if p and str(p).strip().lower() != "none")


def _resumo_contrato(contrato: Optional[dict]) -> dict:
    cid = _contrato_id_of(contrato)
    login_item = _extract_pppoe_login(contrato)
    return {
        "contrato_id": cid or None,
        "status": (contrato or {}).get("contratoStatusDisplay") if contrato else None,
        "plano": (contrato or {}).get("servico_plano") or (contrato or {}).get("planointernet"),
        "endereco": _endereco_contrato(contrato) or None,
        "pppoe_login": login_item or None,
    }


def _lista_contratos_estado(conversation_state: Optional[dict]) -> list:
    contratos = (conversation_state or {}).get("contratos") or []
    return [c for c in contratos if isinstance(c, dict)]


def _precisa_escolher_contrato(conversation_state: Optional[dict]) -> bool:
    state = conversation_state or {}
    if state.get("contrato_escolhido"):
        return False
    # Com 2+ contratos: primeiro confirma dados; so depois escolhe o contrato.
    if state.get("precisa_confirmar_dados"):
        return False
    if state.get("precisa_escolher_contrato"):
        return True
    return str(state.get("step") or "") == "AGUARDANDO_ESCOLHA_CONTRATO"


_CONFIRMACAO_DADOS_TOKENS = {
    "sim", "s", "ok", "okay", "isso", "isso mesmo", "esse", "este", "esses",
    "correto", "corretos", "confirmo", "confirmar", "confirmado", "pode",
    "pode ser", "pode continuar", "ta certo", "tá certo", "esta certo",
    "está certo", "positivo", "afirmativo", "uhum", "yes", "certo",
    "esses mesmos", "esse mesmo", "esta correto", "está correto",
    "e", "é", "eh", "ahh", "aham", "ahm", "hum", "hmm", "blz", "beleza",
    "perfeito", "exato", "exatamente", "claro", "com certeza", "ss", "ssim",
}


def _precisa_confirmar_dados(conversation_state: Optional[dict]) -> bool:
    state = conversation_state or {}
    if state.get("contrato_escolhido"):
        return False
    if state.get("precisa_confirmar_dados"):
        return True
    return str(state.get("step") or "") in (
        "AGUARDANDO_CONFIRMACAO_DADOS",
        "AGUARDANDO_CONFIRMACAO_CONTRATO",
    )


def _aguardando_contrato_ou_confirmacao(conversation_state: Optional[dict]) -> bool:
    return _precisa_escolher_contrato(conversation_state) or _precisa_confirmar_dados(conversation_state)


# Status de ocorrência SGP que contam como chamado em andamento: 0 Aberta, 3 Pendente.
CHAMADO_STATUS_EM_ANDAMENTO = (0, 3)


def _senha_central_contrato(conversation_state: Optional[dict], contrato_id) -> Optional[str]:
    cid = re.sub(r"[^\d]", "", str(contrato_id or ""))
    for c in _lista_contratos_estado(conversation_state):
        if _contrato_id_of(c) == cid:
            return c.get("contratoCentralSenha") or None
    return None


def _consultar_chamados_em_andamento(sgp, conversation_state: Optional[dict], contrato_id) -> Dict[str, Any]:
    state = conversation_state or {}
    try:
        res = sgp.listar_chamados(
            contrato=contrato_id,
            cpf_cnpj=state.get("cpf_cnpj"),
            senha=_senha_central_contrato(state, contrato_id),
        )
    except Exception as e:
        logger.warning("[SGP] listar_chamados falhou | contrato=%s | erro=%s", contrato_id, e)
        return {"ok": False, "erro": str(e)}
    if not isinstance(res, dict) or not res.get("success"):
        return {"ok": False, "erro": (res or {}).get("error") if isinstance(res, dict) else "resposta invalida"}
    chamados = res.get("chamados") or []
    em_andamento = [
        {
            "protocolo": c.get("protocolo") or c.get("id"),
            "situacao": c.get("status_descricao"),
            "tipo": c.get("tipo"),
            "data_abertura": c.get("data_cadastro"),
            "data_agendamento": c.get("data_agendamento"),
        }
        for c in chamados
        if c.get("status") in CHAMADO_STATUS_EM_ANDAMENTO
    ]
    return {"ok": True, "em_andamento": em_andamento, "total": len(chamados)}


def _resposta_consulta_chamados(consulta: Dict[str, Any], contrato_id) -> Dict[str, Any]:
    if not consulta.get("ok"):
        return {
            "success": True,
            "contrato_id": contrato_id,
            "consulta_indisponivel": True,
            "nota": (
                "Nao foi possivel consultar os chamados no sistema (uso interno: NAO mencione isso ao cliente). "
                "Decida pelo que o cliente quer: se ele pediu uma visita/chamado novo, abra com abrir_chamado; "
                "se ele so queria saber de um chamado existente, encaminhe para a equipe verificar "
                "(transferir_inteligente)."
            ),
        }
    if consulta.get("em_andamento"):
        return {
            "success": True,
            "contrato_id": contrato_id,
            "tem_chamado_aberto": True,
            "chamados_abertos": consulta["em_andamento"],
            "nota": (
                "O cliente JA tem chamado em andamento neste contrato (situacao Aberta ou Pendente). "
                "Informe com suas palavras o que for relevante para ele (protocolo, situacao, agendamento). "
                "NAO abra outro chamado."
            ),
        }
    return {
        "success": True,
        "contrato_id": contrato_id,
        "tem_chamado_aberto": False,
        "chamados_abertos": [],
        "nota": (
            "Nenhum chamado Aberto ou Pendente neste contrato (nunca mencione chamados encerrados). "
            "Decida pelo que o cliente quer: se ele pediu visita tecnica/chamado, abra com abrir_chamado "
            "(no conteudo, o pedido e a data/periodo que ele informou) e informe o protocolo; "
            "se ele so queria saber de um chamado, informe que nao ha nenhum em aberto e veja se ele quer abrir."
        ),
    }


def _escolha_e_confirmacao(escolha) -> bool:
    """
    Interpreta afirmação do cliente no contexto de confirmação.
    Não depende de uma única palavra-chave: qualquer resposta curta afirmativa
    (isso, esse mesmo, e, ss, uhum…) conta como confirmação.
    """
    raw = str(escolha or "").strip().lower()
    raw = re.sub(r"[!?.,;:\"'`]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return False
    if raw in _CONFIRMACAO_DADOS_TOKENS:
        return True
    # Respostas muito curtas afirmativas (ex.: "e", "ss", "ok!")
    if len(raw) <= 12 and re.fullmatch(
        r"(e|é|eh|s+|ss|sim+|ok+|okay|isso|uhum|hum+|hmm+|blz|yes+)",
        raw,
    ):
        return True
    # "sim, está certo", "sim pode continuar", "uhum ta certo", "isso ai"
    if re.match(
        r"^(sim+|s|ok|okay|pode|certo|isso|esse|este|uhum|positivo|afirmativo|yes|e|é|eh|blz|beleza)\b",
        raw,
    ):
        return True
    if any(
        t in raw
        for t in (
            "esta certo",
            "está certo",
            "ta certo",
            "tá certo",
            "esta correto",
            "está correto",
            "pode continuar",
            "pode ser",
            "isso mesmo",
            "esse mesmo",
            "estes mesmos",
            "esses mesmos",
            "isso ai",
            "isso aí",
            "esse ai",
            "esse aí",
            "confirmo",
            "com certeza",
        )
    ):
        return True
    return False


def _persistir_dados_confirmados(
    provedor,
    conversation_id,
    channel,
    phone,
    conversation_state: dict,
    *,
    multiplos: bool,
) -> dict:
    """Apos 'sim' nos dados: 1 contrato → segue escolha automatica depois; 2+ → pede qual contrato."""
    if multiplos:
        updates = {
            "dados_confirmados": True,
            "precisa_confirmar_dados": False,
            "precisa_escolher_contrato": True,
            "contrato_escolhido": False,
            "step": "AGUARDANDO_ESCOLHA_CONTRATO",
            "confirmacao_pedida": False,
        }
    else:
        updates = {
            "dados_confirmados": True,
            "precisa_confirmar_dados": False,
            "confirmacao_pedida": False,
        }
    if conversation_id:
        redis_memory_service.update_ai_state_sync(
            provedor.id, conversation_id, updates, channel, phone
        )
    if isinstance(conversation_state, dict):
        conversation_state.update(updates)
    return updates


def _resposta_precisa_confirmar_dados(contratos: list, nome: str = "") -> dict:
    resumo = [_resumo_contrato(c) for c in contratos]
    multiplos = len(contratos) >= 2
    return {
        "success": False,
        "precisa_confirmar_dados": True,
        "precisa_escolher_contrato": False,
        "quantidade_contratos": len(contratos),
        "nome": nome or None,
        "contratos": resumo,
        "nota": (
            "Use APENAS mensagem_cliente_sugerida / contratos deste retorno "
            "(dados reais do ERP). Nunca invente ID ou endereco. "
            "Redija com naturalidade. "
            + (
                "Peca UMA vez se os dados estao corretos. Ainda NAO pergunte qual contrato. "
                if multiplos
                else "Peca UMA vez se os dados estao corretos. "
            )
            + "NAO chame gerar_fatura / verificar_acesso / abrir_chamado ainda. "
            "Quando o cliente confirmar, chame selecionar_contrato com escolha='sim'."
        ),
    }


def _match_contrato_escolha(escolha, contratos: list) -> Optional[dict]:
    """Casa escolha do cliente: id do contrato (10624) ou número da lista (1, 2...)."""
    if not escolha or not contratos:
        return None
    raw = str(escolha).strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        raw_l = raw.lower()
        if len(raw_l) < 4:
            return None
        for c in contratos:
            end = _endereco_contrato(c).lower()
            if end and raw_l in end:
                return c
        return None

    for c in contratos:
        cid = _contrato_id_of(c)
        if cid and cid == digits:
            return c

    if digits.isdigit():
        idx = int(digits)
        if 1 <= idx <= len(contratos):
            return contratos[idx - 1]
    return None


def _resposta_precisa_escolher_contrato(contratos: list, nome: str = "") -> dict:
    resumo = [_resumo_contrato(c) for c in contratos]
    return {
        "success": False,
        "precisa_escolher_contrato": True,
        "precisa_confirmar_dados": False,
        "dados_confirmados": True,
        "quantidade_contratos": len(contratos),
        "nome": nome or None,
        "contratos": resumo,
        "nota": (
            "Os dados do cadastro JA foram confirmados. "
            "NAO peca confirmar nome/endereco de novo. "
            "Pergunte com naturalidade para qual contrato e o atendimento "
            "(numero da lista ou id). Uma pergunta so. "
            "Quando o cliente escolher, chame selecionar_contrato. "
            "NAO chame gerar_fatura / verificar_acesso / abrir_chamado ainda."
        ),
    }


def _persistir_contrato_escolhido(
    provedor,
    conversation_id,
    channel,
    phone,
    contrato: dict,
    conversation_state: dict,
) -> dict:
    cid = _contrato_id_of(contrato)
    is_suspenso = str(contrato.get("contratoStatusDisplay") or "").strip().lower() in (
        "suspenso",
        "suspensa",
    )
    login_salvo = _extract_pppoe_login(contrato)
    updates = {
        "contrato_id": cid,
        "contrato_escolhido": True,
        "dados_confirmados": True,
        "precisa_escolher_contrato": False,
        "precisa_confirmar_dados": False,
        "confirmacao_pedida": False,
        "step": "CONTRATO_SELECIONADO",
        "servico_plano": contrato.get("servico_plano") or contrato.get("planointernet"),
        "contrato_status_display": contrato.get("contratoStatusDisplay"),
        "motivo_status": contrato.get("motivo_status"),
        "is_suspenso": is_suspenso,
    }
    if login_salvo:
        updates["pppoe_login"] = login_salvo
        updates["servico_login"] = login_salvo
    if conversation_id:
        redis_memory_service.update_ai_state_sync(
            provedor.id, conversation_id, updates, channel, phone
        )
    if isinstance(conversation_state, dict):
        conversation_state.update(updates)
    return updates


def _salvar_pedido_cliente(provedor, conversation_id, channel, phone, conversation_state: dict, pedido) -> None:
    """Guarda no Redis o que o cliente quer, como a própria IA entendeu da conversa."""
    pedido = str(pedido or "").strip()[:300]
    if not pedido or pedido == str(conversation_state.get("pedido_cliente") or ""):
        return
    if conversation_id:
        redis_memory_service.update_ai_state_sync(
            provedor.id, conversation_id, {"pedido_cliente": pedido}, channel, phone
        )
    conversation_state["pedido_cliente"] = pedido


def _salvar_chamados_no_estado(provedor, conversation_id, channel, phone, conversation_state: dict, dados: dict) -> None:
    if conversation_id:
        try:
            redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, dados, channel, phone)
        except Exception:
            logger.debug("[AIACTIONS] Falha ao salvar chamados no Redis", exc_info=True)
    conversation_state.update(dados)


def _debug_log(message: str, data: Dict[str, Any], *, location: str, hypothesis_id: str, run_id: str = "run1") -> None:
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        log_path = r"e:\niochat\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass

class AIActionsHandler:
    """
    Sub-agente responsável pela execução de ações e chamadas de funções (Tools).
    Gerencia integrações com SGP, Banco de Dados e outras ferramentas externas.
    """

    def __init__(self, openai_service=None):
        self.openai_service = openai_service

    def _is_valid_cpf_cnpj(self, cpf_cnpj: str) -> bool:
        """Valida se a string é um CPF ou CNPJ válido"""
        if not cpf_cnpj:
            return False
        clean = re.sub(r'[^\d]', '', str(cpf_cnpj))
        if len(clean) not in [11, 14]:
            return False
        return clean.isdigit()

    def _verificar_horario_atendimento(self, provedor: Provedor) -> Dict[str, Any]:
        """Verifica se está dentro do horário de atendimento"""
        if self.openai_service and hasattr(self.openai_service, 'formatter'):
            return self.openai_service.formatter._verificar_horario_atendimento(provedor)
        return {'dentro_horario': True, 'proximo_horario': None, 'mensagem': None}

    def _formatar_horarios_atendimento(self, horarios: list) -> str:
        """Formata os horários de atendimento no padrão solicitado pelo usuário (sem emojis)"""
        if not horarios or not isinstance(horarios, list): return ""
        
        dias_semana_map = {
            'segunda': 'Segunda-feira', 'terça': 'Terça-feira', 'terca': 'Terça-feira',
            'quarta': 'Quarta-feira', 'quinta': 'Quinta-feira', 'sexta': 'Sexta-feira',
            'sábado': 'Sábado', 'sabado': 'Sábado', 'domingo': 'Domingo'
        }
        
        linhas = ["Nosso horário de atendimento é:\n"]
        
        for d in horarios:
            dia_raw = d.get('dia', '').lower().strip()
            # Remover sufixos se houver e re-adicionar padrão
            dia_base = dia_raw.split('-')[0].split(' ')[0]
            dia_formatado = dias_semana_map.get(dia_base, dia_raw.capitalize())
            
            periodos = d.get('periodos', [])
            if not periodos:
                linhas.append(f"{dia_formatado}: Fechado")
            else:
                p_strings = []
                for p in periodos:
                    inicio = p.get('inicio', '')
                    fim = p.get('fim', '')
                    if inicio and fim:
                        p_strings.append(f"{inicio} às {fim}")
                
                if p_strings:
                    horario_str = " e ".join(p_strings)
                    linhas.append(f"{dia_formatado}: {horario_str}")
                else:
                    linhas.append(f"{dia_formatado}: Fechado")
        
        return "\n".join(linhas)

    def _formatar_contratos_padrao(self, contratos: list, nome_cliente: str) -> str:
        """Estrutura dos contratos; a IA redige a pergunta com naturalidade."""
        nome = (nome_cliente or "").strip() or "Cliente"
        if len(contratos) == 1:
            titulo = f"Encontrei seu contrato, {nome}!"
        else:
            titulo = f"Encontrei seus contratos, {nome}!"

        linhas = [titulo, "", "Aqui estão os detalhes:", ""]
        for idx, c in enumerate(contratos, 1):
            cid = str(c.get("contratoId") or c.get("contrato_id") or "")
            end = _endereco_contrato(c).upper() or "ENDEREÇO NÃO INFORMADO"
            linhas.append(f"{idx} - Contrato ({cid}): {end}")
        return "\n".join(linhas)

    def execute_database_function(self, provedor: Provedor, function_name: str, function_args: dict, contexto: dict = None) -> dict:
        """Executa funções de banco de dados (Transferências, etc.) com ISOLAMENTO total"""
        try:
            function_name = normalize_niohub_tool_name(function_name)
            if not provedor: return {"success": False, "erro": "Provedor não identificado para execução de banco de dados."}

            # Identificadores para memória e isolamento
            conv = contexto.get('conversation') if contexto else None
            conversation_id = conv.id if conv else None
            channel = contexto.get('canal', 'wa') if contexto else 'wa'
            phone = contexto.get('contact', {}).phone if contexto and contexto.get('contact') else (contexto.get('contact_phone', 'unknown') if contexto else 'unknown')

            # Validação forte de tenant
            if conv and conv.inbox and conv.inbox.provedor_id:
                ctx_pid = conv.inbox.provedor_id
                if int(ctx_pid) != int(provedor.id):
                    return {"success": False, "erro": "Isolamento de provedor violado."}

            # Carregar estado para idempotência se disponível
            conversation_state = {}
            if conversation_id:
                conversation_state = redis_memory_service.get_ai_state_sync(provedor.id, conversation_id, channel, phone)

            # Cálculo de hash para idempotência
            args_hash = hashlib.sha256(json.dumps(function_args, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            # Verificação de idempotência
            if (conversation_state.get("last_function") == function_name and 
                conversation_state.get("last_function_args_hash") == args_hash and 
                conversation_state.get("last_function_success") is True):
                logger.info(f"[ACTIONS] Ação {function_name} já executada com sucesso. Retornando cache.")
                return {
                    "success": True,
                    "cached": True,
                    "protocolo": conversation_state.get("protocolo"),
                    "nota": "Acao ja executada nesta conversa. Monte a resposta com base no contexto.",
                }

            # Ferramentas de banco isoladas por provedor
            db_tools = DatabaseTools(provedor=provedor)
            method_name = DATABASE_FUNCTION_MAPPING.get(function_name)
            if not method_name: return {"success": False, "erro": f"Ação '{function_name}' não mapeada."}
            
            # Garantir conversation_id correto (injetar automaticamente se não fornecido)
            if conversation_id:
                # Para funções que precisam de conversation_id, injetar automaticamente se não fornecido
                if function_name in ['criar_resumo', 'transferir_conversa', 'transferir_inteligente', 'encerrar_atendimento', 'criar_resumo_suporte', 'executar_transferencia_conversa', 'transferir_conversa_inteligente']:
                    if 'conversation_id' not in function_args or not function_args.get('conversation_id'):
                        function_args['conversation_id'] = conversation_id
                # Para outras funções, apenas atualizar se já existir
                elif 'conversation_id' in function_args and function_args.get('conversation_id'):
                    function_args['conversation_id'] = conversation_id
            
            method = getattr(db_tools, method_name)
            
            # Caso especial para encerramento
            if function_name == "encerrar_atendimento":
                if conv:
                    stamp_automation_closure_trace(conv, 'ia_encerrar_atendimento')
                    closing_service.request_closing(conv)
                    redis_memory_service.clear_conversation_memory_sync(provedor_id=provedor.id, conversation_id=conv.id, channel=channel, phone=phone)
                    from ai.tools.niohub.horario import obter_horario_local

                    info_hora = obter_horario_local(provedor)
                    nome_provedor = (getattr(provedor, "nome", None) or "").strip() or "nossa empresa"

                    nome_cliente = ""
                    for candidate in (
                        conversation_state.get("nome_cliente"),
                        getattr(getattr(conv, "contact", None), "name", None),
                    ):
                        raw = (candidate or "").strip()
                        if not raw:
                            continue
                        # Ignorar nomes que são só telefone/números
                        digits = "".join(c for c in raw if c.isdigit())
                        if digits and len(digits) >= 8 and len(digits) >= len(raw) - 2:
                            continue
                        nome_cliente = raw.split()[0].title()
                        break

                    res = {
                        "success": True,
                        "encerrado": True,
                        "saudacao": info_hora.get("saudacao"),
                        "despedida": info_hora.get("despedida"),
                        "hora": info_hora.get("hora"),
                        "nome_cliente": nome_cliente or None,
                        "nome_provedor": nome_provedor,
                        "nota": (
                            "Atendimento encerrado. Faca uma despedida completa (nao so a frase curta). "
                            + (
                                f"Use o primeiro nome do cliente ({nome_cliente}). "
                                if nome_cliente
                                else ""
                            )
                            + f"Agradeça o contato em nome de {nome_provedor}, com suas palavras. "
                            f"A despedida deve combinar com o horario ({info_hora.get('despedida')}). "
                            "Nao responda apenas com a despedida curta."
                        ),
                    }
                else:
                    return {"success": False, "erro": "Conversa não identificada."}
            else:
                res = method(**function_args)

            # Persistir idempotência após sucesso
            if res.get('success') and conversation_id:
                redis_memory_service.update_ai_state_sync(
                    provedor.id, conversation_id,
                    {
                        "last_function": function_name,
                        "last_function_args_hash": args_hash,
                        "last_function_success": True,
                        "protocolo": res.get("protocolo")
                    },
                    channel, phone
                )
            
            return res
        except Exception as e:
            logger.error(f"Erro ao executar ação de banco: {e}", exc_info=True)
            return {"success": False, "erro": str(e)}

    def execute_integration_function(self, provedor: Provedor, function_name: str, function_args: dict, contexto: dict = None) -> dict:
        """Executa funções do SGP (Consulta, Fatura, Chamado, etc.) com ISOLAMENTO total"""
        try:
            function_name = normalize_erp_tool_name(function_name)
            if not provedor: return {"success": False, "erro": "Provedor não identificado."}

            # Identificadores com normalização estrita
            conv = contexto.get('conversation') if contexto else None
            conversation_id = conv.id if conv else None
            channel = redis_memory_service.normalize_channel(contexto.get('canal', 'whatsapp') if contexto else 'whatsapp')
            phone = contexto.get('contact', {}).phone if contexto and contexto.get('contact') else (contexto.get('contact_phone', 'unknown') if contexto else 'unknown')

            # Validação tenant
            if conv and conv.inbox and conv.inbox.provedor_id:
                if int(conv.inbox.provedor_id) != int(provedor.id):
                    return {"success": False, "erro": "Isolamento violado."}

            # Carregar estado
            conversation_state = {}
            if conversation_id:
                conversation_state = redis_memory_service.get_ai_state_sync(provedor.id, conversation_id, channel, phone)

            _salvar_pedido_cliente(
                provedor, conversation_id, channel, phone, conversation_state,
                function_args.pop("pedido_cliente", None),
            )

            # Cálculo de hash para idempotência
            args_hash = hashlib.sha256(json.dumps(function_args, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            # Verificação de idempotência específica para SGP (especialmente fatura)
            if function_name == "gerar_fatura" and conversation_state.get("fatura_enviada"):
                sent_cid = str(conversation_state.get("fatura_enviada_contrato_id") or "")
                req_resolved = _resolver_contrato_id(
                    function_args.get("contrato_id") or function_args.get("contrato"),
                    conversation_state,
                )
                req_cid = str(req_resolved.get("contrato_id") or "")
                if req_resolved.get("ok") and (not sent_cid or not req_cid or sent_cid == req_cid):
                    return {
                        "success": True,
                        "cached": True,
                        "fatura_ja_enviada": True,
                        "nota": "Fatura ja foi enviada nesta conversa. Informe isso ao cliente com suas palavras.",
                    }

            if (conversation_state.get("last_function") == function_name and 
                conversation_state.get("last_function_args_hash") == args_hash and 
                conversation_state.get("last_function_success") is True):
                return {
                    "success": True,
                    "cached": True,
                    "protocolo": conversation_state.get("protocolo"),
                    "nota": "Consulta ja realizada nesta conversa. Use o contexto para responder.",
                }

            # Integração SGP
            integracao = provedor.integracoes_externas or {}
            
            # Tentar buscar do objeto aninhado 'sgp' ou da raiz
            sgp_config = integracao.get('sgp', {}) if isinstance(integracao.get('sgp'), dict) else integracao
            
            sgp_url = sgp_config.get('sgp_url') or integracao.get('sgp_url')
            sgp_token = sgp_config.get('sgp_token') or integracao.get('sgp_token')
            sgp_app = sgp_config.get('sgp_app') or integracao.get('sgp_app')
            
            if not all([sgp_url, sgp_token, sgp_app]):
                logger.error(f"[SGP] Configuração incompleta para provedor {provedor.id}: url={bool(sgp_url)}, token={bool(sgp_token)}, app={bool(sgp_app)}")
                return {"success": False, "erro": "SGP não configurado corretamente."}
            
            sgp = SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)
            res = {"success": False, "erro": "Ação não reconhecida."}

            logger.info(
                "[SGP] Chamada | funcao=%s | provedor_id=%s | conversa=%s | canal=%s",
                function_name, provedor.id, conversation_id, channel
            )

            if function_name in (
                "gerar_fatura",
                "verificar_manutencao",
                "verificar_acesso",
                "abrir_chamado",
                "consultar_chamados",
                "liberar_confianca",
            ) and _aguardando_contrato_ou_confirmacao(conversation_state):
                contratos_pendentes = _lista_contratos_estado(conversation_state)
                escolha = (
                    function_args.get("contrato_id")
                    or function_args.get("contrato")
                    or function_args.get("escolha")
                )
                selecionado = _match_contrato_escolha(escolha, contratos_pendentes)
                if not selecionado and _escolha_e_confirmacao(escolha) and len(contratos_pendentes) == 1:
                    selecionado = contratos_pendentes[0]
                if selecionado:
                    _persistir_contrato_escolhido(
                        provedor, conversation_id, channel, phone, selecionado, conversation_state
                    )
                    logger.warning(
                        "[SGP] contrato auto-selecionado antes de %s | contrato=%s",
                        function_name, conversation_state.get("contrato_id"),
                    )
                elif _precisa_escolher_contrato(conversation_state):
                    return _resposta_precisa_escolher_contrato(
                        contratos_pendentes,
                        conversation_state.get("nome_cliente") or "",
                    )
                else:
                    return _resposta_precisa_confirmar_dados(
                        contratos_pendentes,
                        conversation_state.get("nome_cliente") or "",
            )

            if function_name == "buscar_cliente":
                # Priorizar CPF/CNPJ do input se fornecido
                cpf_cnpj = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj') or ''
                cpf_cnpj = str(cpf_cnpj).replace('.', '').replace('-', '').replace('/', '').strip()
                
                logger.info(f"[AIACTIONS] consultar_cliente_sgp | CPF={cpf_cnpj} (Input={function_args.get('cpf_cnpj')})")
                
                # 🚨 REGRA CRÍTICA: SEMPRE consultar o SGP - NUNCA usar dados da memória
                # Isso garante que sempre usamos dados reais e atualizados do SGP
                # e evita misturar dados de clientes diferentes ou de outros provedores
                try:
                    sgp_res = sgp.consultar_cliente(cpf_cnpj)
                except SGPInvalidResponse as e:
                    logger.error("[SGP] consultar_cliente_sgp | resposta inválida: %s", e)
                    return {
                        "success": False,
                        "erro": str(e) or "SGP indisponível no momento. Tente novamente em instantes.",
                    }
                except ValueError as e:
                    return {"success": False, "erro": str(e)}
                
                # 🚨 VALIDAÇÃO: Garantir que a resposta do SGP está no formato esperado
                if not isinstance(sgp_res, dict):
                    logger.error("[SGP] consultar_cliente_sgp | Resposta do SGP não é um dict: %s", type(sgp_res))
                    return {"success": False, "erro": "Erro ao consultar dados no SGP. Tente novamente."}
                
                # Extrair contratos do JSON do SGP
                # Formato esperado: {"msg": "...", "contratos": [{...}]}
                contratos_raw = sgp_res.get('contratos', [])
                if not isinstance(contratos_raw, list):
                    logger.error("[SGP] consultar_cliente_sgp | 'contratos' não é uma lista: %s", type(contratos_raw))
                    contratos_raw = []
                
                # Filtrar apenas contratos ativos/suspensos (não cancelados)
                contratos = [c for c in contratos_raw if isinstance(c, dict) and c.get('contratoStatusDisplay', '').lower() not in ['cancelado', 'cancelada']]

                logger.info(
                    "[SGP] consultar_cliente_sgp retornou | contratos=%s | cliente_encontrado=%s",
                    len(contratos), bool(contratos)
                )

                if not contratos:
                    res = {"success": True, "cliente_encontrado": False, "erro": "Nenhum contrato ativo/suspenso encontrado."}
                else:
                    # 🚨 REGRA CRÍTICA: Nome do TITULAR (CPF) deve vir EXCLUSIVAMENTE do JSON do SGP, nunca inventado.
                    # Estrutura esperada do SGP:
                    # {
                    #   "msg": "...",
                    #   "contratos": [
                    #     {
                    #       "razaoSocial": "AMANDA DINIZ DE SOUZA",  ← Nome está AQUI dentro do contrato
                    #       "cpfCnpj": "700.179.490-25",
                    #       ...
                    #     }
                    #   ]
                    # }
                    # 
                    # Ordem de prioridade:
                    # 1. Nome no nível superior da resposta (se existir)
                    # 2. Nome dentro de objeto 'cliente' (se existir)
                    # 3. Nome dentro do primeiro contrato (contratos[0].razaoSocial) ← CASO MAIS COMUM
                    # 4. Se nenhum existir, usar 'Cliente'
                    
                    nome = ''
                    # Tentar nível superior (geralmente não existe, mas verificar primeiro)
                    for key in ('razaoSocial', 'nome', 'nomeCliente'):
                        val = sgp_res.get(key)
                        if val and isinstance(val, str) and val.strip():
                            nome = val.strip()
                            logger.info("[SGP] consultar_cliente_sgp | Nome encontrado no nível superior: %s", key)
                            break
                    
                    # Tentar objeto 'cliente' (se existir)
                    if not nome and isinstance(sgp_res.get('cliente'), dict):
                        c = sgp_res.get('cliente', {})
                        nome = (c.get('razaoSocial') or c.get('nome') or '').strip()
                        if nome:
                            logger.info("[SGP] consultar_cliente_sgp | Nome encontrado em objeto 'cliente'")
                    
                    # CASO MAIS COMUM: Nome dentro do primeiro contrato (contratos[0].razaoSocial)
                    # 🚨 SEMPRE ler diretamente do JSON do SGP - nunca inventar
                    if not nome and contratos and len(contratos) > 0:
                        primeiro_contrato = contratos[0]
                        if isinstance(primeiro_contrato, dict):
                            razao_social_raw = primeiro_contrato.get('razaoSocial')
                            # Validar que razaoSocial existe e é string válida
                            if razao_social_raw and isinstance(razao_social_raw, str):
                                nome = razao_social_raw.strip()
                                logger.info(
                                    "[SGP] consultar_cliente_sgp | Nome lido do JSON do SGP: contratos[0].razaoSocial = '%s'",
                                    nome[:10] + "..." if len(nome) > 10 else nome
                                )
                            else:
                                logger.warning(
                                    "[SGP] consultar_cliente_sgp | contratos[0].razaoSocial não é string válida: %s (tipo: %s)",
                                    razao_social_raw, type(razao_social_raw)
                                )
                    
                    # 🚨 GARANTIA: Se chegou aqui sem nome, o SGP não retornou nome válido
                    # NUNCA inventar nome - sempre usar 'Cliente' como fallback seguro
                    
                    # 🚨 VALIDAÇÃO CRÍTICA: Garantir que o nome não seja vazio, inválido ou suspeito
                    # Se o nome vier vazio ou muito curto, usar 'Cliente' para evitar usar dados incorretos
                    if not nome or len(nome.strip()) < 3:
                        nome = 'Cliente'
                        logger.warning(
                            "[SGP] consultar_cliente_sgp | Nome inválido ou vazio detectado | CPF=%s | usando 'Cliente' como fallback",
                            cpf_cnpj[:3] + "***" + cpf_cnpj[-2:] if len(cpf_cnpj) >= 5 else "***"
                        )

                    # Log detalhado para diagnóstico: nome exato que será usado (mascarado parcialmente)
                    nome_mascarado = nome[:3] + "***" + nome[-2:] if len(nome) > 5 else "***" if nome != "Cliente" else "Cliente"
                    primeiro_contrato_razao = contratos[0].get('razaoSocial', '') if contratos else ''
                    primeiro_contrato_razao_mascarado = primeiro_contrato_razao[:3] + "***" + primeiro_contrato_razao[-2:] if len(primeiro_contrato_razao) > 5 else "***" if primeiro_contrato_razao else "vazio"
                    
                    logger.warning(
                        "[SGP] consultar_cliente_sgp | CPF=%s | nome_usado=%s | nome_resposta_sgp=%s | primeiro_contrato_razaoSocial=%s | contrato_id=%s",
                        cpf_cnpj[:3] + "***" + cpf_cnpj[-2:] if len(cpf_cnpj) >= 5 else "***",
                        nome_mascarado,
                        (sgp_res.get('razaoSocial') or sgp_res.get('nome') or sgp_res.get('nomeCliente') or '')[:3] + "***" if (sgp_res.get('razaoSocial') or sgp_res.get('nome') or sgp_res.get('nomeCliente') or '') else 'vazio',
                        primeiro_contrato_razao_mascarado,
                        contratos[0].get('contratoId') if contratos else 'N/A',
                    )

                    state_atual = conversation_state if isinstance(conversation_state, dict) else {}
                    cpf_confirmado = re.sub(r"[^\d]", "", str(state_atual.get("cpf_cnpj") or ""))
                    contrato_confirmado = None
                    if state_atual.get("contrato_escolhido") and cpf_confirmado == re.sub(r"[^\d]", "", cpf_cnpj):
                        cid_confirmado = re.sub(r"[^\d]", "", str(state_atual.get("contrato_id") or ""))
                        contrato_confirmado = next(
                            (item for item in contratos if cid_confirmado and _contrato_id_of(item) == cid_confirmado),
                            None,
                        )
                    if contrato_confirmado:
                        if conversation_id:
                            redis_memory_service.update_ai_state_sync(
                                provedor.id, conversation_id, {'contratos': contratos}, channel, phone
                            )
                        state_atual['contratos'] = contratos
                        logger.warning(
                            "[SGP] buscar_cliente | conv=%s | CPF ja confirmado, mantendo contrato=%s",
                            conversation_id, _contrato_id_of(contrato_confirmado),
                        )
                        return {
                            "success": True,
                            "cliente_encontrado": True,
                            "nome": nome,
                            "dados_confirmados": True,
                            "contrato_escolhido": True,
                            "precisa_confirmar_dados": False,
                            "contrato_id": _contrato_id_of(contrato_confirmado),
                            "contrato_status_display": contrato_confirmado.get('contratoStatusDisplay'),
                            "quantidade_contratos": len(contratos),
                            "contratos": [_resumo_contrato(item) for item in contratos],
                            "nota": (
                                "Este CPF e este contrato JA foram confirmados pelo cliente nesta conversa. "
                                "NAO mostre os dados para confirmar de novo. "
                                "Siga com o pedido do cliente usando contrato_id. "
                                "So troque de contrato se o cliente pedir outro."
                            ),
                        }

                    msg = self._formatar_contratos_padrao(contratos, nome)
                    multiplos = len(contratos) > 1
                    c = contratos[0]
                    # Sempre confirma dados primeiro; com 2+ so depois pergunta qual contrato.
                    step = "AGUARDANDO_CONFIRMACAO_DADOS"
                    is_suspenso = (
                        False
                        if multiplos
                        else c.get('contratoStatusDisplay', '').strip().lower() in ['suspenso', 'suspensa']
                    )

                    login_salvo = None if multiplos else _extract_pppoe_login(c)
                    updates = {
                        'cpf_cnpj': cpf_cnpj,
                        'nome_cliente': nome,
                        'contrato_id': None if multiplos else c.get('contratoId'),
                        'servico_plano': None if multiplos else (c.get('servico_plano') or c.get('planointernet')),
                        'contrato_status_display': None if multiplos else c.get('contratoStatusDisplay'),
                        'motivo_status': None if multiplos else c.get('motivo_status'),
                        'is_suspenso': is_suspenso,
                        'cliente_consultado': True,
                        'contrato_escolhido': False,
                        'dados_confirmados': False,
                        'precisa_escolher_contrato': False,
                        'precisa_confirmar_dados': True,
                        'confirmacao_pedida': False,
                        'step': step,
                        'contratos': contratos,
                    }
                    if login_salvo:
                        updates['pppoe_login'] = login_salvo
                        updates['servico_login'] = login_salvo
                    
                    if conversation_id:
                        redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, updates, channel, phone)
                    if isinstance(conversation_state, dict):
                        conversation_state.update(updates)

                    contact = (contexto or {}).get('contact')
                    if not contact and conv:
                        contact = getattr(conv, 'contact', None)
                    if contact and nome and nome != 'Cliente':
                        from conversations.contact_name_utils import update_contact_from_sgp_by_id
                        update_contact_from_sgp_by_id(
                            contact.id,
                            nome,
                            cpf_cnpj,
                            conversation_id=conversation_id,
                            provedor_id=provedor.id,
                        )
                    
                    contratos_resumo = [_resumo_contrato(item) for item in contratos]
                    if multiplos:
                        res = {
                            "success": True,
                            "cliente_encontrado": True,
                            "nome": nome,
                            "quantidade_contratos": len(contratos),
                            "tem_apenas_um_contrato": False,
                            "precisa_escolher_contrato": False,
                            "precisa_confirmar_dados": True,
                            "dados_confirmados": False,
                            "contrato_escolhido": False,
                            "contratos": contratos_resumo,
                            "mensagem_cliente_sugerida": msg,
                            "nota": (
                                "Use APENAS mensagem_cliente_sugerida deste retorno "
                                "(dados reais). Nunca invente ID/endereco. "
                                "Redija com naturalidade. "
                                "ETAPA 1: peca UMA vez se os dados estao corretos. Ainda NAO pergunte qual contrato. "
                                "NAO chame gerar_fatura / verificar_acesso / abrir_chamado ainda. "
                                "Quando o cliente confirmar, chame selecionar_contrato com escolha='sim'."
                            ),
                        }
                    else:
                        res = {
                            "success": True,
                            "cliente_encontrado": True,
                            "nome": nome,
                            "is_suspenso": is_suspenso,
                            "contrato_suspenso": is_suspenso,
                            "contrato_status_display": c.get('contratoStatusDisplay'),
                            "motivo_status": c.get('motivo_status'),
                            "quantidade_contratos": 1,
                            "tem_apenas_um_contrato": True,
                            "precisa_escolher_contrato": False,
                            "precisa_confirmar_dados": True,
                            "dados_confirmados": False,
                            "contrato_escolhido": False,
                            "contrato_id": c.get('contratoId'),
                            "pppoe_login": login_salvo or None,
                            "contratos": contratos_resumo,
                            "mensagem_cliente_sugerida": msg,
                            "nota": (
                                "Use APENAS mensagem_cliente_sugerida deste retorno "
                                "(dados reais). Nunca invente ID/endereco. "
                                "Redija com naturalidade; peca confirmacao UMA vez. "
                                "NAO chame gerar_fatura / verificar_acesso / abrir_chamado / liberar_confianca ainda. "
                                "Quando o cliente confirmar, chame selecionar_contrato com escolha='sim' "
                                "e JA execute o que ele pediu. "
                                "NUNCA peca confirmacao de cadastro de novo apos contrato_escolhido=true. "
                                "Se for troca de Wi-Fi: use o pppoe_login retornado — nao peca o login PPPoE."
                            ),
                        }

            elif function_name == "selecionar_contrato":
                contratos_pendentes = _lista_contratos_estado(conversation_state)
                escolha = (
                    function_args.get("escolha")
                    or function_args.get("contrato_id")
                    or function_args.get("contrato")
                    or ""
                )
                selecionado = _match_contrato_escolha(escolha, contratos_pendentes)
                # "sim" so confirma dados; com 1 contrato ja seleciona; com 2+ avanca para escolha.
                confirmando = _escolha_e_confirmacao(escolha) and not selecionado

                if confirmando and _precisa_confirmar_dados(conversation_state) and len(contratos_pendentes) >= 2:
                    _persistir_dados_confirmados(
                        provedor,
                        conversation_id,
                        channel,
                        phone,
                        conversation_state,
                        multiplos=True,
                    )
                    nome = conversation_state.get("nome_cliente") or ""
                    logger.warning(
                        "[SGP] dados confirmados (multiplos) | conv=%s | aguardando escolha de contrato",
                        conversation_id,
                    )
                    return {
                        "success": True,
                        "dados_confirmados": True,
                        "precisa_confirmar_dados": False,
                        "precisa_escolher_contrato": True,
                        "contrato_escolhido": False,
                        "quantidade_contratos": len(contratos_pendentes),
                        "nome": nome or None,
                        "contratos": [_resumo_contrato(c) for c in contratos_pendentes],
                        "nota": (
                            "Os dados do cadastro JA foram confirmados (Redis). "
                            "NAO peca confirmar nome/endereco de novo. "
                            "Pergunte com naturalidade para qual contrato e este atendimento "
                            "(numero da lista ou id). Uma pergunta so. "
                            "Quando o cliente escolher, chame selecionar_contrato."
                        ),
                    }

                if not selecionado and confirmando and len(contratos_pendentes) == 1:
                    selecionado = contratos_pendentes[0]
                if not selecionado:
                    if not contratos_pendentes:
                        return {
                            "success": False,
                            "erro": "Nao ha lista de contratos para escolher. Chame buscar_cliente primeiro.",
                        }
                    if _precisa_confirmar_dados(conversation_state):
                        return {
                            **_resposta_precisa_confirmar_dados(
                                contratos_pendentes,
                                conversation_state.get("nome_cliente") or "",
                            ),
                            "erro": "O cliente ainda nao confirmou os dados. Peca confirmacao e chame selecionar_contrato de novo.",
                        }
                    return {
                        **_resposta_precisa_escolher_contrato(
                            contratos_pendentes,
                            conversation_state.get("nome_cliente") or "",
                        ),
                        "erro": "Escolha invalida. Peça ao cliente o numero da lista ou o id do contrato.",
                    }

                persistido = _persistir_contrato_escolhido(
                    provedor, conversation_id, channel, phone, selecionado, conversation_state
                )
                cid = persistido.get("contrato_id")
                nome = conversation_state.get("nome_cliente") or ""
                endereco = _endereco_contrato(selecionado)
                pedido = conversation_state.get("pedido_cliente") or None
                logger.warning(
                    "[SGP] selecionar_contrato | conv=%s | contrato=%s | pedido_cliente=%s",
                    conversation_id, cid, (pedido or "")[:80],
                )

                res = {
                    "success": True,
                    "contrato_escolhido": True,
                    "nome": nome or None,
                    "contrato_id": cid,
                    "status": persistido.get("contrato_status_display"),
                    "plano": persistido.get("servico_plano"),
                    "endereco": endereco or None,
                    "is_suspenso": persistido.get("is_suspenso"),
                    "pppoe_login": persistido.get("pppoe_login"),
                    "pedido_cliente": pedido,
                    "nota": (
                        "Contrato confirmado e salvo no Redis; nao peca confirmacao de novo. "
                        "Agora, pelo que voce entendeu da conversa (pedido_cliente e historico), "
                        "ja chame neste mesmo turno a ferramenta que atende o que o cliente pediu "
                        "e responda com suas proprias palavras, sem frases prontas. "
                        "Nao execute nada que o cliente nao pediu (ex.: nunca envie fatura sem ele pedir). "
                        "Se ainda nao estiver claro o que ele quer, pergunte."
                    ),
                }

            elif function_name == "verificar_manutencao":
                cpf_cnpj = function_args.get('cpf_cnpj', '')
                if not cpf_cnpj:
                    cpf_cnpj = conversation_state.get('cpf_cnpj')
                if not cpf_cnpj:
                    return {"success": False, "erro": "CPF/CNPJ necessário para verificar manutenção."}
                
                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso. Não é necessário verificar manutenção."}
                
                cpf_limpo = cpf_cnpj.replace('.', '').replace('-', '').replace('/', '')
                sgp_res = sgp.listar_manutencoes(cpf_limpo)
                
                # Verificar se há manutenções ativas/programadas
                manutencoes = []
                if isinstance(sgp_res, list):
                    manutencoes = sgp_res
                elif isinstance(sgp_res, dict):
                    if sgp_res.get('status') == 1 and sgp_res.get('manutencoes'):
                        manutencoes = sgp_res.get('manutencoes', [])
                    elif sgp_res.get('manutencoes'):
                        manutencoes = sgp_res.get('manutencoes', [])
                
                if manutencoes:
                    # Filtrar manutenções futuras ou em andamento
                    from django.utils import timezone
                    agora = timezone.now()
                    manutencoes_ativas = []
                    for manut in manutencoes:
                        # Verificar se a manutenção está programada para o futuro ou em andamento
                        data_manut = manut.get('data_manutencao') or manut.get('data') or manut.get('data_inicio')
                        if data_manut:
                            try:
                                from datetime import datetime
                                if isinstance(data_manut, str):
                                    # Tentar parsear a data
                                    dt_manut = datetime.fromisoformat(data_manut.replace('Z', '+00:00'))
                                else:
                                    dt_manut = data_manut
                                # Se a manutenção é hoje ou futura, considerar ativa
                                if dt_manut.date() >= agora.date():
                                    manutencoes_ativas.append(manut)
                            except:
                                # Se não conseguir parsear, considerar ativa
                                manutencoes_ativas.append(manut)
                        else:
                            # Se não tem data, considerar ativa
                            manutencoes_ativas.append(manut)
                    
                    if manutencoes_ativas:
                        # Formatar informações da manutenção
                        info_manut = []
                        for manut in manutencoes_ativas[:3]:  # Máximo 3 manutenções
                            data = manut.get('data_manutencao') or manut.get('data') or manut.get('data_inicio') or 'Data não informada'
                            descricao = manut.get('descricao') or manut.get('motivo') or manut.get('observacao') or 'Manutenção programada'
                            info_manut.append(f"- {descricao} (Data: {data})")
                        
                        res = {
                            "success": True,
                            "tem_manutencao": True,
                            "manutencoes": manutencoes_ativas[:5],
                            "nota": (
                                "Ha manutencao CONFIRMADA pelo ERP. "
                                "Informe o cliente com suas palavras usando esses dados. "
                                "Nao abra chamado tecnico por causa dessa manutencao."
                            ),
                        }
                    else:
                        res = {
                            "success": True,
                            "tem_manutencao": False,
                            "nota": (
                                "ERP nao retornou manutencao. "
                                "NUNCA mencione manutencao ao cliente. "
                                "Continue diagnostico do modem (ligado, LED vermelho, reinicio)."
                            ),
                        }
                else:
                    res = {
                        "success": True,
                        "tem_manutencao": False,
                        "nota": (
                            "ERP nao retornou manutencao. "
                            "NUNCA mencione manutencao ao cliente. "
                            "Continue diagnostico do modem (ligado, LED vermelho, reinicio)."
                        ),
                    }

            elif function_name == "verificar_acesso":
                resolved = _resolver_contrato_id(function_args.get('contrato'), conversation_state)
                if not resolved.get("ok"):
                    return {"success": False, "erro": resolved.get("erro")}
                cid = resolved["contrato_id"]
                if resolved.get("corrigido_de_cpf"):
                    logger.info("[SGP] verificar_acesso | contrato corrigido de CPF → %s", cid)

                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso por falta de pagamento.", "contrato_suspenso": True}

                sgp_res = sgp.verifica_acesso(cid)
                
                # Verificar se é manutenção em andamento (status == 9)
                if isinstance(sgp_res, dict) and sgp_res.get('status') == 9:
                    # Há manutenção em andamento
                    msg_manutencao_raw = sgp_res.get('msg', '')
                    protocolo = sgp_res.get('protocolo', '')
                    tempo = sgp_res.get('tempo', '')

                    msg_manutencao_limpa = msg_manutencao_raw.replace('\r\n', ' ').replace('\n', ' ').strip()

                    res = {
                        "success": True,
                        "status_conexao": "Manutencao",
                        "tem_manutencao": True,
                        "protocolo": protocolo,
                        "tempo_estimado": tempo,
                        "detalhe": msg_manutencao_limpa,
                        "nota": (
                            "Manutencao CONFIRMADA pelo ERP (status=9). "
                            "Informe o cliente com suas palavras (protocolo/tempo se houver). "
                            "Nao abra chamado tecnico. "
                            "Quando o cliente agradecer ou disser que vai aguardar, "
                            "chame encerrar_atendimento."
                        ),
                    }
                elif isinstance(sgp_res, dict) and sgp_res.get('status') == 1:
                    # Online
                    res = {
                        "success": True,
                        "status_conexao": "Online",
                        "tem_manutencao": False,
                        "nota": (
                            "Conexao Online. Fale de internet/conexao, nao de 'status do contrato'. "
                            "Nao mencione manutencao."
                        ),
                    }
                elif isinstance(sgp_res, list) and len(sgp_res) > 0:
                    # Online (formato de lista)
                    res = {
                        "success": True,
                        "status_conexao": "Online",
                        "tem_manutencao": False,
                        "nota": (
                            "Conexao Online. Fale de internet/conexao, nao de 'status do contrato'. "
                            "Nao mencione manutencao."
                        ),
                    }
                else:
                    # Offline — sem manutenção confirmada neste retorno
                    nome_cli = (
                        conversation_state.get('nome_cliente')
                        or conversation_state.get('nome')
                        or ''
                    )
                    res = {
                        "success": True,
                        "status_conexao": "Offline",
                        "tem_manutencao": False,
                        "nome_cliente": nome_cli or None,
                        "nota": (
                            "Offline no sistema. Nao invente manutencao. "
                            "1a mensagem: informe que o modem/conexao esta offline no sistema"
                            + (f" ({nome_cli})" if nome_cli else "")
                            + " e diga que vai precisar coletar algumas informacoes. "
                            "NAO pergunte nada nessa 1a mensagem. "
                            "Depois, UMA pergunta por mensagem, nesta ordem: "
                            "(A) consegue verificar se o equipamento esta ligado na tomada? "
                            "(B) se SIM ligado: ve algum LED vermelho (LOS/fibra) aceso? "
                            "Se LED vermelho/LOS: explique que pode ser fibra ou o equipamento. "
                            "NAO abra chamado nem transfira so por isso. "
                            "Chame verificar_manutencao se ainda nao chamou. Continue o diagnostico. "
                            "(C) reinicio/Wi-Fi SO se ligado E SEM LED vermelho. "
                            "Nunca junte duas perguntas na mesma mensagem. "
                            "abrir_chamado so apos diagnostico, com contrato_id real do buscar_cliente."
                        ),
                    }

            elif function_name == "gerar_fatura":
                # Priorizar input sobre contexto para evitar dados stale
                cpf = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj')
                # Padrao PIX; KB do provedor ou parametro da tool podem pedir boleto/ambos
                tipo_pagamento = _resolve_tipo_pagamento_fatura(provedor, function_args)
                
                # Se mudou o CPF, ignoramos o contrato antigo do contexto
                input_cpf = re.sub(r"[^\d]", "", str(function_args.get('cpf_cnpj') or ""))
                if input_cpf and input_cpf != re.sub(r"[^\d]", "", str(conversation_state.get('cpf_cnpj') or "")):
                    contrato_id = function_args.get('contrato_id')
                else:
                    resolved = _resolver_contrato_id(
                        function_args.get('contrato_id') or function_args.get('contrato'),
                        conversation_state,
                    )
                    if not resolved.get("ok"):
                        return {"success": False, "erro": resolved.get("erro")}
                    contrato_id = resolved["contrato_id"]

                logger.info(f"[AIACTIONS] gerar_fatura_completa | CPF={cpf} | Contrato={contrato_id} | Tipo={tipo_pagamento}")

                if not self._is_valid_cpf_cnpj(cpf): 
                    logger.warn(f"[AIACTIONS] CPF inválido: {cpf}")
                    return {"success": False, "erro": "CPF/CNPJ inválido."}

                if not contrato_id:
                    return {
                        "success": False,
                        "erro": "Contrato obrigatorio para consultar fatura. Chame buscar_cliente e, se houver varios, selecionar_contrato.",
                    }
                
                from core.fatura_service import fatura_service as fs
                dados = fs.buscar_fatura_sgp(provedor, cpf, contrato_id)

                outros_contratos = len(_lista_contratos_estado(conversation_state)) > 1
                nota_sem_fatura = (
                    f"Neste contrato ({contrato_id}) nao ha fatura vencida nem em aberto. "
                    "Nao generalize para todos os contratos do cliente. "
                    + (
                        "Pergunte se deseja consultar outro contrato da lista."
                        if outros_contratos
                        else "Informe ao cliente com suas palavras."
                    )
                )
                
                # Verificar se retornou mensagem positiva (todas as faturas pagas)
                if dados and dados.get('mensagem_positiva'):
                    return {
                        "success": True,
                        "faturas_em_dia": True,
                        "contrato_id": contrato_id,
                        "nota": nota_sem_fatura,
                    }
                
                if not dados or dados.get('status') != 1: 
                    if dados and dados.get('solicitar_transferencia'):
                        return dados
                    return {
                        "success": False,
                        "erro": f"Nenhuma fatura em aberto neste contrato ({contrato_id}).",
                        "contrato_id": contrato_id,
                        "nota": nota_sem_fatura,
                    }
                
                if not phone or phone == 'unknown': return {"success": False, "erro": "Telefone não identificado."}

                envio = fs.enviar_fatura(provedor, phone, dados, conv, tipo_pagamento)
                
                if (isinstance(envio, bool) and envio) or (isinstance(envio, dict) and envio.get('success')):
                    if conversation_id:
                        # Se foi enviado com sucesso, limpar o fluxo de suspensão/fatura
                        redis_memory_service.update_ai_state_sync(
                            provedor.id,
                            conversation_id,
                            {
                                "flow": "NONE",
                                "step": "INICIAL",
                        "fatura_enviada": True,
                                "fatura_enviada_contrato_id": str(contrato_id),
                            },
                            channel,
                            phone,
                        )
                    forma = {"ambos": "boleto + PIX", "boleto": "boleto"}.get(tipo_pagamento, "PIX")
                    primeiro_nome = (str(conversation_state.get("nome_cliente") or "").split() or [None])[0]
                    nota_envio = (
                        f"A fatura ({forma}) JA esta na conversa, na mensagem logo acima da sua resposta. "
                        "Escreva uma resposta curta, com suas proprias palavras e variando o jeito de falar, que: "
                        "chame o cliente pelo primeiro nome (se houver), diga que a fatura esta na mensagem acima, "
                        "informe o valor e o vencimento, e se coloque a disposicao. "
                        "Nao repita o conteudo da fatura, nao diga que foi 'gerada com sucesso' "
                        "e nao diga que ele ainda vai receber (ja foi enviada)."
                    )
                    res = {
                        "success": True,
                        "fatura_enviada": True,
                        "tipo_pagamento": tipo_pagamento,
                        "contrato_id": contrato_id,
                        "nome_cliente": primeiro_nome.title() if primeiro_nome else None,
                        "valor": dados.get("valor"),
                        "vencimento": dados.get("vencimento"),
                        "nota": nota_envio,
                    }
                else:
                    res = {"success": False, "erro": "Falha no envio."}

            elif function_name == "consultar_chamados":
                if not conversation_state.get("cliente_consultado") and not conversation_state.get("contrato_id"):
                    return {
                        "success": False,
                        "erro": (
                            "Cliente ainda nao foi localizado. "
                            "Peca CPF/CNPJ, chame buscar_cliente e confirme o contrato antes."
                        ),
                    }
                resolved = _resolver_contrato_id(function_args.get('contrato'), conversation_state)
                if not resolved.get("ok"):
                    return {"success": False, "erro": resolved.get("erro")}
                cid = resolved["contrato_id"]
                consulta = _consultar_chamados_em_andamento(sgp, conversation_state, cid)
                logger.info(
                    "[SGP] consultar_chamados | conv=%s | contrato=%s | ok=%s | em_andamento=%s",
                    conversation_id, cid, consulta.get("ok"), len(consulta.get("em_andamento") or []),
                )
                if consulta.get("ok"):
                    _salvar_chamados_no_estado(
                        provedor, conversation_id, channel, phone, conversation_state,
                        {
                            "chamados_consultados_contrato": str(cid),
                            "chamados_em_andamento": consulta.get("em_andamento") or [],
                        },
                    )
                res = _resposta_consulta_chamados(consulta, cid)

            elif function_name == "abrir_chamado":
                cont = function_args.get('conteudo')
                if not cont:
                    return {"success": False, "erro": "Conteudo do chamado obrigatorio."}

                if not conversation_state.get("cliente_consultado") and not conversation_state.get("contrato_id"):
                    return {
                        "success": False,
                        "erro": (
                            "Cliente ainda nao foi localizado. "
                            "Peca CPF/CNPJ, chame buscar_cliente e so entao abrir_chamado "
                            "com o contrato_id retornado. Nao invente numero de contrato."
                        ),
                    }

                resolved = _resolver_contrato_id(function_args.get('contrato'), conversation_state)
                if not resolved.get("ok"):
                    return {"success": False, "erro": resolved.get("erro")}
                cid = resolved["contrato_id"]
                if resolved.get("corrigido_de_cpf"):
                    logger.info("[SGP] abrir_chamado | contrato corrigido de CPF → %s", cid)

                contratos_ok = _lista_contratos_estado(conversation_state)
                if contratos_ok:
                    ids_ok = {_contrato_id_of(c) for c in contratos_ok}
                    if cid not in ids_ok:
                        return {
                            "success": False,
                            "erro": (
                                "Contrato invalido para este cliente. "
                                "Use um contrato_id da lista do buscar_cliente ou chame selecionar_contrato."
                            ),
                        }

                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso.", "contrato_suspenso": True}

                consulta = _consultar_chamados_em_andamento(sgp, conversation_state, cid)
                if consulta.get("ok") and consulta.get("em_andamento"):
                    logger.warning(
                        "[SGP] abrir_chamado recusado: contrato=%s ja tem %s chamado(s) aberto/pendente | conv=%s",
                        cid, len(consulta["em_andamento"]), conversation_id,
                    )
                    return {
                        "success": False,
                        "chamado_ja_aberto": True,
                        "contrato_id": cid,
                        "chamados_abertos": consulta["em_andamento"],
                        "nota": (
                            "NAO foi aberto novo chamado: o cliente ja tem chamado Aberto/Pendente neste contrato. "
                            "Informe com suas palavras o protocolo, a situacao e o agendamento (se houver). "
                            "NAO diga que abriu chamado agora."
                        ),
                    }

                # Criar chamado no SGP com ID real do contrato
                sgp_res = sgp.criar_chamado(contrato=str(cid), conteudo=cont, ocorrenciatipo=1)

                if sgp_res.get('success'):
                    from conversations.protocol_service import (
                        apply_sgp_protocol,
                        format_protocol_update_customer_message,
                    )

                    protocolo = sgp_res.get('protocolo')
                    protocolo_anterior = None

                    if conv:
                        try:
                            proto_result = apply_sgp_protocol(
                                conv,
                                protocolo,
                                chamado_id=sgp_res.get('chamado_id'),
                            )
                            protocolo_anterior = (proto_result or {}).get('protocolo_anterior')
                        except Exception as proto_err:
                            logger.warning(
                                "[SGP] Falha ao atualizar protocolo SGP na conversa %s: %s",
                                conv.id,
                                proto_err,
                            )

                        # Avisar o cliente sobre a troca de protocolo (NioHub → SGP)
                        msg_proto_cliente = None
                        try:
                            if protocolo and (
                                not protocolo_anterior or str(protocolo_anterior) != str(protocolo)
                            ):
                                msg_proto_cliente = format_protocol_update_customer_message(
                                    protocolo_anterior, protocolo
                                )
                                from core.chatbot_engine import ChatbotEngine

                                ok_send, send_detail = ChatbotEngine.send_message_agnostic_sync(
                                    conv, msg_proto_cliente
                                )
                                if ok_send:
                                    logger.info(
                                        "[SGP] Cliente avisado da atualização de protocolo conv=%s novo=%s",
                                        conv.id,
                                        protocolo,
                                    )
                                else:
                                    logger.warning(
                                        "[SGP] Protocolo salvo no painel mas NÃO enviado ao canal conv=%s: %s",
                                        conv.id,
                                        send_detail,
                                    )
                        except Exception as send_proto_err:
                            logger.warning(
                                "[SGP] Falha ao enviar protocolo atualizado ao cliente conv=%s: %s",
                                conv.id,
                                send_proto_err,
                            )

                        db_tools = DatabaseTools(provedor=provedor)
                        # Motivo limpo: sem repetir nome do cliente (já vai no campo Cliente do resumo)
                        cont_limpo = (cont or "").strip()
                        try:
                            nome_cli = (
                                conversation_state.get("nome_cliente")
                                or getattr(getattr(conv, "contact", None), "name", None)
                                or ""
                            )
                            if nome_cli and len(str(nome_cli)) > 3:
                                import re as _re
                                cont_limpo = _re.sub(
                                    _re.escape(f"Cliente {nome_cli}"),
                                    "",
                                    cont_limpo,
                                    flags=_re.IGNORECASE,
                                )
                                cont_limpo = _re.sub(
                                    _re.escape(str(nome_cli)),
                                    "",
                                    cont_limpo,
                                    flags=_re.IGNORECASE,
                                )
                                cont_limpo = _re.sub(r"\s{2,}", " ", cont_limpo).strip(" :,-")
                        except Exception:
                            pass
                        motivo_tx = f"Chamado {protocolo}: {cont_limpo[:400]}".strip()
                        # Incluir dados do estado no additional_attributes antes do resumo
                        try:
                            attrs = conv.additional_attributes or {}
                            if conversation_state.get("contrato_id"):
                                attrs["contrato_id"] = conversation_state.get("contrato_id")
                            if conversation_state.get("cpf_cnpj"):
                                attrs["cpf_cnpj"] = conversation_state.get("cpf_cnpj")
                            conv.additional_attributes = attrs
                            conv.save(update_fields=["additional_attributes"])
                        except Exception:
                            pass
                        transfer_res = db_tools.executar_transferencia_conversa(
                            conv.id, "ATENDIMENTO", motivo_tx
                        )

                        logger.info(
                            "[SGP] Chamado %s criado e conversa %s transferida: %s",
                            protocolo,
                            conv.id,
                            transfer_res.get('success'),
                        )

                    _salvar_chamados_no_estado(
                        provedor, conversation_id, channel, phone, conversation_state,
                        {
                            "chamado_aberto_protocolo": str(protocolo or ""),
                            "chamados_consultados_contrato": str(cid),
                            "chamados_em_andamento": [
                                {"protocolo": protocolo, "situacao": "Aberta", "tipo": None,
                                 "data_abertura": None, "data_agendamento": None}
                            ],
                        },
                    )
                    res = {
                        "success": True,
                        "protocolo": protocolo,
                        "protocolo_anterior": protocolo_anterior,
                        "contrato_id": cid,
                        "transferido_para": "ATENDIMENTO",
                        "protocolo_enviado_ao_cliente": True,
                        "nota": (
                            "Chamado aberto e transferido. "
                            f"O novo protocolo {protocolo} ja foi enviado ao cliente. "
                            "Na resposta, confirme o protocolo e a transferencia com suas palavras "
                            "(nao precisa repetir o texto longo da atualizacao)."
                        ),
                    }
                else:
                    raw = sgp_res.get('raw') or {}
                    erro_msg = (
                        sgp_res.get('error')
                        or (raw.get('msg') if isinstance(raw, dict) else None)
                        or "Falha ao criar chamado no ERP"
                    )
                    logger.warning(
                        "[SGP] Falha ao criar chamado contrato=%s: %s | raw: %s",
                        cid,
                        erro_msg,
                        raw,
                    )
                    res = {
                        "success": False,
                        "erro": erro_msg,
                        "contrato_id_usado": cid,
                        "nota": (
                            "Falha no ERP. Se o erro for contrato nao localizado, "
                            "chame buscar_cliente e use o contrato_id correto."
                        ),
                    }
            
            elif function_name == "consulta_viabilidade":
                gateway_cfg = (
                    sgp_config.get("sgp_viabilidade_gateway")
                    or integracao.get("sgp_viabilidade_gateway")
                    or ""
                )
                raio_cfg = (
                    sgp_config.get("sgp_viabilidade_raio")
                    or integracao.get("sgp_viabilidade_raio")
                    or ""
                )
                try:
                    gateway_id = int(str(gateway_cfg).strip()) if str(gateway_cfg).strip() else None
                except ValueError:
                    gateway_id = None
                try:
                    raio_m = int(str(raio_cfg).strip()) if str(raio_cfg).strip() else None
                except ValueError:
                    raio_m = None

                nota_indisponivel = (
                            "INSTRUCAO CRITICA - NAO REPITA NADA DISTO AO CLIENTE: esta funcionalidade "
                            "nao esta disponivel agora por motivo interno. O cliente NUNCA deve saber "
                            "disso. PROIBIDO mencionar ao cliente, mesmo parafraseando: 'nao configurada', "
                            "'sistema', 'ERP', 'ferramenta', 'nao esta ativo', 'nao disponivel', "
                            "'sem cobertura', 'sem viabilidade' ou qualquer variacao dessas ideias. "
                            "NAO chame esta tool de novo nesta conversa. Aja como se esta tool nem "
                            "existisse: continue o atendimento normalmente, colete endereco completo "
                            "(rua, numero, bairro, cidade, CEP) e um ponto de referencia, responda "
                            "duvidas sobre planos normalmente e, se o cliente quiser contratar, "
                            "transfira para a equipe comercial verificar a viabilidade manualmente "
                            "(sem citar o motivo). Sua proxima resposta ao cliente deve soar 100% "
                            "natural, como se nada de especial tivesse acontecido."
                )
                nota_pedir_opcoes = (
                    "Peca ao cliente UMA destas opcoes na mesma mensagem: "
                    "(1) enviar a localizacao atual pelo WhatsApp (pin), OU "
                    "(2) escrever o nome da rua/avenida e/ou o CEP "
                    "(pelo menos um dos dois e obrigatorio na busca por escrito). "
                    "Numero, bairro e cidade sao opcionais. Depois chame a tool de novo."
                )

                logradouro = (function_args.get("logradouro") or "").strip()
                bairro = (function_args.get("bairro") or "").strip()
                cidade = (function_args.get("cidade") or "").strip()
                cep = re.sub(r"\D", "", str(function_args.get("cep") or ""))
                numero_inicial = str(function_args.get("numero_inicial") or "").strip()
                numero_final = str(function_args.get("numero_final") or "").strip()

                numero_unico = str(function_args.get("numero") or "").strip()
                if numero_unico and not numero_inicial:
                    numero_inicial = numero_unico
                if numero_unico and not numero_final:
                    numero_final = numero_unico
                if numero_inicial and not numero_final:
                    numero_final = numero_inicial

                coords = _parse_coordenadas(function_args)
                # Fallback: coordenadas salvas no estado (ex.: pin de localização do WhatsApp)
                if not coords:
                    state_lat = conversation_state.get("latitude")
                    state_lng = conversation_state.get("longitude")
                    if state_lat is not None and state_lng is not None:
                        coords = (
                            str(state_lat).strip().replace(",", "."),
                            str(state_lng).strip().replace(",", "."),
                        )
                    elif conversation_state.get("coordenada"):
                        coords = _parse_coordenadas(
                            {"coordenada": conversation_state.get("coordenada")}
                        )

                # SGP POST /api/ura/viabilidade/ exige logradouro OU CEP.
                tem_logradouro_ou_cep = bool(logradouro or cep)
                pode_consultar_coords = bool(coords and gateway_id and raio_m)

                if not tem_logradouro_ou_cep and not coords:
                    return {
                        "success": False,
                        "erro": "Informe nome da rua/avenida e/ou CEP, ou a localizacao pelo WhatsApp.",
                        "nota": nota_pedir_opcoes,
                    }

                if not tem_logradouro_ou_cep and coords and not pode_consultar_coords:
                    logger.info(
                        "[SGP] consulta_viabilidade coordenadas bloqueada | provedor=%s | motivo=gateway/raio nao configurados",
                        provedor.id,
                    )
                    return {
                        "success": False,
                        "viabilidade_indisponivel": True,
                        "erro": "indisponivel_uso_interno",
                        "nota": nota_indisponivel,
                    }

                consulta_endereco = {"consultado": False, "viavel": False}
                consulta_coordenadas = {"consultado": False, "viavel": False}

                if tem_logradouro_ou_cep:
                    try:
                        sgp_end = sgp.consultar_viabilidade(
                            logradouro=logradouro or None,
                            numero_inicial=numero_inicial or None,
                            numero_final=numero_final or None,
                            bairro=bairro or None,
                            cep=cep or None,
                            cidade=cidade or None,
                        )
                        consulta_endereco = _avaliar_viabilidade_endereco(sgp_end)
                    except Exception as e:
                        logger.warning("[SGP] consulta_viabilidade endereco falhou: %s", e)
                        consulta_endereco = {
                            "consultado": True,
                            "sucesso": False,
                            "viavel": False,
                            "conclusivo": False,
                            "erro": str(e),
                            "resultados": [],
                        }

                if pode_consultar_coords:
                    try:
                        lat, lng = coords
                        sgp_coord = sgp.consultar_viabilidade_instalacao(
                            gateway=gateway_id,
                            raio=raio_m,
                            latitude=lat,
                            longitude=lng,
                        )
                        consulta_coordenadas = _avaliar_viabilidade_coordenadas(sgp_coord)
                        consulta_coordenadas["gateway"] = gateway_id
                        consulta_coordenadas["raio_metros"] = raio_m
                        consulta_coordenadas["coordenada"] = f"{lat},{lng}"
                    except Exception as e:
                        logger.warning("[SGP] consulta_viabilidade coordenadas falhou: %s", e)
                        consulta_coordenadas = {
                            "consultado": True,
                            "sucesso": False,
                            "viavel": False,
                            "erro": str(e),
                            "caixas": [],
                        }
                elif coords:
                    consulta_coordenadas = {
                        "consultado": False,
                        "viavel": False,
                        "faltam_coordenadas": False,
                        "pulado": True,
                        "motivo": "gateway/raio nao configurados; consulta por endereco segue.",
                        }
                else:
                    consulta_coordenadas = {
                        "consultado": False,
                        "viavel": False,
                        "faltam_coordenadas": True,
                    }

                tem_viabilidade = bool(
                    consulta_endereco.get("viavel") or consulta_coordenadas.get("viavel")
                )
                endereco_conclusivo = bool(
                    consulta_endereco.get("consultado")
                    and consulta_endereco.get("sucesso")
                    and consulta_endereco.get("conclusivo")
                )
                coords_conclusivo = bool(
                    consulta_coordenadas.get("consultado")
                    and consulta_coordenadas.get("sucesso") is not False
                    and not consulta_coordenadas.get("erro")
                )

                inconclusivo = not tem_viabilidade and not endereco_conclusivo and not coords_conclusivo

                if tem_viabilidade:
                    nota = (
                        "Ha VIABILIDADE (endereco e/ou coordenadas). "
                        "Confirme a cobertura ao cliente com suas palavras e continue o atendimento "
                        "(planos, duvidas, transferir comercial se quiser contratar)."
                    )
                elif endereco_conclusivo or coords_conclusivo:
                    nota = (
                        "NAO ha viabilidade nos endpoints consultados. "
                        "Informe ao cliente de forma empatica que nao ha cobertura no endereco/ponto "
                        "informado e ofereca transferir para a equipe comercial para verificar outras "
                        "opcoes. Pergunte se o cliente deseja a transferencia. Nunca invente cobertura."
                    )
                    inconclusivo = False
                else:
                    nota = (
                        "Consulta inconclusiva. NAO diga que nao ha viabilidade. "
                        "Peca a outra opcao que ainda faltar: localizacao atual pelo WhatsApp (pin) "
                        "OU nome da rua/avenida e/ou CEP. Depois chame a tool de novo."
                    )
                    inconclusivo = True

                res = {
                    "success": True,
                    "tem_viabilidade": tem_viabilidade,
                    "viavel": tem_viabilidade,
                    "inconclusivo_faltam_coordenadas": inconclusivo,
                    "consulta_endereco": consulta_endereco,
                    "consulta_coordenadas": consulta_coordenadas,
                    "resultados": consulta_endereco.get("resultados") or [],
                    "caixas": consulta_coordenadas.get("caixas") or [],
                    "filtros_usados": {
                        "logradouro": logradouro or None,
                        "numero_inicial": numero_inicial or None,
                        "numero_final": numero_final or None,
                        "bairro": bairro or None,
                        "cep": cep or None,
                        "cidade": cidade or None,
                        "coordenada": f"{coords[0]},{coords[1]}" if coords else None,
                        "gateway": gateway_id,
                        "raio_metros": raio_m,
                    },
                    "nota": nota,
                }

            elif function_name == "liberar_confianca":
                resolved = _resolver_contrato_id(function_args.get('contrato'), conversation_state)
                if not resolved.get("ok"):
                    return {"success": False, "erro": resolved.get("erro")}
                cid = resolved["contrato_id"]
                cpf_cnpj = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj')
                conteudo = function_args.get('conteudo')  # Conteúdo que o cliente disse (ex: "vou paga amanhã")
                
                sgp_res = sgp.liberar_por_confianca(contrato=str(cid), cpf_cnpj=cpf_cnpj, conteudo=conteudo)
                
                # Verificar se o desbloqueio foi bem-sucedido
                liberado = sgp_res.get('liberado', False)
                status = sgp_res.get('status')
                msg = sgp_res.get('msg', '')
                liberado_dias = sgp_res.get('liberado_dias')
                data_promessa = sgp_res.get('data_promessa')
                
                # Sucesso: liberado = true ou status = 1 ou mensagem contém "liberado"/"sucesso"
                if liberado is True or status == 1 or (isinstance(msg, str) and msg.lower() in ['liberado', 'sucesso']):
                    if conversation_id:
                        redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, {"flow": "NONE", "step": "INICIAL", "is_suspenso": False}, channel, phone)
                    
                    res = {
                        "success": True,
                        "liberado": True,
                        "liberado_dias": liberado_dias,
                        "data_promessa": data_promessa,
                        "nota": "Desbloqueio realizado. Informe prazo ao cliente com suas palavras, sem emoji obrigatorio.",
                    }
                else:
                    # Verificar se é caso de recurso não disponível
                    msg_lower = str(msg).lower() if msg else ''
                    if 'não disponível' in msg_lower or 'nao disponivel' in msg_lower or 'recurso não disponível' in msg_lower or 'recurso nao disponivel' in msg_lower:
                        res = {
                            "success": False,
                            "recurso_indisponivel": True,
                            "erro": msg or "Recurso de desbloqueio em confianca indisponivel para este contrato.",
                        }
                    else:
                        # Outros erros - retornar mensagem genérica
                        res = {"success": False, "erro": msg or "Erro no desbloqueio."}

            # Persistir idempotência SGP
            if res.get('success') and conversation_id and function_name not in (
                "buscar_cliente",
                "selecionar_contrato",
            ):
                redis_memory_service.update_ai_state_sync(
                    provedor.id, conversation_id,
                    {
                        "last_function": function_name,
                        "last_function_args_hash": args_hash,
                        "last_function_success": True,
                        "protocolo": res.get("protocolo")
                    },
                    channel, phone
                )

            logger.info("[SGP] %s retornou | success=%s | conversa=%s", function_name, res.get("success"), conversation_id)
            return res
        except Exception as e:
            logger.error(f"Erro crítico em execute_integration_function: {e}", exc_info=True)
            return {"success": False, "erro": str(e)}

    def get_sgp_tools(self) -> List[Dict[str, Any]]:
        """Retorna definições das ferramentas"""
        return [
            {"type": "function", "function": {"name": "buscar_cliente", "description": "Consulta cliente SGP por CPF/CNPJ (cliente JÁ EXISTENTE). Use para fatura, boleto, meu plano, suporte técnico, liberação, chamado. Retorna contratos, status (Suspenso/Ativo) e motivo da suspensão. 🚨 NÃO USE em fluxo de CONTRATAÇÃO/VENDA/plano novo. 🚨 Após o retorno, MOSTRE os dados do ERP (nome, contrato, status, endereço, plano) e peça confirmação antes de continuar. Se precisa_escolher_contrato=true ou quantidade_contratos>=2, LISTE todos os contratos e AGUARDE a escolha; depois chame selecionar_contrato. NÃO chame gerar_fatura antes da confirmação/escolha e NÃO diga que não há fatura.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "selecionar_contrato", "description": "Confirma os dados ou o contrato escolhido. Use 'sim'/confirmação quando há um contrato, ou o número da lista/id quando há vários. Na resposta, diga o nome do cliente e que ele selecionou o contrato X. Depois executa a ação original (fatura, suporte, etc.).", "parameters": {"type": "object", "properties": {"escolha": {"type": "string", "description": "Número da lista (1, 2, 3...), id do contrato, ou 'sim' para confirmar um único contrato."}}, "required": ["escolha"]}}},
            {"type": "function", "function": {"name": "gerar_fatura", "description": "Gera e envia a fatura ao cliente do CONTRATO já escolhido. Padrao: PIX. Se a base de conhecimento pedir fatura completa / boleto e PIX, use tipo_pagamento=ambos. Se o cliente tiver vários contratos, só use depois de selecionar_contrato.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}, "contrato_id": {"type": "string", "description": "Id do contrato escolhido (obrigatório se houver vários)."}, "tipo_pagamento": {"type": "string", "enum": ["pix", "boleto", "ambos"], "description": "Padrao pix. Use ambos quando a base de conhecimento pedir boleto+PIX / fatura completa."}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "verificar_manutencao", "description": "Verifica se há manutenção programada para o cliente. Use APENAS se o contrato NÃO estiver suspenso e após confirmar os dados do cliente. Se houver manutenção, informe ao cliente e NÃO abra chamado técnico.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "verificar_acesso", "description": "Verifica se o acesso à internet do contrato está online, offline ou em manutenção. Parametro contrato = contrato_id do buscar_cliente, NUNCA o CPF. Se Manutencao: informe e NÃO abra chamado. Se Offline: diagnostico com o cliente (ligado, LED/LOS). LED vermelho/LOS: NÃO abra chamado nem transfira só por isso; verifique manutenção e continue o suporte.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}}, "required": ["contrato"]}}},
            {"type": "function", "function": {"name": "abrir_chamado", "description": "Cria chamado técnico no SGP somente após diagnóstico (CPF, contrato real, verificar_manutencao, verificar_acesso). NUNCA invente contrato. NUNCA use só porque o cliente mencionou LED vermelho ou enviou foto. NUNCA use se houver manutenção ou contrato suspenso.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}, "conteudo": {"type": "string"}}, "required": ["contrato", "conteudo"]}}},
            {"type": "function", "function": {"name": "liberar_confianca", "description": "Realiza desbloqueio em confiança do contrato suspenso. Use quando o cliente quiser desbloquear o acesso sem pagar imediatamente. O CPF/CNPJ é opcional e será buscado da memória se não fornecido. O conteúdo (conteudo) deve ser o que o cliente disse sobre quando vai pagar (ex: 'vou paga amanhã'), ou deixe vazio para usar 'Liberação Via NioChat' como padrão.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}, "cpf_cnpj": {"type": "string", "description": "CPF/CNPJ do cliente (opcional, será buscado da memória se não fornecido)"}, "conteudo": {"type": "string", "description": "Conteúdo da promessa de pagamento que o cliente mencionou (ex: 'vou paga amanhã'). Se o cliente não mencionou nada específico, deixe vazio ou não inclua este parâmetro para usar 'Liberação Via NioChat' como padrão."}}, "required": ["contrato"]}}},
            {"type": "function", "function": {"name": "consulta_viabilidade", "description": "Consulta viabilidade via SGP. Opcoes: pin WhatsApp (latitude/longitude) OU endereco escrito com nome da rua/avenida e/ou CEP (pelo menos um dos dois obrigatorio). Se o cliente quiser contratar e ainda nao informou, peca as duas opcoes. Com pin, rua ou CEP, chame a tool imediatamente. tem_viabilidade=true continua; false ofereca comercial. Se viabilidade_indisponivel=true, siga a nota: NUNCA mencione configuracao/sistema ao cliente.", "parameters": {"type": "object", "properties": {"logradouro": {"type": "string"}, "numero_inicial": {"type": "string"}, "numero_final": {"type": "string"}, "bairro": {"type": "string"}, "cep": {"type": "string"}, "cidade": {"type": "string"}, "latitude": {"type": "string"}, "longitude": {"type": "string"}, "coordenada": {"type": "string"}}, "required": []}}},
        ]

    def convert_tools_to_gemini(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Converte para formato Gemini"""
        gemini_tools = []
        for t in tools:
            if t.get("type") == "function":
                f = t.get("function", {})
                params = f.get("parameters", {})
                if isinstance(params, dict):
                    params = {k: v for k, v in params.items() if k.lower() not in ['additionalproperties', 'strict']}
                gemini_tools.append({"name": f.get("name"), "description": f.get("description"), "parameters": params})
        return gemini_tools
