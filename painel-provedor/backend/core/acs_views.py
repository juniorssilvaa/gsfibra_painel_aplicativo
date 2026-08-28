"""Proxy autenticado da API NIO HUB - ACS (Wi-Fi por device_id ou login PPPoE)."""
from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .acs_client import ACSClient, ACSError
from .models import Provedor

logger = logging.getLogger(__name__)


class ACSIntegrationViewSet(viewsets.ViewSet):
    """
    Endpoints do painel para consultar/alterar Wi-Fi via ACS.

    GET  /api/acs/wifi/?provedor_id=&device_id=... | login=...
    POST /api/acs/wifi/  body: provedor_id + device_id|login + band/ssid/pass_*
    """

    permission_classes = [IsAuthenticated]

    def _get_provedor(self, request, from_body: bool = False):
        raw = (
            (request.data.get("provedor_id") if from_body else None)
            or request.query_params.get("provedor_id")
            or request.data.get("provedor_id")
        )
        if not raw:
            return None, Response(
                {"error": "provedor_id é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        provedor = get_object_or_404(Provedor, pk=raw)
        return provedor, None

    def _get_client(self, provedor):
        client = ACSClient.from_provedor(provedor)
        if not client:
            return None, Response(
                {"error": "Integração ACS não configurada (acs_url/acs_token)."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return client, None

    @staticmethod
    def _error_response(exc: ACSError) -> Response:
        code = exc.status_code or status.HTTP_502_BAD_GATEWAY
        if code < 400:
            code = status.HTTP_502_BAD_GATEWAY
        body = {"error": str(exc), "success": False}
        if isinstance(exc.payload, dict):
            body["acs"] = exc.payload
        return Response(body, status=code)

    @staticmethod
    def _wifi_change_kwargs(data: dict) -> dict:
        return {
            "band": data.get("band"),
            "ssid_24": data.get("ssid_24"),
            "ssid_5": data.get("ssid_5"),
            "pass_24": data.get("pass_24"),
            "pass_5": data.get("pass_5"),
        }

    @action(detail=False, methods=["get", "post"], url_path="wifi")
    def wifi(self, request):
        """
        Consulta (GET) ou aplica (POST) Wi-Fi.
        Identifique o CPE com device_id OU login (PPPoE).
        """
        provedor, err = self._get_provedor(request, from_body=request.method == "POST")
        if err:
            return err
        client, err = self._get_client(provedor)
        if err:
            return err

        data = request.data if request.method == "POST" else request.query_params
        device_id = (data.get("device_id") or "").strip()
        login = (data.get("login") or "").strip()

        if bool(device_id) == bool(login):
            return Response(
                {"error": "Informe exatamente um identificador: device_id ou login."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if request.method == "GET":
                result = (
                    client.get_wifi_by_device_id(device_id)
                    if device_id
                    else client.get_wifi_by_login(login)
                )
            else:
                kwargs = self._wifi_change_kwargs(data)
                result = (
                    client.set_wifi_by_device_id(device_id, **kwargs)
                    if device_id
                    else client.set_wifi_by_login(login, **kwargs)
                )
            return Response(result, status=status.HTTP_200_OK)
        except ACSError as exc:
            logger.warning(
                "[ACS] wifi falhou provedor=%s device_id=%s login=%s: %s",
                provedor.id,
                device_id or "-",
                login or "-",
                exc,
            )
            return self._error_response(exc)
