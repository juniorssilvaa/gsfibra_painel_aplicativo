# NioChat

Sistema de atendimento via WhatsApp com IA inteligente, CSAT automatizado e análise avançada.

## Funcionalidades

### IA Inteligente
- ChatGPT integrado para respostas automáticas
- Transcrição de áudio em tempo real
- Análise de sentimento e intenções
- Consulta automática ao SGP
- Aprendizado contínuo com feedback

### WhatsApp Completo
- Integração nativa com WhatsApp Business API
- Suporte a mídia rica (imagens, vídeos, áudios)
- Templates oficiais e botões interativos
- Status de entrega e leitura
- Multi-instância e QR Code dinâmico

### Sistema CSAT
- Envio automático após fechamento de conversas
- Processamento assíncrono com Dramatiq e RabbitMQ
- Suporte a múltiplos canais (WhatsApp, Telegram)
- Retry automático em caso de falhas
- Monitoramento de status de envio
- Isolamento por provedor de serviço
- Análise de feedback com IA
- Dashboard com métricas em tempo real

### Dashboard Avançado
- KPIs em tempo real
- Gráficos interativos
- Relatórios customizáveis
- Filtros avançados
- Exportação em múltiplos formatos

### Sistema Multi-tenant
- Isolamento completo de dados
- Customização por tenant
- Billing separado
- Domínios personalizados
- Backup individualizado

### Recuperador de Conversas
- Sincronização automática
- Histórico completo
- Mídia preservada
- Metadados mantidos
- Performance otimizada

## Arquitetura

### Backend
- Django REST Framework
- PostgreSQL (Supabase)
- Redis Cache
- RabbitMQ
- Dramatiq
- WebSockets

### Frontend
- React.js
- Material UI
- WebSocket Client
- Service Workers
- PWA Ready

### Infraestrutura
- Docker + Docker Compose
- Nginx
- Let's Encrypt SSL
- GitHub Actions CI/CD
- Portainer

## Fluxo de Dados

1. Cliente envia mensagem via WhatsApp
2. Uazapi/Evolution API recebe e dispara webhook
3. Backend processa e armazena no PostgreSQL
4. WebSocket notifica frontend em tempo real
5. IA analisa mensagem e sugere respostas
6. Agente responde ou IA responde automaticamente
7. Resposta é enviada via WhatsApp
8. Após fechamento, CSAT é enviado via Dramatiq
9. Feedback é coletado e analisado
10. Métricas são atualizadas em tempo real

## Início Rápido

1. Clone o repositório
```bash
git clone https://github.com/juniorssilvaa/niochat.git
cd niochat
```

2. Configure as variáveis de ambiente
```bash
cp .env.example .env
# Edite .env com suas configurações
```

3. Inicie os containers
```bash
docker-compose up -d
```

4. Acesse o sistema (Docker / stack padrão — ver compose do projeto)

Para desenvolvimento local sem Docker, as portas seguem o **Vite** (`vite.dev.js`) em cada app:

| App | Frontend (Vite) | Backend (Daphne / proxy) |
|-----|-----------------|----------------------------|
| **Superadmin** (`superadmin/front`) | **8013** | **8010** → `niochat_sa.asgi` |
| **Painel do provedor** (`painel-provedor/front`) | **8012** | **8011** → `niochat.asgi` |

Abra no navegador: **Superadmin** → http://localhost:8013 · **Provedor** → http://localhost:8012

## App Mobile (API pública)

API consumida pelo aplicativo do cliente (Flutter). Base de produção:

```text
https://api.niohub.com.br/v1/
```

No `config.dart` do app:

```dart
static const String _envApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://api.niohub.com.br/v1/',
);
```

| Método | Endpoint | Uso |
|--------|----------|-----|
| `POST` | `/v1/auth/login` | Login / registro do cliente |
| `GET` | `/v1/home` | Branding, tools, config do provedor |
| `GET` | `/v1/plans` | Planos |
| `GET` | `/v1/warnings` | Avisos in-app |
| `POST` | `/v1/warnings/dismiss` | Dispensar aviso |
| `GET` | `/v1/time` | Horário do servidor |
| `POST` | `/v1/devices/register` | Registrar device / push |
| `POST` | `/v1/webhooks/push` | Webhook de push (SGP → app) |

Autenticação do provedor: header/query `provider_token` (`sk_live_...`) gerado no **Superadmin** ao ativar o App Mobile.

- **Dev local:** `http://127.0.0.1:8010/v1/`
- **Painel (Superadmin / provedor):** continua em `/api/mobile-app/...` (não usar no app)

Apps já publicados com `https://apis.niochat.com.br/api/` devem permanecer apontando ao painel antigo até a atualização nas lojas com a nova base `/v1/` e o token do Superadmin.

## Documentação

- [Instalação](docs/installation.md)
- [Configuração](docs/configuration.md)
- [API](docs/api.md)
- [Desenvolvimento](docs/development.md)
- [Deploy Superadmin](superadmin/DEPLOY_SUPERADMIN.md)

## Tecnologias

- Python 3.12
- Django 5.0
- PostgreSQL 14
- Redis 7
- RabbitMQ 3
- React 18
- Material UI 5
- Docker
- Nginx
- Dramatiq

## Casos de Uso

- Provedores de Internet
- E-commerce
- Suporte Técnico
- Atendimento ao Cliente
- Vendas
- SAC

## Métricas

- 95%+ de satisfação dos clientes
- -50% no tempo de resposta
- +30% em eficiência operacional
- 99.9% de uptime
- Escalável para milhões de mensagens

## Segurança

- Autenticação JWT
- 2FA
- Criptografia em repouso
- SSL/TLS
- Backup automático
- Logs de auditoria
- Conformidade LGPD

## Sistema CSAT

O NioChat inclui um sistema CSAT (Customer Satisfaction) completo para coletar e analisar feedback dos clientes:

### Coleta Automática
- Envio automático após fechamento de conversas
- Processamento assíncrono com Dramatiq
- Retry automático em caso de falhas
- Monitoramento de status de envio
- Isolamento por provedor

### Análise IA
- Interpretação de feedback textual
- Mapeamento de emojis para sentimentos
- Identificação de temas recorrentes
- Sugestões de melhorias
- Alertas para feedback negativo

### Dashboard
- Métricas em tempo real
- Histórico detalhado
- Filtros avançados
- Exportação de relatórios
- Insights automáticos

## Auditoria

Sistema completo de auditoria para rastreamento de ações:

- Log de todas ações
- Trilha de auditoria
- Exportação de logs
- Retenção configurável
- Alertas de segurança

## Licença

Copyright © 2024 NioChat. Todos os direitos reservados.