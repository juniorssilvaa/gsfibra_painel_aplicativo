"""
Cliente da API Banco Inter Empresas — OAuth2 mTLS + Cobrança v3 (boleto + Pix).
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from integrations.inter_config import (
    get_inter_base_url,
    get_inter_client_id,
    get_inter_client_secret,
    get_inter_conta_corrente,
    get_inter_scope,
    is_inter_configured,
    is_inter_sandbox,
    write_inter_cert_files,
)

logger = logging.getLogger(__name__)

# Cache simples de token em memória do processo
_token_cache: Dict[str, Any] = {"access_token": "", "expires_at": 0.0}


class InterService:
    """Operações de cobrança (boleto com Pix) no Banco Inter."""

    def __init__(self):
        self.client_id = get_inter_client_id()
        self.client_secret = get_inter_client_secret()
        self.base_url = get_inter_base_url()
        self.is_sandbox = is_inter_sandbox()
        self.conta_corrente = get_inter_conta_corrente()
        self.scope = get_inter_scope()
        self._cert = write_inter_cert_files()

        if not is_inter_configured():
            logger.warning(
                "[InterService] Credenciais incompletas (client_id/secret/cert/key) no SystemConfig"
            )
        else:
            logger.info(
                "[InterService] Ambiente %s — %s",
                "sandbox" if self.is_sandbox else "produção",
                self.base_url,
            )

    def is_ready(self) -> bool:
        return is_inter_configured() and bool(self._cert[0] and self._cert[1])

    def _cert_tuple(self):
        cert_path, key_path = self._cert
        if not cert_path or not key_path:
            raise RuntimeError("Certificado/chave Inter não configurados")
        return (cert_path, key_path)

    def get_access_token(self, *, force: bool = False) -> str:
        now = time.time()
        if not force and _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > now + 60:
            return str(_token_cache["access_token"])

        if not self.client_id or not self.client_secret:
            raise RuntimeError("Inter client_id/client_secret não configurados")

        url = f"{self.base_url}/oauth/v2/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": self.scope,
        }
        resp = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            cert=self._cert_tuple(),
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Falha ao obter token Inter ({resp.status_code}): {resp.text}")

        body = resp.json()
        token = (body.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Inter não retornou access_token")
        expires_in = int(body.get("expires_in") or 3600)
        _token_cache["access_token"] = token
        _token_cache["expires_at"] = now + expires_in
        return token

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        conta = "".join(ch for ch in str(self.conta_corrente or "") if ch.isdigit()).lstrip("0")
        if conta:
            headers["x-conta-corrente"] = conta
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        raw: bool = False,
        timeout: int = 45,
        ok_statuses: tuple[int, ...] = (200, 201, 204),
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json,
                cert=self._cert_tuple(),
                timeout=timeout,
            )
            if raw:
                if resp.status_code in ok_statuses or resp.status_code in (200, 201):
                    return {"success": True, "content": resp.content, "headers": dict(resp.headers)}
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": self.format_api_error(resp.text),
                }

            if resp.status_code in ok_statuses:
                if resp.status_code in (202, 204) or not (resp.text or "").strip():
                    return {"success": True, "data": {}, "status_code": resp.status_code}
                try:
                    return {"success": True, "data": resp.json(), "status_code": resp.status_code}
                except Exception:
                    return {"success": True, "data": {"raw": resp.text}, "status_code": resp.status_code}
            return {
                "success": False,
                "status_code": resp.status_code,
                "error": self.format_api_error(resp.text),
            }
        except Exception as exc:
            logger.exception("[InterService] %s %s falhou", method, path)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def build_pagador_from_provedor(provedor, incoming: dict | None = None) -> Dict[str, Any]:
        """Monta objeto pagador exigido pela API de cobrança (POST /cobrancas)."""
        incoming = incoming or {}
        cpf_cnpj = "".join(ch for ch in str(incoming.get("cpf_cnpj") or provedor.cpf_cnpj or "") if ch.isdigit())
        nome = (incoming.get("company") or incoming.get("nome") or provedor.nome or "").strip()
        email = (incoming.get("email_contato") or provedor.email_contato or "").strip()
        phone = "".join(
            ch
            for ch in str(
                incoming.get("mobile_phone")
                or provedor.mobile_phone
                or incoming.get("phone")
                or provedor.phone
                or ""
            )
            if ch.isdigit()
        )
        endereco = (incoming.get("endereco") or provedor.endereco or "Não informado").strip()[:100]
        numero = (incoming.get("address_number") or provedor.address_number or "S/N").strip()[:10]
        complemento = (incoming.get("complement") or provedor.complement or "").strip()[:30]
        bairro = (incoming.get("province") or provedor.province or "Centro").strip()[:60]
        cep = "".join(ch for ch in str(incoming.get("postal_code") or provedor.postal_code or "") if ch.isdigit())
        if len(cep) != 8:
            cep = "30130100"
        cidade = (incoming.get("cidade") or getattr(provedor, "cidade", None) or "Belo Horizonte").strip()[:60]
        uf = (incoming.get("uf") or getattr(provedor, "uf", None) or "MG").strip()[:2].upper()
        tipo = "JURIDICA" if len(cpf_cnpj) > 11 else "FISICA"

        ddd, telefone = "", phone
        if len(phone) >= 10:
            ddd = phone[:2]
            telefone = phone[2:]

        return {
            "cpfCnpj": cpf_cnpj,
            "tipoPessoa": tipo,
            "nome": nome[:100] or "Cliente",
            "endereco": endereco,
            "numero": numero,
            "complemento": complemento,
            "bairro": bairro,
            "cidade": cidade,
            "uf": uf,
            "cep": cep,
            "email": email[:80],
            "ddd": ddd,
            "telefone": telefone[:9],
        }

    @staticmethod
    def build_mensagem(*linhas: str) -> Dict[str, str] | None:
        """
        Mensagem impressa no boleto (API Cobrança).
        Aceita até 5 linhas (linha1..linha5), cada uma até 78 caracteres.
        """
        out: Dict[str, str] = {}
        for idx, raw in enumerate(linhas[:5], start=1):
            text = " ".join(str(raw or "").split()).strip()
            if text:
                out[f"linha{idx}"] = text[:78]
        return out or None

    def emitir_cobranca(
        self,
        *,
        seu_numero: str,
        valor_nominal: float,
        data_vencimento: str,
        pagador: Dict[str, Any],
        num_dias_agenda: int = 60,
        mensagem_linhas: list[str] | None = None,
        mensagem_linha1: str = "",
    ) -> Dict[str, Any]:
        """
        POST /cobranca/v3/cobrancas
        Retorna codigoSolicitacao (emissão assíncrona).
        """
        payload: Dict[str, Any] = {
            "seuNumero": str(seu_numero)[:15],
            "valorNominal": round(float(valor_nominal), 2),
            "dataVencimento": str(data_vencimento),
            "numDiasAgenda": max(0, min(60, int(num_dias_agenda))),
            "pagador": pagador,
        }
        linhas = list(mensagem_linhas or [])
        if mensagem_linha1 and not linhas:
            linhas = [mensagem_linha1]
        msg = self.build_mensagem(*linhas)
        if msg:
            payload["mensagem"] = msg

        # Emissão pode retornar 200/201; alguns ambientes usam 202
        return self._request(
            "POST",
            "/cobranca/v3/cobrancas",
            json=payload,
            ok_statuses=(200, 201, 202),
        )

    def consultar_cobranca(self, codigo_solicitacao: str) -> Dict[str, Any]:
        cid = (codigo_solicitacao or "").strip()
        if not cid:
            return {"success": False, "error": "codigoSolicitacao vazio"}
        return self._request("GET", f"/cobranca/v3/cobrancas/{cid}")

    def cancelar_cobranca(self, codigo_solicitacao: str, motivo: str = "Cancelado no Superadmin") -> Dict[str, Any]:
        """
        POST /cobranca/v3/cobrancas/{codigoSolicitacao}/cancelar
        Body: { motivoCancelamento } — máximo 50 caracteres. Sucesso: 202.
        """
        cid = (codigo_solicitacao or "").strip()
        if not cid:
            return {"success": False, "error": "codigoSolicitacao vazio"}
        motivo_limpo = " ".join(str(motivo or "Cancelado no Superadmin").split()).strip()[:50]
        return self._request(
            "POST",
            f"/cobranca/v3/cobrancas/{cid}/cancelar",
            json={"motivoCancelamento": motivo_limpo or "Cancelado no Superadmin"},
            ok_statuses=(200, 201, 202, 204),
        )

    def baixar_pdf(self, codigo_solicitacao: str) -> Dict[str, Any]:
        cid = (codigo_solicitacao or "").strip()
        if not cid:
            return {"success": False, "error": "codigoSolicitacao vazio"}
        return self._request("GET", f"/cobranca/v3/cobrancas/{cid}/pdf", raw=True)

    def listar_cobrancas(
        self,
        *,
        data_inicial: str,
        data_final: str,
        filtrar_data_por: str = "VENCIMENTO",
        situacao: str | None = None,
        pessoa_pagadora: str | None = None,
        cpf_cnpj: str | None = None,
        seu_numero: str | None = None,
        tipo_cobranca: str | None = None,
        pagina: int = 0,
        itens: int = 100,
        ordenar_por: str = "DATA_VENCIMENTO",
        tipo_ordenacao: str = "DESC",
    ) -> Dict[str, Any]:
        """
        GET /cobranca/v3/cobrancas
        Query: dataInicial/dataFinal (obrigatórios), filtrarDataPor, situacao, etc.
        """
        filtrar = (filtrar_data_por or "VENCIMENTO").upper()
        if filtrar not in ("VENCIMENTO", "EMISSAO", "PAGAMENTO"):
            filtrar = "VENCIMENTO"
        params: Dict[str, Any] = {
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "filtrarDataPor": filtrar,
            "paginacao.paginaAtual": int(pagina or 0),
            "paginacao.itensPorPagina": max(1, min(1000, int(itens or 100))),
            "ordenarPor": ordenar_por or "DATA_VENCIMENTO",
            "tipoOrdenacao": (tipo_ordenacao or "DESC").upper(),
        }
        if situacao:
            params["situacao"] = str(situacao).upper()
        if pessoa_pagadora:
            params["pessoaPagadora"] = str(pessoa_pagadora).strip()[:100]
        if cpf_cnpj:
            params["cpfCnpjPessoaPagadora"] = "".join(ch for ch in cpf_cnpj if ch.isdigit())[:18]
        if seu_numero:
            params["seuNumero"] = str(seu_numero)[:15]
        if tipo_cobranca:
            params["tipoCobranca"] = str(tipo_cobranca).upper()
        return self._request("GET", "/cobranca/v3/cobrancas", params=params)

    def cadastrar_webhook(self, webhook_url: str) -> Dict[str, Any]:
        return self._request(
            "PUT",
            "/cobranca/v3/cobrancas/webhook",
            json={"webhookUrl": webhook_url},
            ok_statuses=(200, 201, 204),
        )
    @staticmethod
    def format_api_error(error: Any) -> str:
        """Extrai mensagem legível do JSON de erro do Inter (violacoes/detail)."""
        if error is None:
            return "Erro desconhecido na API do Inter"
        if isinstance(error, dict):
            violacoes = error.get("violacoes") or error.get("violations") or []
            if isinstance(violacoes, list) and violacoes:
                razoes = [
                    str(v.get("razao") or v.get("message") or "").strip()
                    for v in violacoes
                    if isinstance(v, dict)
                ]
                razoes = [r for r in razoes if r]
                if razoes:
                    return " | ".join(razoes)
            for key in ("detail", "title", "message", "error"):
                if error.get(key):
                    return str(error[key]).strip()
            return str(error)
        text = str(error).strip()
        if not text:
            return "Erro desconhecido na API do Inter"
        # Tenta parsear JSON embutido na string
        try:
            import json

            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return InterService.format_api_error(parsed)
        except Exception:
            pass
        # Às vezes vem prefixado com status
        start = text.find("{")
        if start >= 0:
            try:
                import json

                parsed = json.loads(text[start:])
                if isinstance(parsed, dict):
                    return InterService.format_api_error(parsed)
            except Exception:
                pass
        return text

    @staticmethod
    def situacao_to_status(situacao: str | None) -> str:
        """Mapeia situação Inter → status interno (compatível com Asaas)."""
        s = (situacao or "").upper().strip()
        if s in ("RECEBIDO", "MARCADO_RECEBIDO", "PAGO"):
            return "RECEIVED"
        if s in ("ATRASADO", "VENCIDO", "EXPIRADO", "PROTESTO"):
            return "OVERDUE"
        if s in ("CANCELADO", "CANCELADA", "FALHA_EMISSAO"):
            return "DELETED"
        if s in ("A_RECEBER", "EMABERTO", "EMITIDO", "EM_PROCESSAMENTO"):
            return "PENDING"
        return s or "PENDING"

    @staticmethod
    def normalize_cobranca_item(data: dict, *, codigo_solicitacao: str = "") -> dict:
        """Normaliza payload Inter para formato similar ao payment Asaas (UI/WhatsApp)."""
        cob = data.get("cobranca") if isinstance(data.get("cobranca"), dict) else data
        boleto = data.get("boleto") if isinstance(data.get("boleto"), dict) else {}
        pix = data.get("pix") if isinstance(data.get("pix"), dict) else {}
        if not boleto and isinstance(cob.get("boleto"), dict):
            boleto = cob["boleto"]
        if not pix and isinstance(cob.get("pix"), dict):
            pix = cob["pix"]

        codigo = (
            codigo_solicitacao
            or data.get("codigoSolicitacao")
            or cob.get("codigoSolicitacao")
            or ""
        )
        situacao = cob.get("situacao") or data.get("situacao") or ""
        valor = cob.get("valorNominal") or data.get("valorNominal") or 0
        venc = cob.get("dataVencimento") or data.get("dataVencimento")
        seu_numero = cob.get("seuNumero") or data.get("seuNumero") or ""

        linha = (
            boleto.get("linhaDigitavel")
            or boleto.get("codigoBarras")
            or data.get("linhaDigitavel")
            or ""
        )
        pix_copia = pix.get("pixCopiaECola") or pix.get("emv") or data.get("pixCopiaECola") or ""
        pix_tx = pix.get("txid") or ""

        return {
            "id": codigo,
            "codigoSolicitacao": codigo,
            "seuNumero": seu_numero,
            "value": float(valor) if valor is not None else 0,
            "dueDate": venc,
            "status": InterService.situacao_to_status(situacao),
            "situacao": situacao,
            "billingType": "BOLETO",
            "provider": "inter",
            "bankSlipUrl": "",
            "invoiceUrl": "",
            "linhaDigitavel": linha,
            "pixCopiaECola": pix_copia,
            "txid": pix_tx,
            "raw": data,
        }
