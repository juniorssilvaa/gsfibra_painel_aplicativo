"""
Tarefas periódicas no processo ASGI (Daphne) do superadmin.

A cada ~60s (alinhado ao minuto):
- envio de cobranças WhatsApp (config SystemConfig.payload);
- bloqueio automático de provedores por fatura Asaas (~10 min);
- envio de pushes agendados do app mobile (MobileScheduledNotification).

Desative com DISABLE_ASGI_PERIODIC_TASKS=1
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
_last_auto_block = 0.0
_AUTO_BLOCK_INTERVAL_SECONDS = 600


def _sleep_until_next_minute() -> None:
    now = time.time()
    next_minute = (int(now // 60) + 1) * 60
    delay = max(0.2, min(60.0, next_minute - now))
    time.sleep(delay)


def _periodic_loop() -> None:
    global _last_auto_block

    time.sleep(20)
    while True:
        close_old_connections()
        billing_result = None
        try:
            from super_core.billing_send_service import run_billing_send_cycle

            billing_result = run_billing_send_cycle()
            logger.info(
                "[Superadmin ASGI periodic] billing tick: success=%s executed=%s reason=%s sent_ok=%s",
                billing_result.get("success"),
                billing_result.get("executed"),
                billing_result.get("reason"),
                billing_result.get("sent_ok"),
            )
        except Exception:
            logger.exception("[Superadmin ASGI periodic] erro em billing_send")

        try:
            now_m = time.monotonic()
            run_block = now_m - _last_auto_block >= _AUTO_BLOCK_INTERVAL_SECONDS
            if run_block:
                _last_auto_block = now_m
            elif (
                isinstance(billing_result, dict)
                and billing_result.get("executed")
                and (billing_result.get("sent_ok") or 0) > 0
            ):
                run_block = True
                _last_auto_block = now_m

            if run_block:
                from super_core.billing_auto_block import run_billing_auto_block_cycle

                blk = run_billing_auto_block_cycle()
                logger.info("[Superadmin ASGI periodic] auto_block: %s", blk)
        except Exception:
            logger.exception("[Superadmin ASGI periodic] erro em auto_block")

        try:
            from mobile_app.push_service import process_due_scheduled_notifications

            sched = process_due_scheduled_notifications()
            if sched.get("processed"):
                logger.info(
                    "[Superadmin ASGI periodic] scheduled_push: processed=%s checked=%s",
                    sched.get("processed"),
                    sched.get("checked"),
                )
        except Exception:
            logger.exception("[Superadmin ASGI periodic] erro em scheduled_push")

        _sleep_until_next_minute()


def start_inline_periodic_tasks() -> None:
    global _started
    if os.environ.get("DISABLE_ASGI_PERIODIC_TASKS", "").lower() in ("1", "true", "yes"):
        logger.info("[Superadmin ASGI periodic] desabilitado (DISABLE_ASGI_PERIODIC_TASKS)")
        return
    with _lock:
        if _started:
            return
        _started = True
    t = threading.Thread(
        target=_periodic_loop,
        name="superadmin-asgi-periodic",
        daemon=True,
    )
    t.start()
    logger.info(
        "[Superadmin ASGI periodic] thread iniciada "
        "(billing_send + auto_block Asaas + scheduled_push)"
    )
