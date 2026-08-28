# NioHub Telefonia — start local (conforme README do serviço)
# Uso: .\tools\niohub-telefonia\start-niohub-telefonia.ps1
#
# Áudio ao vivo: precisa de native/ + compilador C (w64devkit ou LLVM MinGW).
# Sem compilador: sobe só sinalização (pareia e chama, sem áudio).
#
# Postgres: defina WACALLS_PG_URL ou use services/niohub-telefonia/.env

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$AppDir = Join-Path $Root "services\niohub-telefonia"
$NativeDir = Join-Path $AppDir "native"
$EnvFile = Join-Path $AppDir ".env"
$W64Gcc = Join-Path $AppDir "w64devkit\bin\gcc.exe"

if (-not (Test-Path $AppDir)) {
    Write-Host "Clone ausente. Rode:" -ForegroundColor Yellow
    Write-Host "  git clone https://github.com/juniorssilvaa/niohub_telefonia.git `"$AppDir`""
    exit 1
}

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        Set-Item -Path "env:$key" -Value $val
    }
    Write-Host "Config: $EnvFile" -ForegroundColor DarkGray
}

if (-not $env:WACALLS_PG_URL) {
    $env:WACALLS_PG_URL = "postgres://postgres:postgres@127.0.0.1:5432/postgres?sslmode=disable"
}
if (-not $env:WACALLS_PG_NAMESPACE) {
    $env:WACALLS_PG_NAMESPACE = "niohub_calls"
}

$Port = if ($env:NIOHUB_CALLS_PORT) { $env:NIOHUB_CALLS_PORT } else { "8080" }

function Find-CCompiler {
    if (Test-Path $W64Gcc) { return $W64Gcc }
    $gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if ($gcc) { return $gcc.Source }
    foreach ($p in @(
        "C:\msys64\mingw64\bin\gcc.exe",
        "C:\Program Files\LLVM\bin\clang.exe"
    )) {
        if (Test-Path $p) { return $p }
    }
    $wingetGcc = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "gcc.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetGcc) { return $wingetGcc.FullName }
    return $null
}

function Get-PortListenerPid([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Test-MlowNativeReady {
    $dll = Join-Path $NativeDir "libopus_mlow.dll"
    if (-not (Test-Path $dll)) {
        $alt = Join-Path $NativeDir "opus_mlow.dll"
        if (Test-Path $alt) {
            Copy-Item $alt $dll -Force
        }
    }
    return (Test-Path $dll)
}

function Hide-PgPassword([string]$url) {
    if ($url -match '^(postgres://[^:]+:)([^@]+)(@.+)$') {
        return $matches[1] + '***' + $matches[3]
    }
    return $url
}

$useAudio = $false
$cc = Find-CCompiler
if (Test-MlowNativeReady -and $cc) {
    $useAudio = $true
    $env:CGO_ENABLED = "1"
    $env:CC = $cc
    $env:CGO_LDFLAGS = "-L$NativeDir -lopus_mlow"
    $env:PATH = "$NativeDir;" + (Split-Path $cc) + ";" + $env:PATH
}

$listenerPid = Get-PortListenerPid ([int]$Port)
if ($listenerPid) {
    $procName = (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue).ProcessName
    Write-Host ""
    Write-Host "Porta $Port ja em uso (PID $listenerPid, $procName)." -ForegroundColor Red
    Write-Host "  Stop-Process -Id $listenerPid -Force" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Write-Host "NioHub Telefonia -> http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "Postgres: $(Hide-PgPassword $env:WACALLS_PG_URL)"

if ($useAudio) {
    Write-Host "Modo: audio completo (MLow + CGO, -tags mlow)" -ForegroundColor Green
    Write-Host "Compilador: $cc" -ForegroundColor DarkGray
} else {
    Write-Host "Modo: somente sinalizacao (sem audio bidirecional)" -ForegroundColor Yellow
    if (-not (Test-MlowNativeReady)) {
        Write-Host "Sem libopus_mlow.dll em services/niohub-telefonia/native/" -ForegroundColor DarkGray
    }
    if (-not $cc) {
        Write-Host "Sem compilador C. Veja README: w64devkit nos Releases do niohub_telefonia." -ForegroundColor DarkGray
    }
}
Write-Host ""

Set-Location $AppDir
& go mod download
if ($useAudio) {
    & go run -tags mlow ./cmd/server -addr ":$Port" -debug
} else {
    & go run ./cmd/server -addr ":$Port" -debug
}
