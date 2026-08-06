import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import User, Company, Store, UserRole, PasswordResetToken
from rate_limit import limiter, get_client_ip
from schemas import (
    LoginIn, TokenOut, SignupIn, SignupOut, MeOut,
    ForgotPasswordIn, ForgotPasswordOut, ResetPasswordIn,
)
from auth import verify_password, hash_password, create_access_token, get_current_user
from email_client import EmailClient
from turnstile import verify_turnstile
from tenant_context import set_auth_bootstrap, set_company_context, set_password_reset_lookup

router = APIRouter(prefix="/v1/auth", tags=["auth"])
email_client = EmailClient()

RESET_TOKEN_EXPIRY_HOURS = 1


@router.post("/signup", response_model=SignupOut)
@limiter.limit("5/minute")
def signup(request: Request, payload: SignupIn, db: Session = Depends(get_db)):
    """Onboarding de um novo cliente do SaaS: cria a empresa, a primeira
    loja (com sua própria API key pra box de detecção) e o usuário owner,
    tudo numa única chamada — é o que alimenta a tela de cadastro."""

    if not verify_turnstile(payload.turnstile_token, get_client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verificação de segurança falhou — tente novamente")

    # Checagem de duplicidade precisa enxergar TODAS as empresas (email é
    # único globalmente) — ainda não existe uma empresa/JWT nesse momento.
    set_auth_bootstrap(db)

    # payload.email já vem normalizado (schemas.py), mas comparar com
    # func.lower() também cobre contas antigas salvas antes dessa correção.
    existing = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este email")

    company = Company(name=payload.company_name)
    db.add(company)
    db.flush()  # garante company.id antes de usar como FK
    # Guarda como valor puro: depois do commit() a instância expira, e
    # reler company.id nesse ponto dispararia um SELECT bloqueado pelo
    # RLS (ninguém religou o contexto ainda — é justamente isso que
    # set_company_context faz logo abaixo).
    company_id = company.id

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
    # commit() encerra a transação, e junto com ela o SET LOCAL de mais
    # acima — sem isso o RLS não deixaria o refresh() abaixo enxergar as
    # linhas que acabamos de criar (user e store são da mesma company).
    set_company_context(db, company_id)
    db.refresh(user)
    db.refresh(store)

    try:
        email_client.send_welcome_email(
            to_email=user.email,
            owner_name=user.name,
            company_name=payload.company_name,
        )
    except Exception as exc:
        # Não falha o cadastro se o provedor de email tiver soluço — a
        # conta já foi criada. Só loga o erro.
        print(f"[auth] Falha ao enviar email de boas-vindas: {exc}")

    token = create_access_token(user_id=user.id, company_id=company_id)
    return SignupOut(access_token=token, store_id=store.id, store_edge_api_key=store.edge_api_key)


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    if not verify_turnstile(payload.turnstile_token, get_client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verificação de segurança falhou — tente novamente")

    # Login busca o usuário pelo email antes de saber a empresa dele —
    # é justamente essa consulta que descobre isso.
    set_auth_bootstrap(db)

    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou senha inválidos")

    token = create_access_token(user_id=user.id, company_id=user.company_id)
    return TokenOut(access_token=token)


@router.post("/forgot-password", response_model=ForgotPasswordOut)
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Pedido de redefinição de senha. Endpoint público (quem chama ainda
    não conseguiu entrar na própria conta) — por isso a resposta é
    sempre a mesma mensagem genérica, exista ou não conta com esse email:
    sem isso, dava pra descobrir quais emails têm cadastro só testando
    aqui (enumeração de usuários)."""
    generic_message = "Se existir uma conta com este email, enviaremos as instruções para redefinir a senha."

    # Busca por email sem ainda saber a empresa — mesmo bootstrap do login.
    set_auth_bootstrap(db)
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if user is None:
        return ForgotPasswordOut(detail=generic_message)

    company_id = user.company_id
    user_id = user.id
    user_name = user.name
    user_email = user.email

    set_company_context(db, company_id)

    # Um pedido novo invalida qualquer token anterior ainda não usado —
    # mesmo padrão do convite de equipe (reenviar substitui o anterior).
    old_tokens = db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
    ).all()
    for old in old_tokens:
        db.delete(old)

    # Valor puro: depois do commit() a instância expira, e reler
    # reset_token.token exigiria um SELECT que o RLS ainda não liberou
    # nesse instante — mais simples guardar o valor antes de inserir.
    token_value = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        company_id=company_id,
        user_id=user_id,
        token=token_value,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=RESET_TOKEN_EXPIRY_HOURS),
    )
    db.add(reset_token)
    db.commit()

    try:
        email_client.send_password_reset_email(
            to_email=user_email,
            name=user_name,
            token=token_value,
            app=payload.app,
        )
    except Exception as exc:
        # Não falha o pedido se o provedor de email tiver soluço — o
        # token já existe, dá pra pedir de novo. Só loga o erro.
        print(f"[auth] Falha ao enviar email de redefinição de senha: {exc}")

    return ForgotPasswordOut(detail=generic_message)


@router.post("/reset-password", response_model=TokenOut)
@limiter.limit("10/minute")
def reset_password(request: Request, payload: ResetPasswordIn, db: Session = Depends(get_db)):
    # Quem chama ainda não tem conta acessível — a posse do token é a
    # credencial (igual ao aceite de convite).
    set_password_reset_lookup(db, payload.token)

    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token == payload.token).first()
    if reset_token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link de redefinição inválido")
    if reset_token.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link já foi utilizado")
    if reset_token.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link expirou — peça uma nova redefinição")

    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A senha precisa ter ao menos 8 caracteres")

    # Valores puros: depois do commit() a instância expira, e reler
    # user_id/company_id exigiria um SELECT que o RLS ainda não liberou
    # nesse instante (o token só prova acesso a essa linha específica).
    user_id = reset_token.user_id
    company_id = reset_token.company_id

    # O token de reset só prova acesso à própria linha em
    # password_reset_tokens — libera o contexto da empresa antes do
    # UPDATE de password_hash no usuário, logo abaixo (mesma transação).
    set_company_context(db, company_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")

    user.password_hash = hash_password(payload.password)
    reset_token.used_at = datetime.datetime.utcnow()
    db.commit()

    token_value = create_access_token(user_id=user_id, company_id=company_id)
    return TokenOut(access_token=token_value)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    """Usado pelo frontend para saber, logo após o login, se essa pessoa
    tem acesso ao painel administrativo interno (is_platform_admin) —
    decide se mostra o link para o admin ou não."""
    return MeOut(
        id=user.id, name=user.name, email=user.email,
        role=user.role.value, is_platform_admin=user.is_platform_admin,
    )
