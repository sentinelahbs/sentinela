"""
Correlator local: guarda os alertas recentes desta LOJA (não só desta
câmera) numa base SQLite compartilhada em disco entre os processos de
cada câmera, e responde "isso é continuação de um alerta recente numa
câmera vizinha, ou é um evento novo?" — é isso que evita mandar dois
alertas pro mesmo incidente quando a pessoa atravessa de uma câmera pra
outra vizinha (vizinhança marcada no dashboard, ver camera_neighbors no
backend e store_topology.py aqui).

SQLite em vez de um serviço/fila próprios: já é o mecanismo previsto
nesta base de código pra persistência local da box (ver comentário de
retry em alert_client.py) — reaproveitar evita inventar um canal de IPC
novo só pra isso. Cada chamada abre e fecha sua própria conexão —
alertas são eventos raros (cooldown de 60s, ver main.py), não frame a
frame, então o custo de abrir conexão a cada vez é desprezível, e evita
lidar com uma conexão de longa duração disputada entre processos.
"""

import sqlite3
import time
from dataclasses import dataclass

from appearance import signature_distance


@dataclass
class ContinuationMatch:
    """O alerta recente (de uma câmera vizinha) que casou com o evento
    atual — quem chama usa isso pra reportar a supressão de forma
    auditável (ver SuppressedEvent no backend), não só suprimir calado."""
    camera_id: str
    track_id: int
    distance: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    signature BLOB NOT NULL,
    created_at REAL NOT NULL
)
"""


class LocalCorrelator:
    def __init__(
        self,
        db_path: str = "./correlator.db",
        correlation_window_seconds: float = 8.0,
        appearance_max_distance: float = 0.4,
    ):
        self.db_path = db_path
        self.correlation_window_seconds = correlation_window_seconds
        self.appearance_max_distance = appearance_max_distance
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        # WAL: permite os processos de cada câmera lerem/escreverem o
        # mesmo arquivo concorrentemente sem se travarem uns aos outros
        # (o modo padrão do SQLite serializa até leituras durante um write).
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def find_continuation(
        self, camera_id: str, neighbor_camera_ids: list, signature: bytes, now: "float | None" = None
    ) -> "ContinuationMatch | None":
        """Retorna o melhor (menor distância) alerta recente de uma
        câmera VIZINHA que bate com essa aparência dentro da janela de
        correlação, ou None se não achou nenhum. Nunca olha pra alertas
        da própria câmera — dedup dentro da mesma câmera já é feito pelo
        cooldown em main.py, isso aqui é só entre câmeras. Câmera sem
        vizinhas cadastradas nunca correlaciona com nada — mantém o
        comportamento de hoje (um alerta por câmera, sem supressão).

        Devolver o match (não só um bool) é o que permite reportar a
        supressão de forma auditável (ver SuppressedEvent no backend) —
        sem isso não daria pra dizer PRA QUAL câmera/evento essa
        supressão foi atribuída."""
        if not neighbor_camera_ids:
            return None
        now = now if now is not None else time.time()
        cutoff = now - self.correlation_window_seconds

        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in neighbor_camera_ids)
            rows = conn.execute(
                f"SELECT camera_id, track_id, signature FROM alert_events "
                f"WHERE camera_id IN ({placeholders}) AND created_at >= ?",
                (*neighbor_camera_ids, cutoff),
            ).fetchall()
        finally:
            conn.close()

        best = None
        for row_camera_id, row_track_id, row_signature in rows:
            distance = signature_distance(signature, row_signature)
            if distance <= self.appearance_max_distance:
                if best is None or distance < best.distance:
                    best = ContinuationMatch(camera_id=row_camera_id, track_id=row_track_id, distance=distance)
        return best

    def record_alert(self, camera_id: str, track_id: int, signature: bytes, now: "float | None" = None) -> None:
        now = now if now is not None else time.time()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO alert_events (camera_id, track_id, signature, created_at) VALUES (?, ?, ?, ?)",
                (camera_id, track_id, signature, now),
            )
            # limpeza oportunista: eventos mais velhos que a janela de
            # correlação nunca mais vão casar com nada — sem isso a base
            # cresce sem limite pro resto da vida da loja.
            conn.execute(
                "DELETE FROM alert_events WHERE created_at < ?",
                (now - self.correlation_window_seconds * 5,),
            )
            conn.commit()
        finally:
            conn.close()
