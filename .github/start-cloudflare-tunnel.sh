#!/bin/bash
# Script Bash para iniciar o Cloudflare Tunnel
# Uso: ./start-cloudflare-tunnel.sh

echo "🔵 Iniciando Cloudflare Tunnel..."

# Verificar se cloudflared está instalado
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared não encontrado. Instale primeiro:"
    echo "   brew install cloudflare/cloudflare/cloudflared"
    exit 1
fi

# Verificar se o arquivo de configuração existe
if [ ! -f "cloudflare-tunnel.yml" ]; then
    echo "❌ Arquivo cloudflare-tunnel.yml não encontrado!"
    exit 1
fi

# Verificar se o arquivo de token existe
if [ ! -f ".cloudflare-token.json" ]; then
    echo "❌ Arquivo .cloudflare-token.json não encontrado!"
    exit 1
fi

# Verificar se backend está rodando
if ! nc -z localhost 8010 2>/dev/null; then
    echo "⚠️  Backend não está rodando na porta 8010!"
    echo "   Inicie o backend primeiro: daphne -b 0.0.0.0 -p 8010 niochat.asgi:application"
fi

# Verificar se frontend está rodando
if ! nc -z localhost 8012 2>/dev/null; then
    echo "⚠️  Frontend não está rodando na porta 8012!"
    echo "   Inicie o frontend primeiro: cd painel-provedor && pnpm dev"
fi

echo ""
echo "✅ Iniciando tunnel..."
echo "   Frontend: https://front.niochat.com.br"
echo "   Backend:  https://api.niochat.com.br"
echo ""

# Iniciar tunnel
cloudflared tunnel --config cloudflare-tunnel.yml run






