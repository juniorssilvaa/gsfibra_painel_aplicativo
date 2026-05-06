import logging
import json
import re
import asyncio
import random
import time
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from django.utils import timezone
from asgiref.sync import sync_to_async, async_to_sync

# Importações necessárias do projeto
from .models import Provedor, AuditLog
from .database_tools import DatabaseTools
from .database_function_definitions import DATABASE_FUNCTION_MAPPING, DATABASE_FUNCTION_TOOLS
from .sgp_client import SGPClient
from .fatura_service import FaturaService
from .redis_memory_service import redis_memory_service
from conversations.closing_service import closing_service, stamp_automation_closure_trace
from core.chat_migration_service import chat_migration_service

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

class AIActionsHandler:
    """
    Sub-agente responsável pela execução de ações e chamadas de funções (Tools).
    Gerencia integrações com SGP, Banco de Dados e outras ferramentas externas.
    """

    def __init__(self, openai_service=None):
        self.openai_service = openai_service

    def _is_valid_cpf_cnpj(self, cpf_cnpj: str) -> bool:
        """Valida se a string é um CPF ou CNPJ válido"""
        if not cpf_cnpj:
            return False
        clean = re.sub(r'[^\d]', '', str(cpf_cnpj))
        if len(clean) not in [11, 14]:
            return False
        return clean.isdigit()

    def _verificar_horario_atendimento(self, provedor: Provedor) -> Dict[str, Any]:
        """Verifica se está dentro do horário de atendimento"""
        if self.openai_service and hasattr(self.openai_service, 'formatter'):
            return self.openai_service.formatter._verificar_horario_atendimento(provedor)
        return {'dentro_horario': True, 'proximo_horario': None, 'mensagem': None}

    def _formatar_horarios_atendimento(self, horarios: list) -> str:
        """Formata os horários de atendimento no padrão solicitado pelo usuário (sem emojis)"""
        if not horarios or not isinstance(horarios, list): return ""
        
        dias_semana_map = {
            'segunda': 'Segunda-feira', 'terça': 'Terça-feira', 'terca': 'Terça-feira',
            'quarta': 'Quarta-feira', 'quinta': 'Quinta-feira', 'sexta': 'Sexta-feira',
            'sábado': 'Sábado', 'sabado': 'Sábado', 'domingo': 'Domingo'
        }
        
        linhas = ["Nosso horário de atendimento é:\n"]
        
        for d in horarios:
            dia_raw = d.get('dia', '').lower().strip()
            # Remover sufixos se houver e re-adicionar padrão
            dia_base = dia_raw.split('-')[0].split(' ')[0]
            dia_formatado = dias_semana_map.get(dia_base, dia_raw.capitalize())
            
            periodos = d.get('periodos', [])
            if not periodos:
                linhas.append(f"{dia_formatado}: Fechado")
            else:
                p_strings = []
                for p in periodos:
                    inicio = p.get('inicio', '')
                    fim = p.get('fim', '')
                    if inicio and fim:
                        p_strings.append(f"{inicio} às {fim}")
                
                if p_strings:
                    horario_str = " e ".join(p_strings)
                    linhas.append(f"{dia_formatado}: {horario_str}")
                else:
                    linhas.append(f"{dia_formatado}: Fechado")
        
        return "\n".join(linhas)

    def _formatar_contratos_padrao(self, contratos: list, nome_cliente: str) -> str:
        """Formata contratos no padrão WhatsApp com status"""
        nome = f"*{nome_cliente.upper()}*"
        if len(contratos) == 1:
            c = contratos[0]
            cid = str(c.get('contratoId', ''))
            status = str(c.get('contratoStatusDisplay', '')).upper()
            end_parts = [c.get('endereco_logradouro'), c.get('endereco_numero'), c.get('endereco_bairro'), c.get('endereco_cidade'), c.get('endereco_uf')]
            end = ' '.join(str(p).strip() for p in end_parts if p and str(p).strip().lower() != 'none').upper() or "ENDEREÇO NÃO INFORMADO"
            
            msg = f"{nome}, contrato localizado:\n\n1 - Contrato ({cid}) - *{status}*\nEndereço: *{end}*\n\nSeus dados estão corretos? Me confirma para continuar."
            return msg
        else:
            msg = f"{nome}, encontramos mais de um contrato. Escolha o contrato desejado:"
            for idx, c in enumerate(contratos, 1):
                cid = str(c.get('contratoId', ''))
                status = str(c.get('contratoStatusDisplay', '')).upper()
                end_parts = [c.get('endereco_logradouro'), c.get('endereco_numero'), c.get('endereco_bairro'), c.get('endereco_cidade'), c.get('endereco_uf')]
                end = ' '.join(str(p).strip() for p in end_parts if p and str(p).strip().lower() != 'none').upper() or "ENDEREÇO NÃO INFORMADO"
                msg += f"\n\n{idx} - Contrato ({cid}) - *{status}*\nEndereço: *{end}*"
            return msg

    def execute_database_function(self, provedor: Provedor, function_name: str, function_args: dict, contexto: dict = None) -> dict:
        """Executa funções de banco de dados (Transferências, etc.) com ISOLAMENTO total"""
        try:
            if not provedor: return {"success": False, "erro": "Provedor não identificado para execução de banco de dados."}

            # Identificadores para memória e isolamento
            conv = contexto.get('conversation') if contexto else None
            conversation_id = conv.id if conv else None
            channel = contexto.get('canal', 'wa') if contexto else 'wa'
            phone = contexto.get('contact', {}).phone if contexto and contexto.get('contact') else (contexto.get('contact_phone', 'unknown') if contexto else 'unknown')

            # Validação forte de tenant
            if conv and conv.inbox and conv.inbox.provedor_id:
                ctx_pid = conv.inbox.provedor_id
                if int(ctx_pid) != int(provedor.id):
                    return {"success": False, "erro": "Isolamento de provedor violado."}

            # Carregar estado para idempotência se disponível
            conversation_state = {}
            if conversation_id:
                conversation_state = redis_memory_service.get_ai_state_sync(provedor.id, conversation_id, channel, phone)

            # Cálculo de hash para idempotência
            args_hash = hashlib.sha256(json.dumps(function_args, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            # Verificação de idempotência
            if (conversation_state.get("last_function") == function_name and 
                conversation_state.get("last_function_args_hash") == args_hash and 
                conversation_state.get("last_function_success") is True):
                logger.info(f"[ACTIONS] Ação {function_name} já executada com sucesso. Retornando cache.")
                return {
                    "success": True, 
                    "cached": True,
                    "mensagem_formatada": conversation_state.get("last_ia_response") or "Certo. Já realizei essa ação para você.",
                    "protocolo": conversation_state.get("protocolo")
                }

            # Ferramentas de banco isoladas por provedor
            db_tools = DatabaseTools(provedor=provedor)
            method_name = DATABASE_FUNCTION_MAPPING.get(function_name)
            if not method_name: return {"success": False, "erro": f"Ação '{function_name}' não mapeada."}
            
            # Garantir conversation_id correto (injetar automaticamente se não fornecido)
            if conversation_id:
                # Para funções que precisam de conversation_id, injetar automaticamente se não fornecido
                if function_name in ['criar_resumo_suporte', 'executar_transferencia_conversa', 'transferir_conversa_inteligente', 'encerrar_atendimento']:
                    if 'conversation_id' not in function_args or not function_args.get('conversation_id'):
                        function_args['conversation_id'] = conversation_id
                # Para outras funções, apenas atualizar se já existir
                elif 'conversation_id' in function_args and function_args.get('conversation_id'):
                    function_args['conversation_id'] = conversation_id
            
            method = getattr(db_tools, method_name)
            
            # Caso especial para encerramento
            if function_name == "encerrar_atendimento":
                if conv:
                    stamp_automation_closure_trace(conv, 'ia_encerrar_atendimento')
                    closing_service.request_closing(conv)
                    redis_memory_service.clear_conversation_memory_sync(provedor_id=provedor.id, conversation_id=conv.id, channel=channel, phone=phone)
                    res = {
                        "success": True, 
                        "mensagem_formatada": "Perfeito! Estou encerrando seu atendimento agora conforme solicitado. Se precisar de algo no futuro, é só nos chamar novamente. Tenha um ótimo dia! 👋"
                    }
                else:
                    return {"success": False, "erro": "Conversa não identificada."}
            else:
                res = method(**function_args)

            # Persistir idempotência após sucesso
            if res.get('success') and conversation_id:
                redis_memory_service.update_ai_state_sync(
                    provedor.id, conversation_id,
                    {
                        "last_function": function_name,
                        "last_function_args_hash": args_hash,
                        "last_function_success": True,
                        "protocolo": res.get("protocolo")
                    },
                    channel, phone
                )
            
            return res
        except Exception as e:
            logger.error(f"Erro ao executar ação de banco: {e}", exc_info=True)
            return {"success": False, "erro": str(e)}

    def execute_sgp_function(self, provedor: Provedor, function_name: str, function_args: dict, contexto: dict = None) -> dict:
        """Executa funções do SGP (Consulta, Fatura, Chamado, etc.) com ISOLAMENTO total"""
        try:
            if not provedor: return {"success": False, "erro": "Provedor não identificado."}

            # Identificadores com normalização estrita
            conv = contexto.get('conversation') if contexto else None
            conversation_id = conv.id if conv else None
            channel = redis_memory_service.normalize_channel(contexto.get('canal', 'whatsapp') if contexto else 'whatsapp')
            phone = contexto.get('contact', {}).phone if contexto and contexto.get('contact') else (contexto.get('contact_phone', 'unknown') if contexto else 'unknown')

            # Validação tenant
            if conv and conv.inbox and conv.inbox.provedor_id:
                if int(conv.inbox.provedor_id) != int(provedor.id):
                    return {"success": False, "erro": "Isolamento violado."}

            # Carregar estado
            conversation_state = {}
            if conversation_id:
                conversation_state = redis_memory_service.get_ai_state_sync(provedor.id, conversation_id, channel, phone)

            # Cálculo de hash para idempotência
            args_hash = hashlib.sha256(json.dumps(function_args, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            # Verificação de idempotência específica para SGP (especialmente fatura)
            if function_name == "gerar_fatura_completa" and conversation_state.get("fatura_enviada"):
                return {
                    "success": True, 
                    "cached": True,
                    "mensagem_formatada": "Sua fatura já foi enviada aqui no WhatsApp. Precisa de mais alguma coisa?"
                }

            if (conversation_state.get("last_function") == function_name and 
                conversation_state.get("last_function_args_hash") == args_hash and 
                conversation_state.get("last_function_success") is True):
                return {
                    "success": True, 
                    "cached": True,
                    "mensagem_formatada": conversation_state.get("last_ia_response") or "Já realizei essa consulta para você.",
                    "protocolo": conversation_state.get("protocolo")
                }

            # Integração SGP
            integracao = provedor.integracoes_externas or {}
            
            # Tentar buscar do objeto aninhado 'sgp' ou da raiz
            sgp_config = integracao.get('sgp', {}) if isinstance(integracao.get('sgp'), dict) else integracao
            
            sgp_url = sgp_config.get('sgp_url') or integracao.get('sgp_url')
            sgp_token = sgp_config.get('sgp_token') or integracao.get('sgp_token')
            sgp_app = sgp_config.get('sgp_app') or integracao.get('sgp_app')
            
            if not all([sgp_url, sgp_token, sgp_app]):
                logger.error(f"[SGP] Configuração incompleta para provedor {provedor.id}: url={bool(sgp_url)}, token={bool(sgp_token)}, app={bool(sgp_app)}")
                return {"success": False, "erro": "SGP não configurado corretamente."}
            
            sgp = SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)
            res = {"success": False, "erro": "Ação não reconhecida."}

            logger.info(
                "[SGP] Chamada | funcao=%s | provedor_id=%s | conversa=%s | canal=%s",
                function_name, provedor.id, conversation_id, channel
            )

            if function_name == "consultar_cliente_sgp":
                # Priorizar CPF/CNPJ do input se fornecido
                cpf_cnpj = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj') or ''
                cpf_cnpj = str(cpf_cnpj).replace('.', '').replace('-', '').replace('/', '').strip()
                
                logger.info(f"[AIACTIONS] consultar_cliente_sgp | CPF={cpf_cnpj} (Input={function_args.get('cpf_cnpj')})")
                
                # 🚨 REGRA CRÍTICA: SEMPRE consultar o SGP - NUNCA usar dados da memória
                # Isso garante que sempre usamos dados reais e atualizados do SGP
                # e evita misturar dados de clientes diferentes ou de outros provedores
                sgp_res = sgp.consultar_cliente(cpf_cnpj)
                
                # 🚨 VALIDAÇÃO: Garantir que a resposta do SGP está no formato esperado
                if not isinstance(sgp_res, dict):
                    logger.error("[SGP] consultar_cliente_sgp | Resposta do SGP não é um dict: %s", type(sgp_res))
                    return {"success": False, "erro": "Erro ao consultar dados no SGP. Tente novamente."}
                
                # Extrair contratos do JSON do SGP
                # Formato esperado: {"msg": "...", "contratos": [{...}]}
                contratos_raw = sgp_res.get('contratos', [])
                if not isinstance(contratos_raw, list):
                    logger.error("[SGP] consultar_cliente_sgp | 'contratos' não é uma lista: %s", type(contratos_raw))
                    contratos_raw = []
                
                # Filtrar apenas contratos ativos/suspensos (não cancelados)
                contratos = [c for c in contratos_raw if isinstance(c, dict) and c.get('contratoStatusDisplay', '').lower() not in ['cancelado', 'cancelada']]

                logger.info(
                    "[SGP] consultar_cliente_sgp retornou | contratos=%s | cliente_encontrado=%s",
                    len(contratos), bool(contratos)
                )

                if not contratos:
                    res = {"success": True, "cliente_encontrado": False, "erro": "Nenhum contrato ativo/suspenso encontrado."}
                else:
                    # 🚨 REGRA CRÍTICA: Nome do TITULAR (CPF) deve vir EXCLUSIVAMENTE do JSON do SGP, nunca inventado.
                    # Estrutura esperada do SGP:
                    # {
                    #   "msg": "...",
                    #   "contratos": [
                    #     {
                    #       "razaoSocial": "AMANDA DINIZ DE SOUZA",  ← Nome está AQUI dentro do contrato
                    #       "cpfCnpj": "700.179.490-25",
                    #       ...
                    #     }
                    #   ]
                    # }
                    # 
                    # Ordem de prioridade:
                    # 1. Nome no nível superior da resposta (se existir)
                    # 2. Nome dentro de objeto 'cliente' (se existir)
                    # 3. Nome dentro do primeiro contrato (contratos[0].razaoSocial) ← CASO MAIS COMUM
                    # 4. Se nenhum existir, usar 'Cliente'
                    
                    nome = ''
                    # Tentar nível superior (geralmente não existe, mas verificar primeiro)
                    for key in ('razaoSocial', 'nome', 'nomeCliente'):
                        val = sgp_res.get(key)
                        if val and isinstance(val, str) and val.strip():
                            nome = val.strip()
                            logger.info("[SGP] consultar_cliente_sgp | Nome encontrado no nível superior: %s", key)
                            break
                    
                    # Tentar objeto 'cliente' (se existir)
                    if not nome and isinstance(sgp_res.get('cliente'), dict):
                        c = sgp_res.get('cliente', {})
                        nome = (c.get('razaoSocial') or c.get('nome') or '').strip()
                        if nome:
                            logger.info("[SGP] consultar_cliente_sgp | Nome encontrado em objeto 'cliente'")
                    
                    # CASO MAIS COMUM: Nome dentro do primeiro contrato (contratos[0].razaoSocial)
                    # 🚨 SEMPRE ler diretamente do JSON do SGP - nunca inventar
                    if not nome and contratos and len(contratos) > 0:
                        primeiro_contrato = contratos[0]
                        if isinstance(primeiro_contrato, dict):
                            razao_social_raw = primeiro_contrato.get('razaoSocial')
                            # Validar que razaoSocial existe e é string válida
                            if razao_social_raw and isinstance(razao_social_raw, str):
                                nome = razao_social_raw.strip()
                                logger.info(
                                    "[SGP] consultar_cliente_sgp | Nome lido do JSON do SGP: contratos[0].razaoSocial = '%s'",
                                    nome[:10] + "..." if len(nome) > 10 else nome
                                )
                            else:
                                logger.warning(
                                    "[SGP] consultar_cliente_sgp | contratos[0].razaoSocial não é string válida: %s (tipo: %s)",
                                    razao_social_raw, type(razao_social_raw)
                                )
                    
                    # 🚨 GARANTIA: Se chegou aqui sem nome, o SGP não retornou nome válido
                    # NUNCA inventar nome - sempre usar 'Cliente' como fallback seguro
                    
                    # 🚨 VALIDAÇÃO CRÍTICA: Garantir que o nome não seja vazio, inválido ou suspeito
                    # Se o nome vier vazio ou muito curto, usar 'Cliente' para evitar usar dados incorretos
                    if not nome or len(nome.strip()) < 3:
                        nome = 'Cliente'
                        logger.warning(
                            "[SGP] consultar_cliente_sgp | Nome inválido ou vazio detectado | CPF=%s | usando 'Cliente' como fallback",
                            cpf_cnpj[:3] + "***" + cpf_cnpj[-2:] if len(cpf_cnpj) >= 5 else "***"
                        )

                    # Log detalhado para diagnóstico: nome exato que será usado (mascarado parcialmente)
                    nome_mascarado = nome[:3] + "***" + nome[-2:] if len(nome) > 5 else "***" if nome != "Cliente" else "Cliente"
                    primeiro_contrato_razao = contratos[0].get('razaoSocial', '') if contratos else ''
                    primeiro_contrato_razao_mascarado = primeiro_contrato_razao[:3] + "***" + primeiro_contrato_razao[-2:] if len(primeiro_contrato_razao) > 5 else "***" if primeiro_contrato_razao else "vazio"
                    
                    logger.warning(
                        "[SGP] consultar_cliente_sgp | CPF=%s | nome_usado=%s | nome_resposta_sgp=%s | primeiro_contrato_razaoSocial=%s | contrato_id=%s",
                        cpf_cnpj[:3] + "***" + cpf_cnpj[-2:] if len(cpf_cnpj) >= 5 else "***",
                        nome_mascarado,
                        (sgp_res.get('razaoSocial') or sgp_res.get('nome') or sgp_res.get('nomeCliente') or '')[:3] + "***" if (sgp_res.get('razaoSocial') or sgp_res.get('nome') or sgp_res.get('nomeCliente') or '') else 'vazio',
                        primeiro_contrato_razao_mascarado,
                        contratos[0].get('contratoId') if contratos else 'N/A',
                    )

                    msg = self._formatar_contratos_padrao(contratos, nome)
                    c = contratos[0]
                    step = "AGUARDANDO_ESCOLHA_CONTRATO" if len(contratos) > 1 else "AGUARDANDO_CONFIRMACAO_CONTRATO"
                    is_suspenso = c.get('contratoStatusDisplay', '').strip().lower() in ['suspenso', 'suspensa']
                    
                    # Se o contrato está suspenso, mudar para o fluxo de suspensão para evitar que o determinístico trave em FATURA
                    actual_flow = 'SUSPENSO' if is_suspenso else 'FATURA'
                    actual_step = 'AGUARDANDO_OPCAO_SUSPENSO' if is_suspenso else step

                    updates = {
                        'cpf_cnpj': cpf_cnpj, 'nome_cliente': nome, 'contrato_id': c.get('contratoId'),
                        'servico_plano': c.get('servico_plano') or c.get('planointernet'),
                        'contrato_status_display': c.get('contratoStatusDisplay'),
                        'motivo_status': c.get('motivo_status'),
                        'is_suspenso': is_suspenso, 'cliente_consultado': True, 
                        'flow': actual_flow if len(contratos) == 1 else 'FATURA', 
                        'step': actual_step if len(contratos) == 1 else 'AGUARDANDO_ESCOLHA_CONTRATO',
                        'contratos': contratos if len(contratos) > 1 else None
                    }
                    
                    if conversation_id:
                        redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, updates, channel, phone)
                    
                    res = {
                        "success": True, 
                        "cliente_encontrado": True, 
                        "nome": nome, 
                        "mensagem_formatada": msg, 
                        "is_suspenso": is_suspenso,
                        "contrato_suspenso": is_suspenso,
                        "contrato_status_display": c.get('contratoStatusDisplay'),
                        "motivo_status": c.get('motivo_status'),
                        "quantidade_contratos": len(contratos),  # 🚨 CRÍTICO: Quantidade de contratos retornados pelo SGP
                        "tem_apenas_um_contrato": len(contratos) == 1  # 🚨 CRÍTICO: Flag explícita para IA analisar
                    }

            elif function_name == "verificar_manutencao_sgp":
                cpf_cnpj = function_args.get('cpf_cnpj', '')
                if not cpf_cnpj:
                    cpf_cnpj = conversation_state.get('cpf_cnpj')
                if not cpf_cnpj:
                    return {"success": False, "erro": "CPF/CNPJ necessário para verificar manutenção."}
                
                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso. Não é necessário verificar manutenção."}
                
                cpf_limpo = cpf_cnpj.replace('.', '').replace('-', '').replace('/', '')
                sgp_res = sgp.listar_manutencoes(cpf_limpo)
                
                # Verificar se há manutenções ativas/programadas
                manutencoes = []
                if isinstance(sgp_res, list):
                    manutencoes = sgp_res
                elif isinstance(sgp_res, dict):
                    if sgp_res.get('status') == 1 and sgp_res.get('manutencoes'):
                        manutencoes = sgp_res.get('manutencoes', [])
                    elif sgp_res.get('manutencoes'):
                        manutencoes = sgp_res.get('manutencoes', [])
                
                if manutencoes:
                    # Filtrar manutenções futuras ou em andamento
                    from django.utils import timezone
                    agora = timezone.now()
                    manutencoes_ativas = []
                    for manut in manutencoes:
                        # Verificar se a manutenção está programada para o futuro ou em andamento
                        data_manut = manut.get('data_manutencao') or manut.get('data') or manut.get('data_inicio')
                        if data_manut:
                            try:
                                from datetime import datetime
                                if isinstance(data_manut, str):
                                    # Tentar parsear a data
                                    dt_manut = datetime.fromisoformat(data_manut.replace('Z', '+00:00'))
                                else:
                                    dt_manut = data_manut
                                # Se a manutenção é hoje ou futura, considerar ativa
                                if dt_manut.date() >= agora.date():
                                    manutencoes_ativas.append(manut)
                            except:
                                # Se não conseguir parsear, considerar ativa
                                manutencoes_ativas.append(manut)
                        else:
                            # Se não tem data, considerar ativa
                            manutencoes_ativas.append(manut)
                    
                    if manutencoes_ativas:
                        # Formatar informações da manutenção
                        info_manut = []
                        for manut in manutencoes_ativas[:3]:  # Máximo 3 manutenções
                            data = manut.get('data_manutencao') or manut.get('data') or manut.get('data_inicio') or 'Data não informada'
                            descricao = manut.get('descricao') or manut.get('motivo') or manut.get('observacao') or 'Manutenção programada'
                            info_manut.append(f"- {descricao} (Data: {data})")
                        
                        mensagem = f"Verifiquei aqui e há manutenção programada para seu contrato:\n\n" + "\n".join(info_manut)
                        if len(manutencoes_ativas) > 3:
                            mensagem += f"\n\nE mais {len(manutencoes_ativas) - 3} manutenção(ões) programada(s)."
                        mensagem += "\n\nO problema que você está enfrentando pode estar relacionado a essa manutenção. Após a conclusão da manutenção, seu acesso deve voltar ao normal."
                        
                        res = {
                            "success": True,
                            "tem_manutencao": True,
                            "manutencoes": manutencoes_ativas,
                            "mensagem_formatada": mensagem
                        }
                    else:
                        res = {
                            "success": True,
                            "tem_manutencao": False,
                            "mensagem_formatada": "Não há manutenção programada para seu contrato no momento."
                        }
                else:
                    res = {
                        "success": True,
                        "tem_manutencao": False,
                        "mensagem_formatada": "Não há manutenção programada para seu contrato no momento."
                    }

            elif function_name == "verificar_acesso_sgp":
                cid = function_args.get('contrato')
                if not cid: return {"success": False, "erro": "Contrato obrigatório."}
                
                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso por falta de pagamento.", "contrato_suspenso": True}
                
                sgp_res = sgp.verifica_acesso(cid)
                
                # Verificar se é manutenção em andamento (status == 9)
                if isinstance(sgp_res, dict) and sgp_res.get('status') == 9:
                    # Há manutenção em andamento
                    msg_manutencao_raw = sgp_res.get('msg', '')
                    protocolo = sgp_res.get('protocolo', '')
                    tempo = sgp_res.get('tempo', '')
                    
                    # Formatar mensagem de forma amigável (a IA vai melhorar ainda mais)
                    # Remover quebras de linha \r\n e limpar a mensagem
                    msg_manutencao_limpa = msg_manutencao_raw.replace('\r\n', ' ').replace('\n', ' ').strip()
                    
                    # Criar mensagem base para a IA melhorar
                    mensagem_base = f"Identifiquei que há uma manutenção preventiva em andamento na sua região."
                    if msg_manutencao_limpa:
                        mensagem_base += f" {msg_manutencao_limpa}"
                    if protocolo:
                        mensagem_base += f" Protocolo: {protocolo}"
                    if tempo:
                        mensagem_base += f" Tempo estimado: {tempo}"
                    
                    res = {
                        "success": True,
                        "status_conexao": "Manutencao",
                        "tem_manutencao": True,
                        "protocolo": protocolo,
                        "tempo_estimado": tempo,
                        "mensagem_manutencao_raw": msg_manutencao_raw,
                        "mensagem_manutencao_limpa": msg_manutencao_limpa,
                        "mensagem_formatada": mensagem_base,
                        "instrucao_ia": "Você deve criar sua própria mensagem sobre a manutenção de forma educada, profissional e amigável usando suas próprias palavras. NUNCA copie literalmente a mensagem_manutencao_raw ou mensagem_manutencao_limpa do SGP. Use as informações disponíveis (protocolo, tempo_estimado) mas crie uma mensagem natural, variada e adaptada ao contexto da conversa. Seja empático e explique que o problema está relacionado à manutenção preventiva."
                    }
                elif isinstance(sgp_res, dict) and sgp_res.get('status') == 1:
                    # Online
                    status = "Online"
                    msg_status = "sua conexão está normal"
                    res = {"success": True, "status_conexao": status, "mensagem_formatada": f"Verifiquei aqui e {msg_status}. Como posso ajudar?"}
                elif isinstance(sgp_res, list) and len(sgp_res) > 0:
                    # Online (formato de lista)
                    status = "Online"
                    msg_status = "sua conexão está normal"
                    res = {"success": True, "status_conexao": status, "mensagem_formatada": f"Verifiquei aqui e {msg_status}. Como posso ajudar?"}
                else:
                    # Offline
                    status = "Offline"
                    msg_status = "não consegui detectar seu equipamento online"
                    res = {"success": True, "status_conexao": status, "mensagem_formatada": f"Verifiquei aqui e {msg_status}. Como posso ajudar?"}

            elif function_name == "gerar_fatura_completa":
                # Priorizar input sobre contexto para evitar dados stale
                cpf = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj')
                tipo_pagamento = function_args.get('tipo_pagamento', 'pix')
                
                # Se mudou o CPF, ignoramos o contrato antigo do contexto
                input_cpf = function_args.get('cpf_cnpj')
                if input_cpf and str(input_cpf).strip() != str(conversation_state.get('cpf_cnpj')).strip():
                    contrato_id = function_args.get('contrato_id')
                else:
                    contrato_id = function_args.get('contrato_id') or conversation_state.get('contrato_id')

                logger.info(f"[AIACTIONS] gerar_fatura_completa | CPF={cpf} | Contrato={contrato_id} | Tipo={tipo_pagamento}")

                if not self._is_valid_cpf_cnpj(cpf): 
                    logger.warn(f"[AIACTIONS] CPF inválido: {cpf}")
                    return {"success": False, "erro": "CPF/CNPJ inválido."}
                
                from .fatura_service import fatura_service as fs
                dados = fs.buscar_fatura_sgp(provedor, cpf, contrato_id)
                
                # Verificar se retornou mensagem positiva (todas as faturas pagas)
                if dados and dados.get('mensagem_positiva'):
                    return {
                        "success": True,
                        "mensagem": dados.get('mensagem', 'Parabéns! Todas as suas faturas estão pagas.'),
                        "mensagem_formatada": dados.get('mensagem', 'Parabéns! Todas as suas faturas estão pagas.')
                    }
                
                if not dados or dados.get('status') != 1: 
                    return {"success": False, "erro": "Nenhuma fatura em aberto."}
                
                if not phone or phone == 'unknown': return {"success": False, "erro": "Telefone não identificado."}

                envio = fs.enviar_fatura(provedor, phone, dados, conv, tipo_pagamento)
                
                if (isinstance(envio, bool) and envio) or (isinstance(envio, dict) and envio.get('success')):
                    if conversation_id:
                        # Se foi enviado com sucesso, limpar o fluxo de suspensão/fatura
                        redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, {"flow": "NONE", "step": "INICIAL", "fatura_enviada": True}, channel, phone)
                    res = {"success": True, "mensagem": "Fatura enviada com sucesso!"}
                else:
                    res = {"success": False, "erro": "Falha no envio."}

            elif function_name == "criar_chamado_tecnico":
                cid, cont = function_args.get('contrato'), function_args.get('conteudo')
                tipo_arg = function_args.get('ocorrenciatipo')
                if not cid or not cont: return {"success": False, "erro": "Dados insuficientes."}
                if tipo_arg is None or (isinstance(tipo_arg, str) and not str(tipo_arg).strip()):
                    return {"success": False, "erro": "Informe o código ocorrenciatipo (tipo de ocorrência no SGP do provedor)."}
                
                if conversation_state.get('is_suspenso'):
                    return {"success": False, "erro": "Contrato suspenso.", "contrato_suspenso": True}
                
                # Criar chamado no SGP
                sgp_res = sgp.criar_chamado(contrato=re.sub(r'[^\d]', '', str(cid)), conteudo=cont, ocorrenciatipo=tipo_arg)
                
                if sgp_res.get('success'):
                    protocolo = sgp_res.get('protocolo')
                    
                    # 🚨 REGRA DE ORDEM: O protocolo deve ser retornado para o Chatbot primeiro
                    # O Chatbot irá gerar a resposta contendo o protocolo e então solicitaremos a transferência
                    if conv:
                        # Executar a transferência via DatabaseTools
                        # Importante: Isso muda o status para 'pending'. O fluxo do webhook garantirá
                        # que a resposta atual do Chatbot ainda seja enviada antes do bot parar de responder.
                        db_tools = DatabaseTools(provedor=provedor)
                        transfer_res = db_tools.executar_transferencia_conversa(conv.id, "SUPORTE TÉCNICO", f"Chamado: {protocolo}")
                        
                        logger.info(f"[SGP] Chamado {protocolo} criado e conversa {conv.id} transferida: {transfer_res.get('success')}")

                    res = {
                        "success": True, 
                        "protocolo": protocolo, 
                        "mensagem_formatada": f"Com certeza! Já abri seu chamado técnico (Protocolo: {protocolo}) e estou transferindo você agora mesmo para o suporte para que possam te dar continuidade. Só um momento!"
                    }
                else:
                    logger.warning(f"[SGP] Falha ao criar chamado: {sgp_res.get('error')} | raw: {sgp_res.get('raw')}")
                    res = {"success": False, "erro": sgp_res.get('error')}
            
            elif function_name == "liberar_por_confianca":
                cid = function_args.get('contrato')
                cpf_cnpj = function_args.get('cpf_cnpj') or conversation_state.get('cpf_cnpj')
                conteudo = function_args.get('conteudo')  # Conteúdo que o cliente disse (ex: "vou paga amanhã")
                if not cid: return {"success": False, "erro": "Contrato obrigatório."}
                
                sgp_res = sgp.liberar_por_confianca(contrato=str(cid), cpf_cnpj=cpf_cnpj, conteudo=conteudo)
                
                # Verificar se o desbloqueio foi bem-sucedido
                liberado = sgp_res.get('liberado', False)
                status = sgp_res.get('status')
                msg = sgp_res.get('msg', '')
                liberado_dias = sgp_res.get('liberado_dias')
                data_promessa = sgp_res.get('data_promessa')
                
                # Sucesso: liberado = true ou status = 1 ou mensagem contém "liberado"/"sucesso"
                if liberado is True or status == 1 or (isinstance(msg, str) and msg.lower() in ['liberado', 'sucesso']):
                    if conversation_id:
                        redis_memory_service.update_ai_state_sync(provedor.id, conversation_id, {"flow": "NONE", "step": "INICIAL", "is_suspenso": False}, channel, phone)
                    
                    # Construir mensagem de sucesso com informações sobre os dias de liberação
                    if liberado_dias:
                        mensagem_sucesso = f"Pronto! Realizei o desbloqueio em confiança. Seu acesso ficará liberado por {liberado_dias} {'dia' if liberado_dias == 1 else 'dias'}"
                        if data_promessa:
                            mensagem_sucesso += f" (até {data_promessa})"
                        mensagem_sucesso += ". Seu acesso voltará em alguns minutos. 😊"
                    else:
                        mensagem_sucesso = "Pronto! Realizei o desbloqueio em confiança. Seu acesso voltará em alguns minutos. 😊"
                    
                    res = {
                        "success": True, 
                        "mensagem_formatada": mensagem_sucesso,
                        "liberado_dias": liberado_dias,
                        "data_promessa": data_promessa
                    }
                else:
                    # Verificar se é caso de recurso não disponível
                    msg_lower = str(msg).lower() if msg else ''
                    if 'não disponível' in msg_lower or 'nao disponivel' in msg_lower or 'recurso não disponível' in msg_lower or 'recurso nao disponivel' in msg_lower:
                        # Retornar mensagem formatada informando que o recurso não está disponível
                        res = {
                            "success": False, 
                            "mensagem_formatada": f"Entendo que você precisa do desbloqueio, mas infelizmente o recurso de desbloqueio em confiança não está disponível para seu contrato no momento. {msg if msg else 'Por favor, entre em contato com nossa equipe financeira para regularizar sua situação.'}",
                            "recurso_indisponivel": True
                        }
                    else:
                        # Outros erros - retornar mensagem genérica
                        res = {"success": False, "erro": msg or "Erro no desbloqueio."}

            # Persistir idempotência SGP
            if res.get('success') and conversation_id and function_name != "consultar_cliente_sgp":
                redis_memory_service.update_ai_state_sync(
                    provedor.id, conversation_id,
                    {
                        "last_function": function_name,
                        "last_function_args_hash": args_hash,
                        "last_function_success": True,
                        "protocolo": res.get("protocolo")
                    },
                    channel, phone
                )

            logger.info("[SGP] %s retornou | success=%s | conversa=%s", function_name, res.get("success"), conversation_id)
            return res
        except Exception as e:
            logger.error(f"Erro crítico em execute_sgp_function: {e}", exc_info=True)
            return {"success": False, "erro": str(e)}

    def get_sgp_tools(self) -> List[Dict[str, Any]]:
        """Retorna definições das ferramentas"""
        return [
            {"type": "function", "function": {"name": "consultar_cliente_sgp", "description": "Consulta cliente SGP por CPF/CNPJ. Retorna informações do contrato incluindo status (Suspenso/Ativo) e motivo da suspensão. 🚨 CRÍTICO: A função retorna 'quantidade_contratos' e 'tem_apenas_um_contrato' no JSON. Se 'tem_apenas_um_contrato: true' ou 'quantidade_contratos: 1', há APENAS 1 contrato - NÃO pergunte qual contrato, apenas peça confirmação dos dados ('Seus dados estão corretos?'). Se 'quantidade_contratos: 2' ou mais, há múltiplos contratos - aí sim pergunte qual contrato. Use SEMPRE quando o cliente relatar problemas de internet para verificar se o contrato está suspenso antes de fazer diagnóstico técnico.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "gerar_fatura_completa", "description": "Gera e envia fatura completa para o cliente via WhatsApp. Use quando o cliente pedir fatura, segunda via, boleto ou PIX.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}, "tipo_pagamento": {"type": "string", "enum": ["pix", "boleto"]}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "verificar_manutencao_sgp", "description": "Verifica se há manutenção programada para o cliente. Use APENAS se o contrato NÃO estiver suspenso e após confirmar os dados do cliente. Se houver manutenção, informe ao cliente e NÃO abra chamado técnico.", "parameters": {"type": "object", "properties": {"cpf_cnpj": {"type": "string"}}, "required": ["cpf_cnpj"]}}},
            {"type": "function", "function": {"name": "verificar_acesso_sgp", "description": "Verifica se o acesso à internet do contrato está online, offline ou em manutenção. Retorna status_conexao que pode ser 'Online', 'Offline' ou 'Manutencao'. Se retornar 'Manutencao' ou tem_manutencao=True, há manutenção preventiva em andamento - NÃO abra chamado técnico. IMPORTANTE: Quando houver manutenção, você DEVE criar sua própria mensagem de forma educada, profissional e amigável usando suas próprias palavras. NUNCA copie literalmente a mensagem_manutencao_raw do SGP. Use as informações (protocolo, tempo_estimado) mas crie uma mensagem natural e variada, adaptando ao contexto da conversa. 🚨 SE RETORNAR 'Offline': Faça perguntas sobre LED vermelho e modem ligado PRIMEIRO. Se confirmar LED vermelho OU modem desligado, automatize: criar_resumo_suporte + criar_chamado_tecnico + executar_transferencia_conversa para SUPORTE TÉCNICO. Use APENAS se o contrato NÃO estiver suspenso. NUNCA use para contrato suspenso.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}}, "required": ["contrato"]}}},
            {"type": "function", "function": {"name": "criar_chamado_tecnico", "description": "Cria chamado técnico no SGP. Use APENAS se o contrato NÃO estiver suspenso, NÃO houver manutenção programada e após coletar todas as informações de diagnóstico e criar o resumo. ocorrenciatipo é o código numérico do tipo de ocorrência cadastrado no SGP do provedor. NUNCA use para contrato suspenso ou se houver manutenção.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}, "conteudo": {"type": "string"}, "ocorrenciatipo": {"type": "integer", "description": "ID do tipo de ocorrência no SGP"}}, "required": ["contrato", "conteudo", "ocorrenciatipo"]}}},
            {"type": "function", "function": {"name": "liberar_por_confianca", "description": "Realiza desbloqueio em confiança do contrato suspenso. Use quando o cliente quiser desbloquear o acesso sem pagar imediatamente. O CPF/CNPJ é opcional e será buscado da memória se não fornecido. O conteúdo (conteudo) deve ser o que o cliente disse sobre quando vai pagar (ex: 'vou paga amanhã'), ou deixe vazio para usar 'Liberação Via NioChat' como padrão.", "parameters": {"type": "object", "properties": {"contrato": {"type": "string"}, "cpf_cnpj": {"type": "string", "description": "CPF/CNPJ do cliente (opcional, será buscado da memória se não fornecido)"}, "conteudo": {"type": "string", "description": "Conteúdo da promessa de pagamento que o cliente mencionou (ex: 'vou paga amanhã'). Se o cliente não mencionou nada específico, deixe vazio ou não inclua este parâmetro para usar 'Liberação Via NioChat' como padrão."}}, "required": ["contrato"]}}}
        ]

    def convert_tools_to_gemini(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Converte para formato Gemini"""
        gemini_tools = []
        for t in tools:
            if t.get("type") == "function":
                f = t.get("function", {})
                params = f.get("parameters", {})
                if isinstance(params, dict):
                    params = {k: v for k, v in params.items() if k.lower() not in ['additionalproperties', 'strict']}
                gemini_tools.append({"name": f.get("name"), "description": f.get("description"), "parameters": params})
        return gemini_tools
