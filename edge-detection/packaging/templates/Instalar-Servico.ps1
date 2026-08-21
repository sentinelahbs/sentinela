<#
Registra o supervisor.py como servico do Windows (via NSSM) -- sobe
sozinho com o PC, sem precisar de terminal aberto, e reinicia se cair.

Precisa rodar como Administrador (clique com o botao direito ->
"Executar com PowerShell" abrindo como admin, ou "Executar como
administrador" se aparecer a opcao). Rode Configurar.ps1 primeiro.
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ServiceName = "VigiaBox"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Este script precisa rodar como Administrador (registrar um servico do Windows exige isso)." -ForegroundColor Red
    Write-Host "Feche esta janela, clique com o botao direito em Instalar-Servico.ps1 e escolha 'Executar como administrador'."
    Read-Host "Pressione Enter para fechar"
    exit 1
}

if (-not (Test-Path "$PSScriptRoot\box_config.json")) {
    Write-Host "Nao achei box_config.json -- rode Configurar.ps1 primeiro." -ForegroundColor Red
    Read-Host "Pressione Enter para fechar"
    exit 1
}

$nssm = "$PSScriptRoot\nssm.exe"
$pythonExe = "$PSScriptRoot\python\python.exe"
$supervisorScript = "$PSScriptRoot\supervisor.py"
$logsDir = "$PSScriptRoot\logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

# Reinstalacao idempotente: se o servico ja existe (ex: reaplicando
# depois de atualizar os arquivos manualmente), para e remove antes de
# recriar -- evita erro "servico ja existe" e garante que o registro
# reflete os caminhos/config atuais.
$existing = & $nssm status $ServiceName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "==> Servico '$ServiceName' ja existe, removendo antes de recriar"
    & $nssm stop $ServiceName
    & $nssm remove $ServiceName confirm
}

Write-Host "==> Registrando servico '$ServiceName'"
& $nssm install $ServiceName $pythonExe $supervisorScript
& $nssm set $ServiceName AppDirectory $PSScriptRoot
& $nssm set $ServiceName Start SERVICE_AUTO_START
& $nssm set $ServiceName AppStdout "$logsDir\service.log"
& $nssm set $ServiceName AppStderr "$logsDir\service.log"
& $nssm set $ServiceName AppRotateFiles 1
& $nssm set $ServiceName AppRotateBytes 10485760
# Reinicia sozinho se o processo supervisor.py cair inteiro (raro --
# ele ja trata queda de camera individual internamente, com backoff).
& $nssm set $ServiceName AppExit Default Restart
& $nssm set $ServiceName AppRestartDelay 5000

Write-Host "==> Iniciando servico"
& $nssm start $ServiceName

Start-Sleep -Seconds 3
$status = & $nssm status $ServiceName
Write-Host ""
Write-Host "Status do servico: $status"
if ($status -match "RUNNING") {
    Write-Host "Instalado e rodando. A box vai iniciar sozinha a cada reinicio do PC." -ForegroundColor Green
} else {
    Write-Host "Servico registrado mas nao esta RUNNING -- confira $logsDir\service.log" -ForegroundColor Yellow
}
Read-Host "Pressione Enter para fechar"
