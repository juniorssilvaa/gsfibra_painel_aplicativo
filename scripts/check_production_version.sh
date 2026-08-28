#!/bin/bash
# Script para verificar qual versão do código está rodando na produção

echo "🔍 Verificando versão do código em produção..."

# Verificar commit atual no GitHub
echo "📌 Último commit no GitHub:"
git log -1 --oneline 2>/dev/null || echo "Git não disponível localmente"

# Verificar imagens Docker
echo ""
echo "🐳 Imagens Docker em uso:"
docker images | grep "juniorssilvaa/niochat" | head -5

# Verificar containers rodando
echo ""
echo "📦 Containers em execução:"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep niochat

# Verificar data de criação das imagens
echo ""
echo "📅 Data de criação das imagens:"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}" | grep "juniorssilvaa/niochat"

# Verificar se há atualizações disponíveis
echo ""
echo "🔄 Verificando atualizações disponíveis no registry..."
docker pull ghcr.io/juniorssilvaa/niochat-backend:latest --quiet 2>&1 | grep -i "up to date\|downloaded" || echo "Erro ao verificar atualizações"

# Verificar hash do commit no código (se disponível)
echo ""
echo "🔍 Verificando se há informação de commit no código..."
docker exec niochat-backend cat /app/backend/.git/HEAD 2>/dev/null || echo "Informação de commit não disponível no container"

echo ""
echo "✅ Verificação concluída!"

