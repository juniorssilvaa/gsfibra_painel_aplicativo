"""
Comando Django para gerenciar worker das integrações Telegram
"""

import asyncio
import os
import signal
import threading
import time
from django.core.management.base import BaseCommand
from integrations.telegram_service import telegram_manager


class Command(BaseCommand):
    help = 'Gerenciar worker das integrações Telegram'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'stop', 'restart', 'status'],
            help='Ação a ser executada'
        )
        parser.add_argument(
            '--integration-id',
            type=int,
            help='ID da integração específica (opcional)'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        integration_id = options.get('integration_id')
        
        if action == 'start':
            self.start_worker(integration_id)
        elif action == 'stop':
            self.stop_worker(integration_id)
        elif action == 'restart':
            self.restart_worker(integration_id)
        elif action == 'status':
            self.show_status()
    
    def start_worker(self, integration_id=None):
        """Iniciar worker de forma resiliente"""
        self.stdout.write(self.style.SUCCESS("🤖 Iniciando Worker Telegram Resiliente..."))
        
        stop_requested = {"value": False}

        while True:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def _graceful_shutdown():
                    """Desconecta os clientes Telegram com prazo limitado antes de parar o loop."""
                    try:
                        await asyncio.wait_for(telegram_manager.stop_all_integrations(), timeout=6)
                    except Exception as shutdown_err:
                        self.stdout.write(
                            self.style.WARNING(f"⚠️ Shutdown não concluiu a tempo/limpo: {shutdown_err}")
                        )
                    finally:
                        loop.stop()

                # Configurar handlers para sinais
                def signal_handler(signum, frame):
                    # Em Swarm/Portainer é normal receber SIGTERM em update/redeploy.
                    self.stdout.write(self.style.WARNING("⚠️ Recebido sinal de parada. Encerrando worker..."))
                    stop_requested["value"] = True

                    # Watchdog: se o processo não sair sozinho a tempo (loop travado por
                    # alguma conexão pendente do Telethon), força a saída para evitar que o
                    # orquestrador (Swarm/Portainer) precise enviar SIGKILL (exit code 137).
                    def _watchdog():
                        time.sleep(8)
                        os._exit(0)

                    threading.Thread(target=_watchdog, name="telegram-shutdown-watchdog", daemon=True).start()

                    try:
                        loop.call_soon_threadsafe(lambda: loop.create_task(_graceful_shutdown()))
                    except Exception:
                        try:
                            loop.stop()
                        except Exception:
                            pass
                
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)
                
                self.stdout.write("🔍 Buscando integrações Telegram ativas...")
                
                if integration_id:
                    # Iniciar integração específica
                    loop.run_until_complete(
                        telegram_manager.start_integration(integration_id)
                    )
                else:
                    # Iniciar todas as integrações
                    loop.run_until_complete(
                        telegram_manager.start_all_integrations()
                    )
                
                # Verificar se alguma começou
                if not telegram_manager.services:
                    self.stdout.write(self.style.WARNING("😴 Nenhuma integração ativa encontrada. Verificando novamente em 60s..."))
                    # Agendar um stop do loop para re-checar depois do sleep no while True
                    loop.call_later(60, loop.stop)
                else:
                    self.stdout.write(self.style.SUCCESS(f"🚀 {len(telegram_manager.services)} integração(ões) iniciada(s)."))
                
                # Manter o worker vivo infinitamente (Importante para o Docker)
                # Mesmo que não haja nada agora, ele deve ficar vivo aguardando novas
                loop.run_forever()

                # Se foi pedido parar, sair sem reiniciar
                if stop_requested["value"]:
                    return

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Erro fatal no Worker: {e}"))
                self.stdout.write("🔄 Reiniciando Worker em 15 segundos...")
                time.sleep(15)
            finally:
                if 'loop' in locals() and loop.is_running():
                    loop.stop()
                if 'loop' in locals():
                    loop.close()
    
    def stop_worker(self, integration_id=None):
        """Parar worker"""
        self.stdout.write("Parando worker Telegram...")
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if integration_id:
                loop.run_until_complete(
                    telegram_manager.stop_integration(integration_id)
                )
            else:
                loop.run_until_complete(
                    telegram_manager.stop_all_integrations()
                )
            
            self.stdout.write(
                self.style.SUCCESS("Worker Telegram parado com sucesso!")
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Erro ao parar worker: {e}")
            )
    
    def restart_worker(self, integration_id=None):
        """Reiniciar worker"""
        self.stop_worker(integration_id)
        self.start_worker(integration_id)
    
    def show_status(self):
        """Mostrar status das integrações"""
        from integrations.models import TelegramIntegration
        
        integrations = TelegramIntegration.objects.filter(is_active=True)
        
        if not integrations:
            self.stdout.write("Nenhuma integração Telegram ativa encontrada.")
            return
        
        self.stdout.write("Status das integrações Telegram:")
        self.stdout.write("-" * 50)
        
        for integration in integrations:
            status = "🟢 Rodando" if integration.id in telegram_manager.services else "🔴 Parado"
            connected = " Conectado" if integration.is_connected else " Desconectado"
            
            self.stdout.write(
                f"ID: {integration.id} | "
                f"Empresa: {integration.company.name} | "
                f"Telefone: {integration.phone_number} | "
                f"Status: {status} | "
                f"Conexão: {connected}"
            )
    
    async def shutdown(self, loop):
        """Shutdown graceful"""
        self.stdout.write("Parando todas as integrações...")
        await telegram_manager.stop_all_integrations()
        loop.stop()

