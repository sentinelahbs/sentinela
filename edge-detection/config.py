"""
Configuração do módulo de detecção (roda na "box" instalada em cada loja).

Ideia geral: cada câmera tem sua própria configuração de zona de interesse
(ex: perto de uma prateleira) e seus próprios thresholds. Isso evita ter
uma regra genérica "uma pra todas as câmeras", que na prática gera
excesso de falso positivo.
"""

import json
import os
from dataclasses import dataclass, field


def _parse_zone_of_interest(raw: str) -> list:
    """Formato esperado: JSON de lista de pares [x,y] normalizados (0-1),
    ex: '[[0.1,0.35],[0.9,0.35],[0.9,0.98],[0.1,0.98]]'. String vazia ou
    ausente = sem zona configurada (zona vira o quadro inteiro, ver
    SuspiciousBehaviorRule._in_zone em pose_rules.py)."""
    if not raw:
        return []
    return [tuple(point) for point in json.loads(raw)]


def _parse_exclusion_zones(raw: str) -> list:
    """Formato esperado: JSON de lista de zonas, cada uma no mesmo formato
    de _parse_zone_of_interest -- ex: '[[[0.1,0.6],[0.3,0.6],[0.3,0.9],
    [0.1,0.9]]]' (uma zona excluída) ou com mais de uma zona na lista.
    String vazia ou ausente = nenhuma exclusão."""
    if not raw:
        return []
    return [[tuple(point) for point in zone] for zone in json.loads(raw)]


def build_intelbras_rtsp_url(
    host: str, username: str, password: str, channel: int, port: int = 554, main_stream: bool = False
) -> str:
    """Monta a URL RTSP no formato usado por DVR/NVR Intelbras (firmware
    derivado da Dahua — linhas MHDX, iMHDX, NVD) e pela maioria das câmeras
    IP standalone da Intelbras (linha VIP), que usam o mesmo esquema.

    channel é o número do canal no DVR — cada câmera ligada nele (analógica
    via coaxial OU IP, tanto faz) aparece como um canal independente. Pro
    nosso código isso é transparente: os dois tipos viram a mesma URL RTSP
    (ver COMPATIBILIDADE_CAMERAS.md pra mais detalhes).

    subtype=1 (sub-stream, resolução mais baixa) é o padrão de propósito:
    o stream principal (subtype=0, main_stream=True) custa decodificação
    de CPU que a box já não tem sobrando — sem GPU, a inferência sozinha
    já é o gargalo (ver detector.py)."""
    subtype = 0 if main_stream else 1
    return f"rtsp://{username}:{password}@{host}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"


@dataclass
class CameraConfig:
    camera_id: str
    label: str                     # nome amigável, ex: "Câmera 03 — Corredor 2"
    source: str                    # URL RTSP ou índice da webcam (para testes)
    # Zona de interesse em coordenadas normalizadas (0-1) — ex: perto de uma
    # prateleira de alto valor. Formato: [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    zone_of_interest: list = field(default_factory=list)
    # Sub-áreas DENTRO da zona de interesse que não contam pras regras de
    # mão parada/sumida -- ex: um freezer/prateleira baixa, onde reabastecer
    # produto tem a mesma assinatura geométrica (mão na altura do quadril,
    # some da visão) que esconder algo no bolso, gerando falso positivo em
    # funcionário repondo mercadoria. Mesmo formato de zone_of_interest, só
    # que é uma LISTA de polígonos (pode ter mais de uma área excluída):
    # [[(x1,y1), (x2,y2), ...], [(x1,y1), ...]]. Lista vazia = nenhuma.
    exclusion_zones: list = field(default_factory=list)
    # Quantos frames seguidos de "mão parada perto do corpo dentro da zona"
    # são necessários para considerar suspeito. Calibra sensibilidade.
    hand_still_frames_threshold: int = 45   # ~1.5s a 30fps
    min_confidence_to_alert: float = 0.55


@dataclass
class StoreConfig:
    store_id: str
    api_base_url: str              # backend central (mesmo que alimenta o dashboard)
    api_key: str                   # autenticação da box com o backend
    cameras: list                  # lista de CameraConfig
    pre_event_seconds: int = 5     # quanto de vídeo guardar ANTES do evento
    # Quanto guardar DEPOIS do evento -- era 10s, aumentado pra 20s (2026-09-01)
    # pra dar mais margem de mostrar o que acontece depois do disparo (pessoa
    # continuando a mexer, saindo da loja, etc.) na revisão do alerta. Sem
    # contrapartida técnica real: a câmera de produção é um stream contínuo
    # ao vivo (RollingCapture), não um arquivo de tamanho fixo -- clipe mais
    # longo só usa mais espaço de armazenamento por alerta, não "esgota" nada.
    post_event_seconds: int = 20
    fps_target: int = 15           # roda a inferência a uma taxa menor que a
                                    # captura para economizar CPU/GPU da box


# Zona padrão usada tanto pelo EXAMPLE_STORE quanto pelas câmeras vindas
# do assistente de configuração (que não pede ajuste fino de zona/
# threshold — isso fica pra calibração manual depois, ver
# edge_detection_calibration na memória do projeto).
_DEFAULT_ZONE = [(0.1, 0.35), (0.9, 0.35), (0.9, 0.98), (0.1, 0.98)]
# Era 6 -- recalibrado usando test_offline.py contra um vídeo real de
# furto (ver memória do projeto): a 6 frames, disparos fracos (confiança
# bem no mínimo, ~0.2s de mão "parada") viravam falso positivo com
# frequência, sem ganhar nada de detecção real -- 15 cortou boa parte
# desses disparos fracos sem perder os disparos de sinal forte no mesmo
# vídeo (a pior diferença observada foi um atraso de <1s pra detectar
# uma pessoa de verdade concretizando o gesto). ATENÇÃO: esse número é
# em FRAMES, não segundos -- quanto tempo real isso representa depende
# do fps de captura da câmera. O vídeo de teste usado tinha ~28fps
# nativo (15 frames ~= 0,5s); já o fps_target de produção (StoreConfig
# abaixo) é 15fps, o que faria os mesmos 15 frames representarem ~1s de
# mão parada de verdade -- recalibrar de novo com test_offline.py assim
# que tiver câmera/hardware real definido pra loja.
_DEFAULT_HAND_STILL_FRAMES = 15
_DEFAULT_MIN_CONFIDENCE = 0.55

BOX_CONFIG_PATH = os.environ.get("BOX_CONFIG_PATH", "./box_config.json")


def load_box_config(path: str = BOX_CONFIG_PATH) -> "StoreConfig | None":
    """Carrega a configuração gerada pelo assistente (ver
    setup_wizard.py) — se o arquivo existir, tem prioridade sobre
    EXAMPLE_STORE/variáveis de ambiente abaixo, que ficam só como
    fallback pra desenvolvimento/teste local sem o assistente."""
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    dvr = data["dvr"]
    cameras = [
        CameraConfig(
            camera_id=cam["camera_id"],
            label=cam["label"],
            source=build_intelbras_rtsp_url(
                host=dvr["host"],
                username=dvr["username"],
                password=dvr["password"],
                channel=cam["channel"],
                port=dvr.get("port", 554),
                main_stream=not dvr.get("sub_stream", True),
            ),
            zone_of_interest=_DEFAULT_ZONE,
            hand_still_frames_threshold=_DEFAULT_HAND_STILL_FRAMES,
            min_confidence_to_alert=_DEFAULT_MIN_CONFIDENCE,
        )
        for cam in data["cameras"]
    ]
    return StoreConfig(
        store_id=data["store_id"],
        api_base_url=data.get("api_base_url", "https://api.vigialoja.com.br"),
        api_key=data["api_key"],
        cameras=cameras,
    )


# Exemplo de configuração — usado só quando box_config.json (gerado pelo
# assistente) não existe, pra desenvolvimento/teste local continuar
# funcionando por variável de ambiente como sempre funcionou. Os 3 dados
# sensíveis (chave da loja, id da loja, endereço do backend) nunca ficam
# hardcoded aqui, pra não ir parar no repositório por engano.
EXAMPLE_STORE = StoreConfig(
    store_id=os.environ.get("STORE_ID", "s1"),
    api_base_url=os.environ.get("STORE_API_BASE_URL", "https://api.suaempresa.com.br"),
    api_key=os.environ.get("STORE_API_KEY", "TROCAR_PELA_CHAVE_REAL_DA_LOJA"),
    cameras=[
        CameraConfig(
            # ID real da câmera cadastrada no dashboard (aba "Câmeras") —
            # não é mais um rótulo qualquer: o backend usa isso pra
            # vincular o alerta à câmera certa (FK em alerts.camera_id) e
            # pra correlação entre câmeras da mesma loja. Copie o ID
            # mostrado no dashboard depois de cadastrar a câmera lá.
            camera_id=os.environ.get("CAMERA_ID", "cam03"),
            # Tudo abaixo era hardcoded pra essa câmera de exemplo — agora
            # vem de env var, com o valor de exemplo como fallback. Isso é
            # o que permite rodar duas (ou mais) câmeras DIFERENTES de
            # verdade ao mesmo tempo, cada uma no seu próprio processo com
            # seu próprio conjunto de variáveis de ambiente — sem isso,
            # toda instância deste processo configurava a mesma câmera
            # fixa do exemplo, não dava pra apontar cada processo pra uma
            # câmera física diferente da loja.
            label=os.environ.get("CAMERA_LABEL", "Câmera 03 — Corredor 2"),
            # Exemplo no formato real de DVR/NVR Intelbras (ver
            # build_intelbras_rtsp_url acima e COMPATIBILIDADE_CAMERAS.md).
            # Em produção, troque host/usuário/senha/canal pelos da loja
            # de verdade — normalmente via CAMERA_SOURCE já pronta.
            source=os.environ.get("CAMERA_SOURCE") or build_intelbras_rtsp_url(
                host="192.168.0.50", username="admin", password="TROCAR_PELA_SENHA_REAL", channel=1
            ),
            zone_of_interest=_parse_zone_of_interest(
                os.environ.get("CAMERA_ZONE", "[[0.1,0.35],[0.9,0.35],[0.9,0.98],[0.1,0.98]]")
            ),
            exclusion_zones=_parse_exclusion_zones(os.environ.get("CAMERA_EXCLUSION_ZONES", "")),
            # Calibrado pra CPU sem GPU: nesse hardware o YOLOX+MediaPipe
            # processam ~1-1.5 frame/s, bem abaixo dos 30fps assumidos no
            # valor padrão da classe (45 frames levaria uns 30s pra
            # acumular aqui, em vez dos ~3s pretendidos). 6 frames ~ 4-5s.
            # Precisa recalibrar por câmera/hardware real (ver
            # edge_detection_calibration na memória do projeto).
            hand_still_frames_threshold=int(os.environ.get("CAMERA_HAND_STILL_FRAMES", "6")),
            min_confidence_to_alert=float(os.environ.get("CAMERA_MIN_CONFIDENCE", "0.55")),
        ),
    ],
)

# Isso é o que main.py de fato usa: box_config.json (assistente) se
# existir, senão a configuração de exemplo por variável de ambiente.
ACTIVE_STORE = load_box_config() or EXAMPLE_STORE
