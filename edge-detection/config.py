"""
Configuração do módulo de detecção (roda na "box" instalada em cada loja).

Ideia geral: cada câmera tem sua própria configuração de zona de interesse
(ex: perto de uma prateleira) e seus próprios thresholds. Isso evita ter
uma regra genérica "uma pra todas as câmeras", que na prática gera
excesso de falso positivo.
"""

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
# carregado por loja, não hardcoded.
EXAMPLE_STORE = StoreConfig(
    store_id="s1",
    api_base_url="https://api.suaempresa.com.br",
    api_key="TROCAR_PELA_CHAVE_REAL_DA_LOJA",
    cameras=[
        CameraConfig(
            camera_id="cam03",
            label="Câmera 03 — Corredor 2",
            source="rtsp://usuario:senha@192.168.0.50:554/stream1",
            zone_of_interest=[(0.3, 0.4), (0.7, 0.4), (0.7, 0.9), (0.3, 0.9)],
        ),
    ],
)
