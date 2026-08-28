# Configuração do Banco de Dados em Produção

## Problema Resolvido

O backend agora está configurado para usar automaticamente o PostgreSQL de produção quando `ENVIRONMENT=production`.

## Como Funciona

### 1. Prioridade de Configuração

1. **DATABASE_URL** (mais alta prioridade)
   - Se definida, será usada diretamente
   - Formato: `postgresql://usuario:senha@host:porta/banco`

2. **Variáveis Individuais** (se DATABASE_URL não estiver definida)
   - `POSTGRES_HOST` - Host do PostgreSQL
   - `POSTGRES_USER` - Usuário
   - `POSTGRES_PASSWORD` - Senha
   - `POSTGRES_DB` - Nome do banco
   - `POSTGRES_PORT` - Porta (padrão: 5432)

3. **Detecção Automática em Produção**
   - Se `ENVIRONMENT=production` E `POSTGRES_HOST` for "postgres" ou vazio
   - O sistema usa automaticamente `POSTGRES_PRODUCTION_HOST` (padrão: 178.156.219.104)

## Configuração no .env

Para produção, configure no arquivo `.env`:

```env
# Ambiente
ENVIRONMENT=production

# PostgreSQL de Produção
POSTGRES_HOST=178.156.219.104
POSTGRES_PORT=5432
POSTGRES_USER=niochat_user
POSTGRES_PASSWORD=E0sJT3wAYFuahovmHkxgy
POSTGRES_DB=niochat

# OU use DATABASE_URL completa (opcional)
# DATABASE_URL=postgresql://niochat_user:E0sJT3wAYFuahovmHkxgy@178.156.219.104:5432/niochat
```

## Para Desenvolvimento Local

```env
# Ambiente
ENVIRONMENT=development

# PostgreSQL Local (container)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=niochat_user
POSTGRES_PASSWORD=E0sJT3wAYFuahovmHkxgy
POSTGRES_DB=niochat
```

## Verificação

Após configurar, verifique a conexão:

```bash
# No container do backend
docker-compose exec niochat-backend python manage.py dbshell

# Ou testar conexão
docker-compose exec niochat-backend python manage.py check --database default
```

## Notas Importantes

1. **Senha do PostgreSQL**: A senha no banco de produção DEVE ser `E0sJT3wAYFuahovmHkxgy`
   - Se a senha estiver diferente, altere no PostgreSQL:
   ```sql
   ALTER USER niochat_user WITH PASSWORD 'E0sJT3wAYFuahovmHkxgy';
   ```

2. **Firewall**: Certifique-se de que a porta 5432 está aberta no servidor de produção (178.156.219.104)

3. **Variável ENVIRONMENT**: Deve estar configurada como `production` no .env ou nas variáveis de ambiente do Docker/Portainer

