"""
Supervisor multi-câmera: sobe um processo main.py por câmera de
ACTIVE_STORE (ver config.py — vem de box_config.json, gerado pelo
setup_wizard.py, ou de variável de ambiente como fallback), reinicia
automaticamente se algum cair, e roda o heartbeat da loja uma vez só —
não um por câmera (ver VIGIA_SUPERVISED em main.py).

Cada câmera continua um processo do SISTEMA OPERACIONAL separado, não
thread — mesma razão de sempre: uma câmera travando ou vazando memória
não pode derrubar as outras.

Este é o processo pensado pra rodar como serviço do Windows (via NSSM,
ver decisão de empacotamento) — um serviço só, que por baixo gerencia
todas as câmeras da loja.
"""

import logging
import os
import subprocess
import sys
import time

from config import ACTIVE_STORE
from heartbeat import HeartbeatSender

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("supervisor")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")

POLL_INTERVAL_SECONDS = 3.0
MAX_BACKOFF_SECONDS = 60.0
# Quanto tempo rodando sem cair já é "saudável" o bastante pra resetar o
# backoff — sem isso, uma câmera que travou depois de rodar bem por
# horas voltaria a esperar o backoff máximo pra reconectar, como se
# estivesse quebrando desde o início (mesma lógica de RollingCapture).
HEALTHY_UPTIME_SECONDS = 300.0


class CameraSupervisor:
    """Um por câmera. Não bloqueia esperando o backoff — só marca
    next_restart_at e deixa o loop principal seguir monitorando as
    outras câmeras nesse meio tempo (ver poll_and_maybe_restart)."""

    def __init__(self, camera_index: int, camera_label: str):
        self.camera_index = camera_index
        self.camera_label = camera_label
        self.process = None
        self.backoff_seconds = 1.0
        self.started_at = None
        self.next_restart_at = 0.0
        self._log_file = None

    def _spawn(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = os.path.join(LOG_DIR, f"camera_{self.camera_index}.log")
        self._log_file = open(log_path, "a", encoding="utf-8")

        env = os.environ.copy()
        env["CAMERA_INDEX"] = str(self.camera_index)
        env["VIGIA_SUPERVISED"] = "1"

        log.info(f"Iniciando câmera {self.camera_index} ({self.camera_label}) — log em {log_path}")
        self.process = subprocess.Popen(
            [sys.executable, MAIN_SCRIPT],
            cwd=BASE_DIR, env=env,
            stdout=self._log_file, stderr=subprocess.STDOUT,
        )
        self.started_at = time.time()

    def poll_and_maybe_restart(self):
        now = time.time()

        if self.process is not None:
            exit_code = self.process.poll()
            if exit_code is None:
                return  # ainda rodando, nada a fazer

            uptime = now - (self.started_at or now)
            if self._log_file:
                self._log_file.close()
            self.process = None

            # rodou "saudável" por tempo suficiente antes de cair -> não
            # trata como parte de uma sequência de falhas, reseta o backoff
            if uptime >= HEALTHY_UPTIME_SECONDS:
                self.backoff_seconds = 1.0
            else:
                self.backoff_seconds = min(self.backoff_seconds * 2, MAX_BACKOFF_SECONDS)

            log.warning(
                f"Câmera {self.camera_index} ({self.camera_label}) encerrou "
                f"(código {exit_code}, rodou {uptime:.0f}s) — reiniciando em {self.backoff_seconds:.0f}s"
            )
            self.next_restart_at = now + self.backoff_seconds
            return

        # process is None: primeira vez, ou esperando o backoff terminar
        if now >= self.next_restart_at:
            self._spawn()

    def terminate(self):
        if self.process is not None and self.process.poll() is None:
            log.info(f"Encerrando câmera {self.camera_index} ({self.camera_label})")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning(f"Câmera {self.camera_index} não encerrou a tempo — forçando")
                self.process.kill()
        if self._log_file:
            self._log_file.close()


def main():
    if not ACTIVE_STORE.cameras:
        log.error("Nenhuma câmera configurada (ACTIVE_STORE.cameras vazio) — nada a supervisionar.")
        return

    log.info(f"Loja {ACTIVE_STORE.store_id} — {len(ACTIVE_STORE.cameras)} câmera(s) sob supervisão")

    # Heartbeat é da loja, não de cada câmera — roda uma vez só aqui.
    # Os processos filhos nunca sobem o próprio (ver VIGIA_SUPERVISED em
    # main.py), senão a loja mandaria N heartbeats por ciclo.
    HeartbeatSender(
        api_base_url=ACTIVE_STORE.api_base_url,
        api_key=ACTIVE_STORE.api_key,
        store_id=ACTIVE_STORE.store_id,
    ).start()

    supervisors = [CameraSupervisor(i, cam.label) for i, cam in enumerate(ACTIVE_STORE.cameras)]

    try:
        while True:
            for sup in supervisors:
                sup.poll_and_maybe_restart()
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log.info("Encerrando supervisor — parando todas as câmeras…")
        for sup in supervisors:
            sup.terminate()


if __name__ == "__main__":
    main()
