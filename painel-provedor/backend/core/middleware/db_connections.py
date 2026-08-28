"""
Fecha conexões PostgreSQL ao fim de cada request HTTP.

Com Daphne/ASGI e CONN_MAX_AGE baixo, garante que threads do pool não acumulem
ligações ociosas — crítico quando max_connections do Postgres é limitado (ex.: 100).
"""
from __future__ import annotations

from django.db import close_old_connections


class CloseDatabaseConnectionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            close_old_connections()
