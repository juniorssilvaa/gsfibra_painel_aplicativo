# Instalação em Desenvolvimento

Este guia explica como configurar o ambiente de desenvolvimento do NioChat.

## Portas locais (fonte: `vite.dev.js`)

O frontend em desenvolvimento usa **Vite**; o proxy HTTP/WebSocket aponta para o backend na porta indicada.

| Aplicação | Pasta do front | Porta Vite (browser) | Porta API (Daphne) | Módulo ASGI |
|-----------|----------------|----------------------|--------------------|-------------|
| **Superadmin** | `superadmin/front` | **8013** | **8010** | `niochat_sa.asgi:application` |
| **Painel do provedor** | `painel-provedor/front` | **8012** | **8011** | `niochat.asgi:application` |

Comandos típicos (Windows PowerShell), um terminal para API e outro para Vite:

**Superadmin — API**
```powershell
cd superadmin\backend
.\venv\Scripts\Activate.ps1
daphne -b 0.0.0.0 -p 8010 niochat_sa.asgi:application
```

**Superadmin — front**
```powershell
cd superadmin\front
npx --yes pnpm@10.4.1 run dev
```
→ http://localhost:8013

**Provedor — API**
```powershell
cd painel-provedor\backend
.\venv\Scripts\Activate.ps1
daphne -b 0.0.0.0 -p 8011 niochat.asgi:application
```

**Provedor — front**
```powershell
cd painel-provedor\front
npx --yes pnpm@10.4.1 run dev
```
→ http://localhost:8012

Rodar **Superadmin** e **Painel do provedor** ao mesmo tempo: use **8010+8013** e **8011+8012** (sem conflito).

---

## Pré-requisitos

### Software Necessário
- **Python**: 3.8 ou superior
- **Node.js**: 16 ou superior
- **PostgreSQL**: 12 ou superior
- **Redis**: 6 ou superior
- **Git**: Para clonar o repositório

### Sistema Operacional
- **Ubuntu**: 20.04+
- **CentOS**: 8+
- **macOS**: 10.15+
- **Windows**: 10+ (com WSL recomendado)

## Instalação

### 1. Clone do Repositório
```bash
git clone https://github.com/juniorssilvaa/niochat.git
cd niochat
```

### 2. Configurar Backend

#### Criar Ambiente Virtual
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/macOS
# ou
venv\Scripts\activate  # Windows
```

#### Instalar Dependências
```bash
pip install -r requirements.txt
```

#### Configurar Banco de Dados
```bash
# Criar banco de dados
createdb niochat

# Aplicar migrações
python manage.py migrate

# Criar superusuário
python manage.py createsuperuser

# Coletar arquivos estáticos
python manage.py collectstatic
```

### 3. Configurar Frontend

#### Instalar Dependências
```bash
cd frontend/frontend
npm install
```

#### Build de Desenvolvimento
```bash
npm run build
```

### 4. Configurar Variáveis de Ambiente

#### Criar arquivo .env
```bash
cd backend
cp .env.example .env
```

#### Configurar .env
```env
# Django
DEBUG=True
SECRET_KEY=sua_chave_secreta_aqui
ALLOWED_HOSTS=localhost,127.0.0.1

# Banco de Dados
DATABASE_URL=postgresql://usuario:senha@localhost:5432/niochat

# Redis (porta 6379)
REDIS_URL=redis://:SUA_SENHA_REDIS@49.12.9.11:6379/0
REDIS_HOST=49.12.9.11
REDIS_PORT=6379
REDIS_PASSWORD=SUA_SENHA_REDIS

# RabbitMQ (para Dramatiq broker)
DRAMATIQ_BROKER_URL=amqp://niochat:ccf9e819f70a54bb790487f2438da6ee@49.12.9.11:5672

# OpenAI
OPENAI_API_KEY=sua_chave_openai

# Supabase
SUPABASE_URL=sua_url_supabase
SUPABASE_ANON_KEY=sua_chave_supabase

# Uazapi
UAZAPI_URL=https://seu-provedor.uazapi.com
UAZAPI_TOKEN=seu_token_uazapi
```

## Executar o Sistema

### 1. Iniciar Serviços

#### Terminal 1 - Backend
```bash
cd backend
source venv/bin/activate
python manage.py runserver 0.0.0.0:8010
```

#### Terminal 2 - Dramatiq Worker
```bash
cd backend
source venv/bin/activate
python -m dramatiq conversations.dramatiq_tasks integrations.dramatiq_tasks
```

**Nota:** Os módulos de tasks devem ser passados explicitamente para que o worker encontre todos os atores. O `niochat.dramatiq_config` será importado automaticamente pelos módulos de tasks quando necessário.

#### Terminal 3 - Frontend
```bash
cd frontend/frontend
npm run dev
```

### 2. Acessar o Sistema

Use as portas da tabela no início deste documento (Vite + Daphne). O exemplo legado abaixo usa `runserver` na 8010; em desenvolvimento atual prefira **Daphne** nas portas dos `vite.dev.js`.

- **Frontend (provedor, Vite)**: http://localhost:8012
- **Frontend (superadmin, Vite)**: http://localhost:8013
- **Backend**: conforme proxy (8010 superadmin, 8011 provedor)
- **Admin Django**: http://localhost:8010/admin ou http://localhost:8011/admin conforme o app

## Configuração Adicional

### Redis (Porta 6380)
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis-server

# CentOS/RHEL
sudo yum install redis
sudo systemctl start redis

# macOS
brew install redis
brew services start redis

# Configurar Redis para porta 6380 (se necessário)
# Editar /etc/redis/redis.conf
# port 6380
# requirepass SUA_SENHA_REDIS
```

### RabbitMQ (para Celery)
```bash
# Ubuntu/Debian
sudo apt install rabbitmq-server
sudo systemctl start rabbitmq-server
sudo systemctl enable rabbitmq-server

# CentOS/RHEL
sudo yum install rabbitmq-server
sudo systemctl start rabbitmq-server
sudo systemctl enable rabbitmq-server

# macOS
brew install rabbitmq
brew services start rabbitmq

# Configurar usuário e senha
sudo rabbitmqctl add_user admin SUA_SENHA_RABBITMQ
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
```

### PostgreSQL
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb niochat

# CentOS/RHEL
sudo yum install postgresql postgresql-server
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo -u postgres createdb niochat

# macOS
brew install postgresql
brew services start postgresql
createdb niochat
```

## Desenvolvimento

### Estrutura do Projeto
```
niochat/
├── backend/                 # Django Backend
│   ├── niochat/           # Configurações Django
│   ├── core/              # Aplicação principal
│   ├── conversations/      # Sistema de conversas
│   ├── integrations/       # Integrações externas
│   └── requirements.txt    # Dependências Python
├── frontend/               # React Frontend
│   └── frontend/           # Aplicação React
│       ├── src/           # Código fonte
│       ├── public/        # Arquivos públicos
│       └── package.json   # Dependências Node.js
└── docs/                   # Documentação
```

### Comandos Úteis

#### Backend
```bash
# Aplicar migrações
python manage.py migrate

# Criar migração
python manage.py makemigrations

# Shell Django
python manage.py shell

# Testes
python manage.py test

# Coletar estáticos
python manage.py collectstatic
```

#### Frontend
```bash
# Instalar dependências
npm install

# Desenvolvimento
npm run dev

# Build produção
npm run build

# Testes
npm test

# Lint
npm run lint
```

### Debugging

#### Logs do Django
```bash
# Ver logs em tempo real
tail -f logs/django.log

# Configurar nível de log
export DJANGO_LOG_LEVEL=DEBUG
```

#### Logs do Celery
```bash
# Ver logs do worker
tail -f logs/celery.log

# Verificar workers ativos
celery -A niochat inspect active
```

#### Logs do Redis
```bash
# Monitorar Redis
redis-cli monitor

# Verificar conexão
redis-cli ping
```

## Troubleshooting

### Problemas Comuns

#### Porta já em uso
```bash
# Verificar processos na porta
lsof -i :8010
lsof -i :5173

# Matar processo
kill -9 PID
```

#### Erro de banco de dados
```bash
# Verificar conexão
python manage.py dbshell

# Resetar banco
python manage.py flush
```

#### Erro de Redis
```bash
# Verificar status
redis-cli -h 49.12.9.11 -p 6379 -a SUA_SENHA_REDIS ping

# Reiniciar Redis
sudo systemctl restart redis-server
```

#### Erro de RabbitMQ
```bash
# Verificar status
sudo systemctl status rabbitmq-server

# Verificar conexão
rabbitmqctl status

# Reiniciar RabbitMQ
sudo systemctl restart rabbitmq-server
```

#### Erro de dependências
```bash
# Atualizar pip
pip install --upgrade pip

# Reinstalar dependências
pip install -r requirements.txt --force-reinstall
```

### Comandos de Diagnóstico

#### Verificar Status
```bash
# Django
python manage.py check

# Banco de dados
python manage.py dbshell

# Redis
redis-cli -h 49.12.9.11 -p 6379 -a SUA_SENHA_REDIS ping

# RabbitMQ
rabbitmqctl status

# Celery
celery -A niochat inspect stats
```

#### Limpar Cache
```bash
# Django
python manage.py clear_cache

# Redis
redis-cli flushall

# Node.js
npm cache clean --force
```

## Próximos Passos

1. [Configuração do Supabase](../configuration/supabase.md) - Configure a integração com o Supabase.
2. [Uso da Interface](../usage/interface.md) - Aprenda a usar a interface do NioChat.
3. [Endpoints da API](../api/endpoints.md) - Explore a API do NioChat.
4. [Solução de Problemas](../development/troubleshooting.md) - Encontre soluções para problemas comuns.