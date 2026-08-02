"""
Duas formas de autenticação, porque são dois "clientes" diferentes da API:

1. JWT (login com email/senha) -> usado pelo dashboard web/mobile,
   representa uma PESSOA (gestor).
2. API key por loja -> usada pela box de detecção instalada na loja,
   representa um DISPOSITIVO, não uma pessoa. Não faz sentido pedir login
   humano pra um processo automatizado enviar um alerta.
"""

import os
import datetime
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from database import get_db
from models import User, Store, UserRole
from tenant_context import set_company_context, set_store_lookup

SECRET_KEY = os.environ.get("JWT_SECRET", "TROCAR_EM_PRODUCAO")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, company_id: str) -> str:
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    authorization: Optional[str] = Header(None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")

    # O company_id já vem assinado dentro do próprio token — dá pra
    # liberar o RLS pra essa empresa antes mesmo de consultar o usuário.
    set_company_context(db, payload["company_id"])

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário não encontrado")
    return user


def get_store_from_edge_key(
    store_id: str,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Store:
    """Autentica a BOX de detecção via API key própria da loja (não é a
    mesma credencial usada pelos gestores no dashboard)."""
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key ausente")

    # Ainda não sabemos a empresa dessa loja — libera o RLS só pra essa
    # linha específica (ver tenant_context.set_store_lookup).
    set_store_lookup(db, store_id)

    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None or store.edge_api_key != x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial inválida para esta loja")
    return store


def assert_user_can_access_store(user: User, store: Store):
    """Garante que um gestor só acesse dados da própria empresa/loja —
    é essa checagem que garante o isolamento entre clientes do SaaS.
    Além disso, um STORE_MANAGER só acessa as lojas que foram
    especificamente atribuídas a ele pelo owner; só o OWNER enxerga
    todas as lojas da empresa por padrão."""
    if user.company_id != store.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem acesso a esta loja")

    if user.role == UserRole.STORE_MANAGER:
        assigned = (user.assigned_store_ids or "").split(",")
        if store.id not in assigned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem acesso a esta loja")
