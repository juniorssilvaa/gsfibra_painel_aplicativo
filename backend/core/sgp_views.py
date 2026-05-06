from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Provedor
from .sgp_client import SGPClient
from .fatura_service import fatura_service
from conversations.models import Conversation
import logging

logger = logging.getLogger(__name__)

class SGPIntegrationViewSet(viewsets.ViewSet):
    """
    ViewSet para integração com o SGP via API URA.
    Fornece endpoints para o front-end consultar dados de clientes, faturas e suporte.
    """
    permission_classes = [IsAuthenticated]

    def _get_sgp_client(self, provedor):
        """Instancia o SGPClient com base nas configurações do provedor."""
        integracoes = provedor.integracoes_externas or {}
        sgp_url = integracoes.get('sgp_url')
        sgp_token = integracoes.get('sgp_token')
        sgp_app = integracoes.get('sgp_app')

        if not sgp_url or not sgp_token:
            return None
        
        return SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)

    @action(detail=False, methods=['get'], url_path='consultar-cliente')
    def consultar_cliente(self, request):
        """Consulta dados do titular e contratos pelo CPF/CNPJ."""
        cpfcnpj = request.query_params.get('cpfcnpj')
        provedor_id = request.query_params.get('provedor_id')

        if not cpfcnpj or not provedor_id:
            return Response(
                {"error": "Parâmetros 'cpfcnpj' e 'provedor_id' são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            
            if not sgp:
                return Response(
                    {"error": "Integração SGP não configurada para este provedor."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Limpar CPF/CNPJ
            cpf_limpo = "".join(filter(str.isdigit, str(cpfcnpj)))
            resultado = sgp.consultar_cliente(cpf_limpo)
            
            # Adicionar status de conexão para cada contrato se disponível
            if resultado and resultado.get('contratos'):
                for contrato in resultado['contratos']:
                    contrato_id = contrato.get('id') or contrato.get('id_contrato')
                    contrato['id'] = contrato_id  # Garante padronização pro front
                    if contrato_id:
                        try:
                            # Tentar buscar status de conexão em tempo real
                            status_conexao = sgp.verifica_acesso(contrato_id)
                            contrato['status_conexao_realtime'] = status_conexao
                        except Exception:
                            contrato['status_conexao_realtime'] = None

            return Response(resultado)
        except Provedor.DoesNotExist:
            return Response({"error": "Provedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erro ao consultar cliente no SGP: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='faturas')
    def listar_faturas(self, request):
        """Lista faturas de um contrato ou CPF/CNPJ."""
        contrato_id = request.query_params.get('contrato_id')
        cpfcnpj = request.query_params.get('cpfcnpj')
        provedor_id = request.query_params.get('provedor_id')

        if not provedor_id or (not contrato_id and not cpfcnpj):
            return Response(
                {"error": "Parâmetros 'provedor_id' e ('contrato_id' ou 'cpfcnpj') são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            
            if not sgp:
                return Response({"error": "Configuração SGP ausente."}, status=status.HTTP_404_NOT_FOUND)

            resultado = sgp.listar_faturas_v2(contrato_id=contrato_id, cpf_cnpj=cpfcnpj)
            return Response(resultado)
        except Exception as e:
            logger.error(f"Erro ao listar faturas: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='pix')
    def gerar_pix(self, request):
        """Gera QR Code/Copia e Cola do PIX para uma fatura."""
        fatura_id = request.query_params.get('fatura_id')
        provedor_id = request.query_params.get('provedor_id')

        if not fatura_id or not provedor_id:
            return Response({"error": "Fatura e Provedor são obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            resultado = sgp.gerar_pix(fatura_id)
            return Response(resultado)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='abrir-chamado')
    def abrir_chamado(self, request):
        """Abre um novo chamado técnico."""
        contrato_id = request.data.get('contrato_id')
        conteudo = request.data.get('conteudo')
        ocorrenciatipo = request.data.get('ocorrenciatipo')
        provedor_id = request.data.get('provedor_id')

        if not all([contrato_id, conteudo, provedor_id]):
            return Response({"error": "Dados incompletos para abertura de chamado."}, status=status.HTTP_400_BAD_REQUEST)
        if ocorrenciatipo is None or (isinstance(ocorrenciatipo, str) and not str(ocorrenciatipo).strip()):
            return Response({"error": "ocorrenciatipo é obrigatório (ID do tipo de ocorrência no SGP)."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            resultado = sgp.criar_chamado(contrato_id, conteudo, ocorrenciatipo)
            return Response(resultado)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @action(detail=False, methods=['post'], url_path='enviar-fatura-interativa')
    def enviar_fatura_interativa(self, request):
        """
        Gera e envia uma fatura interativa (PIX ou Boleto) via WhatsApp Cloud API.
        Utiliza o serviço centralizado fatura_service para garantir consistência com a IA.
        """
        fatura_id = request.data.get('fatura_id')
        provedor_id = request.data.get('provedor_id')
        conversation_id = request.data.get('conversation_id')
        tipo_pagamento = request.data.get('tipo_pagamento', 'pix') # 'pix' ou 'boleto'

        if not all([fatura_id, provedor_id, conversation_id]):
            return Response(
                {"error": "fatura_id, provedor_id e conversation_id são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            conversation = Conversation.objects.get(id=conversation_id)
            
            # 1. Buscar os detalhes da fatura no SGP usando o CPF/CNPJ
            cpf_cnpj = request.data.get('cpf_cnpj')
            
            if not cpf_cnpj:
                # Fallback: Buscar no contato
                cpf_cnpj = conversation.contact.phone
                if conversation.contact.additional_attributes and conversation.contact.additional_attributes.get('document'):
                    cpf_cnpj = conversation.contact.additional_attributes.get('document')
            
            # Limpar CPF/CNPJ (remover pontuação)
            cpf_cnpj = ''.join(filter(str.isdigit, str(cpf_cnpj)))
            
            logger.info(f">>> [FATURA] Enviando para cliente: {conversation.contact.name} | CPF/CNPJ: {cpf_cnpj} | Fatura: {fatura_id}")
            
            # Buscar dados completos da fatura
            dados_fatura = fatura_service.buscar_fatura_sgp(provedor, cpf_cnpj, fatura_id=fatura_id)
            
            if not dados_fatura or dados_fatura.get('status') != 1:
                return Response(
                    {"error": "Não foi possível recuperar os dados da fatura no SGP."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 2. Enviar a fatura usando o serviço centralizado
            # O serviço já detecta se deve usar WhatsApp Oficial ou Uazapi
            resultado = fatura_service.enviar_fatura(
                provedor=provedor,
                numero_whatsapp=conversation.contact.phone,
                dados_fatura=dados_fatura,
                conversation=conversation,
                tipo_pagamento=tipo_pagamento
            )

            if resultado.get('success'):
                return Response({"success": True, "message": "Fatura enviada com sucesso!"})
            else:
                return Response(
                    {"error": resultado.get('error', 'Falha ao enviar fatura.')},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Provedor.DoesNotExist:
            return Response({"error": "Provedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversa não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erro ao enviar fatura interativa: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
