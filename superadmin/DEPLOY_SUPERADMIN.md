# Deploy do Superadmin (VPS dedicada)

Este deploy publica o painel do Superadmin no domínio `app.niohub.com.br` usando Traefik e rede externa `NioNet`.

## Arquivos

- `superadmin/docker-compose.superadmin.yml`
- `superadmin/Dockerfile`
- `superadmin/nginx.default.conf`
- `superadmin/.env.superadmin.example`

## 1) Preparar DNS

Crie o A record:

- `app.niohub.com.br` -> IP da VPS do Superadmin

## 2) Garantir rede Docker

Na VPS (uma vez):

```bash
docker network create NioNet
```

Se a rede ja existir, pode ignorar.

## 3) Variaveis de ambiente

Copie o exemplo para `.env` no mesmo diretorio do compose:

```bash
cp superadmin/.env.superadmin.example superadmin/.env
```

Preencha as senhas/chaves obrigatorias.

## 4) Subir stack

Com Docker Compose:

```bash
docker compose --env-file superadmin/.env -f superadmin/docker-compose.superadmin.yml up -d --build
```

Depois da primeira subida, para atualizar por imagem no Portainer/Compose:

```bash
docker compose --env-file superadmin/.env -f superadmin/docker-compose.superadmin.yml pull
docker compose --env-file superadmin/.env -f superadmin/docker-compose.superadmin.yml up -d
```

No Portainer:

1. `Stacks` -> `Add stack`
2. Cole o conteudo de `superadmin/docker-compose.superadmin.yml`
3. Em `Environment variables`, adicione as variaveis do `.env.superadmin.example`
4. Deploy

## 5) Servicos esperados

- `superadmin-frontend` (React build + Nginx)
- `superadmin-backend` (Django + Daphne)
- `superadmin-dramatiq` (jobs/filas)
- `superadmin-postgres`
- `superadmin-redis`
- `superadmin-rabbitmq`

## 6) Roteamento

- Frontend: `https://app.niohub.com.br`
- Backend/API/WebSocket: mesmo host, paths:
  - `/api`
  - `/api-token-auth`
  - `/auth`
  - `/webhook` e `/webhooks`
  - `/media`
  - `/ws`

### Webhook Asaas (desbloqueio de provedor)

URL em produção:

```text
https://app.niohub.com.br/api/webhooks/asaas/
```

## 7) Primeiro acesso

Após subir, crie o superadmin no backend se necessario:

```bash
docker exec -it superadmin_backend python manage.py createsuperuser
```

## Imagens publicadas (GitHub Container Registry)

- `ghcr.io/juniorssilvaa/niohub_chat-superadmin-backend:latest`
- `ghcr.io/juniorssilvaa/niohub_chat-dramatiq:latest`
- `ghcr.io/juniorssilvaa/niohub_chat-superadmin:latest`

## Dev local (admin.niohub.com.br)

Somente para máquina de desenvolvimento: use `admin.niohub.com.br` no `/etc/hosts` apontando para `127.0.0.1` e o nginx em `nginx/sites/admin.niohub.com.br.conf` (portas 8013 front / 8010 API). **Não** altere o docker-compose de produção para esse domínio.

## App Mobile — API pública (`/v1/`)

O app do cliente (Flutter) usa a base:

```text
https://api.niohub.com.br/v1/
```

O domínio `api.niohub.com.br` aponta para o backend do Superadmin (`/v1/...`).  
Gestão no painel continua em `/api/mobile-app/...`. Detalhes e endpoints: [README.md](../README.md#app-mobile-api-pública).
