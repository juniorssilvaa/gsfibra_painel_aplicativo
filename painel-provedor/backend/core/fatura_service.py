"""
Serviço para buscar faturas via endpoint SGP e enviar via Uazapi
"""

import requests
import logging
import os
import re
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

    def _codigo_pix_limpo(self, value: Any) -> str:
        """Normaliza código PIX; string vazia / None viram ''."""
        if value is None:
            return ''
        code = str(value).strip()
        return code if code else ''

    def _parse_money(self, value: Any) -> float:
        """Converte valor monetário do SGP para float com segurança."""
        if value is None or value == '':
            return 0.0
        try:
            return float(str(value).replace(',', '.').strip())
        except (TypeError, ValueError):
            return 0.0

    def _format_money_br(self, value: float) -> str:
        return f"R$ {float(value):.2f}".replace('.', ',')

    def _resolver_valores_fatura(self, fatura: Dict[str, Any]) -> Dict[str, float]:
        """
        Valor a cobrar = 'valor' do SGP (já com multa/juros quando em atraso).
        Fallback: valor_original / valor_total.
        """
        valor_atual = self._parse_money(
            fatura.get('valor') if fatura.get('valor') not in (None, '') else None
        )
        valor_original = self._parse_money(fatura.get('valor_original'))
        if valor_atual <= 0:
            valor_atual = self._parse_money(
                fatura.get('valor_total') or fatura.get('valor_original') or fatura.get('desconto_vencimento')
            )
        if valor_original <= 0:
            valor_original = valor_atual
        multa = self._parse_money(fatura.get('multa'))
        juros = self._parse_money(fatura.get('juros'))
        tem_atraso = (multa > 0 or juros > 0) or (
            valor_original > 0 and valor_atual > valor_original + 0.009
        )
        return {
            'valor': valor_atual,
            'valor_original': valor_original,
            'multa': multa,
            'juros': juros,
            'tem_atraso': 1.0 if tem_atraso else 0.0,
        }

    def _texto_valores_fatura(self, valores: Dict[str, float], *, bullet: bool = True) -> str:
        """Texto de valor / atraso para intro e body do card (sem emojis)."""
        valor = valores.get('valor', 0.0) or 0.0
        valor_original = valores.get('valor_original', 0.0) or 0.0
        multa = valores.get('multa', 0.0) or 0.0
        juros = valores.get('juros', 0.0) or 0.0
        tem_atraso = bool(valores.get('tem_atraso'))
        money = self._format_money_br
        if not tem_atraso:
            return f"*Valor:* {money(valor)}" if bullet else f"Valor: {money(valor)}"
        if bullet:
            linhas = [f"*Valor original:* {money(valor_original)}"]
            if multa > 0:
                linhas.append(f"*Multa:* {money(multa)}")
            if juros > 0:
                linhas.append(f"*Juros:* {money(juros)}")
            linhas.append(f"*Valor atualizado:* {money(valor)}")
        else:
            linhas = [f"Valor original: {money(valor_original)}"]
            if multa > 0:
                linhas.append(f"Multa: {money(multa)}")
            if juros > 0:
                linhas.append(f"Juros: {money(juros)}")
            linhas.append(f"Valor atualizado: {money(valor)}")
        return '\n'.join(linhas)

    DEFAULT_INVOICE_INTRO_TEMPLATE = (
        "*Dados para pagamento*\n\n"
        "*Vencimento:* {{vencimento}}\n"
        "{{valores_texto}}"
    )

    DEFAULT_INVOICE_CARD_BODY_TEMPLATE = (
        "*Vencimento:* {{vencimento}}\n"
        "{{valores_texto}}\n\n"
        "{{instrucoes}}"
    )

    def _instrucoes_pagamento_card(self, tipo_pagamento: str = 'pix') -> str:
        """Instruções padrão do card Meta conforme método de pagamento."""
        tp = str(tipo_pagamento or '').lower().strip()
        show_pix = any(opt in tp for opt in ['pix', 'ambos', 'ambas', 'todos']) or tp == ''
        show_boleto = any(opt in tp for opt in ['boleto', 'ambos', 'ambas', 'todos'])
        if show_pix and show_boleto:
            return (
                "*Como pagar*\n\n"
                "1. Copie o código PIX ou do boleto;\n"
                "2. Abra o aplicativo do seu banco;\n"
                "3. Cole o código e finalize o pagamento.\n\n"
                "Toque abaixo para copiar:"
            )
        if show_boleto and not show_pix:
            return (
                "*Pagamento via boleto*\n\n"
                "1. Copie o código do boleto abaixo;\n"
                "2. Use o aplicativo do seu banco para pagar."
            )
        return (
            "*Pagamento via PIX*\n\n"
            "1. Copie o código PIX abaixo;\n"
            "2. Abra o aplicativo do seu banco;\n"
            "3. Cole o código e finalize o pagamento."
        )

    def _body_card_fatura(
        self,
        vencimento_formatado: str,
        valores: Dict[str, float],
        *,
        provedor=None,
        fatura_id: Any = '',
        nome_cliente: str = '',
        nome_provedor: str = '',
        tipo_pagamento: str = 'pix',
    ) -> str:
        """
        Texto do body do card Meta (order_details).
        Usa invoice_intro_message_template do provedor, se preenchido.
        """
        template = ''
        if provedor is not None:
            template = (getattr(provedor, 'invoice_intro_message_template', None) or '').strip()
        if not template:
            template = self.DEFAULT_INVOICE_CARD_BODY_TEMPLATE
        ctx = self._contexto_intro_fatura(
            vencimento_formatado=vencimento_formatado,
            valores=valores,
            fatura_id=fatura_id,
            nome_cliente=nome_cliente,
            nome_provedor=nome_provedor,
            bullet=True,
        )
        ctx['instrucoes'] = self._instrucoes_pagamento_card(tipo_pagamento)
        return self._render_invoice_template(template, ctx).strip()

    def _render_invoice_template(self, template: str, context: Dict[str, Any]) -> str:
        """Substitui {{variavel}} no template da fatura (case-insensitive nas chaves)."""
        msg = template or ''
        normalized = {str(k).lower(): '' if v is None else str(v) for k, v in (context or {}).items()}

        def _repl(match):
            key = (match.group(1) or '').strip().lower()
            return normalized.get(key, match.group(0))

        return re.sub(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', _repl, msg)

    def _tem_template_intro_fatura(self, provedor) -> bool:
        return bool((getattr(provedor, 'invoice_intro_message_template', None) or '').strip())

    def _contexto_intro_fatura(
        self,
        *,
        vencimento_formatado: str,
        valores: Dict[str, float],
        fatura_id: Any = '',
        nome_cliente: str = '',
        nome_provedor: str = '',
        bullet: bool = True,
    ) -> Dict[str, Any]:
        money = self._format_money_br
        valor = valores.get('valor', 0.0) or 0.0
        valor_original = valores.get('valor_original', 0.0) or 0.0
        multa = valores.get('multa', 0.0) or 0.0
        juros = valores.get('juros', 0.0) or 0.0
        return {
            'vencimento': vencimento_formatado or '',
            'valor': money(valor),
            'valor_original': money(valor_original),
            'multa': money(multa),
            'juros': money(juros),
            'valores_texto': self._texto_valores_fatura(valores, bullet=bullet),
            'fatura_id': str(fatura_id or ''),
            'nome_cliente': nome_cliente or '',
            'nome_provedor': nome_provedor or '',
        }

    def _intro_pagamento_fatura(
        self,
        vencimento_formatado: str,
        valores: Dict[str, float],
        *,
        provedor=None,
        fatura_id: Any = '',
        nome_cliente: str = '',
        nome_provedor: str = '',
        bullet: bool = True,
        tipo_pagamento: str = '',
    ) -> str:
        """
        Texto de abertura da fatura (Telegram/Instagram/Uazapi).
        No WhatsApp Oficial o texto customizado vai no card via _body_card_fatura.
        """
        template = ''
        if provedor is not None:
            template = (getattr(provedor, 'invoice_intro_message_template', None) or '').strip()
        if not template:
            template = self.DEFAULT_INVOICE_INTRO_TEMPLATE
        ctx = self._contexto_intro_fatura(
            vencimento_formatado=vencimento_formatado,
            valores=valores,
            fatura_id=fatura_id,
            nome_cliente=nome_cliente,
            nome_provedor=nome_provedor,
            bullet=bullet,
        )
        ctx['instrucoes'] = (
            self._instrucoes_pagamento_card(tipo_pagamento) if tipo_pagamento else ''
        )
        return self._render_invoice_template(template, ctx).strip()

    def _extrair_codigo_pix_resposta(self, resp: Any) -> str:
        """Extrai copia-e-cola de respostas variadas do SGP gerar_pix / fatura2via."""
        if not resp:
            return ''
        if isinstance(resp, str):
            return self._codigo_pix_limpo(resp)
        if not isinstance(resp, dict):
            return ''
        for key in (
            'codigopix',
            'codigo_pix',
            'pix_copia_cola',
            'copia_cola',
            'pix',
            'emv',
            'qrcode',
            'qr_code',
        ):
            code = self._codigo_pix_limpo(resp.get(key))
            if code:
                return code
        # Alguns SGP aninham em data/links[0]
        nested = resp.get('data') or resp.get('resultado') or {}
        if isinstance(nested, dict):
            for key in ('codigopix', 'codigo_pix', 'pix_copia_cola', 'pix'):
                code = self._codigo_pix_limpo(nested.get(key))
                if code:
                    return code
        links = resp.get('links')
        if isinstance(links, list) and links and isinstance(links[0], dict):
            return self._extrair_codigo_pix_resposta(links[0])
        return ''

    def _enriquecer_codigo_pix(self, provedor, fatura: Dict[str, Any]) -> str:
        """
        Garante codigopix na fatura. fatura2via às vezes devolve codigopix vazio;
        tenta endpoint gerar_pix do SGP.
        """
        code = self._codigo_pix_limpo(
            fatura.get('codigopix') or fatura.get('pix_copia_cola')
        )
        if code:
            fatura['codigopix'] = code
            return code

        fatura_id = fatura.get('fatura') or fatura.get('id')
        if not fatura_id or not provedor:
            return ''

        try:
            from .sgp_client import SGPClient

            integ = getattr(provedor, 'integracoes_externas', None) or {}
            sgp_url = integ.get('sgp_url')
            sgp_token = integ.get('sgp_token')
            sgp_app = integ.get('sgp_app')
            if not sgp_url or not sgp_token:
                return ''
            sgp = SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)
            resp = sgp.gerar_pix(fatura_id)
            code = self._extrair_codigo_pix_resposta(resp)
            if code:
                fatura['codigopix'] = code
                logger.info(
                    '[FATURA] codigopix obtido via gerar_pix (fatura=%s)',
                    fatura_id,
                )
                return code
            logger.warning(
                '[FATURA] gerar_pix sem código útil (fatura=%s, keys=%s)',
                fatura_id,
                list(resp.keys()) if isinstance(resp, dict) else type(resp).__name__,
            )
        except Exception as exc:
            logger.warning('[FATURA] Falha ao enriquecer PIX via gerar_pix: %s', exc)
        return ''

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

    def _fatura_esta_paga(self, fatura: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(fatura, dict):
            return False
        status = str(fatura.get("status") or fatura.get("situacao") or "").lower()
        return any(k in status for k in ("pago", "paga", "baixad", "liquid", "quitad"))

    def _fatura_esta_vencida(self, fatura: Optional[Dict[str, Any]]) -> bool:
        """SGP pode marcar título atrasado como 'aberto' e só destacar dias/vencimento."""
        if not isinstance(fatura, dict) or self._fatura_esta_paga(fatura):
            return False
        status = str(fatura.get("status") or fatura.get("situacao") or "").lower()
        if any(k in status for k in ("vencid", "atrasad", "overdue")):
            return True
        for key in ("dias", "diasatraso", "dias_atraso", "dias_vencidos"):
            raw = fatura.get(key)
            if raw is None or raw == "":
                continue
            try:
                if int(raw) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        venc = str(
            fatura.get("vencimento_original")
            or fatura.get("data_vencimento")
            or fatura.get("vencimento")
            or ""
        ).strip()
        if not venc:
            return False
        try:
            date_part = venc.split()[0][:10]
            if "-" in date_part:
                dt = datetime.strptime(date_part, "%Y-%m-%d").date()
            elif "/" in date_part:
                dt = datetime.strptime(date_part, "%d/%m/%Y").date()
            else:
                return False
            return dt < timezone.now().date()
        except Exception:
            return False

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
                if self._fatura_esta_paga(f):
                    continue
                if self._fatura_esta_vencida(f):
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
                if not self._codigo_pix_limpo(f_selecionada.get('codigopix')):
                    if f_selecionada.get('pix_copia_cola'):
                        f_selecionada['codigopix'] = f_selecionada.get('pix_copia_cola')
                    else:
                        self._enriquecer_codigo_pix(provedor, f_selecionada)
                
                f_id = f_selecionada.get('fatura') or f_selecionada.get('id')
                
                # Valor a cobrar: prioriza 'valor' do SGP (já inclui multa/juros se houver)
                valores = self._resolver_valores_fatura(f_selecionada)
                valor = valores['valor']
                f_selecionada['valor'] = valor
                f_selecionada['valor_original'] = valores['valor_original']
                f_selecionada['multa'] = valores['multa']
                f_selecionada['juros'] = valores['juros']
                
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
                    'valor_original': valores['valor_original'],
                    'multa': valores['multa'],
                    'juros': valores['juros'],
                    'vencimento': venc_exibicao,
                    'pix_copia_cola': f_selecionada.get('codigopix'),
                    'mensagem': (
                        f"💳 *Sua fatura {tipo_display}:*\n\n"
                        f"Fatura ID: {f_id}\n"
                        f"Vencimento: {venc_exibicao}\n"
                        f"{self._texto_valores_fatura(valores)}\n\n"
                        f"Segue seu *QRcode PIX* para pagamento."
                    ),
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
            # Instagram — canal dedicado (template button + texto copiável; sem order_details)
            if conversation and hasattr(conversation, 'inbox') and conversation.inbox:
                if conversation.inbox.channel_type == 'instagram':
                    return self._enviar_fatura_instagram(
                        provedor, conversation, dados_fatura, tipo_pagamento
                    )
                if conversation.inbox.channel_type == 'telegram':
                    return self._enviar_fatura_telegram(
                        provedor, conversation, dados_fatura, tipo_pagamento
                    )

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
            
            # 🚨 CORREÇÃO MULTI-CANAL: Priorizar a instância real de onde o cliente enviou a mensagem
            instance_id = None
            if conversation and hasattr(conversation, 'inbox') and conversation.inbox:
                inbox_attrs = conversation.inbox.additional_attributes or {}
                instance_id = inbox_attrs.get('instance')
                
            if not instance_id:
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
            valores = self._resolver_valores_fatura(fatura)
            valor = valores['valor']
            
            # Formatar vencimento para dd/mm/yyyy
            vencimento_formatado = vencimento
            if vencimento and '-' in str(vencimento):
                try:
                    vencimento_date = datetime.strptime(vencimento, "%Y-%m-%d")
                    vencimento_formatado = vencimento_date.strftime("%d.%m.%Y")
                except:
                    pass
            
            # Formatar valor
            valor_formatado = self._format_money_br(valor) if valor else "R$ 0,00"
            
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
            
            # Montar texto da fatura (template customizado do provedor ou padrão do canal)
            if self._tem_template_intro_fatura(provedor):
                texto_fatura = self._intro_pagamento_fatura(
                    vencimento_formatado,
                    valores,
                    provedor=provedor,
                    fatura_id=fatura_id,
                    nome_cliente=nome_cliente or '',
                    nome_provedor=nome_provedor or '',
                    bullet=False,
                )
            else:
                texto_fatura = (
                    f"Vencimento: {vencimento_formatado}\n"
                    f"{self._texto_valores_fatura(valores, bullet=False)}\n\n"
                    f"Escolha como deseja pagar:"
                )
            
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
                                    'pix_code': pix_key or None,
                                    'line_code': boleto_code or None,
                                    'is_invoice': True,
                                    'payment_type': 'uazapi',
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

    def _salvar_media_conversa(self, conversation, data: bytes, filename: str) -> str:
        from django.conf import settings

        safe_name = filename.replace('/', '_').replace('\\', '_') or 'file.bin'
        dest_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conversation.id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, 'wb') as out:
            out.write(data)
        return f'/api/media/messages/{conversation.id}/{safe_name}'

    def _persistir_mensagem_fatura(
        self,
        conversation,
        content: str,
        *,
        channel: str,
        message_type: str = 'text',
        file_url: Optional[str] = None,
        extra_attrs: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not conversation:
            return
        try:
            from conversations.models import Message
            from django.db import transaction

            attrs = dict(extra_attrs or {})
            attrs.setdefault('sent_via', 'fatura_service')
            attrs.setdefault('channel', channel)

            def _create():
                with transaction.atomic():
                    Message.objects.create(
                        conversation=conversation,
                        message_type=message_type,
                        content=content or '',
                        file_url=file_url,
                        is_from_customer=False,
                        additional_attributes=attrs,
                        created_at=timezone.now(),
                    )

            _create()
        except Exception:
            pass

    def _persistir_mensagem_instagram(
        self,
        conversation,
        content: str,
        message_type: str = 'text',
        file_url: Optional[str] = None,
        extra_attrs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._persistir_mensagem_fatura(
            conversation,
            content,
            channel='instagram',
            message_type=message_type,
            file_url=file_url,
            extra_attrs=extra_attrs,
        )

    def _enviar_fatura_telegram(
        self,
        provedor,
        conversation,
        dados_fatura: Dict[str, Any],
        tipo_pagamento: str = 'pix',
    ) -> Dict[str, Any]:
        """
        Envia fatura no Telegram como mensagens de texto + mídia:
        - resumo (vencimento/valor)
        - QR Code PIX em imagem (se houver código)
        - código PIX copia-e-cola em texto
        - linha digitável em texto
        - PDF/link do boleto
        """
        try:
            from core.models import Canal
            from conversations.models import Message as ConvMessage
            from integrations.telegram_service import telegram_manager

            provedor_id = getattr(provedor, 'id', 'unknown')
            inbox = conversation.inbox if conversation else None
            if not inbox or inbox.channel_type != 'telegram':
                return {'success': False, 'error': 'Conversa não é canal Telegram'}

            canal = None
            try:
                canal = inbox.get_canal_instance()
            except Exception:
                canal = None
            if not canal or getattr(canal, 'tipo', None) != 'telegram':
                canal = Canal.objects.filter(
                    provedor=provedor, tipo='telegram', ativo=True
                ).order_by('id').first()
            if not canal:
                return {
                    'success': False,
                    'error': f'Canal Telegram não encontrado (provedor {provedor_id})',
                }

            service = telegram_manager.get_service(canal.id)
            if not service or not service.client:
                return {
                    'success': False,
                    'error': f'Serviço Telegram inativo (canal {canal.id})',
                }

            contact = conversation.contact
            if not contact:
                return {'success': False, 'error': 'Conversa sem contato'}

            chat_id = None
            last_customer = (
                ConvMessage.objects.filter(conversation=conversation, is_from_customer=True)
                .order_by('-created_at')
                .first()
            )
            if last_customer and last_customer.additional_attributes:
                chat_id = last_customer.additional_attributes.get('telegram_chat_id')
            attrs = contact.additional_attributes or {}
            if not chat_id:
                chat_id = attrs.get('telegram_chat_id') or attrs.get('telegram_user_id')
            try:
                chat_id = int(chat_id)
            except (TypeError, ValueError):
                return {'success': False, 'error': f'chat_id Telegram inválido: {chat_id}'}

            if not dados_fatura.get('links'):
                return {
                    'success': False,
                    'error': f'Dados da fatura sem links (provedor {provedor_id})',
                }

            fatura = dados_fatura['links'][0]
            fatura_id = fatura.get('fatura', 'N/A')
            codigo_pix = self._enriquecer_codigo_pix(provedor, fatura)
            linha_digitavel = self._codigo_pix_limpo(fatura.get('linhadigitavel'))
            link_boleto = fatura.get('link')
            link_cobranca = fatura.get('link_cobranca')
            link_fatura = link_boleto or link_cobranca
            link_pix_html = fatura.get('link_pix_html')
            vencimento = fatura.get('vencimento_original') or fatura.get('vencimento', 'N/A')
            valores = self._resolver_valores_fatura(fatura)
            valor = valores['valor']

            vencimento_formatado = vencimento
            if vencimento and '-' in str(vencimento):
                try:
                    vencimento_formatado = datetime.strptime(
                        vencimento, '%Y-%m-%d'
                    ).strftime('%d/%m/%Y')
                except Exception:
                    pass

            valor_formatado = self._format_money_br(valor)
            nome_provedor = provedor.nome if provedor and provedor.nome else 'NioChat'
            nome_cliente = (
                dados_fatura.get('nome_cliente')
                or getattr(contact, 'name', None)
                or ''
            )

            tp = str(tipo_pagamento or '').lower().strip()
            want_pix = any(opt in tp for opt in ['pix', 'ambos', 'ambas', 'todos']) or tp == ''
            want_boleto = any(opt in tp for opt in ['boleto', 'ambos', 'ambas', 'todos'])
            # No Telegram enviamos tudo que existir do método pedido;
            # se PIX veio vazio do SGP, ainda assim manda boleto/links disponíveis.
            send_pix = want_pix
            send_boleto = want_boleto or (want_pix and not codigo_pix)
            has_anything = bool(
                codigo_pix
                or linha_digitavel
                or (link_fatura and str(link_fatura).startswith('http'))
                or (link_pix_html and str(link_pix_html).startswith('http'))
            )
            if not has_anything:
                return {
                    'success': False,
                    'error': (
                        'Nenhum método de pagamento disponível para Telegram '
                        '(SGP sem PIX, boleto ou link nesta fatura)'
                    ),
                }

            invoice_attrs = {
                'is_invoice': True,
                'invoice_number': str(fatura_id),
                'amount': valor,
                'vencimento': str(vencimento_formatado),
                'payment_type': 'telegram',
            }

            def _send_text(content: str, extra: Optional[Dict[str, Any]] = None) -> bool:
                ok = service.run_coro(service.send_message(chat_id, content))
                if ok:
                    self._persistir_mensagem_fatura(
                        conversation,
                        content,
                        channel='telegram',
                        extra_attrs={**invoice_attrs, **(extra or {})},
                    )
                return bool(ok)

            # 1) Resumo em texto (template customizado ou padrão do canal)
            if self._tem_template_intro_fatura(provedor):
                resumo = self._intro_pagamento_fatura(
                    vencimento_formatado,
                    valores,
                    provedor=provedor,
                    fatura_id=fatura_id,
                    nome_cliente=nome_cliente or '',
                    nome_provedor=nome_provedor or '',
                    bullet=False,
                )
            else:
                resumo_lines = [
                    f'📄 Fatura {fatura_id} — {nome_provedor}',
                    '',
                ]
                if nome_cliente:
                    resumo_lines.append(f'Cliente: {nome_cliente}')
                resumo_lines.extend([
                    f'Vencimento: {vencimento_formatado}',
                    self._texto_valores_fatura(valores, bullet=False),
                    '',
                    'Seguem os dados para pagamento:',
                ])
                resumo = '\n'.join(resumo_lines)
            if not _send_text(resumo):
                return {'success': False, 'error': 'Falha ao enviar resumo da fatura no Telegram'}

            enviou_algo = False

            # 2) PIX: QR em imagem + código em texto (+ link se não houver código)
            if send_pix:
                if codigo_pix:
                    try:
                        from .qr_code_service import qr_code_service

                        qr_bytes = qr_code_service.gerar_qr_code_pix_bytes(codigo_pix)
                        if qr_bytes:
                            panel_url = self._salvar_media_conversa(
                                conversation,
                                qr_bytes,
                                f'pix_qr_{fatura_id}.png',
                            )
                            sent_qr = service.run_coro(
                                service.send_photo(
                                    chat_id,
                                    qr_bytes,
                                    caption='QR Code PIX — escaneie no app do banco',
                                    filename=f'pix_qr_{fatura_id}.png',
                                )
                            )
                            if sent_qr:
                                enviou_algo = True
                                self._persistir_mensagem_fatura(
                                    conversation,
                                    'QR Code PIX',
                                    channel='telegram',
                                    message_type='image',
                                    file_url=panel_url,
                                    extra_attrs={**invoice_attrs, 'has_pix': True},
                                )
                    except Exception as exc:
                        logger.warning('[FATURA][Telegram] Erro QR PIX: %s', exc)

                    if _send_text(
                        f'Código PIX copia e cola:\n\n{codigo_pix}',
                        {'has_pix': True, 'pix_code': codigo_pix},
                    ):
                        enviou_algo = True
                elif link_pix_html and str(link_pix_html).startswith('http'):
                    if _send_text(
                        f'Link para pagar com PIX:\n{link_pix_html}',
                        {'has_pix': True, 'pix_link': link_pix_html},
                    ):
                        enviou_algo = True
                    logger.warning(
                        '[FATURA][Telegram] PIX sem codigopix (fatura=%s); enviou link',
                        fatura_id,
                    )
                else:
                    logger.warning(
                        '[FATURA][Telegram] PIX indisponível no SGP (fatura=%s)',
                        fatura_id,
                    )

            # 3) Boleto: PDF + linha digitável em texto + links
            if send_boleto:
                if link_fatura and str(link_fatura).startswith('http'):
                    try:
                        sent_doc = service.run_coro(
                            service.send_document_url(
                                chat_id,
                                link_fatura,
                                caption=f'Boleto fatura {fatura_id}',
                                filename=f'boleto_{fatura_id}.pdf',
                            )
                        )
                        if sent_doc:
                            enviou_algo = True
                            self._persistir_mensagem_fatura(
                                conversation,
                                f'Boleto {fatura_id}',
                                channel='telegram',
                                message_type='document',
                                file_url=link_fatura,
                                extra_attrs={**invoice_attrs, 'has_boleto': True},
                            )
                        else:
                            # Fallback: link em texto se o upload do PDF falhar
                            if _send_text(
                                f'Link do boleto/PDF:\n{link_fatura}',
                                {'has_boleto': True},
                            ):
                                enviou_algo = True
                    except Exception as exc:
                        logger.warning('[FATURA][Telegram] Falha PDF boleto: %s', exc)
                        if _send_text(
                            f'Link do boleto/PDF:\n{link_fatura}',
                            {'has_boleto': True},
                        ):
                            enviou_algo = True

                if linha_digitavel:
                    if _send_text(
                        f'Linha digitável do boleto:\n\n{linha_digitavel}',
                        {'has_boleto': True, 'boleto_code': linha_digitavel},
                    ):
                        enviou_algo = True

                if (
                    link_cobranca
                    and str(link_cobranca).startswith('http')
                    and link_cobranca != link_fatura
                ):
                    if _send_text(
                        f'Link da cobrança:\n{link_cobranca}',
                        {'has_boleto': True},
                    ):
                        enviou_algo = True

            if not enviou_algo:
                return {
                    'success': False,
                    'error': 'Não foi possível enviar dados de pagamento no Telegram',
                }

            logger.info(
                '[FATURA] Fatura %s enviada via Telegram (provedor %s, pix=%s boleto=%s)',
                fatura_id,
                provedor_id,
                bool(send_pix and codigo_pix),
                bool(send_boleto and (linha_digitavel or link_fatura)),
            )
            return {'success': True, 'message': 'Fatura enviada via Telegram com sucesso'}

        except Exception as exc:
            provedor_id = getattr(provedor, 'id', 'unknown')
            logger.exception('[FATURA] Erro ao enviar fatura Telegram (provedor %s)', provedor_id)
            return {'success': False, 'error': str(exc)}

    def _enviar_fatura_instagram(
        self,
        provedor,
        conversation,
        dados_fatura: Dict[str, Any],
        tipo_pagamento: str = 'pix',
    ) -> Dict[str, Any]:
        """
        Envia fatura no Instagram: intro, QR/mídia, botões web_url e código copiável.
        A API Instagram não suporta order_details/copy nativo do WhatsApp.
        """
        try:
            from core.models import Canal
            from integrations.instagram_send import (
                send_instagram_button_template,
                send_instagram_media,
                send_instagram_text,
            )

            provedor_id = getattr(provedor, 'id', 'unknown')
            inbox = conversation.inbox if conversation else None
            if not inbox or inbox.channel_type != 'instagram':
                return {'success': False, 'error': 'Conversa não é canal Instagram'}

            canal = None
            if inbox.channel_id and inbox.channel_id != 'default':
                try:
                    canal = Canal.objects.get(
                        id=inbox.channel_id,
                        provedor=provedor,
                        tipo='instagram',
                        ativo=True,
                    )
                except (Canal.DoesNotExist, ValueError, TypeError):
                    canal = None
            if not canal:
                canal = Canal.objects.filter(
                    provedor=provedor,
                    tipo='instagram',
                    ativo=True,
                ).first()
            if not canal or not canal.token:
                return {
                    'success': False,
                    'error': f'Canal Instagram não encontrado ou sem token (provedor {provedor_id})',
                }

            contact = conversation.contact
            if not contact:
                return {'success': False, 'error': 'Conversa sem contato'}

            contact_attrs = contact.additional_attributes or {}
            recipient = contact_attrs.get('instagram_scoped_id') or contact.phone
            if not recipient:
                return {'success': False, 'error': 'Contato sem IGSID Instagram'}

            if not dados_fatura.get('links'):
                return {
                    'success': False,
                    'error': f'Dados da fatura sem links (provedor {provedor_id})',
                }

            fatura = dados_fatura['links'][0]
            fatura_id = fatura.get('fatura', 'N/A')
            codigo_pix = fatura.get('codigopix')
            linha_digitavel = fatura.get('linhadigitavel')
            link_fatura = fatura.get('link') or fatura.get('link_cobranca')
            link_pix_html = fatura.get('link_pix_html')
            vencimento = fatura.get('vencimento_original') or fatura.get('vencimento', 'N/A')
            valores = self._resolver_valores_fatura(fatura)
            valor = valores['valor']

            vencimento_formatado = vencimento
            if vencimento and '-' in str(vencimento):
                try:
                    vencimento_formatado = datetime.strptime(
                        vencimento, '%Y-%m-%d'
                    ).strftime('%d/%m/%Y')
                except Exception:
                    pass

            valor_formatado = self._format_money_br(valor)
            nome_provedor = provedor.nome if provedor and provedor.nome else 'NioChat'

            tp = str(tipo_pagamento).lower().strip()
            show_pix = any(opt in tp for opt in ['pix', 'ambos', 'ambas', 'todos']) or tp == ''
            show_boleto = any(opt in tp for opt in ['boleto', 'ambos', 'ambas', 'todos'])

            if show_pix and not codigo_pix:
                show_pix = False
            if show_boleto and not linha_digitavel and not link_fatura:
                show_boleto = False
            if not show_pix and not show_boleto:
                return {
                    'success': False,
                    'error': 'Nenhum método de pagamento disponível para Instagram',
                }

            intro = self._intro_pagamento_fatura(
                vencimento_formatado,
                valores,
                provedor=provedor,
                fatura_id=fatura_id,
                nome_provedor=nome_provedor,
            )
            ok, _, err = send_instagram_text(canal, str(recipient), intro)
            if not ok:
                return {'success': False, 'error': err or 'Falha ao enviar intro Instagram'}
            self._persistir_mensagem_instagram(
                conversation,
                intro,
                extra_attrs={'is_invoice': True, 'invoice_number': str(fatura_id)},
            )

            invoice_attrs = {
                'is_invoice': True,
                'invoice_number': str(fatura_id),
                'amount': valor,
                'vencimento': vencimento_formatado,
                'payment_type': 'instagram',
            }

            if show_pix:
                try:
                    from .qr_code_service import qr_code_service

                    qr_bytes = qr_code_service.gerar_qr_code_pix_bytes(codigo_pix)
                    if qr_bytes:
                        panel_url = self._salvar_media_conversa(
                            conversation,
                            qr_bytes,
                            f'pix_qr_{fatura_id}.png',
                        )
                        ok_qr, _, err_qr = send_instagram_media(
                            canal,
                            str(recipient),
                            'image',
                            panel_url,
                            caption='QR Code PIX',
                        )
                        if ok_qr:
                            self._persistir_mensagem_instagram(
                                conversation,
                                'QR Code PIX',
                                message_type='image',
                                file_url=panel_url,
                                extra_attrs={**invoice_attrs, 'has_pix': True},
                            )
                        else:
                            logger.warning('[FATURA][Instagram] QR PIX falhou: %s', err_qr)
                except Exception as exc:
                    logger.warning('[FATURA][Instagram] Erro ao gerar QR PIX: %s', exc)

                btn_items = []
                if link_pix_html and str(link_pix_html).startswith('http'):
                    btn_items.append({
                        'id': 'pix_page',
                        'title': 'Abrir página PIX',
                        'url': link_pix_html,
                    })
                if link_fatura and str(link_fatura).startswith('http'):
                    btn_items.append({
                        'id': 'cobranca',
                        'title': 'Ver cobrança',
                        'url': link_fatura,
                    })

                instrucoes = (
                    'Pagar com PIX:\n\n'
                    '1. Toque e segure a mensagem com o código abaixo para copiar;\n'
                    '2. Abra o app do seu banco;\n'
                    '3. Cole o código e finalize o pagamento.'
                )
                if btn_items:
                    ok_btn, _, err_btn = send_instagram_button_template(
                        canal,
                        str(recipient),
                        instrucoes,
                        msg_btns=btn_items,
                    )
                    if ok_btn:
                        self._persistir_mensagem_instagram(
                            conversation,
                            instrucoes,
                            extra_attrs={
                                **invoice_attrs,
                                'has_pix': True,
                                'interactive_buttons': btn_items,
                            },
                        )
                    else:
                        logger.warning('[FATURA][Instagram] Template PIX falhou: %s', err_btn)
                        send_instagram_text(canal, str(recipient), instrucoes)
                else:
                    send_instagram_text(canal, str(recipient), instrucoes)

                codigo_msg = f'📋 Código PIX copia e cola:\n\n{codigo_pix}'
                ok_code, _, err_code = send_instagram_text(canal, str(recipient), codigo_msg)
                if not ok_code:
                    return {'success': False, 'error': err_code or 'Falha ao enviar código PIX'}
                self._persistir_mensagem_instagram(
                    conversation,
                    codigo_msg,
                    extra_attrs={**invoice_attrs, 'has_pix': True, 'pix_code': codigo_pix},
                )

            if show_boleto:
                if link_fatura and str(link_fatura).startswith('http'):
                    ok_pdf, _, err_pdf = send_instagram_media(
                        canal,
                        str(recipient),
                        'file',
                        link_fatura,
                        caption=f'Boleto {fatura_id}',
                        mime_type='application/pdf',
                    )
                    if ok_pdf:
                        self._persistir_mensagem_instagram(
                            conversation,
                            f'Boleto {fatura_id}',
                            message_type='document',
                            file_url=link_fatura,
                            extra_attrs={**invoice_attrs, 'has_boleto': True},
                        )
                    else:
                        logger.warning('[FATURA][Instagram] PDF boleto falhou: %s', err_pdf)

                boleto_btns = []
                if link_fatura and str(link_fatura).startswith('http'):
                    boleto_btns.append({
                        'id': 'boleto_pdf',
                        'title': 'Abrir boleto PDF',
                        'url': link_fatura,
                    })

                boleto_instr = (
                    'Pagar com boleto:\n\n'
                    '1. Toque e segure a linha digitável abaixo para copiar;\n'
                    '2. Use o app do seu banco para pagar.'
                )
                if boleto_btns:
                    send_instagram_button_template(
                        canal,
                        str(recipient),
                        boleto_instr,
                        msg_btns=boleto_btns,
                    )
                else:
                    send_instagram_text(canal, str(recipient), boleto_instr)

                if linha_digitavel:
                    linha_msg = f'📋 Linha digitável:\n\n{linha_digitavel}'
                    ok_linha, _, err_linha = send_instagram_text(
                        canal, str(recipient), linha_msg
                    )
                    if not ok_linha:
                        return {
                            'success': False,
                            'error': err_linha or 'Falha ao enviar linha digitável',
                        }
                    self._persistir_mensagem_instagram(
                        conversation,
                        linha_msg,
                        extra_attrs={
                            **invoice_attrs,
                            'has_boleto': True,
                            'boleto_code': linha_digitavel,
                        },
                    )

            logger.info(
                '[FATURA] Fatura %s enviada via Instagram (provedor %s, pix=%s boleto=%s)',
                fatura_id,
                provedor_id,
                show_pix,
                show_boleto,
            )
            return {'success': True, 'message': 'Fatura enviada via Instagram com sucesso'}

        except Exception as exc:
            provedor_id = getattr(provedor, 'id', 'unknown')
            logger.exception('[FATURA] Erro ao enviar fatura Instagram (provedor %s)', provedor_id)
            return {'success': False, 'error': str(exc)}

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
            
            # 🚨 CORREÇÃO MULTI-CANAL: Priorizar o canal real da conversa
            canal = None
            if conversation and hasattr(conversation, 'inbox') and conversation.inbox:
                inbox = conversation.inbox
                if inbox.channel_id and inbox.channel_id != 'default':
                    try:
                        # Tentar buscar o canal pelo ID do banco
                        canal = Canal.objects.get(id=inbox.channel_id, provedor=provedor, tipo="whatsapp_oficial", ativo=True)
                    except (Canal.DoesNotExist, ValueError, TypeError):
                        pass

            # Fallback: buscar o primeiro canal ativo se a conversa não tiver vínculo ou falhar
            if not canal:
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
            valores = self._resolver_valores_fatura(fatura)
            valor = valores['valor']
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
            from core.phone_utils import normalize_whatsapp_phone
            recipient_number = normalize_whatsapp_phone(recipient_number)
            if not recipient_number:
                erro_msg = f"Contato sem telefone válido para envio (provedor {provedor_id})"
                logger.error(f"[FATURA] {erro_msg}")
                return {"success": False, "error": erro_msg}
            
            # Obter nome do provedor para merchant_name / rodapé
            from core.external_webhook_dispatch import resolve_merchant_display_name
            nome_provedor = resolve_merchant_display_name(provedor)
            
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

            sent_pix = any(ps.get('type') == 'pix_dynamic_code' for ps in payment_settings)
            sent_boleto = any(ps.get('type') == 'boleto' for ps in payment_settings)
            sent_pdf = bool(link_fatura and show_boleto)
            
            # Obter nome do cliente para a mensagem
            nome_cliente = "Cliente"
            try:
                if conversation and hasattr(conversation, 'contact') and conversation.contact:
                    nome_cliente = conversation.contact.name.split()[0].upper()
            except:
                pass

            # Texto do body do card Meta (customizável pelo provedor)
            body_text = self._body_card_fatura(
                vencimento_formatado,
                valores,
                provedor=provedor,
                fatura_id=fatura_id,
                nome_cliente=nome_cliente or '',
                nome_provedor=nome_provedor or '',
                tipo_pagamento=tp,
            )
            
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
                                    'has_pix': sent_pix,
                                    'has_boleto': sent_boleto,
                                    'pix_code': codigo_pix if sent_pix else None,
                                    'line_code': linha_digitavel if sent_boleto else None,
                                    'document_url': link_fatura if sent_pdf else None,
                                    'is_invoice': True,
                                    'payment_type': 'whatsapp_oficial',
                                    'merchant_name': nome_provedor,
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
                        
                        msg = Message.objects.create(
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
                            from channels.layers import get_channel_layer
                            from asgiref.sync import async_to_sync
                            from conversations.serializers import MessageSerializer
                            
                            channel_layer = get_channel_layer()
                            message_data = MessageSerializer(msg).data
                            
                            async_to_sync(channel_layer.group_send)(
                                f"conversation_{msg.conversation.id}",
                                {
                                    "type": "chat_message",
                                    "message": message_data,
                                    "sender": None,
                                    "timestamp": msg.created_at.isoformat(),
                                }
                            )
                        except Exception as e:
                            logger.error(f"[FATURA] Erro ao transmitir broadcast PIX: {e}")
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
                            
                            msg = Message.objects.create(
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
                                from channels.layers import get_channel_layer
                                from asgiref.sync import async_to_sync
                                from conversations.serializers import MessageSerializer
                                
                                channel_layer = get_channel_layer()
                                message_data = MessageSerializer(msg).data
                                
                                async_to_sync(channel_layer.group_send)(
                                    f"conversation_{msg.conversation.id}",
                                    {
                                        "type": "chat_message",
                                        "message": message_data,
                                        "sender": None,
                                        "timestamp": msg.created_at.isoformat(),
                                    }
                                )
                            except Exception as e:
                                logger.error(f"[FATURA] Erro ao transmitir broadcast Boleto: {e}")
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
