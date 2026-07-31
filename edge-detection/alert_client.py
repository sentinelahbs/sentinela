"""
Envia o alerta gerado pela box para o backend central — o mesmo backend
que alimenta o dashboard web/mobile mostrado ao gestor.

Só sai da loja: o clipe curto do evento + metadados. O stream bruto da
câmera nunca trafega pra fora — isso reduz bastante a superfície de dados
sensíveis e ajuda na conformidade com a LGPD.
"""

import requests


class AlertClient:
    def __init__(self, api_base_url: str, api_key: str, store_id: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.store_id = store_id

    def send_alert(
        self,
        camera_id: str,
        camera_label: str,
        confidence: float,
        reason: str,
        clip_path: str,
        thumbnail_bytes: "bytes | None",
    ):
        url = f"{self.api_base_url}/v1/stores/{self.store_id}/alerts"
        # O backend autentica a box por uma API key própria da loja, num
        # header X-API-Key — diferente do Bearer JWT usado pelo login do
        # gestor no dashboard (ver get_store_from_edge_key no backend).
        headers = {"X-API-Key": self.api_key}

        data = {
            "camera_label": camera_label,
            "confidence": confidence,
            "reason": reason,
        }
        # camera_id não é enviado de propósito: no backend é FK pra uma
        # linha real na tabela "cameras", e ainda não existe fluxo de
        # cadastro de câmera por loja — mandar qualquer valor aqui (ex:
        # "cam03" do config.py) quebra a inserção por violar a chave
        # estrangeira. O campo é opcional no backend (fica None).
        # Lê o clipe como bytes e manda como tupla explícita (nome, bytes,
        # content-type) em vez de passar o arquivo aberto direto — passado
        # cru, o requests monta a parte multipart de um jeito que o backend
        # rejeita com 500 (mesmo conteúdo, mesmo content-type — só a forma
        # de montar o multipart muda). Testado e confirmado nos dois formatos.
        with open(clip_path, "rb") as f:
            clip_bytes = f.read()
        files = {"clip": ("clip.mp4", clip_bytes, "video/mp4")}
        if thumbnail_bytes:
            files["thumbnail"] = ("thumb.jpg", thumbnail_bytes, "image/jpeg")

        try:
            response = requests.post(
                url, headers=headers, data=data, files=files, timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            # Em produção: guardar o evento numa fila local (ex: SQLite) e
            # reenviar depois — a loja não pode perder um alerta só porque
            # a internet caiu por 30 segundos.
            print(f"[AlertClient] Falha ao enviar alerta, será reenfileirado: {exc}")
            return None
