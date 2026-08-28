# Como Corrigir a Senha do PostgreSQL

## Problema
O erro `password authentication failed for user "niochat_user"` ocorre quando o PostgreSQL foi inicializado com uma senha diferente da configurada no `docker-compose.yml`.

## Solução 1: Recriar o Volume do PostgreSQL (Recomendado)

Se você não tem dados importantes no banco, a solução mais simples é recriar o volume:

```bash
# Parar os containers
docker-compose down

# Remover o volume do PostgreSQL (CUIDADO: Isso apaga todos os dados!)
docker volume rm niochat_niochat-postgres

# Ou se o volume tiver outro nome:
docker volume ls | grep postgres
docker volume rm <nome-do-volume>

# Recriar e iniciar os containers
docker-compose up -d
```

## Solução 2: Alterar a Senha Manualmente (Preserva Dados)

Se você tem dados importantes, altere a senha diretamente no PostgreSQL:

```bash
# Conectar ao container do PostgreSQL
docker-compose exec postgres psql -U niochat_user -d niochat

# Ou se não conseguir conectar, use o usuário postgres (superuser)
docker-compose exec postgres psql -U postgres -d niochat

# Alterar a senha do usuário
ALTER USER niochat_user WITH PASSWORD 'E0sJT3wAYFuahovmHkxgy';

# Sair do psql
\q
```

## Solução 3: Verificar Variáveis de Ambiente

Certifique-se de que a variável `DATABASE_URL` não está sobrescrevendo a configuração:

```bash
# Verificar variáveis de ambiente do container
docker-compose exec niochat-backend env | grep DATABASE
docker-compose exec niochat-backend env | grep POSTGRES
```

## Verificação

Após aplicar a correção, verifique a conexão:

```bash
# Testar conexão do backend
docker-compose exec niochat-backend python manage.py dbshell

# Ou testar diretamente do container do PostgreSQL
docker-compose exec postgres psql -U niochat_user -d niochat -c "SELECT version();"
```

## Nota Importante

A senha correta configurada no `docker-compose.yml` é:
- **Usuário**: `niochat_user`
- **Senha**: `E0sJT3wAYFuahovmHkxgy`
- **Database**: `niochat`
- **Host**: `postgres`
- **Port**: `5432`

A `DATABASE_URL` completa é:
```
postgresql://niochat_user:E0sJT3wAYFuahovmHkxgy@postgres:5432/niochat
```

