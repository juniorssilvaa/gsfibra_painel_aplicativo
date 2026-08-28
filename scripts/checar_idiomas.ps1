$json = Get-Content "e:\niohub\scripts\templates_detalhes.json" -Encoding Unicode | ConvertFrom-Json
$json.data | Select-Object name, language, status | Format-Table -AutoSize
