"""
Cliente HTTP da API ReceitaNet Central Digital.

Docs: https://www.receitanet.net/api/centraldigital/
Produção: https://sistema.receitanet.net/api/novo/central-digital

Endpoints usados pelo app Niohub:
- POST /clientes/consulta
- GET  /clientes/{idCliente}/resumo
- GET  /clientes/{idCliente}/faturas
- GET  /clientes/{idCliente}/contrato  (PDF binário)
- GET  /empresa  (razão social do provedor)
- POST /clientes/{idCliente}/promessa-pagamento
- POST /clientes/{idCliente}/chamados
- POST /clientes/{idCliente}/acesso/verificar
- GET  /clientes/{idCliente}/chamados
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_PATH = "/api/novo/central-digital"


def normalize_receitanet_base_url(raw: str) -> str:
    """
    Aceita host puro ou URL completa da Central Digital.
    Exemplos:
      https://sistema.receitanet.net
      https://sistema.receitanet.net/api/novo/central-digital
    """
    base = (raw or "").strip().rstrip("/")
    if not base:
        return ""
    if base.lower().startswith("http://"):
        base = "https://" + base[7:]
    if "central-digital" in base.lower() or "centraldigital" in base.lower():
        return base.rstrip("/")
    return f"{base}{DEFAULT_BASE_PATH}"


class ReceitaNetClient:
    def __init__(self, base_url: str, token: str, *, timeout: int = 30):
        self.base_url = normalize_receitanet_base_url(base_url)
        self.token = (token or "").strip()
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "token": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        path = "/" + (path or "").lstrip("/")
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Dict[str, Any]:
        url = self._url(path)
        try:
            resp = requests.request(
                method.upper(),
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception("ReceitaNet request failed %s %s: %s", method, url, exc)
            return {
                "ok": False,
                "http_status": 0,
                "error": f"Falha de conexão com ReceitaNet: {exc}",
                "data": None,
                "raw": None,
            }

        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {"raw": (resp.text or "")[:500]}

        ok = 200 <= resp.status_code < 300
        # SuccessEnvelope típico: { success/ok, data, message }
        if isinstance(body, dict):
            if body.get("success") is False or body.get("ok") is False:
                ok = False

        data = body.get("data") if isinstance(body, dict) else body
        err = None
        if not ok and isinstance(body, dict):
            err = (
                body.get("message")
                or body.get("msg")
                or body.get("error")
                or body.get("detail")
                or f"ReceitaNet HTTP {resp.status_code}"
            )
            # ValidationError típico: { errors: { campo: ["msg"] } } ou lista
            errors = body.get("errors") or body.get("error_list")
            if isinstance(errors, dict):
                parts = []
                for k, v in errors.items():
                    if isinstance(v, (list, tuple)):
                        parts.append(f"{k}: {', '.join(str(x) for x in v)}")
                    else:
                        parts.append(f"{k}: {v}")
                if parts:
                    err = "; ".join(parts)
            elif isinstance(errors, list) and errors:
                err = "; ".join(str(x) for x in errors)

        logger.info(
            "ReceitaNet %s %s status=%s ok=%s",
            method.upper(),
            path,
            resp.status_code,
            ok,
        )
        return {
            "ok": ok,
            "http_status": resp.status_code,
            "error": err,
            "data": data,
            "raw": body,
            "meta": body.get("meta") if isinstance(body, dict) else None,
        }

    def consultar_clientes(
        self,
        *,
        cpf_cnpj: str = "",
        id_cliente: Optional[int] = None,
        contrato: Optional[int] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"page": page, "perPage": per_page}
        digits = re.sub(r"\D", "", str(cpf_cnpj or ""))
        if digits:
            body["cpfCnpj"] = digits
        if id_cliente:
            body["idCliente"] = int(id_cliente)
        if contrato:
            body["contrato"] = int(contrato)
        if not digits and not id_cliente and not contrato:
            return {
                "ok": False,
                "http_status": 400,
                "error": "Informe CPF/CNPJ, idCliente ou contrato.",
                "data": None,
                "raw": None,
            }
        return self._request("POST", "/clientes/consulta", json_body=body)

    def cliente_resumo(self, id_cliente: int) -> Dict[str, Any]:
        """GET /clientes/{idCliente}/resumo — plano, consumo, faturas e cadastro."""
        return self._request("GET", f"/clientes/{int(id_cliente)}/resumo")

    def empresa(self) -> Dict[str, Any]:
        """GET /empresa — dados da empresa vinculada ao token."""
        return self._request("GET", "/empresa")

    def listar_faturas(
        self,
        id_cliente: int,
        *,
        status: str = "todos",
        tipo_data: str = "vencimento",
        data_inicio: str = "",
        data_fim: str = "",
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "status": status or "todos",
            "tipoData": tipo_data or "vencimento",
            "page": page,
            "perPage": per_page,
        }
        if data_inicio:
            params["dataInicio"] = data_inicio
        if data_fim:
            params["dataFim"] = data_fim
        return self._request("GET", f"/clientes/{int(id_cliente)}/faturas", params=params)

    def promessa_pagamento(self, id_cliente: int, *, contato: str = "") -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if contato:
            body["contato"] = contato
        # Sempre envia JSON (mesmo {}); None pode gerar 400 em alguns gateways.
        return self._request(
            "POST",
            f"/clientes/{int(id_cliente)}/promessa-pagamento",
            json_body=body,
        )

    def verificar_acesso(self, id_cliente: int) -> Dict[str, Any]:
        """POST /clientes/{idCliente}/acesso/verificar — status online do modem/acesso."""
        return self._request(
            "POST",
            f"/clientes/{int(id_cliente)}/acesso/verificar",
            json_body={},
        )

    def listar_chamados(
        self,
        id_cliente: int,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """GET /clientes/{idCliente}/chamados — chamados abertos do cliente."""
        return self._request(
            "GET",
            f"/clientes/{int(id_cliente)}/chamados",
            params={"page": page, "perPage": per_page},
        )

    def abrir_chamado(
        self,
        id_cliente: int,
        *,
        tipo: Optional[int] = None,
        motivo: str = "",
        contato: str = "",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if tipo is not None:
            body["tipo"] = int(tipo)
        if motivo:
            body["motivo"] = motivo
        if contato:
            body["contato"] = contato
        return self._request(
            "POST",
            f"/clientes/{int(id_cliente)}/chamados",
            json_body=body,
        )

    def cliente_contrato_pdf(self, id_cliente: int) -> Dict[str, Any]:
        """GET /clientes/{idCliente}/contrato — PDF do contrato (binário)."""
        url = self._url(f"/clientes/{int(id_cliente)}/contrato")
        headers = {
            "token": self.token,
            "Accept": "application/pdf, application/octet-stream, */*",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.exception("ReceitaNet contrato PDF failed %s: %s", url, exc)
            return {
                "ok": False,
                "http_status": 0,
                "error": f"Falha de conexão com ReceitaNet: {exc}",
                "content": None,
                "content_type": None,
            }

        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        content = resp.content or b""
        looks_pdf = content[:4] == b"%PDF" or "pdf" in content_type
        ok = 200 <= resp.status_code < 300 and bool(content) and looks_pdf

        err = None
        if not ok:
            err = f"ReceitaNet HTTP {resp.status_code}"
            if content and not looks_pdf:
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        err = (
                            body.get("message")
                            or body.get("msg")
                            or body.get("error")
                            or body.get("detail")
                            or err
                        )
                except Exception:
                    text = (resp.text or "")[:300].strip()
                    if text:
                        err = text

        logger.info(
            "ReceitaNet GET /clientes/%s/contrato status=%s ok=%s bytes=%s type=%s",
            id_cliente,
            resp.status_code,
            ok,
            len(content),
            content_type or "-",
        )
        return {
            "ok": ok,
            "http_status": resp.status_code,
            "error": err,
            "content": content if ok else None,
            "content_type": content_type or "application/pdf",
        }
