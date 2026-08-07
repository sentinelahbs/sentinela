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
from fastapi import Depends, HTTPException, status, Header, Request, Response
from sqlalchemy.orm import Session

from database import get_db
from models import User, Store, UserRole
from schemas import MeOut
from tenant_context import set_company_context, set_store_lookup, set_platform_admin_context

SECRET_KEY = os.environ.get("JWT_SECRET", "TROCAR_EM_PRODUCAO")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Cookie de sessão ---------------------------------------------------
#
# O JWT deixou de ser devolvido no corpo da resposta (login/signup/reset
# de senha/aceite de convite) e passou a viajar só como cookie HttpOnly —
# assim um XSS no front não consegue ler o token nem via JS nem lendo a
# resposta do próprio fetch de login.
#
# COOKIE_SAMESITE fica "none" por padrão porque o painel admin roda num
# domínio separado do da API (não é subdomínio de vigialoja.com.br) —
# pro navegador isso é cross-site, e só "None" garante que o cookie seja
# enviado nessas chamadas. Em dev local, dashboard/admin/backend rodam
# todos em "localhost" (portas diferentes), que o navegador já trata como
# same-site entre si — dá pra usar "lax" ali sem perder cobertura de teste
# nesse aspecto (só o caminho cross-site de verdade, exclusivo do admin
# em produção, não dá pra validar localmente).
COOKIE_NAME = "vigia_token"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "none").lower()
# SameSite=None sem Secure é rejeitado silenciosamente pelo navegador —
# força Secure=True nesse caso pra não deixar uma config incompleta
# quebrar o cookie sem avisar.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true" or COOKIE_SAMESITE == "none"


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME, path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        httponly=True,
    )


def require_csrf_header(request: Request) -> None:
    """Defesa contra CSRF pros endpoints que setam ou dependem do cookie
    de sessão. Necessário porque COOKIE_SAMESITE=none (exigido pelo
    painel admin, que roda num domínio diferente da API) faz o navegador
    mandar o cookie mesmo em requisições disparadas por outro site.

    Um <form> ou fetch "simples" de outro site não consegue adicionar
    este header; uma tentativa via fetch com header customizado vira uma
    requisição cross-origin "não simples", que passa pelo preflight do
    CORS — já restrito a ALLOWED_ORIGINS (ver main.py)."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requisição bloqueada (proteção CSRF)")


def user_to_me_out(user: User) -> MeOut:
    """Compartilhado entre login, signup, reset de senha e aceite de
    convite — todos devolvem o mesmo formato pra quem chamou saber quem
    acabou de autenticar, sem precisar de uma segunda chamada a /me."""
    return MeOut(
        id=user.id, name=user.name, email=user.email,
        role=user.role.value, is_platform_admin=user.is_platform_admin,
    )


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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    require_csrf_header(request)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão ausente")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida")

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


def get_current_admin(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Para o painel administrativo interno do VigIA — só quem tem
    is_platform_admin=True (sua equipe, não clientes) passa daqui.
    O flag é ligado direto no banco por você mesmo, não existe endpoint
    de auto-promoção."""
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso restrito à equipe do VigIA")
    # Libera a visão de todas as empresas/lojas/usuários pro painel admin
    # (ver tenant_context.set_platform_admin_context e a migração de RLS).
    set_platform_admin_context(db)
    return user
