$token = "EAAKI9ZAACsD0BRbGQcMwv2nKIrdMc1ZC4Sb2cGAzMddxKkqLVkEDRsPqVa9a1zZBfgkjCXSi5ObgYIEZBT37wXjPXaZC81XQ2fKuzfTyLB2ivtTyZCycDzJEmOs0ZCT6qxfsTFkwzFd8Wk8wsx2NClkbsLkJllo7268HMlFnZAz9hfz4WR3ZBOeHrzYjeWxG8RpnI7cJbfkUJ0zorP7E6tJkOMOMmuUFz8bYyydp4iwdPNZAno8sHkWPRZAnFRGJZADoLVmQ5pGZCS9aVNRKUowZAkoLwqnN4e"
$wabaId = "3052659568265187"

Write-Host "Listando todos os templates da WABA $wabaId..." -ForegroundColor Cyan

$url = "https://graph.facebook.com/v23.0/$wabaId/message_templates?fields=name,status,category,components"
$resp = curl.exe --silent -G $url -H "Authorization: Bearer $token" 2>$null

$json = $resp | ConvertFrom-Json
$json.data | Select-Object name, status, category | Format-Table -AutoSize

# Salvar detalhes completos para analise
$resp | Out-File "e:\niohub\scripts\templates_detalhes.json"
Write-Host "Detalhes salvos em templates_detalhes.json" -ForegroundColor Green
