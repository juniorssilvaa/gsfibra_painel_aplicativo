#!/bin/bash

# Script para build da documentação MkDocs
# Este script deve ser executado no servidor para gerar a documentação

echo "🚀 Iniciando build da documentação NioChat..."

# Navegar para o diretório da documentação
cd /home/junior/niochat/docs

# Ativar ambiente virtual se existir
if [ -d "mkdocs_env" ]; then
    echo "📦 Ativando ambiente virtual..."
    source mkdocs_env/bin/activate
fi

# Instalar dependências se necessário
echo "📦 Verificando dependências..."
pip install mkdocs mkdocs-material

# Gerar documentação
echo "🔨 Gerando documentação..."
mkdocs build

# Verificar se o build foi bem-sucedido
if [ -d "site" ]; then
    echo "✅ Documentação gerada com sucesso!"
    
    # Copiar para o volume do Docker
    echo "📁 Copiando arquivos para volume Docker..."
    sudo rm -rf /var/lib/docker/volumes/niochat-docs/_data/*
    sudo cp -r site/* /var/lib/docker/volumes/niochat-docs/_data/
    
    echo "🎉 Documentação pronta para deploy!"
    echo "🌐 Acesse: https://docs.niohub.com.br"
else
    echo "❌ Erro ao gerar documentação!"
    exit 1
fi