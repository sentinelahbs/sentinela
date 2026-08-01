"""
Gestão de equipe: o OWNER convida gestores (STORE_MANAGER) por email.

Fluxo:
  1. POST /invite      -> cria um convite pendente + dispara email real com link
  2. GET  /invite/{tk} -> a pessoa convidada abre o link, front busca os
                           detalhes pra mostrar "você foi convidado pra X"
  3. POST /invite/{tk}/accept -> ela define a própria senha, a conta é
                           criada só nesse momento

Isso é mais seguro que gerar uma senha temporária e mostrar na tela do
dono: a senha nunca passa pelas mãos de outra pessoa, e o convite expira
sozinho se não for aceito.
"""

import secrets
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import User, Store, Company, TeamInvite, UserRole
from schemas import (
    TeamInviteIn, TeamInviteOut, TeamMemberOut,
    InviteDetailsOut, InviteAcceptIn, TokenOut,
)
from auth import get_current_user, hash_password, create_access_token
from email_client import EmailClient

router = APIRouter(prefix="/v1/team", tags=["team"])
email_client = EmailClient()

INVITE_EXPIRY_DAYS = 7


def _to_member_out(user: User) -> TeamMemberOut:
    store_ids = [s for s in (user.assigned_store_ids or "").split(",") if s]
    return TeamMemberOut(
        id=user.id, name=user.name, email=user.email,
        role=user.role.value, store_ids=store_ids, status="active",
    )


def _pending_invite_out(invite: TeamInvite) -> TeamMemberOut:
    store_ids = [s for s in (invite.store_ids or "").split(",") if s]
    return TeamMemberOut(
        id=invite.id, name=invite.name, email=invite.email,
        role=UserRole.STORE_MANAGER.value, store_ids=store_ids, status="pending",
    )


@router.get("", response_model=list[TeamMemberOut])
def list_team(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista membros ativos + convites ainda pendentes (não aceitos),
    pra tela de Equipe mostrar tudo num lugar só."""
    members = db.query(User).filter(User.company_id == user.company_id).all()

    now = datetime.datetime.utcnow()
    pending = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.company_id == user.company_id,
            TeamInvite.accepted_at.is_(None),
            TeamInvite.expires_at > now,
        )
        .all()
    )

    return [_to_member_out(m) for m in members] + [_pending_invite_out(i) for i in pending]


@router.post("/invite", response_model=TeamInviteOut)
def invite_manager(
    payload: TeamInviteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode convidar gestores")

    if not payload.store_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecione ao menos uma loja para o gestor")

    valid_stores = (
        db.query(Store.id)
        .filter(Store.company_id == user.company_id, Store.id.in_(payload.store_ids))
        .all()
    )
    if {s.id for s in valid_stores} != set(payload.store_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uma ou mais lojas informadas são inválidas")

    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este email")

    existing_invite = (
        db.query(TeamInvite)
        .filter(func.lower(TeamInvite.email) == payload.email, TeamInvite.accepted_at.is_(None))
        .first()
    )
    if existing_invite:
        db.delete(existing_invite)  # reenviar convite substitui o anterior

    company = db.query(Company).filter(Company.id == user.company_id).first()

    invite = TeamInvite(
        company_id=user.company_id,
        name=payload.name,
        email=payload.email,
        store_ids=",".join(payload.store_ids),
        token=secrets.token_urlsafe(32),
        invited_by_user_id=user.id,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    try:
        email_client.send_invite_email(
            to_email=invite.email,
            invited_name=invite.name,
            company_name=company.name,
            token=invite.token,
        )
    except Exception as exc:
        # Não falha o convite inteiro se o provedor de email tiver soluço —
        # o registro já existe, dá pra reenviar depois. Só loga o erro.
        print(f"[team] Falha ao enviar email de convite: {exc}")

    return TeamInviteOut(id=invite.id, name=invite.name, email=invite.email)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team_member(
    user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if user.role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas o dono da conta pode remover gestores")

    target = db.query(User).filter(User.id == user_id, User.company_id == user.company_id).first()
    if target is not None:
        if target.role == UserRole.OWNER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não é possível remover o dono da conta")
        db.delete(target)
        db.commit()
        return

    # também permite cancelar um convite ainda pendente (mesmo botão de remover na UI)
    invite = db.query(TeamInvite).filter(
        TeamInvite.id == user_id, TeamInvite.company_id == user.company_id
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário ou convite não encontrado")
    db.delete(invite)
    db.commit()


# --- Endpoints públicos (a pessoa convidada ainda não tem conta/token) ----

invite_router = APIRouter(prefix="/v1/invites", tags=["team"])


@invite_router.get("/{token}", response_model=InviteDetailsOut)
def get_invite_details(token: str, db: Session = Depends(get_db)):
    invite = db.query(TeamInvite).filter(TeamInvite.token == token).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convite não encontrado")
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este convite já foi utilizado")
    if invite.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este convite expirou — peça um novo")

    company = db.query(Company).filter(Company.id == invite.company_id).first()
    store_ids = [s for s in (invite.store_ids or "").split(",") if s]
    stores = db.query(Store).filter(Store.id.in_(store_ids)).all()

    return InviteDetailsOut(
        name=invite.name,
        email=invite.email,
        company_name=company.name,
        store_names=[s.name for s in stores],
    )


@invite_router.post("/{token}/accept", response_model=TokenOut)
def accept_invite(token: str, payload: InviteAcceptIn, db: Session = Depends(get_db)):
    invite = db.query(TeamInvite).filter(TeamInvite.token == token).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convite não encontrado")
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este convite já foi utilizado")
    if invite.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este convite expirou — peça um novo")

    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A senha precisa ter ao menos 8 caracteres")

    user = User(
        company_id=invite.company_id,
        name=invite.name,
        email=invite.email,
        password_hash=hash_password(payload.password),
        role=UserRole.STORE_MANAGER,
        assigned_store_ids=invite.store_ids,
    )
    db.add(user)
    invite.accepted_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(user)

    token_value = create_access_token(user_id=user.id, company_id=user.company_id)
    return TokenOut(access_token=token_value)
