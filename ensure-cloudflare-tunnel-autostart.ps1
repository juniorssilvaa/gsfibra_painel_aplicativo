# Garante que o tunel Cloudflare suba sozinho no logon do Windows.
# Nao precisa de Administrador (tarefa do usuario atual + processo user-mode).
# Usa config.yml (chat.niohub.com.br -> localhost:8012, api-local -> 8011, etc.).

$ErrorActionPreference = 'Stop'

$taskName = 'NioHub Cloudflare Tunnel'
$watchName = 'NioHub Cloudflare Tunnel Watchdog'
$repoScript = 'E:\niohub\start-cloudflare-tunnel-user.ps1'
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if (-not (Test-Path $repoScript)) {
    throw "Script nao encontrado: $repoScript"
}

# 1) Inicia o tunel agora (se ainda nao estiver rodando)
& $psExe -NoProfile -ExecutionPolicy Bypass -File $repoScript

$action = New-ScheduledTaskAction `
    -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$repoScript`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# 2) No logon
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $triggerLogon `
    -Settings $settings `
    -Principal $principal `
    -Description 'Sobe o Cloudflare Tunnel no logon (chat.niohub.com.br / api-local).' `
    -Force | Out-Null

# 3) Watchdog a cada 5 minutos
$existingWatch = Get-ScheduledTask -TaskName $watchName -ErrorAction SilentlyContinue
if ($existingWatch) {
    Unregister-ScheduledTask -TaskName $watchName -Confirm:$false
}

# Repetition via XML e mais confiavel no Windows
$startAt = (Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:ss')
$watchXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Watchdog: se o cloudflared cair, sobe de novo a cada 5 minutos.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$startAt</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$env:USERDOMAIN\$env:USERNAME</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$psExe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$repoScript"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

Register-ScheduledTask -TaskName $watchName -Xml $watchXml -Force | Out-Null

Write-Host "OK: tunel iniciado e auto-start configurado." -ForegroundColor Green
Write-Host "  Tarefas: '$taskName' (logon) + '$watchName' (a cada 5 min)" -ForegroundColor Cyan
Write-Host "  chat.niohub.com.br -> http://localhost:8012" -ForegroundColor Cyan
Write-Host "  api-local.niohub.com.br -> http://localhost:8011" -ForegroundColor Cyan
