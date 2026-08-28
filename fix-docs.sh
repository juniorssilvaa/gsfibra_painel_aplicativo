#!/bin/bash

echo "🔧 Corrigindo documentação NioChat..."

# 1. Gerar documentação
echo "📚 Gerando documentação MkDocs..."
cd /home/junior/niochat/docs
source mkdocs_env/bin/activate
mkdocs build

# 2. Verificar se o volume existe
echo "📁 Verificando volume Docker..."
if ! sudo docker volume ls | grep -q niochat-docs; then
    echo "📦 Criando volume niochat-docs..."
    sudo docker volume create niochat-docs
fi

# 3. Copiar arquivos para o volume
echo "📋 Copiando arquivos para o volume..."
sudo rm -rf /var/lib/docker/volumes/niochat-docs/_data/*
sudo cp -r /home/junior/niochat/docs/site/* /var/lib/docker/volumes/niochat-docs/_data/

# 4. Reiniciar container
echo "🔄 Reiniciando container de documentação..."
sudo docker restart niochat-docs

echo "✅ Documentação corrigida! Acesse: https://docs.niohub.com.br"
