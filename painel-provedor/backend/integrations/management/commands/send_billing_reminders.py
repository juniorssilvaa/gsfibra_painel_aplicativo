"""
Ciclo de cobrança do superadmin (WhatsApp canal exclusivo + Asaas).

A rotina NÃO roda dentro do Daphne sozinha: em produção costuma ser disparada pelo
Dramatiq (`send_superadmin_billing_reminders`) quando RUN_HEARTBEAT=true e há worker,
ou por este comando em cron.

Uso manual (teste imediato):
    python manage.py send_billing_reminders

Cron (ex.: a cada minuto — o próprio comando ignora fora da janela configurada):
    * * * * * cd /caminho/backend && /caminho/venv/bin/python manage.py send_billing_reminders
"""

import logging
import sys

from django.core.management.base import BaseCommand

from integrations.billing_reminder_service import run_billing_reminder_cycle

logger = logging.getLogger(__name__)


def _emit(msg: str) -> None:
    """Evita falha quando sys.stdout foi fechado (Python 3.14 / alguns terminais)."""
    line = f"{msg}\n"
    for stream in (sys.stdout, getattr(sys, "__stdout__", None)):
        if stream is None or getattr(stream, "closed", False):
            continue
        try:
            stream.write(line)
            stream.flush()
            return
        except (ValueError, OSError, AttributeError, TypeError):
            continue
    logger.info(msg)


class Command(BaseCommand):
    help = "Executa um ciclo da automação de cobrança (superadmin / Asaas / WhatsApp)."

    def handle(self, *args, **options):
        _emit("Executando ciclo de cobrança...")
        result = run_billing_reminder_cycle()
        _emit(str(result))
        if result.get("success") and result.get("sent_total", 0) == 0 and result.get("reason"):
            _emit(f"Motivo: {result.get('reason')}")
