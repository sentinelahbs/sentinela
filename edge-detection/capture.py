"""
Captura de vídeo com buffer circular.

Por que um buffer circular: quando um evento suspeito é detectado, você
quer o clipe com alguns segundos ANTES do momento do alerta (pra dar
contexto de revisão pro gestor), não só depois. Isso só é possível se
você já estiver guardando os frames recentes em memória o tempo todo.
"""

import os
import time
import logging
import collections
import cv2

log = logging.getLogger("edge-detection")


class RollingCapture:
    # Quantas leituras seguidas falhando antes de considerar a conexão
    # morta e recriar do zero, em vez de só continuar chamando read() no
    # mesmo objeto (que nunca recupera uma sessão RTSP derrubada — a
    # conexão TCP/UDP já morreu, ler de novo só volta False pra sempre).
    RECONNECT_AFTER_FAILURES = 10
    MAX_BACKOFF_SECONDS = 30.0

    def __init__(self, source: str, fps_target: int, pre_event_seconds: int):
        self.source = source
        self.fps_target = fps_target
        self.buffer_size = fps_target * pre_event_seconds
        self.buffer = collections.deque(maxlen=self.buffer_size)
        self._cap = None

    def _create_capture(self) -> cv2.VideoCapture:
        # cv2.VideoCapture trata string como caminho/URL — um índice de webcam
        # (ex: "0") só é reconhecido como câmera se for passado como int.
        if str(self.source).isdigit():
            # No Windows, o backend padrão (MSMF) falha em ler frames com
            # alguns drivers de webcam (erro silencioso, sem lançar exceção —
            # só cap.read() nunca retorna sucesso). DSHOW é o workaround usual.
            return cv2.VideoCapture(int(self.source), cv2.CAP_DSHOW)

        # RTSP sobre UDP (padrão do FFmpeg) é a causa mais comum de stream
        # travando ou nunca conectando atrás de NAT/roteador típico de loja
        # — forçar TCP evita isso. Precisa ser setado ANTES de criar o
        # VideoCapture: é assim que o backend FFmpeg do OpenCV lê essa
        # opção (não tem parâmetro direto pra isso na API do Python).
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        return cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)

    def open(self):
        self._cap = self._create_capture()
        if not self._cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir o stream: {self.source}")
        return self

    def _reconnect(self) -> bool:
        """Fecha e recria a conexão do zero. Nunca levanta exceção: falha
        aqui é esperada (rede instável, DVR reiniciando) e não pode
        derrubar o processo da câmera — quem chama trata o retorno False
        como "continua tentando"."""
        log.warning(f"[RollingCapture] Reconectando ao stream: {self.source}")
        if self._cap is not None:
            self._cap.release()
        try:
            self._cap = self._create_capture()
        except cv2.error as exc:
            log.warning(f"[RollingCapture] Erro ao reconectar: {exc}")
            return False
        if not self._cap.isOpened():
            log.warning(f"[RollingCapture] Falha ao reconectar: {self.source}")
            return False
        log.info(f"[RollingCapture] Reconectado: {self.source}")
        return True

    def frames(self):
        """Gerador: produz (timestamp, frame) e mantém o buffer de pré-evento atualizado."""
        min_interval = 1.0 / self.fps_target
        last_ts = 0.0
        consecutive_failures = 0
        backoff_seconds = 1.0

        while True:
            ok, frame = self._cap.read()
            if not ok:
                consecutive_failures += 1
                if consecutive_failures >= self.RECONNECT_AFTER_FAILURES:
                    if self._reconnect():
                        consecutive_failures = 0
                        backoff_seconds = 1.0
                    else:
                        # backoff exponencial até o teto — evita bater no
                        # DVR a cada segundo indefinidamente se ele estiver
                        # de fato fora do ar por um tempo mais longo.
                        backoff_seconds = min(backoff_seconds * 2, self.MAX_BACKOFF_SECONDS)
                    time.sleep(backoff_seconds)
                else:
                    time.sleep(1.0)
                continue

            consecutive_failures = 0
            backoff_seconds = 1.0

            now = time.time()
            if now - last_ts < min_interval:
                continue  # limita a taxa de inferência sem descartar a captura em si
            last_ts = now

            self.buffer.append((now, frame))
            yield now, frame

    def snapshot_buffer(self):
        """Retorna uma cópia da janela de pré-evento no momento do alerta."""
        return list(self.buffer)

    def get_frame_size(self):
        """(largura, altura) reais entregues pela câmera — pode não bater com
        nenhum valor "padrão" assumido de fora, então quem for normalizar
        coordenadas (0-1) deve sempre consultar isto, nunca supor um tamanho fixo."""
        return (
            int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    def close(self):
        if self._cap is not None:
            self._cap.release()
