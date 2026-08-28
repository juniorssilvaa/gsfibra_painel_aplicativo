#!/bin/bash
# Espera PostgreSQL antes de migrations / Daphne / workers.
# - Parsing de DATABASE_URL em Python (passwords com @, :, etc.)
# - pg_isready quando POSTGRES_USER + POSTGRES_DB (ou extraídos do URL)
# - Timeout configurável (evita loop infinito)
# - POSTGRES_WAIT_SKIP=1 para RDS externo ou diagnóstico
set +e

SKIP="${POSTGRES_WAIT_SKIP:-}"
if [[ "$SKIP" == "1" || "$SKIP" == "true" || "$SKIP" == "yes" ]]; then
  echo "⏭ POSTGRES_WAIT_SKIP ativo — a saltar espera pelo PostgreSQL."
  exit 0
fi

MAX="${POSTGRES_WAIT_MAX_SECONDS:-300}"
STEP="${POSTGRES_WAIT_SLEEP_SECONDS:-2}"

TMP="$(mktemp)"
python3 << 'PY' > "$TMP"
import os
import urllib.parse as u

def swarm_host(service: str, configured: str) -> str:
    configured = (configured or "").strip()
    if configured and configured not in ("postgres", "redis"):
        return configured
    stack = (
        os.environ.get("DOCKER_STACK_NAME")
        or os.environ.get("TRAEFIK_ROUTER_PREFIX")
        or ""
    ).strip()
    if stack:
        return f"{stack}_{service}"
    return configured or service

url = (os.environ.get("DATABASE_URL") or "").strip()
host = (os.environ.get("POSTGRES_HOST") or "").strip()
port = (os.environ.get("POSTGRES_PORT") or "").strip() or "5432"
user = (os.environ.get("POSTGRES_USER") or "").strip()
db = (os.environ.get("POSTGRES_DB") or "").strip()

if not host and url:
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    p = u.urlparse(url)
    host = p.hostname or "postgres"
    if p.port:
        port = str(p.port)
    if not user and p.username:
        user = u.unquote(p.username)
    if not db and p.path and p.path != "/":
        db = u.unquote(p.path.lstrip("/"))
elif not host:
    host = "postgres"

host = swarm_host("postgres", host)

print(host)
print(port)
print(user)
print(db)
PY

WAIT_DB_HOST="$(sed -n '1p' "$TMP")"
WAIT_DB_PORT="$(sed -n '2p' "$TMP")"
WAIT_DB_USER="$(sed -n '3p' "$TMP")"
WAIT_DB_NAME="$(sed -n '4p' "$TMP")"
rm -f "$TMP"

echo "⏳ À espera de PostgreSQL em ${WAIT_DB_HOST}:${WAIT_DB_PORT} (máx. ${MAX}s)..."
echo "   Ajuste: POSTGRES_WAIT_MAX_SECONDS | POSTGRES_WAIT_SLEEP_SECONDS | POSTGRES_WAIT_SKIP=1"

try_connect() {
  if [[ -n "$WAIT_DB_USER" && -n "$WAIT_DB_NAME" ]]; then
    pg_isready -h "$WAIT_DB_HOST" -p "$WAIT_DB_PORT" -U "$WAIT_DB_USER" -d "$WAIT_DB_NAME" -t 4 >/dev/null 2>&1
    return $?
  fi
  nc -z -w4 "$WAIT_DB_HOST" "$WAIT_DB_PORT" >/dev/null 2>&1
  return $?
}

elapsed=0
first=1
while [[ "$elapsed" -lt "$MAX" ]]; do
  if try_connect; then
    echo "✅ PostgreSQL disponível (${WAIT_DB_HOST}:${WAIT_DB_PORT}) após ${elapsed}s."
    exit 0
  fi
  if [[ "$first" -eq 1 ]]; then
    echo "⏳ Primeira tentativa falhou para ${WAIT_DB_HOST}:${WAIT_DB_PORT} — a repetir (máx. ${MAX}s)..."
    first=0
  elif [[ $((elapsed % 20)) -eq 0 ]]; then
    echo "⏳ Ainda sem ligação (${elapsed}s / ${MAX}s) — ${WAIT_DB_HOST}:${WAIT_DB_PORT}"
    if command -v getent >/dev/null 2>&1; then
      gh="$(getent hosts "$WAIT_DB_HOST" 2>/dev/null | head -n1)"
      if [[ -n "$gh" ]]; then
        echo "   DNS: $gh"
      else
        echo "   DNS: sem resolução para «${WAIT_DB_HOST}» (serviço fora da rede / nome errado na stack Swarm)."
      fi
    fi
    if [[ -n "$WAIT_DB_USER" && -n "$WAIT_DB_NAME" ]]; then
      echo "   Teste: pg_isready -h $WAIT_DB_HOST -p $WAIT_DB_PORT -U $WAIT_DB_USER -d $WAIT_DB_NAME"
    else
      echo "   Defina POSTGRES_USER e POSTGRES_DB no ambiente para usar pg_isready em vez de nc."
    fi
  fi
  sleep "$STEP"
  elapsed=$((elapsed + STEP))
done

echo ""
echo "❌ Timeout (${MAX}s): não foi possível ligar a PostgreSQL em ${WAIT_DB_HOST}:${WAIT_DB_PORT}."
echo "   Em Docker Swarm, o host costuma ser «{nome_da_stack}_postgres» (ex.: niohub-foo_postgres), não só «postgres»."
echo "   Confirme no Portainer: serviço postgres 1/1 na stack + POSTGRES_HOST / DATABASE_URL com o mesmo hostname."
echo "   Host alternativo: defina POSTGRES_HOST (e alinhe o host em DATABASE_URL)."
exit 1
