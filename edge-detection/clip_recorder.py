"""
Gera o clipe de vídeo do evento: junta os frames que já estavam no buffer
de pré-evento com os frames capturados nos segundos seguintes ao alerta.
"""

import logging
import os
import subprocess
import time
import uuid
import cv2
import imageio_ffmpeg

log = logging.getLogger("edge-detection")


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
        # H.264 (avc1), não mp4v — mp4v é o padrão do OpenCV mas navegadores
        # (Chrome, Safari, Edge) não conseguem reproduzir esse codec nativamente
        # no <video>, mesmo dentro de um .mp4; o clipe subia mas não tocava no
        # painel. Precisa da lib openh264 (ver README) pra isso funcionar.
        writer = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*"avc1"), self.fps_target, (w, h)
        )

        for _, frame in pre_event_frames:
            writer.write(frame)

        deadline = time.time() + post_event_seconds
        for _, frame in capture.frames():
            writer.write(frame)
            if time.time() >= deadline:
                break

        writer.release()
        _make_faststart(path)
        return path

    def thumbnail_from_clip(self, pre_event_frames: list) -> "bytes | None":
        """Usa o frame do meio do buffer de pré-evento como thumbnail do alerta."""
        if not pre_event_frames:
            return None
        mid_frame = pre_event_frames[len(pre_event_frames) // 2][1]
        ok, buf = cv2.imencode(".jpg", mid_frame)
        return buf.tobytes() if ok else None


def _make_faststart(path: str) -> None:
    """Reescreve o índice (moov atom) do MP4 pro início do arquivo.

    cv2.VideoWriter grava o moov no FINAL por padrão (mux de passe
    único) -- o arquivo fica tecnicamente íntegro (o próprio OpenCV relê
    sem problema), mas boa parte dos players, principalmente os
    baseados em navegador (o dashboard mostra o clipe assim), recusam
    ou travam ao abrir, porque precisam ler o índice antes de decidir
    como tocar e ele só existe no fim do arquivo. Descoberto testando
    test_offline.py com um vídeo de ~50MB (clipe real de alerta é bem
    menor, mas o mesmo problema existe em qualquer tamanho — só fica
    mais fácil de disfarçar em arquivo pequeno o bastante pra baixar
    inteiro rápido).

    Usa o binário ffmpeg empacotado pelo pacote imageio-ffmpeg (não
    depende de ffmpeg instalado na box) só pra REMUXAR (-c copy, sem
    recodificar -- rápido, sem perda de qualidade), movendo o moov pro
    início ("+faststart"). Nunca deixa uma falha aqui derrubar o envio
    do alerta: se o remux falhar por qualquer motivo, loga um aviso e
    segue com o arquivo original -- clipe sem faststart ainda é melhor
    que nenhum clipe."""
    tmp_path = path + ".faststart.mp4"
    try:
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", path, "-c", "copy", "-movflags", "+faststart", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning(f"[ClipRecorder] Não consegui mover o índice do clipe pro início (mantendo original): {result.stderr[-300:]}")
            return
        os.replace(tmp_path, path)
    except Exception as exc:
        log.warning(f"[ClipRecorder] Falha ao corrigir o índice do clipe, mantendo original: {exc}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
