"""
Configuração do módulo de detecção (roda na "box" instalada em cada loja).

Ideia geral: cada câmera tem sua própria configuração de zona de interesse
(ex: perto de uma prateleira) e seus próprios thresholds. Isso evita ter
uma regra genérica "uma pra todas as câmeras", que na prática gera
excesso de falso positivo.
"""

import os
from dataclasses import dataclass, field


@dataclass
class CameraConfig:
    camera_id: str
    label: str                     # nome amigável, ex: "Câmera 03 — Corredor 2"
    source: str                    # URL RTSP ou índice da webcam (para testes)
    # Zona de interesse em coordenadas normalizadas (0-1) — ex: perto de uma
    # prateleira de alto valor. Formato: [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    zone_of_interest: list = field(default_factory=list)
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
    post_event_seconds: int = 10   # quanto guardar DEPOIS do evento
    fps_target: int = 15           # roda a inferência a uma taxa menor que a
                                    # captura para economizar CPU/GPU da box


# Exemplo de configuração — na prática isso viria de um arquivo YAML/JSON
# carregado por loja, não hardcoded. Os 3 dados sensíveis (chave da loja,
# id da loja, endereço do backend) vêm de variável de ambiente — nunca
# hardcoded aqui, pra não ir parar no repositório por engano.
EXAMPLE_STORE = StoreConfig(
    store_id=os.environ.get("STORE_ID", "s1"),
    api_base_url=os.environ.get("STORE_API_BASE_URL", "https://api.suaempresa.com.br"),
    api_key=os.environ.get("STORE_API_KEY", "TROCAR_PELA_CHAVE_REAL_DA_LOJA"),
    cameras=[
        CameraConfig(
            camera_id="cam03",
            label="Câmera 03 — Corredor 2",
            source=os.environ.get("CAMERA_SOURCE", "rtsp://usuario:senha@192.168.0.50:554/stream1"),
            zone_of_interest=[(0.1, 0.35), (0.9, 0.35), (0.9, 0.98), (0.1, 0.98)],
            # Calibrado pra CPU sem GPU: nesse hardware o YOLOX+MediaPipe
            # processam ~1-1.5 frame/s, bem abaixo dos 30fps assumidos no
            # valor padrão da classe (45 frames levaria uns 30s pra
            # acumular aqui, em vez dos ~3s pretendidos). 6 frames ~ 4-5s.
            hand_still_frames_threshold=6,
        ),
    ],
)
