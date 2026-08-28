$json = Get-Content "e:\niohub\scripts\templates_detalhes.json" -Encoding Unicode | ConvertFrom-Json
$tpl = $json.data | Where-Object { $_.name -eq "cobranca" }
if ($tpl) {
    $tpl | ConvertTo-Json -Depth 10
} else {
    Write-Host "Template 'cobranca' nao encontrado."
}
