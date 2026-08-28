"""
Cliente HTTP para a API NIO HUB - ACS (TR-069 / Wi-Fi).

Importante: rotas de alteração usam trailing slash em /wifi/
(POST sem barra pode responder 200 com snapshot sem enfileirar a tarefa).
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class ACSError(Exception):
    """Erro de comunicação ou resposta da API ACS."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class ACSClient:
    def __init__(self, base_url: str, token: str, timeout: int = 45):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self.timeout = timeout
        if not self.base_url or not self.token:
            raise ACSError("ACS URL e token são obrigatórios.")

    @classmethod
    def from_provedor(cls, provedor) -> Optional["ACSClient"]:
        ext = getattr(provedor, "integracoes_externas", None) or {}
        url = (ext.get("acs_url") or "").strip()
        token = (ext.get("acs_token") or "").strip()
        if not url or not token:
            return None
        return cls(base_url=url, token=token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _encode_segment(value: str) -> str:
        # Mantém hífens (device_id ACS); escapa o restante do path.
        return quote(str(value).strip(), safe="-._~")

    def _wifi_url_by_device(self, device_id: str, *, trailing_slash: bool = True) -> str:
        seg = self._encode_segment(device_id)
        base = f"{self.base_url}/api/integration/devices/{seg}/wifi"
        return base + ("/" if trailing_slash else "")

    def _wifi_url_by_login(self, login: str, *, trailing_slash: bool = True) -> str:
        seg = self._encode_segment(login)
        base = f"{self.base_url}/api/integration/devices/login/{seg}/wifi"
        return base + ("/" if trailing_slash else "")

    def _get_wifi(self, url_with_slash: str, url_no_slash: str) -> dict:
        """
        GET: tenta /wifi/ e, se falhar/redirect/corpo vazio, tenta /wifi.
        Exige snapshot útil (ssid, device_id, serial ou pppoe_user).
        """
        errors: list[ACSError] = []
        for url in (url_with_slash, url_no_slash):
            try:
                data = self._request("GET", url)
            except ACSError as exc:
                errors.append(exc)
                continue
            if isinstance(data, dict) and any(
                data.get(k)
                for k in (
                    "wifi_ssid",
                    "wifi_ssid_5g",
                    "device_id",
                    "serial",
                    "pppoe_user",
                )
            ):
                return data
            errors.append(
                ACSError(
                    "Resposta ACS sem snapshot Wi-Fi.",
                    status_code=200,
                    payload=data if isinstance(data, dict) else None,
                )
            )
        for exc in errors:
            if exc.status_code == 404:
                raise exc
        if errors:
            raise errors[-1]
        raise ACSError("Falha ao consultar Wi-Fi no ACS.")

    @staticmethod
    def _wifi_payload(
        *,
        band: Optional[str] = None,
        ssid_24: Optional[str] = None,
        ssid_5: Optional[str] = None,
        pass_24: Optional[str] = None,
        pass_5: Optional[str] = None,
    ) -> dict:
        payload: dict[str, str] = {}
        if band is not None and str(band).strip() != "":
            payload["band"] = str(band).strip()
        if ssid_24 is not None and str(ssid_24) != "":
            payload["ssid_24"] = str(ssid_24)
        if ssid_5 is not None and str(ssid_5) != "":
            payload["ssid_5"] = str(ssid_5)
        if pass_24 is not None and str(pass_24) != "":
            payload["pass_24"] = str(pass_24)
        if pass_5 is not None and str(pass_5) != "":
            payload["pass_5"] = str(pass_5)
        if not payload:
            raise ACSError("Informe ao menos um campo de alteração (band/ssid/pass).")
        return payload

    def _request(self, method: str, url: str, *, json_body: Optional[dict] = None) -> dict:
        logger.info("[ACS] %s %s", method.upper(), url)
        try:
            response = requests.request(
                method.upper(),
                url,
                headers=self._headers(),
                json=json_body,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ACSError(f"Falha de rede ao chamar ACS: {exc}") from exc

        if 300 <= response.status_code < 400:
            raise ACSError(
                f"ACS redirecionou (HTTP {response.status_code}). Use a URL canônica.",
                status_code=response.status_code,
                payload={"location": response.headers.get("Location", "")},
            )

        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {"raw": (response.text or "")[:500]}

        if response.status_code >= 400:
            detail = ""
            if isinstance(data, dict):
                detail = (
                    data.get("message")
                    or data.get("detail")
                    or data.get("error")
                    or ""
                )
            raise ACSError(
                detail or f"ACS retornou HTTP {response.status_code}",
                status_code=response.status_code,
                payload=data,
            )

        if not isinstance(data, dict):
            return {"success": True, "data": data}
        return data

    # ------------------------------------------------------------------
    # Wi-Fi por device_id
    # ------------------------------------------------------------------
    def get_wifi_by_device_id(self, device_id: str) -> dict:
        if not (device_id or "").strip():
            raise ACSError("device_id é obrigatório.")
        return self._get_wifi(
            self._wifi_url_by_device(device_id, trailing_slash=True),
            self._wifi_url_by_device(device_id, trailing_slash=False),
        )

    def set_wifi_by_device_id(
        self,
        device_id: str,
        *,
        band: Optional[str] = None,
        ssid_24: Optional[str] = None,
        ssid_5: Optional[str] = None,
        pass_24: Optional[str] = None,
        pass_5: Optional[str] = None,
    ) -> dict:
        if not (device_id or "").strip():
            raise ACSError("device_id é obrigatório.")
        payload = self._wifi_payload(
            band=band,
            ssid_24=ssid_24,
            ssid_5=ssid_5,
            pass_24=pass_24,
            pass_5=pass_5,
        )
        # POST exige trailing slash para enfileirar a tarefa de verdade.
        return self._request(
            "POST",
            self._wifi_url_by_device(device_id, trailing_slash=True),
            json_body=payload,
        )

    # ------------------------------------------------------------------
    # Wi-Fi por login PPPoE
    # ------------------------------------------------------------------
    def get_wifi_by_login(self, login: str) -> dict:
        if not (login or "").strip():
            raise ACSError("login PPPoE é obrigatório.")
        return self._get_wifi(
            self._wifi_url_by_login(login, trailing_slash=True),
            self._wifi_url_by_login(login, trailing_slash=False),
        )

    def set_wifi_by_login(
        self,
        login: str,
        *,
        band: Optional[str] = None,
        ssid_24: Optional[str] = None,
        ssid_5: Optional[str] = None,
        pass_24: Optional[str] = None,
        pass_5: Optional[str] = None,
    ) -> dict:
        if not (login or "").strip():
            raise ACSError("login PPPoE é obrigatório.")
        payload = self._wifi_payload(
            band=band,
            ssid_24=ssid_24,
            ssid_5=ssid_5,
            pass_24=pass_24,
            pass_5=pass_5,
        )
        return self._request(
            "POST",
            self._wifi_url_by_login(login, trailing_slash=True),
            json_body=payload,
        )
