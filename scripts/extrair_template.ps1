$json = Get-Content "e:\niohub\scripts\templates_detalhes.json" -Encoding Unicode | ConvertFrom-Json
$tpl = $json.data | Where-Object { $_.name -eq "prox_do_vencimento" }
if ($tpl) {
    $tpl | ConvertTo-Json -Depth 10
} else {
    Write-Host "Template 'prox_do_vencimento' nao encontrado no JSON."
}
