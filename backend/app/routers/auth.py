from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session
import secrets

from database import get_db
from models import User, Company, Store, UserRole
from rate_limit import limiter
from schemas import LoginIn, TokenOut, SignupIn, SignupOut
from auth import verify_password, hash_password, create_access_token
from email_client import EmailClient

router = APIRouter(prefix="/v1/auth", tags=["auth"])
email_client = EmailClient()


@router.post("/signup", response_model=SignupOut)
@limiter.limit("5/minute")
def signup(request: Request, payload: SignupIn, db: Session = Depends(get_db)):
    """Onboarding de um novo cliente do SaaS: cria a empresa, a primeira
    loja (com sua própria API key pra box de detecção) e o usuário owner,
    tudo numa única chamada — é o que alimenta a tela de cadastro."""

    # payload.email já vem normalizado (schemas.py), mas comparar com
    # func.lower() também cobre contas antigas salvas antes dessa correção.
    existing = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este email")

    company = Company(name=payload.company_name)
    db.add(company)
    db.flush()  # garante company.id antes de usar como FK

    store = Store(
        company_id=company.id,
        name=payload.store_name,
        city=payload.store_city,
        edge_api_key=secrets.token_urlsafe(32),
    )
    db.add(store)

    user = User(
        company_id=company.id,
        name=payload.owner_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.OWNER,
    )
    db.add(user)

    db.commit()
    db.refresh(user)
    db.refresh(store)

    try:
        email_client.send_welcome_email(
            to_email=user.email,
            owner_name=user.name,
            company_name=company.name,
        )
    except Exception as exc:
        # Não falha o cadastro se o provedor de email tiver soluço — a
        # conta já foi criada. Só loga o erro.
        print(f"[auth] Falha ao enviar email de boas-vindas: {exc}")

    token = create_access_token(user_id=user.id, company_id=company.id)
    return SignupOut(access_token=token, store_id=store.id, store_edge_api_key=store.edge_api_key)


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou senha inválidos")

    token = create_access_token(user_id=user.id, company_id=user.company_id)
    return TokenOut(access_token=token)
