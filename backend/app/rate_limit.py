"""
Limitador de tentativas por IP — módulo separado só pra evitar import
circular entre main.py e os routers que usam o decorator @limiter.limit.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
