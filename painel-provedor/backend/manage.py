#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Python 3.13+: argparse coloriza a ajuda e chama isatty(fileno()). Em alguns
# ambientes (ex.: PowerShell/IDE com stream já inválido) isso gera
# ValueError: I/O operation on closed file antes de qualquer comando rodar.
# Desliga cores do stdlib para o processo do manage.py (use DJANGO_FORCE_COLORS=1 para manter).
if os.environ.get("DJANGO_FORCE_COLORS") != "1":
    os.environ.setdefault("PYTHON_COLORS", "0")
    os.environ.setdefault("NO_COLOR", "1")


def _repair_stdio_if_closed():
    """Evita ValueError ao escrever ajuda/comandos quando stdout/stderr foram fechados."""
    try:
        if getattr(sys.stdout, "closed", False):
            sys.stdout = sys.__stdout__
        if getattr(sys.stderr, "closed", False):
            sys.stderr = sys.__stderr__
    except Exception:
        pass


def main():
    """Run administrative tasks."""
    _repair_stdio_if_closed()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
