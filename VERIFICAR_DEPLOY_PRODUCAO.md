# Como Verificar e Forçar Deploy na Produção

## 🔍 Problema
O servidor de produção pode não estar usando o novo código/prompt após o commit no GitHub.

## ✅ Verificações

### 1. Verificar se o GitHub Actions Executou

Acesse: https://github.com/juniorssilvaa/niochat/actions

Verifique se o workflow "Deploy NioChat to Production" foi executado após o último commit (`eb70edf`).

**Se o workflow não executou ou falhou:**
- Verifique os logs do GitHub Actions
- Verifique se os secrets estão configurados (PORTAINER_API_KEY, GHCR_TOKEN, etc.)

### 2. Verificar se as Imagens Foram Atualizadas

No servidor VPS, execute:

```bash
# Verificar imagens Docker
docker images | grep "juniorssilvaa/niochat"

# Verificar data de criação
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}" | grep "juniorssilvaa/niochat"
```

**Se as imagens são antigas:**
- O GitHub Actions pode não ter executado
- O Portainer pode não ter feito pull das novas imagens

### 3. Verificar Containers em Execução

```bash
# Ver status dos containers
docker ps | grep niochat

# Ver logs do backend (verificar se há erros)
docker logs niochat-backend --tail=100
```

## 🔄 Forçar Redeploy Manual

### Opção 1: Via Portainer (Recomendado)

1. Acesse: https://portainer.niohub.com.br
2. Vá em **Stacks** → **niochat**
3. Clique em **Editor**
4. Clique em **Update the stack**
5. Marque **Recreate containers** e **Pull latest image**
6. Clique em **Update the stack**

### Opção 2: Via Script (SSH na VPS)

Execute na VPS:

```bash
# Fazer pull das novas imagens
docker pull ghcr.io/juniorssilvaa/niochat-backend:latest
docker pull ghcr.io/juniorssilvaa/niochat-frontend:latest
docker pull ghcr.io/juniorssilvaa/niochat-dramatiq:latest

# Reiniciar containers com as novas imagens
cd /opt/niochat  # ou /var/www/niochat (depende da sua configuração)
docker-compose down
docker-compose up -d --force-recreate --pull always
```

### Opção 3: Usar o Script Fornecido

```bash
# Copiar script para VPS
scp scripts/force_redeploy.sh usuario@vps:/tmp/

# Na VPS, executar:
chmod +x /tmp/force_redeploy.sh
/tmp/force_redeploy.sh
```

## 🧪 Verificar se o Novo Prompt Está Sendo Usado

### 1. Verificar Logs do Backend

```bash
# Ver logs recentes
docker logs niochat-backend --tail=200 | grep -i "prompt\|servico_plano\|planointernet"

# Verificar se há mensagens sobre consulta de cliente
docker logs niochat-backend --tail=200 | grep -i "consultar_cliente"
```

### 2. Testar com Cliente Real

1. Faça uma pergunta sobre plano: "Qual o meu plano?"
2. A IA deve:
   - Pedir CPF/CNPJ se não tiver
   - Consultar cliente via SGP
   - Usar EXATAMENTE o valor de `servico_plano` ou `planointernet`
   - NÃO inventar valores monetários

### 3. Verificar Código no Container

```bash
# Entrar no container
docker exec -it niochat-backend bash

# Verificar se o arquivo tem as novas regras
grep -A 5 "USAR APENAS OS DADOS RETORNADOS PELA API DO SGP" /app/backend/core/openai_service.py

# Verificar commit (se disponível)
cat /app/backend/.git/HEAD 2>/dev/null || echo "Git não disponível"
```

## 🚨 Problemas Comuns

### GitHub Actions Não Executou

**Causa:** Workflow pode estar desabilitado ou com erro

**Solução:**
1. Verifique: https://github.com/juniorssilvaa/niochat/actions
2. Se não executou, force manualmente:
   - Vá em **Actions** → **Deploy NioChat to Production**
   - Clique em **Run workflow**

### Imagens Não Foram Atualizadas

**Causa:** Portainer não fez pull das novas imagens

**Solução:**
- Force o pull manualmente no Portainer ou via script

### Containers Não Reiniciaram

**Causa:** Portainer não recriou os containers

**Solução:**
- Marque **Recreate containers** ao atualizar o stack no Portainer

## 📝 Checklist de Deploy

- [ ] Commit foi feito no GitHub
- [ ] GitHub Actions executou com sucesso
- [ ] Imagens foram buildadas e enviadas para GHCR
- [ ] Portainer recebeu a atualização
- [ ] Containers foram recriados
- [ ] Logs mostram que o novo código está rodando
- [ ] Teste manual confirma que o novo prompt está funcionando

## 🔗 Links Úteis

- GitHub Actions: https://github.com/juniorssilvaa/niochat/actions
- Portainer: https://portainer.niohub.com.br
- GitHub Container Registry: https://github.com/juniorssilvaa/niochat/pkgs/container/niochat

