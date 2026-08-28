# =============================================================
# ENVIO DE FATURA WHATSAPP - API OFICIAL META
# Template: cobranca_order (PIX dinamico + PDF no header)
# =============================================================

$token         = "EAAKI9ZAACsD0BRYeiZB0av43lvw4UZAMJMrBJioC4FsMu62GfTUqZAnyJkr8bLHABBCF2ICmpl57x8hF2IsmbAy61pZAJAlPtwzIaeHeo83iNpRD1ZCgAxYZBTToDJ0zvj7oM4FNCFyOCYZBZBhvUK0ejhuC8Fs8ued0T646mwTN7DcZA2zXY2TBbbBd02JnElVa5aVeEd87lNyUh0HfMD2i3laZAlolQirzIWlbTe8gKeJSg6gPGm3EWNvicq0d8eeszWAUgZCqnvlNjZAQepVyU9n8Vwf7w"
$phoneNumberId = "1038319469369411"   # sera validado/corrigido no passo 0
$destino       = "558182677293"

# ===================== PIX =====================
$pixCode      = "00020101021226800014br.gov.bcb.pix2558pix.asaas.com/qr/cobv/473bfbd1-2e30-4fa6-9295-ac807fc0ee505204000053039865802BR5925NIO HUB TECNOLOGIA INOVA 6006Maraba61086851329062070503***6304B0A8"
$pixKey       = "63864720000115"

# ===================== BOLETO =====================
# Linha digitavel do boleto (so numeros para o botao de copiar)
$linhaDigitavel = "46191110000000000004229994223013414440000042000"
$merchantName = "NIO HUB TECNOLOGIA"
$pixKeyType   = "CNPJ"   # EMAIL | CPF | CNPJ | PHONE | EVP

# ===================== PDF =====================
$pdfUrl  = "https://www.asaas.com/b/pdf/4x08k1elswru7odj"
$pdfPath = "$env:TEMP\fatura_nio.pdf"

# ===================== VALORES =====================
# Body do template:
#   {{1}} = Nome/Descricao
#   {{2}} = Valor (ex: 59,90)
#   {{3}} = Vencimento (ex: 11/05/2026)
$valorFormatado    = "420,00"
$vencimentoTexto   = "12/05/2026"
$valorCentavos     = 42000

# NOTA: Para adicionar botao 'Copiar codigo de barras',
# e necessario criar um novo template na Meta com o botao
# copy_code cadastrado e aprovado.

# =============================================================
# PASSO 0: Validar token e descobrir Phone Number ID correto
# =============================================================
Write-Host "[0/4] Validando token e Phone Number ID na API Meta..." -ForegroundColor Cyan

$meRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/me" `
    --data-urlencode "fields=id,name" `
    -H "Authorization: Bearer $token" 2>$null

$meJson = $null
try { $meJson = $meRaw | ConvertFrom-Json } catch {}

if (-not $meJson -or $meJson.error) {
    Write-Host "ERRO: Token invalido ou sem permissao." -ForegroundColor Red
    if ($meJson -and $meJson.error) { Write-Host "  $($meJson.error.message)" -ForegroundColor Red }
    exit 1
}

Write-Host "      Token OK. Usuario: $($meJson.name) (ID: $($meJson.id))" -ForegroundColor Green

# Tentar validar o Phone Number ID informado diretamente
$pnRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/$phoneNumberId" `
    --data-urlencode "fields=id,display_phone_number,verified_name" `
    -H "Authorization: Bearer $token" 2>$null

$pnJson = $null
try { $pnJson = $pnRaw | ConvertFrom-Json } catch {}

if ($pnJson -and -not $pnJson.error -and $pnJson.id) {
    Write-Host "      Phone Number ID $phoneNumberId VALIDO => $($pnJson.display_phone_number) ($($pnJson.verified_name))" -ForegroundColor Green
} else {
    # Phone Number ID invalido para este token. Tentar descobrir via /me/businesses
    Write-Host "      Phone Number ID '$phoneNumberId' nao encontrado para este token. Buscando automaticamente..." -ForegroundColor Yellow

    $bizRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/me/businesses" `
        --data-urlencode "fields=id,name" `
        -H "Authorization: Bearer $token" 2>$null

    $bizJson = $null
    try { $bizJson = $bizRaw | ConvertFrom-Json } catch {}

    $wabaId = $null
    if ($bizJson -and $bizJson.data -and $bizJson.data.Count -gt 0) {
        foreach ($biz in $bizJson.data) {
            $wRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/$($biz.id)/owned_whatsapp_business_accounts" `
                --data-urlencode "fields=id,name" `
                -H "Authorization: Bearer $token" 2>$null
            $wJson = $null
            try { $wJson = $wRaw | ConvertFrom-Json } catch {}
            if ($wJson -and $wJson.data -and $wJson.data.Count -gt 0) {
                $wabaId = $wJson.data[0].id
                Write-Host "      WABA encontrada: $wabaId" -ForegroundColor Green
                break
            }
        }
    }

    if (-not $wabaId) {
        Write-Host ""
        Write-Host "======= PROBLEMA: Phone Number ID errado =======" -ForegroundColor Red
        Write-Host "  ID '$phoneNumberId' nao pertence a este token." -ForegroundColor Red
        Write-Host ""
        Write-Host "  SOLUCAO - informe o WABA ID do seu numero:" -ForegroundColor Yellow
        Write-Host "  (Encontre em: business.facebook.com -> Configuracoes -> WhatsApp)" -ForegroundColor Cyan
        $wabaIdInput = Read-Host "  WABA ID"
        if (-not $wabaIdInput) { exit 1 }
        $wabaId = $wabaIdInput
    }

    # Listar phone numbers da WABA
    $pnsRaw = curl.exe --silent -G "https://graph.facebook.com/v23.0/$wabaId/phone_numbers" `
        --data-urlencode "fields=id,display_phone_number,verified_name" `
        -H "Authorization: Bearer $token" 2>$null

    $pnsJson = $null
    try { $pnsJson = $pnsRaw | ConvertFrom-Json } catch {}

    if ($pnsJson -and $pnsJson.data -and $pnsJson.data.Count -gt 0) {
        Write-Host ""
        Write-Host "  Numeros disponiveis:" -ForegroundColor Cyan
        $idx = 0
        foreach ($pn in $pnsJson.data) {
            Write-Host "    [$idx] ID: $($pn.id)  |  $($pn.display_phone_number)  ($($pn.verified_name))" -ForegroundColor Green
            $idx++
        }
        $phoneNumberId = $pnsJson.data[0].id
        Write-Host ""
        Write-Host "  Usando: $phoneNumberId" -ForegroundColor Yellow
    } else {
        Write-Host "  Nao foi possivel listar os numeros. Resposta: $pnsRaw" -ForegroundColor Red
        exit 1
    }
}

# =============================================================
# PASSO 1: Baixar o PDF
# =============================================================
Write-Host ""
Write-Host "[1/4] Baixando PDF da fatura..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $pdfUrl -OutFile $pdfPath -UseBasicParsing -ErrorAction Stop
    $pdfSize = (Get-Item $pdfPath).Length
    Write-Host "      PDF salvo: $pdfPath ($pdfSize bytes)" -ForegroundColor Green
} catch {
    Write-Host "ERRO ao baixar PDF: $_" -ForegroundColor Red
    exit 1
}

# =============================================================
# PASSO 2: Upload do PDF para a API Meta
# =============================================================
Write-Host ""
Write-Host "[2/4] Fazendo upload do PDF para a Meta API..." -ForegroundColor Cyan

$uploadUrl = "https://graph.facebook.com/v23.0/$phoneNumberId/media"

$uploadRaw = curl.exe --silent `
    -X POST $uploadUrl `
    -H "Authorization: Bearer $token" `
    -F "messaging_product=whatsapp" `
    -F "file=@$pdfPath;type=application/pdf" 2>$null

Write-Host "      Resposta: $uploadRaw" -ForegroundColor DarkGray

$uploadJson = $null
try { $uploadJson = $uploadRaw | ConvertFrom-Json } catch {
    Write-Host "ERRO: Nao foi possivel parsear resposta do upload." -ForegroundColor Red
    exit 1
}

if ($uploadJson.error) {
    Write-Host "ERRO no upload: $($uploadJson.error.message)" -ForegroundColor Red
    exit 1
}

$mediaId = $uploadJson.id
if (-not $mediaId) {
    Write-Host "ERRO: Media ID vazio na resposta." -ForegroundColor Red
    exit 1
}

Write-Host "      MEDIA ID: $mediaId" -ForegroundColor Green

# =============================================================
# PASSO 3: Montar o JSON do template
# =============================================================
Write-Host ""
Write-Host "[3/4] Montando payload do template 'prox_do_vencimento'..." -ForegroundColor Cyan

$bodyObject = @{
    messaging_product = "whatsapp"
    to                = $destino
    type              = "template"
    template          = @{
        name     = "prox_do_vencimento"
        language = @{ code = "pt_BR" }
        components = @(

            # HEADER: Documento PDF
            @{
                type       = "header"
                parameters = @(
                    @{
                        type     = "document"
                        document = @{
                            id       = $mediaId
                            filename = "fatura.pdf"
                        }
                    }
                )
            },

            # BODY: {{1}} = nome, {{2}} = valor, {{3}} = vencimento
            @{
                type       = "body"
                parameters = @(
                    @{ type = "text"; text = "NANET TELECOM" },
                    @{ type = "text"; text = $valorFormatado },
                    @{ type = "text"; text = $vencimentoTexto }
                )
            },

            # BUTTON index 0: Copiar Chave Pix (order_details)
            @{
                type       = "button"
                sub_type   = "order_details"
                index      = 0
                parameters = @(
                    @{
                        type   = "action"
                        action = @{
                            order_details = @{
                                reference_id     = "NIOHUB-$(Get-Date -Format 'yyyyMMddHHmmss')"
                                type             = "digital-goods"
                                payment_type     = "br"
                                currency         = "BRL"
                                total_amount     = @{ value = $valorCentavos; offset = 100 }
                                payment_settings = @(
                                    @{
                                        type             = "pix_dynamic_code"
                                        pix_dynamic_code = @{
                                            merchant_name = $merchantName
                                            key           = $pixKey
                                            key_type      = $pixKeyType
                                            code          = $pixCode
                                        }
                                    },
                                    @{
                                        type   = "boleto"
                                        boleto = @{
                                            # Linha digitavel: apenas numeros, 47 ou 48 digitos
                                            digitable_line = ($linhaDigitavel -replace '[^0-9]', '')
                                        }
                                    }
                                )
                                order = @{
                                    status   = "pending"
                                    subtotal = @{ value = $valorCentavos; offset = 100 }
                                    tax      = @{ value = 0; offset = 100 }
                                    shipping = @{ value = 0; offset = 100 }
                                    discount = @{ value = 0; offset = 100 }
                                    items    = @(
                                        @{
                                            retailer_id = "fatura-internet"
                                            name        = "Fatura Internet"
                                            amount      = @{ value = $valorCentavos; offset = 100 }
                                            quantity    = 1
                                        }
                                    )
                                }
                            }
                        }
                    }
                )
            }
            # NOTA: O template cobranca_order so tem 1 botao (ORDER_DETAILS / PIX).
            # Para adicionar 'Copiar codigo de barras', crie um novo template na Meta
            # com sub_type copy_code no index 1 e aguarde aprovacao.
        )
    }
}

$bodyJson = $bodyObject | ConvertTo-Json -Depth 30

Write-Host ""
Write-Host "======= JSON =======" -ForegroundColor DarkGray
Write-Host $bodyJson
Write-Host "====================" -ForegroundColor DarkGray

# =============================================================
# PASSO 4: Enviar via API
# =============================================================
Write-Host ""
Write-Host "[4/4] Enviando mensagem de template..." -ForegroundColor Cyan

$apiUrl  = "https://graph.facebook.com/v23.0/$phoneNumberId/messages"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# Salvar JSON em arquivo temporário sem BOM (UTF-8 puro)
$tmpJsonPath = "$env:TEMP\whatsapp_payload.json"
[System.IO.File]::WriteAllText($tmpJsonPath, $bodyJson, (New-Object System.Text.UTF8Encoding($false)))

# Debug: Mostrar o que tem no arquivo
# Write-Host "DEBUG: Conteudo do arquivo JSON:" -ForegroundColor Gray
# Get-Content $tmpJsonPath | Write-Host -ForegroundColor Gray

# Disparar API via curl lendo do arquivo
$response = curl.exe --silent -X POST $apiUrl `
    -H "Authorization: Bearer $token" `
    -H "Content-Type: application/json" `
    --data-binary "@$tmpJsonPath"

Write-Host ""
if ($response -match '"id":') {
    Write-Host "====== SUCESSO ======" -ForegroundColor Green
    Write-Host $response
    Write-Host "====================" -ForegroundColor Green
    Write-Host "Mensagem enviada para $destino" -ForegroundColor Green
} else {
    Write-Host "ERRO ao enviar mensagem." -ForegroundColor Red
    Write-Host "Detalhe da Meta: $response" -ForegroundColor Red
}

# Limpar arquivo temporário
Remove-Item $tmpJsonPath -ErrorAction SilentlyContinue
