# Script para instalar o Cloudflare Tunnel como serviço do Windows
# DEVE ser executado como Administrador
# Clique com botão direito > Executar como administrador

Write-Host "🔵 Instalando Cloudflare Tunnel como serviço..." -ForegroundColor Cyan

# Verificar se está executando como administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ Este script precisa ser executado como Administrador!" -ForegroundColor Red
    Write-Host "   Clique com botão direito no arquivo e selecione 'Executar como administrador'" -ForegroundColor Yellow
    pause
    exit 1
}

# Token do Cloudflare
$token = "eyJhIjoiMzdmZWJkOWY5NDcxOWNkYTMxMWMyODU2MDIyZDc3OTkiLCJ0IjoiZDFlYTJjN2ItODQ5Yy00YWE2LWE4Y2ItZDQyZmQ0YjkyNjk3IiwicyI6Ik5URTFNVGRtTnpJdFpUazRNeTAwWldGakxXSTVNREV0TVdNNFltSTVNMlprTkRVMSJ9"

Write-Host "Instalando serviço com token..." -ForegroundColor Yellow
cloudflared.exe service install $token

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Serviço instalado com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Para iniciar o serviço:" -ForegroundColor Cyan
    Write-Host "   net start cloudflared" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Para parar o serviço:" -ForegroundColor Cyan
    Write-Host "   net stop cloudflared" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Para verificar o status:" -ForegroundColor Cyan
    Write-Host "   sc query cloudflared" -ForegroundColor Yellow
} else {
    Write-Host "❌ Erro ao instalar serviço" -ForegroundColor Red
}

pause






