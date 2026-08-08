"""
Busca, uma vez ao iniciar a câmera, quais outras câmeras da mesma loja
foram marcadas como vizinhas no dashboard (ver camera_neighbors no
backend) — alimenta o correlator local (correlator.py). Autenticado por
X-API-Key da loja, igual alert_client.py/heartbeat.py: quem chama aqui é
a box, não um usuário logado.

Falha de rede aqui não pode impedir a câmera de começar a detectar: sem
vizinhança conhecida, o correlator simplesmente nunca encontra
continuação nenhuma — mesmo comportamento de hoje (sem correlação), a
box não trava por isso.
"""

import logging

import requests

log = logging.getLogger("edge-detection")


def fetch_neighbor_camera_ids(api_base_url: str, api_key: str, store_id: str, camera_id: str) -> list:
    if not camera_id:
        return []
    url = f"{api_base_url.rstrip('/')}/v1/stores/{store_id}/cameras/{camera_id}/neighbor-ids"
    try:
        response = requests.get(url, headers={"X-API-Key": api_key}, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        log.warning(f"[store_topology] Falha ao buscar câmeras vizinhas, seguindo sem correlação: {exc}")
        return []
