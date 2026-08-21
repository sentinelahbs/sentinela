<#
Abre o assistente grafico de configuracao da box (setup_wizard.py).
Roda uma vez, antes de Instalar-Servico.ps1 -- gera o box_config.json
com a chave da loja, dados do DVR e as cameras.

Clique com o botao direito neste arquivo -> "Executar com PowerShell",
ou abra um PowerShell nesta pasta e rode: .\Configurar.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# O Python embarcado nao tem tcl/tk no lugar padrao (foram enxertados
# em python\tcl\tcl8.6 e python\tcl\tk8.6 pelo build.ps1) -- sem essas
# duas variaveis, a tela do assistente nao abre (erro "Can't find a
# usable init.tcl").
$env:TCL_LIBRARY = Join-Path $PSScriptRoot "python\tcl\tcl8.6"
$env:TK_LIBRARY = Join-Path $PSScriptRoot "python\tcl\tk8.6"

& "$PSScriptRoot\python\python.exe" "$PSScriptRoot\setup_wizard.py"

Write-Host ""
if (Test-Path "$PSScriptRoot\box_config.json") {
    Write-Host "Configuracao salva. Proximo passo: rode Instalar-Servico.ps1 (como Administrador)." -ForegroundColor Green
} else {
    Write-Host "Nenhum box_config.json foi gerado -- o assistente foi fechado sem salvar?" -ForegroundColor Yellow
}
Read-Host "Pressione Enter para fechar"
