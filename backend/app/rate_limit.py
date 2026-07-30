"""
Limitador de tentativas por IP — módulo separado só pra evitar import
circular entre main.py e os routers que usam o decorator @limiter.limit.
"""

from slowapi import Limiter
from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    # Atrás do proxy/edge do Railway, request.client.host é o endereço
    # interno do proxy, não o do cliente de verdade — por isso lemos o
    # X-Forwarded-For (padrão nesse tipo de hospedagem).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)
