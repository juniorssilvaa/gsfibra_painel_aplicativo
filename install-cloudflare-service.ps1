# Script para instalar o Cloudflare Tunnel como servico do Windows
# DEVE ser executado como Administrador
# Clique com botao direito > Executar como administrador

Write-Host "Instalando Cloudflare Tunnel como servico..." -ForegroundColor Cyan

# Verificar se esta executando como administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERRO: Este script precisa ser executado como Administrador!" -ForegroundColor Red
    Write-Host "   Clique com botao direito no arquivo e selecione 'Executar como administrador'" -ForegroundColor Yellow
    pause
    exit 1
}

# Token do Cloudflare
$token = "eyJhIjoiMzdmZWJkOWY5NDcxOWNkYTMxMWMyODU2MDIyZDc3OTkiLCJ0IjoiOTBhYjRjOTYtZWEyYi00YjE1LThlZjUtOGMzMmY0ZjkzMzk4IiwicyI6Ik5qTXhZMk13TnpVdFpXUXpPQzAwWkRjM0xUazVPVFV0TW1Sak4ySXdaVFF5WlRjMiJ9"

# Verificar onde está o cloudflared
$cloudflaredPath = "cloudflared.exe"
if (Test-Path "E:\niochat\cloudflared.exe") {
    $cloudflaredPath = "E:\niochat\cloudflared.exe"
} elseif (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $cloudflaredPath = (Get-Command cloudflared).Source
}

Write-Host "Usando cloudflared em: $cloudflaredPath" -ForegroundColor Cyan
Write-Host "Instalando servico com token..." -ForegroundColor Yellow
& $cloudflaredPath service install $token

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCESSO: Servico instalado com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Iniciando servico..." -ForegroundColor Cyan
    net start cloudflared
    
    Write-Host ""
    Write-Host "Servico iniciado!" -ForegroundColor Green
    Write-Host "Tunnel ativo:" -ForegroundColor Cyan
    Write-Host "   Frontend: https://front.niohub.com.br" -ForegroundColor Green
    Write-Host "   Backend:  https://api.niohub.com.br" -ForegroundColor Green
    Write-Host ""
    Write-Host "Para parar o servico:" -ForegroundColor Cyan
    Write-Host "   net stop cloudflared" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Para verificar o status:" -ForegroundColor Cyan
    Write-Host "   sc query cloudflared" -ForegroundColor Yellow
} else {
    Write-Host "ERRO: Erro ao instalar servico" -ForegroundColor Red
}

pause
