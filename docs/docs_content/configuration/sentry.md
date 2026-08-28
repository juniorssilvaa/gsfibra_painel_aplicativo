# Configuração do Sentry

O NioChat pode usar o [Sentry](https://sentry.io) para monitoramento de erros, performance e logs.

## O que o Sentry captura

- **Exceções não tratadas** – erros que quebram a aplicação
- **Performance** – transações lentas (configurável)
- **Breadcrumbs** – contexto antes do erro (requests, SQL, Redis, logs)
- **Logs** – mensagens de nível ERROR são enviadas como eventos

## Ativação

1. Crie uma conta em [sentry.io](https://sentry.io) e um projeto **Python/Django**.
2. Copie o **DSN** do projeto (Settings → Client Keys).
3. No backend, configure no `.env`:

```env
SENTRY_DSN=https://sua-chave@xxx.ingest.sentry.io/numero-do-projeto
```

4. Reinicie o backend. Se `SENTRY_DSN` estiver vazio, o Sentry não é inicializado (útil em desenvolvimento).

## Produção – Sentry com DEBUG=False

O Sentry **funciona em produção com DEBUG=False**. Não é necessário ativar DEBUG.

### Checklist produção

No servidor de produção, no `.env` do backend:

| Variável | Obrigatório | Exemplo |
|----------|-------------|---------|
| `ENVIRONMENT` | Sim | `production` |
| `DEBUG` | - | `False` |
| `SENTRY_DSN` | Sim | `https://xxx@xxx.ingest.sentry.io/xxx` |
| `SENTRY_TEST_KEY` | Recomendado | Uma chave secreta para testar o endpoint |

**Exemplo de bloco no `.env` de produção:**

```env
ENVIRONMENT=production
DEBUG=False

# Sentry – logs e erros de produção (funciona com DEBUG=False)
SENTRY_DSN=https://sua-chave@xxx.ingest.sentry.io/numero-do-projeto
SENTRY_TEST_KEY=sua_chave_secreta_para_testar
```

Reinicie o backend (Daphne/Gunicorn) após alterar o `.env`.

### Testar em produção

Com `DEBUG=False`, use a chave no endpoint:

```
GET /api/sentry-test/?key=<valor de SENTRY_TEST_KEY>
```

Exemplo: `https://api.niohub.com.br/api/sentry-test/?key=sua_chave_secreta_para_testar`

Resposta esperada: **500** (erro intencional) e o evento aparece no Sentry com **environment: production**.

### Filtrar no Sentry

- **Environment:** `production` – só eventos de produção
- **Release:** valor de `VERSION` no settings (ex.: `2.26.2`)

O mesmo DSN pode ser usado em desenvolvimento e produção; use o filtro **Environment** para separar os eventos.

## Variáveis opcionais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SENTRY_DSN` | (vazio) | DSN do projeto. Se vazio, Sentry fica desativado. |
| `ENVIRONMENT` | development | Ambiente (ex.: `production`). Enviado ao Sentry como tag. |
| `SENTRY_TRACES_SAMPLE_RATE` | 0.1 | Fração de transações enviadas para performance (0.0 a 1.0). |
| `SENTRY_PROFILES_SAMPLE_RATE` | 0.0 | Fração de profiles enviados (0.0 a 1.0). |
| `SENTRY_SEND_PII` | false | Enviar dados pessoais (ex.: user) nos eventos. |
| `SENTRY_TEST_KEY` | (vazio) | Chave para testar o endpoint `/api/sentry-test/?key=<valor>` em produção. |

## Enviar mensagens customizadas (logs/eventos)

Para registrar um evento ou “log” no Sentry manualmente:

```python
import sentry_sdk

# Mensagem informativa (aparece em Issues)
sentry_sdk.capture_message("Cliente sem contrato encontrado", level="warning")

# Capturar uma exceção manualmente
try:
    ...
except Exception as e:
    sentry_sdk.capture_exception(e)
```

## Onde ver no Sentry

- **Issues** – erros e exceções
- **Performance** – transações e tempo de resposta
- **Discover** – queries e filtros nos eventos

A configuração do SDK está em `backend/niochat/settings.py` (final do arquivo).
