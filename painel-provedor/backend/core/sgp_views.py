from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Provedor
from .sgp_client import SGPClient, SGPInvalidResponse
from .sgp_contract_utils import get_contrato_id, get_plano_nome, normalize_verifica_acesso
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
        sgp_nested = integracoes.get('sgp') if isinstance(integracoes.get('sgp'), dict) else {}
        sgp_url = sgp_nested.get('sgp_url') or integracoes.get('sgp_url')
        sgp_token = sgp_nested.get('sgp_token') or integracoes.get('sgp_token')
        sgp_app = sgp_nested.get('sgp_app') or integracoes.get('sgp_app')

        if not sgp_url or not sgp_token or not sgp_app:
            return None

        return SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)

    @action(detail=False, methods=['get'], url_path='consultar-cliente')
    def consultar_cliente(self, request):
        """Consulta dados do titular e contratos pelo CPF/CNPJ."""
        cpfcnpj = request.query_params.get('cpfcnpj')
        provedor_id = request.query_params.get('provedor_id')
        conversation_id = request.query_params.get('conversation_id')

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
                    contrato_id = get_contrato_id(contrato)
                    if contrato_id:
                        contrato['id'] = contrato_id
                        contrato['contratoId'] = contrato.get('contratoId') or contrato_id
                    plano = get_plano_nome(contrato)
                    if plano:
                        contrato['plano_nome'] = plano
                    if contrato_id:
                        try:
                            status_conexao = sgp.verifica_acesso(contrato_id)
                            contrato['status_conexao_realtime'] = normalize_verifica_acesso(status_conexao)
                        except Exception as exc:
                            logger.warning(
                                'verifica_acesso falhou contrato=%s: %s',
                                contrato_id,
                                exc,
                            )
                            contrato['status_conexao_realtime'] = {
                                'connection': 'unknown',
                                'label': 'Indisponível',
                            }

            if conversation_id and resultado:
                try:
                    conv = Conversation.objects.select_related('contact').filter(
                        id=int(conversation_id),
                        inbox__provedor_id=provedor.id,
                    ).first()
                    if conv and conv.contact:
                        from conversations.contact_name_utils import (
                            extract_sgp_client_name,
                            update_contact_from_sgp_by_id,
                        )
                        nome_sgp = extract_sgp_client_name(resultado)
                        if nome_sgp:
                            update_contact_from_sgp_by_id(
                                conv.contact.id,
                                nome_sgp,
                                cpf_limpo,
                                conversation_id=conv.id,
                                provedor_id=provedor.id,
                            )
                except (TypeError, ValueError):
                    pass

            return Response(resultado)
        except Provedor.DoesNotExist:
            return Response({"error": "Provedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except SGPInvalidResponse as e:
            logger.error("SGP resposta inválida ao consultar cliente: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Erro ao consultar cliente no SGP: {e}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='verifica-acesso')
    def verifica_acesso(self, request):
        """Consulta POST /api/ura/verificaacesso/ para status online/offline do contrato."""
        contrato_id = request.query_params.get('contrato_id')
        provedor_id = request.query_params.get('provedor_id')

        if not contrato_id or not provedor_id:
            return Response(
                {"error": "Parâmetros 'contrato_id' e 'provedor_id' são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            if not sgp:
                return Response(
                    {"error": "Integração SGP não configurada para este provedor."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            raw = sgp.verifica_acesso(contrato_id)
            return Response(normalize_verifica_acesso(raw))
        except Provedor.DoesNotExist:
            return Response({"error": "Provedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erro ao verificar acesso SGP: {e}", exc_info=True)
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

    @action(detail=False, methods=['post'], url_path='tipos-ocorrencia')
    def tipos_ocorrencia(self, request):
        """Lista os tipos de ocorrência (chamado) direto do SGP do provedor."""
        from django.core.cache import cache

        provedor_id = request.data.get('provedor_id')
        cpfcnpj = "".join(filter(str.isdigit, str(request.data.get('cpfcnpj') or '')))
        contrato_id = str(request.data.get('contrato_id') or '').strip()
        if not provedor_id:
            return Response({"error": "provedor_id é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f"sgp_tipos_ocorrencia:{provedor_id}"
        cached = cache.get(cache_key)
        if cached:
            return Response({"tipos": cached})

        try:
            provedor = Provedor.objects.get(id=provedor_id)
        except Provedor.DoesNotExist:
            return Response({"error": "Provedor não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        sgp = self._get_sgp_client(provedor)
        if not sgp:
            return Response({"error": "Integração SGP não configurada para este provedor."}, status=status.HTTP_404_NOT_FOUND)

        senha_central = None
        if cpfcnpj:
            try:
                resultado = sgp.consultar_cliente(cpfcnpj)
                contratos = (resultado or {}).get('contratos') or [] if isinstance(resultado, dict) else []
                escolhido = next(
                    (c for c in contratos if contrato_id and str(get_contrato_id(c) or '') == contrato_id),
                    contratos[0] if contratos else None,
                )
                if escolhido:
                    senha_central = escolhido.get('contratoCentralSenha') or None
            except Exception as e:
                logger.warning("[SGP] tipos_ocorrencia | falha ao obter senha da central: %s", e)

        try:
            tipos = sgp.listar_tipos_ocorrencia(cpf_cnpj=cpfcnpj, senha=senha_central)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        cache.set(cache_key, tipos, 600)
        return Response({"tipos": tipos})

    @action(detail=False, methods=['post'], url_path='abrir-chamado')
    def abrir_chamado(self, request):
        """Abre um novo chamado técnico."""
        contrato_id = request.data.get('contrato_id')
        conteudo = request.data.get('conteudo')
        ocorrenciatipo = request.data.get('ocorrenciatipo', 1)
        provedor_id = request.data.get('provedor_id')
        conversation_id = request.data.get('conversation_id')

        if not all([contrato_id, conteudo, provedor_id]):
            return Response({"error": "Dados incompletos para abertura de chamado."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provedor = Provedor.objects.get(id=provedor_id)
            sgp = self._get_sgp_client(provedor)
            resultado = sgp.criar_chamado(contrato_id, conteudo, ocorrenciatipo)

            if resultado.get('success') and resultado.get('protocolo') and conversation_id:
                try:
                    from conversations.models import Conversation
                    from conversations.protocol_service import apply_sgp_protocol

                    conversation = Conversation.objects.filter(id=conversation_id).first()
                    if conversation:
                        apply_sgp_protocol(
                            conversation,
                            resultado.get('protocolo'),
                            chamado_id=resultado.get('chamado_id'),
                        )
                except Exception as proto_err:
                    logger.warning(
                        "[SGP] Falha ao vincular protocolo SGP à conversa %s: %s",
                        conversation_id,
                        proto_err,
                    )

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
        contrato_id = request.data.get('contrato_id') or request.data.get('contrato')

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
            contrato_id = str(contrato_id).strip() if contrato_id not in (None, '') else None
            
            logger.info(
                ">>> [FATURA] Enviando para cliente: %s | CPF/CNPJ: %s | Fatura: %s | Contrato: %s",
                conversation.contact.name,
                cpf_cnpj,
                fatura_id,
                contrato_id,
            )
            
            # Buscar dados completos da fatura (contrato obrigatório se houver vários)
            dados_fatura = fatura_service.buscar_fatura_sgp(
                provedor,
                cpf_cnpj,
                contrato_id=contrato_id,
                fatura_id=fatura_id,
            )
            
            if not dados_fatura or dados_fatura.get('status') != 1:
                err_msg = (
                    dados_fatura.get('mensagem')
                    if isinstance(dados_fatura, dict) and dados_fatura.get('mensagem')
                    else "Não foi possível recuperar os dados da fatura no SGP."
                )
                if (
                    not contrato_id
                    and isinstance(dados_fatura, dict)
                    and (
                        'mais de um contrato' in str(dados_fatura.get('msg') or '').lower()
                        or 'mais de um contrato' in str(dados_fatura.get('mensagem') or '').lower()
                    )
                ):
                    err_msg = (
                        "Cliente com mais de um contrato: selecione o contrato "
                        "antes de enviar a fatura."
                    )
                return Response(
                    {"error": err_msg},
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
