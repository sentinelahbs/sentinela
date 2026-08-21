# Empacotamento da box de detecção

Monta um pacote autocontido (Python embarcável + dependências +
código + modelo + NSSM) pra instalar numa loja sem precisar de Python
no PC do cliente. Ver a seção "Instalando numa loja" no README
principal do módulo para o que acontece do lado do cliente — este
README aqui é sobre **gerar** esse pacote.

## Pré-requisitos (na máquina que builda, não no PC do cliente)

- Windows (o pacote gerado só roda em Windows — NSSM e serviço do
  Windows são específicos da plataforma)
- PowerShell
- Uma instalação **completa** do Python 3.12.x (não embeddable) com
  tkinter — é dela que o `build.ps1` copia os arquivos de tkinter/Tcl/
  Tk que o Python embeddable não inclui por padrão. Vem por padrão no
  instalador oficial de python.org (marque a opção "tcl/tk and IDLE"
  se for uma instalação customizada).
- `models/yolox_s.onnx` e `openh264-*.dll` — o build baixa
  automaticamente se não existirem (mesmas fontes do README principal:
  releases do YOLOX e do Cisco OpenH264), mas dá pra baixar antes se
  preferir controlar a versão manualmente.

## Rodando

```powershell
cd edge-detection\packaging
.\build.ps1
```

Ou apontando explicitamente pra instalação completa do Python (se o
script não achar sozinha):

```powershell
.\build.ps1 -FullPythonDir "C:\Python312"
```

Resultado: `packaging\dist\vigia-box\` (pasta) e
`packaging\dist\vigia-box.zip` (o que se manda pro técnico que instala
na loja).

## Por que Python embeddable não vem com tkinter

A distribuição embeddable oficial é deliberadamente enxuta (sem GUI
toolkit, sem IDLE, sem testes) — pensada pra ser embutida dentro de
outros apps, não pra uso geral. Como `setup_wizard.py` usa `tkinter`
pra interface gráfica, o `build.ps1` enxerta manualmente os arquivos
(`_tkinter.pyd`, `tcl86t.dll`, `tk86t.dll`, o pacote `tkinter`, e as
bibliotecas de script `tcl8.6`/`tk8.6`) de uma instalação normal do
Python — solução documentada e conhecida pra esse cenário, não é
hack frágil. `Configurar.ps1` (dentro do pacote final) seta
`TCL_LIBRARY`/`TK_LIBRARY` apontando pros caminhos certos na hora de
rodar o assistente.

## O que fica de fora deste "empacotamento básico"

- **Atualização automática** — hoje, atualizar uma box já instalada
  significa substituir os arquivos manualmente (acesso remoto) e rodar
  `Instalar-Servico.ps1` de novo (reinstala o serviço, idempotente). Um
  mecanismo de self-update é um passo futuro — o heartbeat que o
  supervisor já manda pro backend é o gancho natural pra isso quando
  fizer sentido (mais lojas).
- **Instalador `.exe` polido** (Inno Setup) — por ora é uma pasta +
  scripts `.ps1`, suficiente pra um técnico instalando fisicamente.
- **Assinatura de código** — o Windows vai mostrar aviso de "editor
  desconhecido" ao rodar os `.ps1`/`nssm.exe`. Aceitável nesta fase.

## Testando o pacote gerado

Antes de mandar pra uma loja de verdade, vale rodar `Configurar.ps1` e
`Instalar-Servico.ps1` numa VM/PC de teste limpo (sem Python instalado)
pra confirmar que o bundle é realmente autocontido — é fácil o
enxerto do tkinter ou alguma dependência parecer certo na máquina de
build (que já tem Python completo) e mascarar um problema que só
aparece numa máquina realmente limpa.
