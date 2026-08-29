import logging
import json
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from conversations.models import Conversation, Message, Team, TeamMember
from core.models import Provedor
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.horario_utils import formatar_aviso_transferencia_fora_horario, verificar_horario_atendimento

logger = logging.getLogger(__name__)

class DatabaseTools:
    """
    Ferramentas seguras para a IA interagir com o banco de dados
    """
    
    def __init__(self, provedor: Provedor):
        self.provedor = provedor
        self._channel_layer = None
    
    @property
    def channel_layer(self):
        """Lazy loading do channel_layer para evitar problemas na inicialização"""
        if self._channel_layer is None:
            try:
                self._channel_layer = get_channel_layer()
            except Exception as e:
                self._channel_layer = None
        return self._channel_layer
    
    def _verificar_horario_atendimento(self) -> Dict[str, Any]:
        """
        Verifica se está dentro do horário de atendimento usando a utilidade centralizada.
        """
        return verificar_horario_atendimento(self.provedor)
    
    def _formatar_mensagem_transferencia_comercial(self, horario_info: Dict[str, Any]) -> str:
        """
        Formata mensagem de transferência comercial com horário de atendimento.
        Retorna mensagem formatada com quebras de linha corretas.
        """
        import json
        
        # Mensagem base de transferência
        mensagem_base = "Ótima escolha! Vou transferir seu atendimento para nossa equipe comercial para finalizar a contratação."
        
        # Se está dentro do horário
        if horario_info.get('dentro_horario'):
            return f"{mensagem_base}\n\nNossa equipe comercial irá atendê-lo em breve."
        
        aviso = formatar_aviso_transferencia_fora_horario(horario_info, setor='comercial').strip()
        if aviso:
            mensagem_base = f"{mensagem_base}\n\n{aviso}"

        # Se está fora do horário, informar quando será atendido e, se possível, a grade
        proximo_horario = horario_info.get('proximo_horario', '')
        if proximo_horario:
            # Buscar horários completos para formatar corretamente
            try:
                if not self.provedor.horarios_atendimento:
                    return mensagem_base
                
                horarios = json.loads(self.provedor.horarios_atendimento) if isinstance(self.provedor.horarios_atendimento, str) else self.provedor.horarios_atendimento
                
                if horarios and isinstance(horarios, list):
                    # Formatar horários completos com quebras de linha
                    # Cada dia deve aparecer em uma linha separada, nunca agrupado
                    horarios_formatados = []
                    
                    # Mapear dias da semana para garantir formato consistente
                    dias_semana_map = {
                        'segunda': 'segunda-feira',
                        'terça': 'terça-feira',
                        'terca': 'terça-feira',
                        'quarta': 'quarta-feira',
                        'quinta': 'quinta-feira',
                        'sexta': 'sexta-feira',
                        'sábado': 'sábado',
                        'sabado': 'sábado',
                        'domingo': 'domingo'
                    }
                    
                    for dia_info in horarios:
                        dia_original = dia_info.get('dia', '').lower().strip()
                        # Normalizar nome do dia
                        dia = dias_semana_map.get(dia_original, dia_original)
                        periodos = dia_info.get('periodos', [])
                        
                        if not periodos:
                            # Dia fechado
                            horarios_formatados.append(f"• {dia}: Fechado")
                            continue
                        
                        # Formatar períodos do dia
                        periodos_str = []
                        for periodo in periodos:
                            inicio = periodo.get('inicio', '')
                            fim = periodo.get('fim', '')
                            if inicio and fim:
                                periodos_str.append(f"{inicio} às {fim}")
                        
                        if periodos_str:
                            # Se tem múltiplos períodos, colocar na mesma linha separados por espaço
                            # Exemplo: "8:00 às 12:00 14:00 às 18:00"
                            horario_dia = f"• {dia}: {' '.join(periodos_str)}"
                            horarios_formatados.append(horario_dia)
                    
                    if horarios_formatados:
                        # Juntar com quebra de linha dupla entre cada dia
                        # Cada dia fica em sua própria linha, nunca agrupado
                        horarios_texto = "\n\n".join(horarios_formatados)
                        return f"{mensagem_base}\n\nNosso horário de atendimento é:\n\n{horarios_texto}"
            except Exception as e:
                logger.warning(f"Erro ao formatar horários completos: {e}")
        
        # Fallback simples
        return mensagem_base

    def buscar_equipes_disponiveis(self) -> Dict[str, Any]:
        """
        Tool: buscar_equipes_disponiveis
        Busca todas as equipes disponíveis no provedor atual
        """
        try:
            # Verificar se provedor está definido
            if not self.provedor:
                return {
                    'success': False,
                    'erro': 'Provedor não definido'
                }
            
            # Buscar equipes do provedor atual
            equipes = Team.objects.filter(
                provedor=self.provedor,
                is_active=True
            ).values('id', 'name', 'description')
            
            equipes_list = list(equipes)
            
            return {
                'success': True,
                'equipes': equipes_list,
                'total': len(equipes_list),
                'provedor': self.provedor.nome,
                'provedor_id': self.provedor.id
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao buscar equipes: {str(e)}"
            }

    def buscar_membro_disponivel_equipe(self, nome_equipe: str) -> Dict[str, Any]:
        """
        Tool: buscar_membro_disponivel_equipe
        Busca um membro disponível de uma equipe específica
        
        Args:
            nome_equipe: Nome da equipe (SUPORTE, FINANCEIRO, ATENDIMENTO, VENDAS, etc.)
        """
        try:
            # Normalizar nome da equipe para busca
            nome_equipe_normalizado = nome_equipe.strip().upper()
            nome_equipe_lower = nome_equipe.strip().lower()

            # Mapeamento de palavras-chave para facilitar busca
            palavras_chave = {
                'VENDAS': ['venda', 'vendas', 'comercial', 'vendedor'],
                'SUPORTE': ['suporte', 'técnico', 'tecnico', 'suporte técnico', 'suporte tecnico'],
                'FINANCEIRO': ['financeiro', 'fatura', 'pagamento', 'cobrança', 'cobranca'],
                'ATENDIMENTO': ['atendimento', 'geral', 'atendente'],
            }

            # Buscar equipe primeiro por nome exato ou contém
            equipe = Team.objects.filter(
                provedor=self.provedor,
                name__icontains=nome_equipe,
                is_active=True
            ).first()

            # Se não encontrou, tentar buscar por palavras-chave relacionadas
            if not equipe:
                palavras_relacionadas = []
                for key, palavras in palavras_chave.items():
                    if any(palavra in nome_equipe_lower for palavra in palavras) or key.lower() in nome_equipe_lower:
                        palavras_relacionadas.extend(palavras)
                        palavras_relacionadas.append(key.lower())

                # Fallback: "suporte técnico" → também tentar ATENDIMENTO
                if any(p in nome_equipe_lower for p in ('suporte', 'tecnico', 'técnico')):
                    palavras_relacionadas.extend(['atendimento', 'suporte'])

                if palavras_relacionadas:
                    from django.db.models import Q
                    query = Q()
                    for palavra in set(palavras_relacionadas):
                        query |= Q(name__icontains=palavra)

                    candidatas = list(Team.objects.filter(
                        query,
                        provedor=self.provedor,
                        is_active=True
                    ))
                    # Preferir match mais específico; nunca escolher equipe IA
                    candidatas = [
                        eq for eq in candidatas
                        if (eq.name or '').strip().upper() not in ('IA', 'BOT', 'CHATBOT')
                    ]
                    if candidatas:
                        # Preferir nome que contenha o termo pedido
                        preferida = None
                        for eq in candidatas:
                            nu = (eq.name or '').upper()
                            if any(t in nu for t in ('SUPORTE', 'TECN')) and 'suporte' in nome_equipe_lower:
                                preferida = eq
                                break
                            if 'FINANC' in nu and 'financ' in nome_equipe_lower:
                                preferida = eq
                                break
                            if any(t in nu for t in ('VENDA', 'COMERC')) and any(t in nome_equipe_lower for t in ('venda', 'comerc')):
                                preferida = eq
                                break
                        equipe = preferida or next(
                            (eq for eq in candidatas if 'ATEND' in (eq.name or '').upper()),
                            candidatas[0],
                        )
            
            # Se ainda não encontrou, tentar busca mais ampla removendo espaços e caracteres especiais
            if not equipe:
                nome_sem_espacos = nome_equipe.replace(' ', '').replace('-', '').replace('_', '').upper()
                # Buscar todas as equipes e filtrar em Python (mais compatível)
                todas_equipes = Team.objects.filter(
                    provedor=self.provedor,
                    is_active=True
                )
                for eq in todas_equipes:
                    nome_eq_normalizado = eq.name.replace(' ', '').replace('-', '').replace('_', '').upper()
                    if nome_sem_espacos in nome_eq_normalizado or nome_eq_normalizado in nome_sem_espacos:
                        equipe = eq
                        break
            
            if not equipe:
                # Listar equipes disponíveis para ajudar no debug
                equipes_disponiveis = Team.objects.filter(
                    provedor=self.provedor,
                    is_active=True
                ).values_list('name', flat=True)
                
                return {
                    'success': False,
                    'erro': f'Equipe "{nome_equipe}" não encontrada ou inativa. Equipes disponíveis: {", ".join(equipes_disponiveis)}'
                }
            
            # Buscar membros da equipe (opcional: fila fica em espera mesmo sem membros)
            membros = TeamMember.objects.filter(
                team=equipe
            ).select_related('user')

            membro_data = None
            membro = membros.first()
            if membro and membro.user_id:
                membro_data = {
                    'id': membro.user.id,
                    'nome': membro.user.get_full_name() or membro.user.username,
                    'username': membro.user.username,
                    'email': membro.user.email,
                }

            return {
                'success': True,
                'membro': membro_data,
                'equipe': {
                    'id': equipe.id,
                    'name': equipe.name,
                    'description': equipe.description
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao buscar membro da equipe: {str(e)}"
            }

    def analisar_conversa_para_transferencia(self, conversation_id: int) -> Dict[str, Any]:
        """
        Analisa a conversa para determinar a equipe mais adequada para transferência
        
        Args:
            conversation_id: ID da conversa a ser analisada
        
        Returns:
            Dict com análise e recomendação de equipe
        """
        try:
            # Buscar conversa
            conversa = Conversation.objects.filter(
                id=conversation_id,
                inbox__provedor=self.provedor
            ).first()
            
            if not conversa:
                return {
                    'success': False,
                    'erro': f'Conversa {conversation_id} não encontrada'
                }
            
            # Buscar últimas mensagens da conversa
            mensagens = Message.objects.filter(
                conversation=conversa
            ).order_by('-created_at')[:20]  # Últimas 20 mensagens
            
            # Analisar conteúdo das mensagens
            texto_completo = ""
            for msg in reversed(mensagens):  # Ordem cronológica
                if msg.content:
                    texto_completo += f" {msg.content.lower()}"
            
            # Palavras-chave para cada tipo de equipe
            palavras_suporte = [
                'internet', 'conexão', 'modem', 'roteador', 'sinal', 'velocidade', 'lenta', 'caiu', 
                'desconectou', 'problema', 'técnico', 'instalação', 'equipamento', 'cabo', 'fibra',
                'drop', 'led', 'vermelho', 'piscando', 'sem acesso', 'não funciona', 'erro',
                'chamado', 'suporte', 'técnico', 'reparo', 'manutenção'
            ]
            
            palavras_financeiro = [
                'fatura', 'boleto', 'pagamento', 'pagar', 'valor', 'preço', 'conta', 'débito',
                'vencimento', 'multa', 'juros', 'desconto', 'segunda via', 'comprovante',
                'recibo', 'parcelamento', 'cartão', 'pix', 'transferência', 'dinheiro',
                'cobrança', 'em aberto', 'atraso', 'suspenso'
            ]
            
            palavras_vendas = [
                'plano', 'contratar', 'contratação', 'oferta', 'melhor', 'escolher', 'novo',
                'mudar', 'alterar', 'preço', 'velocidade', 'instalação', 'endereço',
                'documentos', 'proposta', 'orçamento', 'promoção', 'desconto', 'vantagem'
            ]
            
            # Contar ocorrências
            score_suporte = sum(1 for palavra in palavras_suporte if palavra in texto_completo)
            score_financeiro = sum(1 for palavra in palavras_financeiro if palavra in texto_completo)
            score_vendas = sum(1 for palavra in palavras_vendas if palavra in texto_completo)
            
            # Determinar categoria recomendada
            scores = {
                'SUPORTE': score_suporte,
                'FINANCEIRO': score_financeiro,
                'VENDAS': score_vendas,
            }

            categoria = max(scores, key=scores.get)
            score_maximo = scores[categoria]

            # Verificar equipes disponíveis (método sem acento)
            equipes_disponiveis = self.buscar_equipes_disponiveis()

            if not equipes_disponiveis['success']:
                return {
                    'success': False,
                    'erro': 'Não foi possível verificar equipes disponíveis'
                }

            equipe_recomendada = self._resolver_equipe_para_categoria(
                categoria,
                equipes_disponiveis.get('equipes') or [],
            )

            if not equipe_recomendada:
                return {
                    'success': False,
                    'erro': 'Nenhuma equipe humana disponível encontrada'
                }

            return {
                'success': True,
                'conversa_id': conversation_id,
                'equipe_recomendada': equipe_recomendada,
                'categoria': categoria,
                'score_maximo': score_maximo,
                'scores': scores,
                'confianca': 'alta' if score_maximo >= 3 else 'media' if score_maximo >= 1 else 'baixa',
                'motivo': self._gerar_motivo_transferencia(categoria, scores),
                'equipes_disponiveis': equipes_disponiveis['equipes']
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao analisar conversa: {str(e)}"
            }

    def _equipes_humanas(self, equipes: list) -> list:
        """Exclui equipe 'IA' (bot) das opções de transferência."""
        result = []
        for eq in equipes or []:
            name = (eq.get('name') or '').strip()
            if not name:
                continue
            if name.upper() in ('IA', 'BOT', 'CHATBOT', 'AUTOMAÇÃO', 'AUTOMACAO'):
                continue
            result.append(eq)
        return result

    def _resolver_equipe_para_categoria(self, categoria: str, equipes: list) -> Optional[str]:
        """
        Escolhe o nome real da equipe cadastrada a partir da categoria da análise.
        Ex.: SUPORTE → ATENDIMENTO se não existir equipe de suporte.
        """
        humanas = self._equipes_humanas(equipes)
        if not humanas:
            return None

        preferencias = {
            'SUPORTE': ['SUPORTE', 'TECNICO', 'TÉCNICO', 'ATENDIMENTO'],
            'FINANCEIRO': ['FINANCEIRO', 'COBRANCA', 'COBRANÇA', 'ATENDIMENTO'],
            'VENDAS': ['VENDAS', 'COMERCIAL', 'ATENDIMENTO'],
            'ATENDIMENTO': ['ATENDIMENTO', 'GERAL', 'SUPORTE'],
        }
        prefs = preferencias.get((categoria or '').upper(), ['ATENDIMENTO', 'SUPORTE'])

        for pref in prefs:
            pref_u = pref.upper()
            for eq in humanas:
                name_u = (eq.get('name') or '').upper()
                if pref_u in name_u or name_u in pref_u:
                    return eq['name']

        return humanas[0]['name']

    def _gerar_motivo_transferencia(self, equipe: str, scores: Dict[str, int]) -> str:
        """Gera motivo da transferência baseado na análise"""
        cat = (equipe or '').upper()
        if 'SUPORTE' in cat or 'TECN' in cat:
            return "Problema técnico identificado - transferindo para equipe de suporte"
        if 'FINANC' in cat or 'COBRAN' in cat:
            return "Questão financeira identificada - transferindo para equipe financeira"
        if 'VENDA' in cat or 'COMERC' in cat:
            return "Interesse comercial identificado - transferindo para equipe de vendas"
        if 'ATEND' in cat:
            return "Solicitação de atendimento - transferindo para equipe de atendimento"
        return f"Transferência para {equipe} - análise automática da conversa"

    def transferir_conversa_inteligente(self, conversation_id: int) -> Dict[str, Any]:
        """
        Executa transferência inteligente baseada na análise da conversa
        
        Args:
            conversation_id: ID da conversa
        
        Returns:
            Dict com resultado da transferência
        """
        try:
            # Analisar conversa
            analise = self.analisar_conversa_para_transferencia(conversation_id)
            
            if not analise['success']:
                return analise
            
            # Executar transferência
            resultado = self.executar_transferencia_conversa(
                conversation_id=conversation_id,
                equipe_nome=analise['equipe_recomendada'],
                motivo=analise['motivo']
            )
            
            if resultado['success']:
                resultado['analise'] = analise
                resultado['transferencia_inteligente'] = True
            
            return resultado
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro na transferência inteligente: {str(e)}"
            }

    def encerrar_atendimento(self, motivo: str = "Cliente satisfeito") -> Dict[str, Any]:
        """
        Encerra o atendimento colocando-o em estado 'closing'.
        """
        try:
            from core.redis_memory_service import redis_memory_service
            from conversations.closing_service import closing_service
            
            # Precisamos da conversa atual. Como DatabaseTools não tem o contexto da conversa,
            # o AIActionsHandler deve passar o ID ou a instância.
            # Mas aqui podemos tentar buscar a conversa ativa do contato se necessário.
            # No entanto, o fluxo padrão é passar via function_args.
            
            # Se não temos a conversa aqui, o AIActionsHandler vai cuidar disso.
            return {"success": True, "encerrar": True, "motivo": motivo}
            
        except Exception as e:
            return {"success": False, "erro": str(e)}

    def executar_transferencia_conversa(self, conversation_id: int, equipe_nome: str, motivo: str) -> Dict[str, Any]:
        """
        Tool: executar_transferencia_conversa
        Transfere uma conversa para uma equipe específica
        
        Args:
            conversation_id: ID da conversa
            equipe_nome: Nome da equipe de destino
            motivo: Motivo da transferência
        """
        try:
            with transaction.atomic():
                # Buscar conversa com lock
                conversa = Conversation.objects.select_for_update().filter(
                    id=conversation_id,
                    inbox__provedor=self.provedor  # Segurança: apenas conversas do provedor
                ).first()
                
                if not conversa:
                    return {
                        'success': False,
                        'erro': f'Conversa {conversation_id} não encontrada ou sem permissão'
                    }
                
                # Buscar membro da equipe
                resultado_membro = self.buscar_membro_disponivel_equipe(equipe_nome)
                
                if not resultado_membro['success']:
                    erro_msg = resultado_membro.get('erro', 'Erro desconhecido ao buscar equipe')
                    return {
                        'success': False,
                        'erro': erro_msg,
                        'conversation_id': conversation_id,
                        'equipe_solicitada': equipe_nome
                    }
                
                membro_data = resultado_membro.get('membro')
                equipe_data = resultado_membro['equipe']

                status_anterior = conversa.status

                # IMPORTANTE: Não atribuir diretamente ao membro, deixar em espera humana
                conversa.assignee = None  # Sem atribuição direta
                conversa.status = 'pending'  # Em Espera
                conversa.waiting_for_agent = True  # Sai da IA / entra na fila humana
                try:
                    conversa.team_id = equipe_data['id']
                except Exception:
                    pass

                # Salvar informação da equipe nos additional_attributes
                if not conversa.additional_attributes:
                    conversa.additional_attributes = {}
                conversa.additional_attributes['assigned_team'] = {
                    'id': equipe_data['id'],
                    'name': equipe_data['name']
                }
                conversa.additional_attributes['transfer_motivo'] = motivo
                conversa.additional_attributes['transfer_timestamp'] = str(timezone.now())

                conversa.save()

                # Resumo interno automático para o atendente (não vai ao cliente)
                self._garantir_resumo_na_transferencia(conversa, conversation_id, motivo)
                
                # Enviar notificação WebSocket
                if self.channel_layer:
                    async_to_sync(self.channel_layer.group_send)(
                        f"painel_{self.provedor.id}",
                        {
                            'type': 'conversation_status_changed',
                            'conversation': {
                                'id': conversa.id,
                                'status': conversa.status,
                                'assigned_team': equipe_data['name'],
                                'contact': {
                                    'name': conversa.contact.name,
                                    'phone': conversa.contact.phone
                                }
                            },
                            'message': f'Conversa transferida para {equipe_nome} - Status: Em Espera'
                        }
                    )
                
                
                # Verificar horário de atendimento
                horario_info = self._verificar_horario_atendimento()

                resultado = {
                    'success': True,
                    'transferencia_realizada': True,
                    'conversa_id': conversa.id,
                    'status_anterior': status_anterior,
                    'status_atual': conversa.status,
                    'equipe_destino': equipe_nome,
                    'motivo': motivo,
                    'em_espera': True,
                    'horario_info': horario_info,
                    'mensagem_cliente_sugerida': (
                        '' if horario_info.get('dentro_horario')
                        else formatar_aviso_transferencia_fora_horario(
                            horario_info,
                            setor=equipe_nome,
                        ).strip()
                    ),
                    'nota': (
                        'Transferencia realizada. Se horario_info.dentro_horario=false, INFORME o cliente '
                        'com o motivo (feriado, se houver em horario_info.feriado/mensagem) e quando sera '
                        'atendido (proximo_horario). Nao omita o nome do feriado. '
                        'Pode usar mensagem_cliente_sugerida como base e reescrever com suas palavras.'
                    ),
                }

                motivo_l = (motivo or '').lower()
                equipe_l = (equipe_nome or '').lower()
                if (
                    any(x in motivo_l for x in ('comprovante', 'pagamento', 'baixa', 'recibo', 'pix'))
                    or 'financ' in equipe_l
                ):
                    resultado['instrucao_ia'] = (
                        'Comprovante/financeiro: NÃO diga ao cliente que transferiu para o '
                        'FINANCEIRO, setor financeiro ou equipe financeira. '
                        'Confirme de forma simples que o comprovante/documento será encaminhado '
                        'para ser ADICIONADO AO SISTEMA e realizar a BAIXA DO PAGAMENTO. '
                        'Se horario_info.dentro_horario=false, informe quando o atendimento humano '
                        'retoma (proximo_horario/feriado), sem citar o setor.'
                    )
                    resultado['nota'] = (
                        resultado['nota'] + ' ' + resultado['instrucao_ia']
                    )

            # Fora da transaction: notificar WhatsApp no modo suporte (não reverte a transferência)
            try:
                from core.support_transfer_notify import notify_support_transfer

                notify_res = notify_support_transfer(
                    self.provedor,
                    conversa,
                    equipe_nome=equipe_data.get('name') or equipe_nome,
                    motivo=motivo,
                )
                resultado['support_notify'] = notify_res
            except Exception as notify_err:
                logger.warning(
                    "[Transfer] Falha ao notificar modo suporte conv=%s: %s",
                    conversation_id,
                    notify_err,
                )

            # Aviso WhatsApp aos membros da equipe com telefone no perfil
            try:
                from conversations.models import Team
                from core.agent_alert_notify import notify_agents_waiting_alert

                team_obj = None
                team_id = equipe_data.get('id') if isinstance(equipe_data, dict) else None
                if team_id:
                    team_obj = Team.objects.filter(id=team_id).first()
                agent_notify = notify_agents_waiting_alert(
                    self.provedor,
                    conversa,
                    team=team_obj,
                    motivo=motivo or "",
                )
                resultado['agent_notify'] = agent_notify
            except Exception as agent_notify_err:
                logger.warning(
                    "[Transfer] Falha ao notificar atendentes conv=%s: %s",
                    conversation_id,
                    agent_notify_err,
                )

            return resultado
                
        except Exception as e:
            logger.error(f"Erro ao executar transferência: {e}", exc_info=True)
            return {
                'success': False,
                'erro': f"Erro ao executar transferência: {str(e)}",
                'conversation_id': conversation_id,
                'equipe_solicitada': equipe_nome
            }

    def buscar_conversas_ativas(self) -> Dict[str, Any]:
        """
        Tool: buscar_conversas_ativas
        Busca todas as conversas ativas do provedor
        """
        try:
            conversas = Conversation.objects.filter(
                inbox__provedor=self.provedor
            ).select_related('contact', 'assignee', 'inbox').order_by('-last_message_at')
            
            conversas_data = []
            for conversa in conversas:
                conversas_data.append({
                    'id': conversa.id,
                    'status': conversa.status,
                    'contact_name': conversa.contact.name,
                    'contact_phone': conversa.contact.phone,
                    'assignee': conversa.assignee.get_full_name() if conversa.assignee else None,
                    'last_message_at': conversa.last_message_at.isoformat() if conversa.last_message_at else None,
                    'created_at': conversa.created_at.isoformat()
                })
            
            return {
                'success': True,
                'conversas': conversas_data,
                'total': len(conversas_data),
                'provedor': self.provedor.nome
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao buscar conversas ativas: {str(e)}"
            }

    def buscar_estatisticas_atendimento(self) -> Dict[str, Any]:
        """
        Tool: buscar_estatisticas_atendimento
        Busca estatísticas gerais de atendimento do provedor
        """
        try:
            # Estatísticas básicas
            total_conversas = Conversation.objects.filter(inbox__provedor=self.provedor).count()
            
            conversas_abertas = Conversation.objects.filter(
                inbox__provedor=self.provedor,
                status='open'
            ).count()
            
            conversas_pendentes = Conversation.objects.filter(
                inbox__provedor=self.provedor,
                status='pending'
            ).count()
            
            conversas_com_ia = Conversation.objects.filter(
                inbox__provedor=self.provedor,
                status='snoozed'
            ).count()
            
            # Estatísticas por equipe
            equipes_stats = {}
            for team in Team.objects.filter(provedor=self.provedor, is_active=True):
                conversas_equipe = Conversation.objects.filter(
                    inbox__provedor=self.provedor,
                    additional_attributes__assigned_team__id=team.id
                ).count()
                
                equipes_stats[team.name] = {
                    'total_conversas': conversas_equipe,
                    'membros_ativos': team.members.count()
                }
            
            return {
                'success': True,
                'estatisticas_gerais': {
                    'total_conversas': total_conversas,
                    'conversas_abertas': conversas_abertas,
                    'conversas_pendentes': conversas_pendentes,
                    'conversas_com_ia': conversas_com_ia
                },
                'estatisticas_equipes': equipes_stats,
                'consultado_em': timezone.now().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao consultar estatísticas: {str(e)}"
            }

    def _montar_resumo_para_atendente(self, conversa, motivo: str = "") -> str:
        """Monta resumo interno com o que o cliente disse (visível só no painel)."""
        import re

        nome = ""
        try:
            nome = (conversa.contact.name or "").strip()
        except Exception:
            nome = ""
        nome = nome or "Cliente"

        attrs = conversa.additional_attributes or {}
        contrato = str(attrs.get("contrato_id") or "").strip()
        cpf = str(attrs.get("cpf_cnpj") or "").strip()
        if not contrato or not cpf:
            try:
                from core.redis_memory_service import redis_memory_service

                phone = getattr(conversa.contact, "phone", None) or "unknown"
                for ch in ("tg", "wa", "telegram", "whatsapp", "instagram"):
                    st = redis_memory_service.get_ai_state_sync(
                        self.provedor.id, conversa.id, ch, phone
                    ) or {}
                    if not contrato:
                        contrato = str(st.get("contrato_id") or "").strip() or contrato
                    if not cpf:
                        cpf = str(st.get("cpf_cnpj") or "").strip() or cpf
                    if contrato and cpf:
                        break
            except Exception:
                pass

        cpf_digits = re.sub(r"[^\d]", "", cpf) if cpf else ""
        nome_lower = nome.lower()

        def _is_doc_only(text: str) -> bool:
            digits = re.sub(r"[^\d]", "", text or "")
            if not digits or len(digits) not in (11, 14):
                return False
            cleaned = re.sub(r"[\s.\-/]", "", (text or "").strip())
            return cleaned == digits

        def _sanitize_motivo(raw: str) -> str:
            t = (raw or "").strip()
            if not t:
                return "Transferência solicitada pela IA"
            # Remove "Cliente NOME" / nome repetido no motivo
            if nome and len(nome) > 3:
                t = re.sub(
                    re.escape(f"Cliente {nome}"),
                    "",
                    t,
                    flags=re.IGNORECASE,
                )
                t = re.sub(re.escape(nome), "", t, flags=re.IGNORECASE)
            t = re.sub(r"\s{2,}", " ", t).strip(" :,-")
            # Se ficou só "Chamado XXX:", manter conteúdo útil
            if t.lower().startswith("chamado") and ":" in t:
                prefix, rest = t.split(":", 1)
                rest = rest.strip()
                if rest:
                    t = f"{prefix.strip()}: {rest}"
            return t or "Transferência solicitada pela IA"

        msgs = (
            Message.objects.filter(conversation=conversa, is_from_customer=True)
            .order_by("-created_at")[:12]
        )
        falas = []
        for m in reversed(list(msgs)):
            t = (m.content or "").strip()
            if not t:
                continue
            if _is_doc_only(t):
                continue
            if cpf_digits and re.sub(r"[^\d]", "", t) == cpf_digits:
                continue
            # Evitar mensagem que é só o nome do cliente
            if nome_lower and t.lower() == nome_lower:
                continue
            falas.append(f"• {t[:250]}")

        falas_txt = "\n".join(falas) if falas else "• (sem mensagens de texto do cliente)"
        motivo_txt = _sanitize_motivo(motivo)

        linhas = [
            "📋 Resumo",
            f"Cliente: {nome}",
        ]
        if contrato:
            linhas.append(f"Contrato: {contrato}")
        if cpf:
            linhas.append(f"CPF/CNPJ: {cpf}")
        linhas.append(f"Motivo: {motivo_txt}")
        linhas.append("O que o cliente disse:")
        linhas.append(falas_txt)
        return "\n".join(linhas)

    def _garantir_resumo_na_transferencia(self, conversa, conversation_id: int, motivo: str) -> None:
        """Cria resumo interno automaticamente na transferência (se ainda não houver um recente)."""
        try:
            recente = (
                Message.objects.filter(
                    conversation=conversa,
                    additional_attributes__tipo="resumo_suporte",
                )
                .order_by("-created_at")
                .first()
            )
            if recente and recente.created_at:
                delta = timezone.now() - recente.created_at
                if delta.total_seconds() < 120:
                    return

            texto = self._montar_resumo_para_atendente(conversa, motivo)
            self.criar_resumo_suporte(conversation_id, texto)
        except Exception as e:
            logger.warning(
                "[RESUMO] Falha ao criar resumo automático na transferência conv=%s: %s",
                conversation_id,
                e,
            )

    def criar_resumo_suporte(self, conversation_id: int, resumo_texto: str) -> Dict[str, Any]:
        """
        Tool: criar_resumo_suporte
        Cria uma mensagem de resumo do atendimento de suporte na conversa.
        Esta mensagem é criada APENAS para atendentes - NÃO é enviada para o cliente.
        """
        try:
            conversa = Conversation.objects.filter(
                id=conversation_id,
                inbox__provedor=self.provedor
            ).first()

            if not conversa:
                return {
                    'success': False,
                    'erro': f'Conversa {conversation_id} não encontrada'
                }

            mensagem_resumo = Message.objects.create(
                conversation=conversa,
                content=resumo_texto,
                message_type='text',
                is_from_customer=False,
                additional_attributes={
                    'system_message': True,
                    'tipo': 'resumo_suporte',
                    'criado_por': 'IA',
                    'apenas_atendentes': True
                }
            )

            logger.info(f"[RESUMO] Resumo de suporte criado na conversa {conversation_id}")

            return {
                'success': True,
                'mensagem_id': mensagem_resumo.id,
                'conversation_id': conversation_id,
                'mensagem': 'Resumo criado com sucesso na conversa'
            }

        except Exception as e:
            logger.error(f"Erro ao criar resumo de suporte: {e}", exc_info=True)
            return {
                'success': False,
                'erro': f"Erro ao criar resumo: {str(e)}"
            }

# Factory function para criar instância das ferramentas
def create_database_tools(provedor: Provedor) -> DatabaseTools:
    """Cria instância das ferramentas de banco para um provedor específico"""
    return DatabaseTools(provedor)






DATABASE_FUNCTION_MAPPING = {
    "buscar_equipes": "buscar_equipes_disponiveis",
    "buscar_equipes_disponiveis": "buscar_equipes_disponiveis",
    "buscar_membro_equipe": "buscar_membro_disponivel_equipe",
    "buscar_membro_disponivel_equipe": "buscar_membro_disponivel_equipe",
    "transferir_conversa": "executar_transferencia_conversa",
    "executar_transferencia_conversa": "executar_transferencia_conversa",
    "transferir_inteligente": "transferir_conversa_inteligente",
    "transferir_conversa_inteligente": "transferir_conversa_inteligente",
    "buscar_conversas": "buscar_conversas_ativas",
    "buscar_conversas_ativas": "buscar_conversas_ativas",
    "encerrar_atendimento": "encerrar_atendimento",
    "criar_resumo": "criar_resumo_suporte",
    "criar_resumo_suporte": "criar_resumo_suporte",
}