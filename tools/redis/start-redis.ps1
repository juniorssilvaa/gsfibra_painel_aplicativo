# Inicia Redis local (porta 6379) para desenvolvimento NioHub
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $Root "redis-server.exe"
$Conf = Join-Path $Root "redis.windows.conf"

if (-not (Test-Path $Server)) {
    Write-Error "redis-server.exe nao encontrado em $Root"
    exit 1
}

$existing = Get-NetTCPConnection -LocalPort 6379 -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Redis ja esta rodando na porta 6379."
    & (Join-Path $Root "redis-cli.exe") ping
    exit 0
}

Write-Host "Iniciando Redis em 127.0.0.1:6379 ..."
Start-Process -FilePath $Server -ArgumentList $Conf -WindowStyle Hidden
Start-Sleep -Seconds 2
& (Join-Path $Root "redis-cli.exe") ping
