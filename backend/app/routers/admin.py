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
from schemas import AdminCompanyOut, AdminCompanyDetailOut
from auth import get_current_admin

router = APIRouter(prefix="/v1/admin", tags=["admin"])


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

    return AdminCompanyDetailOut(
        id=company.id,
        name=company.name,
        created_at=company.created_at.isoformat(),
        subscription_status=company.subscription_status,
        stores=stores,
        users=[_team_member_out(u) for u in users],
    )
