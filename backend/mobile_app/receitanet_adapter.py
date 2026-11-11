"""
Adaptador ReceitaNet → contrato do app (mesmo shape do proxy SGP).

App continua chamando /api/sgp/<endpoint>; quando erp_type=receitanet
este módulo atende só os 4 endpoints da Central Digital.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.http import HttpResponse
from rest_framework.response import Response

from .receitanet_client import ReceitaNetClient

logger = logging.getLogger(__name__)

# Endpoints do app mapeados para ReceitaNet
CONSULTA_ENDPOINTS = {
    "cliente/consulta",
    "ura/consultacliente",
    "central/contratos",
}
CONTRATO_PDF_ENDPOINTS = {
    "clientes/contrato",
    "central/contrato",
    "central/contrato/pdf",
}
FATURAS_ENDPOINTS = {
    "ura/titulos",
    "faturas",
}
NOTA_FISCAL_ENDPOINTS = {
    "central/notafiscal/list",
    "central/notafiscal",
    "ura/notafiscal",
}
CONSUMO_ENDPOINTS = {
    "central/extratouso",
}
PROMESSA_ENDPOINTS = {
    "ura/liberacaopromessa",
}
ACESSO_ENDPOINTS = {
    "ura/verificaacesso",
}
CHAMADO_OPEN_ENDPOINTS = {
    "ura/chamado",
    "central/chamado",
}
CHAMADO_LIST_ENDPOINTS = {
    "central/chamado/list",
}


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _as_int(value: Any) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _extract_clientes(data: Any) -> List[dict]:
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("clientes", "items", "results", "data"):
        items = data.get(key)
        if isinstance(items, list):
            return [c for c in items if isinstance(c, dict)]
        if key == "data" and isinstance(items, dict):
            nested = items.get("clientes")
            if isinstance(nested, list):
                return [c for c in nested if isinstance(c, dict)]
    return []


def _extract_faturas(data: Any) -> List[dict]:
    if isinstance(data, list):
        return [f for f in data if isinstance(f, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("faturas", "items", "results"):
        items = data.get(key)
        if isinstance(items, list):
            return [f for f in items if isinstance(f, dict)]
    return []


def _map_cliente_to_contrato(cliente: dict) -> dict:
    """
    Converte item de POST /clientes/consulta → contrato no formato do app.

    Na ReceitaNet cada item da lista já é um vínculo (idCliente + idContrato),
    mesmo com o mesmo CPF — o app deve listar todos e usar idCliente nas APIs.
    """
    id_cliente = cliente.get("idCliente") or cliente.get("id_cliente") or cliente.get("id")
    id_contrato = (
        cliente.get("idContrato")
        or cliente.get("contrato")
        or cliente.get("id_contrato")
        or id_cliente
    )
    # Central Digital opera por idCliente (não confundir com idContrato quando diferem).
    contract_key = str(id_cliente or id_contrato or "").strip()
    display_name = str(
        cliente.get("nome")
        or cliente.get("razaoSocial")
        or cliente.get("razaosocial")
        or ""
    ).strip()
    login = str(cliente.get("login") or "").strip()
    status_display = str(cliente.get("contratoStatusDisplay") or "").strip() or "Ativo"

    endereco = cliente.get("endereco") if isinstance(cliente.get("endereco"), dict) else {}
    # ReceitaNet: { endereco, complemento, bairro, cidade, uf, cep }
    logradouro = (
        endereco.get("endereco")
        or endereco.get("logradouro")
        or endereco.get("rua")
        or ""
    )
    complemento = str(endereco.get("complemento") or "").strip()
    numero = str(endereco.get("numero") or "").strip()
    bairro = str(endereco.get("bairro") or "").strip()
    cidade = str(endereco.get("cidade") or endereco.get("municipio") or "").strip()
    uf = str(endereco.get("uf") or endereco.get("estado") or "").strip()
    cep = str(endereco.get("cep") or "").strip()

    parts = [str(logradouro).strip()]
    if numero and numero not in ("0", "S/N"):
        parts[0] = f"{parts[0]}, {numero}".strip(", ")
    if complemento:
        parts.append(complemento)
    if bairro:
        parts.append(bairro)
    if cidade:
        city = f"{cidade}/{uf}" if uf else cidade
        parts.append(city)
    address = " - ".join(p for p in parts if p)

    # Subtítulo para a UI de seleção (nome fica no título).
    meta_bits = []
    if id_contrato:
        meta_bits.append(f"Contrato {id_contrato}")
    if login:
        meta_bits.append(f"Login {login}")
    subtitle = " · ".join(meta_bits)

    return {
        "contratoId": contract_key,
        "contrato": contract_key,
        "id": contract_key,
        "idCliente": id_cliente,
        "idContrato": id_contrato,
        "razaoSocial": display_name,
        "nome": display_name,
        "titulo": display_name,
        "cpfCnpj": cliente.get("cpfCnpj") or cliente.get("cpf_cnpj") or "",
        "servico_login": login,
        "pppoe_login": login,
        "login": login,
        "contratoStatus": cliente.get("contratoStatus"),
        "contratoStatusDisplay": status_display,
        "status": status_display,
        "email": cliente.get("email") or "",
        "telefones": cliente.get("telefones") or [],
        "endereco_logradouro": str(logradouro).strip(),
        "endereco_numero": numero or ("S/N" if logradouro else ""),
        "endereco_complemento": complemento,
        "endereco_bairro": bairro,
        "endereco_cidade": cidade,
        "endereco_uf": uf,
        "endereco_cep": cep,
        # Campo pronto para a home (contract['address'])
        "address": address or "Endereço não informado",
        "subtitle": subtitle,
        "_erp": "receitanet",
    }


def _pretty_plan_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        return ""
    return name.replace("_", " ").strip()


def _due_day_from_vencimento(raw: Any) -> str:
    """Extrai dia do mês: 2026-09-10 → '10';"""
    s = str(raw or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return str(int(s[8:10]))  # remove zero à esquerda: 09 → 9? Keep as 10/09
    # Já DD/MM/YYYY
    if len(s) >= 10 and s[2] == "/" and s[5] == "/":
        return str(int(s[0:2]))
    digits = re.sub(r"\D", "", s)
    if digits.isdigit() and 1 <= int(digits) <= 31:
        return str(int(digits))
    return s


def _gb_to_bytes(value: Any) -> float:
    try:
        return float(value or 0) * (1024 ** 3)
    except (TypeError, ValueError):
        return 0.0


def _map_consumo_mensal(consumo: Any) -> List[dict]:
    """
    ReceitaNet consumoMensal (GB/mês) → lista no formato do app
    (download/upload em bytes, data ISO), como central/extratouso do SGP.
    """
    if not isinstance(consumo, dict):
        return []
    labels = consumo.get("labels") or []
    downs = consumo.get("down") or []
    ups = consumo.get("up") or []
    out: List[dict] = []
    for i, label in enumerate(labels):
        label_s = str(label or "").strip()
        # "08/2026" → 2026-08-01
        data_iso = ""
        if "/" in label_s:
            parts = label_s.split("/")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                mm, yyyy = int(parts[0]), int(parts[1])
                data_iso = f"{yyyy:04d}-{mm:02d}-01"
        down = downs[i] if i < len(downs) else 0
        up = ups[i] if i < len(ups) else 0
        out.append(
            {
                "data": data_iso or label_s,
                "download": _gb_to_bytes(down),
                "upload": _gb_to_bytes(up),
                "download_gb": down,
                "upload_gb": up,
                "label": label_s,
                "_erp": "receitanet",
            }
        )
    return out


def _enrich_contrato_from_resumo(contrato: dict, resumo: dict) -> dict:
    """Preenche plano, vencimento e data cadastro a partir do /resumo."""
    if not isinstance(resumo, dict):
        return contrato

    mensalidades = resumo.get("mensalidades") or []
    if isinstance(mensalidades, list) and mensalidades:
        plano = mensalidades[0] if isinstance(mensalidades[0], dict) else {}
        plan_name = _pretty_plan_name(plano.get("descricao"))
        if plan_name:
            contrato["planointernet"] = plan_name
            contrato["servico_plano"] = plan_name
            contrato["plan_name"] = plan_name
            contrato["plano_valor"] = plano.get("valor") or plano.get("total")
            contrato["idPlano"] = plano.get("idPlano")

    faturas = resumo.get("ultimasFaturas") or []
    if isinstance(faturas, list) and faturas:
        # Preferir fatura aberta; senão a primeira
        chosen = None
        for f in faturas:
            if not isinstance(f, dict):
                continue
            st = str(f.get("status") or "").lower()
            if st in ("aberto", "aberta", "vencido", "vencida"):
                chosen = f
                break
        if chosen is None:
            chosen = faturas[0] if isinstance(faturas[0], dict) else None
        if chosen:
            venc = chosen.get("vencimento") or chosen.get("dataVencimento") or ""
            if venc:
                contrato["cobVencimento"] = _due_day_from_vencimento(venc)
                contrato["vencimento"] = venc
                contrato["dataVencimento"] = venc
                # ReceitaNet: data de cadastro = data de vencimento do boleto
                cadastro = _format_br_date(venc)
                contrato["dataCadastro"] = cadastro
                contrato["data_cadastro"] = cadastro

    # Fallback se dataCadastro vier em campos extras do resumo
    if not contrato.get("data_cadastro"):
        for src in (resumo, resumo.get("dadosCadastrais") if isinstance(resumo.get("dadosCadastrais"), dict) else {}):
            if not isinstance(src, dict):
                continue
            for key in ("dataCadastro", "data_cadastro", "dataAtivacao", "dataContrato"):
                if src.get(key):
                    raw = src.get(key)
                    cadastro = _format_br_date(raw) if "-" in str(raw) else str(raw)
                    contrato["dataCadastro"] = cadastro
                    contrato["data_cadastro"] = cadastro
                    break
            if contrato.get("data_cadastro"):
                break

    dados = resumo.get("dadosCadastrais") if isinstance(resumo.get("dadosCadastrais"), dict) else {}
    if dados:
        if dados.get("nome") and not contrato.get("nome"):
            contrato["nome"] = dados.get("nome")
            contrato["razaoSocial"] = contrato.get("razaoSocial") or dados.get("nome")
        if dados.get("email") and not contrato.get("email"):
            contrato["email"] = dados.get("email")
        # Endereço textual do resumo se o da consulta veio vazio
        if (not contrato.get("address") or contrato.get("address") == "Endereço não informado") and dados.get(
            "endereco"
        ):
            parts = [
                str(dados.get("endereco") or "").strip(),
                str(dados.get("complemento") or "").strip(),
                str(dados.get("bairro") or "").strip(),
            ]
            cidade = str(dados.get("cidade") or "").strip()
            uf = str(dados.get("uf") or "").strip()
            if cidade:
                parts.append(f"{cidade}/{uf}" if uf else cidade)
            address = " - ".join(p for p in parts if p)
            if address:
                contrato["address"] = address
        if dados.get("isBloqueado") is True:
            contrato["contratoStatusDisplay"] = contrato.get("contratoStatusDisplay") or "Suspenso"

    contrato["isFaturaVencida"] = bool(resumo.get("isFaturaVencida"))
    contrato["isPromessaLiberado"] = resumo.get("isPromessaLiberado")
    contrato["_resumo"] = True
    return contrato


def _map_status_fatura(status: Any, vencida: Any = None) -> str:
    s = str(status or "").strip().lower()
    if s in ("pago", "paga", "baixado", "baixada", "liquidado"):
        return "PAGO"
    if s in ("cancelado", "cancelada"):
        return "CANCELADO"
    # Status textual "vencido" do ERP; "aberto" + vencida=true continua ABERTO
    # (o app usa o flag esta_atrasada / vencida para atraso).
    if s in ("vencido", "vencida", "atrasado"):
        return "VENCIDO"
    return "ABERTO"


def _format_br_date(raw: Any) -> str:
    """YYYY-MM-DD → DD/MM/YYYY."""
    s = str(raw or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _nf_link_from_fatura(fatura: dict) -> str:
    """Extrai o melhor link de documento fiscal disponível na fatura ReceitaNet."""
    for key in (
        "linkNotaFiscal",
        "linkNota",
        "urlNotaFiscal",
        "urlNota",
        "linkNf",
        "link_nf",
        "linkRecibo",
        "link_recibo",
        "linkFaturaPdf",
        "link_fatura_pdf",
        "urlBoletoCopiaCola",
        "linkBoleto",
        "link_fatura",
    ):
        val = str(fatura.get(key) or "").strip()
        if val and val.lower() not in ("null", "none"):
            return val
    return ""


def _map_fatura_to_nota(fatura: dict, *, empresa: str = "", id_cliente: Any = None) -> dict:
    """Converte fatura ReceitaNet → item da tela de notas fiscais do app."""
    emissao = (
        fatura.get("emissao")
        or fatura.get("dataEmissao")
        or fatura.get("data_emissao")
        or fatura.get("pagamento")
        or fatura.get("vencimento")
        or fatura.get("dataVencimento")
        or ""
    )
    numero = (
        fatura.get("numeroNota")
        or fatura.get("numeroNf")
        or fatura.get("numeroBoleto")
        or fatura.get("idBoleto")
        or fatura.get("id")
        or ""
    )
    valor = (
        fatura.get("valorPago")
        if str(fatura.get("status") or "").lower() == "pago"
        else None
    )
    if valor in (None, "", 0):
        valor = fatura.get("valor") or fatura.get("valorFatura") or 0

    return {
        "numero": numero,
        "data_emissao": emissao,
        "valortotal": valor,
        "link": _nf_link_from_fatura(fatura),
        "empresa_razao_social": empresa or "Provedor de Internet",
        "idBoleto": fatura.get("idBoleto"),
        "status": fatura.get("status"),
        "idCliente": id_cliente,
    }


def _empresa_razao_social(client: ReceitaNetClient) -> str:
    try:
        res = client.empresa()
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        return str(
            data.get("razaoSocial")
            or data.get("nomeFantasia")
            or data.get("nome")
            or ""
        ).strip()
    except Exception as exc:
        logger.warning("ReceitaNet empresa: %s", exc)
        return ""


def _map_fatura_to_titulo(fatura: dict, id_cliente: Any = None) -> dict:
    status = _map_status_fatura(fatura.get("status"), fatura.get("vencida"))
    pix = (fatura.get("pixCopiaCola") or fatura.get("codigoPix") or fatura.get("codigopix") or "").strip()
    linha = (fatura.get("linhaDigitavel") or fatura.get("linha_digitavel") or "").strip()
    venc = fatura.get("vencimento") or fatura.get("dataVencimento") or ""
    vencida = bool(fatura.get("vencida"))
    return {
        "id": fatura.get("idBoleto") or fatura.get("numeroBoleto"),
        "idBoleto": fatura.get("idBoleto"),
        "numeroBoleto": fatura.get("numeroBoleto"),
        "dataVencimento": venc,
        "vencimento": venc,
        "valor": fatura.get("valor") or fatura.get("valorFatura"),
        "status": status,
        "linhaDigitavel": linha,
        "codigopix": pix,
        "codigoPix": pix,
        "link": fatura.get("linkBoleto") or fatura.get("urlBoletoCopiaCola") or "",
        "linkBoleto": fatura.get("linkBoleto") or "",
        "urlPixCopiaCola": fatura.get("urlPixCopiaCola") or "",
        "clienteContrato": id_cliente,
        "contrato": id_cliente,
        "vencida": vencida,
        "esta_atrasada": vencida,
        "diasAtraso": fatura.get("diasAtraso") or 0,
    }


def _payload_from_request(request) -> dict:
    if request.method == "POST":
        data = request.data
        if hasattr(data, "dict"):
            try:
                return data.dict().copy()
            except Exception:
                pass
        return dict(data) if isinstance(data, dict) else {}
    return request.query_params.dict().copy()


def _resolve_id_cliente(client: ReceitaNetClient, payload: dict) -> Tuple[Optional[int], Optional[str]]:
    """Resolve idCliente a partir de contrato/cpf no payload do app."""
    # Preferir idCliente explícito. O app grava "contrato" = idCliente após a seleção.
    # Não usar idContrato aqui: na RN pode diferir do idCliente (ex.: 2523950 vs 2466952).
    direct = _as_int(
        payload.get("idCliente")
        or payload.get("id_cliente")
        or payload.get("contrato")
        or payload.get("contract_id")
        or payload.get("contratoId")
    )
    cpf = _digits(payload.get("cpf_cnpj") or payload.get("cpfcnpj") or payload.get("cpfCnpj"))

    if direct:
        return direct, None

    if cpf:
        res = client.consultar_clientes(cpf_cnpj=cpf)
        if not res.get("ok"):
            return None, res.get("error") or "Falha ao consultar cliente no ReceitaNet."
        clientes = _extract_clientes(res.get("data"))
        if not clientes:
            return None, "Cliente não encontrado no ReceitaNet."
        if len(clientes) > 1:
            return None, "Há mais de um contrato para este CPF. Selecione o contrato no app."
        first = clientes[0]
        return _as_int(first.get("idCliente") or first.get("id")), None

    return None, "Informe CPF/CNPJ ou contrato (idCliente)."


def _extract_chamados(data: Any) -> List[dict]:
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("chamados", "items", "results", "data"):
        items = data.get(key)
        if isinstance(items, list):
            return [c for c in items if isinstance(c, dict)]
        if key == "data" and isinstance(items, dict):
            for nested_key in ("chamados", "items", "results"):
                nested = items.get(nested_key)
                if isinstance(nested, list):
                    return [c for c in nested if isinstance(c, dict)]
    return []


def _map_chamado_to_ticket(chamado: dict, id_cliente: Any = None) -> dict:
    """Converte chamado ReceitaNet → campos que a tela de suporte do app já lê."""
    protocolo = (
        chamado.get("protocolo")
        or chamado.get("oc_protocolo")
        or chamado.get("numero")
        or ""
    )
    assunto = (
        chamado.get("tipoDisplay")
        or chamado.get("tipoDescricao")
        or chamado.get("assunto")
        or chamado.get("tipo")
        or chamado.get("oc_tipo_descricao")
        or "Chamado"
    )
    descricao = (
        chamado.get("motivo")
        or chamado.get("conteudo")
        or chamado.get("descricao")
        or chamado.get("mensagem")
        or chamado.get("oc_conteudo")
        or ""
    )
    status = (
        chamado.get("statusDisplay")
        or chamado.get("statusDescricao")
        or chamado.get("status")
        or chamado.get("oc_status_descricao")
        or "Aberto"
    )
    # API: data=YYYY-MM-DD, hora=HH:MM:SS → exibir data DD/MM/YYYY
    data_iso = chamado.get("data") or chamado.get("dataAbertura") or chamado.get("dataCadastro") or ""
    hora = str(chamado.get("hora") or "").strip()
    data_br = _format_br_date(data_iso)
    if data_br and hora:
        data_abertura = f"{data_br} {hora}"
    elif data_br:
        data_abertura = data_br
    else:
        data_abertura = str(
            chamado.get("criadoEm")
            or chamado.get("createdAt")
            or chamado.get("oc_data_cadastro")
            or ""
        )
    cid = str(id_cliente or chamado.get("idCliente") or "").strip()
    return {
        "id": chamado.get("idSuporte") or chamado.get("id") or chamado.get("idChamado"),
        "idSuporte": chamado.get("idSuporte"),
        "oc_protocolo": protocolo,
        "protocolo": protocolo,
        "oc_tipo_descricao": str(assunto),
        "assunto": str(assunto),
        "oc_conteudo": str(descricao),
        "mensagem": str(descricao),
        "descricao": str(descricao),
        "oc_status_descricao": str(status),
        "status": str(status),
        "data": data_br,
        "hora": hora,
        "oc_data_cadastro": data_abertura,
        "data_abertura": data_abertura,
        # App filtra por contrato; no ReceitaNet o idCliente é o "contrato" do app
        "oc_contrato_id": cid,
        "contrato_id": cid,
        "contrato": cid,
        "idCliente": cid,
        "_erp": "receitanet",
    }


def handle_receitanet_proxy(request, endpoint: str, profile) -> Response:
    clean = (endpoint or "").lstrip("/").rstrip("/")
    if clean.startswith("central/contratos"):
        clean = "central/contratos"

    token = (profile.sgp_token or "").strip()
    base = (profile.sgp_url or "").strip()
    if not token or not base:
        return Response(
            {"error": f"Provedor sem credenciais ReceitaNet (URL/token) no painel."},
            status=400,
        )
    if token.startswith("sk_live_") or token.startswith("sk_test_"):
        return Response(
            {
                "error": (
                    "Token do ERP inválido. Em Integração ERP (ReceitaNet), use o token "
                    "da Central Digital (não o sk_live_ do aplicativo)."
                )
            },
            status=400,
        )

    client = ReceitaNetClient(base, token)
    payload = _payload_from_request(request)
    payload.pop("provider_id", None)
    payload.pop("provider_token", None)
    payload.pop("token", None)
    payload.pop("app", None)

    # --- PDF do contrato (GET /clientes/{idCliente}/contrato) ---
    if clean in CONTRATO_PDF_ENDPOINTS or clean.endswith("contrato/pdf"):
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response(
                {"status": 0, "error": err or "Cliente não identificado."},
                status=400,
            )
        res = client.cliente_contrato_pdf(id_cliente)
        if not res.get("ok") or not res.get("content"):
            return Response(
                {
                    "status": 0,
                    "error": res.get("error") or "Falha ao baixar o contrato PDF no ReceitaNet.",
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        pdf = res["content"]
        response = HttpResponse(
            pdf,
            content_type=res.get("content_type") or "application/pdf",
        )
        response["Content-Disposition"] = 'inline; filename="contrato.pdf"'
        response["Content-Length"] = str(len(pdf))
        return response

    # --- Consulta ---
    if clean in CONSULTA_ENDPOINTS:
        cpf = _digits(payload.get("cpf_cnpj") or payload.get("cpfcnpj") or payload.get("cpfCnpj"))
        id_cli = _as_int(payload.get("idCliente") or payload.get("contrato"))
        res = client.consultar_clientes(cpf_cnpj=cpf, id_cliente=id_cli if not cpf else None)
        if not res.get("ok"):
            return Response(
                {"error": res.get("error") or "Falha na consulta ReceitaNet.", "receitanet_status": res.get("http_status")},
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        contratos = []
        for c in _extract_clientes(res.get("data")):
            mapped = _map_cliente_to_contrato(c)
            cid = _as_int(mapped.get("idCliente") or mapped.get("contrato"))
            if cid:
                try:
                    rsum = client.cliente_resumo(cid)
                    if rsum.get("ok") and isinstance(rsum.get("data"), dict):
                        mapped = _enrich_contrato_from_resumo(mapped, rsum["data"])
                except Exception as exc:
                    logger.warning("ReceitaNet resumo id=%s: %s", cid, exc)
            contratos.append(mapped)
        return Response({"contratos": contratos, "status": 1})

    # --- Consumo (mensal via /resumo) ---
    if clean in CONSUMO_ENDPOINTS or clean.endswith("extratouso"):
        id_cliente, err = _resolve_id_cliente(client, payload)
        logger.info("ReceitaNet consumo idCliente=%s err=%s", id_cliente, err)
        if not id_cliente:
            return Response({"list": [], "extrato": [], "error": err or "Cliente não identificado."}, status=400)
        res = client.cliente_resumo(id_cliente)
        if not res.get("ok"):
            logger.warning(
                "ReceitaNet resumo/consumo falhou id=%s status=%s err=%s",
                id_cliente,
                res.get("http_status"),
                res.get("error"),
            )
            return Response(
                {
                    "list": [],
                    "extrato": [],
                    "error": res.get("error") or "Falha ao consultar consumo no ReceitaNet.",
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        extrato = _map_consumo_mensal(data.get("consumoMensal"))
        logger.info("ReceitaNet consumo id=%s pontos=%s", id_cliente, len(extrato))
        # Histórico mensal completo (não diário) — o app escolhe mês só no SGP.
        return Response({"list": extrato, "extrato": extrato, "status": 1})

    # --- Faturas / títulos ---
    if clean in FATURAS_ENDPOINTS:
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response({"error": err or "Cliente não identificado.", "titulos": []}, status=400)

        status_raw = str(payload.get("status") or "todos").strip().lower()
        # App SGP às vezes manda status específico; RN aceita aberto|pago|cancelado|todos
        status_map = {
            "pago": "pago",
            "paga": "pago",
            "aberto": "aberto",
            "abertos": "aberto",
            "pendente": "aberto",
            "cancelado": "cancelado",
            "todos": "todos",
            "all": "todos",
        }
        rn_status = status_map.get(status_raw, "todos")

        today = date.today()
        data_inicio = str(payload.get("dataInicio") or payload.get("data_inicio") or "").strip()
        data_fim = str(payload.get("dataFim") or payload.get("data_fim") or "").strip()
        if not data_inicio:
            data_inicio = (today - timedelta(days=365)).isoformat()
        if not data_fim:
            data_fim = (today + timedelta(days=60)).isoformat()

        res = client.listar_faturas(
            id_cliente,
            status=rn_status,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        if not res.get("ok"):
            return Response(
                {
                    "error": res.get("error") or "Falha ao listar faturas no ReceitaNet.",
                    "titulos": [],
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        titulos = [
            _map_fatura_to_titulo(f, id_cliente=id_cliente)
            for f in _extract_faturas(res.get("data"))
        ]
        return Response({"titulos": titulos, "faturas": titulos, "status": 1})

    # --- Notas fiscais (faturas com link de documento fiscal) ---
    if clean in NOTA_FISCAL_ENDPOINTS or clean.startswith("central/notafiscal"):
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response([], status=200)

        today = date.today()
        data_inicio = str(payload.get("dataInicio") or payload.get("data_inicio") or "").strip()
        data_fim = str(payload.get("dataFim") or payload.get("data_fim") or "").strip()
        if not data_inicio:
            data_inicio = (today - timedelta(days=730)).isoformat()
        if not data_fim:
            data_fim = today.isoformat()

        empresa = _empresa_razao_social(client)
        res = client.listar_faturas(
            id_cliente,
            status="todos",
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        if not res.get("ok"):
            logger.warning(
                "ReceitaNet notas fiscais id=%s status=%s err=%s",
                id_cliente,
                res.get("http_status"),
                res.get("error"),
            )
            return Response([], status=200)

        notas: List[dict] = []
        for f in _extract_faturas(res.get("data")):
            if not isinstance(f, dict):
                continue
            mapped = _map_fatura_to_nota(f, empresa=empresa, id_cliente=id_cliente)
            status = str(mapped.get("status") or "").lower()
            link = str(mapped.get("link") or "").strip()
            # NF costuma existir em faturas pagas; inclui abertas só se houver link de documento.
            if not link:
                continue
            if status not in ("pago", "paga", "aberto", "aberta", "cancelado", "cancelada", ""):
                continue
            notas.append(mapped)

        notas.sort(
            key=lambda n: str(n.get("data_emissao") or ""),
            reverse=True,
        )
        logger.info("ReceitaNet notas fiscais id=%s total=%s", id_cliente, len(notas))
        return Response(notas)

    # --- Promessa / liberação ---
    if clean in PROMESSA_ENDPOINTS:
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response(
                {"status": 0, "liberado": False, "msg": err or "Cliente não identificado.", "error": err},
                status=400,
            )
        contato = str(
            payload.get("contato")
            or payload.get("telefone")
            or payload.get("phone")
            or payload.get("uracontato")
            or ""
        ).strip()
        # Se o app não mandou telefone, tenta do resumo/consulta
        if not contato:
            try:
                rsum = client.cliente_resumo(id_cliente)
                dados = rsum.get("data") if isinstance(rsum.get("data"), dict) else {}
                # telefones às vezes vêm na consulta; no resumo raramente
                if not contato:
                    cons = client.consultar_clientes(id_cliente=id_cliente)
                    for c in _extract_clientes(cons.get("data")):
                        tels = c.get("telefones") or []
                        if isinstance(tels, list) and tels:
                            contato = str(tels[0] or "").strip()
                            break
                        for key in ("telefone", "celular", "fone"):
                            if c.get(key):
                                contato = str(c.get(key)).strip()
                                break
                        if contato:
                            break
                _ = dados  # resumo reservado para regras futuras
            except Exception as exc:
                logger.warning("ReceitaNet promessa: falha ao buscar contato id=%s: %s", id_cliente, exc)

        logger.info("ReceitaNet promessa idCliente=%s contato=%s", id_cliente, bool(contato))
        res = client.promessa_pagamento(id_cliente, contato=contato)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        if not isinstance(data, dict):
            data = {}
        if not data and isinstance(res.get("raw"), dict) and isinstance(res["raw"].get("data"), dict):
            data = res["raw"]["data"]

        if not res.get("ok"):
            msg = res.get("error") or "Não foi possível registrar a promessa de pagamento."
            logger.warning(
                "ReceitaNet promessa falhou id=%s status=%s err=%s raw=%s",
                id_cliente,
                res.get("http_status"),
                msg,
                str(res.get("raw"))[:400],
            )
            return Response(
                {
                    "status": 0,
                    "liberado": False,
                    "msg": msg,
                    "error": msg,
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        liberado = bool(data.get("liberado")) if "liberado" in data else True
        status_val = data.get("status")
        if status_val is None:
            status_val = 1 if liberado else 0
        liberado_ate = data.get("liberadoAteDisplay") or data.get("liberadoAte") or ""
        return Response(
            {
                "status": status_val,
                "liberado": liberado,
                "liberado_dias": liberado_ate or None,
                "liberadoAte": liberado_ate,
                "protocolo": data.get("protocolo") or "",
                "msg": (
                    f"Promessa registrada. Liberado até {liberado_ate}."
                    if liberado and liberado_ate
                    else ("Promessa de pagamento registrada." if liberado else "Promessa registrada.")
                ),
                "idCliente": data.get("idCliente") or id_cliente,
            }
        )

    # --- Verificar acesso / status do modem ---
    if clean in ACESSO_ENDPOINTS:
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response(
                {"status": 0, "online": False, "error": err or "Cliente não identificado."},
                status=400,
            )
        res = client.verificar_acesso(id_cliente)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        if not isinstance(data, dict):
            data = {}
        # Se a API devolver o envelope no raw sem nested data
        if not data and isinstance(res.get("raw"), dict):
            raw = res["raw"]
            if isinstance(raw.get("data"), dict):
                data = raw["data"]
            elif "online" in raw or "status" in raw:
                data = raw

        if not res.get("ok"):
            return Response(
                {
                    "status": 0,
                    "online": False,
                    "error": res.get("error") or "Falha ao verificar acesso no ReceitaNet.",
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )

        online = data.get("online")
        status_rn = data.get("status")
        # App (parseAccessStatus): 1=online, 0=offline, 9=manutenção
        # ReceitaNet: online bool; status 2 = Cliente Offline (legado)
        if online is True or status_rn in (1, "1"):
            status_out = 1
            online_out = True
        elif online is False or status_rn in (2, "2", 0, "0"):
            status_out = 0
            online_out = False
        elif status_rn in (9, "9"):
            status_out = 9
            online_out = False
        else:
            status_out = 0 if online is False else (1 if online else 0)
            online_out = bool(online) if online is not None else False

        return Response(
            {
                "status": status_out,
                "online": online_out,
                "idCliente": data.get("idCliente") or id_cliente,
                "msg": data.get("message") or data.get("msg") or "",
                "raw_status": status_rn,
            }
        )

    # --- Abrir chamado ---
    if clean in CHAMADO_OPEN_ENDPOINTS:
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response({"status": 0, "error": err or "Cliente não identificado.", "msg": err}, status=400)

        tipo = _as_int(payload.get("tipo") or payload.get("ocorrenciatipo") or payload.get("typeId"))
        motivo = str(
            payload.get("motivo")
            or payload.get("conteudo")
            or payload.get("conteudolimpo")
            or payload.get("message")
            or ""
        ).strip()
        contato = str(payload.get("contato") or payload.get("telefone") or "").strip()
        if not motivo:
            return Response({"status": 0, "error": "Informe o motivo/conteúdo do chamado.", "msg": "Motivo obrigatório."}, status=400)

        res = client.abrir_chamado(id_cliente, tipo=tipo, motivo=motivo, contato=contato)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        chamado = data.get("chamado") if isinstance(data.get("chamado"), dict) else data
        if not res.get("ok"):
            return Response(
                {
                    "status": 0,
                    "error": res.get("error") or "Falha ao abrir chamado no ReceitaNet.",
                    "msg": res.get("error"),
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        return Response(
            {
                "status": 1,
                "protocolo": (chamado or {}).get("protocolo") or "",
                "id": (chamado or {}).get("idSuporte") or (chamado or {}).get("id"),
                "msg": "Chamado aberto com sucesso.",
                "chamado": chamado,
            },
            status=201 if res.get("http_status") == 201 else 200,
        )

    # --- Listar chamados ---
    if clean in CHAMADO_LIST_ENDPOINTS:
        id_cliente, err = _resolve_id_cliente(client, payload)
        if not id_cliente:
            return Response(
                {"chamados": [], "list": [], "status": 0, "error": err or "Cliente não identificado."},
                status=400,
            )
        res = client.listar_chamados(id_cliente)
        if not res.get("ok"):
            return Response(
                {
                    "chamados": [],
                    "list": [],
                    "status": 0,
                    "error": res.get("error") or "Falha ao listar chamados no ReceitaNet.",
                    "receitanet_status": res.get("http_status"),
                },
                status=400 if res.get("http_status") in (400, 401, 403, 404, 422) else 502,
            )
        chamados = [
            _map_chamado_to_ticket(c, id_cliente=id_cliente)
            for c in _extract_chamados(res.get("data"))
        ]
        return Response({"chamados": chamados, "list": chamados, "status": 1})

    return Response(
        {
            "error": (
                f"Endpoint '{clean}' não suportado para ReceitaNet. "
                "Disponíveis: consulta, resumo/consumo, faturas, notas fiscais, "
                "contrato PDF, promessa, verificar acesso, listar e abrir chamado."
            ),
            "status": 0,
        },
        status=400,
    )
