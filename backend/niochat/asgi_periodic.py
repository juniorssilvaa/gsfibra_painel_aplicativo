"""
Tarefas periódicas leves no mesmo processo do ASGI (Daphne).

Dispara a cada ~60s:
- encerramento de conversas em "closing" (mesma lógica do actor Dramatiq);
- ciclo de cobrança superadmin (mesma lógica do actor Dramatiq);
- bloqueio automático de provedores por fatura Asaas (cerca de a cada 10 minutos).

Assim o backend sozinho já agenda cobrança e fechamentos, sem depender de
RUN_HEARTBEAT nem de processo dramatiq separado (útil em dev e instalações simples).

Desative com variável de ambiente: DISABLE_ASGI_PERIODIC_TASKS=1
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()
_last_asaas_block_check = 0.0
_ASAAS_BLOCK_CHECK_INTERVAL_SECONDS = 600  # valida bloqueio automático a cada 10 minutos


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
    time.sleep(25)
    while True:
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

        global _last_asaas_block_check
        try:
            now_m = time.monotonic()
            if now_m - _last_asaas_block_check >= _ASAAS_BLOCK_CHECK_INTERVAL_SECONDS:
                _last_asaas_block_check = now_m
                from core.asaas_provedor_block import run_periodic_asaas_provedor_blocks

                blk = run_periodic_asaas_provedor_blocks()
                logger.info("[ASGI periodic] asaas_provedor_block: %s", blk)
        except Exception:
            logger.exception("[ASGI periodic] erro em asaas_provedor_block")

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
    t = threading.Thread(
        target=_periodic_loop,
        name="niochat-asgi-periodic",
        daemon=True,
    )
    t.start()
    logger.info(
        "[ASGI periodic] thread de tarefas periódicas iniciada (billing + finalize_closing + asaas_provedor_block)"
    )
