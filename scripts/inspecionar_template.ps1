$token = "EAAKI9ZAACsD0BRbGQcMwv2nKIrdMc1ZC4Sb2cGAzMddxKkqLVkEDRsPqVa9a1zZBfgkjCXSi5ObgYIEZBT37wXjPXaZC81XQ2fKuzfTyLB2ivtTyZCycDzJEmOs0ZCT6qxfsTFkwzFd8Wk8wsx2NClkbsLkJllo7268HMlFnZAz9hfz4WR3ZBOeHrzYjeWxG8RpnI7cJbfkUJ0zorP7E6tJkOMOMmuUFz8bYyydp4iwdPNZAno8sHkWPRZAnFRGJZADoLVmQ5pGZCS9aVNRKUowZAkoLwqnN4e"

# Buscar business
$biz = curl.exe --silent -G "https://graph.facebook.com/v23.0/me/businesses" `
    --data-urlencode "fields=id,name" `
    -H "Authorization: Bearer $token" 2>$null | ConvertFrom-Json

Write-Host "Businesses: $($biz | ConvertTo-Json)"

$wabaId = $null
foreach ($b in $biz.data) {
    $w = curl.exe --silent -G "https://graph.facebook.com/v23.0/$($b.id)/owned_whatsapp_business_accounts" `
        --data-urlencode "fields=id,name" `
        -H "Authorization: Bearer $token" 2>$null | ConvertFrom-Json
    if ($w.data.Count -gt 0) {
        $wabaId = $w.data[0].id
        Write-Host "WABA ID: $wabaId"
        break
    }
}

if (-not $wabaId) {
    Write-Host "WABA nao encontrada via businesses. Informe manualmente:"
    $wabaId = Read-Host "WABA ID"
}

# Buscar template cobranca_order
Write-Host ""
Write-Host "Buscando template 'cobranca_order'..."
$tplRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/$wabaId/message_templates" `
    --data-urlencode "name=cobranca_order" `
    --data-urlencode "fields=name,status,components" `
    -H "Authorization: Bearer $token" 2>$null

$tplJson = $tplRaw | ConvertFrom-Json
Write-Host ""
Write-Host "======= TEMPLATE COMPLETO ======="
$tplJson | ConvertTo-Json -Depth 20
Write-Host "================================="
