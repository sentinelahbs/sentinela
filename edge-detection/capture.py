"""
Captura de vídeo com buffer circular.

Por que um buffer circular: quando um evento suspeito é detectado, você
quer o clipe com alguns segundos ANTES do momento do alerta (pra dar
contexto de revisão pro gestor), não só depois. Isso só é possível se
você já estiver guardando os frames recentes em memória o tempo todo.
"""

import time
import collections
import cv2


class RollingCapture:
    def __init__(self, source: str, fps_target: int, pre_event_seconds: int):
        self.source = source
        self.fps_target = fps_target
        self.buffer_size = fps_target * pre_event_seconds
        self.buffer = collections.deque(maxlen=self.buffer_size)
        self._cap = None

    def open(self):
        # cv2.VideoCapture trata string como caminho/URL — um índice de webcam
        # (ex: "0") só é reconhecido como câmera se for passado como int.
        if str(self.source).isdigit():
            # No Windows, o backend padrão (MSMF) falha em ler frames com
            # alguns drivers de webcam (erro silencioso, sem lançar exceção —
            # só cap.read() nunca retorna sucesso). DSHOW é o workaround usual.
            self._cap = cv2.VideoCapture(int(self.source), cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir o stream: {self.source}")
        return self

    def frames(self):
        """Gerador: produz (timestamp, frame) e mantém o buffer de pré-evento atualizado."""
        min_interval = 1.0 / self.fps_target
        last_ts = 0.0
        while True:
            ok, frame = self._cap.read()
            if not ok:
                # Em produção: log + tentativa de reconexão com backoff,
                # em vez de simplesmente parar.
                time.sleep(1.0)
                continue

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
