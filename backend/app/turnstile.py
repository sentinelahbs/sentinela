"""
Verificação do Cloudflare Turnstile (CAPTCHA) — confirma que quem está
tentando logar/cadastrar é uma pessoa de verdade, não um script automatizado
tentando muitas combinações (complementa o rate limit, que já existe).
"""

import os
import requests

TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token: str, remote_ip: "str | None" = None) -> bool:
    if not TURNSTILE_SECRET_KEY:
        # Sem chave configurada (ex: ambiente de dev local) — não bloqueia,
        # só não verifica. Em produção a env var sempre estará definida.
        return True
    if not token:
        return False

    data = {"secret": TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        resp = requests.post(VERIFY_URL, data=data, timeout=10)
        resp.raise_for_status()
        return resp.json().get("success", False)
    except requests.RequestException:
        # Se a Cloudflare estiver fora do ar, falha fechado (bloqueia) —
        # melhor recusar um login legítimo por alguns segundos do que
        # abrir a porta pra automação.
        return False
