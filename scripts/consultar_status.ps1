$token = "EAAKI9ZAACsD0BRbGQcMwv2nKIrdMc1ZC4Sb2cGAzMddxKkqLVkEDRsPqVa9a1zZBfgkjCXSi5ObgYIEZBT37wXjPXaZC81XQ2fKuzfTyLB2ivtTyZCycDzJEmOs0ZCT6qxfsTFkwzFd8Wk8wsx2NClkbsLkJllo7268HMlFnZAz9hfz4WR3ZBOeHrzYjeWxG8RpnI7cJbfkUJ0zorP7E6tJkOMOMmuUFz8bYyydp4iwdPNZAno8sHkWPRZAnFRGJZADoLVmQ5pGZCS9aVNRKUowZAkoLwqnN4e"
$messageId = "wamid.HBgMNTU5NDkxNTYxMjQ4FQIAERgSRENBNjVEOTUxQzdENDQzOTBGAA=="

Write-Host "Consultando status da mensagem $messageId..." -ForegroundColor Cyan

$url = "https://graph.facebook.com/v23.0/$messageId"
$resp = curl.exe --silent -G $url -H "Authorization: Bearer $token" 2>$null

Write-Host ""
Write-Host "======= STATUS DA MENSAGEM ======="
$resp | ConvertFrom-Json | ConvertTo-Json -Depth 10
Write-Host "=================================="
