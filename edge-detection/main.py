"""
Ponto de entrada da box de detecção — roda continuamente em cada loja,
um processo por câmera (em produção, provavelmente um processo separado
por câmera, pra uma travar não derrubar as outras).

Fluxo por frame:
  captura -> percepção (pessoa + mãos) -> regra (é suspeito?) -> alerta

Quando a regra dispara: grava o clipe (pré + pós evento) e envia pro
backend, que é o mesmo que alimenta o dashboard já construído.
"""

import os
import time
import logging

from config import EXAMPLE_STORE
from capture import RollingCapture
from detector import PerceptionPipeline, DETECTION_BACKEND
from pose_rules import SuspiciousBehaviorRule
from tracker import IouTracker
from appearance import color_signature
from correlator import LocalCorrelator
from store_topology import fetch_neighbor_camera_ids
from clip_recorder import ClipRecorder
from alert_client import AlertClient
from heartbeat import HeartbeatSender

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("edge-detection")

# Evita re-alertar a mesma pessoa repetidamente enquanto ela continua parada
# no mesmo lugar — sem isso, uma pessoa parada 30s geraria vários alertas.
COOLDOWN_SECONDS = 60

# DETECTION_DEBUG=1: loga o que a pipeline está vendo a cada frame (pessoas,
# posição da mão). Usar só pra calibrar/depurar — em produção deixar desligado.
DETECTION_DEBUG = os.environ.get("DETECTION_DEBUG", "0") == "1"


def run_camera(store_cfg, camera_cfg):
    log.info(f"Iniciando câmera: {camera_cfg.label} (backend de detecção: {DETECTION_BACKEND})")

    capture = RollingCapture(
        source=camera_cfg.source,
        fps_target=store_cfg.fps_target,
        pre_event_seconds=store_cfg.pre_event_seconds,
    ).open()

    # Usa a resolução real entregue pela câmera, não um valor fixo — câmeras
    # diferentes (webcam de notebook, câmera IP) capturam em tamanhos diferentes,
    # e normalizar com o tamanho errado faz a checagem de zona nunca bater.
    perception = PerceptionPipeline(frame_size=capture.get_frame_size())
    rule = SuspiciousBehaviorRule(
        zone_points=camera_cfg.zone_of_interest,
        still_frames_threshold=camera_cfg.hand_still_frames_threshold,
    )
    tracker = IouTracker()
    recorder = ClipRecorder(output_dir="./clips", fps_target=store_cfg.fps_target)
    alert_client = AlertClient(
        api_base_url=store_cfg.api_base_url,
        api_key=store_cfg.api_key,
        store_id=store_cfg.store_id,
    )

    # Vizinhança é cadastrada uma vez no dashboard e muda raramente —
    # busca só ao iniciar, não precisa reconsultar a cada frame nem a
    # cada alerta. Loja compartilha a mesma base local entre os processos
    # de cada câmera (ver correlator.py — por isso db_path é relativo ao
    # diretório de trabalho da BOX, não por câmera).
    neighbor_camera_ids = fetch_neighbor_camera_ids(
        store_cfg.api_base_url, store_cfg.api_key, store_cfg.store_id, camera_cfg.camera_id
    )
    correlator = LocalCorrelator()

    last_alert_at = {}

    try:
        for ts, frame in capture.frames():
            signals = perception.process(frame)
            track_ids = tracker.update([s.person_bbox for s in signals], capture.get_frame_size())

            # Pessoas que o tracker deu como fora de cena (frames demais
            # sem bater bbox nenhum) — limpa o estado acumulado delas em
            # outros lugares, senão cresce sem limite pro resto da vida
            # do processo (ver comentário em SuspiciousBehaviorRule.forget).
            for ended in tracker.ended_tracks:
                ended_id = f"person_{ended.track_id}"
                rule.forget(ended_id)
                last_alert_at.pop(ended_id, None)
                if DETECTION_DEBUG:
                    log.info(f"debug: {ended_id} saiu de cena (borda_do_quadro={ended.exited_frame_edge})")

            if DETECTION_DEBUG:
                if not signals:
                    log.info("debug: nenhuma pessoa detectada neste frame")
                for track_id, s in zip(track_ids, signals):
                    log.info(
                        f"debug: person_{track_id} conf={s.confidence:.2f} "
                        f"bbox={s.person_bbox} maos_norm={s.hands_norm}"
                    )

            for track_id, signal in zip(track_ids, signals):
                person_id = f"person_{track_id}"

                is_suspicious, confidence, reason = rule.evaluate(
                    person_id, signal.hands_norm
                )
                if not is_suspicious or confidence < camera_cfg.min_confidence_to_alert:
                    continue

                if time.time() - last_alert_at.get(person_id, 0) < COOLDOWN_SECONDS:
                    continue
                last_alert_at[person_id] = time.time()

                # Correlação entre câmeras vizinhas (ver correlator.py):
                # registra esse evento sempre, mesmo quando ele próprio
                # acaba sendo suprimido como continuação — permite
                # encadear por uma terceira câmera vizinha, se existir.
                # Registrar ANTES de checar evita que duas câmeras vizinhas
                # disparando quase juntas se suprimam mutuamente (a que
                # registra primeiro "vence"; a segunda vê o registro da
                # primeira e se suprime).
                signature = color_signature(frame, signal.person_bbox)
                continuation = correlator.find_continuation(camera_cfg.camera_id, neighbor_camera_ids, signature)
                correlator.record_alert(camera_cfg.camera_id, track_id, signature)

                if continuation is not None:
                    log.info(
                        f"Evento suspeito (confiança={confidence}) tratado como continuação de um "
                        f"alerta recente na câmera {continuation.camera_id} "
                        f"(distância={continuation.distance:.3f}) — não reenviado: {reason}"
                    )
                    # Log de auditoria (ver SuppressedEvent no backend) —
                    # não crítico, se falhar não deve travar a detecção.
                    alert_client.report_suppressed_event(
                        camera_id=camera_cfg.camera_id,
                        matched_camera_id=continuation.camera_id,
                        track_id=track_id,
                        confidence=confidence,
                        appearance_distance=continuation.distance,
                    )
                    continue

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
    # Heartbeat é por LOJA, não por câmera — se no futuro isso virar um
    # processo por câmera (ver comentário abaixo), só o primeiro processo
    # da loja deveria iniciar o sender, pra não mandar heartbeats
    # duplicados. Por agora, MVP de uma câmera só, sem esse problema.
    HeartbeatSender(
        api_base_url=EXAMPLE_STORE.api_base_url,
        api_key=EXAMPLE_STORE.api_key,
        store_id=EXAMPLE_STORE.store_id,
    ).start()

    # MVP: uma câmera. Em produção, um processo (ou thread) por câmera da loja.
    run_camera(EXAMPLE_STORE, EXAMPLE_STORE.cameras[0])
