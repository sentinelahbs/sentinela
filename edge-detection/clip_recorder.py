"""
Gera o clipe de vídeo do evento: junta os frames que já estavam no buffer
de pré-evento com os frames capturados nos segundos seguintes ao alerta.
"""

import os
import time
import uuid
import cv2


class ClipRecorder:
    def __init__(self, output_dir: str, fps_target: int):
        self.output_dir = output_dir
        self.fps_target = fps_target
        os.makedirs(output_dir, exist_ok=True)

    def write_clip(self, pre_event_frames: list, capture, post_event_seconds: int) -> str:
        """
        pre_event_frames: lista de (timestamp, frame) já capturados antes do evento
        capture: instância de RollingCapture ainda aberta, usada pra continuar
                 gravando os frames de DEPOIS do evento
        """
        if not pre_event_frames:
            raise ValueError("Buffer de pré-evento vazio — nada para gravar")

        clip_id = str(uuid.uuid4())
        path = os.path.join(self.output_dir, f"{clip_id}.mp4")

        h, w = pre_event_frames[0][1].shape[:2]
        writer = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps_target, (w, h)
        )

        for _, frame in pre_event_frames:
            writer.write(frame)

        deadline = time.time() + post_event_seconds
        for _, frame in capture.frames():
            writer.write(frame)
            if time.time() >= deadline:
                break

        writer.release()
        return path

    def thumbnail_from_clip(self, pre_event_frames: list) -> "bytes | None":
        """Usa o frame do meio do buffer de pré-evento como thumbnail do alerta."""
        if not pre_event_frames:
            return None
        mid_frame = pre_event_frames[len(pre_event_frames) // 2][1]
        ok, buf = cv2.imencode(".jpg", mid_frame)
        return buf.tobytes() if ok else None
