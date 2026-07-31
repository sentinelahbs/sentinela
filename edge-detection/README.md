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
clip_recorder.py    → grava o clipe (antes + depois do evento) e gera thumbnail
alert_client.py     → envia o evento pro backend (mesmo que alimenta o dashboard)
main.py             → orquestra tudo, um processo por câmera
config.py           → configuração por loja e por câmera (zona de interesse, thresholds)
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

## O que falta para produção (próximos passos)

- Tracker de pessoa real entre frames (ex: ByteTrack), em vez do índice
  simples usado aqui — importante pra loja com mais de uma pessoa no quadro
- Fila local (ex: SQLite) para reenviar alertas se a internet cair
- Um processo supervisor que reinicia a câmera automaticamente se o stream
  RTSP cair
- Fluxo de cadastro de câmera por loja no dashboard (a tabela `cameras`
  existe no backend, mas ainda não tem tela — por isso `camera_id` não é
  enviado pelo alert_client hoje)
