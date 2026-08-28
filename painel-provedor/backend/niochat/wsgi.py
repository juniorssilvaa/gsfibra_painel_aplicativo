"""
WSGI config for nio chat project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')

logger.info("Iniciando carregamento do WSGI application...")
try:
    from django.core.wsgi import get_wsgi_application
    logger.info("get_wsgi_application importado")
    application = get_wsgi_application()
    logger.info("✓ WSGI application carregada com sucesso")
except Exception as e:
    logger.error(f"✗ Erro ao carregar WSGI application: {e}", exc_info=True)
    raise
