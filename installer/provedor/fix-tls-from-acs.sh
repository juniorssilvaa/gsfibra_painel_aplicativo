#!/usr/bin/env bash
# Reutiliza o certificado Let's Encrypt do Caddy do ACS e reinicia o Caddy do painel.
set -euo pipefail

DOMAIN="${1:-painelapp.gsfibra.com}"
PORT="${2:-8443}"

if [[ ! -f docker-compose.yml ]]; then
  echo "Rode este script dentro do diretório installer/provedor"
  exit 1
fi

mkdir -p certs
if ! docker volume inspect installer_caddy_data >/dev/null 2>&1; then
  echo "Volume installer_caddy_data não encontrado. O ACS precisa estar instalado neste host."
  exit 1
fi

echo "Copiando certificado de ${DOMAIN} do ACS..."
docker run --rm \
  -v installer_caddy_data:/acs:ro \
  -v "$(pwd)/certs:/out" \
  alpine:3.20 sh -c "
    set -e
    crt=\$(find /acs -type f -name '${DOMAIN}.crt' | head -n1)
    key=\$(find /acs -type f -name '${DOMAIN}.key' | head -n1)
    if [ -z \"\$crt\" ] || [ -z \"\$key\" ]; then
      echo 'Certificado não encontrado no volume do ACS.'
      find /acs -type f \\( -name '*.crt' -o -name '*.key' \\) | head -n 40
      exit 2
    fi
    cp \"\$crt\" /out/fullchain.pem
    cp \"\$key\" /out/privkey.pem
    echo \"OK: \$crt\"
  "

cat > Caddyfile <<EOF
{
    https_port ${PORT}
    auto_https disable_redirects
}

https://${DOMAIN}:${PORT} {
    tls /certs/fullchain.pem /certs/privkey.pem
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
}
EOF

# Garante mount de ./certs no compose (versões antigas podem não ter)
if ! grep -q './certs:/certs' docker-compose.yml && ! grep -q 'certs:/certs' docker-compose.yml; then
  echo "Atualize o docker-compose.yml (mount ./certs) ou rode o instalador de novo."
fi

docker compose up -d caddy
echo "Pronto. Teste: https://${DOMAIN}:${PORT}"
