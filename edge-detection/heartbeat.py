"""
Ping periódico pro backend saber que a box está viva — independente de
disparar algum alerta. Roda numa thread separada do loop de detecção
(main.py): esse loop fica bloqueado processando frame a frame, e sozinho
não teria como garantir um ping a cada N segundos.

Um heartbeat por LOJA, não por câmera — usa a mesma API key já usada
pros alertas (ver alert_client.py). O backend deriva "offline" a partir
de quanto tempo faz desde o último heartbeat (ver models.py, ONLINE_
THRESHOLD_SECONDS), não existe estado "online"/"offline" guardado aqui.
"""

import logging
import threading
import time

import requests

log = logging.getLogger("edge-detection")

# Backend considera offline depois de 3 heartbeats perdidos seguidos
# (ver ONLINE_THRESHOLD_SECONDS = 180 em models.py) — mantenha os dois
# valores coerentes se mudar um deles.
HEARTBEAT_INTERVAL_SECONDS = 60


class HeartbeatSender:
    def __init__(self, api_base_url: str, api_key: str, store_id: str, interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS):
        self.url = f"{api_base_url.rstrip('/')}/v1/stores/{store_id}/heartbeat"
        self.headers = {"X-API-Key": api_key}
        self.interval_seconds = interval_seconds

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return thread

    def _run(self):
        while True:
            try:
                response = requests.post(self.url, headers=self.headers, timeout=10)
                response.raise_for_status()
            except requests.RequestException as exc:
                # Não derruba a box por causa disso — só loga e tenta de
                # novo no próximo ciclo. Uma falha pontual de rede não
                # pode impedir a detecção de continuar rodando.
                log.warning(f"[HeartbeatSender] Falha ao enviar heartbeat: {exc}")
            time.sleep(self.interval_seconds)
