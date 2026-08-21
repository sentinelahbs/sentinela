<#
Para e remove o servico VigiaBox do Windows. Nao apaga box_config.json
nem os arquivos da box -- so desliga e desregistra o servico. Precisa
rodar como Administrador.
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ServiceName = "VigiaBox"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Este script precisa rodar como Administrador." -ForegroundColor Red
    Read-Host "Pressione Enter para fechar"
    exit 1
}

$nssm = "$PSScriptRoot\nssm.exe"
$existing = & $nssm status $ServiceName 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Servico '$ServiceName' nao esta instalado -- nada a fazer."
    Read-Host "Pressione Enter para fechar"
    exit 0
}

Write-Host "==> Parando e removendo servico '$ServiceName'"
& $nssm stop $ServiceName
& $nssm remove $ServiceName confirm

Write-Host "Servico removido. Os arquivos da box (incluindo box_config.json) continuam aqui." -ForegroundColor Green
Read-Host "Pressione Enter para fechar"
