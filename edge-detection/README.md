# Módulo de detecção (edge)

Esta é a parte que roda **dentro de cada loja**, numa box/mini-PC conectada
às câmeras. Ela não decide sozinha se algo é furto — ela apenas identifica
padrões de comportamento (mão parada perto de uma zona de interesse por
tempo prolongado) e envia um **alerta com clipe de vídeo** para o backend
central, que é o mesmo que alimenta o dashboard mostrado ao gestor.

A decisão final é sempre humana, feita no dashboard.

## Como as peças se encaixam

```
capture.py        → lê o stream RTSP da câmera, mantém buffer de pré-evento
detector.py        → detecta pessoas (YOLOv8 ou YOLOX) + posição das mãos (MediaPipe Pose)
pose_rules.py       → decide se o padrão observado é "suspeito" (heurística, não IA treinada)
tracker.py          → mantém identidade da pessoa entre frames da mesma câmera
correlator.py        → evita alerta duplicado quando a pessoa passa por câmeras vizinhas
clip_recorder.py    → grava o clipe (antes + depois do evento) e gera thumbnail
alert_client.py     → envia o evento pro backend (mesmo que alimenta o dashboard)
main.py             → orquestra tudo, um processo por câmera
config.py           → configuração por loja e por câmera (zona de interesse, thresholds)
setup_wizard.py      → assistente gráfico de instalação (ver seção abaixo)
supervisor.py         → sobe um processo por câmera e reinicia se algum cair (ver seção abaixo)
```

## Backend de detecção de pessoa: YOLOv8 vs YOLOX

O `detector.py` suporta dois backends, escolhidos pela variável de ambiente
`DETECTION_BACKEND`:

- **`yolov8`** (padrão) — Ultralytics YOLOv8. **Licença AGPL-3.0**: usar em
  produto comercial de código fechado exige uma Enterprise License paga da
  Ultralytics.
- **`yolox`** — YOLOX (Megvii), rodando via ONNX Runtime. **Licença Apache
  2.0**, sem essa exigência. Use este backend pra testar em loja parceira
  antes de resolver o licenciamento do YOLOv8.

```bash
# Windows (PowerShell)
$env:DETECTION_BACKEND = "yolox"
$env:DETECTION_MODEL_PATH = "./models/yolox_s.onnx"

# Linux/Mac
export DETECTION_BACKEND=yolox
export DETECTION_MODEL_PATH=./models/yolox_s.onnx
```

O modelo `.onnx` não fica versionado no repositório (arquivo grande, baixado
sob demanda). Baixe o `yolox_s.onnx` das releases oficiais do GitHub
(Megvii-BaseDetection/YOLOX → Releases → ONNX Model) e salve em
`edge-detection/models/yolox_s.onnx`.

## Por que regras, e não um modelo treinado do zero

Treinar um classificador de "comportamento suspeito" do zero exigiria um
dataset rotulado de furtos reais — difícil de conseguir e cheio de viés.
Em vez disso, usamos:

- **YOLOv8** pré-treinado (já sabe detectar "pessoa" — uma das classes padrão)
- **MediaPipe Pose** pré-treinado (já sabe estimar onde estão as mãos)
- Uma **regra explicável** por cima: mão parada dentro de uma zona configurada

Isso é o mesmo tipo de abordagem usada por soluções já validadas no mercado
(pose + heurística + zona de interesse), e tem a vantagem de ser calibrável
por câmera sem re-treinamento.

## Rodando localmente (teste com webcam)

Use **Python 3.12** (ou entre 3.9 e 3.12) — numpy/mediapipe/onnxruntime ainda
não têm pacote pronto pra versões mais novas do Python, e instalar do zero
exige compilador C, que normalmente não está disponível. Recomendado usar
um ambiente virtual dedicado:

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/Mac
```

Para testar sem uma câmera IP real, use a variável `CAMERA_SOURCE` pra
apontar pro índice da sua webcam, e as variáveis `STORE_*` pra mandar o
alerta pro backend de verdade (senão usa o placeholder de exemplo):

```bash
# Windows (PowerShell)
$env:CAMERA_SOURCE = "0"
$env:STORE_API_BASE_URL = "https://sua-api.com.br"
$env:STORE_ID = "id-da-loja"
$env:STORE_API_KEY = "chave-da-loja"

python main.py
```

Os clipes gerados ficam em `./clips`. Se o `api_base_url` não estiver
acessível, o envio falha de forma segura (loga o erro) — o clipe local
continua existindo.

### Codec do clipe (H.264 via OpenH264)

O clipe é gravado em H.264 (`avc1`) — é o único codec que os navegadores
(Chrome, Safari, Edge) reproduzem nativamente no `<video>` do dashboard.
O pip `opencv-python` não vem com esse codec embutido (é separado por
licenciamento); é preciso baixar a lib da Cisco e colocar na pasta
`edge-detection/` (mesma pasta de onde `main.py` roda):

```bash
curl -L -o openh264-1.8.0-win64.dll.bz2 https://github.com/cisco/openh264/releases/download/v1.8.0/openh264-1.8.0-win64.dll.bz2
python -c "import bz2; open('openh264-1.8.0-win64.dll','wb').write(bz2.decompress(open('openh264-1.8.0-win64.dll.bz2','rb').read()))"
```

Sem essa lib, o clipe ainda é gravado (com outro codec, `mp4v`) e sobe
normalmente pro backend, mas **não toca no navegador** — só percebe o
problema ao tentar assistir. A versão da lib importa: precisa bater
exatamente com a que o FFmpeg embutido no OpenCV está pedindo (aparece
no erro do terminal se a versão errada for baixada).

## Já testado

- Fluxo completo testado de ponta a ponta com webcam real (não só RTSP
  simulado): alerta disparou, clipe gravado (pré + pós evento) e recebido
  pelo backend, sem travar o processo. Calibração de frames-parados
  ajustada para o hardware sem GPU usado no teste (ver
  `edge_detection_calibration` na memória do projeto — precisa recalibrar
  quando o hardware real da loja for escolhido, já que fps varia por
  máquina)

## Instalando numa loja (assistente de configuração)

Pra quem está instalando não precisar editar variável de ambiente nem
abrir terminal, existe um assistente gráfico:

```bash
python setup_wizard.py
```

Ele pede, em 3 passos: (1) a chave da loja (mostrada no dashboard ao
cadastrar a loja — resolve o store_id sozinho, via `GET /v1/edge/whoami`),
(2) os dados do DVR (IP, usuário, senha), e (3) uma ou mais câmeras — cole
o ID de cada uma (copiado da aba "Câmeras" do dashboard, onde elas
precisam ser cadastradas ANTES de rodar o assistente) e o canal
correspondente no DVR. Tem um botão "Testar conexões" que confirma se dá
pra abrir o stream de cada câmera antes de salvar.

O resultado é `box_config.json` (nunca commitado — tem senha do DVR e
chave da loja em texto puro, ver `.gitignore`), que `main.py` carrega
automaticamente se existir (`config.ACTIVE_STORE`), sem precisar de
nenhuma variável de ambiente. Rodando sem o assistente (`CAMERA_SOURCE`,
`STORE_*` etc. por env var, como antes), continua funcionando igual —
o assistente é aditivo, não obrigatório.

Cada processo `main.py` roda uma câmera só — `CAMERA_INDEX` (padrão `0`)
escolhe qual câmera de `box_config.json` esse processo em particular
representa. Pra rodar manualmente mais de uma câmera ao mesmo tempo sem
o supervisor (ex: depurando uma câmera específica), um processo por
índice:

```bash
$env:CAMERA_INDEX = "1"   # roda a segunda câmera do box_config.json
python main.py
```

Em uso normal, é o `supervisor.py` (ver seção abaixo) quem faz isso
automaticamente pra todas as câmeras da loja.

## Rodando todas as câmeras da loja (supervisor.py)

```bash
python supervisor.py
```

Sobe um processo `main.py` por câmera de `ACTIVE_STORE` (uma pra cada
entrada de `box_config.json`), monitora cada um, e reinicia
automaticamente com backoff exponencial (1s, 2s, 4s... até 60s) se
algum cair — sem desistir permanentemente de nenhuma câmera, mesmo que
ela fique caindo repetidamente (mesma filosofia da reconexão de stream
em `capture.py`). Se uma câmera ficar 5 minutos rodando sem cair, o
backoff dela reseta — não trata uma queda isolada depois de horas
saudáveis como se fizesse parte de uma sequência de falhas.

O heartbeat da loja (ping periódico pro backend saber que a box está
online) roda **uma vez só aqui**, nunca dentro de cada processo de
câmera — os processos filhos sabem que estão sob supervisão pela
variável `VIGIA_SUPERVISED` (setada automaticamente) e não sobem o
próprio heartbeat, senão a loja mandaria um ping duplicado por câmera.

Cada câmera grava seu próprio log em `./logs/camera_N.log` (não
versionado, ver `.gitignore`) — inclui o traceback real se o processo
cair, útil pra descobrir qual câmera especificamente está com problema
sem precisar abrir N janelas de terminal.

Testado rodando de verdade por 90s com 2 câmeras apontando pra um DVR
inexistente: as duas subiram juntas, travaram (~36s até o FFmpeg
desistir da conexão RTSP — comportamento do próprio FFmpeg, não do
supervisor), caíram, foram reiniciadas com backoff crescente (2s → 4s),
e o heartbeat central nunca duplicou. Encerramento gracioso
(`terminate()`) testado separadamente com uma câmera de verdade
(webcam) rodando — confirma que o processo filho encerra e não fica
órfão. O caminho de Ctrl+C→`KeyboardInterrupt` em si (que só chama esse
mesmo `terminate()` pra cada câmera) não foi testado com um Ctrl+C real
de terminal, só a lógica de encerramento que ele aciona.

## Compatibilidade com CFTV/DVR (Intelbras)

Ver [`COMPATIBILIDADE_CAMERAS.md`](./COMPATIBILIDADE_CAMERAS.md) — cobre
o formato de URL RTSP de DVR/NVR Intelbras (analógico via coaxial e IP,
ambos suportados do mesmo jeito), transporte TCP forçado, reconexão
automática em queda de stream, e o que ainda falta testar contra
hardware real.

## O que falta para produção (próximos passos)

- **Testar contra um DVR/NVR Intelbras real** — tudo em
  `COMPATIBILIDADE_CAMERAS.md` foi implementado e testado com mocks, mas
  nunca rodou contra o equipamento de verdade.
- Empacotamento pra instalação sem Python (Python embarcável + serviço
  do Windows via NSSM, ver decisão registrada na conversa do projeto) —
  o assistente e o supervisor hoje ainda precisam do ambiente Python já
  configurado pra rodar. NSSM entra aqui pra rodar `supervisor.py` como
  serviço do Windows (inicia sozinho com o PC, sem terminal aberto).
- Fila local (ex: SQLite) para reenviar alertas se a internet cair — hoje
  uma falha de rede na hora de enviar o alerta só loga o erro, o clipe
  fica local mas não há retry automático depois.
- Documentar a instalação no hardware real da loja (mini-PC) — testado só
  em notebook/webcam até agora.

### Já resolvido (não é mais pendência)

- ~~Tracker de pessoa real entre frames~~ — `tracker.py` (IOU + fallback
  por distância de centro), com identidade estável entre frames da mesma
  câmera.
- ~~Reconexão automática de stream~~ — `capture.py` recria a conexão do
  zero após falhas seguidas, com backoff exponencial (ver
  `COMPATIBILIDADE_CAMERAS.md`).
- ~~Fluxo de cadastro de câmera por loja~~ — aba "Câmeras" no dashboard,
  `camera_id` real enviado e validado pelo backend.
- ~~Assistente de configuração gráfico~~ — `setup_wizard.py`, ver seção
  "Instalando numa loja" acima. Testado de ponta a ponta contra
  produção (chave real, câmera real, e os dois caminhos de erro).
- ~~Processo supervisor multi-câmera~~ — `supervisor.py`, ver seção
  acima. Testado rodando de verdade (crash + reinício com backoff,
  heartbeat centralizado, encerramento gracioso sem processo órfão).
