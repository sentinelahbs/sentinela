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

from appearance import signature_distance

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
    ) -> bool:
        """True se algum alerta recente de uma câmera VIZINHA bate com
        essa aparência dentro da janela de correlação. Nunca olha pra
        alertas da própria câmera — dedup dentro da mesma câmera já é
        feito pelo cooldown em main.py, isso aqui é só entre câmeras.
        Câmera sem vizinhas cadastradas nunca correlaciona com nada —
        mantém o comportamento de hoje (um alerta por câmera, sem
        supressão)."""
        if not neighbor_camera_ids:
            return False
        now = now if now is not None else time.time()
        cutoff = now - self.correlation_window_seconds

        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in neighbor_camera_ids)
            rows = conn.execute(
                f"SELECT signature FROM alert_events WHERE camera_id IN ({placeholders}) AND created_at >= ?",
                (*neighbor_camera_ids, cutoff),
            ).fetchall()
        finally:
            conn.close()

        return any(signature_distance(signature, row[0]) <= self.appearance_max_distance for row in rows)

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
