#!/bin/bash
# Espera Redis antes de arrancar o backend / workers.
# Parsing seguro de REDIS_URL via Python (passwords com @ ou :).
# REDIS_WAIT_SKIP=1 para saltar (ex.: Redis externo gerido).
set +e

SKIP="${REDIS_WAIT_SKIP:-}"
if [[ "$SKIP" == "1" || "$SKIP" == "true" || "$SKIP" == "yes" ]]; then
  echo "⏭ REDIS_WAIT_SKIP ativo — a saltar espera pelo Redis."
  exit 0
fi

MAX="${REDIS_WAIT_MAX_SECONDS:-120}"
STEP="${REDIS_WAIT_SLEEP_SECONDS:-2}"

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

url = (os.environ.get("REDIS_URL") or "").strip()
host = (os.environ.get("REDIS_HOST") or "").strip()
port = (os.environ.get("REDIS_PORT") or "").strip() or "6379"

if not host and url:
    p = u.urlparse(url)
    host = p.hostname or "redis"
    if p.port:
        port = str(p.port)
elif not host:
    host = "redis"

host = swarm_host("redis", host)

stack = (
    os.environ.get("DOCKER_STACK_NAME")
    or os.environ.get("TRAEFIK_ROUTER_PREFIX")
    or ""
).strip()
candidates = []
for h in (host, "redis", f"{stack}_redis" if stack else ""):
    h = (h or "").strip()
    if h and h not in candidates:
        candidates.append(h)

print("|".join(candidates))
print(port)
PY

mapfile -t REDIS_HOSTS < <(sed -n '1p' "$TMP" | tr '|' '\n')
WAIT_REDIS_PORT="$(sed -n '2p' "$TMP")"
rm -f "$TMP"

WAIT_REDIS_HOST="${REDIS_HOSTS[0]}"
HOSTS_LABEL="$(IFS=, ; echo "${REDIS_HOSTS[*]}")"
echo "⏳ À espera de Redis em ${HOSTS_LABEL}:${WAIT_REDIS_PORT} (máx. ${MAX}s)..."

try_connect() {
  local h
  for h in "${REDIS_HOSTS[@]}"; do
    [[ -z "$h" ]] && continue
    if nc -z -w4 "$h" "$WAIT_REDIS_PORT" >/dev/null 2>&1; then
      WAIT_REDIS_HOST="$h"
      return 0
    fi
  done
  return 1
}

elapsed=0
first=1
while [[ "$elapsed" -lt "$MAX" ]]; do
  if try_connect; then
    echo "✅ Redis disponível (${WAIT_REDIS_HOST}:${WAIT_REDIS_PORT}) após ${elapsed}s."
    exit 0
  fi
  if [[ "$first" -eq 1 ]]; then
    echo "⏳ Primeira tentativa falhou — a repetir (máx. ${MAX}s)..."
    first=0
  elif [[ $((elapsed % 20)) -eq 0 ]]; then
    echo "⏳ Ainda sem Redis (${elapsed}s / ${MAX}s) — ${HOSTS_LABEL}:${WAIT_REDIS_PORT}"
    if command -v getent >/dev/null 2>&1; then
      resolved=0
      for h in "${REDIS_HOSTS[@]}"; do
        [[ -z "$h" ]] && continue
        gh="$(getent hosts "$h" 2>/dev/null | head -n1)"
        if [[ -n "$gh" ]]; then
          echo "   DNS ($h): $gh"
          resolved=1
        fi
      done
      if [[ "$resolved" -eq 0 ]]; then
        echo "   DNS: nenhum host resolve (serviço redis provavelmente 0/1 — veja logs do redis)."
      fi
    fi
  fi
  sleep "$STEP"
  elapsed=$((elapsed + STEP))
done

echo ""
echo "❌ Timeout (${MAX}s): não foi possível ligar a Redis em ${WAIT_REDIS_HOST}:${WAIT_REDIS_PORT}."
echo "   Em Docker Swarm, o host costuma ser «{nome_da_stack}_redis» (ex.: niohub-foo_redis), não só «redis»."
echo "   Verifique: REDIS_HOST, REDIS_URL, serviço redis 1/1 na stack."
exit 1
