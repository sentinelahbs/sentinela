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
detector.py        → detecta pessoas (YOLOv8) + posição das mãos (MediaPipe Pose)
pose_rules.py       → decide se o padrão observado é "suspeito" (heurística, não IA treinada)
clip_recorder.py    → grava o clipe (antes + depois do evento) e gera thumbnail
alert_client.py     → envia o evento pro backend (mesmo que alimenta o dashboard)
main.py             → orquestra tudo, um processo por câmera
config.py           → configuração por loja e por câmera (zona de interesse, thresholds)
```

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

```bash
pip install -r requirements.txt
```

Para testar sem uma câmera IP real, edite `config.py` e troque o `source`
da câmera de exemplo pelo índice da sua webcam:

```python
source="0"  # webcam padrão do notebook
```

Depois:

```bash
python main.py
```

Os clipes gerados ficam em `./clips`. Se o `api_base_url` não estiver
acessível, o envio falha de forma segura (loga o erro) — o clipe local
continua existindo.

## O que falta para produção (próximos passos)

- Tracker de pessoa real entre frames (ex: ByteTrack), em vez do índice
  simples usado aqui — importante pra loja com mais de uma pessoa no quadro
- Fila local (ex: SQLite) para reenviar alertas se a internet cair
- Um processo supervisor que reinicia a câmera automaticamente se o stream
  RTSP cair
- Endpoint real no backend (`POST /v1/stores/{id}/alerts`) recebendo esses
  eventos e persistindo pro dashboard já construído
