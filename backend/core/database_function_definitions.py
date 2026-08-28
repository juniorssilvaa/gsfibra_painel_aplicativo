# Ferramentas de banco de dados para OpenAI Function Calling
DATABASE_FUNCTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_equipes_disponiveis",
            "description": "Busca todas as equipes disponíveis do provedor atual. Retorna lista de equipes (ex: SUPORTE TÉCNICO, FINANCEIRO, VENDAS, COMERCIAL) que podem receber transferências. Use SEMPRE antes de transferir uma conversa para verificar quais equipes existem.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_membro_disponivel_equipe",
            "description": "Busca membros disponíveis de uma equipe específica. Use quando precisar transferir conversa para um membro específico da equipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_equipe": {
                        "type": "string",
                        "description": "Nome da equipe para buscar membros disponíveis"
                    }
                },
                "required": ["nome_equipe"]
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "executar_transferencia_conversa",
            "description": "Executa transferência de conversa para uma equipe específica. Use quando cliente solicitar atendimento de equipe específica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "integer",
                        "description": "ID da conversa a ser transferida"
                    },
                    "equipe_nome": {
                        "type": "string",
                        "description": "Nome da equipe de destino"
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Motivo da transferência explicado em português"
                    }
                },
                "required": ["conversation_id", "equipe_nome", "motivo"]
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_conversas_ativas",
            "description": "Busca conversas ativas do provedor. Use para verificar status das conversas, relatórios ou quando precisar de informações sobre atendimentos em andamento.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transferir_conversa_inteligente",
            "description": "TRANSFERENCIA INTELIGENTE! Analisa automaticamente a conversa e transfere para a equipe mais adequada baseada no conteudo das mensagens. Use quando a IA nao conseguir resolver o problema do cliente e precisar transferir para equipe humana. IMPORTANTE: Use o ID da conversa atual (não o ID do contrato). O ID da conversa está disponível no contexto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "integer",
                        "description": "ID da CONVERSA atual (não o ID do contrato). Use o ID da conversa que está sendo atendida no momento. Se não souber, use buscar_conversas_ativas() para encontrar."
                    }
                },
                "required": ["conversation_id"]
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "encerrar_atendimento",
            "description": "Encerra o atendimento atual com o cliente. Use quando o cliente confirmar que não precisa de mais nada ou quando o atendimento for finalizado com sucesso.",
            "parameters": {
                "type": "object",
                "properties": {
                    "motivo": {
                        "type": "string",
                        "description": "Motivo do encerramento (ex: 'Cliente satisfeito', 'Dúvida resolvida')"
                    }
                },
                "required": ["motivo"]
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "criar_resumo_suporte",
            "description": "Cria um resumo do atendimento de suporte na conversa. Use após coletar todas as informações do cliente sobre o problema técnico. 🚨 IMPORTANTE: O resumo é criado APENAS para atendentes - NÃO é enviado para o cliente. Fica visível apenas no chat interno para a equipe técnica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "integer",
                        "description": "ID da conversa onde o resumo será criado"
                    },
                    "resumo_texto": {
                        "type": "string",
                        "description": "Texto do resumo contendo: o que o cliente disse, o que a IA entendeu, informações coletadas (dispositivos conectados, reinício do modem, quando começou, etc.)"
                    }
                },
                "required": ["conversation_id", "resumo_texto"]
            },
            "strict": True
        }
    }
]

# Mapeamento de nomes de função para implementação
DATABASE_FUNCTION_MAPPING = {
    "buscar_equipes_disponiveis": "buscar_equipes_disponiveis",
    "buscar_membro_disponivel_equipe": "buscar_membro_disponivel_equipe",
    "executar_transferencia_conversa": "executar_transferencia_conversa",
    "transferir_conversa_inteligente": "transferir_conversa_inteligente",
    "buscar_conversas_ativas": "buscar_conversas_ativas",
    "encerrar_atendimento": "encerrar_atendimento",
    "criar_resumo_suporte": "criar_resumo_suporte"
}

# Instruções específicas para o sistema prompt
DATABASE_SYSTEM_INSTRUCTIONS = """
FERRAMENTAS DE BANCO DE DADOS DISPONÍVEIS:

**Para Transferências (PRIORITÁRIO):**
1. buscar_equipes_disponiveis() - Verificar equipes existentes
2. buscar_membro_disponivel_equipe(nome_equipe) - Verificar disponibilidade  
3. executar_transferencia_conversa(conversation_id, equipe_nome, motivo) - Transferir conversa
4. transferir_conversa_inteligente(conversation_id) - Transferência automática baseada no conteúdo

**Para Consultas:**
5. buscar_conversas_ativas() - Ver conversas em andamento

**Para Suporte Técnico:**
6. criar_resumo_suporte(conversation_id, resumo_texto) - Cria resumo do atendimento de suporte na conversa. Use após coletar todas as informações de diagnóstico do cliente sobre problemas de internet.

**REGRAS IMPORTANTES:**
- SEMPRE use buscar_equipes_disponiveis() ANTES de tentar transferir
- Use executar_transferencia_conversa() quando cliente solicitar equipe específica
- Use transferir_conversa_inteligente() quando IA não conseguir resolver e precisar transferir
- Motivo deve ser em português e explicar por que está transferindo

**REGRA CRÍTICA PARA VENDAS:**
- A IA deve SEMPRE atender o cliente primeiro: explicar planos, tirar dúvidas, enviar preços, confirmar endereço, ajudar a entender opções
- NÃO transfira para vendas apenas por intenção inicial como "quero contratar", "quero assinar", "quero instalar" - essas frases indicam interesse, mas continue atendendo
- Só transfira para VENDAS quando o cliente CONFIRMAR explicitamente que quer FECHAR a contratação (ex: "quero fechar", "vamos fechar", "pode prosseguir", "vamos fazer então")
- Use seu julgamento baseado no contexto completo da conversa para identificar quando o cliente realmente quer fechar

**EXEMPLOS CORRETOS:**
Cliente: "Preciso falar com o financeiro"
IA: executa executar_transferencia_conversa("FINANCEIRO", "Cliente solicitou atendimento financeiro")

Cliente: "Alguém para me ajudar aí?"
IA: executa executar_transferencia_conversa("ATENDIMENTO", "Cliente pediu ajuda de atendente")

Cliente: "Quero ajuda"
IA: executa executar_transferencia_conversa("ATENDIMENTO", "Cliente solicitou atendimento humano")

Resultado: Conversa move de "Com IA" para "Em Espera" + Notificação WebSocket

**EXEMPLO INCORRETO:**
Cliente: "Preciso do financeiro" 
IA: "Vou buscar suas faturas..." + executa buscar_faturas_vencidas
ERRADO! Cliente quer transferência, não fatura!
"""