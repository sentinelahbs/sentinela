"""
Painel administrativo interno do VigIA — não é o dashboard que os
clientes (mercadinhos) usam. É onde VOCÊ, dono do VigIA, vê todas as
empresas cadastradas, quantas lojas cada uma tem, e o status de cobrança.

Protegido por get_current_admin (auth.py) — só usuários com
is_platform_admin=True acessam. Esse flag não tem endpoint de
auto-promoção de propósito: você liga ele direto no banco para sua
própria conta, a primeira vez.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Company, Store, User, Camera
from schemas import AdminCompanyOut, AdminCompanyDetailOut, AdminOnboardingOut, OnboardingStatusIn
from auth import get_current_admin
from tenant_context import set_platform_admin_context

router = APIRouter(prefix="/v1/admin", tags=["admin"])

ONBOARDING_STATUSES = ("pending", "in_progress", "completed")


def _team_member_out(u: User):
    from schemas import TeamMemberOut
    store_ids = [s for s in (u.assigned_store_ids or "").split(",") if s]
    return TeamMemberOut(id=u.id, name=u.name, email=u.email, role=u.role.value, store_ids=store_ids)


@router.get("/companies", response_model=list[AdminCompanyOut])
def list_companies(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Alimenta a tabela principal do painel admin: todas as empresas
    clientes, com contagem de lojas/usuários e status de cobrança."""
    companies = db.query(Company).order_by(Company.created_at.desc()).all()

    result = []
    for company in companies:
        store_count = db.query(Store).filter(Store.company_id == company.id).count()
        user_count = db.query(User).filter(User.company_id == company.id).count()
        cameras_used = (
            db.query(Camera)
            .join(Store, Camera.store_id == Store.id)
            .filter(Store.company_id == company.id, Camera.active.is_(True))
            .count()
        )
        result.append(AdminCompanyOut(
            id=company.id,
            name=company.name,
            created_at=company.created_at.isoformat(),
            store_count=store_count,
            user_count=user_count,
            subscription_status=company.subscription_status,
            camera_limit=company.camera_limit or 0,
            cameras_used=cameras_used,
        ))
    return result


@router.get("/companies/{company_id}", response_model=AdminCompanyDetailOut)
def get_company_detail(
    company_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Detalhe de uma empresa específica — usado quando você clica numa
    linha da tabela no painel admin, para ver as lojas e a equipe dela."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")

    stores = db.query(Store).filter(Store.company_id == company.id).all()
    users = db.query(User).filter(User.company_id == company.id).all()
    cameras_used = (
        db.query(Camera)
        .join(Store, Camera.store_id == Store.id)
        .filter(Store.company_id == company.id, Camera.active.is_(True))
        .count()
    )

    return AdminCompanyDetailOut(
        id=company.id,
        name=company.name,
        created_at=company.created_at.isoformat(),
        subscription_status=company.subscription_status,
        camera_limit=company.camera_limit or 0,
        cameras_used=cameras_used,
        stores=stores,
        users=[_team_member_out(u) for u in users],
    )


def _onboarding_out(store: Store, company: Company) -> AdminOnboardingOut:
    return AdminOnboardingOut(
        store_id=store.id,
        store_name=store.name,
        company_id=company.id,
        company_name=company.name,
        payment_confirmed_at=company.payment_confirmed_at.isoformat() if company.payment_confirmed_at else None,
        onboarding_status=store.onboarding_status,
        online=store.online,
        last_seen_at=store.last_seen_at.isoformat() if store.last_seen_at else None,
    )


@router.get("/onboarding", response_model=list[AdminOnboardingOut])
def list_onboarding(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Fila de lojas aguardando conexão de câmeras — só empresas com
    pagamento já confirmado, da que está esperando há mais tempo pra
    mais recente (mesma lógica de fila de qualquer painel de suporte)."""
    rows = (
        db.query(Store, Company)
        .join(Company, Store.company_id == Company.id)
        .filter(Company.payment_confirmed_at.isnot(None))
        .filter(Store.onboarding_status != "completed")
        .order_by(Company.payment_confirmed_at.asc())
        .all()
    )
    return [_onboarding_out(store, company) for store, company in rows]


@router.patch("/stores/{store_id}/onboarding", response_model=AdminOnboardingOut)
def update_onboarding_status(
    store_id: str,
    payload: OnboardingStatusIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Botão de avançar/corrigir status na tela de onboarding do admin.
    "completed" só chega aqui por ação manual — nunca automático (ver
    stores.py store_heartbeat), já que câmera online não garante que o
    setup foi validado de verdade (ângulo certo, zona configurada etc.)."""
    if payload.status not in ONBOARDING_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status inválido")

    store = db.query(Store).filter(Store.id == store_id).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loja não encontrada")

    company = db.query(Company).filter(Company.id == store.company_id).first()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")

    # Valores puros: depois do commit() a instância expira, e reler os
    # atributos exigiria um SELECT sob o contexto de admin religado logo
    # abaixo — mais simples guardar antes.
    company_id = company.id
    company_name = company.name
    payment_confirmed_at = company.payment_confirmed_at

    store.onboarding_status = payload.status
    db.commit()
    # commit() encerra a transação e reseta o SET LOCAL setado por
    # get_current_admin — precisa religar antes do refresh() abaixo.
    set_platform_admin_context(db)
    db.refresh(store)

    return AdminOnboardingOut(
        store_id=store.id,
        store_name=store.name,
        company_id=company_id,
        company_name=company_name,
        payment_confirmed_at=payment_confirmed_at.isoformat() if payment_confirmed_at else None,
        onboarding_status=store.onboarding_status,
        online=store.online,
        last_seen_at=store.last_seen_at.isoformat() if store.last_seen_at else None,
    )
