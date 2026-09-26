"""
Tarefas periódicas leves no mesmo processo do ASGI (Daphne).

Dispara a cada ~60s:
- encerramento de conversas em "closing" (mesma lógica do actor Dramatiq);
- ciclo de cobrança superadmin (mesma lógica do actor Dramatiq);
- bloqueio automático de provedores por fatura Asaas (cerca de a cada 10 minutos);
- análise de aprendizado da IA das encerradas há pelo menos 3 minutos (verificação a cada minuto);
- rotina noturna: encerradas de dias anteriores vão ao Supabase (core.nightly_migration).

Assim o backend sozinho já agenda cobrança e fechamentos, sem depender de
RUN_HEARTBEAT nem de processo dramatiq separado (útil em dev e instalações simples).

Desative com variável de ambiente: DISABLE_ASGI_PERIODIC_TASKS=1
"""

from __future__ import annotations

import logging
import os
import threading
import time

from django.db import close_old_connections

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()
_last_asaas_block_check = 0.0
_ASAAS_BLOCK_CHECK_INTERVAL_SECONDS = 600  # valida bloqueio automático a cada 10 minutos
_last_version_report = 0.0
_VERSION_REPORT_INTERVAL_SECONDS = 300
_last_ai_learning_scan = 0.0
_AI_LEARNING_SCAN_INTERVAL_SECONDS = 60


def _sleep_until_next_minute() -> None:
    """
    Dorme até a virada do próximo minuto de relógio.
    Evita drift acumulado de sleep(60) e melhora gatilhos com janela = 0.
    """
    now = time.time()
    next_minute = (int(now // 60) + 1) * 60
    delay = max(0.2, min(60.0, next_minute - now))
    time.sleep(delay)


def _periodic_loop() -> None:
    global _last_asaas_block_check, _last_version_report, _last_ai_learning_scan

    time.sleep(25)
    while True:
        close_old_connections()
        try:
            from conversations.closing_service import closing_service

            stats = closing_service.process_final_closures()
            if stats.get("finalized") or stats.get("errors"):
                logger.info("[ASGI periodic] finalize_closing: %s", stats)
        except Exception:
            logger.exception("[ASGI periodic] erro em finalize_closing")

        try:
            from integrations.billing_reminder_service import run_billing_reminder_cycle

            result = run_billing_reminder_cycle()
            logger.info(
                "[ASGI periodic] billing tick: run_at=%s success=%s reason=%s sent_total=%s sent_template=%s sent_interactive=%s sent_text=%s",
                result.get("run_at"),
                result.get("success"),
                result.get("reason"),
                result.get("sent_total"),
                result.get("sent_template"),
                result.get("sent_interactive"),
                result.get("sent_text_fallback"),
            )
            if result.get("sent_total") or result.get("sent_template") or result.get("sent_interactive"):
                logger.info("[ASGI periodic] billing: %s", result)
            elif result.get("success") is False:
                logger.warning("[ASGI periodic] billing: %s", result)
        except Exception:
            logger.exception("[ASGI periodic] erro em billing")

        try:
            from conversations.chatbot_timeout_service import run_chatbot_inactivity_scan

            run_chatbot_inactivity_scan()
        except Exception:
            logger.exception("[ASGI periodic] erro em chatbot inactivity scan")

        try:
            now_m = time.monotonic()
            if now_m - _last_ai_learning_scan >= _AI_LEARNING_SCAN_INTERVAL_SECONDS:
                _last_ai_learning_scan = now_m
                from conversations.ai_learning import analyze_pending_closed

                analyzed = analyze_pending_closed()
                if analyzed:
                    logger.info("[ASGI periodic] aprendizado da IA: %s atendimento(s) analisado(s)", analyzed)

                from ai.learnings import start_pending_suggestions

                start_pending_suggestions()
        except Exception:
            logger.exception("[ASGI periodic] erro na análise de aprendizado da IA")

        try:
            from core.nightly_migration import maybe_start_nightly_migration

            if maybe_start_nightly_migration():
                logger.info("[ASGI periodic] rotina noturna de migração iniciada")
        except Exception:
            logger.exception("[ASGI periodic] erro ao iniciar rotina noturna de migração")

        try:
            now_m = time.monotonic()
            if now_m - _last_version_report >= _VERSION_REPORT_INTERVAL_SECONDS:
                _last_version_report = now_m
                from integrations.superadmin_notifier import report_running_version

                report_running_version()
        except Exception:
            logger.exception("[ASGI periodic] erro em heartbeat de versão")

        try:
            now_m = time.monotonic()
            if now_m - _last_asaas_block_check >= _ASAAS_BLOCK_CHECK_INTERVAL_SECONDS:
                _last_asaas_block_check = now_m
                from core.asaas_provedor_block import run_periodic_asaas_provedor_blocks

                blk = run_periodic_asaas_provedor_blocks()
                logger.info("[ASGI periodic] asaas_provedor_block: %s", blk)
        except Exception:
            logger.exception("[ASGI periodic] erro em asaas_provedor_block")

        close_old_connections()
        _sleep_until_next_minute()


def start_inline_periodic_tasks() -> None:
    """Inicia thread daemon uma vez (idempotente)."""
    global _started
    if os.environ.get("DISABLE_ASGI_PERIODIC_TASKS", "").lower() in ("1", "true", "yes"):
        logger.info("[ASGI periodic] desabilitado (DISABLE_ASGI_PERIODIC_TASKS)")
        return
    with _lock:
        if _started:
            return
        _started = True
    try:
        from core.health_report import install_error_counter

        install_error_counter()
    except Exception:
        logger.exception("[ASGI periodic] falha ao instalar contador de erros")
    t = threading.Thread(
        target=_periodic_loop,
        name="niochat-asgi-periodic",
        daemon=True,
    )
    t.start()
    logger.info(
        "[ASGI periodic] thread de tarefas periódicas iniciada (billing + finalize_closing + asaas_provedor_block + version heartbeat)"
    )
