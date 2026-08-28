import logging
import json
from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from conversations.models import Conversation, Message, Team, TeamMember
from core.models import Provedor
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .horario_utils import verificar_horario_atendimento

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
        
        # Se está fora do horário, informar quando será atendido
        proximo_horario = horario_info.get('proximo_horario', '')
        if proximo_horario:
            # Buscar horários completos para formatar corretamente
            try:
                if not self.provedor.horarios_atendimento:
                    return f"{mensagem_base}\n\nVocê será atendido {proximo_horario}."
                
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
                        return f"{mensagem_base}\n\nVocê será atendido {proximo_horario}.\n\nNosso horário de atendimento é:\n\n{horarios_texto}"
            except Exception as e:
                logger.warning(f"Erro ao formatar horários completos: {e}")
        
        # Fallback simples
        return f"{mensagem_base}\n\nVocê será atendido {proximo_horario}."

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
            
            # Mapeamento de palavras-chave para facilitar busca
            palavras_chave = {
                'VENDAS': ['venda', 'vendas', 'comercial', 'vendedor'],
                'SUPORTE': ['suporte', 'técnico', 'tecnico', 'suporte técnico'],
                'FINANCEIRO': ['financeiro', 'fatura', 'pagamento', 'cobrança'],
                'ATENDIMENTO': ['atendimento', 'geral', 'atendente']
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
                    if any(palavra in nome_equipe_normalizado for palavra in palavras):
                        palavras_relacionadas.extend(palavras)
                
                if palavras_relacionadas:
                    from django.db.models import Q
                    query = Q()
                    for palavra in palavras_relacionadas:
                        query |= Q(name__icontains=palavra)
                    
                    equipe = Team.objects.filter(
                        query,
                        provedor=self.provedor,
                        is_active=True
                    ).first()
            
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
            
            # Buscar membros da equipe
            membros = TeamMember.objects.filter(
                team=equipe
            ).select_related('user')
            
            if not membros.exists():
                return {
                    'success': False,
                    'erro': f'Nenhum membro ativo encontrado na equipe {nome_equipe}'
                }
            
            # Escolher primeiro membro disponível
            membro = membros.first()
            
            return {
                'success': True,
                'membro': {
                    'id': membro.user.id,
                    'nome': membro.user.get_full_name() or membro.user.username,
                    'username': membro.user.username,
                    'email': membro.user.email
                },
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
            
            # Determinar equipe recomendada
            scores = {
                'SUPORTE TÉCNICO': score_suporte,
                'FINANCEIRO': score_financeiro,
                'ATENDIMENTO': score_vendas
            }
            
            equipe_recomendada = max(scores, key=scores.get)
            score_maximo = scores[equipe_recomendada]
            
            # Verificar se há equipe disponível
            equipes_disponiveis = self.buscar_equipes_disponíveis()
            
            if not equipes_disponiveis['success']:
                return {
                    'success': False,
                    'erro': 'Não foi possível verificar equipes disponíveis'
                }
            
            # Verificar se a equipe recomendada existe
            equipe_existe = any(
                equipe['name'].upper() == equipe_recomendada.upper() 
                for equipe in equipes_disponiveis['equipes']
            )
            
            if not equipe_existe:
                # Se não existe, usar primeira equipe disponível
                if equipes_disponiveis['equipes']:
                    equipe_recomendada = equipes_disponiveis['equipes'][0]['name']
                else:
                    return {
                        'success': False,
                        'erro': 'Nenhuma equipe disponível encontrada'
                    }
            
            return {
                'success': True,
                'conversa_id': conversation_id,
                'equipe_recomendada': equipe_recomendada,
                'score_maximo': score_maximo,
                'scores': scores,
                'confianca': 'alta' if score_maximo >= 3 else 'media' if score_maximo >= 1 else 'baixa',
                'motivo': self._gerar_motivo_transferencia(equipe_recomendada, scores),
                'equipes_disponiveis': equipes_disponiveis['equipes']
            }
            
        except Exception as e:
            return {
                'success': False,
                'erro': f"Erro ao analisar conversa: {str(e)}"
            }

    def _gerar_motivo_transferencia(self, equipe: str, scores: Dict[str, int]) -> str:
        """Gera motivo da transferência baseado na análise"""
        if equipe == 'SUPORTE TÉCNICO':
            return "Problema técnico identificado - transferindo para equipe de suporte"
        elif equipe == 'FINANCEIRO':
            return "Questão financeira identificada - transferindo para equipe financeira"
        elif equipe == 'ATENDIMENTO':
            return "Solicitação de atendimento geral - transferindo para equipe de atendimento"
        else:
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
            from .redis_memory_service import redis_memory_service
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
                
                membro_data = resultado_membro['membro']
                equipe_data = resultado_membro['equipe']
                
                # Executar transferência
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                membro_usuario = User.objects.get(id=membro_data['id'])
                
                status_anterior = conversa.status
                assignee_anterior = conversa.assignee
                
                # IMPORTANTE: Não atribuir diretamente ao membro, deixar em espera
                conversa.assignee = None  # Sem atribuição direta
                conversa.status = 'pending'  # Em Espera
                
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
                
                # Se for transferência comercial/vendas, formatar mensagem com horário
                mensagem_formatada = None
                equipe_lower = equipe_nome.lower()
                if 'comercial' in equipe_lower or 'vendas' in equipe_lower:
                    # Formatar mensagem com horário de atendimento
                    mensagem_formatada = self._formatar_mensagem_transferencia_comercial(horario_info)
                
                # Garantir mensagem formatada para qualquer equipe
                if not mensagem_formatada:
                    if horario_info.get('dentro_horario'):
                        mensagem_formatada = f"Entendi! Já estou transferindo seu atendimento para a equipe de {equipe_nome}. Um de nossos consultores falará com você em breve."
                    else:
                        proximo = horario_info.get('proximo_horario')
                        if proximo:
                            mensagem_formatada = f"Entendi! Vou transferir seu atendimento para a equipe de {equipe_nome}. Como estamos fora do horário de atendimento agora, eles falarão com você a partir de {proximo}."
                        else:
                            mensagem_formatada = f"Entendi! Vou transferir seu atendimento para a equipe de {equipe_nome}. Eles falarão com você assim que possível."

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
                    'mensagem_formatada': mensagem_formatada
                }
                
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

    def criar_resumo_suporte(self, conversation_id: int, resumo_texto: str) -> Dict[str, Any]:
        """
        Tool: criar_resumo_suporte
        Cria uma mensagem de resumo do atendimento de suporte na conversa.
        🚨 IMPORTANTE: Esta mensagem é criada APENAS para atendentes - NÃO é enviada para o cliente.
        O resumo fica visível apenas no chat interno para a equipe técnica.
        
        Args:
            conversation_id: ID da conversa
            resumo_texto: Texto do resumo do que o cliente disse e o que a IA entendeu
        
        Returns:
            Dict com resultado da operação
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
            
            # Criar mensagem de resumo (apenas para atendentes, não visível para o cliente)
            mensagem_resumo = Message.objects.create(
                conversation=conversa,
                content=resumo_texto,
                message_type='text',
                is_from_customer=False,
                additional_attributes={
                    'system_message': True,
                    'tipo': 'resumo_suporte',
                    'criado_por': 'IA',
                    'apenas_atendentes': True  # Flag para indicar que é apenas para atendentes
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





