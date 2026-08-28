#!/bin/bash
# Script para forçar redeploy na produção
# Este script força o pull das novas imagens e reinicia os containers

echo "🔄 Forçando redeploy do NioChat na produção..."

# Verificar se está na VPS
if [ ! -f "/opt/niochat/docker-compose.yml" ] && [ ! -f "/var/www/niochat/docker-compose.yml" ]; then
    echo "❌ Este script deve ser executado na VPS"
    exit 1
fi

# Determinar diretório do projeto
if [ -f "/opt/niochat/docker-compose.yml" ]; then
    PROJECT_DIR="/opt/niochat"
elif [ -f "/var/www/niochat/docker-compose.yml" ]; then
    PROJECT_DIR="/var/www/niochat"
else
    PROJECT_DIR="."
fi

cd "$PROJECT_DIR"

echo "📦 Fazendo pull das novas imagens do GitHub Container Registry..."
docker pull ghcr.io/juniorssilvaa/niochat-backend:latest
docker pull ghcr.io/juniorssilvaa/niochat-frontend:latest
docker pull ghcr.io/juniorssilvaa/niochat-dramatiq:latest

echo "🔄 Reiniciando containers com as novas imagens..."
docker-compose down
docker-compose up -d --force-recreate --pull always

echo "⏳ Aguardando containers iniciarem..."
sleep 10

echo "✅ Verificando status dos containers..."
docker-compose ps

echo "📋 Últimas linhas dos logs do backend (para verificar se está usando o novo código)..."
docker-compose logs --tail=50 niochat-backend | grep -i "prompt\|openai\|ia" || echo "Nenhum log relevante encontrado"

echo ""
echo "✅ Redeploy concluído!"
echo "🔍 Para verificar se o novo prompt está sendo usado, verifique os logs:"
echo "   docker-compose logs -f niochat-backend"

