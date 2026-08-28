#!/bin/bash
set -e

echo "Starting NioChat Backend..."

if [[ -x /app/wait-for-postgres.sh ]]; then
  /app/wait-for-postgres.sh
else
  echo "⚠️ /app/wait-for-postgres.sh em falta — a continuar sem espera explícita pelo PostgreSQL."
fi

if [[ -x /app/wait-for-redis.sh ]]; then
  /app/wait-for-redis.sh
else
  echo "⚠️ /app/wait-for-redis.sh em falta — a continuar sem espera explícita pelo Redis."
fi

echo "Running migrations..."
# Sincronização inteligente do histórico de migrações com a realidade física do banco
# IMPORTANTE: Usa psycopg2 puro para NÃO disparar django.setup() e os ready() dos apps
python -c "
import os

db_url = os.environ.get('DATABASE_URL', '')
if not db_url:
    print('[MIGRATE-FIX] DATABASE_URL nao definida. Pulando sincronizacao.')
    exit(0)

import psycopg2

try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Verificar se django_migrations existe (banco novo = nao existe)
    cur.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'django_migrations')\")
    has_migrations_table = cur.fetchone()[0]

    if not has_migrations_table:
        print('[MIGRATE-FIX] django_migrations nao existe (banco novo). Pulando sincronizacao pre-migrate.')
        cur.close()
        conn.close()
        exit(0)

    def column_exists(table, column):
        cur.execute('SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = %s AND column_name = %s)', (table, column))
        return cur.fetchone()[0]

    def table_exists(table):
        cur.execute('SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)', (table,))
        return cur.fetchone()[0]

    checks = [
        ('0058_add_openai_transcription_api_key', column_exists('core_systemconfig', 'openai_transcription_api_key')),
        ('0061_canal_ia_ativa', column_exists('core_canal', 'ia_ativa')),
        ('0062_chatbotflow', table_exists('core_chatbotflow')),
        ('0063_add_bot_mode_to_provedor', column_exists('core_provedor', 'bot_mode')),
        ('0067_add_canal_to_chatbotflow', column_exists('core_chatbotflow', 'canal_id')),
        ('0070_add_asaas_fields', column_exists('core_systemconfig', 'asaas_access_token')),
        ('0071_provedor_asaas_details', column_exists('core_provedor', 'asaas_customer_id')),
        ('0072_provedor_subscription_fields', column_exists('core_provedor', 'asaas_subscription_id')),
        ('0073_provedor_subscription_next_due_date', column_exists('core_provedor', 'subscription_next_due_date')),
    ]

    for name in ['0055_1_alter_provedor_redes_sociais_default', '0055_add_more']:
        cur.execute(
            'INSERT INTO django_migrations (app, name, applied) SELECT %s, %s, NOW() WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app=%s AND name=%s)',
            ('core', name, 'core', name)
        )

    for name, exists in checks:
        if exists:
            cur.execute(
                'INSERT INTO django_migrations (app, name, applied) SELECT %s, %s, NOW() WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app=%s AND name=%s)',
                ('core', name, 'core', name)
            )
            print(f'[MIGRATE-FIX] {name} garantida no historico (existe fisicamente).')
        else:
            cur.execute('DELETE FROM django_migrations WHERE app=%s AND name=%s', ('core', name))
            print(f'[MIGRATE-FIX] {name} removida do historico (NAO existe fisicamente).')

    cur.close()
    conn.close()
    print('[MIGRATE-FIX] Sincronizacao concluida com sucesso.')
except Exception as e:
    print(f'[MIGRATE-FIX] Erro (nao-fatal): {e}')
    print('[MIGRATE-FIX] Continuando com migrate normal...')
"

python manage.py migrate --noinput

# Cria/atualiza o primeiro admin no DB do provedor (mais fiável que AppConfig.ready durante migrate)
if [[ -n "${INITIAL_ADMIN_USERNAME:-}" && -n "${INITIAL_ADMIN_PASSWORD:-}" ]]; then
  echo "Ensuring initial provider admin (${INITIAL_ADMIN_USERNAME})..."
  set +e
  ev_cmd=(python manage.py ensure_provider_admin --username "$INITIAL_ADMIN_USERNAME" --password "$INITIAL_ADMIN_PASSWORD")
  if [[ -n "${INITIAL_ADMIN_EMAIL:-}" ]]; then
    ev_cmd+=(--email "$INITIAL_ADMIN_EMAIL")
  fi
  if [[ -n "${SUPERADMIN_PROVEDOR_ID:-}" ]]; then
    ev_cmd+=(--provedor-id "$SUPERADMIN_PROVEDOR_ID")
  fi
  "${ev_cmd[@]}"
  ev_rc=$?
  set -e
  if [[ $ev_rc -ne 0 ]]; then
    echo "⚠️ ensure_provider_admin falhou (rc=$ev_rc) — verifique logs; a continuar."
  fi
fi

echo "Ensuring support user niohub..."
set +e
python manage.py ensure_niohub_support_user
nh_rc=$?
set -e
if [[ $nh_rc -ne 0 ]]; then
  echo "⚠️ ensure_niohub_support_user falhou (rc=$nh_rc) — a continuar."
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Launching Daphne server..."
exec "$@"
