# Script para reinstalar o Cloudflare Tunnel como servico do Windows
# DEVE ser executado como Administrador
# Clique com botao direito > Executar como administrador

Write-Host "Reinstalando Cloudflare Tunnel como servico..." -ForegroundColor Cyan

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

Write-Host "Parando servico..." -ForegroundColor Yellow
net stop cloudflared

# Verificar onde está o cloudflared
$cloudflaredPath = "cloudflared.exe"
if (Test-Path "E:\niochat\cloudflared.exe") {
    $cloudflaredPath = "E:\niochat\cloudflared.exe"
} elseif (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $cloudflaredPath = (Get-Command cloudflared).Source
}

Write-Host "Usando cloudflared em: $cloudflaredPath" -ForegroundColor Cyan

Write-Host "Desinstalando servico antigo..." -ForegroundColor Yellow
& $cloudflaredPath service uninstall

Write-Host "Aguardando 2 segundos..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

Write-Host "Instalando servico com novo token..." -ForegroundColor Yellow
& $cloudflaredPath service install $token

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCESSO: Servico reinstalado com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Iniciando servico..." -ForegroundColor Cyan
    net start cloudflared
    
    Write-Host ""
    Write-Host "Servico iniciado!" -ForegroundColor Green
    Write-Host "Tunnel ativo:" -ForegroundColor Cyan
    Write-Host "   Frontend: https://front.niohub.com.br" -ForegroundColor Green
    Write-Host "   Backend:  https://api.niohub.com.br" -ForegroundColor Green
} else {
    Write-Host "ERRO: Erro ao reinstalar servico" -ForegroundColor Red
}

pause

