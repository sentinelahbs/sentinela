<#
.SYNOPSIS
Monta o pacote instalavel da box de deteccao: Python embarcavel (com
todas as dependencias e o tkinter enxertado) + codigo-fonte + modelo
YOLOX + NSSM, pronto pra copiar pro PC do cliente sem precisar de
Python instalado la.

Roda UMA VEZ no ambiente de build (aqui), nao no PC da loja. O
resultado e uma pasta (e um .zip) em packaging\dist\vigia-box.

.PARAMETER PythonVersion
Versao exata do Python embeddable a baixar (precisa ter wheel pronta
pra opencv/ultralytics/onnxruntime/mediapipe, ver README do modulo).

.PARAMETER FullPythonDir
Pasta de uma instalacao COMPLETA do Python (mesma versao major.minor)
de onde tkinter/tcl/tk sao copiados -- o embeddable nao inclui isso.
Por padrao tenta achar automaticamente.

.PARAMETER OutputDir
Pasta onde o bundle e' montado ANTES de virar zip. Por padrao fica
perto da raiz do disco (nao dentro do repositorio) de proposito: o
torch (dependencia do ultralytics) empacota arquivos de licenca com
caminho MUITO profundo (dist-info\licenses\third_party\kineto\
libkineto\...\cJSON) -- combinado com um caminho de base ja longo tipo
"C:\Users\Fulano\Downloads\sentinela\edge-detection\packaging\dist\...",
estoura o limite de 260 caracteres do Windows (MAX_PATH) durante o pip
install, e o build quebra com "WinError 206: nome do arquivo ou
extensao muito grande". Um caminho de base curto evita isso sem
precisar mexer em LongPathsEnabled (config de sistema, fora do escopo
deste script).
#>
param(
    [string]$PythonVersion = "3.12.10",
    [string]$NssmVersion = "2.24",
    [string]$FullPythonDir = "",
    [string]$OutputDir = "C:\vigia-build"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$bundleDir = Join-Path $OutputDir "vigia-box"
$pyDir = Join-Path $bundleDir "python"
$downloadsDir = Join-Path $OutputDir "_downloads"
$finalZipDir = Join-Path $PSScriptRoot "dist"

Write-Host "==> Limpando saida anterior ($bundleDir)"
if (Test-Path $bundleDir) { Remove-Item $bundleDir -Recurse -Force }
New-Item -ItemType Directory -Path $pyDir -Force | Out-Null
New-Item -ItemType Directory -Path $downloadsDir -Force | Out-Null

# --- 1. Python embeddable ---------------------------------------------
Write-Host "==> Baixando Python $PythonVersion embeddable"
$embedZip = Join-Path $downloadsDir "python-embed.zip"
if (-not (Test-Path $embedZip)) {
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $embedZip
}
Expand-Archive -Path $embedZip -DestinationPath $pyDir -Force

# Layout do embeddable e' tudo solto na raiz (python.exe, DLLs, e a
# stdlib comprimida em pythonXXX.zip) -- "." ja e' um caminho de busca
# no ._pth por padrao, entao qualquer pacote solto colocado direto
# aqui vira importavel sem editar mais nada alem do "import site".
$pthFile = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
Write-Host "==> Habilitando site-packages em $($pthFile.Name)"
(Get-Content $pthFile.FullName) -replace '^#\s*import site', 'import site' | Set-Content $pthFile.FullName

# --- 2. pip ------------------------------------------------------------
Write-Host "==> Bootstrap do pip"
$getPip = Join-Path $downloadsDir "get-pip.py"
if (-not (Test-Path $getPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
}
& "$pyDir\python.exe" $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip.py falhou" }

# --- 3. dependencias do requirements.txt --------------------------------
Write-Host "==> Instalando dependencias (pode demorar -- opencv/ultralytics/onnxruntime/mediapipe sao pesados)"
& "$pyDir\python.exe" -m pip install --no-warn-script-location -r "$repoRoot\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt falhou" }

# --- 4. enxerto do tkinter (setup_wizard.py precisa, embeddable nao inclui) ---
if (-not $FullPythonDir) {
    $found = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($found) { $FullPythonDir = Split-Path $found.Source -Parent }
}
if (-not $FullPythonDir -or -not (Test-Path "$FullPythonDir\DLLs\_tkinter.pyd")) {
    throw ("Nao achei uma instalacao completa do Python com tkinter " +
           "(procurei em '$FullPythonDir'). Passe -FullPythonDir apontando " +
           "pra uma instalacao normal do Python $PythonVersion (nao embeddable) " +
           "com tkinter -- vem por padrao no instalador oficial python.org.")
}
Write-Host "==> Enxertando tkinter de $FullPythonDir"
Copy-Item "$FullPythonDir\DLLs\_tkinter.pyd" $pyDir
Copy-Item "$FullPythonDir\DLLs\tcl86t.dll" $pyDir
Copy-Item "$FullPythonDir\DLLs\tk86t.dll" $pyDir
# tcl86t.dll depende de zlib1.dll dinamicamente -- o embeddable nao
# inclui essa DLL solta (o zlib do stdlib vem estatico dentro do
# python312.dll), entao sem copiar isso manualmente o _tkinter.pyd
# falha ao carregar com "DLL load failed" (erro generico do Windows,
# nao aponta qual dependencia faltou -- descoberto comparando a pasta
# DLLs da instalacao completa com o que tinha sido copiado aqui).
Copy-Item "$FullPythonDir\DLLs\zlib1.dll" $pyDir
Copy-Item "$FullPythonDir\Lib\tkinter" (Join-Path $pyDir "tkinter") -Recurse
# Scripts .tcl/.tk em si (nao sao codigo Python, tcl86t.dll os procura
# via TCL_LIBRARY/TK_LIBRARY -- ver essas env vars em Configurar.ps1,
# apontando pra exatamente esses dois caminhos). tcl8.6 e tk8.6 sao
# pastas IRMAS dentro de "tcl\" na instalacao completa, tk8.6 nao fica
# aninhado dentro de tcl8.6 (confirmado inspecionando a instalacao real).
$tclDir = Join-Path $pyDir "tcl"
New-Item -ItemType Directory -Path $tclDir -Force | Out-Null
Copy-Item "$FullPythonDir\tcl\tcl8.6" (Join-Path $tclDir "tcl8.6") -Recurse
Copy-Item "$FullPythonDir\tcl\tk8.6" (Join-Path $tclDir "tk8.6") -Recurse

# --- 5. codigo-fonte, modelo, codec ------------------------------------
Write-Host "==> Copiando codigo-fonte do modulo de deteccao"
Get-ChildItem "$repoRoot\*.py" | Copy-Item -Destination $bundleDir

# Guarda de licenciamento: ate a licenca Enterprise da Ultralytics estar
# assinada, YOLOv8 (AGPL-3.0) nao pode ser o backend padrao de nenhum
# pacote que sai daqui -- ver README do modulo. Isso NAO confia so no
# default de detector.py: confere o arquivo de fato copiado pro bundle,
# entao mesmo uma reversao acidental desse default e' pega aqui, antes
# do zip sair da maquina de build.
Write-Host "==> Conferindo guarda de licenciamento (DETECTION_BACKEND default)"
$detectorCopy = Join-Path $bundleDir "detector.py"
if ((Get-Content $detectorCopy -Raw) -notmatch 'DETECTION_BACKEND"\s*,\s*"yolox"') {
    throw ("detector.py copiado pro bundle nao tem 'yolox' como default de " +
           "DETECTION_BACKEND -- build abortado pra nao empacotar YOLOv8 " +
           "(AGPL-3.0) sem a licenca Enterprise da Ultralytics assinada. " +
           "Ver README do modulo (secao de licenciamento) antes de mudar isso.")
}

$modelsDir = Join-Path $bundleDir "models"
New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
$onnxModel = "$repoRoot\models\yolox_s.onnx"
if (-not (Test-Path $onnxModel)) {
    throw ("Modelo YOLOX nao encontrado em '$onnxModel' -- baixe manualmente " +
           "das releases oficiais (Megvii-BaseDetection/YOLOX -> Releases -> " +
           "ONNX Model) antes de rodar o build, ver README do modulo.")
}
Copy-Item $onnxModel $modelsDir

$openh264 = Get-ChildItem "$repoRoot\openh264*.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $openh264) {
    Write-Host "==> Baixando OpenH264 (codec H.264 pro clipe)"
    $openh264Bz2 = Join-Path $downloadsDir "openh264-1.8.0-win64.dll.bz2"
    Invoke-WebRequest -Uri "https://github.com/cisco/openh264/releases/download/v1.8.0/openh264-1.8.0-win64.dll.bz2" -OutFile $openh264Bz2
    & "$pyDir\python.exe" -c "import bz2,shutil; shutil.copyfileobj(bz2.BZ2File(r'$openh264Bz2'), open(r'$bundleDir\openh264-1.8.0-win64.dll', 'wb'))"
} else {
    Copy-Item $openh264.FullName $bundleDir
}

# --- 6. NSSM (roda o supervisor.py como servico do Windows) ------------
Write-Host "==> Baixando NSSM $NssmVersion"
$nssmZip = Join-Path $downloadsDir "nssm.zip"
if (-not (Test-Path $nssmZip)) {
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-$NssmVersion.zip" -OutFile $nssmZip
}
$nssmExtract = Join-Path $downloadsDir "nssm-extract"
Expand-Archive -Path $nssmZip -DestinationPath $nssmExtract -Force
Copy-Item "$nssmExtract\nssm-$NssmVersion\win64\nssm.exe" $bundleDir

# --- 7. scripts de instalacao (rodam no PC do cliente) ------------------
Write-Host "==> Copiando scripts de instalacao"
Copy-Item "$PSScriptRoot\templates\Configurar.ps1" $bundleDir
Copy-Item "$PSScriptRoot\templates\Instalar-Servico.ps1" $bundleDir
Copy-Item "$PSScriptRoot\templates\Desinstalar-Servico.ps1" $bundleDir
Copy-Item "$PSScriptRoot\templates\LEIA-ME.txt" $bundleDir

# --- 8. zip final --------------------------------------------------------
# O zip em si fica dentro do repo (packaging\dist) pra ficar facil de
# achar -- mas a PASTA de origem (com os caminhos profundos do torch)
# continua em $OutputDir (curto), nao e' movida. Um .zip e' um arquivo
# so, sem o problema de MAX_PATH; a pasta profunda so precisa existir
# temporariamente ali pra ser lida durante a compactacao.
New-Item -ItemType Directory -Path $finalZipDir -Force | Out-Null
$zipPath = Join-Path $finalZipDir "vigia-box.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath }
Write-Host "==> Compactando pacote final em $zipPath"
Compress-Archive -Path $bundleDir -DestinationPath $zipPath

Write-Host ""
Write-Host "==> Pronto: $zipPath"
Write-Host "    Pasta de origem (caminho curto, pode apagar depois): $bundleDir"
