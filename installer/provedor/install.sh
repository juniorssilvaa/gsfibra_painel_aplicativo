#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

header() {
  clear
  echo -e "${BLUE}====================================================${NC}"
  echo -e "${BLUE}     INSTALADOR PAINEL DO APLICATIVO GS FIBRA       ${NC}"
  echo -e "${BLUE}====================================================${NC}"
  echo
}

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
error() { echo -e "${RED}[ERRO]${NC} $1"; }

prompt() {
  local label="$1"
  local var="$2"
  local default="${3:-}"
  local secret="${4:-0}"
  local value

  while true; do
    if [[ "$secret" == "1" ]]; then
      read -r -s -p "$(echo -e "${YELLOW}${label}${NC} ${default:+($default)}: ")" value
      echo
    else
      read -r -p "$(echo -e "${YELLOW}${label}${NC} ${default:+($default)}: ")" value
    fi
    value="${value:-$default}"
    if [[ -n "${value}" ]]; then
      printf -v "$var" "%s" "$value"
      return 0
    fi
    error "Este campo é obrigatório."
  done
}

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return 0
  fi
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
}

if [[ "${EUID:-0}" -ne 0 ]]; then
  error "Execute como root (sudo ./install.sh)."
  exit 1
fi

header

info "Atualizando repositórios..."
apt-get update -y >/dev/null
for pkg in curl openssl ca-certificates; do
  if ! command -v "$pkg" >/dev/null 2>&1; then
    warn "Instalando $pkg..."
    apt-get install -y "$pkg" >/dev/null
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  warn "Docker não encontrado. Instalando..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

if ! docker compose version >/dev/null 2>&1; then
  warn "Docker Compose não encontrado. Instalando..."
  apt-get install -y docker-compose-v2 >/dev/null
fi

PUBLIC_IP=$(curl -s https://ifconfig.me || curl -s https://icanhazip.com || echo "SEU_IP")

while true; do
  header
  echo -e "${BLUE}--- Domínio e porta (convive com GenieACS) ---${NC}"
  echo -e "ACS já usa ${YELLOW}80/443/7547/7557/7567/8000${NC}."
  echo -e "Este painel sobe em outra porta no mesmo domínio."
  echo
  prompt "Domínio do painel (mesmo do ACS)" PANEL_DOMAIN "painelapp.gsfibra.com"
  prompt "Porta HTTPS do painel do app" PANEL_PORT "8443"
  PANEL_PUBLIC_URL="https://${PANEL_DOMAIN}:${PANEL_PORT}"
  prompt "E-mail para SSL / avisos" LETSENCRYPT_EMAIL

  echo
  echo -e "${BLUE}--- TLS ---${NC}"
  echo "  acs      = reutiliza o certificado Let's Encrypt do Caddy do ACS (recomendado)"
  echo "  internal = certificado local (browser mostra 'Não seguro')"
  echo "  acme     = Let's Encrypt direto (em porta != 443 costuma falhar)"
  prompt "Modo TLS (acs/internal/acme)" TLS_MODE "acs"

  echo
  echo -e "${BLUE}--- Imagens (GHCR) ---${NC}"
  prompt "Registry" IMAGE_REGISTRY "ghcr.io/juniorssilvaa"
  prompt "Tag das imagens" IMAGE_TAG "latest"
  # Imagens esperadas: ${IMAGE_REGISTRY}/gsfibra_painel_aplicativo(+-backend):${IMAGE_TAG}
  read -r -p "$(echo -e "${YELLOW}Imagens privadas? (S/N)${NC} [S]: ")" GHCR_PRIVATE
  GHCR_PRIVATE="$(echo "${GHCR_PRIVATE:-S}" | tr '[:lower:]' '[:upper:]')"
  if [[ "$GHCR_PRIVATE" == "S" ]]; then
    prompt "Usuário GitHub" GHCR_USER "juniorssilvaa"
    prompt "Token PAT (read:packages)" GHCR_TOKEN "" 1
  else
    GHCR_USER=""
    GHCR_TOKEN=""
  fi

  echo
  echo -e "${BLUE}--- Admin do painel ---${NC}"
  prompt "Nome do provedor" PANEL_PROVEDOR_NOME "GSFibra"
  prompt "Usuário admin" PANEL_ADMIN_USER "admin"
  prompt "Senha admin" PANEL_ADMIN_PASS "" 1

  if [[ "$IMAGE_REGISTRY" == *":"* ]]; then
    IMAGE_TAG="${IMAGE_REGISTRY##*:}"
    IMAGE_REGISTRY="${IMAGE_REGISTRY%:*}"
  fi

  header
  echo -e "${BLUE}--- Resumo ---${NC}"
  echo -e "URL:        ${GREEN}${PANEL_PUBLIC_URL}${NC}"
  echo -e "IP público: ${GREEN}${PUBLIC_IP}${NC}"
  echo -e "TLS:        ${GREEN}${TLS_MODE}${NC}"
  echo -e "Registry:   ${GREEN}${IMAGE_REGISTRY}${NC}"
  echo -e "Tag:        ${GREEN}${IMAGE_TAG}${NC}"
  echo -e "Provedor:   ${GREEN}${PANEL_PROVEDOR_NOME}${NC}"
  echo -e "Admin:      ${GREEN}${PANEL_ADMIN_USER}${NC}"
  echo
  warn "Abra a porta ${PANEL_PORT}/TCP no firewall/Cloudflare."
  warn "Não use 80/443/8000 — são do ACS."
  echo
  read -r -p "$(echo -e "${YELLOW}Confirma? (S/C)${NC} [S]: ")" confirm
  confirm="$(echo "${confirm:-S}" | tr '[:lower:]' '[:upper:]')"
  [[ "$confirm" == "S" ]] && break
done

info "Gerando .env..."
SECRET_KEY="$(rand_hex)"
POSTGRES_PASSWORD="$(rand_hex | head -c 24)"
REDIS_PASSWORD="$(rand_hex | head -c 24)"
RABBITMQ_PASSWORD="$(rand_hex | head -c 24)"
COMPOSE_PROJECT_NAME="gsfibra_painel"
HOST_INSTALLER_DIR="$(pwd)"

cat > .env <<EOF
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}
HOST_INSTALLER_DIR=${HOST_INSTALLER_DIR}
PANEL_DOMAIN=${PANEL_DOMAIN}
PANEL_PORT=${PANEL_PORT}
PANEL_PUBLIC_URL=${PANEL_PUBLIC_URL}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
TLS_MODE=${TLS_MODE}
IMAGE_REGISTRY=${IMAGE_REGISTRY}
IMAGE_TAG=${IMAGE_TAG}
POSTGRES_DB=gsfibra
POSTGRES_USER=gsfibra
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
RABBITMQ_USER=gsfibra
RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD}
SECRET_KEY=${SECRET_KEY}
DEBUG=False
ALLOWED_HOSTS=${PANEL_DOMAIN},localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=${PANEL_PUBLIC_URL}
CSRF_TRUSTED_ORIGINS=${PANEL_PUBLIC_URL}
BACKEND_URL=${PANEL_PUBLIC_URL}
FRONTEND_URL=${PANEL_PUBLIC_URL}
MOBILE_API_PUBLIC_BASE=${PANEL_PUBLIC_URL}/v1
PANEL_ADMIN_USER=${PANEL_ADMIN_USER}
PANEL_ADMIN_PASS=${PANEL_ADMIN_PASS}
PANEL_PROVEDOR_NOME=${PANEL_PROVEDOR_NOME}
GITHUB_USER=${GHCR_USER}
GITHUB_TOKEN=${GHCR_TOKEN}
EOF

info "Gerando Caddyfile (porta ${PANEL_PORT})..."
mkdir -p certs
TLS_BLOCK="tls internal"
if [[ "${TLS_MODE}" == "acs" ]]; then
  info "Procurando certificado do ACS (volume installer_caddy_data)..."
  if docker volume inspect installer_caddy_data >/dev/null 2>&1; then
    docker run --rm \
      -v installer_caddy_data:/acs:ro \
      -v "$(pwd)/certs:/out" \
      alpine:3.20 sh -c "
        set -e
        crt=\$(find /acs -type f -name '${PANEL_DOMAIN}.crt' | head -n1)
        key=\$(find /acs -type f -name '${PANEL_DOMAIN}.key' | head -n1)
        if [ -z \"\$crt\" ] || [ -z \"\$key\" ]; then
          echo 'CERT_NOT_FOUND'
          exit 2
        fi
        cp \"\$crt\" /out/fullchain.pem
        cp \"\$key\" /out/privkey.pem
        echo \"OK \$crt\"
      " && TLS_BLOCK="tls /certs/fullchain.pem /certs/privkey.pem" \
        && info "Certificado ACS copiado para ./certs" \
        || { warn "Certificado ACS não encontrado; usando tls internal."; TLS_MODE=internal; }
  else
    warn "Volume installer_caddy_data não existe; usando tls internal."
    TLS_MODE=internal
  fi
fi

PROXY_HANDLES=$(cat <<'HANDLES'
    encode gzip

    handle /api* {
        reverse_proxy gsfibra-backend:8010
    }
    handle /v1* {
        reverse_proxy gsfibra-backend:8010
    }
    handle /ws* {
        reverse_proxy gsfibra-backend:8010
    }
    handle /media* {
        reverse_proxy gsfibra-backend:8010
    }
    handle {
        reverse_proxy gsfibra-frontend:80
    }
HANDLES
)

if [[ "${TLS_MODE}" == "acme" ]]; then
  cat > Caddyfile <<EOF
{
    https_port ${PANEL_PORT}
    http_port 8088
    email ${LETSENCRYPT_EMAIL}
}

https://${PANEL_DOMAIN}:${PANEL_PORT} {
${PROXY_HANDLES}
}
EOF
else
  cat > Caddyfile <<EOF
{
    https_port ${PANEL_PORT}
    auto_https disable_redirects
}

https://${PANEL_DOMAIN}:${PANEL_PORT} {
    ${TLS_BLOCK}
${PROXY_HANDLES}
}
EOF
fi

# Evita Docker criar diretório no lugar do arquivo de credenciais
if [[ ! -f firebase-credentials.json ]]; then
  warn "firebase-credentials.json ausente — criando placeholder (push FCM desativado até configurar)."
  echo '{}' > firebase-credentials.json
fi

if [[ ! -f docker-compose.yml ]]; then
  info "Baixando docker-compose.yml..."
  if [[ -n "${GHCR_TOKEN}" ]]; then
    curl -H "Authorization: token ${GHCR_TOKEN}" -fsSL \
      "https://raw.githubusercontent.com/juniorssilvaa/gsfibra_painel_aplicativo/main/installer/provedor/docker-compose.yml" \
      -o docker-compose.yml || true
  fi
  if [[ ! -f docker-compose.yml ]] || [[ $(stat -c%s docker-compose.yml 2>/dev/null || echo 0) -lt 100 ]]; then
    error "docker-compose.yml não encontrado. Coloque o arquivo neste diretório e rode de novo."
    exit 1
  fi
fi

if [[ "${GHCR_PRIVATE}" == "S" ]]; then
  info "Login no GHCR..."
  if ! echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin; then
    error "Falha no login GHCR. Token precisa de read:packages."
    exit 1
  fi
fi

info "Pull das imagens..."
docker compose pull

info "Subindo stack..."
docker compose up -d

info "Aguardando backend (migrações + Daphne :8010)..."
backend_ready=0
for i in $(seq 1 90); do
  if docker compose exec -T gsfibra-backend python -c \
    "import socket; s=socket.create_connection(('127.0.0.1', 8010), 2); s.close()" \
    >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  if ! docker compose ps --status running gsfibra-backend 2>/dev/null | grep -q gsfibra-backend; then
    warn "Backend não está rodando. Logs:"
    docker compose logs --tail=80 gsfibra-backend || true
    error "Falha ao subir o backend."
    exit 1
  fi
  sleep 2
done
if [[ "$backend_ready" != "1" ]]; then
  docker compose logs --tail=80 gsfibra-backend || true
  error "Timeout aguardando o backend."
  exit 1
fi
info "Backend pronto."

info "Criando provedor + usuário admin..."
docker compose exec -T gsfibra-backend python - <<'PY'
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat_sa.settings')
django.setup()

from django.contrib.auth import get_user_model
from super_core.models import Provedor

try:
    from mobile_app.services import ensure_mobile_app_for_provedor
except Exception:
    ensure_mobile_app_for_provedor = None

User = get_user_model()
nome = (os.environ.get('PANEL_PROVEDOR_NOME') or 'GSFibra').strip()
username = (os.environ.get('PANEL_ADMIN_USER') or 'admin').strip()
password = os.environ.get('PANEL_ADMIN_PASS') or ''

provedor = Provedor.objects.filter(nome__iexact=nome).first()
if not provedor:
    provedor = Provedor.objects.create(
        nome=nome,
        company=nome,
        is_active=True,
        status='ativo',
        subdomain='gsfibra',
    )
else:
    provedor.is_active = True
    provedor.status = 'ativo'
    provedor.save(update_fields=['is_active', 'status'])

if ensure_mobile_app_for_provedor:
    try:
        profile, _, _ = ensure_mobile_app_for_provedor(provedor, create_token=True)
        # Campo "Nome do App no ERP" começa vazio (não pré-preenche gsfibra)
        if getattr(profile, 'sgp_app_name', None):
            profile.sgp_app_name = None
            profile.save(update_fields=['sgp_app_name'])
    except Exception as exc:
        print(f'aviso mobile_app: {exc}')

if username and password:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            'is_staff': True,
            'is_superuser': False,
            'user_type': 'admin',
            'provedor': provedor,
        },
    )
    user.is_staff = True
    user.user_type = 'admin'
    user.provedor = provedor
    user.is_active = True
    user.set_password(password)
    user.save()
    print(f'admin ok: {username} provedor_id={provedor.id}')
else:
    print('admin não criado (usuário/senha vazios)')
PY

header
echo -e "${GREEN}INSTALAÇÃO CONCLUÍDA${NC}"
echo
echo -e "Painel:     ${BLUE}${PANEL_PUBLIC_URL}${NC}"
echo -e "Usuário:    ${YELLOW}${PANEL_ADMIN_USER}${NC}"
echo -e "Senha:      ${YELLOW}${PANEL_ADMIN_PASS}${NC}"
echo
echo -e "${YELLOW}Lembretes:${NC}"
echo -e " - Libere ${PANEL_PORT}/TCP no firewall"
echo -e " - ACS continua em https://${PANEL_DOMAIN} (443)"
echo -e " - App mobile: API_BASE_URL=${PANEL_PUBLIC_URL}/v1/"
echo -e " - Coloque firebase-credentials.json neste diretório e rode: docker compose up -d gsfibra-backend"
echo
