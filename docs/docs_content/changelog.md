# Changelog

Todas as mudanças notáveis do projeto NioChat serão documentadas neste arquivo.

**Fonte oficial do histórico no produto:** `CHANGELOG.json` na raiz do repositório (servido por `/api/changelog/` e exibido no modal de versões). Atualize apenas esse JSON para novas versões.

## [2.67.0] - 2026-09-01

### 🐛 Corrigido
- **Atendimento / Mídia**: corrigido erro em que, em alguns casos, as mídias retornavam 404 por assinatura expirada ao abrir PDF ou imagem no painel. A abertura passa a usar autenticação do atendente e a conversa aberta não troca mais ao visualizar anexos.

## [2.66.0] - 2026-08-29

### 🐛 Corrigido
- **IA / OCR**: corrigido o módulo de OCR da IA para leitura de imagens e documentos (PDF), com melhor interpretação de comprovantes e arquivos enviados pelo cliente.

## [2.65.0] - 2026-08-28

### 🐛 Corrigido
- **CSAT / IA**: corrigido o módulo de envio de CSAT — quando o provedor desativa o disparo automático, a pesquisa não é mais enviada após encerramento pela IA ou chatbot.

### 🔧 Melhoria
- **Chat de conversas**: correções e otimizações internas no módulo de conversas (mensagens em tempo real mais rápidas, lista mais leve e melhor desempenho do painel).

## [2.64.0] - 2026-08-21

### ✨ Novo
- **Dashboard Meta · WhatsApp Analytics**: agora é possível ter visão de gasto com a API oficial do WhatsApp (mensagens gratuitas vs templates pagos, gráficos, categorias e estimativa em R$). **Caminho:** Integrações → Meta.

### 🔧 Melhoria
- **Gasto estimado em Real (USD → BRL)**: tarifas por categoria (Utility, Marketing, Authentication) × cotação do dólar (AwesomeAPI). **Caminho:** Integrações → Meta.

## [2.63.0] - 2026-08-21

### 🐛 Corrigido
- **Chat Area**: corrigido o Chat Area (composer, resposta e banner de atender com fundo sólido/legível).

### 🔧 Melhoria
- **Módulo da IA**: melhorias no módulo da IA (confirmação de contratos sem loop e formatação mais clara dos dados do cliente).

## [2.62.0] - 2026-08-19

### 🐛 Corrigido
- **Módulo de viabilidade da IA**: corrigida a consulta de viabilidade. Na contratação, o cliente pode enviar a localização pelo WhatsApp ou o endereço escrito (nome da rua/avenida ou CEP). A leitura da resposta do SGP foi ajustada para reconhecer cobertura corretamente.

## [2.61.0] - 2026-08-17

### ✨ Novo
- **IA entende áudio e imagem**: a IA transcreve mensagens de áudio e interpreta imagens (visão) nos canais oficiais (WhatsApp, Instagram e Telegram). A resposta do áudio é devolvida ao cliente em texto.

### 🐛 Corrigido
- **Cliente com vários contratos**: a IA lista os contratos, pede a escolha e só então consulta fatura ou suporte no contrato selecionado.

## [2.60.0] - 2026-08-15

### ✨ Novo
- **Módulo de feriados nacionais**: adicionado módulo com feriados nacionais.
- **Aplicativo mobile como canal**: o cliente conversa pelo app do provedor e o atendimento entra na mesma fila do NioChat (texto, imagem e áudio).

### 🐛 Corrigido
- **Atendimento pela internet**: ajustes no fluxo de mensagens e notificações do app do cliente no painel (incluindo ícone do canal App).
- **Timeout da sessão**: o tempo escolhido em Perfil → Segurança passa a ser respeitado; incluídas opções de 3 e 4 horas.

## [2.59.0] - 2026-08-11

### ✨ Novo
- **Troca de senha ou nome do Wi-Fi pela IA/chatbot**: com integração TR-069 (ACS) configurada, a IA ou o chatbot pode consultar e alterar o nome da rede (SSID) e a senha do Wi-Fi do modem do cliente.

## [2.58.1] - 2026-08-08

### 🐛 Corrigido
- **Erro interno no envio de mensagem automática**: corrigido o preenchimento das variáveis dos templates Meta em disparos automáticos (SGP). Datas e valores deixam de ser trocados (ex.: valor no lugar do vencimento); o mapeamento usa o texto do template, sem fixar `{{2}}`/`{{3}}` a um tipo.

## [2.58.0] - 2026-08-07

### ✨ Novo
- **Customizar o card de envio de faturas**: personalize o texto do card de pagamento (WhatsApp Oficial) enviado pela IA ou pelo chatbot. **Caminho:** Regras de Atendimento → Configurações gerais → Texto do card da fatura. Variáveis disponíveis (`{{vencimento}}`, `{{valor}}`, `{{valores_texto}}`, `{{instrucoes}}`, `{{fatura_id}}`, `{{nome_cliente}}`, `{{nome_provedor}}`, etc.) com prévia ao vivo do card.

### 🔧 Melhoria
- **Fatura com valor atualizado em atraso**: no envio (IA e chatbot, todos os canais), prioriza o valor atualizado quando há multa/juros e pode detalhar original, multa, juros e valor atualizado.
- **Card sem mensagem avulsa**: no WhatsApp Oficial a fatura vai direto no card interativo, sem texto separado antes.

## [2.57.0] - 2026-08-01

### ✨ Novo
- **Indicador de novas mensagens na lista**: quando outro contato envia mensagem enquanto você está em um atendimento, a conversa mostra um contador de mensagens novas.
- **Nome do atendente no balão**: mensagens enviadas pelo atendente exibem o nome dele no topo do balão no chat.

### 🔧 Melhoria
- **Preview limpo na lista**: o resumo da última mensagem mostra só o conteúdo, sem a assinatura do atendente.
- **Tempo desde a atribuição**: o “Há X min” conta desde que o atendimento foi atribuído.

### 🐛 Corrigido
- **Mensagem de atribuição**: a mensagem de Perfil → Atribuição volta a ser enviada ao cliente ao atender.
- **Chat ao atualizar ou voltar**: a tela de atendimento não mantém a conversa anterior aberta após atualizar a página ou voltar do dashboard.

## [2.56.1] - 2026-07-30

### 🔧 Melhoria
- **Melhorias internas no módulo de ligação**: ajustes internos no módulo de ligações de voz para maior estabilidade e confiabilidade no atendimento.

## [2.56.0] - 2026-07-28

### ✨ Novo
- **Nova área de Regras de Atendimento**: reorganizada em cards (horário comercial, automação por horário, feriados e configurações gerais). O menu Horário passou a ficar dentro dessa área.
- **Automação por horário**: ligue a IA ou o chatbot automaticamente conforme o horário comercial. O modo mais comum deixa humanos no expediente e ativa a automação quando a empresa está fechada.
- **Feriados e datas especiais**: cadastre feriados de dia inteiro ou com horário parcial (ex.: fechamento a partir das 12h). Essas datas entram no cálculo do atendimento e da automação.
- **Opção para desativar consulta de viabilidade**: em Integrações → Seu ERP, é possível desligar a viabilidade pela IA.

## [2.55.3] - 2026-07-24

### ✨ Novo
- **Avisos no WhatsApp do atendente**: agora é possível receber avisos no WhatsApp quando um atendimento for transferido para você ou entrar na fila de espera.

## [2.55.2] - 2026-07-23

### 🐛 Corrigido
- **Áudio nas ligações de voz**: corrigido o problema em que a ligação conectava, mas a voz do atendente e do cliente não saía. Agora o áudio funciona nos dois sentidos durante a chamada.

### ✨ Novo
- **Várias ligações ao mesmo tempo**: agora é possível fazer e receber várias ligações ao mesmo tempo no painel.

## [2.55.1] - 2026-07-23

### 🐛 Corrigido
- **Envio e abertura de áudio no iOS**: corrigido o envio e a abertura de mensagens de áudio/voz no WhatsApp em dispositivos iOS. Clientes no iPhone deixavam de conseguir ouvir o áudio (“Este áudio não está mais disponível”).

## [2.55.0] - 2026-07-21

### 🐛 Corrigido
- **Envio de fatura no menu de acesso rápido**: corrigido o erro ao enviar fatura pela sidebar Financeiro quando o cliente tinha mais de um contrato. O contrato selecionado passa a ser enviado corretamente.

### ✨ Novo
- **IA envia imagens da galeria**: o agente pode enviar imagens ao cliente. Nomeie a imagem no formato com a tag entre chaves, por exemplo `Cartão 500MB {planos}` — use o nome da tag dentro das chaves (`{planos}`) para a IA localizar e enviar a imagem.

## [2.54.0] - 2026-07-18

### ✨ Novo
- **Consulta de viabilidade pela IA**: a IA verifica se há cobertura para instalação. Pode pedir a localização atual direto pelo WhatsApp do cliente ou o endereço completo (rua, número, bairro, cidade e/ou CEP). Com viabilidade, segue o atendimento; sem viabilidade, informa e oferece a equipe comercial.

### 🔧 Melhorado
- **Como configurar**: em Integrações → Seu ERP, preencha URL, Token, App, **ID do Gateway de mapas** e **Raio máximo (metros)** (ex.: 300). Sem Gateway/Raio, a consulta é só por endereço; com ambos, a IA também consulta por coordenadas no mapa.

## [2.53.0] - 2026-07-16

### 🐛 Corrigido
- **Agente de IA**: várias correções no módulo do agente — encerramento ao agradecer/aguardar, horário real do provedor, fatura sempre com PIX, despedida completa com nome do cliente e do provedor, além de melhorias em diagnóstico, transferência e protocolo.

### 🔧 Melhorado
- **Agente mais personalizável**: o agente respeita melhor a personalidade, o horário e as regras do seu provedor, com respostas mais alinhadas à sua operação.

## [2.52.0] - 2026-07-14

### ✨ Novo
- **Board de ideias**: novo menu Ideias para enviar sugestões, acompanhar o andamento (Em análise, Em desenvolvimento e Concluído) e comentar — disponível para administradores e agentes.
- **Geração de protocolo**: agora é possível gerar e enviar o protocolo de atendimento ao cliente (incluindo a variável `{{protocolo}}` no fluxo do chatbot).
- **Nome do chatbot**: agora é possível dar um nome ao chatbot nas regras de atendimento.

### 🔧 Melhorado
- **Telegram**: melhorias no fluxo de atendimento no canal Telegram, alinhando chatbot e respostas automáticas aos demais canais.

## [2.47.0] - 2026-06-03

### ✨ Novo
- **Contrato suspenso**: agora é possível permitir ou não a abertura de chamado técnico no fluxo quando o contrato do cliente estiver suspenso, em Regras de Atendimento.

## [2.46.0] - 2026-05-29

### ✨ Novo
- **Novo canal disponível: Instagram** — agora é possível atender seus clientes pelo Instagram, com as conversas centralizadas no mesmo painel de atendimento.

### 🔧 Melhorado
- **Telas de cadastro de canais**: modais de WhatsApp, Telegram, Instagram e e-mail com visual mais limpo e padronizado.
- **Modo supervisão**: supervisores podem transferir conversas para outro agente sem assumir o atendimento.
- **Painel de conversas**: abas Atendimento e Espera com nomes completos e barra superior do chat mais compacta.

### 🐛 Corrigido
- **Áudios no WhatsApp do cliente**: alguns áudios enviados pelo painel chegavam ao cliente, mas não reproduziam no celular. Gravações e anexos passam a ser preparados corretamente antes do envio.

## [2.45.0] - 2026-05-29

### ✨ Novo
- **Autenticação em dois fatores (2FA)**: tela no perfil para ativar TOTP (QR code, OTP, recriar chave), login em duas etapas e apps recomendados (Google, Microsoft, FreeOTP, Authy).
- **Aba Em andamento** no painel de conversas (admin): visão de todos os atendimentos humanos em curso com contato, tempo e atendente.

### 🐛 Corrigido
- **Disparos SGP → WhatsApp Meta**: Contrato, Valor e Vencimento extraídos da mensagem preenchida, na ordem correta, sem `body_params` no export do webhook.

## [2.44.0] - 2026-05-26

### ✨ Novo
- **Pesquisa de satisfação do cliente** ao encerrar (lista com 5 opções no WhatsApp Oficial, painel e dashboard atualizados).
- **Controle de horário por equipe**: cadastro na tela Horário (global ou por equipe), com chatbot e IA respeitando o expediente.

### 🔧 Melhorado
- **Acesso Rápido (SGP)**: visual renovado e correção no envio de fatura.

### 🐛 Corrigido
- **Player de áudio no chat**: contador 00:00, barra de progresso e controles de reprodução.
- **Texto duplicado no envio via webhook**: disparo de sistema externo deixava de enviar ao cliente a mensagem com frases repetidas.
- **Campo de envio no modo claro**: texto digitado visível ao escrever no chat.

## [2.42.0] - 2026-05-15

### 🐛 Corrigido
- **Som de notificação**: não toca mais durante atendimento só com o robô; apenas na fila de espera ou conversa atribuída a você.

### ✨ Novo
- **Agora você pode editar o nome do contato** no painel de atendimento (ícone de lápis ao lado do nome).
- **Webhook SGP com texto livre**: disparos sem template, enviando mensagem de texto simples.
- **canal_id** para provedores com mais de um WhatsApp ativo.

### 🔧 Melhorado
- **ID do canal** visível e copiável na tela de canais.
- **Editor de modelos** com cabeçalho, corpo limpo ao criar e prévia alinhada ao WhatsApp.

## [2.39.0] - 2026-05-12

### 🐛 Corrigido
- **Mensagens sempre pelo número certo**: o atendimento não troca mais o número de envio entre canais.
- **Aviso de inatividade sem repetição**: a mensagem de encaminhamento por inatividade agora é enviada apenas uma vez.
- **Imagens da galeria mais estáveis**: as imagens enviadas para a galeria não somem mais.

### ✨ Novo
- **Pré-visualização de PDF no chat**: o chat mostra uma prévia do PDF ao receber/enviar.
- **Colar print no chat (Ctrl+V)**: agora dá para colar uma imagem direto no campo de mensagem.

## [2.34.0] - 2026-04-16

### 🎉 Adicionado
- **Imagem na mensagem inicial do chatbot**: fluxo do chatbot passa a suportar envio de imagem (bloco Galeria / mídia) como parte da automação e da primeira interação com o cliente.
- **Inatividade do cliente na automação**: sistema de detecção e tratamento de inatividade do cliente integrado ao motor de automação, permitindo encerramentos ou ações programadas conforme regras do provedor.

### 🔧 Melhorado
- **Dashboard e tela de atendimento**: painel de conversas renovado com nova experiência de atendimento, organização visual e fluxo mais claro para equipes.

## [2.25.0] - 2026-01-12

### 🎉 Adicionado
- **Bloqueio Automático de Chamados para Contratos Suspensos**: Sistema com 3 camadas de proteção impede abertura de chamados técnicos para contratos suspensos por falta de pagamento
- **Equipe "IA" Automática**: Todas as conversas agora iniciam automaticamente na equipe "IA" com status "snoozed", melhorando a organização do fluxo de atendimento
- **Validação de Status de Contrato**: Backend verifica automaticamente o status do contrato antes de criar chamados técnicos
- **Exibição de Equipe nos Cards**: Frontend agora mostra a equipe responsável no card de cada conversação

### 🔧 Melhorado
- **Sistema de Chat Interno**: Correções importantes na listagem de usuários e sincronização de mensagens em tempo real
- **Prompt da IA Significativamente Melhorado**: 
  - Adicionada regra crítica sobre contratos suspensos com instruções detalhadas
  - Corrigido formato de exibição de contratos para WhatsApp com quebras de linha corretas
  - Melhorada formatação de negrito para WhatsApp (uso correto de asterisco simples)
  - Adicionadas instruções claras sobre quando solicitar CPF/CNPJ do cliente
  - Exemplos práticos de formatação para diferentes cenários
- **Sistema de Transferência da IA**: 
  - Conversas transferidas agora mantêm contexto correto
  - Equipe "IA" é atribuída automaticamente em todas as plataformas (WhatsApp Cloud API, Evolution, Uazapi, Telegram)
  - Melhor sincronização entre frontend e backend para exibição de equipes
- **Endpoint de Usuários em Equipes**: Corrigido para usar `/api/users/my_provider_users/`, garantindo isolamento correto entre provedores
- **Formatação de Mensagens WhatsApp**: Sistema agora limpa automaticamente formatação markdown incorreta antes de enviar mensagens

### 🐛 Corrigido
- **Erro de Variável Indefinida no Prompt**: Corrigido erro `name 'NOME_CLIENTE' is not defined` que impedia a IA de responder
- **Dados Mockados em Equipes**: Removidos usuários fictícios (João Silva, Maria Santos) da listagem de membros de equipe
- **Formatação de Negrito WhatsApp**: Corrigido uso de `**texto**` para `*texto*` em todas as mensagens
- **Serialização de Equipes**: Campo `team` agora é corretamente serializado e enviado para o frontend
- **Priorização de Token de Autenticação**: Frontend agora prioriza `auth_token` ao invés de `token` genérico

### 🛡️ Segurança
- **Isolamento de Usuários por Provedor**: Cada provedor agora visualiza apenas seus próprios usuários ao gerenciar equipes
- **Validação de Contrato Suspenso**: Sistema impede abertura de chamados para contratos inadimplentes, protegendo recursos técnicos

## [2.23.12] - 2025-11-28

### 🎉 Adicionado
- **Sistema de Bloqueio de Contatos para Atendimento**: Agora é possível bloquear contatos para que a IA não responda suas mensagens. O provedor pode ativar/desativar o bloqueio através de um toggle na lista de contatos.
- **Interface de Gerenciamento de Bloqueio**: Adicionada coluna 'ATENDER' na lista de contatos com toggle visual (verde = ativo, vermelho = bloqueado) para gerenciar o bloqueio de atendimento.
- **Filtro de Contatos Bloqueados**: Adicionado filtro para visualizar apenas contatos bloqueados para atendimento, facilitando o gerenciamento.

### 🔧 Melhorado
- **Verificação de Bloqueio nos Webhooks**: Sistema verifica automaticamente se o contato está bloqueado antes de chamar a IA, tanto no webhook Evolution quanto no Uazapi.
- **Auditoria de Bloqueios**: Todas as alterações de bloqueio são registradas no AuditLog para rastreabilidade.

## [2.23.4] - 2025-11-25

### 🎉 Adicionado
- **Parâmetro conteudolimpo no SGP**: Adicionado parâmetro para remover mensagem padrão 'Chamado via URA' do SGP, permitindo usar formato personalizado 'Chamado aberto via NIOCHAT'
- **Verificação Obrigatória de Horário de Funcionamento**: Implementada verificação obrigatória antes de criar chamado técnico, informando ao cliente quando será atendido se estiver fora do horário

### 🔧 Melhorado
- **Mensagens Variadas de Confirmação de Chamado**: Sistema agora gera mensagens variadas incluindo o relato literal do cliente, tornando a comunicação mais natural
- **Saudações Variadas e Naturais**: IA agora varia saudações naturalmente (ex: 'Oii, tudo bem?', 'Boa noite! Como posso ajudar?', 'Olá! Em que posso te ajudar?') ao invés de sempre usar a mesma frase
- **Prevenção de Repetição de Mensagens**: Adicionadas instruções reforçadas para IA consultar histórico completo antes de responder, evitando repetição de mensagens e perguntas
- **Uso de Relato Literal do Cliente**: Melhoradas descrições dos parâmetros para garantir que IA use exatamente o que o cliente disse, não resumos genéricos

### 🐛 Corrigido
- **Formato da Descrição de Chamados**: Corrigido formato para 'Chamado aberto via NIOCHAT\nCliente relatou: [relato do cliente]' removendo duplicação de texto

## [2.24.0] - 2025-11-23

### 🎉 Adicionado
- **Sistema CSAT com Processamento Assíncrono**: Implementado sistema completo de CSAT (Customer Satisfaction Score) com processamento assíncrono usando Dramatiq e RabbitMQ
- **Integração Dramatiq + RabbitMQ**: Sistema de filas assíncronas para processamento de tarefas em background, garantindo alta performance e escalabilidade
- **Agendamento Inteligente de CSAT**: CSATs são agendados automaticamente com delay configurável (padrão: 2 minutos após encerramento) usando delay/eta do Dramatiq
- **Logging Detalhado**: Sistema de logging completo com logs explícitos [DRAMATIQ] para facilitar debugging e monitoramento

### 🔧 Melhorado
- **Configuração de Middleware Dramatiq**: Configurado middleware completo (AgeLimit, Retries, TimeLimit) para garantir que mensagens não sejam perdidas
- **Tratamento de Erros**: Implementado tratamento adequado para evitar que mensagens caiam em dead letter queues
- **Consistência de Timezone**: Ajustado cálculo de delay e timezone para garantir consistência, sempre usando UTC

### 🐛 Corrigido
- **Fluxo de Envio CSAT**: Corrigido problema onde tarefas CSAT não eram enviadas para o Dramatiq quando havia delay
- **Cálculo de Delay**: Ajustado cálculo de delay e timezone para garantir consistência entre scheduled_send_at e eta
- **Dead Letter Queue**: Prevenção de mensagens em default.DQ, garantindo reprocessamento automático

## [2.1.5] - 2025-01-XX

### 🎉 Adicionado
- **Sistema CSAT Completo**: Coleta automática de feedback com dashboard
- **Análise de Sentimento IA**: Interpretação automática de feedback textual
- **Auditoria Avançada**: Histórico completo de conversas e avaliações
- **Dashboard Melhorado**: Métricas em tempo real e gráficos interativos
- **Isolamento de Dados**: Segurança total entre provedores
- **Automação Celery**: Tarefas programadas para CSAT
- **Interface Otimizada**: Componentes sem emojis e mais profissional
- **Transferência para Equipes**: Novo endpoint `/transfer_to_team/` para transferência correta
- **Classificação de Conversas**: Lógica aprimorada para abas (Com IA, Em Espera, Em Atendimento)
- **Sistema de Equipes**: Conversas transferidas ficam visíveis para toda a equipe

### 🔧 Melhorado
- **Performance**: Otimizações no dashboard e carregamento de dados
- **UX**: Interface mais limpa e profissional
- **Segurança**: Isolamento total de dados entre provedores
- **Relatórios**: Gráficos mais informativos e interativos

### 🐛 Corrigido
- **CSAT**: Correção no envio automático de pesquisas
- **Transferência**: Correção na lógica de transferência para equipes
- **Dashboard**: Correção na atualização de métricas em tempo real
- **Auditoria**: Correção na exibição de logs de auditoria

## [2.0.0] - 2024-12-XX

### 🎉 Adicionado
- **Integração ChatGPT**: IA conversacional avançada
- **SGP Automático**: Consulta dados reais do cliente
- **Function Calls**: IA executa funções SGP em tempo real
- **Fluxo Inteligente**: Detecção automática de demandas
- **Personalidade Avançada**: Customização completa da IA
- **Geração Automática**: Faturas com PIX e QR Code
- **Atendimento 3x mais rápido**: Sem perguntas desnecessárias

### 🔧 Melhorado
- **Performance**: Atendimento automatizado 24/7
- **Precisão**: Dados reais do SGP, nunca inventados
- **Velocidade**: Respostas instantâneas com dados completos
- **Personalização**: IA única para cada provedor

## [1.0.0] - 2024-XX-XX

### 🎉 Adicionado
- **Sistema Base**: Estrutura completa do NioChat
- **Integração WhatsApp**: Uazapi/Evolution API integrado
- **Interface React**: Interface moderna e responsiva
- **WebSocket**: Comunicação em tempo real
- **Sistema de Reações**: Emojis e exclusão de mensagens
- **Gestão de Equipes**: Organização por equipes
- **Upload de Mídia**: Suporte completo a mídia
- **Painel Admin**: Interface Django customizada
- **Sistema Multi-tenant**: Suporte a múltiplos provedores
- **Logs de Auditoria**: Sistema completo de auditoria
- **Integrações Múltiplas**: WhatsApp, Telegram, Email, Nio Chat
- **Permissões Granulares**: Controle fino de acesso
- **Configurações Avançadas**: Provedores personalizáveis
- **Webhooks Configuráveis**: Integração flexível

### 🔧 Melhorado
- **Arquitetura**: Sistema escalável e robusto
- **Segurança**: Isolamento total entre provedores
- **Performance**: Otimizações em todas as camadas
- **UX**: Interface intuitiva e moderna

## 🚀 Roadmap

### Próximas Versões
- **v2.2.0**: Integração com mais sistemas de gestão
- **v2.3.0**: IA multilíngue
- **v2.4.0**: Dashboard avançado com mais métricas
- **v3.0.0**: Arquitetura microserviços

### Funcionalidades Planejadas
- **Integração CRM**: Conectores para CRMs populares
- **IA Multilíngue**: Suporte a múltiplos idiomas
- **Dashboard Avançado**: Mais métricas e relatórios
- **Arquitetura Microserviços**: Escalabilidade máxima
- **Mobile App**: Aplicativo nativo para mobile
- **API GraphQL**: API mais flexível
- **Integração Slack**: Notificações no Slack
- **Integração Teams**: Notificações no Microsoft Teams

## 📊 Estatísticas

### Desenvolvimento
- **Commits**: 500+
- **Issues**: 50+ resolvidas
- **Pull Requests**: 100+ aprovados
- **Contribuidores**: 5+

### Funcionalidades
- **Endpoints API**: 50+
- **Componentes React**: 100+
- **Integrações**: 10+
- **Testes**: 200+

### Performance
- **Tempo de Resposta**: < 200ms
- **Uptime**: 99.9%
- **Escalabilidade**: 1000+ usuários simultâneos
- **Disponibilidade**: 24/7

## 🏆 Reconhecimentos

### Tecnologias Utilizadas
- **Django 5.2**: Framework web robusto
- **React 18**: Interface moderna
- **PostgreSQL**: Banco de dados confiável
- **Redis**: Cache e sessões
- **Celery**: Processamento assíncrono
- **WebSocket**: Tempo real
- **OpenAI**: IA avançada
- **Supabase**: Dashboard e auditoria

### Integrações
- **Uazapi/Evolution**: WhatsApp Business
- **OpenAI ChatGPT**: IA conversacional
- **SGP**: Sistema de gestão
- **Supabase**: Dashboard e dados
- **Telegram**: Notificações
- **Email**: Comunicação

## 📝 Notas de Versão

### v2.1.5
Esta versão representa um marco importante no desenvolvimento do NioChat, com a introdução do sistema CSAT completo e auditoria avançada. O sistema agora oferece:

- **Coleta automática de feedback** com análise de sentimento
- **Dashboard em tempo real** com métricas precisas
- **Auditoria completa** de todas as ações do sistema
- **Isolamento total** de dados entre provedores
- **Interface otimizada** para melhor experiência do usuário

### v2.0.0
Esta versão revolucionou o atendimento automatizado com a introdução da IA inteligente e integração SGP. O sistema agora oferece:

- **Atendimento 24/7** com IA avançada
- **Dados reais** do SGP, nunca inventados
- **Function Calls** para ações automáticas
- **Personalização completa** da IA por provedor
- **Fluxo inteligente** sem perguntas desnecessárias

### v1.0.0
Esta versão estabeleceu a base sólida do NioChat com:

- **Arquitetura robusta** e escalável
- **Integração completa** com WhatsApp
- **Interface moderna** e responsiva
- **Sistema multi-tenant** com isolamento total
- **Permissões granulares** para controle fino

## 🔗 Links Úteis

- **GitHub**: [github.com/juniorssilvaa/niochat](https://github.com/juniorssilvaa/niochat)
- **Documentação**: [docs.niohub.com.br](https://docs.niohub.com.br)
- **Demo**: [demo.niohub.com.br](https://demo.niohub.com.br)
- **Suporte**: [suporte@niohub.com.br](mailto:suporte@niohub.com.br)

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](https://github.com/juniorssilvaa/niochat/blob/main/LICENSE) para mais detalhes.

