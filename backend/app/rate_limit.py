"""
Limitador de tentativas por IP — módulo separado só pra evitar import
circular entre main.py e os routers que usam o decorator @limiter.limit.
"""

import os

from slowapi import Limiter
from starlette.requests import Request


def _parse_trusted_hop_count() -> int:
    # Quantos hops de proxy confiáveis existem entre a internet e essa
    # app (cada um deles anexando uma entrada ao X-Forwarded-For). O
    # default é 1 porque, com o binding em 127.0.0.1 do docker-compose.yml
    # (ver DEPLOY.md), há sempre exatamente um hop confiável em todo
    # caminho de deploy documentado nesse repo -- o edge da própria
    # Railway/Render/Fly, ou o Caddy/Traefik self-managed rodando no
    # mesmo host/rede Docker. Um default 0 quebraria o rate limiting e o
    # relato de IP pro Turnstile em toda instalação atual, sem nenhuma
    # ação do operador. Quem tiver mais de um proxy na frente (ex:
    # CDN + load balancer + reverse proxy) precisa aumentar esse valor.
    raw = os.environ.get("TRUSTED_HOP_COUNT", "1")
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return 1
    # Negativo não faz sentido -- não deixa a app cair por causa disso,
    # só trata como "não confia em nenhum hop" (equivalente a 0).
    return max(value, 0)


TRUSTED_HOP_COUNT = _parse_trusted_hop_count()


def get_client_ip(request: Request) -> str:
    # Atrás do proxy/edge (Railway, ou o reverse proxy self-managed --
    # ver DEPLOY.md), request.client.host é o endereço interno do
    # proxy, não o do cliente de verdade -- por isso lemos o
    # X-Forwarded-For. Só confiamos nele, porém, na medida do
    # TRUSTED_HOP_COUNT configurado: pegamos a entrada escrita pelo hop
    # confiável mais externo (posição -TRUSTED_HOP_COUNT a partir do
    # fim da lista), nunca a primeira entrada, que qualquer cliente
    # pode forjar livremente. Isso só é seguro porque o container só é
    # alcançável através desse(s) hop(s) confiável(is) -- nunca
    # diretamente da internet (ver o binding em 127.0.0.1 no
    # docker-compose.yml e o Security Group exigido em DEPLOY.md pro
    # caminho ECS/Fargate).
    fallback = request.client.host if request.client else "unknown"

    if TRUSTED_HOP_COUNT < 1:
        return fallback

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return fallback

    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if len(hops) < TRUSTED_HOP_COUNT:
        return fallback

    return hops[-TRUSTED_HOP_COUNT]


limiter = Limiter(key_func=get_client_ip)
