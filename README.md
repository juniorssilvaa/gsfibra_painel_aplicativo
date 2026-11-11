# GSFibra

Painel do aplicativo do provedor.

## Estrutura

```
front/     # SPA React (porta 8014 em dev)
backend/   # Django API (porta 8010)
```

## Desenvolvimento

```bash
# Backend
cd backend
python -m venv venv
# Windows: .\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8010

# Front (outro terminal)
pnpm --dir front install
pnpm --dir front dev
# http://localhost:8014
```

O Vite faz proxy de `/api` e `/ws` para `localhost:8010`.

## Produção

- Front + API (Swarm/Traefik): `docker-compose.yml`
- **Instalador no servidor do provedor** (convive com GenieACS na porta **8443**):

```bash
cd installer/provedor
chmod +x install.sh
sudo ./install.sh
# URL padrão: https://painelapp.gsfibra.com:8443
```

Detalhes: `installer/provedor/README.md`
