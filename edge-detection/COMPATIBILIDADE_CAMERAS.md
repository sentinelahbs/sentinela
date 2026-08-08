# Compatibilidade de câmeras — DVR/NVR Intelbras e RTSP em geral

Este arquivo não existia antes — foi criado depois de um diagnóstico do
código atual (`capture.py`, `config.py`) contra o público-alvo real do
VigIA: minimercados com sistema de CFTV já instalado, tipicamente
Intelbras, não câmeras Wi-Fi avulsas de consumo.

## Resumo

- **Analógico (via DVR, cabo coaxial) e IP são suportados da mesma
  forma**, porque o código nunca fala com "a câmera" diretamente — fala
  com o servidor RTSP do DVR/NVR, que expõe cada canal (analógico ou IP,
  tanto faz) como um stream RTSP independente.
- **Transporte RTSP forçado em TCP** (era UDP, o padrão do FFmpeg) —
  evita o problema mais comum de stream travando/nunca conectando atrás
  de NAT/roteador típico de loja.
- **Reconexão real implementada** — antes, uma queda de stream travava a
  câmera pro resto da execução (só ficava tentando ler de uma conexão
  morta). Agora recria a conexão do zero com backoff exponencial.
- **Sub-stream (`subtype=1`) como padrão** — o stream principal do DVR
  custa decodificação de CPU que a box não tem sobrando.
- **Ainda não testado contra hardware Intelbras real** — tudo abaixo foi
  implementado e testado com dados sintéticos/mocks, e a captura por
  webcam local foi testada com pessoa real. RTSP contra um DVR/NVR de
  verdade nunca rodou nesta base de código. Fica pendente pra quando
  houver acesso a um equipamento real.

## Formato de URL — Intelbras / Dahua

A maioria dos DVRs, NVRs e câmeras IP Intelbras roda firmware derivado
da Dahua, e usa este esquema de URL RTSP:

```
rtsp://USUARIO:SENHA@IP_DO_DVR:554/cam/realmonitor?channel=N&subtype=S
```

- `channel=N` — número do canal no DVR (1, 2, 3...). Cada câmera ligada
  ao DVR, seja analógica via coaxial ou IP, aparece como um canal
  independente aqui. **Isso é o que faz uma central de 5, 10, 15+
  câmeras funcionar com o código atual sem nenhuma mudança**: cada
  `CameraConfig` da loja aponta pro mesmo IP do DVR, mudando só o
  `channel`.
- `subtype=S` — `0` é o stream principal (alta resolução, bitrate alto),
  `1` é o sub-stream (resolução mais baixa). **Use sempre `1`** pra
  detecção — é o padrão da função `build_intelbras_rtsp_url()` em
  `config.py`. O stream principal só faz sentido se algum dia precisarmos
  de qualidade alta pra outra finalidade (ex: revisão manual em alta
  definição), não pra rodar YOLO+MediaPipe numa box sem GPU.
- Porta `554` é o padrão RTSP — normalmente não muda, mas alguns DVRs
  permitem reconfigurar.

Câmeras IP Intelbras standalone (linha VIP), fora de um NVR, geralmente
usam o mesmo esquema de URL — mas modelos ONVIF-only ou linhas mais
antigas podem variar; confirme no manual do modelo específico se a URL
acima não conectar.

### Helper pra montar a URL

```python
from config import build_intelbras_rtsp_url

url = build_intelbras_rtsp_url(
    host="192.168.1.100",
    username="admin",
    password="sua_senha",
    channel=3,           # canal 3 do DVR
)
# rtsp://admin:sua_senha@192.168.1.100:554/cam/realmonitor?channel=3&subtype=1
```

Passe `main_stream=True` só se precisar do stream principal por algum
motivo específico — não recomendado pra detecção.

## O que mudou no código

### 1. Transporte RTSP forçado em TCP (`capture.py`)

RTSP sobre UDP (comportamento padrão do FFmpeg/OpenCV) é a causa mais
comum de stream travando ou nunca conectando atrás de NAT/roteador
doméstico ou de pequena empresa — problema conhecido de qualquer
integração OpenCV+RTSP, não específico da Intelbras. Agora, antes de
abrir qualquer stream que não seja webcam local, o código seta:

```python
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
```

Isso precisa ser setado *antes* de criar o `cv2.VideoCapture` — é assim
que o backend FFmpeg do OpenCV lê essa opção (não existe parâmetro
direto na API Python pra isso).

### 2. Reconexão real (`capture.py`)

Antes: quando `cap.read()` falhava, o código só esperava 1s e tentava
ler de novo *no mesmo objeto* `VideoCapture`. Isso nunca recupera uma
sessão RTSP derrubada de verdade (a conexão TCP já morreu — ler de novo
só volta `False` pra sempre). Pra webcam USB isso quase não importava
(o driver às vezes se recupera sozinho); pra RTSP numa rede de loja
real, era um travamento permanente até reiniciar o processo manualmente.

Agora: depois de `RollingCapture.RECONNECT_AFTER_FAILURES` (10) leituras
falhas seguidas, a conexão é fechada (`release()`) e recriada do zero. Se
a reconexão em si falhar (DVR fora do ar, rede caída), tenta de novo com
backoff exponencial (1s, 2s, 4s... até `MAX_BACKOFF_SECONDS`, 30s) — não
fica batendo no DVR a cada segundo indefinidamente.

Testado com mocks simulando: falha temporária seguida de reconexão bem
sucedida, e reconexão que falha algumas vezes antes de dar certo
(backoff crescendo corretamente nos dois casos).

### 3. Exemplo de configuração corrigido (`config.py`)

O exemplo anterior (`rtsp://usuario:senha@192.168.0.50:554/stream1`) era
um placeholder genérico que não bate com nenhum DVR/câmera Intelbras
real — quem fosse configurar uma box de verdade se guiaria por um
formato errado. Agora o `EXAMPLE_STORE` usa `build_intelbras_rtsp_url()`
como exemplo, já no formato correto.

### 4. Sub-stream por padrão

`build_intelbras_rtsp_url()` usa `subtype=1` a menos que
`main_stream=True` seja passado explicitamente — decisão de propósito
pra proteger o orçamento de CPU já apertado da box (ver `detector.py`:
~1-1.5 frame/s sem GPU).

## O que ainda não está resolvido / precisa de teste com hardware real

- **Nunca testado contra um DVR/NVR Intelbras de verdade.** Tudo acima é
  implementação + teste com mocks/webcam — não substitui testar contra o
  equipamento real.
- **Limite de conexões RTSP simultâneas por canal** — varia por modelo
  de DVR, não verificado. Se a loja tiver várias câmeras no mesmo DVR e
  cada uma virar um processo próprio (ver seção "múltiplos processos" no
  README), pode esbarrar num limite do equipamento — não sabemos qual é
  até testar.
- **Processo único por loja ainda não existe** — `main.py` continua MVP
  de uma câmera só (`EXAMPLE_STORE.cameras[0]`). Um DVR real, por
  definição, significa várias câmeras desde o primeiro dia — falta o
  supervisor que sobe um processo por canal.
- **Credenciais/porta não-padrão** — alguns DVRs permitem trocar a porta
  RTSP do padrão 554, ou têm particularidades de autenticação por
  firmware/modelo. `build_intelbras_rtsp_url()` cobre o caso comum, mas
  não é garantia universal pra toda a linha Intelbras.
