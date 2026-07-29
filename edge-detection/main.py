"""
Ponto de entrada da box de detecção — roda continuamente em cada loja,
um processo por câmera (em produção, provavelmente um processo separado
por câmera, pra uma travar não derrubar as outras).

Fluxo por frame:
  captura -> percepção (pessoa + mãos) -> regra (é suspeito?) -> alerta

Quando a regra dispara: grava o clipe (pré + pós evento) e envia pro
backend, que é o mesmo que alimenta o dashboard já construído.
"""

import time
import logging

from config import EXAMPLE_STORE
from capture import RollingCapture
from detector import PerceptionPipeline
from pose_rules import SuspiciousBehaviorRule
from clip_recorder import ClipRecorder
from alert_client import AlertClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("edge-detection")

# Evita re-alertar a mesma pessoa repetidamente enquanto ela continua parada
# no mesmo lugar — sem isso, uma pessoa parada 30s geraria vários alertas.
COOLDOWN_SECONDS = 60


def run_camera(store_cfg, camera_cfg):
    log.info(f"Iniciando câmera: {camera_cfg.label}")

    capture = RollingCapture(
        source=camera_cfg.source,
        fps_target=store_cfg.fps_target,
        pre_event_seconds=store_cfg.pre_event_seconds,
    ).open()

    perception = PerceptionPipeline(frame_size=(1280, 720))
    rule = SuspiciousBehaviorRule(
        zone_points=camera_cfg.zone_of_interest,
        still_frames_threshold=camera_cfg.hand_still_frames_threshold,
    )
    recorder = ClipRecorder(output_dir="./clips", fps_target=store_cfg.fps_target)
    alert_client = AlertClient(
        api_base_url=store_cfg.api_base_url,
        api_key=store_cfg.api_key,
        store_id=store_cfg.store_id,
    )

    last_alert_at = {}

    try:
        for ts, frame in capture.frames():
            signals = perception.process(frame)

            for i, signal in enumerate(signals):
                # Nota: em produção, usar um tracker real (ex: ByteTrack) pra
                # manter a identidade da pessoa entre frames. Aqui, índice
                # simples só pra ilustrar o fluxo.
                person_id = f"person_{i}"

                is_suspicious, confidence, reason = rule.evaluate(
                    person_id, signal.hands_norm
                )
                if not is_suspicious or confidence < camera_cfg.min_confidence_to_alert:
                    continue

                if time.time() - last_alert_at.get(person_id, 0) < COOLDOWN_SECONDS:
                    continue
                last_alert_at[person_id] = time.time()

                log.info(f"Evento suspeito detectado (confiança={confidence}): {reason}")

                pre_event_frames = capture.snapshot_buffer()
                thumbnail = recorder.thumbnail_from_clip(pre_event_frames)
                clip_path = recorder.write_clip(
                    pre_event_frames, capture, store_cfg.post_event_seconds
                )

                alert_client.send_alert(
                    camera_id=camera_cfg.camera_id,
                    camera_label=camera_cfg.label,
                    confidence=confidence,
                    reason=reason,
                    clip_path=clip_path,
                    thumbnail_bytes=thumbnail,
                )
    finally:
        perception.close()
        capture.close()


if __name__ == "__main__":
    # MVP: uma câmera. Em produção, um processo (ou thread) por câmera da loja.
    run_camera(EXAMPLE_STORE, EXAMPLE_STORE.cameras[0])
