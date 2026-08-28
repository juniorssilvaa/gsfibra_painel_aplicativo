# Script para iniciar o serviço Cloudflare Tunnel
# Pode ser executado sem privilégios de administrador (se o serviço já estiver instalado)

Write-Host "🔵 Iniciando serviço Cloudflare Tunnel..." -ForegroundColor Cyan

# Verificar se o serviço existe
$service = Get-Service -Name cloudflared -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "❌ Serviço cloudflared não encontrado!" -ForegroundColor Red
    Write-Host "   Execute primeiro: .\install-cloudflare-service.ps1 (como Administrador)" -ForegroundColor Yellow
    exit 1
}

# Verificar status do serviço
if ($service.Status -eq 'Running') {
    Write-Host "✅ Serviço já está rodando!" -ForegroundColor Green
    exit 0
}

# Iniciar serviço
Write-Host "Iniciando serviço..." -ForegroundColor Yellow
Start-Service -Name cloudflared

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Serviço iniciado com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Tunnel ativo:" -ForegroundColor Cyan
    Write-Host "   Frontend: https://front.niochat.com.br" -ForegroundColor Green
    Write-Host "   Backend:  https://api.niochat.com.br" -ForegroundColor Green
} else {
    Write-Host "❌ Erro ao iniciar serviço" -ForegroundColor Red
    Write-Host "   Tente executar como Administrador" -ForegroundColor Yellow
}






