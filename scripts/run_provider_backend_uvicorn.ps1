# Provider backend (ASGI) — Windows dev
# Evita spam "ValueError: I/O operation on closed file" no access log do Uvicorn
# quando o stdout do terminal (ex.: integrado) está com stream fechado.
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m uvicorn niochat.asgi:application --host 0.0.0.0 --port 8010 --no-access-log
