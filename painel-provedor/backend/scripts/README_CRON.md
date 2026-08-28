# Configuração Cron + Dramatiq - Finalização de Conversas

## 📋 Passo a Passo

### 1. Tornar o script executável

```bash
chmod +x backend/scripts/finalize_closing_cron.py
```

### 2. Obter o caminho absoluto do script

```bash
# No Linux/Mac
realpath backend/scripts/finalize_closing_cron.py

# Ou use pwd
cd backend/scripts && pwd
```

### 3. Configurar o Cron

```bash
# Editar crontab
crontab -e
```

### 4. Adicionar linha no crontab

**Substitua `/caminho/absoluto/para` pelo caminho real do seu projeto:**

```cron
# Executar a cada 2 minutos - Finalizar conversas em 'closing'
*/2 * * * * /caminho/absoluto/para/niochat/backend/scripts/finalize_closing_cron.py >> /var/log/niochat/finalize_closing.log 2>&1
```

**Exemplo real:**
```cron
*/2 * * * * /home/usuario/niochat/backend/scripts/finalize_closing_cron.py >> /var/log/niochat/finalize_closing.log 2>&1
```

### 5. Criar diretório de logs (se não existir)

```bash
sudo mkdir -p /var/log/niochat
sudo chown $USER:$USER /var/log/niochat
```

### 6. Verificar se está funcionando

```bash
# Ver logs em tempo real
tail -f /var/log/niochat/finalize_closing.log

# Verificar se o cron está executando
grep CRON /var/log/syslog | grep finalize_closing

# Testar manualmente
python backend/scripts/finalize_closing_cron.py
```

## 🔍 Como Funciona

1. **Cron executa** o script Python a cada 2 minutos
2. **Script configura** o broker Dramatiq
3. **Task é enviada** para a fila Dramatiq (assíncrono)
4. **Worker Dramatiq** processa a task
5. **Conversas em 'closing'** são finalizadas e migradas

## ⚠️ Requisitos

- Worker Dramatiq deve estar rodando
- RabbitMQ deve estar acessível
- Variáveis de ambiente configuradas (DRAMATIQ_BROKER_URL, etc.)

## 🚨 Troubleshooting

### Script não executa:
```bash
# Verificar permissões
ls -la backend/scripts/finalize_closing_cron.py

# Testar manualmente
python backend/scripts/finalize_closing_cron.py
```

### Task não é processada:
- Verifique se o worker Dramatiq está rodando
- Verifique conexão com RabbitMQ
- Veja logs do worker Dramatiq

### Ver logs do cron:
```bash
# Ubuntu/Debian
grep CRON /var/log/syslog

# CentOS/RHEL
grep CRON /var/log/cron
```

