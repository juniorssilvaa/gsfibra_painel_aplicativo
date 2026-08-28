import logging
import json
import requests
import re
import uuid
from datetime import datetime, date
from typing import Any, Dict, Optional, List, Tuple
from asgiref.sync import sync_to_async
from django.conf import settings
from .models import ChatbotFlow, Provedor
from .redis_memory_service import redis_memory_service
from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api
from conversations.closing_service import closing_service, stamp_automation_closure_trace
from .horario_utils import verificar_horario_atendimento

logger = logging.getLogger(__name__)


def _copy_provider_gallery_to_conversation_media(conv, gallery_image) -> str:
    """
    Copia o arquivo da galeria para media/messages/<conversation_id>/ para o painel
    usar a mesma rota /api/media/messages/... (CORS + mesmo fluxo do WhatsApp).
    """
    import os
    import shutil

    fallback = f"/api/media/provider-gallery/{gallery_image.id}/"
    try:
        src_path = gallery_image.imagem.path
    except Exception:
        return fallback
    if not src_path or not os.path.isfile(src_path):
        return fallback
    raw_name = os.path.basename(gallery_image.imagem.name or "image.jpg")
    safe_name = raw_name.replace("/", "_").replace("\\", "_")
    dest_name = f"gallery_{gallery_image.id}_{safe_name}"
    dest_dir = os.path.join(settings.MEDIA_ROOT, "messages", str(conv.id))
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, dest_name)
        shutil.copyfile(src_path, dest_path)
    except Exception as copy_err:
        logger.warning(f"[ChatbotEngine][Galeria] Falha ao copiar mídia para pasta da conversa: {copy_err}")
        return fallback
    return f"/api/media/messages/{conv.id}/{dest_name}"


def _sgp_contrato_id_from_fatura2via_response(faturas_res, fallback_digits: str) -> str:
    """
    A API /api/ura/fatura2via/ pode retornar contratoId na raiz com links=[].
    Antes só lia links[0].contrato — com links vazio caía no CPF e o chamado falhava.
    """
    if not faturas_res or not isinstance(faturas_res, dict):
        return fallback_digits
    links = faturas_res.get('links') or []
    if isinstance(links, list) and len(links) > 0 and isinstance(links[0], dict):
        first = links[0]
        cid = first.get('contrato') or first.get('contratoId') or first.get('contrato_id')
        if cid is not None and str(cid).strip() != '':
            return str(cid).strip()
    for key in ('contratoId', 'contrato_id'):
        val = faturas_res.get(key)
        if val is not None and str(val).strip() != '':
            return str(val).strip()
    return fallback_digits


def _formatar_endereco(contrato: dict) -> str:
    """Monta o endereço completo a partir de um dict de contrato SGP."""
    campos = [
        contrato.get('endereco_tipo_logradouro', ''),
        contrato.get('endereco_logradouro', ''),
        contrato.get('endereco_numero', ''),
        contrato.get('endereco_complemento', ''),
        contrato.get('endereco_bairro', ''),
        contrato.get('endereco_cidade', ''),
        contrato.get('endereco_uf', ''),
    ]
    # Filtra valores vazios, None, 'None', 'null'
    partes = [str(c).strip() for c in campos if c and str(c).strip().lower() not in ('none', 'null', '')]
    if partes:
        return ' '.join(partes)
    return ''

def _formatar_data_br(data_str: str) -> str:
    """Converte YYYY-MM-DD para DD.MM.YYYY ou retorna como está."""
    if not data_str or not isinstance(data_str, str):
        return data_str
    try:
        # Tentar converter de YYYY-MM-DD
        if '-' in data_str and len(data_str) == 10:
            dt = datetime.strptime(data_str, '%Y-%m-%d')
            return dt.strftime('%d.%m.%Y')
        # Tentar converter de DD/MM/YYYY
        if '/' in data_str and len(data_str) == 10:
            dt = datetime.strptime(data_str, '%d/%m/%Y')
            return dt.strftime('%d.%m.%Y')
    except:
        pass
    return data_str


def _parse_ocorrenciatipo_node(node_data: dict) -> Optional[int]:
    """ID do tipo de ocorrência no SGP configurado no bloco pelo provedor (sem valor padrão)."""
    raw = node_data.get('ocorrenciatipo')
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return n


class ChatbotEngine:
    """
    Motor de execução para fluxos criados no Chatbot Builder.
    Gerencia estados no Redis e executa transições entre nós.
    """

    @staticmethod
    def _replace_placeholders(data: Any, context: Dict[str, Any]) -> Any:
        """
        Recursivamente substitui {{var}} nos dados (str, list, dict) usando o contexto.
        """
        if isinstance(data, str):
            for key, value in context.items():
                if isinstance(value, (str, int, float, bool)):
                    # Suporta {{var}} e {{ var }}
                    placeholder1 = f"{{{{{key}}}}}"
                    placeholder2 = f"{{{{ {key} }}}}"
                    data = data.replace(placeholder1, str(value)).replace(placeholder2, str(value))
            return data
        elif isinstance(data, list):
            return [ChatbotEngine._replace_placeholders(item, context) for item in data]
        elif isinstance(data, dict):
            return {k: ChatbotEngine._replace_placeholders(v, context) for k, v in data.items()}
        return data

    @staticmethod
    def _normalize_option_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()

    @staticmethod
    def _infer_team_id_from_path(start_node_id: Optional[str], nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], max_depth: int = 12) -> Optional[int]:
        """
        Inferência de equipe por caminho: a partir do nó atual, procura o primeiro
        nó de transferência direta (transferMode=direct + teamId).
        """
        if not start_node_id:
            return None

        node_map = {str(n.get('id')): n for n in (nodes or []) if n.get('id')}
        visited = set()

        def _walk(node_id: str, depth: int) -> Optional[int]:
            if depth > max_depth or node_id in visited:
                return None
            visited.add(node_id)

            node = node_map.get(str(node_id))
            if not node:
                return None

            if node.get('type') == 'transfer':
                data = node.get('data', {}) or {}
                if data.get('transferMode', 'choice') == 'direct' and data.get('teamId'):
                    try:
                        return int(data.get('teamId'))
                    except (TypeError, ValueError):
                        return None

            outgoing = [e for e in (edges or []) if str(e.get('source')) == str(node_id)]
            for edge in outgoing:
                target = edge.get('target')
                if not target:
                    continue
                found = _walk(str(target), depth + 1)
                if found:
                    return found
            return None

        return _walk(str(start_node_id), 0)

    @staticmethod
    def _resolve_interactive_selection(node: Dict[str, Any], message_content: str) -> Optional[str]:
        """
        Resolve seleção digitada em nós interativos (menu/botões) para o ID da opção.
        Aceita:
        - índice numérico (1, 2, 3...)
        - título exato da opção (case-insensitive)
        """
        data = node.get('data', {}) if isinstance(node, dict) else {}
        rows = data.get('rows', []) if isinstance(data.get('rows', []), list) else []
        buttons = data.get('buttons', []) if isinstance(data.get('buttons', []), list) else []
        options = rows if rows else buttons
        if not options:
            return None

        text = str(message_content or "").strip()
        if not text:
            return None

        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(options):
                selected = options[idx]
                return selected.get('id')

        normalized = ChatbotEngine._normalize_option_text(text)
        for option in options:
            title = ChatbotEngine._normalize_option_text(option.get('title'))
            if title and title == normalized:
                return option.get('id')

        return None

    @staticmethod
    async def process_message(provedor_id: int, conversation_id: int, message_content: str, button_id: Optional[str] = None, canal_id: Optional[int] = None):
        """
        Processa uma mensagem recebida e avança o fluxo.
        """
        logger.info(f"[ChatbotEngine][TRACE] Iniciando process_message | conv={conversation_id} | texto='{message_content}' | button='{button_id}' | canal={canal_id}")
        provedor = await Provedor.objects.filter(id=provedor_id).afirst()
        if not provedor:
            logger.warning(f"[ChatbotEngine] Provedor {provedor_id} não encontrado.")
            return False, "Provedor não encontrado"
        if not provedor.is_active:
            logger.info(
                f"[ChatbotEngine] Execução bloqueada para provedor {provedor_id}: "
                f"provedor inativo. Motivo: {provedor.block_reason}"
            )
            return False, "Provedor inativo"

        # 1. Obter o fluxo ativo para o provedor (priorizando o canal se informado)
        query = ChatbotFlow.objects.filter(provedor_id=provedor_id)
        
        flow = None
        if canal_id:
            # 1a. Tentar fluxo específico para o canal
            flow = await query.filter(canal_id=canal_id).order_by('-updated_at').afirst()
            if flow:
                logger.info(f"[ChatbotEngine] Fluxo específico para canal {canal_id} encontrado: {flow.id}")
        
        if not flow:
            # 1b. Fallback para fluxo global (sem canal definido)
            flow = await query.filter(canal__isnull=True).order_by('-updated_at').afirst()
            if flow:
                logger.info(f"[ChatbotEngine] Fluxo global (sem canal) encontrado: {flow.id}")

        if not flow:
            logger.info(f"[ChatbotEngine] Nenhum fluxo encontrado para provedor {provedor_id} (Canal: {canal_id})")
            return False, "Nenhum fluxo encontrado"

        nodes = flow.nodes
        edges = flow.edges
        
        logger.info(f"[ChatbotEngine] Processando mensagem para conv {conversation_id}. Flow={flow.id}, Nodes={len(nodes)}")

        # 2. Identificar estado atual (nó atual)
        # Usamos uma chave específica no Redis para o estado do chatbot
        state_key = f"chatbot_state:{provedor_id}:{conversation_id}"
        current_state = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
        logger.info(f"[ChatbotEngine] Processando msg: conv={conversation_id}, content='{message_content}', button={button_id}")
        current_node_id = current_state.get("chatbot_node_id")
        flow_context = current_state.get('flow_context', {})

        # Salvar última mensagem do usuário no contexto para uso nos nós SGP
        if message_content and message_content.strip():
            flow_context['last_user_message'] = message_content.strip()
            # Se parece com CPF (11 dígitos) ou CNPJ (14 dígitos), guardar também como 'cpf'
            digits_only = ''.join(filter(str.isdigit, message_content.strip()))
            if len(digits_only) in [11, 14]:
                flow_context['cpf'] = digits_only
                flow_context['cpfcnpj'] = digits_only
                logger.info(f"[ChatbotEngine] CPF/CNPJ detectado na mensagem e salvo no contexto do fluxo.")
            # Se parece com número de contrato (numérico genérico, mas não CPF/CNPJ)
            if digits_only and len(digits_only) >= 4 and len(digits_only) not in [11, 14]:
                flow_context.setdefault('contrato', digits_only)
            current_state['flow_context'] = flow_context
            current_state['last_user_message'] = message_content.strip()
            await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")

        next_node = None

        if current_node_id:
            logger.info(f"[ChatbotEngine] Continuando fluxo da conversa {conversation_id}. Nó atual: {current_node_id}")

            # === SGP: Verifica se está aguardando seleção de contrato ===
            if current_node_id.startswith('sgp_select_'):
                sgp_original_node_id = current_node_id[len('sgp_select_'):]
                flow_context = current_state.get('flow_context', {})
                contratos_pendentes = flow_context.get('contratos_pendentes', [])
                selected_contrato = None

                if button_id and button_id.startswith('sgp_contrato_'):
                    num_sel = button_id[len('sgp_contrato_'):]
                    selected_contrato = next((c for c in contratos_pendentes if str(c.get('contratoId') or c.get('contrato_id') or c.get('contrato', '')) == num_sel), None)
                elif message_content and message_content.strip().isdigit():
                    idx = int(message_content.strip()) - 1
                    if 0 <= idx < len(contratos_pendentes):
                        selected_contrato = contratos_pendentes[idx]

                if selected_contrato:
                    # Campo real do SGP é 'contratoId'
                    num_contrato_sel = str(selected_contrato.get('contratoId') or selected_contrato.get('contrato_id') or selected_contrato.get('contrato', ''))
                    logger.warning(f"[ChatbotEngine][SGP] Contrato selecionado: {num_contrato_sel} | contratoId={selected_contrato.get('contratoId')}")
                    # Salva o contrato escolhido no contexto
                    flow_context['contrato'] = num_contrato_sel
                    flow_context['contrato_id'] = num_contrato_sel
                    flow_context['sgp_contrato_id'] = num_contrato_sel
                    flow_context['cliente_id'] = str(selected_contrato.get('cliente_id', ''))
                    flow_context['cidade'] = selected_contrato.get('popNome', '') or selected_contrato.get('endereco_cidade', '')
                    flow_context['endereco'] = _formatar_endereco(selected_contrato)
                    flow_context['status_contrato'] = str(selected_contrato.get('contratoStatus', ''))
                    flow_context.pop('contratos_pendentes', None)
                    current_state['flow_context'] = flow_context
                    current_state['chatbot_node_id'] = sgp_original_node_id
                    await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")
                    # Avançar para o próximo nó após o SGP
                    edge = next((e for e in edges if e.get('source') == sgp_original_node_id), None)
                    if edge:
                        nxt = next((n for n in nodes if n.get('id') == edge.get('target')), None)
                        if nxt:
                            await ChatbotEngine.execute_node(provedor_id, conversation_id, nxt, flow)
                            return True, "Contrato selecionado, fluxo avançado"
                    logger.warning(f"[ChatbotEngine][SGP] Nenhum nó após o SGP após seleção de contrato.")
                    return True, "Contrato selecionado"
                else:
                    logger.warning(f"[ChatbotEngine][SGP] Seleção de contrato inválida: button_id={button_id}, msg={message_content}")
                    from conversations.models import Conversation
                    conv = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                    await ChatbotEngine.send_message_agnostic(conv=conv, text="Por favor, selecione uma das opções listadas acima.")
                    return True, "Aguardando seleção de contrato"
            # === FIM da seleção de contrato ===

            # === TRANSFER: Verifica se está aguardando escolha de equipe ===
            if current_node_id.startswith('transfer_select_'):
                transfer_original_node_id = current_node_id[len('transfer_select_'):]
                
                # Se o usuário escolheu uma equipe via botão ou texto
                selected_team_id = None
                if button_id and button_id.startswith('team_'):
                    selected_team_id = button_id[len('team_'):]
                elif message_content:
                    # Tentar encontrar equipe pelo nome (ignore case)
                    from conversations.models import Team
                    team_name_input = str(message_content).strip().lower()
                    team = await sync_to_async(Team.objects.filter(provedor_id=provedor_id, name__iexact=team_name_input, is_active=True).first)()
                    if team:
                        selected_team_id = team.id

                if selected_team_id:
                    logger.info(f"[ChatbotEngine][Transfer] Equipe selecionada: {selected_team_id}")
                    from conversations.models import Conversation, Team
                    conv = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                    team = await sync_to_async(Team.objects.get)(id=selected_team_id)
                    
                    # Realizar transferência para "Em Espera" (pending)
                    conv.status = 'pending'
                    conv.team = team
                    conv.assignee = None # Limpa atribuição individual se houver
                    conv.waiting_for_agent = True # Libera para visualização humana
                    await sync_to_async(conv.save)() # Salva tudo para garantir que equipe e status persistam
                    
                    # Verificar horário de atendimento
                    horario_info = verificar_horario_atendimento(conv.inbox.provedor)
                    msg_transfer = f"Entendido! Você será atendido pelo setor *{team.name}*."
                    
                    if not horario_info.get('dentro_horario'):
                        proximo = horario_info.get('proximo_horario')
                        if proximo:
                            msg_transfer += f"\n\nComo estamos fora do nosso horário de atendimento agora, nossa equipe falará com você a partir de *{proximo}*."
                        else:
                            msg_transfer += f"\n\nComo estamos fora do nosso horário de atendimento agora, nossa equipe falará com você assim que possível."
                    else:
                        msg_transfer += " Um atendente falará com você em breve."

                    # Enviar confirmação
                    await ChatbotEngine.send_message_agnostic(conv=conv, text=msg_transfer)
                    
                    # Resetar estado do chatbot para esta conversa
                    await redis_memory_service.clear_memory(provedor_id, conversation_id, "whatsapp", "unknown")
                    
                    logger.info(f"[ChatbotEngine][Transfer] Conversa {conversation_id} transferida para equipe {team.name}")
                    return True, f"Transferido para {team.name}"
                else:
                    # Se não reconheceu a equipe, repetir o menu ou avisar
                    logger.warning(f"[ChatbotEngine][Transfer] Equipe inválida: {message_content}")
                    from conversations.models import Conversation
                    conv = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                    await ChatbotEngine.send_message_agnostic(conv=conv, text="Desculpe, não reconheci essa opção. Por favor, selecione um dos setores da lista.")
                    return True, "Aguardando seleção válida de equipe"
            # === FIM da seleção de equipe ===

            current_node = next((n for n in nodes if n.get('id') == current_node_id), None)
            current_node_data = current_node.get('data', {}) if current_node else {}

            # Se o nó atual é interativo, só deve avançar com opção válida.
            is_interactive_node = bool(
                current_node and (
                    current_node.get('type') in ('menu', 'planos') or
                    (
                        current_node.get('type') == 'message' and
                        (current_node_data.get('buttons') or current_node_data.get('rows'))
                    )
                )
            )

            stripped_in = (message_content or "").strip()

            async def _handle_invalid_interactive_attempt():
                """Áudio/imagem/texto fora do menu: incrementa tentativas e aplica ação do provedor ao limite."""
                from conversations.models import Conversation

                conv = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(
                    id=conversation_id
                )
                max_attempts = int(current_node_data.get('maxInvalidAttempts') or 3)
                invalid_msg = current_node_data.get('invalidOptionMessage') or (
                    "Opção inválida. Toque em um item da lista ou digite o título exatamente como aparece no menu."
                )
                limit_msg = current_node_data.get('maxInvalidAttemptsMessage') or (
                    "Não consegui identificar a opção informada. Vou reenviar o menu para você."
                )

                attempts = dict(current_state.get('invalid_option_attempts') or {})
                node_attempts = int(attempts.get(current_node_id, 0)) + 1
                attempts[current_node_id] = node_attempts
                current_state['invalid_option_attempts'] = attempts
                await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")

                if node_attempts >= max_attempts:
                    attempts[current_node_id] = 0
                    current_state['invalid_option_attempts'] = attempts
                    await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")
                    await ChatbotEngine.send_message_agnostic(conv=conv, text=limit_msg)

                    after_action = (current_node_data.get('maxInvalidAction') or 'repeat_menu').strip()
                    after_team_id = current_node_data.get('maxInvalidActionTeamId')

                    if after_action == 'transfer_direct' and after_team_id:
                        from conversations.models import Team
                        team = await sync_to_async(Team.objects.filter(
                            id=after_team_id,
                            provedor=conv.inbox.provedor,
                            is_active=True
                        ).first)()
                        if team:
                            conv.status = 'pending'
                            conv.team = team
                            conv.assignee = None
                            conv.waiting_for_agent = True
                            await sync_to_async(conv.save)()
                            await redis_memory_service.clear_memory(provedor_id, conversation_id, "whatsapp", "unknown")
                            return True, f"Tentativas esgotadas; transferido para {team.name}"

                    if after_action == 'transfer_choice':
                        from conversations.models import Team
                        teams = await sync_to_async(list)(
                            Team.objects.filter(provedor=conv.inbox.provedor, is_active=True).exclude(name="IA")
                        )
                        if teams:
                            rows = [{
                                'id': f'team_{t.id}',
                                'title': t.name[:24],
                                'description': (t.description or 'Falar com atendente')[:72]
                            } for t in teams[:10]]
                            await ChatbotEngine.send_message_agnostic(
                                conv=conv,
                                text="Nao consegui identificar sua opcao. Selecione o setor desejado:",
                                msg_rows=rows,
                                msg_btn_text="Ver Setores",
                                msg_sec_title="Setores Disponiveis"
                            )
                            current_state['chatbot_node_id'] = f'transfer_select_{current_node_id}'
                            await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")
                            return True, "Tentativas esgotadas; aguardando escolha de equipe"

                    await ChatbotEngine.execute_node(provedor_id, conversation_id, current_node, flow)
                    return True, "Tentativas inválidas atingidas; menu reenviado"

                await ChatbotEngine.send_message_agnostic(
                    conv=conv,
                    text=f"{invalid_msg} (Tentativa {node_attempts}/{max_attempts})"
                )
                return True, "Aguardando opção válida do menu"

            if is_interactive_node and not button_id:
                if stripped_in:
                    resolved_button_id = ChatbotEngine._resolve_interactive_selection(current_node, stripped_in)
                    if resolved_button_id:
                        button_id = resolved_button_id
                        logger.info(f"[ChatbotEngine] Seleção textual mapeada para botão/row id: {button_id}")
                if not button_id:
                    # Áudio, foto, sticker, texto que não bate com nenhuma opção, ou vazio
                    res = await _handle_invalid_interactive_attempt()
                    return res

            edge = None
            # Tentar encontrar o próximo nó
            # 1. Se for clique em botão (button_id), tentar achar aresta que combine com o handle
            if button_id:
                logger.info(f"[ChatbotEngine] Recebido button_id: {button_id}. Buscando aresta com sourceHandle correspondente.")
                # O builder agora salva o ID do botão/item no campo sourceHandle do edge
                edge = next((e for e in edges if e.get('source') == current_node_id and e.get('sourceHandle') == button_id), None)
                
                if edge:
                    logger.info(f"[ChatbotEngine] Aresta encontrada pelo handle: {edge.get('id')} -> Target: {edge.get('target')}")
                else:
                    edges_from_current = [e for e in edges if e.get('source') == current_node_id]
                    handles = [e.get('sourceHandle') for e in edges_from_current]
                    logger.warning(f"[ChatbotEngine) SEM MATCH de handle para {button_id}. Handles no nó {current_node_id}: {handles}")
                    # Em menu/lista/planos ou mensagem com botões: NÃO seguir por aresta "sem handle"
                    # (isso enviava o cliente para um ramo aleatório ao mandar áudio/foto ou id inválido).
                    if is_interactive_node:
                        edge = edges_from_current[0] if len(edges_from_current) == 1 else None
                    else:
                        edge = next((e for e in edges_from_current if not e.get('sourceHandle')), None)
                        if not edge and len(edges_from_current) == 1:
                            edge = edges_from_current[0]
                    
                    if edge:
                        logger.info(f"[ChatbotEngine] Usando fallback para: {edge.get('target')}")
                    else:
                        logger.error(
                            f"[ChatbotEngine] Ambiguidade de roteamento! {len(edges_from_current)} saídas "
                            f"mas nenhuma bate com {button_id}"
                        )
                        # Cliente tocou numa linha que existe no menu (WhatsApp) mas o fluxo não tem aresta — não travar.
                        row_valid = None
                        if current_node and current_node.get("type") == "menu":
                            row_valid = next(
                                (r for r in (current_node_data.get("rows") or []) if r.get("id") == button_id),
                                None,
                            )
                        if row_valid:
                            logger.warning(
                                f"[ChatbotEngine] Opção de menu válida sem aresta no builder (corrija o fluxo): {button_id}"
                            )
                            from conversations.models import Conversation

                            conv = await sync_to_async(
                                Conversation.objects.select_related(
                                    "inbox", "inbox__provedor", "contact"
                                ).get
                            )(id=conversation_id)
                            await ChatbotEngine.send_message_agnostic(
                                conv=conv,
                                text="Não consegui seguir com essa opção agora. Por favor, escolha outra opção no menu abaixo.",
                            )
                            await ChatbotEngine.execute_node(
                                provedor_id, conversation_id, current_node, flow
                            )
                            return True, "Menu reenviado (aresta ausente para opção válida)"
                        if is_interactive_node:
                            res = await _handle_invalid_interactive_attempt()
                            return res
                        return None, "Ambiguidade de roteamento"
            else:
                logger.info(f"[ChatbotEngine] Mensagem de texto simples. Buscando aresta padrão (sem handle).")
                # Mensagem de texto: pegamos a primeira aresta ou a que tem sourceHandle nulo
                edge = next((e for e in edges if e.get('source') == current_node_id and not e.get('sourceHandle')), None)
                if not edge:
                    edge = next((e for e in edges if e.get('source') == current_node_id), None)

            if is_interactive_node and button_id and not edge:
                res = await _handle_invalid_interactive_attempt()
                return res
            
            if edge:
                # === NOVO: Capturar título da opção selecionada (botão ou menu) ===
                if current_node:
                    data = current_node.get('data', {})
                    if button_id and current_node.get('type') == 'message':
                        btn = next((b for b in data.get('buttons', []) if b.get('id') == button_id), None)
                        if btn:
                            titulo = btn.get('title', '').upper()
                            flow_context['conteudo'] = btn.get('title')
                            # Mapeamento automático de tipo de pagamento
                            if 'BOLETO' in titulo: flow_context['tipo_pagamento'] = 'boleto'
                            elif 'PIX' in titulo: flow_context['tipo_pagamento'] = 'pix'
                            elif 'AMBOS' in titulo or 'AMBAS' in titulo: flow_context['tipo_pagamento'] = 'ambos'
                            
                            logger.info(f"[ChatbotEngine] OPÇÃO ESCOLHIDA (Botão): {btn.get('title')} | tipo_pagamento mapped: {flow_context.get('tipo_pagamento')}")
                    elif button_id and current_node.get('type') == 'menu':
                        row = next((r for r in data.get('rows', []) if r.get('id') == button_id), None)
                        if row:
                            titulo = row.get('title', '').upper()
                            flow_context['conteudo'] = row.get('title')
                            # Mapeamento automático de tipo de pagamento
                            if 'BOLETO' in titulo: flow_context['tipo_pagamento'] = 'boleto'
                            elif 'PIX' in titulo: flow_context['tipo_pagamento'] = 'pix'
                            elif 'AMBOS' in titulo or 'AMBAS' in titulo: flow_context['tipo_pagamento'] = 'ambos'
                            
                            logger.info(f"[ChatbotEngine] OPÇÃO ESCOLHIDA (Menu): {row.get('title')} | tipo_pagamento mapped: {flow_context.get('tipo_pagamento')}")

                    inferred_team_id = None
                    if button_id and current_node.get('type') == 'message':
                        btn_pick = next(
                            (b for b in (current_node_data.get('buttons') or []) if b.get('id') == button_id),
                            None,
                        )
                        if btn_pick:
                            raw_tid = btn_pick.get('teamId') or btn_pick.get('routingTeamId')
                            if raw_tid not in (None, '', 'null'):
                                try:
                                    inferred_team_id = int(raw_tid)
                                except (TypeError, ValueError):
                                    inferred_team_id = None
                                if inferred_team_id:
                                    logger.info(
                                        f"[ChatbotEngine] last_routing_team_id={inferred_team_id} "
                                        f"(definido no botão) conv={conversation_id}"
                                    )
                    elif button_id and current_node.get('type') == 'menu':
                        row_pick = next(
                            (r for r in (current_node_data.get('rows') or []) if r.get('id') == button_id),
                            None,
                        )
                        if row_pick:
                            raw_tid = row_pick.get('teamId') or row_pick.get('routingTeamId')
                            if raw_tid not in (None, '', 'null'):
                                try:
                                    inferred_team_id = int(raw_tid)
                                except (TypeError, ValueError):
                                    inferred_team_id = None
                                if inferred_team_id:
                                    logger.info(
                                        f"[ChatbotEngine] last_routing_team_id={inferred_team_id} "
                                        f"(definido na linha do menu) conv={conversation_id}"
                                    )
                    if inferred_team_id is None:
                        inferred_team_id = ChatbotEngine._infer_team_id_from_path(
                            edge.get('target'), nodes, edges
                        )
                        if inferred_team_id:
                            logger.info(
                                f"[ChatbotEngine] last_routing_team_id={inferred_team_id} inferido no caminho "
                                f"para conv={conversation_id}"
                            )
                    if inferred_team_id:
                        flow_context['last_routing_team_id'] = int(inferred_team_id)

                    current_state['flow_context'] = flow_context
                    attempts = dict(current_state.get('invalid_option_attempts') or {})
                    attempts[current_node_id] = 0
                    current_state['invalid_option_attempts'] = attempts
                    await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")
                # === FIM da captura ===

                next_node = next((n for n in nodes if n.get('id') == edge.get('target')), None)
                logger.info(f"[ChatbotEngine] Aresta encontrada: {edge.get('id')} | target={edge.get('target')} | sourceHandle={edge.get('sourceHandle')} | next_node={'ENCONTRADO: ' + next_node.get('id') if next_node else 'NÃO ENCONTRADO'}")
                logger.info(f"[ChatbotEngine] IDs de nós disponíveis: {[n.get('id') for n in nodes]}")
            else:
                logger.warning(f"[ChatbotEngine] Nenhuma aresta saindo de {current_node_id}. Arestas disponíveis: {[(e.get('source'), e.get('target'), e.get('sourceHandle')) for e in edges]}")
            
            if not next_node:
                logger.warning(f"[ChatbotEngine] Nó atual {current_node_id} é um beco sem saída ou transição inválida. Resetando para o início.")
                current_node_id = None # Força reinício abaixo

        if not current_node_id:
            # Iniciar fluxo: procurar nó do tipo 'start'
            start_node = next((n for n in nodes if n.get('type') == 'start'), None)
            if start_node:
                logger.info(f"[ChatbotEngine] Iniciando novo fluxo para conv {conversation_id}")
                # Encontrar o primeiro nó conectado ao start
                edge = next((e for e in edges if e.get('source') == start_node.get('id')), None)
                if edge:
                    next_node = next((n for n in nodes if n.get('id') == edge.get('target')), None)
                else:
                    # Se o start não tiver aresta, talvez o próprio start seja executável (raro)
                    next_node = start_node

        if next_node:
            logger.info(f"[ChatbotEngine] Próximo nó encontrado: {next_node.get('id')} ({next_node.get('type')})")
            await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)
            return True, "Fluxo avançado/iniciado"
        
        logger.warning(f"[ChatbotEngine] Nenhum nó seguinte encontrado para conv {conversation_id}. Mensagem ignorada pelo Chatbot.")
        return False, "Nenhum nó seguinte encontrado"

    @staticmethod
    async def execute_node(provedor_id: int, conversation_id: int, node: Dict[str, Any], flow: ChatbotFlow):
        """
        Executa a ação de um nó específico (ex: enviar mensagem).
        """
        node_id = node.get('id')
        node_type = node.get('type')
        logger.info(f"[ChatbotEngine][TRACE] Executando nó {node_id} ({node_type}) para conv {conversation_id}")
        node_id = node.get('id')
        node_type = node.get('type')
        node_data = node.get('data', {})

        logger.info(f"[ChatbotEngine] Executando nó {node_id} ({node_type}) para conv {conversation_id}")

        if node_type in ['message', 'menu', 'planos']:
            try:
                # Obter contexto para substituição de variáveis
                existing_state = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
                flow_context = existing_state.get('flow_context', {})
                
                # Substituição Universal de Placeholders
                node_data_processed = ChatbotEngine._replace_placeholders(node_data, flow_context)
                logger.info(f"[ChatbotEngine] Node Data Processada: {json.dumps(node_data_processed, indent=2, ensure_ascii=False)}")
                
                content = node_data_processed.get('content')
                if not content or str(content).strip() == "":
                    # WhatsApp Cloud API exige corpo não vazio para mensagens interativas
                    content = "..."
                
                buttons = node_data_processed.get('buttons', [])
                rows = node_data_processed.get('rows', [])
                
                # Para nós do tipo 'planos', buscar planos ativos do banco dinamicamente
                if node_type == 'planos' and node_data.get('useDynamicPlanos'):
                    try:
                        from core.models import Plano
                        planos_ativos = await sync_to_async(
                            lambda: list(Plano.objects.filter(provedor_id=provedor_id, ativo=True).order_by('ordem', 'nome'))
                        )()
                        if planos_ativos:
                            rows = [
                                {
                                    'id': f'plano_{p.id}',
                                    'title': p.nome[:24],
                                    'description': f'{p.velocidade_download}Mbps - R$ {p.preco}'[:72]
                                }
                                for p in planos_ativos
                            ]
                            logger.info(f"[ChatbotEngine] Planos dinâmicos carregados: {len(rows)} planos ativos")
                        else:
                            logger.warning(f"[ChatbotEngine] Nenhum plano ativo encontrado para provedor {provedor_id}")
                    except Exception as e:
                        logger.error(f"[ChatbotEngine] Erro ao buscar planos dinâmicos: {e}", exc_info=True)
                button_text = node_data_processed.get('buttonText', 'Ver Opções')
                section_title = node_data_processed.get('sectionTitle', 'Selecione uma opção')
                header = node_data_processed.get('headerText') or node_data_processed.get('header')
                footer = node_data_processed.get('footerText') or node_data_processed.get('footer')
                
                from conversations.models import Conversation
                
                logger.info(f"[ChatbotEngine] Preparando envio de {node_type} para conversa {conversation_id} | Body length={len(content)}")
                
                conversation = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                
                success, response = await ChatbotEngine.send_message_agnostic(
                    conv=conversation, 
                    text=content, 
                    msg_btns=buttons, 
                    msg_header=header, 
                    msg_footer=footer,
                    msg_rows=rows,
                    msg_btn_text=button_text,
                    msg_sec_title=section_title
                )
                logger.info(f"[ChatbotEngine] Resultado do envio do nó {node_id}: success={success}, response={response}")

                if success:
                    # Atualizar estado no Redis
                    existing_state["chatbot_node_id"] = node_id
                    existing_state["flow_id"] = flow.id
                    await redis_memory_service.update_ai_state(
                        provedor_id, 
                        conversation_id, 
                        existing_state,
                        "whatsapp",
                        "unknown"
                    )
                    
                    # Verificar autoClose para nós message/menu
                    if node_data.get('autoClose'):
                        closing_msg = node_data.get('closingMessage')
                        if closing_msg and str(closing_msg).strip():
                            # Substituir placeholders na mensagem de encerramento
                            closing_msg_processed = ChatbotEngine._replace_placeholders(str(closing_msg), flow_context)
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=closing_msg_processed)
                            logger.info(f"[ChatbotEngine] Mensagem de encerramento enviada para conv {conversation_id}")
                        
                        await sync_to_async(stamp_automation_closure_trace)(conversation, 'chatbot_autoclose_message')
                        await sync_to_async(closing_service.request_closing)(conversation)
                        logger.info(f"[ChatbotEngine] Encerramento solicitado para conv {conversation_id} (nó {node_id})")
                    else:
                        # Se for um nó de MENSAGEM pura (sem botões interativos) e não estiver configurado para aguardar,
                        # avançamos automaticamente para o próximo nó para permitir encadeamento de balões.
                        if node_type == 'message' and not buttons and not rows and not node_data.get('waitForInput', False):
                            import asyncio
                            await asyncio.sleep(0.8) # Pequeno delay para fluidez/legibilidade
                            
                            edge = next((e for e in flow.edges if e.get('source') == node_id), None)
                            if edge:
                                next_node = next((n for n in flow.nodes if n.get('id') == edge.get('target')), None)
                                if next_node:
                                    # Proteção para blocos que requerem input ativo do usuário
                                    if next_node.get('type') == 'sgp':
                                        n_data = next_node.get('data', {})
                                        i_var = n_data.get('inputVar', 'cpf')
                                        sgp_action_next = n_data.get('sgpAction', '')
                                        # Se a variável requerida não está no contexto, NÃO avançar.
                                        # Forçamos o bot a parar e esperar o usuário digitar especificamente após a pergunta.
                                        if i_var and i_var != 'None' and i_var not in flow_context:
                                            logger.info(f"[ChatbotEngine] Auto-avanço cancelado: Próximo nó {next_node.get('id')} (sgp) requer entrada do usuário para '{i_var}'.")
                                            return
                                        # Para liberação por confiança, o CPF do usuário é obrigatório e deve vir do usuário agora.
                                        # Mesmo que 'contrato' já esteja no contexto (de consulta anterior), o CPF deve ter sido
                                        # digitado pelo usuário recentemente. Se não estiver no contexto, bloquear o auto-avanço.
                                        if sgp_action_next == 'liberar_por_confianca':
                                            cpf_disponivel = flow_context.get('cpf') or flow_context.get('cpfcnpj')
                                            if not cpf_disponivel:
                                                logger.info(f"[ChatbotEngine] Auto-avanço cancelado: Nó {next_node.get('id')} (liberar_por_confianca) requer CPF/CNPJ do usuário, que ainda não foi fornecido.")
                                                return

                                    logger.info(f"[ChatbotEngine] Auto-avanço: De {node_id} para {next_node.get('id')}")
                                    await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)
                        else:
                            # Casos que devem realmente esperar input: Menu interativo ou Mensagem com botões/listas
                            pass
            except Exception as e:
                logger.error(f"[ChatbotEngine] Erro crítico ao executar nó {node_id}: {e}", exc_info=True)

        elif node_type == 'condition':
            try:
                # Obter contexto
                current_state = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
                flow_context = current_state.get('flow_context', {})
                
                variable = node_data.get('variable')
                operator = node_data.get('operator', 'equals')
                value = node_data.get('value')
                
                actual_value = flow_context.get(variable)
                
                logger.info(f"[ChatbotEngine][Condition] Avaliando: {variable}({actual_value}) {operator} {value}")
                
                result = False
                if operator == 'equals':
                    result = str(actual_value).lower() == str(value).lower()
                elif operator == 'contains':
                    result = str(value).lower() in str(actual_value).lower()
                elif operator == 'exists':
                    result = actual_value is not None and actual_value != ''
                
                # Definir porta de saída (TRUE ou FALSE)
                handle = 'TRUE' if result else 'FALSE'
                logger.info(f"[ChatbotEngine][Condition] Resultado: {handle}")
                
                # Encontrar aresta correspondente ao handle
                edge = next((e for e in flow.edges if e.get('source') == node_id and e.get('sourceHandle') == handle), None)
                if edge:
                    next_node = next((n for n in flow.nodes if n.get('id') == edge.get('target')), None)
                    if next_node:
                        await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)
            except Exception as e:
                logger.error(f"[ChatbotEngine][Condition] Erro ao avaliar nó {node_id}: {e}")

        elif node_type == 'start':
            # Apenas pula para o próximo
            edges = flow.edges
            nodes = flow.nodes
            edge = next((e for e in edges if e.get('source') == node_id), None)
            if edge:
                next_node = next((n for n in nodes if n.get('id') == edge.get('target')), None)
                if next_node:
                    await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)

        elif node_type == 'sgp':
            try:
                sgp_action = node_data.get('sgpAction', 'consultar_cliente')
                logger.info(f"[ChatbotEngine][TRACE] Entrou nó SGP: conv={conversation_id} | action={sgp_action}")
                input_var = node_data.get('inputVar', 'cpf')
                error_message = node_data.get('errorMessage')
                if not error_message or str(error_message).strip() == "":
                    error_message = "Não foi possível consultar seus dados. Tente novamente."

                # Obter o domínio/conversa para enviar feedback ao usuário depois
                from conversations.models import Conversation
                conversation = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)

                # Ler estado atual do Redis para obter o valor da variável de entrada
                current_state = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
                flow_context = current_state.get('flow_context', {})
                input_value = flow_context.get(input_var) if input_var and input_var != 'None' else None

                # Fallback Inteligente: apenas para ações que aceitam contrato.
                # Para consultar_cliente, jamais usar contrato como fallback.
                if not input_value:
                    if sgp_action == 'consultar_cliente':
                        input_value = flow_context.get('cpf') or flow_context.get('cpfcnpj')
                    else:
                        input_value = flow_context.get('contrato') or flow_context.get('cpf') or flow_context.get('cpfcnpj')
                
                # Removido fallback de last_user_message aqui para evitar que 
                # seleções de menu (ex: "1", "2") sejam interpretadas como input do SGP acidentalmente.
                # O input deve vir do flow_context (preenchido na mensagem anterior) ou ser digitado agora.

                logger.info(f"[ChatbotEngine][SGP] Executando ação '{sgp_action}' com input='{input_value}' (var original: {input_var}) para conv {conversation_id}")

                if not input_value:
                    logger.warning(f"[ChatbotEngine][SGP] Variável '{input_var}' não encontrada no contexto. Saindo silenciosamente para aguardar input.")
                    return

                # Obter configurações do SGP do provedor (Robustez Unificada)
                provedor = conversation.inbox.provedor
                integracao = provedor.integracoes_externas or {}
                
                # Tentar buscar do objeto aninhado 'sgp' ou da raiz
                sgp_config = integracao.get('sgp', {}) if isinstance(integracao.get('sgp'), dict) else integracao
                
                sgp_url = sgp_config.get('sgp_url') or sgp_config.get('base_url') or integracao.get('sgp_url')
                sgp_token = sgp_config.get('sgp_token') or sgp_config.get('token') or integracao.get('sgp_token')
                sgp_app = sgp_config.get('sgp_app') or sgp_config.get('app') or integracao.get('sgp_app') or 'NioChat'

                if not sgp_url or not sgp_token:
                    logger.error(f"[ChatbotEngine][SGP] Configuração SGP incompleta para provedor {provedor_id}: url={bool(sgp_url)}, token={bool(sgp_token)}")
                    await ChatbotEngine.send_message_agnostic(conv=conversation, text=error_message)
                    return

                from core.sgp_client import SGPClient
                sgp = SGPClient(base_url=sgp_url, token=sgp_token, app_name=sgp_app)

                result = None
                result_context = {}

                # Despachar para o endpoint correto
                if sgp_action == 'consultar_cliente':
                    input_digits = re.sub(r'[^\d]', '', str(input_value or ''))
                    if len(input_digits) not in (11, 14):
                        logger.warning(
                            f"[ChatbotEngine][SGP] consultar_cliente bloqueado: CPF/CNPJ inválido ou ausente "
                            f"(input='{input_value}') na conversa {conversation_id}"
                        )
                        await ChatbotEngine.send_message_agnostic(
                            conv=conversation,
                            text="Para continuar, informe um CPF ou CNPJ valido (somente numeros)."
                        )
                        return

                    flow_context['cpf'] = input_digits
                    flow_context['cpfcnpj'] = input_digits
                    current_state['flow_context'] = flow_context
                    await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")

                    result = await sync_to_async(sgp.consultar_cliente)(input_digits)
                    if result:
                        contratos = result.get('contratos', [])
                        primeiro = contratos[0] if contratos else {}
                        # Nome vem dentro de contratos[0].razaoSocial (não na raiz!)
                        nome = (
                            result.get('razaoSocial') or result.get('nomeCliente') or result.get('nome') or
                            primeiro.get('razaoSocial') or primeiro.get('nomeCliente') or primeiro.get('nome', '')
                        )
                        nome_upper = nome.upper() if nome else 'CLIENTE'

                        # === FORMATAR E ENVIAR MENSAGEM DE CONTRATOS ===
                        if len(contratos) == 0:
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=f"❌ Nenhum contrato encontrado para o CPF/CNPJ informado.")
                            return

                        elif len(contratos) == 1:
                            c = contratos[0]
                            num = c.get('contratoId') or c.get('contrato_id') or c.get('contrato', '')
                            num_str = str(num).strip() if num is not None else ''
                            status = str(c.get('contratoStatusDisplay', '') or c.get('contratoStatus', '')).upper()
                            end = _formatar_endereco(c)
                            # Persistir ID do contrato no Redis já neste passo (antes do envio WA),
                            # para criar_chamado e outros nós SGP sempre encontrarem o contrato correto.
                            if num_str:
                                flow_context['contrato'] = num_str
                                flow_context['contrato_id'] = num_str
                                flow_context['sgp_contrato_id'] = num_str
                                current_state['flow_context'] = flow_context
                                await redis_memory_service.update_ai_state(
                                    provedor_id, conversation_id, current_state, "whatsapp", "unknown"
                                )
                                logger.info(
                                    f"[ChatbotEngine][SGP] consultar_cliente: contrato_id={num_str} "
                                    f"gravado no contexto antes da mensagem ao cliente."
                                )
                            texto = f"*{nome_upper}*, contrato localizado:\n\n1 - Contrato ({num}) - *{status}*\nEndereço: {end}"
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=texto)

                        else:
                            linhas = [f"*{nome_upper}*, encontramos mais de um contrato. Escolha o contrato desejado:"]
                            rows = []
                            for i, c in enumerate(contratos, 1):
                                num = c.get('contratoId') or c.get('contrato_id') or c.get('contrato', '')
                                status = str(c.get('contratoStatusDisplay', '') or c.get('contratoStatus', '')).upper()
                                end = _formatar_endereco(c)
                                linhas.append(f"{i} - Contrato ({num}) - *{status}*\nEndereço: {end}")
                                rows.append({
                                    'id': f'sgp_contrato_{num}',
                                    'title': f'Contrato {num}',
                                    'description': f"{status} - {end}"[:72]
                                })
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text="\n\n".join(linhas))
                            import asyncio
                            await asyncio.sleep(0.8)
                            await ChatbotEngine.send_message_agnostic(
                                conv=conversation,
                                text="Selecione o contrato desejado:",
                                msg_rows=rows,
                                msg_btn_text="Ver Contratos",
                                msg_sec_title="Meus Contratos"
                            )
                            # Salvar estado de seleção pendente
                            current_state2 = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
                            fc2 = current_state2.get('flow_context', {})
                            fc2['contratos_pendentes'] = contratos
                            fc2['nome'] = nome
                            current_state2['flow_context'] = fc2
                            current_state2['chatbot_node_id'] = f'sgp_select_{node_id}'
                            current_state2['flow_id'] = flow.id
                            await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state2, "whatsapp", "unknown")
                            return  # Aguardar seleção do usuário

                        # Contexto para 1 contrato (ou continuação após seleção)
                        num_contrato = str(
                            primeiro.get('contratoId') or primeiro.get('contrato_id') or
                            primeiro.get('id') or primeiro.get('contrato') or primeiro.get('numero') or primeiro.get('idContrato') or ''
                        )
                        result_context = {
                            'nome': nome,
                            'contratos': contratos,
                            'sgp_cliente': result,
                            'contrato': str(num_contrato),
                            'contrato_id': str(num_contrato),
                            'sgp_contrato_id': str(num_contrato),
                            'cliente_id': str(primeiro.get('cliente_id', '') or primeiro.get('clienteId', '')),
                            'status_contrato': str(primeiro.get('contratoStatus', '')),
                            'cidade': primeiro.get('popNome', '') or primeiro.get('endereco_cidade', ''),
                            'endereco': _formatar_endereco(primeiro),
                            'vencimento': primeiro.get('dataVencimento', '') or primeiro.get('data_vencimento', ''),
                        }
                        logger.info(f"[ChatbotEngine][SGP] Nome extraído: '{nome}' | Contrato: '{num_contrato}'")

                elif sgp_action == 'verifica_acesso':
                    result = await sync_to_async(sgp.verifica_acesso)(input_value)
                    if result:
                        result_context = {
                            'status_acesso': result.get('status') or result.get('status_conexao', ''),
                            'sgp_acesso': result
                        }

                elif sgp_action == 'listar_contratos':
                    result = await sync_to_async(sgp.listar_contratos)(input_value)
                    result_context = {'contratos': result, 'sgp_contratos': result}


                elif sgp_action == 'listar_titulos':
                    from .fatura_service import fatura_service as fs
                    
                    # Prioridade: usar o input_value (que é o que o usuário acabou de informar no nó ou variável mapeada)
                    # Se input_value parecer um CPF (11 dígitos), usamos ele primariamente como CPF
                    input_limpo = ''.join(filter(str.isdigit, str(input_value))) if input_value else ''
                    
                    if len(input_limpo) in (11, 14):
                        cpf_ctx = input_limpo
                        # Mantemos o contrato do contexto se existir, para filtrar faturas desse contrato específico
                        contrato_id_ctx = flow_context.get('contrato') or flow_context.get('contrato_id')
                    else:
                        # Se não for CPF, o valor digitado/mapeado é o próprio ID do contrato
                        contrato_id_ctx = input_limpo or flow_context.get('contrato') or flow_context.get('contrato_id')
                        cpf_ctx = flow_context.get('cpf') or flow_context.get('cpfcnpj')

                    logger.warning(f"[ChatbotEngine][DEBUG] listar_titulos | CPF={cpf_ctx} | Contrato={contrato_id_ctx} | flow_context_keys={list(flow_context.keys())} | input_var={input_var} | input_value='{input_value}'")
                    
                    # Buscar fatura usando o serviço unificado (síncrono, rodando via sync_to_async)
                    dados_fatura = await sync_to_async(fs.buscar_fatura_sgp)(provedor, cpf_ctx, contrato_id_ctx)
                    
                    if not dados_fatura:
                        logger.error(f"[ChatbotEngine][SGP] buscar_fatura_sgp retornou None para CPF={cpf_ctx}")
                        dados_fatura = {'status': -1, 'error': 'Erro na comunicação ou SGP fora do ar.'}

                    logger.info(f"[ChatbotEngine][SGP] listar_titulos | Resultado status={dados_fatura.get('status')}")
                    
                    if dados_fatura:
                        # Se encontramos faturas (status=1), enviar ao cliente IMEDIATAMENTE usando o serviço robusto
                        if dados_fatura.get('status') == 1:
                            # Preferir configuração explícita do nó SGP.
                            # Isso evita herdar PIX do contexto quando o bloco está fixado como "Apenas Boleto".
                            tipo_pagamento = (
                                node_data.get('paymentMethod') or
                                node_data.get('tipoPagamento') or
                                flow_context.get('tipo_pagamento') or
                                flow_context.get('metodo_pagamento') or
                                'pix'
                            )
                            numero_wa = conversation.contact.phone
                            
                            logger.info(f"[ChatbotEngine][SGP] BLOCO ENVIAR: conv={conversation_id} | WA={numero_wa} | tipo_pagamento={tipo_pagamento} (ctx={flow_context.get('tipo_pagamento')} node={node_data.get('tipoPagamento')})")
                            # Enviar via serviço que suporta tanto Cloud API quanto Uazapi
                            envio_res = await sync_to_async(fs.enviar_fatura)(provedor, numero_wa, dados_fatura, conversation=conversation, tipo_pagamento=tipo_pagamento)
                            logger.info(f"[ChatbotEngine][SGP] BLOCO ENVIAR: Resultado final: {envio_res}")
                            
                            result_context = {
                                'status_faturas': 'encontrada',
                                'sgp_titulos': dados_fatura
                            }
                        elif dados_fatura.get('mensagem_positiva'):
                            # Caso onde todas estão pagas (Parabéns!)
                            msg_positiva = dados_fatura.get('mensagem', 'Parabéns! Todas as suas faturas estão pagas.')
                            logger.info(f"[ChatbotEngine][SGP] BLOCO POSITIVO: {msg_positiva}")
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=msg_positiva)
                            result_context = {
                                'status_faturas': 'em_dia',
                                'sgp_titulos': dados_fatura
                            }
                        elif dados_fatura.get('status') == 2:
                            # Caso de múltiplas faturas vencidas -> Notificar e sugerir/fazer transferência
                            msg_transfer = dados_fatura.get('mensagem', 'Você possui múltiplas faturas vencidas.')
                            logger.info(f"[ChatbotEngine][SGP] BLOCO TRANSFERÊNCIA: {msg_transfer}")
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=msg_transfer)
                            
                            if dados_fatura.get('solicitar_transferencia'):
                                # Tentar transferir para o setor especificado
                                setor = dados_fatura.get('setor', 'financeiro')
                                logger.info(f"[ChatbotEngine][SGP] Solicitando transferência para o setor: {setor}")
                                # Aqui poderíamos chamar um serviço de transferência se disponível
                                # Por enquanto, o chatbot apenas avisou o usuário.
                            
                            result_context = {
                                'status_faturas': 'multiplas_vencidas',
                                'sgp_titulos': dados_fatura
                            }
                        else:
                            logger.info(f"[ChatbotEngine][SGP] BLOCO OUTRO: status={dados_fatura.get('status')}")
                            result_context = {'status_faturas': 'error', 'sgp_titulos': dados_fatura}
                    else:
                        logger.warn(f"[ChatbotEngine][SGP] dados_fatura é NONE para conv {conversation_id}")
                        result_context = {'status_faturas': 'error', 'sgp_titulos': None}

                    # Auto Close if applicable
                    auto_close = node_data.get('autoClose', False)
                    if result_context.get('status_faturas') != 'error' and auto_close:
                        closing_msg = node_data.get('closingMessage')
                        if closing_msg and str(closing_msg).strip():
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=str(closing_msg))
                        
                        if auto_close:
                            closing_msg = node_data.get('closingMessage')
                            if closing_msg and str(closing_msg).strip():
                                await ChatbotEngine.send_message_agnostic(conv=conversation, text=str(closing_msg))
                                logger.info(f"[ChatbotEngine][SGP] Mensagem de encerramento enviada para conv {conversation_id}")
                            await sync_to_async(stamp_automation_closure_trace)(conversation, 'chatbot_sgp_autoclose')
                            await sync_to_async(closing_service.request_closing)(conversation)
                            logger.info(f"[ChatbotEngine][SGP] Encerramento solicitado para conv {conversation_id}")

                elif sgp_action == 'liberar_por_confianca':
                    # Garantir que o CPF usado na liberação seja o mais atual
                    input_limpo = re.sub(r'[^\d]', '', str(input_value))

                    # Verificação crítica: o CPF/CNPJ do usuário é obrigatório para a liberação.
                    # O input_value pode vir do fallback com o número do contrato anterior.
                    # Precisamos garantir que o CPF foi especificamente digitado pelo usuário.
                    cpf_ctx_check = flow_context.get('cpf') or flow_context.get('cpfcnpj')
                    if len(input_limpo) not in (11, 14) and not cpf_ctx_check:
                        # Não temos CPF/CNPJ — aguardar input do usuário
                        logger.warning(
                            f"[ChatbotEngine][SGP] liberar_por_confianca: CPF/CNPJ não disponível no contexto "
                            f"(input_limpo='{input_limpo}', cpf_ctx='{cpf_ctx_check}'). "
                            f"Aguardando input do usuário."
                        )
                        return

                    if len(input_limpo) in (11, 14):
                        cpf_ctx = input_limpo
                        logger.info(f"[ChatbotEngine][SGP] CPF/CNPJ detectado ({len(input_limpo)} dígitos) na liberação. Buscando Contrato ID real...")
                        contrato_final = input_limpo
                        try:
                            # Tentar buscar via fatura2via (que retorna o contrato ID)
                            faturas_res = await sync_to_async(sgp.listar_faturas_v2)(cpf_cnpj=input_limpo)
                            if faturas_res:
                                contrato_final = _sgp_contrato_id_from_fatura2via_response(faturas_res, input_limpo)
                                if contrato_final != input_limpo:
                                    logger.info(f"[ChatbotEngine][SGP] Contrato ID descoberto via fatura2via para liberação: {contrato_final}")
                        except Exception as e:
                            logger.error(f"[ChatbotEngine][SGP] Erro ao buscar contrato por CPF via fatura2via na liberação: {e}")
                    else:
                        cpf_ctx = cpf_ctx_check or ''
                        contrato_final = input_limpo

                    logger.info(f"[ChatbotEngine][SGP] liberar_por_confianca | Contrato={contrato_final} | CPF={cpf_ctx}")
                    result = await sync_to_async(sgp.liberar_por_confianca)(contrato_final, cpf_cnpj=cpf_ctx)
                    
                    if result:
                        sucesso = result.get('status') == 1 or result.get('liberado') == True
                        protocolo = result.get('protocolo', '')
                        dias = result.get('liberado_dias', 0)
                        
                        result_context = {
                            'sucesso': sucesso,
                            'protocolo': protocolo,
                            'liberado_dias': dias,
                            'sgp_liberacao': result
                        }
                        
                        if sucesso:
                            custom_msg = node_data.get('successMessage')
                            if custom_msg and str(custom_msg).strip():
                                msg_confirmacao = str(custom_msg).replace('{protocolo}', str(protocolo)).replace('{liberado_dias}', str(dias))
                            else:
                                # Fallback padrão
                                msg_confirmacao = f"Sua liberação por confiança foi realizada com sucesso! Seu serviço estará disponível por mais {dias} dias. Protocolo: {protocolo}"
                            
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=msg_confirmacao)
                            logger.info(f"[ChatbotEngine][SGP] Feedback de liberação enviado. Protocolo: {protocolo}")
                            
                            if node_data.get('autoClose'):
                                closing_msg = node_data.get('closingMessage')
                                if closing_msg and str(closing_msg).strip():
                                    await ChatbotEngine.send_message_agnostic(conv=conversation, text=str(closing_msg))
                                    logger.info(f"[ChatbotEngine][SGP] Mensagem de encerramento enviada após liberação para conv {conversation_id}")
                                await sync_to_async(stamp_automation_closure_trace)(conversation, 'chatbot_sgp_liberacao_autoclose')
                                await sync_to_async(closing_service.request_closing)(conversation)
                                logger.info(f"[ChatbotEngine][SGP] Encerramento solicitado após liberação para conv {conversation_id}")
                        else:
                            # Caso onde NÃO foi liberado (pode ser atingido o limite)
                            limit_msg = node_data.get('limitReachedMessage')
                            sgp_msg = result.get('mensagem') or result.get('msg')
                            
                            logger.info(f"[ChatbotEngine][SGP] Liberação negada. status={result.get('status')} | sgp_msg={sgp_msg}")
                            
                            if limit_msg and str(limit_msg).strip():
                                await ChatbotEngine.send_message_agnostic(conv=conversation, text=str(limit_msg))
                            elif sgp_msg:
                                await ChatbotEngine.send_message_agnostic(conv=conversation, text=str(sgp_msg))
                            else:
                                await ChatbotEngine.send_message_agnostic(conv=conversation, text="Não foi possível realizar a liberação por confiança no momento.")
                    else:
                        result_context = {'sucesso': False, 'sgp_liberacao': None}

                elif sgp_action == 'criar_chamado':
                    tipo_oc = _parse_ocorrenciatipo_node(node_data)
                    if tipo_oc is None:
                        err_txt = (node_data.get('errorMessage') or '').strip() or (
                            "Configure o ID do tipo de ocorrência no bloco Consulta SGP (ação Criar chamado técnico) e salve o fluxo."
                        )
                        await ChatbotEngine.send_message_agnostic(conv=conversation, text=err_txt)
                        return

                    # Descrição do chamado: priorizar texto configurado no nó (evita usar só o título do menu).
                    conteudo_cfg_raw = node_data.get('content', '')
                    conteudo_cfg = str(conteudo_cfg_raw).strip() if conteudo_cfg_raw else ''
                    conteudo = conteudo_cfg or flow_context.get('conteudo') or 'Chamado via Chatbot NioChat'
                    
                    # Substituir placeholders se houver
                    conteudo = ChatbotEngine._replace_placeholders(conteudo, flow_context)
                    
                    logger.info(f"[ChatbotEngine][SGP] Criando chamado com conteúdo: {conteudo}")
                    
                    # Garantir que o contrato seja apenas números se for criação de chamado
                    input_limpo = re.sub(r'[^\d]', '', str(input_value))
                    ctx_raw = (
                        flow_context.get('sgp_contrato_id')
                        or flow_context.get('contrato_id')
                        or flow_context.get('contrato')
                        or ''
                    )
                    ctx_contrato_limpo = re.sub(r'[^\d]', '', str(ctx_raw))

                    # 1) Preferir contrato já resolvido no fluxo (ex.: consultar_cliente gravou contratoId=2121)
                    if ctx_contrato_limpo and ctx_contrato_limpo != input_limpo:
                        contrato_final = ctx_contrato_limpo
                    elif ctx_contrato_limpo and len(ctx_contrato_limpo) not in (11, 14):
                        contrato_final = ctx_contrato_limpo
                    else:
                        contrato_final = input_limpo

                    # 2) Se ainda é CPF (11) ou CNPJ (14), resolver ID via fatura2via (links ou contratoId na raiz)
                    if len(contrato_final) in (11, 14):
                        logger.info(
                            f"[ChatbotEngine][SGP] Documento ({len(contrato_final)} dígitos) para chamado. "
                            f"Buscando contrato ID via fatura2via..."
                        )
                        try:
                            faturas_res = await sync_to_async(sgp.listar_faturas_v2)(cpf_cnpj=contrato_final)
                            novo = _sgp_contrato_id_from_fatura2via_response(faturas_res, contrato_final)
                            if novo != contrato_final:
                                logger.info(f"[ChatbotEngine][SGP] Contrato ID para chamado via fatura2via: {novo}")
                            contrato_final = novo
                        except Exception as e:
                            logger.error(f"[ChatbotEngine][SGP] Erro ao buscar contrato via fatura2via: {e}")
                    
                    result = await sync_to_async(sgp.criar_chamado)(contrato_final, conteudo, ocorrenciatipo=tipo_oc)
                    if result:
                        result_context = {
                            'protocolo': result.get('protocolo', ''),
                            'chamado_id': result.get('chamado_id', ''),
                            'sucesso': result.get('success', False),
                            'sgp_chamado': result
                        }
                        
                        # 🚨 REGRA DE OURO: Feedback automático de protocolo no Chatbot
                        if result.get('success') and result.get('protocolo'):
                            protocolo = result.get('protocolo')
                            
                            # Tentar descobrir para qual equipe vamos transferir (para o feedback ser mais natural)
                            equipe_nome = "nossa equipe técnica"
                            try:
                                next_nodes_ids = [e.get('target') for e in flow.edges if e.get('source') == node_id]
                                if next_nodes_ids:
                                    target_node = next((n for n in flow.nodes if n.get('id') == next_nodes_ids[0]), None)
                                    if target_node and target_node.get('type') == 'transfer':
                                        team_id = target_node.get('data', {}).get('teamId')
                                        if team_id:
                                            from conversations.models import Team
                                            team_obj = await sync_to_async(Team.objects.filter(id=team_id).first)()
                                            if team_obj:
                                                equipe_nome = team_obj.name
                            except Exception as e:
                                logger.warning(f"[ChatbotEngine][SGP] Erro ao tentar descobrir nome da equipe: {e}")

                            # Permitir que o usuário personalize a mensagem de sucesso no nó
                            custom_msg = node_data.get('successMessage')
                            if custom_msg and str(custom_msg).strip():
                                msg_confirmacao = str(custom_msg).replace('{protocolo}', str(protocolo)).replace('{equipe}', equipe_nome)
                            else:
                                # Fallback para mensagem padrão (Sugerido pelo usuário)
                                msg_confirmacao = f"Chamado técnico registrado (Protocolo: {protocolo}). Estou te transferindo agora para a equipe {equipe_nome}, que dará continuidade ao atendimento. Só um instante!"
                            
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=msg_confirmacao)
                            logger.info(f"[ChatbotEngine][SGP] Feedback automático de protocolo enviado: {protocolo}")
                        elif not result.get('success'):
                            # Se falhou, avisar o usuário usando a mensagem de erro do nó
                            await ChatbotEngine.send_message_agnostic(conv=conversation, text=error_message)
                            return # Interrompe o avanço se falhar a criação crítica

                elif sgp_action == 'listar_manutencoes':
                    result = await sync_to_async(sgp.listar_manutencoes)(input_value)
                    result_context = {'manutencoes': result, 'sgp_manutencoes': result}

                logger.info(f"[ChatbotEngine][SGP] Resultado ação '{sgp_action}': {list(result_context.keys())}")

                if result is None and result_context == {}:
                    # Consulta falhou ou retornou vazio
                    await ChatbotEngine.send_message_agnostic(conv=conversation, text=error_message)
                    return

                # Salvar resultado no contexto do Redis
                flow_context.update(result_context)
                current_state['flow_context'] = flow_context
                current_state['chatbot_node_id'] = node_id
                current_state['flow_id'] = flow.id
                await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")

                # Avançar automaticamente para o próximo nó
                # (SGP é um nó de processo, deve sempre avançar se houver conexão)
                import asyncio
                edge = next((e for e in flow.edges if e.get('source') == node_id), None)
                if edge:
                    next_node = next((n for n in flow.nodes if n.get('id') == edge.get('target')), None)
                    if next_node:
                        # Delay de 1s conforme solicitado para fluidez
                        await asyncio.sleep(1.0)
                        logger.info(f"[ChatbotEngine][SGP] Avançando automaticamente de {node_id} para {next_node.get('id')} ({next_node.get('type')})")
                        
                        # Executa o próximo nó (execute_node agora cuida de placeholders internamente)
                        try:
                            await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)
                        except Exception as next_err:
                            logger.error(f"[ChatbotEngine][SGP] Erro ao executar nó seguinte {next_node.get('id')}: {next_err}")
                    else:
                        logger.warning(f"[ChatbotEngine][SGP] Próximo nó {edge.get('target')} não encontrado.")
                else:
                    logger.info(f"[ChatbotEngine][SGP] Nenhum nó de saída encontrado após SGP {node_id}.")

            except Exception as e:
                logger.error(f"[ChatbotEngine][SGP] Erro ao executar nó SGP {node_id}: {e}", exc_info=True)

        elif node_type == 'transfer':
            try:
                transfer_mode = node_data.get('transferMode', 'choice') # 'direct' ou 'choice'
                team_id = node_data.get('teamId')
                content = node_data.get('content', 'Aguarde um momento, estamos transferindo seu atendimento...')
                
                from conversations.models import Conversation, Team
                conversation = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                
                # 1. Enviar mensagem de aviso
                if content:
                    await ChatbotEngine.send_message_agnostic(conv=conversation, text=content)

                if transfer_mode == 'direct' and team_id:
                    # Transferência Direta
                    logger.info(f"[ChatbotEngine][Transfer] Iniciando transferência direta para equipe {team_id}")
                    team = await sync_to_async(Team.objects.get)(id=team_id)
                    
                    # Verificar horário
                    horario_info = verificar_horario_atendimento(conversation.inbox.provedor)
                    if not horario_info.get('dentro_horario'):
                        proximo = horario_info.get('proximo_horario')
                        aviso = f"\n\n🚨 *Ateção:* No momento estamos fora do nosso horário de atendimento. Nossa equipe de *{team.name}* falará com você a partir de *{proximo}*." if proximo else f"\n\n🚨 *Atenção:* No momento estamos fora do nosso horário de atendimento. Nossa equipe de *{team.name}* falará com você assim que possível."
                        # Se já enviamos o 'content' acima, enviamos o aviso separado para destaque
                        await ChatbotEngine.send_message_agnostic(conv=conversation, text=aviso)

                    conversation.status = 'pending'
                    conversation.team = team
                    conversation.assignee = None
                    conversation.waiting_for_agent = True # Libera para visualização humana
                    await sync_to_async(conversation.save)() # Salva tudo para garantir persistência
                    
                    # Limpar estado para encerrar o fluxo (humano assume)
                    await redis_memory_service.clear_memory(provedor_id, conversation_id, "whatsapp", "unknown")
                    logger.info(f"[ChatbotEngine][Transfer] Transferência direta CONCLUÍDA para {team.name}")
                
                elif transfer_mode == 'choice':
                    # Listar equipes do provedor
                    provedor = conversation.inbox.provedor
                    teams = await sync_to_async(list)(Team.objects.filter(provedor=provedor, is_active=True).exclude(name="IA"))
                    
                    if not teams:
                        logger.warning(f"[ChatbotEngine][Transfer] Nenhuma equipe encontrada para o provedor {provedor_id}")
                        conversation.status = 'pending' # Abre geral (fila de espera) se não houver equipes
                        await sync_to_async(conversation.save)()
                        await redis_memory_service.clear_memory(provedor_id, conversation_id, "whatsapp", "unknown")
                        return

                    rows = []
                    for t in teams[:10]:
                        rows.append({
                            'id': f'team_{t.id}',
                            'title': t.name[:24],
                            'description': (t.description or 'Falar com atendente')[:72]
                        })
                    
                    await ChatbotEngine.send_message_agnostic(
                        conv=conversation,
                        text="Por favor, selecione o setor desejado:",
                        msg_rows=rows,
                        msg_btn_text="Ver Setores",
                        msg_sec_title="Setores Disponíveis"
                    )
                    
                    # Salvar estado de aguardando seleção
                    current_state = await redis_memory_service.get_ai_state(provedor_id, conversation_id, "whatsapp", "unknown")
                    current_state['chatbot_node_id'] = f'transfer_select_{node_id}'
                    await redis_memory_service.update_ai_state(provedor_id, conversation_id, current_state, "whatsapp", "unknown")
                    logger.info(f"[ChatbotEngine][Transfer] Aguardando seleção de equipe na conv {conversation_id}")
            
            except Exception as e:
                logger.error(f"[ChatbotEngine][Transfer] Erro ao executar nó de transferência: {e}", exc_info=True)

        elif node_type == 'galeria':
            try:
                from conversations.models import Conversation
                from core.models import ProviderGalleryImage

                conversation = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                image_id = node_data.get('galleryImageId')
                caption = (node_data.get('content') or '').strip()

                if not image_id:
                    logger.warning(f"[ChatbotEngine][Galeria] Nó {node_id} sem galleryImageId.")
                    return

                gallery_image = await sync_to_async(ProviderGalleryImage.objects.filter(
                    id=image_id,
                    provedor_id=provedor_id,
                    ativo=True
                ).first)()

                if not gallery_image:
                    logger.warning(f"[ChatbotEngine][Galeria] Imagem {image_id} não encontrada para provedor {provedor_id}.")
                    return

                await ChatbotEngine.send_gallery_image_agnostic(conversation, gallery_image, caption)

                edge = next((e for e in flow.edges if e.get('source') == node_id), None)
                if edge:
                    next_node = next((n for n in flow.nodes if n.get('id') == edge.get('target')), None)
                    if next_node:
                        await ChatbotEngine.execute_node(provedor_id, conversation_id, next_node, flow)
            except Exception as e:
                logger.error(f"[ChatbotEngine][Galeria] Erro ao executar nó {node_id}: {e}", exc_info=True)

        elif node_type == 'close':
            try:
                content = node_data.get('content', 'Atendimento encerrado. Obrigado!')
                from conversations.models import Conversation
                conversation = await sync_to_async(Conversation.objects.select_related('inbox', 'inbox__provedor', 'contact').get)(id=conversation_id)
                
                # 1. Enviar mensagem de despedida
                if content:
                    await ChatbotEngine.send_message_agnostic(conv=conversation, text=content)
                
                # 2. Encerrar conversa usando o closing_service
                await sync_to_async(stamp_automation_closure_trace)(conversation, 'chatbot_close_node')
                await sync_to_async(closing_service.request_closing)(conversation)
                
                # 3. Limpar memória para garantir que o fluxo pare aqui
                await redis_memory_service.clear_memory(provedor_id, conversation_id, "whatsapp", "unknown")
                logger.info(f"[ChatbotEngine][Close] Encerramento solicitado para conv {conversation_id}")
                
            except Exception as e:
                logger.error(f"[ChatbotEngine][Close] Erro ao encerrar atendimento: {e}", exc_info=True)

    @staticmethod
    def _extract_wamid_from_cloud_response(response: Any) -> Optional[str]:
        """Extrai wamid da resposta da WhatsApp Cloud API (JSON dict ou string)."""
        if response is None:
            return None
        data = None
        if isinstance(response, dict):
            data = response
        elif isinstance(response, str):
            try:
                data = json.loads(response)
            except (json.JSONDecodeError, TypeError):
                data = None
        if isinstance(data, dict):
            messages = data.get("messages") or []
            if messages and isinstance(messages[0], dict):
                mid = messages[0].get("id")
                if mid:
                    return str(mid)[:255]
        if isinstance(response, str):
            id_patterns = [
                r'"id":\s*"([^"]+)"',
                r"'id':\s*'([^']+)'",
                r'wamid\.[A-Za-z0-9_=+/\-]+',
            ]
            for pattern in id_patterns:
                match = re.search(pattern, response)
                if match:
                    raw = match.group(1) if match.lastindex else match.group(0)
                    return str(raw)[:255]
        return None

    @staticmethod
    async def _sync_cloud_wamid_to_message(message_id: Optional[int], response: Any) -> None:
        """Grava external_id (wamid) na mensagem persistida para replies do cliente resolverem no webhook."""
        if not message_id:
            return
        wamid = ChatbotEngine._extract_wamid_from_cloud_response(response)
        if not wamid:
            return

        def _upd():
            from conversations.models import Message
            try:
                m = Message.objects.only("id", "external_id", "additional_attributes").get(pk=message_id)
            except Message.DoesNotExist:
                return
            if m.external_id:
                return
            attrs = dict(m.additional_attributes or {})
            attrs["external_id"] = wamid
            attrs["whatsapp_message_id"] = wamid
            m.external_id = wamid
            m.additional_attributes = attrs
            m.save(update_fields=["external_id", "additional_attributes"])

        await sync_to_async(_upd)()

    @staticmethod
    async def _persist_chatbot_message(conv, content_for_db, msg_btns=None, msg_rows=None):
        """
        Salva a mensagem do chatbot no banco de dados e emite via WebSocket.
        Isso garante que as mensagens apareçam no ChatArea e na auditoria.
        Retorna a instância Message ou None se falhar.
        """
        try:
            from conversations.models import Message
            from channels.layers import get_channel_layer
            import json as _json

            # Montar conteúdo para exibição no ChatArea
            display_content = content_for_db or ''
            additional_attrs = {
                'from_ai': True,
                'sent_via': 'chatbot_engine',
                'sender_type': 'bot',
            }

            # Se tiver botões/rows, salvar info extra para renderização
            if msg_btns:
                additional_attrs['interactive_buttons'] = msg_btns
            if msg_rows:
                additional_attrs['interactive_rows'] = msg_rows

            msg_obj = await sync_to_async(Message.objects.create)(
                conversation=conv,
                content=display_content,
                message_type='text',
                is_from_customer=False,
                additional_attributes=additional_attrs
            )
            logger.info(f"[ChatbotEngine] Mensagem do chatbot salva no banco: id={msg_obj.id}, conv={conv.id}")

            # Broadcast via WebSocket para o ChatArea receber em tempo real
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    from django.utils import timezone as tz
                    await channel_layer.group_send(
                        f"conversation_{conv.id}",
                        {
                            "type": "chat_message",
                            "message": {
                                "id": msg_obj.id,
                                "content": display_content,
                                "message_type": "text",
                                "is_from_customer": False,
                                "created_at": msg_obj.created_at.isoformat() if msg_obj.created_at else tz.now().isoformat(),
                                "sender": {"sender_type": "bot"},
                                "from_ai": True,
                                "additional_attributes": additional_attrs,
                            },
                            "sender": {"sender_type": "bot"},
                        }
                    )
                    logger.debug(f"[ChatbotEngine] WebSocket broadcast enviado para conversation_{conv.id}")
            except Exception as ws_err:
                logger.warning(f"[ChatbotEngine] Falha no WebSocket broadcast (não crítico): {ws_err}")

            return msg_obj
        except Exception as db_err:
            logger.error(f"[ChatbotEngine] Erro ao salvar mensagem do chatbot no banco: {db_err}", exc_info=True)
            return None

    @staticmethod
    async def send_message_agnostic(conv, text, msg_btns=None, msg_header=None, msg_footer=None, msg_rows=None, msg_btn_text=None, msg_sec_title=None) -> Tuple[bool, Any]:
        """
        Helper para enviar mensagem baseada na integração (WhatsApp Cloud, Uazapi).
        Persiste no banco ANTES de enviar para garantir experiência em tempo real.
        """
        inbox = conv.inbox
        provedor = inbox.provedor
        
        logger.info(f"[ChatbotEngine] Processando envio de mensagem para inbox {inbox.id} | Texto: {text[:100]}...")

        # Persistir no banco ANTES do envio real para garantir exibição instantânea no painel
        # Isso elimina o atraso causado pela latência da API externa
        msg_obj = await ChatbotEngine._persist_chatbot_message(conv, text, msg_btns, msg_rows)

        success = False
        response = None

        # 1. WhatsApp Cloud API (Oficial)
        if inbox.channel_id == "whatsapp_cloud_api" or inbox.channel_type == "whatsapp_oficial" or (provedor.integracoes_externas.get('cloud_api_active') == True):
            if msg_btns or msg_rows:
                success, response = await sync_to_async(send_via_whatsapp_cloud_api)(
                    conversation=conv,
                    content=text,
                    message_type='interactive',
                    buttons=msg_btns,
                    rows=msg_rows,
                    button_text=msg_btn_text,
                    section_title=msg_sec_title,
                    header=msg_header,
                    footer=msg_footer
                )
            else:
                success, response = await sync_to_async(send_via_whatsapp_cloud_api)(
                    conversation=conv,
                    content=text,
                    message_type='text'
                )
            if success and msg_obj:
                await ChatbotEngine._sync_cloud_wamid_to_message(msg_obj.id, response)
            return success, response

        # 2. Uazapi
        uazapi_token = provedor.integracoes_externas.get('whatsapp_token')
        uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
        uazapi_instance = provedor.integracoes_externas.get('whatsapp_instance')
        
        if uazapi_token and uazapi_url:
            # Garantir URL correta (send/text)
            if not uazapi_url.endswith('/send/text'):
                base_url = uazapi_url.rstrip('/')
                # Tentar reconstruir se for apenas a base
                if '/instance/' in uazapi_url:
                    # Já parece ser uma URL completa mas talvez sem o final
                    pass
                else:
                    uazapi_url = f"{base_url}/message/sendText/{uazapi_instance}"
            
            payload = {
                "number": conv.contact.phone.replace('@s.whatsapp.net', '').replace('@c.us', ''),
            }
            
            if msg_btns or msg_rows:
                # Evolution/Uazapi suporte a botões varia, usando texto simples como fallback se não for Evolution v2
                all_items = (msg_btns or []) + (msg_rows or [])
                btn_text = text + "\n\n" + "\n".join([f"• {b['title']}" for b in all_items])
                payload["text"] = btn_text
            else:
                payload["text"] = text
                
            headers = {
                "apikey": uazapi_token, # Evolution usa apikey
                "token": uazapi_token,  # Uazapi usa token
                "Content-Type": "application/json"
            }
            
            try:
                # Tenta enviar via Uazapi
                resp = await sync_to_async(requests.post)(
                    uazapi_url,
                    json=payload,
                    headers=headers,
                    timeout=15
                )
                success = resp.status_code in [200, 201]
                response = resp.text
                return success, response
            except Exception as e:
                logger.error(f"[ChatbotEngine] Erro ao enviar Uazapi: {e}")
                return False, str(e)
        
        return False, "Nenhuma integração compatível encontrada"
    
    @staticmethod
    async def send_message_agnostic_document(conv, text, file_url, file_name=None) -> Tuple[bool, Any]:
        """Envia um documento (PDF, etc) via Cloud API ou Uazapi."""
        inbox = conv.inbox
        provedor = inbox.provedor
        
        if inbox.channel_id == "whatsapp_cloud_api" or inbox.channel_type == "whatsapp_oficial" or (provedor.integracoes_externas.get('cloud_api_active') == True):
            return await sync_to_async(send_via_whatsapp_cloud_api)(
                conversation=conv,
                content=text,
                message_type='document',
                file_url=file_url,
                file_name=file_name
            )
        # Uazapi fallback placeholder
        return await ChatbotEngine.send_message_agnostic(conv, f"{text}\n\nLink: {file_url}")

    @staticmethod
    async def _persist_chatbot_image_message(conv, content_for_db, file_url, display_file_name=None):
        try:
            from conversations.models import Message
            from channels.layers import get_channel_layer
            from django.utils import timezone as tz

            fname = (display_file_name or "chatbot_gallery_image").strip() or "chatbot_gallery_image"
            if len(fname) > 250:
                fname = fname[:250]

            msg_obj = await sync_to_async(Message.objects.create)(
                conversation=conv,
                content=content_for_db or '',
                message_type='image',
                is_from_customer=False,
                file_url=file_url,
                file_name=fname,
                additional_attributes={
                    'from_ai': True,
                    'sent_via': 'chatbot_gallery',
                    'sender_type': 'bot',
                },
            )

            channel_layer = get_channel_layer()
            if channel_layer:
                await channel_layer.group_send(
                    f"conversation_{conv.id}",
                    {
                        "type": "chat_message",
                        "message": {
                            "id": msg_obj.id,
                            "content": msg_obj.content,
                            "message_type": "image",
                            "is_from_customer": False,
                            "created_at": msg_obj.created_at.isoformat() if msg_obj.created_at else tz.now().isoformat(),
                            "sender": {"sender_type": "bot"},
                            "from_ai": True,
                            "file_url": file_url,
                            "additional_attributes": msg_obj.additional_attributes or {},
                        },
                        "sender": {"sender_type": "bot"},
                    }
                )
            return msg_obj
        except Exception as db_err:
            logger.error(f"[ChatbotEngine][Galeria] Erro ao persistir imagem: {db_err}", exc_info=True)
            return None

    @staticmethod
    async def send_gallery_image_agnostic(conv, gallery_image, caption='') -> Tuple[bool, Any]:
        inbox = conv.inbox
        provedor = inbox.provedor
        panel_url = await sync_to_async(_copy_provider_gallery_to_conversation_media)(conv, gallery_image)
        msg_obj = await ChatbotEngine._persist_chatbot_image_message(
            conv, caption, panel_url, display_file_name=gallery_image.nome
        )

        if inbox.channel_id == "whatsapp_cloud_api" or inbox.channel_type == "whatsapp_oficial" or (provedor.integracoes_externas.get('cloud_api_active') is True):
            success, response = await sync_to_async(send_via_whatsapp_cloud_api)(
                conversation=conv,
                content=caption or ' ',
                message_type='image',
                file_path=gallery_image.imagem.path
            )
            if success and msg_obj:
                await ChatbotEngine._sync_cloud_wamid_to_message(msg_obj.id, response)
            return success, response

        base_url = getattr(settings, 'APP_BASE_URL', '').rstrip('/')
        public_url = f"{base_url}{panel_url}" if base_url else panel_url
        fallback_text = caption or "Imagem enviada"
        return await ChatbotEngine.send_message_agnostic(conv, f"{fallback_text}\n{public_url}")

    @staticmethod
    async def send_order_details_payment(conv, content, pix_code=None, boleto_code=None, merchant_name=None, amount_value=0, reference_id="ref", items_list=None) -> Tuple[bool, Any]:
        """
        Envia mensagem interativa de detalhes do pedido com Pix e/ou Boleto.
        """
        payment_settings = []
        
        # 1. PIX
        if pix_code:
            pix_key, pix_key_type = ChatbotEngine._extract_pix_info(pix_code)
            payment_settings.append({
                "type": "pix_dynamic_code",
                "pix_dynamic_code": {
                    "code": pix_code,
                    "merchant_name": merchant_name or "Empresa",
                    "key": pix_key,
                    "key_type": pix_key_type
                }
            })
            
        # 2. BOLETO
        if boleto_code:
            # Limpar linha digitável (apenas números, max 48)
            linha_limpa = ''.join(filter(str.isdigit, str(boleto_code)))[:48]
            if len(linha_limpa) >= 47:
                payment_settings.append({
                    "type": "boleto",
                    "boleto": {
                        "digitable_line": linha_limpa
                    }
                })

        order_details = {
            "reference_id": reference_id,
            "type": "digital-goods",
            "payment_type": "br",
            "payment_settings": payment_settings,
            "currency": "BRL",
            "total_amount": {
                "value": int(amount_value * 100),
                "offset": 100
            },
            "order": {
                "status": "pending",
                "items": items_list or [],
                "subtotal": {
                    "value": int(amount_value * 100),
                    "offset": 100
                }
            }
        }
        
        return await sync_to_async(send_via_whatsapp_cloud_api)(
            conversation=conv,
            content=content,
            message_type='order_details',
            order_details=order_details
        )

    @staticmethod
    def _extract_pix_info(codigo_pix: str) -> Tuple[str, str]:
        """
        Extrai chave e tipo de chave de um código PIX (EMV ou chave direta).
        Lógica baseada no FaturaService.
        """
        pix_key = ""
        pix_key_type = "EVP"
        
        if not codigo_pix:
            return pix_key, pix_key_type

        # 1. Se for QR Code EMV
        if codigo_pix.startswith('000201'):
            try:
                # Procurar padrões comuns dentro do EMV
                # CPF (11)
                for match in re.finditer(r'\b\d{11}\b', codigo_pix):
                    if match.start() > 10 and len(set(match.group())) > 1:
                        return match.group(), "CPF"
                # CNPJ (14)
                for match in re.finditer(r'\b\d{14}\b', codigo_pix):
                    if match.start() > 10 and len(set(match.group())) > 1:
                        return match.group(), "CNPJ"
                # Email
                email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', codigo_pix)
                if email:
                    return email.group(), "EMAIL"
                # Telefone
                for pattern in [r'\+55\d{10,11}', r'\b55\d{10,11}\b']:
                    for m in re.finditer(pattern, codigo_pix):
                        if m.start() > 10 and not m.group().startswith('0002'):
                            return m.group().lstrip('+'), "PHONE"
                
                # Fallback EVP determinístico
                pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50]))
            except:
                pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50]))
        
        # 2. Se for chave direta
        elif len(codigo_pix) == 11 and codigo_pix.isdigit():
            return codigo_pix, "CPF"
        elif len(codigo_pix) == 14 and codigo_pix.isdigit():
            return codigo_pix, "CNPJ"
        elif '@' in codigo_pix:
            return codigo_pix, "EMAIL"
        elif codigo_pix.startswith('+55') or (codigo_pix.startswith('55') and len(codigo_pix) >= 12):
            return codigo_pix.lstrip('+'), "PHONE"
        elif '-' in codigo_pix and len(codigo_pix) == 36:
            return codigo_pix, "EVP"
        else:
            # Resíduo
            pix_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, codigo_pix[:50])) if len(codigo_pix) > 50 else codigo_pix
            pix_key_type = "EVP"

        return pix_key, pix_key_type

    @staticmethod
    async def handle_button_click(provedor_id: int, conversation_id: int, button_id: str):
        """
        Trata o clique em um botão interativo.
        """
        logger.info(f"[ChatbotEngine] Botão clicado: {button_id} na conv {conversation_id}")
        return await ChatbotEngine.process_message(provedor_id, conversation_id, "", button_id=button_id)
