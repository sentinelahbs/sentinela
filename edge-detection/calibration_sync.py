"""
Sincronização remota de calibração: a box busca periodicamente no
backend a zona de interesse e os thresholds mais recentes da própria
câmera, e aplica ao pipeline de detecção em execução — sem reinstalar
nada, sem acessar o PC do cliente, sem reiniciar o processo.

Por que isso NÃO é só mais uma coisa pendurada no heartbeat.py: o
heartbeat é por LOJA (um ping só por loja, mesmo com N câmeras rodando
em N processos separados — ver VIGIA_SUPERVISED em main.py/supervisor.py,
que existe justamente pra não duplicar o ping). Calibração é por CÂMERA,
e precisa ser aplicada dentro do processo que dona o `SuspiciousBehaviorRule`
daquela câmera especificamente. Em produção (supervisor.py), o heartbeat
roda no processo do SUPERVISOR, não no processo de cada câmera — reusar
a mesma thread exigiria inventar um jeito de levar o resultado de volta
pra cada processo filho (arquivo compartilhado, socket etc.) só pra
economizar uma chamada HTTP leve a cada 60s por câmera, que não é caro.
Por isso este é um módulo novo, seguindo o mesmo estilo (thread daemon,
mesmo intervalo, mesma resiliência a falha de rede) mas rodando dentro
de cada processo de câmera (main.py), supervisionado ou não.
"""

import logging
import threading
import time

import requests

from heartbeat import HEARTBEAT_INTERVAL_SECONDS
from pose_rules import SuspiciousBehaviorRule

log = logging.getLogger("edge-detection")


class CalibrationSync:
    """Um por câmera. Guarda referência direta ao `rule` e ao
    `camera_cfg` já em uso pelo loop de detecção (main.py) — quando
    chega calibração nova, aplica direto neles, em memória, sem
    reiniciar nenhum componente."""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        store_id: str,
        camera_id: str,
        rule: SuspiciousBehaviorRule,
        camera_cfg,
        interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
    ):
        self.url = f"{api_base_url.rstrip('/')}/v1/stores/{store_id}/cameras/{camera_id}/calibration"
        self.headers = {"X-API-Key": api_key}
        self.rule = rule
        self.camera_cfg = camera_cfg
        self.interval_seconds = interval_seconds
        self._last_applied_at = None  # string ISO do updated_at já aplicado, pra não reprocessar à toa

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return thread

    def _run(self):
        while True:
            try:
                self._sync_once()
            except requests.RequestException as exc:
                # Falha de rede pontual não pode impedir a detecção de
                # continuar rodando com a última calibração aplicada
                # (ou o default local, se nunca aplicou nenhuma ainda).
                log.warning(f"[CalibrationSync] Falha ao buscar calibração, mantendo a atual: {exc}")
            except Exception as exc:
                # Payload malformado, zona inválida (Polygon() estourando
                # em pose_rules.py) etc. — mesma lógica: nunca deixa isso
                # derrubar o processo de detecção nem adotar um estado
                # inválido. Fica com a calibração anterior e tenta de
                # novo no próximo ciclo.
                log.warning(f"[CalibrationSync] Calibração recebida inválida, ignorando: {exc}")
            time.sleep(self.interval_seconds)

    def _sync_once(self):
        response = requests.get(self.url, headers=self.headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        updated_at = data.get("updated_at")
        if updated_at is None or updated_at == self._last_applied_at:
            return  # nada novo desde a última vez, ou loja nunca calibrou remotamente ainda

        zone = data.get("zone_of_interest")
        threshold = data.get("hand_still_frames_threshold")
        confidence = data.get("min_confidence_to_alert")

        # Cada campo é independente: a loja pode ter calibrado só a zona,
        # só o threshold, ou só a confiança — None em qualquer um deles
        # significa "sem override remoto pra esse campo", mantém o valor
        # local atual (não o zera).
        if zone is not None or threshold is not None:
            self.rule.apply_calibration(
                zone_points=zone if zone is not None else self._current_zone_points(),
                still_frames_threshold=threshold if threshold is not None else self.rule.still_frames_threshold,
            )
        if confidence is not None:
            self.camera_cfg.min_confidence_to_alert = confidence

        self._last_applied_at = updated_at
        log.info(
            f"[CalibrationSync] Calibração remota aplicada "
            f"(zona={'sim' if zone is not None else 'sem alteração'}, "
            f"threshold={threshold if threshold is not None else 'sem alteração'}, "
            f"confiança={confidence if confidence is not None else 'sem alteração'})"
        )

    def _current_zone_points(self) -> list:
        # SuspiciousBehaviorRule guarda a zona já como shapely Polygon,
        # não como lista de pontos — reconstrói a lista a partir dele
        # pra poder reaplicar só o threshold sem perder a zona atual.
        if self.rule.zone is None:
            return []
        return list(self.rule.zone.exterior.coords)[:-1]  # shapely fecha o polígono repetindo o 1º ponto
