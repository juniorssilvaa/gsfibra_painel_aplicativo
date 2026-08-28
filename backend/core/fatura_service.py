"""
Serviço para buscar faturas via endpoint SGP e enviar via Uazapi
"""

import requests
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import json
import time
from django.utils import timezone

logger = logging.getLogger(__name__)


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

class FaturaService:
    """Serviço para gerenciar faturas via SGP e Uazapi"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'NioChat/1.0'
        })

    def _formatar_cpf_cnpj(self, cpf_cnpj: str) -> str:
        """
        Formata CPF/CNPJ adicionando pontos e traços
        Args:
            cpf_cnpj: CPF ou CNPJ sem formatação
        Returns:
            CPF/CNPJ formatado
        """
        # Remover todos os caracteres não numéricos
        numeros = ''.join(filter(str.isdigit, cpf_cnpj))
        
        # Se já está formatado, retornar como está
        if '.' in cpf_cnpj or '-' in cpf_cnpj:
            return cpf_cnpj
        
        # Formatar CPF (11 dígitos)
        if len(numeros) == 11:
            return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
        
        # Formatar CNPJ (14 dígitos)
        elif len(numeros) == 14:
            return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
        
        # Se não for CPF nem CNPJ válido, retornar como está
        return cpf_cnpj

    def buscar_fatura_sgp(self, provedor, cpf_cnpj: str, contrato_id: Optional[str] = None, fatura_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Busca fatura no SGP usando o novo endpoint v2 (priorizando por contrato se disponível).
        Regra de Priorização:
        0. Se houver um fatura_id específico, procura por ela prioritariamente.
        1. Se houver mais de uma vencida -> Setor Financeiro (status: 2)
        2. Se houver exatamente uma vencida -> Retorna essa (status: 1)
        3. Se não houver vencidas, mas houver abertas -> Retorna a mais recente (status: 1)
        4. Se não houver nenhuma -> Parabéns (status: 0)
        """
        try:
            from .sgp_client import SGPClient
            
            integracao = provedor.integracoes_externas or {}
            sgp_url = integracao.get('sgp_url')
            sgp_token = integracao.get('sgp_token')
            sgp_app = integracao.get('sgp_app')
            
            if not all([sgp_url, sgp_token, sgp_app]):
                logger.warning(f"[FATURA] SGP não configurado para provedor {provedor.id}")
                return None
            
            sgp = SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)

            # --- BUSCA DA FATURA (V2 UNIFICADA) ---
            logger.warning(f"[FATURA][DEBUG] buscar_fatura_sgp | CPF={cpf_cnpj} | Contrato={contrato_id} | Usando fatura2via")
            cpf_limpo = ''.join(filter(str.isdigit, str(cpf_cnpj)))
            
            # Chamar o novo método unificado do SGPClient
            resultado = sgp.listar_faturas_v2(contrato_id=contrato_id, cpf_cnpj=cpf_limpo)
            
            if not resultado or not isinstance(resultado, dict):
                logger.error(f"[FATURA] Resposta inválida do SGP v2 para {contrato_id or cpf_cnpj}")
                return None
                
            faturas = resultado.get('links', [])
            if not isinstance(faturas, list): faturas = []
            
            # Ordenar faturas por data de vencimento (mais antiga primeiro)
            try:
                # O SGP costuma retornar 'vencimento_original' ou 'data_vencimento'
                faturas.sort(key=lambda x: str(x.get('vencimento_original') or x.get('data_vencimento') or '9999-12-31'))
            except Exception as e:
                logger.warning(f"[FATURA] Erro ao ordenar faturas: {e}")
                
            faturas_vencidas = []
            faturas_abertas = []
            
            for f in faturas:
                status = str(f.get('status', '')).lower()
                if status == 'vencida':
                    faturas_vencidas.append(f)
                else:
                    faturas_abertas.append(f)
            
            logger.info(f"[FATURA] Resumo: Vencidas: {len(faturas_vencidas)} | Abertas: {len(faturas_abertas)}")

            # 1.5 PRIORIDADE: Se foi passado um fatura_id específico
            f_selecionada = None
            tipo_display = ""
            
            if fatura_id:
                for f in faturas:
                    current_f_id = str(f.get('fatura') or f.get('id'))
                    if current_f_id == str(fatura_id):
                        f_selecionada = f
                        tipo_display = "selecionada"
                        break
            
            # 1. MÚLTIPLAS VENCIDAS -> TRANSFERIR FINANCEIRO (Somente se não for uma fatura específica)
            if not f_selecionada and len(faturas_vencidas) > 1:
                return {
                    'status': 2,
                    'solicitar_transferencia': True,
                    'setor': 'financeiro',
                    'mensagem': 'Detectamos que você possui múltiplas faturas vencidas. Para garantir um melhor atendimento, estamos transferindo você para o setor financeiro.'
                }
            
            # 2. SELEÇÃO DA FATURA (Se não foi selecionada por ID acima)
            if not f_selecionada:
                if faturas_vencidas:
                    f_selecionada = faturas_vencidas[0]
                    tipo_display = "vencida"
                elif faturas_abertas:
                    f_selecionada = faturas_abertas[0]
                    tipo_display = "em aberto"
            
            if f_selecionada:
                # Normalizar chaves para compatibilidade com enviar_fatura
                # enviar_fatura espera 'codigopix' e 'valor'
                if 'codigopix' not in f_selecionada and f_selecionada.get('pix_copia_cola'):
                    f_selecionada['codigopix'] = f_selecionada.get('pix_copia_cola')
                
                f_id = f_selecionada.get('fatura') or f_selecionada.get('id')
                
                # Tratar valor como float com segurança
                try:
                    valor_raw = f_selecionada.get('valor_original') or f_selecionada.get('valor') or f_selecionada.get('valor_total')
                    valor = float(str(valor_raw).replace(',', '.')) if valor_raw else 0.0
                    f_selecionada['valor'] = valor # injetar valor formatado para enviar_fatura
                except:
                    valor = 0.0
                
                venc_original = f_selecionada.get('vencimento_original') or f_selecionada.get('data_vencimento') or ''
                
                # Formatar data de vencimento (YYYY-MM-DD -> DD/MM/YYYY)
                venc_exibicao = venc_original
                try:
                    if '-' in str(venc_original):
                        dt = datetime.strptime(str(venc_original).split()[0], '%Y-%m-%d')
                        venc_exibicao = dt.strftime('%d/%m/%Y')
                except:
                    pass
                
                return {
                    'status': 1,
                    'links': [f_selecionada], # ESSENCIAL para compatibility com enviar_fatura
                    'fatura_id': f_id,
                    'valor': valor,
                    'vencimento': venc_exibicao,
                    'pix_copia_cola': f_selecionada.get('codigopix'),
                    'mensagem': f"💳 *Sua fatura {tipo_display}:*\n\nFatura ID: {f_id}\nVencimento: {venc_exibicao}\nValor: R$ {valor:.2f}\n\nSegue seu *QRcode PIX* para pagamento."
                }

            # 3. NADA ENCONTRADO
            return {
                'status': 0,
                'mensagem_positiva': True,
                'mensagem': 'Parabéns, você não possui faturas vencidas ou em aberto no momento. 😊'
            }
        except Exception as e:
            logger.exception(f"[FATURA] Erro crítico em buscar_fatura_sgp: {e}")
            return None

    def enviar_fatura(self, provedor, numero_whatsapp: str, dados_fatura: Dict[str, Any], conversation=None, tipo_pagamento: str = 'pix') -> Dict[str, Any]:
        """
        Envia fatura completa via canal apropriado (Uazapi ou WhatsApp Oficial).
        Detecta automaticamente o canal usado na conversa e envia pelo mesmo canal.
        E salva todas as mensagens no banco do Nio Chat
        
        Args:
            provedor: Objeto Provedor com configurações
            numero_whatsapp: Número do WhatsApp do cliente
            dados_fatura: Dados da fatura do SGP
            conversation: Objeto Conversation para salvar mensagens no banco
            tipo_pagamento: 'pix' ou 'boleto' - define quais botões enviar
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Detectar canal usado na conversa - verificar qual canal a conversa REALMENTE usa
            usar_whatsapp_oficial = False
            if conversation and hasattr(conversation, 'inbox') and conversation.inbox:
                inbox = conversation.inbox
                
                # Verificar se o channel_type do inbox é 'whatsapp_oficial'
                if inbox.channel_type == 'whatsapp_oficial':
                    usar_whatsapp_oficial = True
                # Verificar se o channel_id é 'whatsapp_cloud_api' (identificador usado pelo coexistence_webhooks)
                elif inbox.channel_id == 'whatsapp_cloud_api':
                    # Se o channel_id é whatsapp_cloud_api, verificar se existe Canal WhatsApp Oficial ativo
                    from core.models import Canal
                    canal_oficial = Canal.objects.filter(
                        provedor=provedor,
                        tipo='whatsapp_oficial',
                        ativo=True
                    ).first()
                    if canal_oficial:
                        usar_whatsapp_oficial = True
                else:
                    # Verificar se o channel_id corresponde a um Canal do tipo 'whatsapp_oficial'
                    from core.models import Canal
                    if inbox.channel_id and inbox.channel_id != 'default':
                        try:
                            # Tentar buscar como ID numérico
                            canal = Canal.objects.get(id=inbox.channel_id, provedor=provedor)
                            if canal.tipo == 'whatsapp_oficial' and canal.ativo:
                                usar_whatsapp_oficial = True
                        except (Canal.DoesNotExist, ValueError, TypeError):
                            # Se falhar, tentar buscar por tipo diretamente
                            canal_oficial = Canal.objects.filter(
                                provedor=provedor,
                                tipo='whatsapp_oficial',
                                ativo=True
                            ).first()
                            if canal_oficial:
                                usar_whatsapp_oficial = True
            
            # Se for WhatsApp Oficial, enviar via WhatsApp Cloud API
            if usar_whatsapp_oficial:
                return self._enviar_fatura_whatsapp_oficial(provedor, conversation, dados_fatura, tipo_pagamento)
            
            # Caso contrário, usar Uazapi (comportamento padrão)
            from .uazapi_client import UazapiClient
            try:
                from .qr_code_service import qr_code_service
            except ImportError as e:
                return {"success": False, "error": "Módulo qrcode não está instalado. Por favor, instale com: pip install qrcode[pil]"}
            
            # Obter configurações do Uazapi do provedor (campos corretos)
            integracao = provedor.integracoes_externas or {}
            uazapi_url = integracao.get('whatsapp_url')  # Corrigido: whatsapp_url
            uazapi_token = integracao.get('whatsapp_token')  # Corrigido: whatsapp_token
            instance_id = integracao.get('whatsapp_instance') or integracao.get('instance') or integracao.get('instance_name')
            
            # region agent log
            _debug_log(
                "uazapi_config",
                {
                    "provedor_id": getattr(provedor, "id", None),
                    "has_uazapi_url": bool(uazapi_url),
                    "has_uazapi_token": bool(uazapi_token),
                    "has_instance_id": bool(instance_id),
                    "phone_len": len("".join(filter(str.isdigit, str(numero_whatsapp)))) if numero_whatsapp else None,
                    "phone_last2": "".join(filter(str.isdigit, str(numero_whatsapp)))[-2:] if numero_whatsapp else None,
                },
                location="fatura_service.py:enviar_fatura_uazapi:config",
                hypothesis_id="H7",
            )
            # endregion

            if not all([uazapi_url, uazapi_token]):
                erro_msg = f"Configurações Uazapi incompletas para provedor {provedor.id}: falta URL ou token"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Criar cliente Uazapi
            uazapi = UazapiClient(base_url=uazapi_url, token=uazapi_token)
            
            if not dados_fatura.get('links'):
                # region agent log
                _debug_log(
                    "uazapi_no_links",
                    {
                        "provedor_id": getattr(provedor, "id", None),
                        "has_links": False,
                    },
                    location="fatura_service.py:enviar_fatura_uazapi:nolinks",
                    hypothesis_id="H7",
                )
                # endregion
                erro_msg = f"Dados da fatura não contêm links de pagamento (provedor {provedor.id})"
                logger.warning(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Pegar primeira fatura
            fatura = dados_fatura['links'][0]
            fatura_id = fatura.get('fatura', 'N/A')
            codigo_pix = fatura.get('codigopix')
            linha_digitavel = fatura.get('linhadigitavel')
            link_fatura = fatura.get('link')
            vencimento = fatura.get('vencimento_original') or fatura.get('vencimento', 'N/A')
            valor = fatura.get('valor', 0)
            
            # Formatar vencimento para dd/mm/yyyy
            vencimento_formatado = vencimento
            if vencimento and '-' in str(vencimento):
                try:
                    vencimento_date = datetime.strptime(vencimento, "%Y-%m-%d")
                    vencimento_formatado = vencimento_date.strftime("%d.%m.%Y")
                except:
                    pass
            
            # Formatar valor
            valor_formatado = f"R$ {valor:.2f}".replace('.', ',') if valor else "R$ 0,00"
            
            # Obter nome para footer e pix_name: priorizar nome da empresa (provedor), senão usar primeiro e segundo nome do cliente
            nome_provedor = provedor.nome if provedor and provedor.nome else None
            
            # Tentar obter nome do cliente da conversa ou dados da fatura
            nome_cliente = None
            try:
                if conversation and hasattr(conversation, 'contact') and conversation.contact:
                    # Acessar de forma segura para evitar problemas em contexto assíncrono
                    try:
                        nome_cliente = conversation.contact.name
                    except:
                        # Se falhar, tentar buscar do banco de forma síncrona
                        if hasattr(conversation, 'contact_id'):
                            from conversations.models import Contact
                            try:
                                contact_obj = Contact.objects.get(id=conversation.contact_id)
                                nome_cliente = contact_obj.name
                            except:
                                pass
            except:
                pass
            
            # Se não conseguiu da conversa, tentar dos dados da fatura
            if not nome_cliente and dados_fatura.get('nome_cliente'):
                nome_cliente = dados_fatura.get('nome_cliente')
            
            # Extrair primeiro e segundo nome do cliente se disponível
            primeiro_segundo_nome = None
            if nome_cliente:
                partes_nome = nome_cliente.strip().split()
                if len(partes_nome) >= 2:
                    primeiro_segundo_nome = f"{partes_nome[0]} {partes_nome[1]}"
                elif len(partes_nome) == 1:
                    primeiro_segundo_nome = partes_nome[0]
            
            # Definir footer e pix_name: usar nome do provedor se disponível, senão usar primeiro e segundo nome do cliente
            footer = nome_provedor if nome_provedor else (primeiro_segundo_nome if primeiro_segundo_nome else "NioChat")
            pix_name = nome_provedor if nome_provedor else (primeiro_segundo_nome if primeiro_segundo_nome else "NioChat")
            
            # Montar texto da fatura conforme exemplo
            texto_fatura = f"Vencimento: {vencimento_formatado}\nValor: {valor_formatado}\n\nEscolha como deseja pagar:"
            
            # Preparar dados para enviar fatura no formato invoice da Uazapi
            title = f"Fatura {fatura_id}"
            item_name = f"Fatura {fatura_id}"
            amount = float(valor) if valor else 0.0
            
            # Determinar pix_key, pix_type, pix_name e boleto_code
            # RESPEITAR tipo_pagamento: 'pix', 'boleto' ou 'ambos'/'todos'/'pix_boleto'
            pix_key = None
            pix_type = None
            boleto_code = None
            
            # Determinar se mostra PIX/Boleto (Normalizar tipo_pagamento)
            tp = str(tipo_pagamento).lower().strip()
            show_pix = any(opt in tp for opt in ['pix', 'ambos', 'ambas', 'todos'])
            show_boleto = any(opt in tp for opt in ['boleto', 'ambos', 'ambas', 'todos'])

            if codigo_pix and show_pix:
                pix_key = codigo_pix
                pix_type = "EVP"  # Tipo padrão para chave PIX
            
            if linha_digitavel and show_boleto:
                boleto_code = linha_digitavel
            
            # Enviar fatura usando o formato invoice da Uazapi
            resultado = uazapi.enviar_fatura(
                numero=numero_whatsapp,
                title=title,
                text=texto_fatura,
                footer=footer,
                invoice_number=str(fatura_id),
                item_name=item_name,
                amount=amount,
                pix_key=pix_key,
                pix_type=pix_type,
                pix_name=pix_name,
                boleto_code=boleto_code,
                delay=300,
                instance_id=instance_id
            )

            # region agent log
            _debug_log(
                "uazapi_send_result",
                {
                    "provedor_id": getattr(provedor, "id", None),
                    "send_success": bool(resultado),
                },
                location="fatura_service.py:enviar_fatura_uazapi:result",
                hypothesis_id="H7",
            )
            # endregion
            
            if not resultado:
                erro_msg = f"Falha ao enviar fatura via invoice Uazapi (provedor {provedor.id})"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # SALVAR MENSAGEM DA FATURA NO BANCO (opcional, não crítico)
            # Nota: Salvar mensagem no banco pode falhar em contexto assíncrono, mas não é crítico
            if conversation:
                try:
                    from conversations.models import Message
                    from django.db import transaction
                    # Montar conteúdo da mensagem para salvar no banco
                    conteudo_mensagem = f"{title}\n\n{texto_fatura}\n\n{footer}"
                    
                    # Usar transaction.atomic para garantir que funciona mesmo em contexto assíncrono
                    def criar_mensagem_sync():
                        with transaction.atomic():
                            Message.objects.create(
                                conversation=conversation,
                                message_type='text',
                                content=conteudo_mensagem,
                                is_from_customer=False,
                                additional_attributes={
                                    'invoice_number': str(fatura_id),
                                    'amount': amount,
                                    'vencimento': vencimento_formatado,
                                    'has_pix': bool(pix_key),
                                    'has_boleto': bool(boleto_code),
                                    'is_invoice': True
                                },
                                created_at=timezone.now()
                            )
                    
                    # Tentar executar de forma síncrona primeiro
                    try:
                        criar_mensagem_sync()
                    except Exception as sync_error:
                        # Se falhar, pode ser contexto assíncrono - pular salvamento (não é crítico)
                        pass
                except Exception as e:
                    pass
            
            return {"success": True, "message": "Fatura enviada com sucesso"}
            
        except Exception as e:
            provedor_id = getattr(provedor, "id", "unknown")
            erro_msg = f"Erro ao enviar fatura via Uazapi (provedor {provedor_id}): {str(e)}"
            logger.exception(f"[FATURA] {erro_msg}")
            return {"success": False, "error": erro_msg}

    def _enviar_fatura_whatsapp_oficial(self, provedor, conversation, dados_fatura: Dict[str, Any], tipo_pagamento: str = 'pix') -> Dict[str, Any]:
        """
        Envia fatura via WhatsApp Cloud API usando order_details com payment_settings (PIX e Boleto).
        
        Args:
            provedor: Objeto Provedor com configurações
            conversation: Objeto Conversation para obter número do destinatário
            dados_fatura: Dados da fatura do SGP
            tipo_pagamento: 'pix' ou 'boleto' - usado apenas para determinar qual formato mostrar primeiro
            
        Returns:
            Dict com success (bool) e error/message (str)
        """
        try:
            from core.models import Canal
            from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
            import requests
            
            provedor_id = getattr(provedor, "id", "unknown")
            
            # Buscar canal WhatsApp Oficial do provedor
            canal = Canal.objects.filter(
                provedor=provedor,
                tipo="whatsapp_oficial",
                ativo=True
            ).first()
            
            if not canal:
                erro_msg = f"Canal WhatsApp Oficial não encontrado para provedor {provedor_id}"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            if not canal.token:
                erro_msg = f"Token do canal WhatsApp Oficial não configurado para provedor {provedor_id}"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            if not canal.phone_number_id:
                erro_msg = f"Phone Number ID do canal WhatsApp Oficial não configurado para provedor {provedor_id}"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Verificar dados da fatura
            if not dados_fatura.get('links'):
                erro_msg = f"Dados da fatura não contêm links de pagamento (provedor {provedor_id})"
                logger.warning(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Pegar primeira fatura
            fatura = dados_fatura['links'][0]
            fatura_id = fatura.get('fatura', 'N/A')
            codigo_pix = fatura.get('codigopix')
            linha_digitavel = fatura.get('linhadigitavel')
            vencimento = fatura.get('vencimento_original') or fatura.get('vencimento', 'N/A')
            valor = float(fatura.get('valor', 0))
            link_fatura = fatura.get('link') or fatura.get('link_cobranca')
            logger.info(f"[FATURA] link_fatura extraído (prioridade link): {link_fatura}")
            
            # Formatar vencimento para dd/mm/yyyy
            vencimento_formatado = vencimento
            if vencimento and '-' in str(vencimento):
                try:
                    vencimento_date = datetime.strptime(vencimento, "%Y-%m-%d")
                    vencimento_formatado = vencimento_date.strftime("%d.%m.%Y")
                except:
                    pass
            
            # Obter número do destinatário da conversa
            if not conversation or not hasattr(conversation, 'contact') or not conversation.contact:
                erro_msg = f"Conversa não possui contato válido para envio (provedor {provedor_id})"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            recipient_number = conversation.contact.phone
            recipient_number = ''.join(filter(str.isdigit, recipient_number))
            
            # Garantir que comece com código do país (se não tiver, assumir Brasil 55)
            if not recipient_number.startswith('55') and len(recipient_number) <= 11:
                recipient_number = '55' + recipient_number
            
            # Obter nome do provedor para merchant_name
            nome_provedor = provedor.nome if provedor and provedor.nome else "NioChat"
            
            # Converter valor para centavos (valor * 100)
            valor_centavos = int(round(valor * 100))
            
            # Determinar se mostra PIX/Boleto (Normalizar tipo_pagamento)
            tp = str(tipo_pagamento).lower().strip()
            # Se for 'ambos', 'ambas' ou 'todos', mostra os dois.
            # Se for um valor específico, mostra só aquele.
            # Caso contrário (ex: vazio), fallback para pix.
            show_pix = any(opt in tp for opt in ['pix', 'ambos', 'ambas', 'todos']) or tp == ''
            show_boleto = any(opt in tp for opt in ['boleto', 'ambos', 'ambas', 'todos'])
            
            logger.info(f"[FATURA] Normalização: input='{tipo_pagamento}' -> tp='{tp}' | show_pix={show_pix} | show_boleto={show_boleto}")
            
            # Montar payment_settings
            payment_settings = []
            
            # Adicionar PIX se disponível e solicitado
            if codigo_pix and show_pix:
                # Tentar extrair informações do código PIX
                pix_code = codigo_pix
                pix_key = None
                pix_key_type = None
                
                # Tentar detectar tipo de chave PIX pelo código
                # Se for QR Code completo (formato EMV), tentar extrair chave ou omitir
                # Se for chave direta (CPF, CNPJ, email, telefone), detectar tipo
                if codigo_pix.startswith('000201'):
                    # QR Code completo (formato EMV)
                    # Tentar extrair chave PIX do QR Code EMV
                    # Formato EMV: ...26XX... onde XX é o tamanho e depois vem a chave
                    # Ou pode estar em outros campos do EMV
                    # Por enquanto, vamos tentar encontrar padrões conhecidos
                    try:
                        # Tentar encontrar chave no QR Code (procura por padrões de CPF, CNPJ, email, etc)
                        import re
                        # Procurar por CPF (11 dígitos) ou CNPJ (14 dígitos) no código
                        # Validar CPF (formato XXX.XXX.XXX-XX ou 11 dígitos seguidos, não no início do QR Code)
                        cpf_match = None
                        for match in re.finditer(r'\b\d{11}\b', codigo_pix):
                            # Verificar se não está no início do QR Code (primeiros 10 caracteres)
                            if match.start() > 10:
                                # Validar que é um CPF válido (não todos iguais)
                                cpf_candidate = match.group()
                                if len(set(cpf_candidate)) > 1:  # Não são todos dígitos iguais
                                    cpf_match = match
                                    break
                        
                        # Validar CNPJ (14 dígitos seguidos, não no início do QR Code)
                        cnpj_match = None
                        for match in re.finditer(r'\b\d{14}\b', codigo_pix):
                            if match.start() > 10:
                                # Validar que é um CNPJ válido (não todos iguais)
                                cnpj_candidate = match.group()
                                if len(set(cnpj_candidate)) > 1:
                                    cnpj_match = match
                                    break
                        
                        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', codigo_pix)
                        
                        # Validar telefone (formato +55XX... ou 55XX... com 10-11 dígitos após código país)
                        # Não capturar números que começam com 0002 (parte do QR Code EMV)
                        phone_match = None
                        # Procurar por padrão de telefone brasileiro: +55 ou 55 seguido de 10-11 dígitos
                        phone_patterns = [
                            r'\+55\d{10,11}',  # +55 seguido de 10-11 dígitos
                            r'\b55\d{10,11}\b',  # 55 seguido de 10-11 dígitos (com limites de palavra)
                        ]
                        for pattern in phone_patterns:
                            for match in re.finditer(pattern, codigo_pix):
                                # Verificar que não está no início do QR Code e não começa com 0002
                                if match.start() > 10 and not match.group().startswith('0002'):
                                    phone_match = match
                                    break
                            if phone_match:
                                break
                        
                        if cpf_match:
                            pix_key = cpf_match.group()
                            pix_key_type = "CPF"
                        elif cnpj_match:
                            pix_key = cnpj_match.group()
                            pix_key_type = "CNPJ"
                        elif email_match:
                            pix_key = email_match.group()
                            pix_key_type = "EMAIL"
                        elif phone_match:
                            pix_key = phone_match.group().lstrip('+')
                            pix_key_type = "PHONE"
                        else:
                            # Não conseguiu extrair chave - usar EVP genérico baseado no código
                            # Gerar um hash ou usar parte do código como identificador
                            # Mas EVP precisa ser um UUID ou formato específico
                            # Se não conseguirmos, vamos omitir key e key_type (se a API permitir)
                            # Ou usar um formato UUID gerado
                            import uuid
                            # Usar hash do código para gerar UUID determinístico
                            pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50]))
                            pix_key_type = "EVP"
                    except Exception:
                        # Se falhar, tentar gerar UUID baseado no código
                        import uuid
                        pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50]))
                        pix_key_type = "EVP"
                elif len(codigo_pix) == 11 and codigo_pix.isdigit():
                    # CPF
                    pix_key = codigo_pix
                    pix_key_type = "CPF"
                elif len(codigo_pix) == 14 and codigo_pix.isdigit():
                    # CNPJ
                    pix_key = codigo_pix
                    pix_key_type = "CNPJ"
                elif '@' in codigo_pix:
                    # EMAIL
                    pix_key = codigo_pix
                    pix_key_type = "EMAIL"
                elif codigo_pix.startswith('+55') or (codigo_pix.startswith('55') and len(codigo_pix) >= 12):
                    # PHONE (Brasil)
                    pix_key = codigo_pix.lstrip('+')
                    pix_key_type = "PHONE"
                elif len(codigo_pix) == 36 and '-' in codigo_pix:
                    # UUID (chave aleatória EVP)
                    pix_key = codigo_pix
                    pix_key_type = "EVP"
                else:
                    # Outros formatos - assumir que pode ser chave ou código
                    # Se for muito longo (>100 chars), provavelmente é QR Code completo
                    if len(codigo_pix) > 100:
                        # Tratar como QR Code e tentar extrair chave
                        import re
                        cpf_match = re.search(r'\b\d{11}\b', codigo_pix)
                        cnpj_match = re.search(r'\b\d{14}\b', codigo_pix)
                        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', codigo_pix)
                        
                        if cpf_match:
                            pix_key = cpf_match.group()
                            pix_key_type = "CPF"
                        elif cnpj_match:
                            pix_key = cnpj_match.group()
                            pix_key_type = "CNPJ"
                        elif email_match:
                            pix_key = email_match.group()
                            pix_key_type = "EMAIL"
                        else:
                            import uuid
                            pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50]))
                            pix_key_type = "EVP"
                    else:
                        # Assume que é chave direta
                        pix_key = codigo_pix[:50]
                        pix_key_type = "EVP"
                
                # Montar objeto pix_dynamic_code
                pix_dynamic_code = {
                    "code": pix_code,  # Código PIX completo (QR Code)
                    "merchant_name": nome_provedor
                }
                
                # Adicionar key e key_type apenas se encontrados
                if pix_key and pix_key_type:
                    pix_dynamic_code["key"] = pix_key
                    pix_dynamic_code["key_type"] = pix_key_type
                
                # Adicionar PIX aos payment_settings
                pix_payment = {
                    "type": "pix_dynamic_code",
                    "pix_dynamic_code": pix_dynamic_code
                }
                payment_settings.append(pix_payment)
            
            # Adicionar Boleto se disponível e solicitado
            if linha_digitavel and show_boleto:
                # Remover espaços e caracteres especiais, manter apenas números
                linha_limpa = ''.join(filter(str.isdigit, linha_digitavel))
                
                # WhatsApp requer no máximo 48 caracteres na linha digitável
                if len(linha_limpa) > 48:
                    logger.warning(f"[FATURA] Linha digitável muito longa ({len(linha_limpa)} chars), truncando para 48 chars")
                    linha_limpa = linha_limpa[:48]
                
                if len(linha_limpa) >= 47:  # Boleto padrão tem 47 dígitos
                    boleto_payment = {
                        "type": "boleto",
                        "boleto": {
                            "digitable_line": linha_limpa
                        }
                    }
                    payment_settings.append(boleto_payment)
                else:
                    logger.warning(f"[FATURA] Linha digitável inválida (muito curta: {len(linha_limpa)} chars) para fatura {fatura_id}")
            
            # Se não houver nem PIX nem Boleto, retornar erro
            if not payment_settings:
                erro_msg = f"Nenhum método de pagamento disponível (PIX ou Boleto) para a fatura (provedor {provedor_id})"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Obter nome do cliente para a mensagem
            nome_cliente = "Cliente"
            try:
                if conversation and hasattr(conversation, 'contact') and conversation.contact:
                    nome_cliente = conversation.contact.name.split()[0].upper()
            except:
                pass

            # Montar texto do body personalizado conforme imagem
            valor_formatado = f"R$ {valor:.2f}".replace('.', ',')
            
            # Layout Profissional (Texto antes + Card Meta) para TODOS os métodos
            intro_text = (
                "Aqui estão os dados para pagamento de sua fatura: 👇\n\n"
                f"📅 Vencimento: {vencimento_formatado}\n"
                f"💰 Valor: {valor_formatado}"
            )
            
            # Enviar mensagem introdutória primeiro
            intro_payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_number,
                "type": "text",
                "text": {"body": intro_text}
            }
            
            url_intro = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
            headers_intro = {
                "Authorization": f"Bearer {canal.token}",
                "Content-Type": "application/json"
            }
            
            try:
                logger.info(f"[FATURA] Enviando introdução para {recipient_number} (TP={tp})")
                requests.post(url_intro, json=intro_payload, headers=headers_intro, timeout=10)
            except Exception as e:
                logger.warning(f"[FATURA] Falha ao enviar mensagem de introdução: {e}")

            # Definir Texto do Body e Instruções conforme o método
            if show_pix and show_boleto:
                body_text = (
                    "Escolha como deseja pagar: 👇\n\n"
                    "1. Copie o código PIX;\n"
                    "2. Abra o aplicativo do seu banco;\n"
                    "3. Cole o código e finalize o pagamento\n\n"
                    "Toque abaixo para copiar o código:"
                )
            elif show_pix:
                body_text = (
                    "Pagar com PIX: 👇\n\n"
                    "1. Copie o código PIX abaixo;\n"
                    "2. Abra o aplicativo do seu banco;\n"
                    "3. Cole o código e finalize o pagamento."
                )
            elif show_boleto:
                body_text = (
                    "Pagar com Boleto: 👇\n\n"
                    "1. Copie o código do boleto abaixo;\n"
                    "2. Use o aplicativo do seu banco para pagar."
                )
            else:
                # Fallback genérico
                body_text = "Selecione a forma de pagamento abaixo para visualizar os dados:"
            
            # Montar payload order_details
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_number,
                "type": "interactive",
                "interactive": {
                    "type": "order_details",
                    "header": {
                        "type": "document",
                        "document": {
                            "link": link_fatura,
                            "filename": "Fatura.pdf"
                        }
                        } if (link_fatura and show_boleto) else None,
                    "body": {
                        "text": body_text
                    },
                    "footer": {
                        "text": nome_provedor
                    },
                    "action": {
                        "name": "review_and_pay",
                        "parameters": {
                            "reference_id": str(fatura_id),
                            "type": "digital-goods",
                            "payment_type": "br",
                            "currency": "BRL",
                            "total_amount": {
                                "value": valor_centavos,
                                "offset": 100
                            },
                            "order": {
                                "status": "pending",
                                "tax": {
                                    "value": 0,
                                    "offset": 100,
                                    "description": "Impostos"
                                },
                                "items": [
                                    {
                                        "retailer_id": str(fatura_id),
                                        "name": str(fatura_id),
                                        "amount": {
                                            "value": valor_centavos,
                                            "offset": 100
                                        },
                                        "quantity": 1
                                    }
                                ],
                                "subtotal": {
                                    "value": valor_centavos,
                                    "offset": 100
                                }
                            }
                        }
                    }
                }
            }
            
            # Adicionar payment_settings se houver
            if payment_settings:
                payload["interactive"]["action"]["parameters"]["payment_settings"] = payment_settings
            
            # Enviar via WhatsApp Cloud API
            url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {canal.token}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"[FATURA] Enviando fatura {fatura_id} via WhatsApp Oficial para {recipient_number} (provedor {provedor_id})")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code != 200:
                erro_msg = f"Erro ao enviar fatura via WhatsApp Oficial (provedor {provedor_id}): {response.status_code} - {response.text}"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            response_data = response.json()
            
            # Verificar se houve erro na resposta
            if response_data.get('error'):
                erro_msg = f"Erro da API WhatsApp ao enviar fatura (provedor {provedor_id}): {response_data.get('error', {}).get('message', 'Erro desconhecido')}"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Salvar mensagem no banco (opcional, não crítico)
            if conversation:
                try:
                    from conversations.models import Message
                    from django.db import transaction
                    
                    def criar_mensagem_sync():
                        with transaction.atomic():
                            Message.objects.create(
                                conversation=conversation,
                                message_type='interactive',
                                content=body_text,
                                is_from_customer=False,
                                additional_attributes={
                                    'invoice_number': str(fatura_id),
                                    'amount': valor,
                                    'vencimento': vencimento_formatado,
                                    'has_pix': bool(codigo_pix),
                                    'has_boleto': bool(linha_digitavel),
                                    'is_invoice': True,
                                    'payment_type': 'whatsapp_oficial',
                                    'whatsapp_message_id': response_data.get('messages', [{}])[0].get('id') if response_data.get('messages') else None
                                },
                                created_at=timezone.now()
                            )
                    
                    try:
                        criar_mensagem_sync()
                    except Exception:
                        pass  # Não crítico se falhar
                except Exception:
                    pass  # Não crítico se falhar
            
            logger.info(f"[FATURA] Fatura {fatura_id} enviada com sucesso via WhatsApp Oficial (provedor {provedor_id})")
            return {"success": True, "message": "Fatura enviada via WhatsApp Oficial com sucesso"}
            
        except Exception as e:
            provedor_id = getattr(provedor, "id", "unknown")
            erro_msg = f"Erro crítico ao enviar fatura via WhatsApp Oficial (provedor {provedor_id}): {str(e)}"
            logger.exception(f"[FATURA] {erro_msg}")
            return {"success": False, "error": erro_msg}

    def enviar_formato_adicional(self, provedor, numero_whatsapp: str, dados_fatura: Dict[str, Any], formato_solicitado: str, conversation=None) -> bool:
        """
        Envia formato adicional de pagamento (PIX ou Boleto) quando cliente pede depois
        
        Args:
            provedor: Objeto Provedor com configurações
            numero_whatsapp: Número do WhatsApp do cliente
            dados_fatura: Dados da fatura do SGP
            formato_solicitado: 'pix' ou 'boleto' - o formato que o cliente pediu adicionalmente
            conversation: Objeto Conversation para salvar mensagens no banco
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            from .uazapi_client import UazapiClient
            try:
                from .qr_code_service import qr_code_service
            except ImportError as e:
                return {"success": False, "error": "Módulo qrcode não está instalado. Por favor, instale com: pip install qrcode[pil]"}
            
            # Obter configurações do Uazapi
            integracao = provedor.integracoes_externas or {}
            uazapi_url = integracao.get('whatsapp_url')
            uazapi_token = integracao.get('whatsapp_token')
            
            if not all([uazapi_url, uazapi_token]):
                return {"success": False, "error": "Configurações do Uazapi não encontradas"}
            
            # Criar cliente Uazapi
            uazapi = UazapiClient(base_url=uazapi_url, token=uazapi_token)
            
            if not dados_fatura.get('links'):
                return {"success": False, "error": "Dados da fatura não contêm links de pagamento"}
            
            # Pegar primeira fatura
            fatura = dados_fatura['links'][0]
            
            if formato_solicitado.lower() == 'pix':
                # Enviar apenas PIX adicional
                codigo_pix = fatura.get('codigopix')
                
                if not codigo_pix:
                    return {"success": False, "error": "Código PIX não disponível para esta fatura"}
                
                # 1. Enviar QR Code PIX
                qr_code_bytes = qr_code_service.gerar_qr_code_pix_bytes(codigo_pix)
                
                if qr_code_bytes:
                    resultado_qr = uazapi.enviar_imagem(
                        numero=numero_whatsapp,
                        imagem_bytes=qr_code_bytes,
                        legenda="QR Code PIX para pagamento"
                    )
                    
                    if not resultado_qr:
                        return {"success": False, "error": "Falha ao enviar QR code PIX adicional"}
                    
                    # SALVAR MENSAGEM DO QR CODE NO BANCO
                    if conversation:
                        try:
                            from conversations.models import Message
                            Message.objects.create(
                                conversation=conversation,
                                message_type='image',
                                content="QR Code PIX para pagamento",
                                is_from_customer=False,
                                file_url=f"/api/media/qr_code_pix_{conversation.id}.png",
                                created_at=timezone.now()
                            )
                            pass
                        except Exception as e:
                            pass
                else:
                    return {"success": False, "error": "QR code PIX não pôde ser gerado"}
                
                # 2. Enviar botão "Copiar Chave PIX"
                # Tentar formato alternativo com \n em vez de |
                choices = [f"Copiar Chave PIX\ncopy:{codigo_pix}"]
                texto_botoes = "Clique para copiar a chave PIX:"
                footer_text = "Copie e cole o código no aplicativo do seu banco."
                
                resultado_botoes = uazapi.enviar_menu(
                    numero=numero_whatsapp,
                    tipo="button",
                    texto=texto_botoes,
                    choices=choices,
                    footer_text=footer_text
                )
                
                if not resultado_botoes:
                    # Retornar sucesso parcial - QR code foi enviado
                    return {"success": True, "message": "QR Code PIX enviado com sucesso (botões não enviados)"}
                
                # SALVAR MENSAGEM DOS BOTÕES NO BANCO
                if conversation:
                    try:
                        from conversations.models import Message
                        botao_texto = f"{texto_botoes}\n\n🔘 Copiar Chave PIX\n\n{footer_text}"
                        
                        Message.objects.create(
                            conversation=conversation,
                            message_type='text',
                            content=botao_texto,
                            is_from_customer=False,
                            additional_attributes={
                                'has_buttons': True,
                                'button_choices': choices,
                                'is_interactive': True,
                                'is_invoice': True,
                                'invoice_number': str(fatura.get('fatura')),
                                'amount': fatura.get('valor'),
                                'vencimento': fatura.get('vencimento'),
                                'payment_type': 'pix',
                                'pix_code': fatura.get('codigopix')
                            },
                            created_at=timezone.now()
                        )
                        
                        # BROADCAST PARA O FRONTEND (REAL-TIME)
                        try:
                            from chat.utils import broadcast_message
                            broadcast_message(msg)
                        except Exception as e:
                            logger.error(f"[FATURA] Erro ao transmitir broadcast PIX: {e}")
                        pass
                    except Exception as e:
                        pass
                
                return {"success": True, "message": "QR Code PIX e botões enviados com sucesso"}
                    
            elif formato_solicitado.lower() == 'boleto':
                # Enviar apenas Boleto adicional
                linha_digitavel = fatura.get('linhadigitavel')
                link_boleto = fatura.get('link')
                
                if not linha_digitavel or not link_boleto:
                    return {"success": False, "error": "Linha digitável ou link do boleto não disponível"}
                
                # 1. Enviar PDF do boleto
                resultado_pdf = uazapi.enviar_documento(
                    numero=numero_whatsapp,
                    documento_url=link_boleto,
                    nome_arquivo=f"boleto_{fatura.get('fatura', 'N/A')}.pdf",
                    legenda="Boleto Bancário em PDF"
                )
                
                if not resultado_pdf:
                    return {"success": False, "error": "Falha ao enviar PDF do boleto adicional"}
                
                # SALVAR MENSAGEM DO PDF NO BANCO
                if conversation:
                    try:
                        from conversations.models import Message
                        Message.objects.create(
                            conversation=conversation,
                            message_type='document',
                            content="📄 Boleto Bancário em PDF",
                            is_from_customer=False,
                            file_url=link_boleto,
                            created_at=timezone.now()
                        )
                        pass
                    except Exception as e:
                        pass
                
                # 2. Enviar botão "Copiar Linha Digitável"
                choices = [f"Copiar Linha Digitável|copy:{linha_digitavel}"]
                texto_botoes = "Clique no botão para copiar a linha digitável:"
                footer_text = "Clique para copiar a linha digitável"
                
                resultado_botoes = uazapi.enviar_menu(
                    numero=numero_whatsapp,
                    tipo="button",
                    texto=texto_botoes,
                    choices=choices,
                    footer_text=footer_text
                )
                
                if resultado_botoes:
                    # SALVAR MENSAGEM DOS BOTÕES NO BANCO
                    if conversation:
                        try:
                            from conversations.models import Message
                            botao_texto = f"{texto_botoes}\n\n🔘 Copiar Linha Digitável\n\n{footer_text}"
                            
                            Message.objects.create(
                                conversation=conversation,
                                message_type='text',
                                content=botao_texto,
                                is_from_customer=False,
                                additional_attributes={
                                    'has_buttons': True,
                                    'button_choices': choices,
                                    'is_interactive': True,
                                    'is_invoice': True,
                                    'invoice_number': str(fatura.get('fatura')),
                                    'amount': fatura.get('valor'),
                                    'vencimento': fatura.get('vencimento'),
                                    'payment_type': 'boleto',
                                    'line_code': fatura.get('linhadigitavel'),
                                    'document_url': fatura.get('link')
                                },
                                created_at=timezone.now()
                            )
                            
                            # BROADCAST PARA O FRONTEND (REAL-TIME)
                            try:
                                from chat.utils import broadcast_message
                                broadcast_message(msg)
                            except Exception as e:
                                logger.error(f"[FATURA] Erro ao transmitir broadcast Boleto: {e}")
                            pass
                        except Exception as e:
                            pass
                    
                    return {"success": True, "message": "Boleto adicional enviado com sucesso"}
                else:
                    return {"success": False, "error": "Falha ao enviar botões boleto adicionais"}
            else:
                return {"success": False, "error": f"Formato solicitado inválido: {formato_solicitado}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

# Instância global do serviço
fatura_service = FaturaService()
