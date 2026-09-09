"""
API REST para o painel Acesso Rápido no modo suporte (Asaas).
Espelha o fluxo do SGP: consultar CPF/CNPJ → listar faturas → enviar na conversa.
"""
from __future__ import annotations

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from conversations.models import Conversation
from core.models import Provedor
from integrations.asaas_support_fatura import (
    buscar_faturas_por_cpf_cnpj,
    enviar_fatura_asaas,
)

logger = logging.getLogger(__name__)


class AsaasSupportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_provedor(self, request):
        provedor_id = (
            request.query_params.get("provedor_id")
            or request.data.get("provedor_id")
        )
        if not provedor_id:
            return None, Response(
                {"error": "Parâmetro 'provedor_id' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Provedor.objects.get(id=provedor_id), None
        except Provedor.DoesNotExist:
            return None, Response(
                {"error": "Provedor não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def _ensure_support_mode(self, provedor):
        mode = (getattr(provedor, "agent_mode", None) or "isp").strip().lower()
        if mode != "support":
            return Response(
                {
                    "error": (
                        "Este endpoint é exclusivo do modo suporte da plataforma. "
                        "No modo ISP use o painel SGP."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    @action(detail=False, methods=["get"], url_path="consultar-cliente")
    def consultar_cliente(self, request):
        """
        Busca cliente no Asaas por CPF/CNPJ e devolve formato compatível
        com o Acesso Rápido (contratos sintéticos + faturas).
        """
        cpfcnpj = request.query_params.get("cpfcnpj")
        customer_id = request.query_params.get("customer_id") or None
        provedor, err = self._get_provedor(request)
        if err:
            return err
        blocked = self._ensure_support_mode(provedor)
        if blocked:
            return blocked
        if not cpfcnpj:
            return Response(
                {"error": "Parâmetro 'cpfcnpj' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = buscar_faturas_por_cpf_cnpj(
            cpfcnpj,
            customer_id=customer_id,
            incluir_pagas=False,
            limit=20,
        )
        if not result.get("success"):
            return Response(
                {
                    "error": result.get("erro") or "Falha ao consultar Asaas.",
                    "cpfCnpj": result.get("cpf_cnpj"),
                },
                status=status.HTTP_404_NOT_FOUND
                if "nenhum cliente" in (result.get("erro") or "").lower()
                else status.HTTP_400_BAD_REQUEST,
            )

        if result.get("precisa_escolher_cliente"):
            return Response(
                {
                    "success": True,
                    "precisa_escolher_cliente": True,
                    "cpfCnpj": result.get("cpf_cnpj"),
                    "clientes": result.get("clientes") or [],
                    "nota": result.get("nota"),
                }
            )

        cliente = result.get("cliente") or {}
        local = result.get("provedor_painel") or {}
        cid = str(cliente.get("id") or "").strip() or "asaas"
        nome = (
            local.get("nome")
            or cliente.get("nome")
            or "Cliente Asaas"
        )
        doc = cliente.get("cpf_cnpj") or result.get("cpf_cnpj") or ""

        # Contrato sintético para reutilizar a UI do Acesso Rápido
        contrato = {
            "id": cid,
            "contratoId": cid,
            "plano_nome": "Assinatura NioHub",
            "nomeCliente": nome,
            "razaoSocial": nome,
            "cliente": nome,
            "cpfCnpj": doc,
            "contratoStatus": 1,
            "contratoStatusDisplay": "Ativo",
            "status": "ativo",
        }

        faturas = []
        for f in result.get("faturas") or []:
            faturas.append(
                {
                    "fatura": f.get("id"),
                    "id": f.get("id"),
                    "valor": f.get("valor"),
                    "vencimento": f.get("vencimento_br") or f.get("vencimento"),
                    "vencimento_br": f.get("vencimento_br"),
                    "status": f.get("status"),
                    "status_label": f.get("status_label"),
                    "descricao": f.get("descricao"),
                    "invoice_url": f.get("invoice_url"),
                    "bank_slip_url": f.get("bank_slip_url"),
                }
            )

        return Response(
            {
                "success": True,
                "source": "asaas",
                "nome": nome,
                "razaoSocial": nome,
                "cpfCnpj": doc,
                "contratos": [contrato],
                "faturas": faturas,
                "quantidade_em_aberto": len(faturas),
                "em_dia": len(faturas) == 0,
                "cliente_asaas": cliente,
                "provedor_painel": local or None,
                "nota": result.get("nota"),
            }
        )

    @action(detail=False, methods=["post"], url_path="enviar-fatura-interativa")
    def enviar_fatura_interativa(self, request):
        """Envia PIX/boleto Asaas na conversa (mesmo canal do atendimento)."""
        provedor, err = self._get_provedor(request)
        if err:
            return err
        blocked = self._ensure_support_mode(provedor)
        if blocked:
            return blocked

        payment_id = (
            request.data.get("payment_id")
            or request.data.get("fatura_id")
            or ""
        ).strip()
        conversation_id = request.data.get("conversation_id")
        tipo = (request.data.get("tipo_pagamento") or "ambos").strip().lower()
        cpf_cnpj = request.data.get("cpf_cnpj") or request.data.get("cpfcnpj")

        if not payment_id:
            return Response(
                {"success": False, "error": "payment_id / fatura_id obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not conversation_id:
            return Response(
                {"success": False, "error": "conversation_id obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            conversation = Conversation.objects.select_related("contact", "inbox").get(
                id=int(conversation_id),
                inbox__provedor_id=provedor.id,
            )
        except (Conversation.DoesNotExist, TypeError, ValueError):
            return Response(
                {"success": False, "error": "Conversa não encontrada neste provedor."},
                status=status.HTTP_404_NOT_FOUND,
            )

        phone = getattr(getattr(conversation, "contact", None), "phone", None) or ""
        if not phone:
            return Response(
                {"success": False, "error": "Contato da conversa sem telefone."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = enviar_fatura_asaas(
                provedor,
                payment_id=payment_id,
                phone=phone,
                conversation=conversation,
                tipo_pagamento=tipo,
                cpf_cnpj=cpf_cnpj,
            )
        except Exception as exc:
            logger.exception("[AsaasSupport] Erro ao enviar fatura: %s", exc)
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not result.get("success"):
            return Response(
                {
                    "success": False,
                    "error": result.get("erro") or "Falha ao enviar fatura Asaas.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "payment_id": result.get("payment_id"),
                "tipo_pagamento": result.get("tipo_pagamento"),
                "valor": result.get("valor"),
                "vencimento_br": result.get("vencimento_br"),
            }
        )
