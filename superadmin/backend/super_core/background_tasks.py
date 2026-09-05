import threading
import time
import logging
import traceback
from .billing_send_service import run_billing_send_cycle
from .billing_auto_block import run_billing_auto_block_cycle

logger = logging.getLogger(__name__)

_AUTO_BLOCK_INTERVAL_SEC = 600  # 10 minutos (igual ao cron em produção)

def background_worker():
    """Loop principal de tarefas em background"""
    logger.info("[BackgroundWorker] Iniciado.")
    last_auto_block = -_AUTO_BLOCK_INTERVAL_SEC  # primeira execução logo ao subir o servidor

    while True:
        try:
            was_time = run_billing_send_cycle()

            now = time.time()
            if now - last_auto_block >= _AUTO_BLOCK_INTERVAL_SEC:
                last_auto_block = now
                logger.info("[BackgroundWorker] Ciclo de auto-bloqueio Asaas...")
                run_billing_auto_block_cycle()
            elif was_time and isinstance(was_time, dict) and was_time.get("executed"):
                logger.info("[BackgroundWorker] Pós-cobrança: auto-bloqueio extra...")
                run_billing_auto_block_cycle()
                last_auto_block = now

        except Exception as e:
            logger.error(f"[BackgroundWorker] Erro no loop: {str(e)}")
            traceback.print_exc()

        time.sleep(60)

_started = False
_start_lock = threading.Lock()


def start_background_tasks():
    """Inicia a thread de background (runserver dev; produção usa asgi_periodic)."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=background_worker, daemon=True, name="NioHubBackgroundWorker")
    t.start()
