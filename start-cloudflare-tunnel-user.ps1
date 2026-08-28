# Sobe o túnel local (config.yml) se ainda não estiver rodando.
# Usado no logon do Windows e para iniciar agora sem admin.

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$config = 'C:\Users\Junio\.cloudflared\config.yml'
$logDir = 'C:\Users\Junio\.cloudflared'
$logOut = Join-Path $logDir 'tunnel-user.out.log'
$logErr = Join-Path $logDir 'tunnel-user.err.log'

if (-not (Test-Path $exe)) {
    throw "cloudflared.exe nao encontrado em $exe"
}
if (-not (Test-Path $config)) {
    throw "config.yml nao encontrado em $config"
}

$already = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'cloudflared' -and $_.CommandLine -match 'config.yml' }
if ($already) {
    Write-Host 'Tunel Cloudflare ja esta em execucao.'
    exit 0
}

$cfArgs = @('tunnel', '--config', $config, '--protocol', 'http2', 'run')
Start-Process -FilePath $exe -ArgumentList $cfArgs -WindowStyle Hidden -RedirectStandardOutput $logOut -RedirectStandardError $logErr
Write-Host 'Tunel Cloudflare iniciado (api-local.niohub.com.br -> localhost:8011).'
