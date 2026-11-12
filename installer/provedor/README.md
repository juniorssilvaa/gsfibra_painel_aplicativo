# Instalador — Painel do Aplicativo GS Fibra

Sobe o painel web do app no **mesmo servidor do GenieACS**, no **mesmo domínio**, em **outra porta**.

| Sistema | URL |
|---------|-----|
| ACS (já instalado) | `https://painelapp.gsfibra.com` → **443** |
| Painel do app | `https://painelapp.gsfibra.com:8443` → **8443** |

## Portas

### Já usadas pelo ACS (não usar)
- 80 / 443 — Caddy ACS  
- 7547 / 7557 / 7567 — GenieACS  
- 8000 — Painel ACS  
- 3000 / 5432 / 27017 — internos ACS  

### Este instalador
- **8443** (padrão) — HTTPS do painel do app (Caddy)  
- Postgres / Redis / RabbitMQ — **só rede Docker** (não publica no host)

## Como usar (Linux)

No servidor você **não** precisa do código-fonte completo.

```bash
tar -xzf installer-gsfibra-painel.tar.gz
cd installer/provedor
chmod +x install.sh
sudo ./install.sh
```

O script pergunta domínio, porta, TLS, registry e admin; gera `.env` + `Caddyfile` e sobe o Compose.

## Imagens (GHCR)

- `ghcr.io/juniorssilvaa/gsfibra_painel_aplicativo:<tag>` — front (nginx)  
- `ghcr.io/juniorssilvaa/gsfibra_painel_aplicativo-backend:<tag>` — API Django  

Repositório: https://github.com/juniorssilvaa/gsfibra_painel_aplicativo

O front de produção para este instalador deve ser buildado com **`VITE_API_URL` vazio** (mesmo origin: Caddy encaminha `/api` e `/v1`).

## TLS

- `acs` (recomendado): copia o certificado Let's Encrypt do Caddy do ACS (`installer_caddy_data`) — remove o aviso **Não seguro**.  
- `internal`: certificado Caddy local — browser mostra **Não seguro**.  
- `acme`: Let's Encrypt direto — em porta ≠ 443 costuma falhar sem DNS-01.

Já instalado com `internal`? No servidor:

```bash
cd installer/provedor
chmod +x fix-tls-from-acs.sh
sudo ./fix-tls-from-acs.sh painelapp.gsfibra.com 8443
```

Com Cloudflare no domínio, use Full SSL apontando a origem para `IP:8443`.

## Firebase (push)

Coloque `firebase-credentials.json` neste diretório **antes** ou **depois** do install:

```bash
# depois de copiar o arquivo
docker compose up -d gsfibra-backend
```

Sem o arquivo, o painel sobe; envio FCM fica desativado.

## Comandos úteis

```bash
cd installer/provedor
docker compose ps
docker compose logs -f gsfibra-backend
docker compose pull && docker compose up -d
```

## App mobile

Aponte o APK/build para:

```text
API_BASE_URL=https://painelapp.gsfibra.com:8443/v1/
```

(e o `PROVIDER_API_TOKEN` gerado no painel em Integrações).
